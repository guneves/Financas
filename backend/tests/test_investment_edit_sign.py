"""Editing an operation: the sign belongs to the stored operation, not the field.

Operações › Editar shows a sale's quantity without the "-" (owner, 2026-10-19).
The screen puts it back on save, and the PATCH keeps the stored type anyway: a
sale sent with a positive quantity stays a sale, a buy sent with a negative one
stays a buy.
"""

import pytest


def post_movement(client, auth, payload):
    response = client.post("/api/investments", headers=auth, json=payload)
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    body = response.get_json()
    return body[0] if isinstance(body, list) else body


def buy(client, auth, *, ticker="PETR4", quantity=100, price=10.0, date="2026-02-10"):
    return post_movement(client, auth, {
        "asset_class": "STOCKS",
        "ticker_or_name": ticker,
        "quantity": quantity,
        "average_price": price,
        "current_price": price,
        "metadata": {"purchase_date": date},
    })


def sell(client, auth, *, ticker="PETR4", quantity=40, price=15.0, date="2026-03-10"):
    return post_movement(client, auth, {
        "asset_class": "STOCKS",
        "ticker_or_name": ticker,
        "quantity": -quantity,
        "average_price": price,
        "current_price": price,
        "metadata": {"sale_date": date, "sale_price": price},
    })


def stored(client, auth, investment_id):
    response = client.get("/api/investments", headers=auth)
    assert response.status_code == 200
    return next(item for item in response.get_json() if item["id"] == investment_id)


def patch(client, auth, investment_id, payload):
    return client.patch(f"/api/investments/{investment_id}", headers=auth, json=payload)


class TestASaleIsEditedWithoutTheMinus:
    def test_a_positive_quantity_keeps_the_sale_a_sale(self, client, auth):
        buy(client, auth)
        sale = sell(client, auth)

        response = patch(client, auth, sale["id"], {"quantity": 30, "metadata": sale["metadata"]})
        assert response.status_code == 200, response.get_data(as_text=True)

        row = stored(client, auth, sale["id"])
        assert float(row["quantity"]) == pytest.approx(-30)
        assert row["movement_type"] == "SELL"

    def test_the_old_negative_quantity_still_works(self, client, auth):
        buy(client, auth)
        sale = sell(client, auth)

        response = patch(client, auth, sale["id"], {"quantity": -25, "metadata": sale["metadata"]})
        assert response.status_code == 200, response.get_data(as_text=True)
        assert float(stored(client, auth, sale["id"])["quantity"]) == pytest.approx(-25)

    def test_the_position_follows_the_edited_sale(self, client, auth):
        buy(client, auth, quantity=100)
        sale = sell(client, auth, quantity=40)

        assert patch(client, auth, sale["id"], {"quantity": 10, "metadata": sale["metadata"]}).status_code == 200

        portfolio = client.get("/api/investments/portfolio?refresh_prices=false", headers=auth).get_json()
        asset = next(item for item in portfolio["assets"] if item["ticker"] == "PETR4")
        assert float(asset["quantity"]) == pytest.approx(90)

    def test_a_positive_quantity_above_the_position_is_still_refused(self, client, auth):
        buy(client, auth, quantity=100)
        sale = sell(client, auth, quantity=40)

        response = patch(client, auth, sale["id"], {"quantity": 150, "metadata": sale["metadata"]})
        assert response.status_code == 400, response.get_data(as_text=True)
        assert float(stored(client, auth, sale["id"])["quantity"]) == pytest.approx(-40)


class TestABuyNeverTurnsIntoASale:
    def test_a_negative_quantity_on_a_buy_stays_a_buy(self, client, auth):
        purchase = buy(client, auth, quantity=100)

        response = patch(client, auth, purchase["id"], {"quantity": -50, "metadata": purchase["metadata"]})
        assert response.status_code == 200, response.get_data(as_text=True)

        row = stored(client, auth, purchase["id"])
        assert float(row["quantity"]) == pytest.approx(50)
        assert row["movement_type"] == "BUY"
