"""Paying a credit card invoice: only once it has closed, and "Debito automatico".

An invoice (month, year) is named after the month it falls due. It closes on the
card's closing day — in that same month when closing comes before the due day,
in the previous month otherwise — and from that day on it can be paid. Before
that its total can still change, so every path that marks it PAID refuses.

With a debit account set on the card, each invoice is paid by itself on its due
date, from that account, the first time the app reads its data on or after it.

The clock is frozen through `app.local_today`.
"""

from datetime import date, timedelta

import pytest


@pytest.fixture()
def today(app_module, monkeypatch):
    """Set the app's "today": `today.set(date(...))`."""

    class Clock:
        value = date(2026, 9, 22)

        def set(self, value):
            self.value = value

    clock = Clock()
    monkeypatch.setattr(app_module, "local_today", lambda: clock.value)
    return clock


def create_card(client, auth, due_day=10, closing_day=3, **extra):
    response = client.post(
        "/api/credit-cards",
        headers=auth,
        json={"name": f"Cartao {due_day}-{closing_day}", "due_day": due_day, "closing_day": closing_day, **extra},
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def create_account(client, auth, name="Banco", initial_balance=1000):
    response = client.post(
        "/api/accounts",
        headers=auth,
        json={"name": name, "type": "CHECKING", "initial_balance": initial_balance},
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def add_line(client, auth, card, month, year, amount=100.0, description="Compra"):
    response = client.post(
        "/api/cc-expenses",
        headers=auth,
        json={
            "card_id": card["id"],
            "category": "Compras",
            "description": description,
            "amount": amount,
            "purchase_date": f"{year}-{month:02d}-01",
            "invoice_month": month,
            "invoice_year": year,
            "installment_info": "1/1",
        },
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()[0]


def lines(client, auth):
    return {row["id"]: row for row in client.get("/api/cc-expenses", headers=auth).get_json()}


def payments(client, auth):
    return [
        row
        for row in client.get("/api/transactions", headers=auth).get_json()
        if row["category"].startswith("Pagamento Fatura")
    ]


def balance(client, auth, account_id):
    rows = client.get("/api/accounts", headers=auth).get_json()
    return next(row["balance"] for row in rows if row["id"] == account_id)


def pay(client, auth, card, month, year, **extra):
    return client.post(
        "/api/cc-expenses/pay-invoice",
        headers=auth,
        json={"card_id": card["id"], "invoice_month": month, "invoice_year": year, **extra},
    )


class TestClosingDate:
    @pytest.mark.parametrize(
        "due_day, closing_day, invoice, expected",
        [
            (10, 3, (3, 2026), date(2026, 3, 3)),      # closes in its own month
            (5, 25, (3, 2026), date(2026, 2, 25)),     # closes the month before
            (5, 25, (1, 2026), date(2025, 12, 25)),    # ... across the year
            (5, 31, (3, 2026), date(2026, 2, 28)),     # clamped to a short month
            (10, 10, (3, 2026), date(2026, 2, 10)),    # same day counts as "after"
        ],
    )
    def test_closing_date(self, app_module, due_day, closing_day, invoice, expected):
        assert app_module.invoice_closing_date(*invoice, due_day, closing_day) == expected

    @pytest.mark.parametrize("due_day, closing_day", [(10, 3), (5, 25), (15, 8), (1, 24)])
    def test_matches_the_purchase_rule(self, app_module, due_day, closing_day):
        """A purchase always lands in an invoice that has not closed yet, and the
        invoice before it had already closed on the purchase day."""
        day = date(2026, 1, 1)
        while day < date(2027, 1, 1):
            start = app_module.compute_invoice_start(day, due_day, closing_day)
            month, year = start["invoice_month"], start["invoice_year"]
            assert app_module.invoice_closing_date(month, year, due_day, closing_day) > day
            prev_month, prev_year = app_module.add_invoice_months(month, year, -1)
            assert app_module.invoice_closing_date(prev_month, prev_year, due_day, closing_day) <= day
            day += timedelta(days=1)

    def test_lines_carry_the_invoice_dates(self, client, auth, today):
        card = create_card(client, auth)
        line = add_line(client, auth, card, 10, 2026)

        today.set(date(2026, 10, 2))
        row = lines(client, auth)[line["id"]]
        assert row["invoice_closing_date"] == "2026-10-03"
        assert row["invoice_due_date"] == "2026-10-10"
        assert row["invoice_closed"] is False

        today.set(date(2026, 10, 3))
        assert lines(client, auth)[line["id"]]["invoice_closed"] is True


class TestPayInvoice:
    def test_an_open_invoice_cannot_be_paid(self, client, auth, today):
        card = create_card(client, auth)
        line = add_line(client, auth, card, 10, 2026)
        today.set(date(2026, 10, 2))

        response = pay(client, auth, card, 10, 2026)

        assert response.status_code == 409
        assert "ainda esta aberta" in response.get_json()["error"]
        assert lines(client, auth)[line["id"]]["status"] == "OPEN"
        assert payments(client, auth) == []

    def test_a_closed_invoice_is_paid_from_the_account(self, client, auth, today):
        card = create_card(client, auth)
        account = create_account(client, auth, initial_balance=1000)
        first = add_line(client, auth, card, 10, 2026, amount=100.10)
        second = add_line(client, auth, card, 10, 2026, amount=0.2)
        later = add_line(client, auth, card, 11, 2026, amount=50)
        today.set(date(2026, 10, 3))

        response = pay(client, auth, card, 10, 2026, account_id=account["id"])

        assert response.status_code == 201, response.get_data(as_text=True)
        transaction = response.get_json()["transaction"]
        assert transaction["type"] == "EXPENSE"
        assert transaction["amount"] == 100.30
        assert transaction["date"] == "2026-10-03"
        assert transaction["account_id"] == account["id"]
        assert transaction["category"] == f"Pagamento Fatura {card['name']}"
        assert balance(client, auth, account["id"]) == 899.70

        rows = lines(client, auth)
        assert rows[first["id"]]["status"] == "PAID"
        assert rows[second["id"]]["status"] == "PAID"
        assert rows[later["id"]]["status"] == "OPEN"

    def test_paying_twice_is_refused(self, client, auth, today):
        card = create_card(client, auth)
        add_line(client, auth, card, 10, 2026)
        today.set(date(2026, 10, 5))

        assert pay(client, auth, card, 10, 2026).status_code == 201
        second = pay(client, auth, card, 10, 2026)

        assert second.status_code == 409
        assert len(payments(client, auth)) == 1

    def test_a_reopened_invoice_can_be_paid_again(self, client, auth, today):
        card = create_card(client, auth)
        add_line(client, auth, card, 10, 2026)
        today.set(date(2026, 10, 5))
        assert pay(client, auth, card, 10, 2026).status_code == 201
        client.patch(
            "/api/cc-expenses/invoice-status",
            headers=auth,
            json={"card_id": card["id"], "invoice_month": 10, "invoice_year": 2026,
                  "status": "OPEN", "current_status": "PAID"},
        )

        assert pay(client, auth, card, 10, 2026).status_code == 201

    def test_another_users_card_is_not_found(self, client, auth, other_user, today):
        card = create_card(client, auth)
        add_line(client, auth, card, 10, 2026)
        today.set(date(2026, 10, 5))

        response = pay(client, other_user["headers"], card, 10, 2026)

        assert response.status_code == 404
        assert payments(client, auth) == []

    def test_another_users_account_is_refused(self, client, auth, other_user, today):
        card = create_card(client, auth)
        add_line(client, auth, card, 10, 2026)
        foreign = create_account(client, other_user["headers"], name="Alheia")
        today.set(date(2026, 10, 5))

        response = pay(client, auth, card, 10, 2026, account_id=foreign["id"])

        assert response.status_code == 400
        assert payments(client, auth) == []


    def test_without_an_account_the_autopay_account_is_used(self, client, auth, today):
        # Pagar manualmente antes do vencimento sai da mesma conta do debito automatico.
        account = create_account(client, auth, name="Conta do cartao")
        card = create_card(client, auth, autopay_account_id=account["id"])
        add_line(client, auth, card, 10, 2026)
        today.set(date(2026, 10, 5))

        response = pay(client, auth, card, 10, 2026)

        assert response.status_code == 201, response.get_data(as_text=True)
        assert response.get_json()["transaction"]["account_id"] == account["id"]

    def test_an_explicit_account_wins_over_the_autopay_account(self, client, auth, today):
        autopay = create_account(client, auth, name="Debito")
        chosen = create_account(client, auth, name="Escolhida")
        card = create_card(client, auth, autopay_account_id=autopay["id"])
        add_line(client, auth, card, 10, 2026)
        today.set(date(2026, 10, 5))

        response = pay(client, auth, card, 10, 2026, account_id=chosen["id"])

        assert response.get_json()["transaction"]["account_id"] == chosen["id"]

    def test_an_archived_autopay_account_falls_back_to_the_default(self, client, auth, today):
        autopay = create_account(client, auth, name="Encerrada")
        card = create_card(client, auth, autopay_account_id=autopay["id"])
        add_line(client, auth, card, 10, 2026)
        assert client.delete(f"/api/accounts/{autopay['id']}", headers=auth).status_code == 200
        today.set(date(2026, 10, 5))

        response = pay(client, auth, card, 10, 2026)

        assert response.status_code == 201, response.get_data(as_text=True)
        default = next(row for row in client.get("/api/accounts", headers=auth).get_json() if row["is_default"])
        assert response.get_json()["transaction"]["account_id"] == default["id"]

class TestPaymentLancamentoIsLocked:
    """Editing or deleting only the payment would leave the invoice PAID with no
    money having left the account."""

    @pytest.mark.parametrize("autopay", [False, True])
    def test_cannot_be_edited_or_deleted(self, client, auth, today, autopay):
        today.set(date(2026, 9, 22))
        card = create_card(client, auth)
        account = create_account(client, auth)
        add_line(client, auth, card, 10, 2026)
        if autopay:
            client.patch(f"/api/credit-cards/{card['id']}", headers=auth,
                         json={"autopay_account_id": account["id"]})
            today.set(date(2026, 10, 10))
        else:
            today.set(date(2026, 10, 5))
            assert pay(client, auth, card, 10, 2026).status_code == 201
        payment = payments(client, auth)[0]

        edit = client.patch(f"/api/transactions/{payment['id']}", headers=auth, json={"amount": 1})
        delete = client.delete(f"/api/transactions/{payment['id']}", headers=auth)

        assert edit.status_code == 409
        assert delete.status_code == 409
        assert payments(client, auth)[0]["amount"] == 100


class TestStatusEndpointsRespectClosing:
    def test_invoice_status_refuses_paid_before_closing(self, client, auth, today):
        card = create_card(client, auth)
        line = add_line(client, auth, card, 10, 2026)
        today.set(date(2026, 10, 2))

        response = client.patch(
            "/api/cc-expenses/invoice-status",
            headers=auth,
            json={"card_id": card["id"], "invoice_month": 10, "invoice_year": 2026, "status": "PAID"},
        )

        assert response.status_code == 409
        assert lines(client, auth)[line["id"]]["status"] == "OPEN"

    def test_status_by_ids_refuses_paid_before_closing(self, client, auth, today):
        card = create_card(client, auth)
        closed = add_line(client, auth, card, 9, 2026)
        still_open = add_line(client, auth, card, 10, 2026)
        today.set(date(2026, 10, 2))

        response = client.patch(
            "/api/cc-expenses/status",
            headers=auth,
            json={"ids": [closed["id"], still_open["id"]], "status": "PAID"},
        )

        assert response.status_code == 409
        rows = lines(client, auth)
        assert rows[closed["id"]]["status"] == "OPEN"
        assert rows[still_open["id"]]["status"] == "OPEN"

    def test_reopening_is_always_allowed(self, client, auth, today):
        card = create_card(client, auth)
        line = add_line(client, auth, card, 10, 2026)
        today.set(date(2026, 10, 2))

        response = client.patch(
            "/api/cc-expenses/status",
            headers=auth,
            json={"ids": [line["id"]], "status": "OPEN"},
        )
        assert response.status_code == 200


class TestAutopay:
    def enable(self, client, auth, card, account_id):
        response = client.patch(
            f"/api/credit-cards/{card['id']}",
            headers=auth,
            json={"autopay_account_id": account_id},
        )
        assert response.status_code == 200, response.get_data(as_text=True)
        return response.get_json()

    def test_pays_on_the_due_date_from_the_chosen_account(self, client, auth, today):
        today.set(date(2026, 9, 22))
        card = create_card(client, auth)
        account = create_account(client, auth, initial_balance=500)
        line = add_line(client, auth, card, 10, 2026, amount=120)
        updated = self.enable(client, auth, card, account["id"])
        assert updated["autopay_account_id"] == account["id"]
        assert updated["autopay_start_date"] == "2026-09-22"

        today.set(date(2026, 10, 9))          # closed, not yet due
        assert payments(client, auth) == []
        assert lines(client, auth)[line["id"]]["status"] == "OPEN"

        today.set(date(2026, 10, 10))         # due day
        paid = payments(client, auth)
        assert len(paid) == 1
        assert paid[0]["amount"] == 120
        assert paid[0]["date"] == "2026-10-10"
        assert paid[0]["account_id"] == account["id"]
        assert paid[0]["source_type"] == "CC_AUTOPAY"
        assert lines(client, auth)[line["id"]]["status"] == "PAID"
        assert balance(client, auth, account["id"]) == 380

    def test_a_late_read_still_dates_the_payment_on_the_due_day(self, client, auth, today):
        today.set(date(2026, 9, 22))
        card = create_card(client, auth)
        account = create_account(client, auth)
        add_line(client, auth, card, 10, 2026)
        add_line(client, auth, card, 11, 2026)
        self.enable(client, auth, card, account["id"])

        today.set(date(2026, 11, 20))
        assert sorted(row["date"] for row in payments(client, auth)) == ["2026-10-10", "2026-11-10"]

    def test_running_again_does_not_pay_twice(self, client, auth, today):
        today.set(date(2026, 9, 22))
        card = create_card(client, auth)
        account = create_account(client, auth)
        add_line(client, auth, card, 10, 2026)
        self.enable(client, auth, card, account["id"])

        today.set(date(2026, 10, 15))
        for _ in range(3):
            client.get("/api/cc-expenses", headers=auth)
            client.get("/api/accounts", headers=auth)
        assert len(payments(client, auth)) == 1

    def test_a_reopened_invoice_is_not_debited_again(self, client, auth, today):
        today.set(date(2026, 9, 22))
        card = create_card(client, auth)
        account = create_account(client, auth)
        line = add_line(client, auth, card, 10, 2026)
        self.enable(client, auth, card, account["id"])
        today.set(date(2026, 10, 15))
        assert len(payments(client, auth)) == 1

        client.patch(
            "/api/cc-expenses/status", headers=auth, json={"ids": [line["id"]], "status": "OPEN"}
        )

        assert len(payments(client, auth)) == 1
        assert lines(client, auth)[line["id"]]["status"] == "OPEN"

    def test_invoices_due_before_it_was_enabled_are_left_for_manual_payment(self, client, auth, today):
        card = create_card(client, auth)
        account = create_account(client, auth)
        old = add_line(client, auth, card, 8, 2026)
        new = add_line(client, auth, card, 10, 2026)
        today.set(date(2026, 9, 22))
        self.enable(client, auth, card, account["id"])

        today.set(date(2026, 10, 10))
        paid = payments(client, auth)
        assert [row["date"] for row in paid] == ["2026-10-10"]
        rows = lines(client, auth)
        assert rows[old["id"]]["status"] == "OPEN"
        assert rows[new["id"]]["status"] == "PAID"

    def test_enabling_on_the_due_day_pays_that_invoice(self, client, auth, today):
        card = create_card(client, auth)
        account = create_account(client, auth)
        line = add_line(client, auth, card, 10, 2026)
        today.set(date(2026, 10, 10))

        self.enable(client, auth, card, account["id"])

        assert lines(client, auth)[line["id"]]["status"] == "PAID"

    def test_can_be_set_when_the_card_is_created(self, client, auth, today):
        today.set(date(2026, 9, 22))
        account = create_account(client, auth)
        card = create_card(client, auth, autopay_account_id=account["id"])
        assert card["autopay_account_id"] == account["id"]
        assert card["autopay_start_date"] == "2026-09-22"

        add_line(client, auth, card, 10, 2026)
        today.set(date(2026, 10, 10))
        assert len(payments(client, auth)) == 1

    def test_disabling_stops_it(self, client, auth, today):
        today.set(date(2026, 9, 22))
        card = create_card(client, auth)
        account = create_account(client, auth)
        add_line(client, auth, card, 10, 2026)
        self.enable(client, auth, card, account["id"])

        disabled = self.enable(client, auth, card, None)
        assert disabled["autopay_account_id"] is None
        assert disabled["autopay_start_date"] is None

        today.set(date(2026, 10, 15))
        assert payments(client, auth) == []

    def test_an_archived_account_is_not_debited(self, client, auth, today):
        today.set(date(2026, 9, 22))
        card = create_card(client, auth)
        account = create_account(client, auth)
        add_line(client, auth, card, 10, 2026)
        self.enable(client, auth, card, account["id"])
        assert client.delete(f"/api/accounts/{account['id']}", headers=auth).status_code == 200

        today.set(date(2026, 10, 15))
        assert payments(client, auth) == []

    def test_another_users_account_is_refused(self, client, auth, other_user, today):
        card = create_card(client, auth)
        foreign = create_account(client, other_user["headers"], name="Alheia")

        response = client.patch(
            f"/api/credit-cards/{card['id']}",
            headers=auth,
            json={"autopay_account_id": foreign["id"]},
        )
        assert response.status_code == 400

    def test_another_users_card_cannot_be_changed(self, client, auth, other_user, today):
        card = create_card(client, auth)
        account = create_account(client, other_user["headers"], name="Dele")

        response = client.patch(
            f"/api/credit-cards/{card['id']}",
            headers=other_user["headers"],
            json={"autopay_account_id": account["id"]},
        )
        assert response.status_code == 404

    def test_does_not_touch_other_users(self, client, auth, other_user, today):
        today.set(date(2026, 9, 22))
        card = create_card(client, auth)
        account = create_account(client, auth)
        add_line(client, auth, card, 10, 2026)
        self.enable(client, auth, card, account["id"])

        today.set(date(2026, 10, 15))
        client.get("/api/transactions", headers=other_user["headers"])
        # The other user's read pays nothing of ours: that happens on our read.
        rows = client.get("/api/cc-expenses", headers=other_user["headers"]).get_json()
        assert rows == []
