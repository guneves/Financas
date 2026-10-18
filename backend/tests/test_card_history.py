"""O historico do cartao nao some (037).

O que estes testes protegem:

- excluir uma compra parcelada tira so as parcelas em aberto: as ja pagas
  ficam com a fatura delas, o pagamento continua batendo e o orcamento do mes
  da compra conta o que foi pago; a API recusa (409) apagar item pago;
- uma compra (digitada ou aprovada em Aprovar) cuja data cai numa fatura ja
  paga — pelo debito automatico ou a mao — vai para a primeira fatura nao
  paga, como o estorno: senao ficava em aberto para sempre e virava "vencida";
- excluir um cartao com item em aberto e recusado; com historico, o cartao e
  arquivado (compras, orcamentos e pagamentos ficam); sem nada, sai de verdade;
- um pagamento de fatura se desfaz: o lancamento sai, os itens que ele pagou
  reabrem, e o debito automatico nao paga a fatura de novo sozinho.

Cartao dos testes: vence dia 10, fecha dia 3 — uma compra em 05/03 cai na
fatura 04/2026, que fecha em 03/04 e vence em 10/04.
"""

import importlib
import uuid
from datetime import date, datetime, timedelta, timezone

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


def create_account(client, auth, name="Banco"):
    response = client.post("/api/accounts", headers=auth, json={
        "name": name, "type": "CHECKING", "initial_balance": 1000,
    })
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def create_card(client, auth, name="Cartao", **extra):
    response = client.post("/api/credit-cards", headers=auth, json={
        "name": name, "due_day": 10, "closing_day": 3, **extra,
    })
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def purchase(client, auth, card, total=300, purchase_date="2026-03-05", installments=1,
             category="Alimentação", expected=201):
    response = client.post("/api/cc-expenses/purchases", headers=auth, json={
        "card_id": card["id"], "category": category, "description": "Loja",
        "total_amount": total, "purchase_date": purchase_date, "installments": installments,
    })
    assert response.status_code == expected, response.get_data(as_text=True)
    return response.get_json()


def pay(client, auth, card, month=4, year=2026, account=None, expected=201):
    payload = {"card_id": card["id"], "invoice_month": month, "invoice_year": year}
    if account:
        payload["account_id"] = account["id"]
    response = client.post("/api/cc-expenses/pay-invoice", headers=auth, json=payload)
    assert response.status_code == expected, response.get_data(as_text=True)
    return response.get_json()


def undo(client, auth, transaction_id, expected=200):
    response = client.delete(f"/api/cc-expenses/payments/{transaction_id}", headers=auth)
    assert response.status_code == expected, response.get_data(as_text=True)
    return response.get_json()


def card_rows(client, auth, card, status=None):
    query = {"status": status} if status else {}
    rows = client.get("/api/cc-expenses", headers=auth, query_string=query).get_json()
    return [row for row in rows if row["card_id"] == card["id"]]


def invoice_of(row):
    return (row["invoice_year"], row["invoice_month"])


def payments(client, auth):
    return [
        row for row in client.get("/api/transactions", headers=auth).get_json()
        if row.get("source_type") in ("CC_INVOICE_PAYMENT", "CC_AUTOPAY")
    ]


def balance(client, auth, account):
    accounts = client.get("/api/accounts", headers=auth).get_json()
    return next(item for item in accounts if item["id"] == account["id"])["balance"]


def budget_spent(client, auth, month, category="Alimentação"):
    categories = {item["name"]: item for item in client.get("/api/categories", headers=auth).get_json()}
    client.post("/api/budgets", headers=auth, json={
        "category_id": categories[category]["id"], "month": month, "planned_amount": 1000,
    })
    body = client.get("/api/budgets", headers=auth, query_string={"month": month}).get_json()
    return next(item for item in body["items"] if item["category_name"] == category)["spent"]


# --- 1. excluir compra parcelada ---------------------------------------------

class TestDeletingAPartlyPaidPurchase:
    def test_the_api_refuses_to_delete_a_paid_installment(self, client, auth, today):
        account = create_account(client, auth)
        card = create_card(client, auth)
        installments = purchase(client, auth, card, total=300, installments=3)
        today.set(date(2026, 4, 5))
        pay(client, auth, card, 4, 2026, account)

        response = client.delete("/api/cc-expenses", headers=auth, json={"ids": [row["id"] for row in installments]})
        assert response.status_code == 409
        assert "desfaca o pagamento" in response.get_json()["error"]
        # Nada saiu: a recusa e do pedido inteiro.
        assert len(card_rows(client, auth, card)) == 3

    def test_deleting_the_open_installments_keeps_the_paid_one_and_its_payment(self, client, auth, today):
        account = create_account(client, auth)
        card = create_card(client, auth)
        installments = purchase(client, auth, card, total=300, installments=3)
        today.set(date(2026, 4, 5))
        [payment] = [pay(client, auth, card, 4, 2026, account)["transaction"]]

        # O que a tela manda agora: so as parcelas em aberto (candidates traz o status).
        candidates = client.get(
            "/api/cc-expenses/candidates", headers=auth, query_string={"id": installments[0]["id"]},
        ).get_json()
        open_ids = [row["id"] for row in candidates if row["status"] == "OPEN"]
        assert len(open_ids) == 2
        response = client.delete("/api/cc-expenses", headers=auth, json={"ids": open_ids})
        assert response.status_code == 200

        [paid] = card_rows(client, auth, card)
        assert paid["status"] == "PAID" and paid["installment_info"] == "1/3"
        assert [row["amount"] for row in payments(client, auth)] == [payment["amount"]] == [100]
        # A compra continua no orcamento do mes dela pelo que foi pago.
        assert budget_spent(client, auth, "2026-03") == 100


# --- 2. compra numa fatura ja paga -----------------------------------------

class TestPurchaseIntoAPaidInvoice:
    def test_autopay_paid_invoice_sends_a_late_purchase_to_the_next_invoice(self, client, auth, today):
        account = create_account(client, auth)
        card = create_card(client, auth, autopay_account_id=account["id"])
        purchase(client, auth, card, total=200)
        today.set(date(2026, 4, 12))
        client.get("/api/credit-cards", headers=auth)  # o debito roda na leitura
        assert [row["amount"] for row in payments(client, auth)] == [200]

        # Lancada depois, com a data de 06/03: cairia na 04/2026, ja debitada.
        [late] = purchase(client, auth, card, total=50, purchase_date="2026-03-06")
        assert invoice_of(late) == (2026, 5)

        today.set(date(2026, 5, 10))
        client.get("/api/credit-cards", headers=auth)
        assert sorted(row["amount"] for row in payments(client, auth)) == [50, 200]
        assert card_rows(client, auth, card, status="OPEN") == []

    def test_a_manually_paid_invoice_also_moves_the_installments_forward(self, client, auth, today):
        account = create_account(client, auth)
        card = create_card(client, auth)
        purchase(client, auth, card, total=200)
        today.set(date(2026, 4, 5))
        pay(client, auth, card, 4, 2026, account)

        rows = purchase(client, auth, card, total=90, purchase_date="2026-03-06", installments=3)
        assert [invoice_of(row) for row in rows] == [(2026, 5), (2026, 6), (2026, 7)]

    def test_an_unpaid_closed_invoice_still_takes_the_purchase(self, client, auth, today):
        card = create_card(client, auth)
        purchase(client, auth, card, total=200)
        today.set(date(2026, 4, 5))  # 04/2026 fechou, nao foi paga
        [late] = purchase(client, auth, card, total=50, purchase_date="2026-03-06")
        assert invoice_of(late) == (2026, 4)

    def test_a_purchase_approved_in_aprovar_skips_the_paid_invoice(self, client, auth, today):
        account = create_account(client, auth)
        card = create_card(client, auth, name="Itaú Visa")
        # 10/10 cai na 11/2026 (fecha 03/11); ela e paga antes da notificacao ser aprovada.
        purchase(client, auth, card, total=200, purchase_date="2026-10-05")
        today.set(date(2026, 11, 5))
        pay(client, auth, card, 11, 2026, account)

        posted = int(datetime(2026, 10, 10, 14, 0, tzinfo=timezone(timedelta(hours=-3))).timestamp() * 1000)
        response = client.post("/api/inbox/detections", headers=auth, json={"detections": [{
            "key": uuid.uuid4().hex, "app": "com.itau", "kind": "CREDIT_PURCHASE", "amount_cents": 4590,
            "posted_ms": posted, "utc_offset_minutes": -180, "merchant": "PADARIA",
        }]})
        assert response.status_code == 200, response.get_data(as_text=True)
        [item] = client.get("/api/inbox", headers=auth).get_json()["items"]
        response = client.post(f"/api/inbox/{item['id']}/approve", headers=auth, json={
            "version": item["version"], "card_id": card["id"],
        })
        assert response.status_code == 200, response.get_data(as_text=True)

        [approved] = [row for row in card_rows(client, auth, card, status="OPEN") if row["amount"] == 45.9]
        assert invoice_of(approved) == (2026, 12)


# --- 3. excluir cartao, desfazer pagamento -----------------------------------

class TestDeletingACard:
    def test_a_card_with_open_items_is_not_deleted(self, client, auth, today):
        card = create_card(client, auth)
        purchase(client, auth, card, total=300, installments=3)
        response = client.delete(f"/api/credit-cards/{card['id']}", headers=auth)
        assert response.status_code == 409
        assert "3 item(ns) em aberto" in response.get_json()["error"]
        assert "R$ 300,00" in response.get_json()["error"]
        assert len(card_rows(client, auth, card)) == 3

    def test_a_card_with_history_is_archived_and_its_history_stays(self, client, auth, today):
        account = create_account(client, auth)
        card = create_card(client, auth, autopay_account_id=account["id"])
        purchase(client, auth, card, total=200)
        today.set(date(2026, 4, 12))
        client.get("/api/credit-cards", headers=auth)
        spent_before = budget_spent(client, auth, "2026-03")

        response = client.delete(f"/api/credit-cards/{card['id']}", headers=auth)
        assert response.status_code == 200
        assert response.get_json() == {"deleted": True, "archived": True}

        assert [item["id"] for item in client.get("/api/credit-cards", headers=auth).get_json()] == []
        [archived] = client.get("/api/credit-cards", headers=auth, query_string={"include_archived": 1}).get_json()
        assert archived["archived_at"] and archived["autopay_account_id"] is None
        assert len(card_rows(client, auth, card, status="PAID")) == 1
        assert budget_spent(client, auth, "2026-03") == spent_before == 200
        assert len(payments(client, auth)) == 1

        # Nao recebe mais nada, e o nome continua dele.
        purchase(client, auth, card, total=10, expected=400)
        response = client.post("/api/cc-expenses/refunds", headers=auth, json={
            "card_id": card["id"], "amount": 10, "purchase_date": "2026-04-12", "description": "Estorno",
        })
        assert response.status_code == 400
        assert client.patch(f"/api/credit-cards/{card['id']}", headers=auth,
                            json={"autopay_account_id": account["id"]}).status_code == 404
        response = client.post("/api/credit-cards", headers=auth, json={"name": "Cartao", "due_day": 10, "closing_day": 3})
        assert response.status_code == 409
        assert "excluido" in response.get_json()["error"]
        # Excluir de novo nao acha nada.
        assert client.delete(f"/api/credit-cards/{card['id']}", headers=auth).status_code == 404

    def test_the_payment_of_an_archived_card_can_still_be_undone(self, client, auth, today):
        account = create_account(client, auth)
        card = create_card(client, auth)
        purchase(client, auth, card, total=200)
        today.set(date(2026, 4, 5))
        payment = pay(client, auth, card, 4, 2026, account)["transaction"]
        # Paga a fatura, o item vira historico; sem item aberto, o cartao se arquiva.
        assert client.delete(f"/api/credit-cards/{card['id']}", headers=auth).status_code == 200
        undo(client, auth, payment["id"])
        assert payments(client, auth) == []
        assert balance(client, auth, account) == 1000

    def test_an_empty_card_is_really_deleted(self, client, auth):
        card = create_card(client, auth)
        response = client.delete(f"/api/credit-cards/{card['id']}", headers=auth)
        assert response.get_json() == {"deleted": True, "archived": False}
        assert client.get("/api/credit-cards", headers=auth, query_string={"include_archived": 1}).get_json() == []
        # O nome fica livre.
        create_card(client, auth)

    def test_aprovar_does_not_offer_or_take_an_archived_card(self, client, auth, today, db_module):
        account = create_account(client, auth)
        card = create_card(client, auth, name="Itaú Visa")
        purchase(client, auth, card, total=200)
        today.set(date(2026, 4, 5))
        pay(client, auth, card, 4, 2026, account)
        assert client.delete(f"/api/credit-cards/{card['id']}", headers=auth).status_code == 200

        response = client.post("/api/inbox/detections", headers=auth, json={"detections": [{
            "key": uuid.uuid4().hex, "app": "com.itau", "kind": "CREDIT_PURCHASE", "amount_cents": 1000,
            "posted_ms": int(datetime(2026, 4, 5, 12, tzinfo=timezone.utc).timestamp() * 1000),
            "utc_offset_minutes": -180, "merchant": "PADARIA",
        }]})
        assert response.status_code == 200
        [item] = client.get("/api/inbox", headers=auth).get_json()["items"]
        assert item.get("card_id") is None
        response = client.post(f"/api/inbox/{item['id']}/approve", headers=auth, json={
            "version": item["version"], "card_id": card["id"],
        })
        assert response.status_code == 400


class TestUndoingAPayment:
    def test_undo_removes_the_payment_and_reopens_the_items(self, client, auth, today):
        account = create_account(client, auth)
        card = create_card(client, auth)
        purchase(client, auth, card, total=200)
        today.set(date(2026, 4, 5))
        payment = pay(client, auth, card, 4, 2026, account)["transaction"]
        assert balance(client, auth, account) == 800

        body = undo(client, auth, payment["id"])
        assert body["undone"] is True and body["reopened"] == 1
        assert payments(client, auth) == []
        assert balance(client, auth, account) == 1000
        [row] = card_rows(client, auth, card)
        assert row["status"] == "OPEN"
        # E paga de novo, a mao.
        pay(client, auth, card, 4, 2026, account)
        assert balance(client, auth, account) == 800

    def test_undoing_an_autopay_does_not_debit_the_invoice_again(self, client, auth, today):
        account = create_account(client, auth)
        card = create_card(client, auth, autopay_account_id=account["id"])
        purchase(client, auth, card, total=200)
        purchase(client, auth, card, total=70, purchase_date="2026-04-05")  # fatura 05/2026
        today.set(date(2026, 4, 12))
        client.get("/api/credit-cards", headers=auth)
        [autopay] = payments(client, auth)
        assert autopay["source_type"] == "CC_AUTOPAY"

        undo(client, auth, autopay["id"])
        for _ in range(2):
            client.get("/api/cc-expenses", headers=auth)
        assert payments(client, auth) == []
        assert [invoice_of(row) for row in card_rows(client, auth, card, status="OPEN")] == [(2026, 4), (2026, 5)]

        # A fatura seguinte continua no debito automatico.
        today.set(date(2026, 5, 10))
        client.get("/api/credit-cards", headers=auth)
        assert [row["amount"] for row in payments(client, auth)] == [70]
        # E a desfeita se paga pelo botao, como qualquer outra.
        pay(client, auth, card, 4, 2026)
        assert sorted(row["amount"] for row in payments(client, auth)) == [70, 200]

    def test_undo_reopens_the_credit_lines_the_payment_took_along(self, client, auth, today):
        account = create_account(client, auth)
        card = create_card(client, auth)
        purchase(client, auth, card, total=50)                    # 04/2026
        client.post("/api/cc-expenses/refunds", headers=auth, json={
            "card_id": card["id"], "amount": 80, "purchase_date": "2026-03-06", "description": "Estorno",
        })                                                       # 04/2026 fica -30
        purchase(client, auth, card, total=100, purchase_date="2026-04-05")  # 05/2026
        today.set(date(2026, 5, 5))
        payment = pay(client, auth, card, 5, 2026, account)["transaction"]
        assert payment["amount"] == 70
        assert card_rows(client, auth, card, status="OPEN") == []

        assert undo(client, auth, payment["id"])["reopened"] == 3
        assert len(card_rows(client, auth, card, status="OPEN")) == 3

    def test_undo_only_reopens_what_that_payment_paid(self, client, auth, today):
        account = create_account(client, auth)
        card = create_card(client, auth)
        purchase(client, auth, card, total=200)                              # 04/2026
        purchase(client, auth, card, total=100, purchase_date="2026-04-05")  # 05/2026
        today.set(date(2026, 5, 5))
        first = pay(client, auth, card, 4, 2026, account)["transaction"]
        pay(client, auth, card, 5, 2026, account)

        undo(client, auth, first["id"])
        assert [invoice_of(row) for row in card_rows(client, auth, card, status="OPEN")] == [(2026, 4)]
        assert [row["amount"] for row in payments(client, auth)] == [100]

    def test_a_payment_from_before_037_reopens_its_invoice(self, client, auth, today, db_module, user):
        account = create_account(client, auth)
        card = create_card(client, auth)
        purchase(client, auth, card, total=200)
        today.set(date(2026, 4, 5))
        payment = pay(client, auth, card, 4, 2026, account)["transaction"]
        with db_module.get_db() as conn:
            conn.execute("UPDATE cc_expenses SET paid_by = NULL WHERE user_id = ?", (user["id"],))

        assert undo(client, auth, payment["id"])["reopened"] == 1
        assert card_rows(client, auth, card)[0]["status"] == "OPEN"

    def test_undo_is_refused_while_the_payment_has_a_receipt(self, client, auth, today, db_module, user):
        account = create_account(client, auth)
        card = create_card(client, auth)
        purchase(client, auth, card, total=200)
        today.set(date(2026, 4, 5))
        payment = pay(client, auth, card, 4, 2026, account)["transaction"]
        with db_module.get_db() as conn:
            conn.execute(
                """
                INSERT INTO transaction_attachments
                (id, user_id, transaction_id, original_name, stored_name, content_type, size_bytes, sha256)
                VALUES (?, ?, ?, 'recibo.pdf', ?, 'application/pdf', 10, 'x')
                """,
                (str(uuid.uuid4()), user["id"], payment["id"], f"{uuid.uuid4().hex}.pdf"),
            )
        response = client.delete(f"/api/cc-expenses/payments/{payment['id']}", headers=auth)
        assert response.status_code == 409
        assert "comprovante" in response.get_json()["error"]
        assert len(payments(client, auth)) == 1

    def test_only_an_invoice_payment_of_the_owner_is_undone(self, client, auth, other_user, today):
        account = create_account(client, auth)
        card = create_card(client, auth)
        purchase(client, auth, card, total=200)
        today.set(date(2026, 4, 5))
        payment = pay(client, auth, card, 4, 2026, account)["transaction"]
        assert client.delete(f"/api/cc-expenses/payments/{payment['id']}", headers=other_user["headers"]).status_code == 404

        expense = client.post("/api/transactions", headers=auth, json={
            "amount": 10, "date": "2026-04-05", "category": "Outros", "type": "EXPENSE", "description": "x",
        }).get_json()
        undo(client, auth, expense["id"], expected=404)
        assert len(payments(client, auth)) == 1

    def test_a_manual_status_change_detaches_the_items_from_the_payment(self, client, auth, today):
        account = create_account(client, auth)
        card = create_card(client, auth)
        [row] = purchase(client, auth, card, total=200)
        today.set(date(2026, 4, 5))
        payment = pay(client, auth, card, 4, 2026, account)["transaction"]
        client.patch("/api/cc-expenses/status", headers=auth, json={"ids": [row["id"]], "status": "OPEN"})
        pay(client, auth, card, 4, 2026, account)
        # O primeiro pagamento ja nao baixa nada: desfaze-lo nao mexe no segundo.
        assert undo(client, auth, payment["id"])["reopened"] == 0
        assert card_rows(client, auth, card)[0]["status"] == "PAID"
