"""A listagem de proventos le as operacoes de cada ativo uma vez.

Antes era uma consulta de operacoes por provento (114 proventos, 114 consultas
iguais). O que a listagem devolve nao muda: cada item e identico ao que o
serializador devolve sozinho, com a consulta propria dele.
"""

import importlib

import pytest


@pytest.fixture()
def portfolio(client, auth):
    """Dois ativos, compras e uma venda em datas diferentes, e 12 proventos."""
    assets = []
    for ticker, price in (("PETR4", 30.0), ("ITSA4", 10.0)):
        bought = client.post("/api/investments", headers=auth, json={
            "asset_class": "STOCKS", "ticker_or_name": ticker, "quantity": 100, "average_price": price,
            "current_price": price, "metadata": {"purchase_date": "2025-01-10", "cash_account_id": None},
        })
        assert bought.status_code == 201, bought.get_data(as_text=True)
        body = bought.get_json()
        asset_id = (body[0] if isinstance(body, list) else body)["asset_id"]
        more = client.post("/api/investments", headers=auth, json={
            "asset_class": "STOCKS", "ticker_or_name": ticker, "quantity": 50, "average_price": price * 1.2,
            "current_price": price, "metadata": {"purchase_date": "2025-04-10", "cash_account_id": None},
        })
        assert more.status_code == 201, more.get_data(as_text=True)
        assets.append(asset_id)
    for month in range(2, 8):
        for asset_id in assets:
            paid = client.post("/api/investment-proceeds", headers=auth, json={
                "asset_id": asset_id, "proceeds_type": "DIVIDEND", "record_date": f"2025-{month:02d}-15",
                "payment_date": f"2025-{month:02d}-25", "gross_amount": 10 + month,
            })
            assert paid.status_code == 201, paid.get_data(as_text=True)
    return assets


def test_the_listing_reads_each_assets_operations_once(client, auth, user, portfolio, db_module):
    proceeds = importlib.import_module("services.proceeds")
    with db_module.get_db() as conn:
        statements = []
        conn.set_trace_callback(statements.append)
        listed = proceeds.serialized_proceeds(conn, user["id"], {})
        conn.set_trace_callback(None)
        movement_reads = [text for text in statements if "FROM investment_transactions" in text]
        assert len(listed) == 12
        assert len(movement_reads) == len(portfolio) == 2
        # Item a item, o mesmo que o serializador devolve com a consulta dele.
        rows = proceeds.fetch_investment_proceeds(conn, user["id"], {})
        alone = [proceeds.serialize_investment_proceed(row, conn, user["id"]) for row in rows]
        assert listed == alone
    # A posicao na data com acompanha as compras: 100 ate abril, 150 depois.
    by_month = {item["record_date"][5:7]: item["eligible_quantity"] for item in listed if item["asset_id"] == portfolio[0]}
    assert by_month["02"] == 100 and by_month["07"] == 150


def test_the_route_returns_what_the_service_lists(client, auth, user, portfolio, db_module):
    proceeds = importlib.import_module("services.proceeds")
    response = client.get("/api/investment-proceeds?date_from=2025-01-01&date_to=2025-12-31", headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    items = body["items"] if isinstance(body, dict) else body
    assert len(items) == 12
    assert all(item["yield_on_cost_percent"] > 0 for item in items)
