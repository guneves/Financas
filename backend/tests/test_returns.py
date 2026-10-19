"""Rentabilidade ponderada no tempo (TWR): services/returns.py e GET /api/investments/returns.

As funcoes de conta sao testadas puras (valores, fluxos, proventos); a rota, com
o historico diario do yfinance e o CDI do BCB trocados onde sao lidos
(`routes.investments` para `yf` e `get_daily_history`, `services.fixed_income`
para `fetch_bcb_series`). Os caminhos de preco sao mensais: cada dia do mes
fecha no preco daquele mes (`daily_history_from_months` no conftest).
"""

import importlib
from datetime import datetime, timedelta

import pytest


@pytest.fixture()
def returns_module(app_module):
    return importlib.import_module("services.returns")


# --- funcoes puras ---------------------------------------------------------------

class TestDailyReturn:
    def test_buy_and_hold_equals_the_price_change(self, returns_module):
        r = returns_module
        # Compra 100 x 10 (fecha a 10,50), depois 11 e 12.
        days = [
            r.daily_return(0, 1050, inflow=1000),
            r.daily_return(1050, 1100),
            r.daily_return(1100, 1200),
        ]
        assert days[0] == pytest.approx(0.05)
        assert r.chain_returns(days) == pytest.approx(0.20)

    def test_a_buy_enters_at_the_price_paid(self, returns_module):
        # Valia 1.000, compra mais 1.000 e o dia fecha sem variacao: zero.
        assert returns_module.daily_return(1000, 2000, inflow=1000) == pytest.approx(0)

    def test_a_contribution_does_not_move_twr(self, returns_module):
        r = returns_module
        alone = r.chain_returns([r.daily_return(1000, 1100), r.daily_return(1100, 1200)])
        with_contribution = r.chain_returns([r.daily_return(1000, 1100), r.daily_return(1100, 2400, inflow=1100)])
        assert with_contribution == pytest.approx(alone)
        assert alone == pytest.approx(0.20)

    def test_a_provento_adds_to_the_day(self, returns_module):
        assert returns_module.daily_return(1000, 1000, income=50) == pytest.approx(0.05)

    def test_proventos_are_not_added_twice_if_prices_become_adjusted(self, returns_module, monkeypatch):
        monkeypatch.setattr(returns_module, "PRICES_ARE_DIVIDEND_ADJUSTED", True)
        assert returns_module.daily_return(1000, 1000, income=50) == pytest.approx(0)

    def test_a_sale_leaves_at_what_it_paid(self, returns_module):
        # Valia 1.000 ontem, vende tudo hoje por 1.100: +10%, sem base negativa.
        assert returns_module.daily_return(1000, 0, outflow=1100) == pytest.approx(0.10)

    def test_bought_and_sold_on_the_same_day(self, returns_module):
        assert returns_module.daily_return(0, 0, inflow=1000, outflow=1050) == pytest.approx(0.05)

    def test_a_day_without_base_is_skipped(self, returns_module):
        r = returns_module
        assert r.daily_return(0, 0) is None
        assert r.daily_return(0, 0, income=10) is None
        assert r.chain_returns([None, 0.10, None]) == pytest.approx(0.10)
        assert r.chain_returns([None, None]) is None

    def test_a_bonus_is_not_a_contribution(self, returns_module):
        bonus = {
            "quantity": 14, "average_price": 5.0,
            "metadata": {"is_bonus": True, "corporate_action_id": "evento"},
        }
        purchase = {"quantity": 14, "average_price": 5.0, "metadata": {}}
        assert returns_module.movement_flow_amount(bonus) == 0
        assert returns_module.movement_flow_amount(purchase) == pytest.approx(70.0)


class TestQuantityBasis:
    """O Yahoo trata a bonificacao como desdobramento e ajusta o fechamento anterior."""

    def test_a_bonus_is_undone_on_the_days_before_it(self, prices_module):
        prices = {"KLBN4": {"2024-05-06": 4.0, "2024-05-07": 4.1}}
        restored = prices_module.restore_quantity_basis(prices, {"KLBN4": [("2024-05-07", 1.1)]}, {})
        assert restored["KLBN4"]["2024-05-06"] == pytest.approx(4.4)
        assert restored["KLBN4"]["2024-05-07"] == pytest.approx(4.1)

    def test_a_registered_split_keeps_the_yahoo_adjustment(self, prices_module):
        # O desdobramento registrado ja reescalou as quantidades (data ex um dia antes).
        prices = {"FESA4": {"2024-01-22": 11.0, "2024-01-24": 10.9}}
        restored = prices_module.restore_quantity_basis(
            prices, {"FESA4": [("2024-01-24", 4.0)]}, {"FESA4": [("2024-01-23", 4.0)]},
        )
        assert restored == prices

    def test_monthly_keys_are_adjusted_before_the_event_month(self, prices_module):
        prices = {"SOJA3": {"2025-11": 9.0, "2025-12": 8.5}}
        restored = prices_module.restore_quantity_basis(prices, {"SOJA3": [("2025-12-19", 1.05)]}, {})
        assert restored["SOJA3"] == {"2025-11": pytest.approx(9.45), "2025-12": pytest.approx(8.5)}

    def test_monthly_closes_take_the_last_day(self, prices_module):
        daily = {"PETR4": {"2026-01-30": 10.0, "2026-01-02": 9.0, "2026-02-27": 11.0}}
        assert prices_module.monthly_closes(daily) == {"PETR4": {"2026-01": 10.0, "2026-02": 11.0}}


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
def market(app_module, prices_module, monkeypatch, daily_history_from_months):
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
    monkeypatch.setattr(routes, "get_daily_history", lambda tickers, start: daily_history_from_months(fake_history(tickers, start)))
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
        # Comprado ha 3 meses numa janela de 6: a comparacao comeca na compra,
        # com o ponto de 0% no fim do mes anterior a ela.
        assert [item["month_key"] for item in body["series"]] == [key(4), key(3), key(2), key(1), key(0)]
        assert body["series"][0]["base"] is True
        assert body["series"][0]["accumulated_percent"] == 0.0
        assert body["comparison"]["start"] == key(3)
        assert body["comparison"]["starts_after_window"] is True
        assert body["period"]["start"] == key(5)
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
        # 60 meses e o ponto de partida (0%) antes do primeiro.
        assert len(returns(client, auth, months=500)["series"]) == 61

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


# --- o mes atual vale o que a Posicao mostra --------------------------------------

def fixed_income_title(client, auth, date, *, current_price, amount=10000.0, name="CDB HOJE", redeem=None):
    """Titulo CDI 100%; `redeem` = (custo, recebido, data) de um resgate parcial."""
    response = client.post("/api/investments", headers=auth, json=[{
        "asset_class": "FIXED_INCOME", "ticker_or_name": name, "quantity": 1,
        "average_price": amount, "current_price": current_price,
        "metadata": {"fixed_income_type": "CDB", "rate_type": "POS", "indexer": "CDI",
                     "cdi_percentage": 1.0, "purchase_date": date},
    }])
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    created = response.get_json()
    title = created[0] if isinstance(created, list) else created
    if redeem:
        cost, received, when = redeem
        response = client.post("/api/investments", headers=auth, json=[{
            "asset_class": "FIXED_INCOME", "ticker_or_name": name, "quantity": -1,
            "average_price": cost, "current_price": received,
            "metadata": {"is_redemption": True, "affects_position": True,
                         "related_id": title["id"], "redemption_date": when},
        }])
        assert response.status_code in (200, 201), response.get_data(as_text=True)
    return title


def portfolio(client, auth):
    response = client.get("/api/investments/portfolio?refresh_prices=false", headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


class TestCurrentMonthMatchesThePosition:
    """Rentabilidade "Carteira hoje" = Posicao "Carteira" (achado do seed: R$ 25,58).

    O mes atual da TWR (e da evolucao) valia a renda fixa sem cotacao do BCB
    pela serie recalculada ate hoje e a bolsa pelo fechamento do mes no
    historico; a Posicao usa a cotacao gravada. Agora os dois saem de
    `position_value_today()`.
    """

    def assert_same_value(self, client, auth):
        snapshot = portfolio(client, auth)
        body = returns(client, auth, months=6)
        assert body["series"][-1]["value"] == pytest.approx(snapshot["current_balance"], abs=0.005)
        by_ticker = {asset["ticker"]: asset["current_value"] for asset in body["assets"] if asset["open"]}
        assert by_ticker == {
            asset["ticker"]: pytest.approx(asset["current_value"], abs=0.005)
            for asset in snapshot["assets"]
        }
        return snapshot, body

    def test_fixed_income_with_a_manual_price(self, client, auth, market):
        # Preco manual diferente do que a serie do CDI daria ate hoje.
        fixed_income_title(client, auth, iso(4), current_price=10321.45)
        snapshot, _ = self.assert_same_value(client, auth)
        assert snapshot["current_balance"] == pytest.approx(10321.45)

    def test_fixed_income_after_the_bcb_refresh_and_a_partial_redemption(self, client, auth, user, market):
        fixed_income_title(
            client, auth, iso(4), current_price=10000.0,
            redeem=(4000.0, 4100.0, (month_start(2) + timedelta(days=4)).strftime("%Y-%m-%d")),
        )
        investments = importlib.import_module("services.investments")
        fixed_income = importlib.import_module("services.fixed_income")
        result = fixed_income.refresh_fixed_income_prices(user["id"], investments.fetch_investments(user["id"]))
        assert result["updated_count"] == 1
        snapshot, _ = self.assert_same_value(client, auth)
        assert snapshot["current_balance"] > 6000.0

    def test_a_stock_uses_todays_quote_not_the_month_close(self, client, auth, market):
        # Fechamento do mes no historico: 12,00; cotacao gravada: 12,34.
        response = client.post("/api/investments", headers=auth, json={
            "asset_class": "STOCKS", "ticker_or_name": "PETR4", "quantity": 100,
            "average_price": 10.0, "current_price": 12.34,
            "metadata": {"purchase_date": iso(3)},
        })
        assert response.status_code in (200, 201), response.get_data(as_text=True)
        fixed_income_title(client, auth, iso(4), current_price=10321.45)
        snapshot, body = self.assert_same_value(client, auth)
        assert snapshot["current_balance"] == pytest.approx(1234.0 + 10321.45)
        # O mes passado continua no fechamento daquele mes (100 x 12,00 + a renda fixa).
        by_key = {item["month_key"]: item for item in body["series"]}
        assert by_key[key(1)]["value"] > 10000.0 + 1200.0 - 0.01

    def test_the_class_filter_and_the_evolution_agree_too(self, client, auth, market):
        fixed_income_title(client, auth, iso(4), current_price=10321.45)
        trade(client, auth, "PETR4", 100, 10.0, iso(3))
        snapshot = portfolio(client, auth)
        fixed = [asset for asset in snapshot["assets"] if asset["class"] == "FIXED_INCOME"]
        body = returns(client, auth, months=6, asset_class="FIXED_INCOME")
        assert body["series"][-1]["value"] == pytest.approx(sum(asset["current_value"] for asset in fixed))

        response = client.get("/api/investments/history", headers=auth, query_string={"months": 6})
        assert response.status_code == 200
        # A evolucao e liquida: o mes atual bate com o liquido da Posicao.
        assert response.get_json()["evolution"][-1]["patrimonio"] == pytest.approx(
            snapshot["current_net_balance"], abs=0.005,
        )


class TestBonus:
    """Bonificacao: o Yahoo ajusta o fechamento anterior como desdobramento, e as
    cotas chegam sem dinheiro. Preco negociado 11 ate a data ex e 10 depois
    (11 / 1,1): 100 cotas x 11 = 110 cotas x 10, rentabilidade zero."""

    def test_a_bonus_neither_drags_nor_lifts_the_return(self, client, auth, market, daily_history_from_months, monkeypatch):
        routes = importlib.import_module("routes.investments")
        ex_date = (month_start(2) + timedelta(days=14)).strftime("%Y-%m-%d")
        adjusted = {"PETR4": {key(months): 10.0 for months in (4, 3, 2, 1, 0)}}
        monkeypatch.setattr(
            routes, "get_daily_history",
            lambda tickers, start: daily_history_from_months(adjusted, {"PETR4": [(ex_date, 1.1)]}),
        )
        response = client.post("/api/investments", headers=auth, json={
            "asset_class": "STOCKS", "ticker_or_name": "PETR4", "quantity": 100,
            "average_price": 11.0, "current_price": 10.0,
            "metadata": {"purchase_date": iso(3)},
        })
        assert response.status_code in (200, 201), response.get_data(as_text=True)
        created = response.get_json()
        asset_id = (created[0] if isinstance(created, list) else created)["asset_id"]
        response = client.post("/api/corporate-actions", headers=auth, json={
            "asset_id": asset_id, "action_type": "BONUS", "ex_date": ex_date,
            "ratio_from": 10, "ratio_to": 1, "bonus_unit_cost": 5.0,
        })
        assert response.status_code == 201, response.get_data(as_text=True)

        body = returns(client, auth, months=6)
        assert body["twr_percent"] == pytest.approx(0.0, abs=0.01)
        by_key = {item["month_key"]: item for item in body["series"]}
        # As 10 cotas a R$ 5 nao sao aporte.
        assert by_key[key(2)]["net_flow"] == 0
        assert body["series"][-1]["value"] == pytest.approx(1100.0)


class TestSinceTheStart:
    def test_months_all_starts_at_the_first_operation(self, client, auth, market):
        trade(client, auth, "PETR4", 100, 10.0, iso(3))
        body = returns(client, auth, months="all")
        assert body["months"] == 4
        assert body["period"]["start"] == key(3)
        assert body["twr_percent"] == pytest.approx(20.0)

    def test_months_all_follows_the_class_filter(self, client, auth, market):
        trade(client, auth, "HGLG11", 10, 100.0, iso(3), asset_class="REIT")
        trade(client, auth, "PETR4", 100, 11.0, iso(2))
        assert returns(client, auth, months="all", asset_class="STOCKS")["months"] == 3
        assert returns(client, auth, months="all")["months"] == 4

    def test_months_all_on_an_empty_portfolio(self, client, auth, market):
        assert returns(client, auth, months="all")["months"] == 12
