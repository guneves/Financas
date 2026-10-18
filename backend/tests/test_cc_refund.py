"""Estorno no cartao (033, POST /api/cc-expenses/refunds).

Um estorno e um credito na fatura: uma linha `kind = 'REFUND'` de cc_expenses,
com valor positivo, que abate o total em vez de somar. Cai na fatura da data
(a regra da compra) ou, se essa ja foi paga, na seguinte em aberto. Uma fatura
que fica com credito nao e paga; o credito abate a proxima. Orcamento e plano
do mes descontam o estorno no mes dele.

Cartao dos testes: vence dia 10, fecha dia 3 — uma compra em 05/03 cai na
fatura 04/2026, que fecha em 03/04.
"""

import importlib
from datetime import date

import pytest


@pytest.fixture()
def today(invoices_module, monkeypatch):
    class Clock:
        value = date(2026, 3, 20)

        def set(self, value):
            self.value = value

    clock = Clock()
    for module in (invoices_module, importlib.import_module("routes.cards")):
        monkeypatch.setattr(module, "local_today", lambda: clock.value)
    return clock


def create_card(client, auth, **extra):
    response = client.post("/api/credit-cards", headers=auth, json={
        "name": extra.pop("name", "Cartao"), "due_day": 10, "closing_day": 3, **extra,
    })
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def create_account(client, auth, name="Banco"):
    response = client.post("/api/accounts", headers=auth, json={
        "name": name, "type": "CHECKING", "initial_balance": 1000,
    })
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def purchase(client, auth, card, total=300, purchase_date="2026-03-05", installments=1, category="Alimentação"):
    response = client.post("/api/cc-expenses/purchases", headers=auth, json={
        "card_id": card["id"], "category": category, "description": "Loja",
        "total_amount": total, "purchase_date": purchase_date, "installments": installments,
    })
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def refund(client, auth, card, amount=100, purchase_date="2026-03-20", expected=201, **extra):
    response = client.post("/api/cc-expenses/refunds", headers=auth, json={
        "card_id": card["id"], "amount": amount, "purchase_date": purchase_date,
        "description": "Estorno · Loja", **extra,
    })
    assert response.status_code == expected, response.get_data(as_text=True)
    return response.get_json()


def pay(client, auth, card, month=4, year=2026, account=None):
    payload = {"card_id": card["id"], "invoice_month": month, "invoice_year": year}
    if account:
        payload["account_id"] = account["id"]
    return client.post("/api/cc-expenses/pay-invoice", headers=auth, json=payload)


def card_rows(client, auth, card):
    rows = client.get("/api/cc-expenses", headers=auth).get_json()
    return [row for row in rows if row["card_id"] == card["id"]]


def test_refund_is_a_credit_line_in_the_invoice_of_its_date(client, auth, today):
    card = create_card(client, auth)
    body = refund(client, auth, card, amount=100.005)
    assert body["kind"] == "REFUND"
    assert body["amount"] == 100.01
    assert body["installment_info"] == "1/1"
    assert (body["invoice_month"], body["invoice_year"]) == (4, 2026)
    assert body["category"] == "Estorno"
    assert body["status"] == "OPEN"


def test_payment_debits_purchases_minus_refunds(client, auth, today):
    card = create_card(client, auth)
    account = create_account(client, auth)
    purchase(client, auth, card, total=300)
    refund(client, auth, card, amount=100)
    today.set(date(2026, 4, 5))

    response = pay(client, auth, card, account=account)
    assert response.status_code == 201, response.get_data(as_text=True)
    assert response.get_json()["transaction"]["amount"] == 200
    assert {row["status"] for row in card_rows(client, auth, card)} == {"PAID"}


def test_autopay_debits_the_net_total(client, auth, today):
    account = create_account(client, auth)
    card = create_card(client, auth, autopay_account_id=account["id"])
    purchase(client, auth, card, total=300)
    refund(client, auth, card, amount=120)
    today.set(date(2026, 4, 10))

    transactions = client.get("/api/transactions", headers=auth).get_json()
    payments = [item for item in transactions if item.get("source_type") == "CC_AUTOPAY"]
    assert [item["amount"] for item in payments] == [180]


def test_refund_dated_in_a_paid_invoice_goes_to_the_next_open_one(client, auth, today):
    card = create_card(client, auth)
    account = create_account(client, auth)
    purchase(client, auth, card, total=100)
    today.set(date(2026, 4, 5))
    assert pay(client, auth, card, account=account).status_code == 201

    body = refund(client, auth, card, amount=40, purchase_date="2026-03-25")
    assert (body["invoice_month"], body["invoice_year"]) == (5, 2026)


def test_invoice_zeroed_by_a_refund_closes_without_a_payment(client, auth, today):
    card = create_card(client, auth)
    account = create_account(client, auth)
    purchase(client, auth, card, total=100)
    refund(client, auth, card, amount=100)
    today.set(date(2026, 4, 5))

    response = pay(client, auth, card, account=account)
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json() == {"transaction": None}
    assert {row["status"] for row in card_rows(client, auth, card)} == {"PAID"}
    transactions = client.get("/api/transactions", headers=auth).get_json()
    assert not [item for item in transactions if item.get("source_type") == "CC_INVOICE_PAYMENT"]


def test_credit_invoice_is_not_paid_and_the_credit_lowers_the_next(client, auth, today):
    card = create_card(client, auth)
    account = create_account(client, auth)
    purchase(client, auth, card, total=50)
    refund(client, auth, card, amount=150)  # fatura 04: -100
    purchase(client, auth, card, total=300, purchase_date="2026-04-10")  # fatura 05
    today.set(date(2026, 4, 5))

    response = pay(client, auth, card, account=account)
    assert response.status_code == 409
    assert "credito" in response.get_json()["error"]

    today.set(date(2026, 5, 5))
    response = pay(client, auth, card, month=5, account=account)
    assert response.status_code == 201, response.get_data(as_text=True)
    assert response.get_json()["transaction"]["amount"] == 200
    assert {row["status"] for row in card_rows(client, auth, card)} == {"PAID"}


def test_budget_and_monthly_plan_subtract_the_refund_in_its_month(client, auth, today, monkeypatch):
    for name in ("services.monthly_plan", "services.goals"):
        monkeypatch.setattr(importlib.import_module(name), "local_today", lambda: date(2026, 3, 20))
    categories = {item["name"]: item for item in client.get("/api/categories", headers=auth).get_json()}
    client.post("/api/budgets", headers=auth, json={
        "category_id": categories["Alimentação"]["id"], "month": "2026-03", "planned_amount": 1000,
    })
    card = create_card(client, auth)
    purchase(client, auth, card, total=300)
    refund(client, auth, card, amount=100, category="Alimentação")

    month = client.get("/api/budgets", headers=auth, query_string={"month": "2026-03"}).get_json()
    item = next(entry for entry in month["items"] if entry["category_name"] == "Alimentação")
    assert item["spent"] == 200

    plan = client.get("/api/monthly-plan", headers=auth, query_string={"month": "2026-03"}).get_json()
    assert plan["actual"]["spent_cards"] == 200


def test_refund_cannot_be_shared(client, auth, today):
    card = create_card(client, auth)
    body = refund(client, auth, card)
    response = client.patch(f"/api/cc-expenses/{body['id']}/share", headers=auth, json={
        "share_mode": "OTHERS", "share_person": "Ana",
    })
    assert response.status_code == 400
    assert "estorno" in response.get_json()["error"]


def test_refund_is_not_a_candidate_of_a_purchase_with_the_same_key(client, auth, today):
    card = create_card(client, auth)
    purchase(client, auth, card, total=100, purchase_date="2026-03-20")
    client.post("/api/cc-expenses/refunds", headers=auth, json={
        "card_id": card["id"], "amount": 100, "purchase_date": "2026-03-20",
        "description": "Loja", "category": "Alimentação",
    })
    candidates = client.get("/api/cc-expenses/candidates", headers=auth, query_string={
        "card_id": card["id"], "description": "Loja", "purchase_date": "2026-03-20", "category": "Alimentação",
    }).get_json()
    assert len(candidates) == 1


def test_refund_is_idempotent_by_client_id(client, auth, today):
    card = create_card(client, auth)
    first = refund(client, auth, card, client_id="estorno-1")
    again = refund(client, auth, card, client_id="estorno-1", expected=200)
    assert again["id"] == first["id"]
    assert len(card_rows(client, auth, card)) == 1


def test_refund_of_must_be_a_purchase_of_the_same_card(client, auth, today):
    card = create_card(client, auth)
    other = create_card(client, auth, name="Outro")
    rows = purchase(client, auth, other, total=100)
    body = refund(client, auth, card, refund_of=rows[0]["id"], expected=400)
    assert "estornada" in body["error"]
    ok = refund(client, auth, other, refund_of=rows[0]["id"])
    assert ok["refund_of"] == rows[0]["id"]


@pytest.mark.parametrize("payload", [
    {"amount": 0},
    {"amount": -10},
    {"purchase_date": ""},
    {"description": ""},
])
def test_refund_validation(client, auth, today, payload):
    card = create_card(client, auth)
    base = {"card_id": card["id"], "amount": 10, "purchase_date": "2026-03-20", "description": "Estorno"}
    response = client.post("/api/cc-expenses/refunds", headers=auth, json={**base, **payload})
    assert response.status_code == 400


def test_refund_on_another_users_card_is_refused(client, auth, other_user, today):
    card = create_card(client, other_user["headers"])
    body = refund(client, auth, card, expected=400)
    assert "Cartao" in body["error"]
