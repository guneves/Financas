"""Axis 3: credit card invoices — settlement, installments and validation.

Scope note: these tests cover the settlement state machine, installment
separation and payload validation on the raw `/api/cc-expenses` endpoint, which
stores the `invoice_month`/`invoice_year` it is handed. The rule that *decides*
which invoice a purchase lands in moved out of the frontend on 2026-09-15 and is
covered by `test_invoice_month.py`.
"""

import pytest


@pytest.fixture()
def card(client, auth):
    response = client.post(
        "/api/credit-cards",
        headers=auth,
        json={"name": "Cartao Teste", "due_day": 10, "closing_day": 3},
    )
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    body = response.get_json()
    return body[0] if isinstance(body, list) else body


def add_expense(client, auth, card, **overrides):
    payload = {
        "card_id": card["id"],
        "category": "Compras",
        "description": "Compra",
        "amount": 100.0,
        "purchase_date": "2026-03-01",
        "invoice_month": 3,
        "invoice_year": 2026,
        "installment_info": "1/1",
    }
    payload.update(overrides)
    response = client.post("/api/cc-expenses", headers=auth, json=payload)
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    body = response.get_json()
    return body[0] if isinstance(body, list) else body


def fetch_expense(client, auth, expense_id):
    rows = client.get("/api/cc-expenses", headers=auth).get_json()
    matches = [row for row in rows if row["id"] == expense_id]
    return matches[0] if matches else None


def pay(client, auth, card, month, year=2026):
    return client.post(
        "/api/cc-expenses/pay-invoice",
        headers=auth,
        json={"card_id": card["id"], "invoice_month": month, "invoice_year": year},
    )


class TestInvoiceSettlement:
    """A baixa da fatura e o pagamento real (pay-invoice). Os PATCH antigos
    /status e /invoice-status marcavam PAID sem lancar o pagamento e sairam."""

    def test_settling_an_invoice_marks_only_that_month_as_paid(self, client, auth, card):
        march = add_expense(client, auth, card, invoice_month=3, description="Marco")
        april = add_expense(client, auth, card, invoice_month=4, description="Abril")

        response = pay(client, auth, card, 3)
        assert response.status_code == 201, response.get_data(as_text=True)
        assert response.get_json()["transaction"]["amount"] == 100.0

        assert fetch_expense(client, auth, march["id"])["status"] == "PAID"
        assert fetch_expense(client, auth, april["id"])["status"] == "OPEN"

    def test_settling_pays_every_line_of_the_invoice_at_once(self, client, auth, card):
        lines = [
            add_expense(client, auth, card, invoice_month=5, description=f"Item {i}")
            for i in range(3)
        ]

        response = pay(client, auth, card, 5)
        assert response.get_json()["transaction"]["amount"] == 300.0
        for line in lines:
            assert fetch_expense(client, auth, line["id"])["status"] == "PAID"

    def test_settling_twice_pays_once(self, client, auth, card):
        add_expense(client, auth, card, invoice_month=6)

        first = pay(client, auth, card, 6)
        second = pay(client, auth, card, 6)

        assert first.status_code == 201
        # Nada mais em aberto: o segundo pedido nao debita a conta de novo.
        assert second.status_code == 409

    def test_an_invoice_is_reopened_by_undoing_its_payment(self, client, auth, card):
        expense = add_expense(client, auth, card, invoice_month=7)

        payment = pay(client, auth, card, 7).get_json()["transaction"]
        assert fetch_expense(client, auth, expense["id"])["status"] == "PAID"

        response = client.delete(f"/api/cc-expenses/payments/{payment['id']}", headers=auth)
        assert response.status_code == 200, response.get_data(as_text=True)
        assert fetch_expense(client, auth, expense["id"])["status"] == "OPEN"

    def test_the_same_month_of_another_year_is_left_alone(self, client, auth, card):
        this_year = add_expense(client, auth, card, invoice_month=8, invoice_year=2026)
        next_year = add_expense(client, auth, card, invoice_month=8, invoice_year=2027)

        pay(client, auth, card, 8, 2026)

        assert fetch_expense(client, auth, this_year["id"])["status"] == "PAID"
        assert fetch_expense(client, auth, next_year["id"])["status"] == "OPEN"

    def test_settling_an_unknown_card_is_refused(self, client, auth):
        response = pay(client, auth, {"id": "does-not-exist"}, 3)
        assert response.status_code == 404

    def test_the_old_status_endpoints_are_gone(self, client, auth, card):
        expense = add_expense(client, auth, card, invoice_month=3)
        for path, body in (
            ("/api/cc-expenses/status", {"ids": [expense["id"]], "status": "PAID"}),
            (
                "/api/cc-expenses/invoice-status",
                {"card_id": card["id"], "invoice_month": 3, "invoice_year": 2026, "status": "PAID"},
            ),
        ):
            assert client.patch(path, headers=auth, json=body).status_code in (404, 405)
        assert fetch_expense(client, auth, expense["id"])["status"] == "OPEN"


class TestInstallments:
    def test_an_installment_purchase_spreads_across_consecutive_invoices(self, client, auth, card):
        """The frontend posts one line per installment; the backend must keep them apart."""
        created = [
            add_expense(
                client,
                auth,
                card,
                description="Notebook",
                amount=1000.0,
                purchase_date="2026-09-20",
                invoice_month=month,
                invoice_year=2026,
                installment_info=f"{index}/3",
            )
            for index, month in enumerate([10, 11, 12], start=1)
        ]

        rows = client.get("/api/cc-expenses", headers=auth).get_json()
        mine = {row["id"]: row for row in rows}
        months = sorted(mine[item["id"]]["invoice_month"] for item in created)
        assert months == [10, 11, 12]
        assert {mine[item["id"]]["installment_info"] for item in created} == {"1/3", "2/3", "3/3"}

    def test_settling_one_month_does_not_settle_the_later_installments(self, client, auth, card):
        # Past months: an invoice can only be settled once it has closed
        # (test_invoice_payment.py).
        first = add_expense(
            client, auth, card, invoice_month=10, invoice_year=2025, installment_info="1/2"
        )
        second = add_expense(
            client, auth, card, invoice_month=11, invoice_year=2025, installment_info="2/2"
        )

        pay(client, auth, card, 10, 2025)

        assert fetch_expense(client, auth, first["id"])["status"] == "PAID"
        assert fetch_expense(client, auth, second["id"])["status"] == "OPEN"


class TestExpenseValidation:
    def test_an_expense_needs_a_real_card(self, client, auth):
        response = client.post(
            "/api/cc-expenses",
            headers=auth,
            json={
                "card_id": "nope",
                "category": "Compras",
                "description": "Compra",
                "amount": 10.0,
                "purchase_date": "2026-03-01",
                "invoice_month": 3,
                "invoice_year": 2026,
                "installment_info": "1/1",
            },
        )
        assert response.status_code in (400, 404)

    @pytest.mark.parametrize("month", [0, 13, -1])
    def test_an_out_of_range_invoice_month_is_refused(self, client, auth, card, month):
        response = client.post(
            "/api/cc-expenses",
            headers=auth,
            json={
                "card_id": card["id"],
                "category": "Compras",
                "description": "Compra",
                "amount": 10.0,
                "purchase_date": "2026-03-01",
                "invoice_month": month,
                "invoice_year": 2026,
                "installment_info": "1/1",
            },
        )
        assert response.status_code == 400

    def test_a_zero_amount_is_refused(self, client, auth, card):
        response = client.post(
            "/api/cc-expenses",
            headers=auth,
            json={
                "card_id": card["id"],
                "category": "Compras",
                "description": "Compra",
                "amount": 0,
                "purchase_date": "2026-03-01",
                "invoice_month": 3,
                "invoice_year": 2026,
                "installment_info": "1/1",
            },
        )
        assert response.status_code == 400

    def test_a_malformed_purchase_date_is_refused(self, client, auth, card):
        response = client.post(
            "/api/cc-expenses",
            headers=auth,
            json={
                "card_id": card["id"],
                "category": "Compras",
                "description": "Compra",
                "amount": 10.0,
                "purchase_date": "01/03/2026",
                "invoice_month": 3,
                "invoice_year": 2026,
                "installment_info": "1/1",
            },
        )
        assert response.status_code == 400

    def test_deleting_a_card_is_refused_or_removes_its_expenses(self, client, auth, card):
        expense = add_expense(client, auth, card, invoice_month=9, invoice_year=2028)

        response = client.delete("/api/credit-cards/" + card["id"], headers=auth)
        assert response.status_code in (200, 400, 409)

        if response.status_code == 200 and response.get_json().get("deleted"):
            # A deleted card must not leave orphan invoice lines behind.
            assert fetch_expense(client, auth, expense["id"]) is None
