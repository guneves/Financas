"""De quem e o gasto (032, services/sharing.py) e "A receber".

Um lancamento ou compra no cartao pode ser de outra pessoa, inteiro ou em
parte, sempre com o nome dela. O saldo nao muda; o orcamento e o plano do mes
contam so a parte do dono; a parte dos outros de uma despesa fica em "A
receber" ate o dono marcar que a pessoa pagou.
"""

import importlib
from datetime import date

import pytest


def create_transaction(client, headers, **overrides):
    payload = {
        "amount": 80,
        "date": "2026-03-10",
        "category": "Alimentação",
        "description": "Pizza",
        "type": "EXPENSE",
    }
    payload.update(overrides)
    response = client.post("/api/transactions", json=payload, headers=headers)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def patch(client, headers, item_id, payload):
    return client.patch(f"/api/transactions/{item_id}", json=payload, headers=headers)


def create_purchase(client, headers, total=300, installments=3, purchase_date="2026-03-05"):
    card = client.post(
        "/api/credit-cards", headers=headers, json={"name": "Cartao", "due_day": 10, "closing_day": 3},
    ).get_json()
    card = card[0] if isinstance(card, list) else card
    response = client.post("/api/cc-expenses/purchases", headers=headers, json={
        "card_id": card["id"], "category": "Alimentação", "description": "Restaurante",
        "total_amount": total, "purchase_date": purchase_date, "installments": installments,
    })
    assert response.status_code == 201, response.get_data(as_text=True)
    rows = client.get("/api/cc-expenses", headers=headers).get_json()
    return [row for row in rows if row["card_id"] == card["id"]]


def receivables(client, headers, **query):
    response = client.get("/api/receivables", headers=headers, query_string=query)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


# --------------------------------------------------------------------------
# Marcar um lancamento
# --------------------------------------------------------------------------


def test_split_stores_the_others_part_and_the_person(client, auth):
    item = create_transaction(client, auth)
    response = patch(client, auth, item["id"], {
        "share_mode": "SPLIT", "share_others_amount": 40.005, "share_person": " Ana ",
    })
    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert body["share_mode"] == "SPLIT"
    assert body["share_others_amount"] == 40.01  # ROUND_HALF_UP
    assert body["share_person"] == "Ana"
    assert body["share_settled_at"] is None
    assert body["amount"] == 80  # o valor do lancamento nao muda


def test_others_needs_no_amount(client, auth):
    item = create_transaction(client, auth)
    body = patch(client, auth, item["id"], {"share_mode": "OTHERS", "share_person": "Bruno"}).get_json()
    assert body["share_mode"] == "OTHERS"
    assert body["share_others_amount"] is None


@pytest.mark.parametrize("payload, message", [
    ({"share_mode": "SPLIT", "share_others_amount": 40}, "nome"),
    ({"share_mode": "OTHERS", "share_person": "  "}, "nome"),
    ({"share_mode": "SPLIT", "share_person": "Ana"}, "Parte"),
    ({"share_mode": "SPLIT", "share_person": "Ana", "share_others_amount": 80}, "menor"),
    ({"share_mode": "SPLIT", "share_person": "Ana", "share_others_amount": 0}, "Parte"),
    ({"share_mode": "HALF", "share_person": "Ana"}, "invalida"),
])
def test_invalid_shares_are_refused(client, auth, payload, message):
    item = create_transaction(client, auth)
    response = patch(client, auth, item["id"], payload)
    assert response.status_code == 400
    assert message in response.get_json()["error"]


def test_back_to_mine_clears_everything(client, auth):
    item = create_transaction(client, auth)
    patch(client, auth, item["id"], {"share_mode": "OTHERS", "share_person": "Ana"})
    client.post("/api/receivables/settle", headers=auth, json={"transaction_ids": [item["id"]]})
    body = patch(client, auth, item["id"], {"share_mode": None}).get_json()
    assert body["share_mode"] is None
    assert body["share_person"] is None
    assert body["share_settled_at"] is None


def test_lowering_the_amount_below_the_others_part_is_refused(client, auth):
    item = create_transaction(client, auth)
    patch(client, auth, item["id"], {"share_mode": "SPLIT", "share_others_amount": 50, "share_person": "Ana"})
    response = patch(client, auth, item["id"], {"amount": 40})
    assert response.status_code == 400
    # Junto com uma divisao nova, passa.
    response = patch(client, auth, item["id"], {
        "amount": 40, "share_mode": "SPLIT", "share_others_amount": 20, "share_person": "Ana",
    })
    assert response.status_code == 200


def test_investment_and_transfer_cannot_be_shared(client, auth):
    aporte = create_transaction(client, auth, category="Investimento")
    response = patch(client, auth, aporte["id"], {"share_mode": "OTHERS", "share_person": "Ana"})
    assert response.status_code == 400

    accounts = [
        client.post("/api/accounts", headers=auth, json={"name": name, "type": "CHECKING"}).get_json()
        for name in ("A", "B")
    ]
    transfer = client.post("/api/transfers", headers=auth, json={
        "amount": 10, "date": "2026-03-01",
        "account_id": accounts[0]["id"], "transfer_account_id": accounts[1]["id"],
    }).get_json()
    response = patch(client, auth, transfer["id"], {"share_mode": "OTHERS", "share_person": "Ana"})
    assert response.status_code == 400


def test_sharing_leaves_the_account_balance_alone(client, auth):
    account = client.post("/api/accounts", headers=auth, json={
        "name": "Conta", "type": "CHECKING", "initial_balance": 100,
    }).get_json()
    item = create_transaction(client, auth, account_id=account["id"])
    patch(client, auth, item["id"], {"share_mode": "OTHERS", "share_person": "Ana"})
    accounts = client.get("/api/accounts", headers=auth).get_json()
    assert next(a for a in accounts if a["id"] == account["id"])["balance"] == 20


def test_other_user_cannot_share_my_transaction(client, auth, other_user):
    item = create_transaction(client, auth)
    response = patch(client, other_user["headers"], item["id"], {"share_mode": "OTHERS", "share_person": "X"})
    assert response.status_code == 404


# --------------------------------------------------------------------------
# Compra no cartao
# --------------------------------------------------------------------------


def test_purchase_split_goes_to_every_installment_and_adds_up(client, auth):
    rows = create_purchase(client, auth, total=100, installments=3)
    response = client.patch(f"/api/cc-expenses/{rows[1]['id']}/share", headers=auth, json={
        "share_mode": "SPLIT", "share_others_amount": 50, "share_person": "Ana",
    })
    assert response.status_code == 200, response.get_data(as_text=True)
    updated = response.get_json()
    assert len(updated) == 3
    assert all(row["share_mode"] == "SPLIT" and row["share_person"] == "Ana" for row in updated)
    shares = [row["share_others_amount"] for row in updated]
    assert round(sum(shares), 2) == 50
    assert all(share <= row["amount"] for share, row in zip(shares, updated))


def test_purchase_share_validates_against_the_purchase_total(client, auth):
    rows = create_purchase(client, auth, total=90, installments=3)
    response = client.patch(f"/api/cc-expenses/{rows[0]['id']}/share", headers=auth, json={
        "share_mode": "SPLIT", "share_others_amount": 60, "share_person": "Ana",
    })
    assert response.status_code == 200  # 60 < 90, mesmo maior que uma parcela
    response = client.patch(f"/api/cc-expenses/{rows[0]['id']}/share", headers=auth, json={
        "share_mode": "SPLIT", "share_others_amount": 90, "share_person": "Ana",
    })
    assert response.status_code == 400


def test_purchase_share_is_per_user(client, auth, other_user):
    rows = create_purchase(client, auth)
    response = client.patch(f"/api/cc-expenses/{rows[0]['id']}/share", headers=other_user["headers"], json={
        "share_mode": "OTHERS", "share_person": "X",
    })
    assert response.status_code == 404


# --------------------------------------------------------------------------
# A receber
# --------------------------------------------------------------------------


def test_receivables_list_pending_until_settled(client, auth):
    pizza = create_transaction(client, auth)
    patch(client, auth, pizza["id"], {"share_mode": "SPLIT", "share_others_amount": 40, "share_person": "Ana"})
    rows = create_purchase(client, auth, total=300, installments=3)
    client.patch(f"/api/cc-expenses/{rows[0]['id']}/share", headers=auth, json={
        "share_mode": "OTHERS", "share_person": "Bruno",
    })
    salario = create_transaction(client, auth, type="INCOME", category="Salário", amount=100)
    patch(client, auth, salario["id"], {"share_mode": "OTHERS", "share_person": "Carla"})

    items = receivables(client, auth)
    by_person = {item["person"]: item for item in items}
    assert set(by_person) == {"Ana", "Bruno"}  # receita nao e "a receber"
    assert by_person["Ana"]["others_amount"] == 40
    assert by_person["Bruno"]["kind"] == "CARD_PURCHASE"
    assert by_person["Bruno"]["others_amount"] == 300  # a compra inteira, um item so

    response = client.post("/api/receivables/settle", headers=auth, json={
        "transaction_ids": [pizza["id"]], "cc_expense_ids": [rows[2]["id"]],
    })
    assert response.status_code == 200
    assert response.get_json()["updated"] == 2
    assert receivables(client, auth) == []
    settled = receivables(client, auth, include_settled="1")
    assert len(settled) == 2 and all(item["settled_at"] for item in settled)

    client.post("/api/receivables/settle", headers=auth, json={"transaction_ids": [pizza["id"]], "settled": False})
    assert [item["person"] for item in receivables(client, auth)] == ["Ana"]


def test_settle_requires_items_and_ignores_other_users(client, auth, other_user):
    assert client.post("/api/receivables/settle", headers=auth, json={}).status_code == 400
    pizza = create_transaction(client, auth)
    patch(client, auth, pizza["id"], {"share_mode": "OTHERS", "share_person": "Ana"})
    response = client.post("/api/receivables/settle", headers=other_user["headers"], json={
        "transaction_ids": [pizza["id"]],
    })
    assert response.get_json()["updated"] == 0
    assert receivables(client, other_user["headers"]) == []
    assert len(receivables(client, auth)) == 1


# --------------------------------------------------------------------------
# Orcamento e plano do mes: so a parte do dono
# --------------------------------------------------------------------------


def test_budget_counts_only_the_owner_part(client, auth):
    categories = {item["name"]: item for item in client.get("/api/categories", headers=auth).get_json()}
    alimentacao = categories["Alimentação"]
    client.post("/api/budgets", headers=auth, json={
        "category_id": alimentacao["id"], "month": "2026-03", "planned_percent": 10,
    })
    pizza = create_transaction(client, auth, category_id=alimentacao["id"])
    patch(client, auth, pizza["id"], {"share_mode": "SPLIT", "share_others_amount": 60, "share_person": "Ana"})
    jantar = create_transaction(client, auth, category_id=alimentacao["id"], amount=50)
    patch(client, auth, jantar["id"], {"share_mode": "OTHERS", "share_person": "Bruno"})
    rows = create_purchase(client, auth, total=90, installments=3)
    client.patch(f"/api/cc-expenses/{rows[0]['id']}/share", headers=auth, json={
        "share_mode": "SPLIT", "share_others_amount": 30, "share_person": "Ana",
    })

    month = client.get("/api/budgets", headers=auth, query_string={"month": "2026-03"}).get_json()
    item = next(entry for entry in month["items"] if entry["category_name"] == "Alimentação")
    assert item["spent"] == 20 + 0 + 60


def test_monthly_plan_counts_only_the_owner_part(client, auth, app_module, monkeypatch):
    for name in ("services.monthly_plan", "services.goals"):
        monkeypatch.setattr(importlib.import_module(name), "local_today", lambda: date(2026, 3, 20))
    pizza = create_transaction(client, auth)
    patch(client, auth, pizza["id"], {"share_mode": "SPLIT", "share_others_amount": 60, "share_person": "Ana"})
    pix = create_transaction(client, auth, type="INCOME", category="Salário", amount=60)
    patch(client, auth, pix["id"], {"share_mode": "OTHERS", "share_person": "Ana"})
    rows = create_purchase(client, auth, total=90, installments=3)
    client.patch(f"/api/cc-expenses/{rows[0]['id']}/share", headers=auth, json={
        "share_mode": "OTHERS", "share_person": "Ana",
    })

    body = client.get("/api/monthly-plan", headers=auth, query_string={"month": "2026-03"}).get_json()
    assert body["actual"]["spent_accounts"] == 20
    assert body["actual"]["spent_cards"] == 0
    assert body["actual"]["income"] == 0
