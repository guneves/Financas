"""Arredondamento da carteira: bruto - IR = liquido no centavo, totais em ROUND_HALF_UP.

Antes o bruto, o IR e o liquido eram arredondados cada um por si, e um CDB saia
28.959,44 - 1.343,92 = 27.615,53 (um centavo a mais). Os totais usavam o
round() do Python, que arredonda a metade para o par.
"""


def fixed_income_row(row_id, invested, current, purchase_date="2025-01-02"):
    return {
        "id": row_id,
        "asset_id": None,
        "ticker_or_name": f"CDB {row_id}",
        "asset_class": "FIXED_INCOME",
        "quantity": 1,
        "average_price": invested,
        "current_price": current,
        "metadata": {"purchase_date": purchase_date},
    }


def snapshot(portfolio_module, monkeypatch, rows, net_of):
    monkeypatch.setattr(portfolio_module, "fetch_investments", lambda user_id: rows)
    monkeypatch.setattr(
        portfolio_module, "fixed_income_net_value",
        lambda asset_class, metadata, invested, market, reference: net_of(market),
    )
    return portfolio_module.build_portfolio_snapshot(1)


def test_gross_minus_tax_equals_net_to_the_cent(portfolio_module, monkeypatch):
    # Bruto 28959,444 -> 28959,44; IR 1343,915 -> 1343,92; liquido 27615,529 -> 27615,53.
    result = snapshot(
        portfolio_module, monkeypatch,
        [fixed_income_row(1, 20000, 28959.444)],
        lambda market: market - 1343.915,
    )
    asset = result["assets"][0]
    assert asset["current_value"] == 28959.44
    assert asset["net_value"] == 27615.53
    assert asset["taxes"] == 1343.91
    assert round(asset["current_value"] - asset["taxes"], 2) == asset["net_value"]


def test_asset_carries_its_invested_total(portfolio_module, monkeypatch):
    result = snapshot(
        portfolio_module, monkeypatch,
        [fixed_income_row(1, 20000.005, 21000)],
        lambda market: market,
    )
    assert result["assets"][0]["total_invested"] == 20000.01


def test_portfolio_totals_round_half_up(portfolio_module, monkeypatch):
    # 0,125 + 0,5 + ...: round() daria 1000,12 (metade para o par); o certo e 1000,13.
    result = snapshot(
        portfolio_module, monkeypatch,
        [fixed_income_row(1, 1000.125, 1000.125)],
        lambda market: market,
    )
    assert result["total_invested"] == 1000.13
    assert result["current_balance"] == 1000.13
    assert result["current_net_balance"] == 1000.13


def test_materialized_position_keeps_the_real_invested_amount(client, auth):
    # 1 x 333,34 + 2 x 333,33 = 1000,00; preco medio 333,33 x 3 daria 999,99.
    for quantity, price, day in ((1, 333.34, "2026-01-10"), (2, 333.33, "2026-01-11")):
        response = client.post(
            "/api/investments",
            headers=auth,
            json={
                "asset_class": "STOCKS",
                "ticker_or_name": "PETR4",
                "quantity": quantity,
                "average_price": price,
                "current_price": price,
                "metadata": {"purchase_date": day},
            },
        )
        assert response.status_code in (200, 201), response.get_data(as_text=True)

    positions = client.get("/api/investment-positions", headers=auth).get_json()
    [position] = [p for p in positions if p["quantity"] == 3]
    assert position["invested_amount"] == 1000.0
    assert position["average_price"] == 333.33
