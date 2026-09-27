"""Axis 4: investment movements must stay in sync with the cash statement.

A buy creates an EXPENSE in `transactions`, a sell creates an INCOME, and the
link is carried by `source_type = 'INVESTMENT_TRANSACTION'` + `source_id`.
Deleting the movement has to take the cash entry with it, otherwise the balance
silently drifts.
"""

import pytest


def post_buy(client, auth, *, ticker="PETR4", quantity=100, price=10.0, date="2026-02-10", fee=0):
    response = client.post(
        "/api/investments",
        headers=auth,
        json={
            "asset_class": "STOCKS",
            "ticker_or_name": ticker,
            "quantity": quantity,
            "average_price": price,
            "current_price": price,
            "metadata": {"purchase_date": date, "fee_amount": fee},
        },
    )
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    body = response.get_json()
    return body[0] if isinstance(body, list) else body


def cash_entries(client, auth):
    response = client.get("/api/transactions", headers=auth)
    assert response.status_code == 200
    return [
        item for item in response.get_json()
        if item.get("source_type") == "INVESTMENT_TRANSACTION"
    ]


class TestBuyCreatesAnOutflow:
    def test_a_buy_creates_a_matching_expense(self, client, auth):
        investment = post_buy(client, auth, ticker="PETR4", quantity=100, price=10.0)

        entries = cash_entries(client, auth)
        linked = [e for e in entries if e["source_id"] == investment["id"]]
        assert len(linked) == 1

        entry = linked[0]
        assert entry["type"] == "EXPENSE"
        assert entry["amount"] == pytest.approx(1000.0)
        assert entry["date"] == "2026-02-10"

    def test_the_outflow_amount_follows_quantity_times_price(self, client, auth):
        investment = post_buy(client, auth, ticker="VALE3", quantity=7, price=33.33)
        entry = [e for e in cash_entries(client, auth) if e["source_id"] == investment["id"]][0]
        assert entry["amount"] == pytest.approx(233.31)

    def test_two_buys_create_two_independent_entries(self, client, auth):
        first = post_buy(client, auth, ticker="ITUB4", quantity=10, price=5.0)
        second = post_buy(client, auth, ticker="ITUB4", quantity=20, price=5.0)

        entries = cash_entries(client, auth)
        ids = {e["source_id"] for e in entries}
        assert {first["id"], second["id"]} <= ids


class TestDeletingTheMovementRemovesTheCashEntry:
    def test_deleting_a_buy_removes_its_linked_expense(self, client, auth):
        investment = post_buy(client, auth, ticker="BBAS3", quantity=50, price=8.0)
        assert any(e["source_id"] == investment["id"] for e in cash_entries(client, auth))

        response = client.delete(f"/api/investments/{investment['id']}", headers=auth)
        assert response.status_code == 200, response.get_data(as_text=True)

        assert not any(e["source_id"] == investment["id"] for e in cash_entries(client, auth))

    def test_deleting_every_movement_of_an_asset_clears_its_cash_entries(self, client, auth):
        first = post_buy(client, auth, ticker="WEGE3", quantity=10, price=10.0)
        second = post_buy(client, auth, ticker="WEGE3", quantity=10, price=12.0)
        asset_id = first["asset_id"]

        # The endpoint demands the asset class as a confirmation guard, so a
        # stale id from the UI cannot wipe the wrong asset.
        response = client.delete(
            f"/api/investments/by-asset/{asset_id}?asset_class=STOCKS",
            headers=auth,
        )
        assert response.status_code == 200, response.get_data(as_text=True)

        remaining = {e["source_id"] for e in cash_entries(client, auth)}
        assert first["id"] not in remaining
        assert second["id"] not in remaining


class TestSellCreatesAnInflow:
    def test_a_sell_creates_an_income_entry(self, client, auth):
        post_buy(client, auth, ticker="ABEV3", quantity=100, price=10.0, date="2026-01-10")

        response = client.post(
            "/api/investments",
            headers=auth,
            json={
                "asset_class": "STOCKS",
                "ticker_or_name": "ABEV3",
                "quantity": -40,
                "average_price": 10.0,
                "current_price": 15.0,
                "metadata": {"sale_date": "2026-03-10", "sale_price": 15.0},
            },
        )
        assert response.status_code in (200, 201), response.get_data(as_text=True)
        sale = response.get_json()
        sale = sale[0] if isinstance(sale, list) else sale

        entry = [e for e in cash_entries(client, auth) if e["source_id"] == sale["id"]][0]
        assert entry["type"] == "INCOME"
        assert entry["amount"] == pytest.approx(600.0)

    def test_selling_more_than_owned_is_rejected(self, client, auth):
        post_buy(client, auth, ticker="MGLU3", quantity=10, price=10.0)

        response = client.post(
            "/api/investments",
            headers=auth,
            json={
                "asset_class": "STOCKS",
                "ticker_or_name": "MGLU3",
                "quantity": -50,
                "average_price": 10.0,
                "current_price": 12.0,
                "metadata": {"sale_date": "2026-03-10", "sale_price": 12.0},
            },
        )
        assert response.status_code == 400, response.get_data(as_text=True)


class TestDestructiveGuards:
    def test_deleting_an_asset_without_its_class_is_refused(self, client, auth):
        investment = post_buy(client, auth, ticker="B3SA3", quantity=10, price=10.0)

        response = client.delete(
            f"/api/investments/by-asset/{investment['asset_id']}",
            headers=auth,
        )
        assert response.status_code == 400

    def test_deleting_an_asset_with_the_wrong_class_is_refused(self, client, auth):
        investment = post_buy(client, auth, ticker="TOTS3", quantity=10, price=10.0)

        response = client.delete(
            f"/api/investments/by-asset/{investment['asset_id']}?asset_class=REIT",
            headers=auth,
        )
        assert response.status_code == 409
        # The movement and its cash entry survive the refused delete.
        assert any(e["source_id"] == investment["id"] for e in cash_entries(client, auth))


class TestPositionBeforeTheApp:
    """`metadata.skip_cash`: an investment bought long before the app — with
    money that never went through it — enters the portfolio without touching
    the balance."""

    def post_old_buy(self, client, auth, **kwargs):
        response = client.post(
            "/api/investments",
            headers=auth,
            json={
                "asset_class": "STOCKS",
                "ticker_or_name": kwargs.get("ticker", "PETR4"),
                "quantity": kwargs.get("quantity", 100),
                "average_price": kwargs.get("price", 10.0),
                "current_price": kwargs.get("price", 10.0),
                "metadata": {"purchase_date": "2019-03-10", "skip_cash": True},
            },
        )
        assert response.status_code == 201, response.get_data(as_text=True)
        return response.get_json()[0]

    def test_an_old_buy_creates_no_cash_entry(self, client, auth):
        investment = self.post_old_buy(client, auth)
        assert [e for e in cash_entries(client, auth) if e["source_id"] == investment["id"]] == []

        positions = client.get("/api/investments", headers=auth).get_json()
        assert any(p["id"] == investment["id"] for p in positions)

    def test_the_account_balance_is_untouched(self, client, auth):
        self.post_old_buy(client, auth, quantity=50, price=20.0)
        accounts = client.get("/api/accounts", headers=auth).get_json()
        assert sum(a["balance"] for a in accounts) == pytest.approx(0)

    def test_a_later_sale_of_the_old_position_still_brings_cash_in(self, client, auth):
        self.post_old_buy(client, auth, quantity=100, price=10.0)
        response = client.post(
            "/api/investments",
            headers=auth,
            json={
                "asset_class": "STOCKS",
                "ticker_or_name": "PETR4",
                "quantity": -40,
                "average_price": 10.0,
                "current_price": 15.0,
                "metadata": {"sale_date": "2026-02-10", "sale_price": 15.0},
            },
        )
        assert response.status_code == 201, response.get_data(as_text=True)
        sale = response.get_json()[0]
        linked = [e for e in cash_entries(client, auth) if e["source_id"] == sale["id"]]
        assert len(linked) == 1
        assert linked[0]["type"] == "INCOME"
        assert linked[0]["amount"] == pytest.approx(600.0)

    def test_toggling_the_flag_on_an_edit_adds_and_removes_the_entry(self, client, auth):
        investment = post_buy(client, auth, ticker="VALE3", quantity=10, price=50.0)
        assert len([e for e in cash_entries(client, auth) if e["source_id"] == investment["id"]]) == 1

        metadata = {**investment["metadata"], "skip_cash": True}
        response = client.patch(f"/api/investments/{investment['id']}", headers=auth, json={"metadata": metadata})
        assert response.status_code == 200, response.get_data(as_text=True)
        assert [e for e in cash_entries(client, auth) if e["source_id"] == investment["id"]] == []

        metadata["skip_cash"] = False
        response = client.patch(f"/api/investments/{investment['id']}", headers=auth, json={"metadata": metadata})
        assert response.status_code == 200, response.get_data(as_text=True)
        linked = [e for e in cash_entries(client, auth) if e["source_id"] == investment["id"]]
        assert len(linked) == 1
        assert linked[0]["amount"] == pytest.approx(500.0)
