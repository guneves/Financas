"""Custo medio ponderado: o custo das vendas e o das posicoes.

A regra da Receita para acoes, FIIs, ETFs e BDRs e o custo medio ponderado
(Lei 8.981/1995, art. 72, par. 2o; IN RFB 1.585/2015, art. 58): cada compra
entra na media, e vender nao muda o custo medio do que fica. O app usava FIFO
no resultado realizado e em Bens e Direitos, e na Posicao tirava da venda o
preco que estivesse gravado na linha (o preco medio que a tela mandou, ou o
proprio preco de venda que a API aceitava) — tres custos para a mesma posicao.

O que estes testes fixam:

- `apply_average_cost()` (services/investments.py) anota cada venda com o custo
  medio da hora e cada operacao com o quanto o custo da posicao muda;
- o preco gravado na linha da venda nao entra na conta;
- `build_variable_realized_result()` parte desse custo;
- pela API: Posicao, resultado realizado, Bens e Direitos e a evolucao saem do
  mesmo custo.
"""

import importlib
from datetime import datetime

import pytest


@pytest.fixture()
def investments_module(app_module):
    return importlib.import_module("services.investments")


def movement(movement_id, quantity, price, date, *, asset_id="asset-1", asset_class="STOCKS", created_at=None):
    return {
        "id": movement_id,
        "asset_id": asset_id,
        "asset_class": asset_class,
        "quantity": quantity,
        "average_price": price,
        "transaction_date": date,
        "created_at": created_at or f"{date}T12:00:00Z",
        "metadata": {"sale_date": date} if quantity < 0 else {"purchase_date": date},
    }


class TestAverageCostWalk:
    def test_a_partial_sale_costs_the_average_and_keeps_it_for_what_remains(self, investments_module):
        rows = investments_module.apply_average_cost([
            movement("buy-1", 100, 10.0, "2026-01-10"),
            movement("buy-2", 100, 20.0, "2026-03-10"),
            movement("sell-1", -150, 30.0, "2026-06-10"),
        ])
        sale = rows[2]
        assert sale["average_cost"] == pytest.approx(15.0)
        assert sale["cost_amount"] == pytest.approx(-2250.0)
        # FIFO teria dado 100 x 10 + 50 x 20 = 2.000.
        remaining = sum(row["cost_amount"] for row in rows)
        assert remaining == pytest.approx(50 * 15.0)

    def test_the_price_recorded_on_the_sale_row_is_ignored(self, investments_module):
        # A API aceitava o preco de venda no lugar do preco medio.
        with_sale_price = investments_module.apply_average_cost([
            movement("buy-1", 52, 38.484231, "2024-04-07"),
            movement("sell-1", -26, 43.95, "2024-05-20"),
        ])
        with_average = investments_module.apply_average_cost([
            movement("buy-1", 52, 38.484231, "2024-04-07"),
            movement("sell-1", -26, 38.48, "2024-05-20"),
        ])
        assert with_sale_price[1]["cost_amount"] == pytest.approx(with_average[1]["cost_amount"])
        assert with_sale_price[1]["average_cost"] == pytest.approx(38.484231)

    def test_sequential_sales_and_a_new_buy_re_average(self, investments_module):
        rows = investments_module.apply_average_cost([
            movement("buy-1", 100, 10.0, "2026-01-10"),
            movement("buy-2", 100, 20.0, "2026-02-10"),
            movement("sell-1", -60, 15.0, "2026-03-10"),
            movement("sell-2", -60, 15.0, "2026-04-10"),
            movement("buy-3", 80, 30.0, "2026-05-10"),
            movement("sell-3", -100, 40.0, "2026-06-10"),
        ])
        assert rows[2]["average_cost"] == pytest.approx(15.0)
        assert rows[3]["average_cost"] == pytest.approx(15.0)
        # 80 restantes a 15 (1.200) + 80 a 30 (2.400) = 3.600 / 160 = 22,50.
        assert rows[5]["average_cost"] == pytest.approx(22.5)

    def test_a_full_exit_starts_the_next_buy_from_scratch(self, investments_module):
        rows = investments_module.apply_average_cost([
            movement("buy-1", 30, 10.0, "2026-01-10"),
            movement("buy-2", 70, 20.0, "2026-02-10"),
            movement("sell-1", -100, 25.0, "2026-03-10"),
            movement("buy-3", 10, 50.0, "2026-04-10"),
            movement("sell-2", -10, 60.0, "2026-05-10"),
        ])
        assert rows[2]["cost_amount"] == pytest.approx(-(30 * 10 + 70 * 20))
        assert rows[4]["average_cost"] == pytest.approx(50.0)

    def test_operations_are_walked_by_date_not_by_list_order(self, investments_module):
        rows = investments_module.apply_average_cost([
            movement("sell-1", -50, 30.0, "2026-06-10"),
            movement("buy-2", 50, 20.0, "2026-03-10"),
            movement("buy-1", 50, 10.0, "2026-01-10"),
        ])
        assert rows[0]["id"] == "sell-1"
        assert rows[0]["average_cost"] == pytest.approx(15.0)

    def test_each_asset_has_its_own_average(self, investments_module):
        rows = investments_module.apply_average_cost([
            movement("a-buy", 10, 10.0, "2026-01-10", asset_id="a"),
            movement("b-buy", 10, 100.0, "2026-01-10", asset_id="b"),
            movement("a-sell", -10, 12.0, "2026-02-10", asset_id="a"),
        ])
        assert rows[2]["average_cost"] == pytest.approx(10.0)

    def test_a_sale_without_a_buy_before_it_keeps_its_own_price(self, investments_module):
        rows = investments_module.apply_average_cost([movement("sell-1", -50, 8.0, "2026-06-10")])
        assert rows[0]["average_cost"] == pytest.approx(8.0)
        assert rows[0]["cost_amount"] == pytest.approx(-400.0)

    def test_fixed_income_stays_per_title(self, investments_module):
        rows = investments_module.apply_average_cost([
            movement("cdb", 1, 1000.0, "2026-01-10", asset_class="FIXED_INCOME"),
            movement("resgate", -1, 400.0, "2026-06-10", asset_class="FIXED_INCOME"),
        ])
        assert rows[0]["cost_amount"] == pytest.approx(1000.0)
        assert rows[1]["cost_amount"] == pytest.approx(-400.0)
        assert "average_cost" not in rows[1]


def make_sale(quantity, sale_price, *, average_cost=None, asset_class="STOCKS", fee=0, date="2026-06-10", average_price=0):
    """A SELL movement as `fetch_investments` hands it over (with `average_cost`)."""
    sale = {
        "id": f"sell-{quantity}-{sale_price}",
        "user_id": "user-1",
        "asset_id": "asset-1",
        "asset_class": asset_class,
        "movement_type": "SELL",
        "quantity": -abs(quantity),
        "average_price": average_price,
        "current_price": sale_price,
        "fee_amount": fee,
        "transaction_date": date,
        "metadata": {"sale_date": date, "sale_price": sale_price, "fee_amount": fee},
    }
    if average_cost is not None:
        sale["average_cost"] = average_cost
    return sale


@pytest.fixture()
def build(realized_results_module):
    return realized_results_module.build_variable_realized_result


class TestRealizedResult:
    def test_the_cost_basis_is_the_quantity_times_the_average_cost(self, build):
        result = build(make_sale(150, 30.0, average_cost=15.0))
        assert result["cost_basis"] == pytest.approx(2250.0)
        assert result["average_cost"] == pytest.approx(15.0)
        assert result["realized_profit"] == pytest.approx(150 * 30.0 - 2250.0)
        assert result["metadata"]["cost_method"] == "AVERAGE"
        assert result["metadata"]["allocations"][0]["unit_cost"] == pytest.approx(15.0)

    def test_without_an_average_cost_it_falls_back_to_the_recorded_price(self, build):
        result = build(make_sale(50, 15.0, average_price=8.0))
        assert result["cost_basis"] == pytest.approx(400.0)

    def test_fees_are_deducted_from_the_net_proceeds(self, build):
        result = build(make_sale(100, 15.0, average_cost=10.0, fee=25.0))
        assert result["gross_proceeds"] == pytest.approx(1500.0)
        assert result["fee_amount"] == pytest.approx(25.0)
        assert result["net_proceeds"] == pytest.approx(1475.0)
        assert result["realized_profit"] == pytest.approx(475.0)

    def test_the_standalone_estimate_is_15_for_stocks_and_20_for_reits(self, build):
        # refresh_realized_results() troca pelo imposto do mes (test_variable_income_tax.py).
        assert build(make_sale(100, 20.0, average_cost=10.0))["tax_amount"] == pytest.approx(150.0)
        assert build(make_sale(100, 20.0, average_cost=10.0, asset_class="REIT"))["tax_amount"] == pytest.approx(200.0)

    def test_a_loss_generates_no_tax(self, build):
        result = build(make_sale(100, 10.0, average_cost=20.0))
        assert result["realized_profit"] == pytest.approx(-1000.0)
        assert result["tax_amount"] == pytest.approx(0.0)


# --- Pela API ---------------------------------------------------------------


def trade(client, auth, ticker, quantity, price, date, *, asset_class="STOCKS", recorded_price=None):
    """Uma operacao pela API. Na venda, `recorded_price` e o que vai na coluna de
    preco (a tela manda o preco medio; a API aceitava o de venda)."""
    sale = quantity < 0
    payload = {
        "asset_class": asset_class,
        "ticker_or_name": ticker,
        "quantity": quantity,
        "average_price": recorded_price if sale and recorded_price is not None else price,
        "current_price": price,
        "metadata": {"sale_date": date, "sale_price": price} if sale else {"purchase_date": date},
    }
    response = client.post("/api/investments", headers=auth, json=payload)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()[0]


def position(client, auth, ticker):
    body = client.get("/api/investments/portfolio", headers=auth).get_json()
    return next(item for item in body["assets"] if item["ticker"] == ticker)


def realized(client, auth, ticker):
    rows = client.get("/api/investments", headers=auth).get_json()
    return next(row for row in rows if row["ticker_or_name"] == ticker and row["quantity"] < 0)


def test_two_buys_and_a_partial_sale_share_one_cost(client, auth):
    # O caso da WEGE3 no seed: com FIFO a venda dava prejuizo de R$ 77 e Bens e
    # Direitos, a Posicao e o custo medio diziam tres custos diferentes.
    trade(client, auth, "WEGE3", 59, 34.153051, "2024-10-07")
    trade(client, auth, "WEGE3", 64, 31.126563, "2025-06-07")
    trade(client, auth, "WEGE3", -61, 32.87, "2025-07-14", recorded_price=32.87)

    average = (59 * 34.153051 + 64 * 31.126563) / 123
    sale = realized(client, auth, "WEGE3")
    assert sale["realized_cost_basis"] == pytest.approx(61 * average, abs=0.01)
    assert sale["realized_profit"] == pytest.approx(61 * 32.87 - 61 * average, abs=0.01)
    assert sale["realized_profit"] > 0

    held = position(client, auth, "WEGE3")
    assert held["quantity"] == 62
    assert held["average_price"] == pytest.approx(average, abs=0.01)
    assert held["total_invested"] == pytest.approx(62 * average, abs=0.01)

    report = client.get("/api/tax-report?year=2025", headers=auth).get_json()
    bens = next(item for item in report["bens_e_direitos"] if item["ticker"] == "WEGE3")
    assert bens["cost"] == pytest.approx(held["total_invested"], abs=0.01)


def test_the_screen_and_the_api_sale_give_the_same_position(client, auth):
    trade(client, auth, "PETR4", 52, 38.484231, "2024-04-07")
    trade(client, auth, "PETR4", -26, 43.95, "2024-05-20", recorded_price=43.95)
    held = position(client, auth, "PETR4")
    assert held["average_price"] == pytest.approx(38.48, abs=0.01)
    assert held["total_invested"] == pytest.approx(26 * 38.484231, abs=0.01)


@pytest.fixture()
def no_market(app_module, prices_module, monkeypatch):
    # Como em test_portfolio_evolution.py: sem yfinance, nada vai a rede.
    monkeypatch.setattr(importlib.import_module("routes.investments"), "yf", None)
    monkeypatch.setattr(prices_module, "yf", None)


def months_ago(months):
    dates = importlib.import_module("dates")
    return dates.subtract_months(datetime.now(), months).replace(day=5).strftime("%Y-%m-%d")


def test_a_profitable_sale_does_not_drop_the_position_from_the_evolution(client, auth, no_market):
    # Antes: o aplicado descontava o valor da venda (60 x 30 = 1.800 de 1.000) e
    # ficava <= 0, e a posicao sumia da evolucao e da rentabilidade enquanto a
    # Posicao a mostrava.
    trade(client, auth, "ITUB4", 100, 10.0, months_ago(3))
    trade(client, auth, "ITUB4", -60, 30.0, months_ago(2), recorded_price=30.0)
    response = client.get("/api/investments/history?months=6", headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    last = response.get_json()["evolution"][-1]
    assert last["valorAplicado"] == pytest.approx(400.0)
    assert last["patrimonioBruto"] == pytest.approx(40 * 30.0)
