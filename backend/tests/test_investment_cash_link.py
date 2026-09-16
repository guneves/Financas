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
        investment = post_buy(client, auth, ticker="BUYTEST1", quantity=100, price=10.0)

        entries = cash_entries(client, auth)
        linked = [e for e in entries if e["source_id"] == investment["id"]]
        assert len(linked) == 1

        entry = linked[0]
        assert entry["type"] == "EXPENSE"
        assert entry["amount"] == pytest.approx(1000.0)
        assert entry["date"] == "2026-02-10"

    def test_the_outflow_amount_follows_quantity_times_price(self, client, auth):
        investment = post_buy(client, auth, ticker="BUYTEST2", quantity=7, price=33.33)
        entry = [e for e in cash_entries(client, auth) if e["source_id"] == investment["id"]][0]
        assert entry["amount"] == pytest.approx(233.31)

    def test_two_buys_create_two_independent_entries(self, client, auth):
        first = post_buy(client, auth, ticker="BUYTEST3", quantity=10, price=5.0)
        second = post_buy(client, auth, ticker="BUYTEST3", quantity=20, price=5.0)

        entries = cash_entries(client, auth)
        ids = {e["source_id"] for e in entries}
        assert {first["id"], second["id"]} <= ids


class TestDeletingTheMovementRemovesTheCashEntry:
    def test_deleting_a_buy_removes_its_linked_expense(self, client, auth):
        investment = post_buy(client, auth, ticker="DELTEST1", quantity=50, price=8.0)
        assert any(e["source_id"] == investment["id"] for e in cash_entries(client, auth))

        response = client.delete(f"/api/investments/{investment['id']}", headers=auth)
        assert response.status_code == 200, response.get_data(as_text=True)

        assert not any(e["source_id"] == investment["id"] for e in cash_entries(client, auth))

    def test_deleting_every_movement_of_an_asset_clears_its_cash_entries(self, client, auth):
        first = post_buy(client, auth, ticker="DELTEST2", quantity=10, price=10.0)
        second = post_buy(client, auth, ticker="DELTEST2", quantity=10, price=12.0)
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
        post_buy(client, auth, ticker="SELLTEST1", quantity=100, price=10.0, date="2026-01-10")

        response = client.post(
            "/api/investments",
            headers=auth,
            json={
                "asset_class": "STOCKS",
                "ticker_or_name": "SELLTEST1",
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
        post_buy(client, auth, ticker="SELLTEST2", quantity=10, price=10.0)

        response = client.post(
            "/api/investments",
            headers=auth,
            json={
                "asset_class": "STOCKS",
                "ticker_or_name": "SELLTEST2",
                "quantity": -50,
                "average_price": 10.0,
                "current_price": 12.0,
                "metadata": {"sale_date": "2026-03-10", "sale_price": 12.0},
            },
        )
        assert response.status_code == 400, response.get_data(as_text=True)


class TestDestructiveGuards:
    def test_deleting_an_asset_without_its_class_is_refused(self, client, auth):
        investment = post_buy(client, auth, ticker="GUARD1", quantity=10, price=10.0)

        response = client.delete(
            f"/api/investments/by-asset/{investment['asset_id']}",
            headers=auth,
        )
        assert response.status_code == 400

    def test_deleting_an_asset_with_the_wrong_class_is_refused(self, client, auth):
        investment = post_buy(client, auth, ticker="GUARD2", quantity=10, price=10.0)

        response = client.delete(
            f"/api/investments/by-asset/{investment['asset_id']}?asset_class=REIT",
            headers=auth,
        )
        assert response.status_code == 409
        # The movement and its cash entry survive the refused delete.
        assert any(e["source_id"] == investment["id"] for e in cash_entries(client, auth))
