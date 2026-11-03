"""A receber pago por uma receita (052, services/sharing.py `link_income()`).

Dono, 2026-11-02: o tio pagou R$ 300 por um fone de R$ 230,28 comprado no
cartao para ele. Marcar o item como pago abate da receita: so R$ 69,72 e do
dono. Com a receita escolhida o abatimento fica nela, no mes dela; sem, no mes
em que foi marcado, e o repasse de uma pessoa nunca cobre o que outra pagou.
"""

import importlib
from datetime import datetime, timedelta, timezone

import pytest

BRT = timezone(timedelta(hours=-3))


def this_month():
    return datetime.now(BRT).strftime("%Y-%m")


@pytest.fixture()
def account(client, auth):
    return client.post("/api/accounts", json={"name": "Banco", "type": "CHECKING"}, headers=auth).get_json()["id"]


def income(client, auth, account, amount, day, description="Pix de A. F. R. Corretora"):
    response = client.post("/api/transactions", headers=auth, json={
        "account_id": account, "amount": amount, "date": day, "type": "INCOME",
        "category": "Receita", "description": description,
    })
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["id"]


def purchase_for(client, auth, person, total=230.28, day="2026-03-01"):
    card = client.post(
        "/api/credit-cards", headers=auth, json={"name": "Cartao", "due_day": 10, "closing_day": 3},
    ).get_json()
    card = card[0] if isinstance(card, list) else card
    response = client.post("/api/cc-expenses/purchases", headers=auth, json={
        "card_id": card["id"], "category": "Compras", "description": "Ali Express",
        "total_amount": total, "purchase_date": day, "installments": 1,
    })
    assert response.status_code == 201, response.get_data(as_text=True)
    expense = [row for row in client.get("/api/cc-expenses", headers=auth).get_json() if row["card_id"] == card["id"]][0]
    shared = client.patch(f"/api/cc-expenses/{expense['id']}/share", headers=auth, json={
        "share_mode": "OTHERS", "share_person": person,
    })
    assert shared.status_code == 200, shared.get_data(as_text=True)
    return expense["id"]


def expense_for(client, auth, account, person, amount, day):
    response = client.post("/api/transactions", headers=auth, json={
        "account_id": account, "amount": amount, "date": day, "type": "EXPENSE", "category": "Alimentação",
    })
    row = response.get_json()["id"]
    client.patch(f"/api/transactions/{row}", headers=auth, json={"share_mode": "OTHERS", "share_person": person})
    return row


def settle(client, auth, settled=True, **ids):
    response = client.post("/api/receivables/settle", headers=auth, json={"settled": settled, **ids})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def flow(user, month):
    home = importlib.import_module("services.home")
    accounts = importlib.import_module("services.accounts")
    db = importlib.import_module("db")
    with db.get_db() as conn:
        listed = [dict(row) for row in accounts.account_balance_rows(conn, user["id"])]
        return home.monthly_flow(conn, user["id"], listed, [month])[0]


def row_of(row_id):
    db = importlib.import_module("db")
    with db.get_db() as conn:
        return dict(conn.execute("SELECT * FROM transactions WHERE id = ?", (row_id,)).fetchone())


def test_the_paying_income_keeps_only_the_change(client, auth, user, account):
    pix = income(client, auth, account, 300, "2026-03-02")
    item = purchase_for(client, auth, "Tio Toninho")
    assert settle(client, auth, cc_expense_ids=[item], income_id=pix)["updated"] == 1

    march = flow(user, "2026-03")
    assert (march["income"], march["others_received"]) == (69.72, 230.28)
    assert (march["expense"], march["others_paid"]) == (0, 230.28)
    saved = row_of(pix)
    assert (saved["share_mode"], saved["share_others_amount"], saved["share_person"]) == ("SPLIT", 230.28, "Tio Toninho")
    [listed] = client.get("/api/receivables?include_settled=1", headers=auth).get_json()
    assert listed["paid_by"] == {"id": pix, "date": "2026-03-02", "description": "Pix de A. F. R. Corretora", "amount": 300}


def test_no_second_cut_in_the_month_it_was_marked(client, auth, user, account):
    pix = income(client, auth, account, 300, "2026-03-02")
    income(client, auth, account, 1000, f"{this_month()}-01", "Salario")
    item = purchase_for(client, auth, "Tio")
    settle(client, auth, cc_expense_ids=[item], income_id=pix)
    assert flow(user, this_month())["income"] == 1000


def test_undoing_gives_the_income_back(client, auth, user, account):
    pix = income(client, auth, account, 300, "2026-03-02")
    item = purchase_for(client, auth, "Tio")
    settle(client, auth, cc_expense_ids=[item], income_id=pix)
    settle(client, auth, settled=False, cc_expense_ids=[item])
    assert flow(user, "2026-03")["income"] == 300
    saved = row_of(pix)
    assert (saved["share_mode"], saved["share_person"], saved["share_settled_at"]) == (None, None, None)


def test_a_smaller_income_is_all_of_theirs(client, auth, user, account):
    pix = income(client, auth, account, 200, "2026-03-02")
    item = purchase_for(client, auth, "Tio")
    settle(client, auth, cc_expense_ids=[item], income_id=pix)
    assert row_of(pix)["share_mode"] == "OTHERS"
    assert flow(user, "2026-03")["income"] == 0


def test_two_items_on_one_pix(client, auth, user, account):
    pix = income(client, auth, account, 300, "2026-03-02")
    first = expense_for(client, auth, account, "Tio", 100, "2026-03-01")
    second = expense_for(client, auth, account, "Tio", 50, "2026-03-01")
    settle(client, auth, transaction_ids=[first, second], income_id=pix)
    assert row_of(pix)["share_others_amount"] == 150
    settle(client, auth, settled=False, transaction_ids=[second])
    assert row_of(pix)["share_others_amount"] == 100


def test_without_an_income_the_cut_is_the_month_it_was_marked(client, auth, user, account):
    income(client, auth, account, 300, f"{this_month()}-01")
    item = purchase_for(client, auth, "Tio")
    settle(client, auth, cc_expense_ids=[item])
    assert flow(user, this_month())["income"] == 69.72


def test_one_persons_repasse_never_covers_another(client, auth, user, account):
    """O caso de producao: os repasses do pai cobriam o que o tio pagou."""
    month = this_month()
    father = income(client, auth, account, 500, f"{month}-01", "Pai")
    client.post("/api/review", headers=auth, json={"items": [
        {"table": "transactions", "id": father, "repasse": True, "person": "Pai"},
    ]})
    income(client, auth, account, 300, f"{month}-01")
    item = purchase_for(client, auth, "Tio")
    settle(client, auth, cc_expense_ids=[item])
    assert flow(user, month)["income"] == 69.72


def test_a_repasse_of_the_same_person_covers_it(client, auth, user, account):
    month = this_month()
    uncle = income(client, auth, account, 230.28, f"{month}-01", "Tio")
    client.post("/api/review", headers=auth, json={"items": [
        {"table": "transactions", "id": uncle, "repasse": True, "person": "tio "},
    ]})
    income(client, auth, account, 300, f"{month}-01")
    item = purchase_for(client, auth, "Tio")
    settle(client, auth, cc_expense_ids=[item])
    assert flow(user, month)["income"] == 300


def test_candidates_are_reais_incomes_with_room(client, auth, account, other_user):
    pix = income(client, auth, account, 300, "2026-03-02")
    income(client, auth, account, 50, "2026-02-01", "Antiga")
    item = purchase_for(client, auth, "Tio")

    def listed():
        response = client.get("/api/receivables/incomes?since=2026-03-01", headers=auth)
        assert response.status_code == 200, response.get_data(as_text=True)
        return {row["id"]: row["room"] for row in response.get_json()}

    assert listed() == {pix: 300}
    settle(client, auth, cc_expense_ids=[item], income_id=pix)
    assert listed() == {pix: 69.72}
    assert client.get("/api/receivables/incomes?since=2026-03-01", headers=other_user["headers"]).get_json() == []
    assert client.get("/api/receivables/incomes?since=ontem", headers=auth).status_code == 400


def test_the_income_must_be_an_income_of_the_owner(client, auth, account, other_user):
    item = purchase_for(client, auth, "Tio")
    spent = expense_for(client, auth, account, "Tio", 10, "2026-03-01")
    for bad in (spent, "nao-existe"):
        response = client.post("/api/receivables/settle", headers=auth, json={"cc_expense_ids": [item], "income_id": bad})
        assert response.status_code == 400
    assert client.get("/api/receivables", headers=auth).get_json()[0]["settled_at"] is None
