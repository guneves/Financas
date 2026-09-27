"""Rentabilidade ponderada no tempo (TWR): services/returns.py e GET /api/investments/returns.

As funcoes de conta sao testadas puras (valores, fluxos, proventos); a rota, com
o historico mensal do yfinance e o CDI do BCB trocados onde sao lidos
(`routes.investments` para `yf` e `get_monthly_history`, `services.fixed_income`
para `fetch_bcb_series`).
"""

import importlib
from datetime import datetime, timedelta

import pytest


@pytest.fixture()
def returns_module(app_module):
    return importlib.import_module("services.returns")


# --- funcoes puras ---------------------------------------------------------------

class TestModifiedDietz:
    def test_single_buy_and_hold_equals_the_price_change(self, returns_module):
        r = returns_module
        # Compra de 100 x 10 no dia 15, fecha o mes a 11 e o seguinte a 12.
        first = r.modified_dietz(0, 1100, [(15, 1000)], period_days=30)
        second = r.modified_dietz(1100, 1200, [], period_days=31)
        assert first == pytest.approx(0.10)
        assert r.chain_returns([first, second]) == pytest.approx(0.20)

    def test_a_buy_on_the_last_day_is_not_magnified(self, returns_module):
        # Sem valor inicial o periodo comeca na compra: 1%, nao 31%.
        assert returns_module.modified_dietz(0, 1010, [(31, 1000)], period_days=31) == pytest.approx(0.01)

    def test_a_contribution_mid_period_does_not_move_twr(self, returns_module):
        r = returns_module
        # Mesmo caminho de preco (10 -> 11 -> 12), com e sem um aporte de 100 x 11
        # no inicio do segundo mes.
        alone = r.chain_returns([
            r.modified_dietz(1000, 1100, []),
            r.modified_dietz(1100, 1200, []),
        ])
        with_contribution = r.chain_returns([
            r.modified_dietz(1000, 1100, []),
            r.modified_dietz(1100, 2400, [(1, 1100)]),
        ])
        assert with_contribution == pytest.approx(alone)
        assert alone == pytest.approx(0.20)

    def test_a_mid_month_contribution_in_a_flat_month_is_zero(self, returns_module):
        assert returns_module.modified_dietz(1000, 1500, [(15, 500)], period_days=30) == pytest.approx(0)

    def test_a_month_with_a_provento_adds_it(self, returns_module):
        assert returns_module.modified_dietz(1000, 1000, [], income=50) == pytest.approx(0.05)

    def test_proventos_are_not_added_twice_if_prices_become_adjusted(self, returns_module, monkeypatch):
        monkeypatch.setattr(returns_module, "PRICES_ARE_DIVIDEND_ADJUSTED", True)
        assert returns_module.modified_dietz(1000, 1000, [], income=50) == pytest.approx(0)

    def test_a_full_sale_and_rebuy(self, returns_module):
        r = returns_module
        # Vende tudo no dia 10 por 1.100 (valia 1.000 no inicio): +10%.
        sale = r.modified_dietz(1000, 0, [(10, -1100)], period_days=30)
        assert sale == pytest.approx(0.10)
        # Mes sem posicao: pulado.
        empty = r.modified_dietz(0, 0, [], period_days=31)
        assert empty is None
        # Recompra 800 no dia 20, fecha a 1.000: +25%.
        rebuy = r.modified_dietz(0, 1000, [(20, 800)], period_days=30)
        assert rebuy == pytest.approx(0.25)
        assert r.chain_returns([sale, empty, rebuy]) == pytest.approx(1.10 * 1.25 - 1)

    def test_bought_and_sold_on_the_same_day(self, returns_module):
        assert returns_module.modified_dietz(0, 0, [(10, 1000), (10, -1050)]) == pytest.approx(0.05)

    def test_zero_value_months_are_skipped_not_divided_by_zero(self, returns_module):
        r = returns_module
        assert r.modified_dietz(0, 0, []) is None
        assert r.modified_dietz(0, 0, [], income=10) is None
        assert r.chain_returns([None, 0.10, None]) == pytest.approx(0.10)
        assert r.chain_returns([None, None]) is None

    def test_a_flow_is_weighted_by_the_time_it_was_invested(self, returns_module):
        # 1.000 no inicio, aporte de 1.000 no dia 16 de 30 (metade do mes), ganho de 150.
        value = returns_module.modified_dietz(1000, 2150, [(16, 1000)], period_days=30)
        assert value == pytest.approx(150 / 1500)


class TestHelpers:
    def test_cdi_monthly_returns_compounds_the_daily_rate(self, returns_module):
        series = [(datetime(2026, 1, day), 0.001) for day in (2, 5, 6)] + [(datetime(2026, 2, 2), 0.002)]
        result = returns_module.cdi_monthly_returns(series, ["2026-01", "2026-02", "2026-03"])
        assert result["2026-01"] == pytest.approx(1.001 ** 3 - 1)
        assert result["2026-02"] == pytest.approx(0.002)
        assert "2026-03" not in result

    def test_year_month_table(self, returns_module):
        table = returns_module.year_month_table([
            ("2025-12", 0.01), ("2026-01", 0.10), ("2026-02", None), ("2026-03", -0.05),
        ])
        assert [row["year"] for row in table] == [2025, 2026]
        assert table[0]["months"][11] == 1.0
        assert table[0]["total_percent"] == 1.0
        assert table[1]["months"][:4] == [10.0, None, -5.0, None]
        assert table[1]["total_percent"] == pytest.approx(round((1.10 * 0.95 - 1) * 100, 2))


# --- rota -------------------------------------------------------------------------

def month_start(months):
    subtract_months = importlib.import_module("dates").subtract_months
    return subtract_months(datetime.now().replace(day=1), months)


def iso(months):
    return month_start(months).strftime("%Y-%m-%d")


def key(months):
    return month_start(months).strftime("%Y-%m")


# Fechamento mensal de cada papel, por meses atras (0 = mes atual).
PRICE_PATHS = {
    "PETR4": {3: 10.0, 2: 11.0, 1: 12.0, 0: 12.0},
    "HGLG11": {3: 100.0, 2: 90.0, 1: 90.0, 0: 90.0},
}


@pytest.fixture()
def market(app_module, prices_module, monkeypatch):
    routes = importlib.import_module("routes.investments")
    fixed_income = importlib.import_module("services.fixed_income")
    fixed_income._index_history_cache.clear()

    def fake_history(tickers, start_date):
        return {
            ticker: {key(months): price for months, price in PRICE_PATHS.get(ticker, {}).items()}
            for ticker in tickers
        }

    def fake_cdi(code, start, end=None):
        end = end or datetime.now()
        days, day = [], start
        while day <= end:
            if day.weekday() < 5:
                days.append((day, 0.0004))
            day += timedelta(days=1)
        return days

    monkeypatch.setattr(prices_module, "yf", None)
    monkeypatch.setattr(routes, "yf", object())
    monkeypatch.setattr(routes, "get_monthly_history", fake_history)
    monkeypatch.setattr(fixed_income, "fetch_bcb_series", fake_cdi)
    # Indices de comparacao sem rede (test_benchmarks.py cobre esse caminho).
    benchmarks = importlib.import_module("services.benchmarks")
    benchmarks.reset_fetch_throttle()
    monkeypatch.setattr(benchmarks, "download_monthly_history", lambda tickers, start: {})
    monkeypatch.setattr(benchmarks.brapi_client, "is_configured", lambda: False)
    return app_module


def trade(client, auth, ticker, quantity, price, date, asset_class="STOCKS"):
    sale = quantity < 0
    response = client.post("/api/investments", headers=auth, json={
        "asset_class": asset_class,
        "ticker_or_name": ticker,
        "quantity": quantity,
        "average_price": price,
        "current_price": PRICE_PATHS[ticker][0],
        "metadata": {"sale_date": date, "sale_price": price} if sale else {"purchase_date": date},
    })
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    return response.get_json()


def dividend(client, auth, asset_id, per_unit, date):
    response = client.post("/api/investment-proceeds", headers=auth, json={
        "asset_id": asset_id,
        "proceeds_type": "DIVIDEND",
        "record_date": date,
        "payment_date": date,
        "amount_per_unit": per_unit,
    })
    assert response.status_code == 201, response.get_data(as_text=True)


def returns(client, auth, **params):
    response = client.get("/api/investments/returns", headers=auth, query_string=params)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


class TestEndpoint:
    def test_buy_and_hold(self, client, auth, market):
        trade(client, auth, "PETR4", 100, 10.0, iso(3))
        body = returns(client, auth, months=6)

        assert body["basis"] == "gross"
        assert body["twr_percent"] == pytest.approx(20.0)
        assert len(body["series"]) == 6
        assert body["series"][-1]["accumulated_percent"] == pytest.approx(20.0)
        assert body["series"][-1]["value"] == pytest.approx(1200.0)
        by_key = {item["month_key"]: item for item in body["series"]}
        assert by_key[key(2)]["return_percent"] == pytest.approx(10.0)
        assert by_key[key(3)]["net_flow"] == pytest.approx(1000.0)

        [asset] = body["assets"]
        assert asset["ticker"] == "PETR4"
        assert asset["twr_percent"] == pytest.approx(20.0)
        assert asset["capped"] is False
        assert asset["since"] == key(3)
        assert asset["open"] is True

    def test_cdi_and_percent_of_cdi(self, client, auth, market):
        trade(client, auth, "PETR4", 100, 10.0, iso(3))
        body = returns(client, auth, months=6)
        assert body["cdi_available"] is True
        assert body["cdi_percent"] > 0
        assert body["percent_of_cdi"] == pytest.approx(round(body["twr_percent"] / body["cdi_percent"] * 100, 2), rel=0.01)
        assert body["series"][-1]["cdi_accumulated_percent"] == pytest.approx(body["cdi_percent"])

    def test_a_contribution_mid_period_does_not_move_twr(self, client, auth, market):
        trade(client, auth, "PETR4", 100, 10.0, iso(3))
        # Novo aporte no inicio do mes, ao fechamento anterior (11).
        trade(client, auth, "PETR4", 100, 11.0, iso(1))
        body = returns(client, auth, months=6)
        assert body["twr_percent"] == pytest.approx(20.0, abs=0.01)
        assert body["series"][-1]["value"] == pytest.approx(2400.0)

    def test_a_provento_counts_as_income(self, client, auth, market):
        created = trade(client, auth, "PETR4", 100, 10.0, iso(3))
        asset_id = (created[0] if isinstance(created, list) else created)["asset_id"]
        dividend(client, auth, asset_id, 1.0, (month_start(1) + timedelta(days=9)).strftime("%Y-%m-%d"))
        body = returns(client, auth, months=6)
        by_key = {item["month_key"]: item for item in body["series"]}
        assert by_key[key(1)]["income"] == pytest.approx(100.0)
        # 10% e depois (1200 - 1100 + 100) / 1100.
        assert body["twr_percent"] == pytest.approx(round((1.1 * (1 + 200 / 1100) - 1) * 100, 2), abs=0.01)

    def test_a_full_sale(self, client, auth, market):
        trade(client, auth, "PETR4", 100, 10.0, iso(3))
        trade(client, auth, "PETR4", -100, 12.0, iso(1))
        body = returns(client, auth, months=6)
        # 10% ate o fechamento de 11, e a venda a 12 no primeiro dia do mes: +9,09%.
        assert body["twr_percent"] == pytest.approx(20.0, abs=0.01)
        [asset] = body["assets"]
        assert asset["open"] is False
        assert asset["current_value"] == 0

    def test_window_caps_the_per_asset_return(self, client, auth, market):
        trade(client, auth, "PETR4", 100, 10.0, iso(3))
        body = returns(client, auth, months=2)
        [asset] = body["assets"]
        assert asset["capped"] is True
        assert asset["since"] == key(1)
        # So o mes passado (11 -> 12) e o atual (12 -> 12).
        assert asset["twr_percent"] == pytest.approx(round((12 / 11 - 1) * 100, 2))
        assert body["twr_percent"] == asset["twr_percent"]

    def test_asset_class_filter(self, client, auth, market):
        trade(client, auth, "PETR4", 100, 10.0, iso(3))
        trade(client, auth, "HGLG11", 10, 100.0, iso(3), asset_class="REIT")
        assert returns(client, auth, months=6, asset_class="STOCKS")["twr_percent"] == pytest.approx(20.0)
        assert returns(client, auth, months=6, asset_class="REIT")["twr_percent"] == pytest.approx(-10.0)
        assert len(returns(client, auth, months=6)["assets"]) == 2

    def test_asset_class_filter_scopes_assets_and_proventos(self, client, auth, market):
        trade(client, auth, "PETR4", 100, 10.0, iso(3))
        created = trade(client, auth, "HGLG11", 10, 100.0, iso(3), asset_class="REIT")
        reit_id = (created[0] if isinstance(created, list) else created)["asset_id"]
        dividend(client, auth, reit_id, 1.0, (month_start(1) + timedelta(days=9)).strftime("%Y-%m-%d"))

        stocks = returns(client, auth, months=6, asset_class="STOCKS")
        assert [asset["class"] for asset in stocks["assets"]] == ["STOCKS"]
        # O provento do FII nao entra na rentabilidade das acoes.
        assert all(item["income"] == 0 for item in stocks["series"])

        reits = returns(client, auth, months=6, asset_class="reit")
        assert [asset["class"] for asset in reits["assets"]] == ["REIT"]
        assert sum(item["income"] for item in reits["series"]) > 0

        # Classe desconhecida (ou "todos") cai na carteira inteira.
        assert len(returns(client, auth, months=6, asset_class="XYZ")["assets"]) == 2
        assert len(returns(client, auth, months=6, asset_class="todos")["assets"]) == 2

    def test_year_table_and_ytd(self, client, auth, market):
        trade(client, auth, "PETR4", 100, 10.0, iso(3))
        body = returns(client, auth, months=6)
        current_year = datetime.now().year
        row = next(row for row in body["years"] if row["year"] == current_year)
        assert len(row["months"]) == 12
        assert row["total_percent"] == body["ytd_percent"]

    def test_months_is_capped_at_sixty(self, client, auth, market):
        assert len(returns(client, auth, months=500)["series"]) == 60

    def test_empty_portfolio(self, client, auth, market):
        body = returns(client, auth)
        assert body["twr_percent"] is None
        assert body["assets"] == []

    def test_another_users_movements_and_proventos_are_not_counted(self, client, auth, other_user, market):
        created = trade(client, other_user["headers"], "PETR4", 100, 10.0, iso(3))
        asset_id = (created[0] if isinstance(created, list) else created)["asset_id"]
        dividend(client, other_user["headers"], asset_id, 5.0, (month_start(1) + timedelta(days=9)).strftime("%Y-%m-%d"))
        assert returns(client, auth, months=6)["assets"] == []

        trade(client, auth, "PETR4", 100, 10.0, iso(3))
        body = returns(client, auth, months=6)
        assert body["twr_percent"] == pytest.approx(20.0)
        assert all(item["income"] == 0 for item in body["series"])

    def test_requires_a_token(self, client):
        assert client.get("/api/investments/returns").status_code == 401
