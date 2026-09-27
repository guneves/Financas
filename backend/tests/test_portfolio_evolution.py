"""GET /api/investments/history: the monthly series behind "Evolução do Patrimônio".

Each month carries the valor aplicado and the ganho de capital at month end.
yfinance is stubbed out, so a quoted asset falls back to its current price —
the series is deterministic and the suite never touches the network.
"""

import importlib
from datetime import datetime

import pytest


@pytest.fixture()
def no_market(app_module, prices_module, monkeypatch):
    # A rota le `yf` para decidir se busca historico; o download tambem. Os dois.
    monkeypatch.setattr(importlib.import_module("routes.investments"), "yf", None)
    monkeypatch.setattr(prices_module, "yf", None)
    return app_module


def months_ago(app_module, months):
    subtract_months = importlib.import_module("dates").subtract_months
    return subtract_months(datetime.now(), months).replace(day=1).strftime("%Y-%m-%d")


def post_buy(client, auth, *, ticker, quantity, price, current_price, date):
    response = client.post(
        "/api/investments",
        headers=auth,
        json={
            "asset_class": "STOCKS",
            "ticker_or_name": ticker,
            "quantity": quantity,
            "average_price": price,
            "current_price": current_price,
            "metadata": {"purchase_date": date},
        },
    )
    assert response.status_code in (200, 201), response.get_data(as_text=True)


def history(client, auth, **params):
    response = client.get("/api/investments/history", headers=auth, query_string=params)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["evolution"]


class TestPeriod:
    def test_default_is_twelve_months_ending_this_month(self, client, auth, no_market):
        evolution = history(client, auth)
        assert len(evolution) == 12
        assert evolution[-1]["month_key"] == datetime.now().strftime("%Y-%m")

    @pytest.mark.parametrize("months", [6, 24, 36, 60])
    def test_the_requested_period_is_returned(self, client, auth, no_market, months):
        assert len(history(client, auth, months=months)) == months

    def test_the_period_is_capped_at_sixty_months(self, client, auth, no_market):
        assert len(history(client, auth, months=500)) == 60


class TestAppliedAndGain:
    def test_a_buy_counts_from_its_month_on(self, client, auth, no_market):
        post_buy(client, auth, ticker="PETR4", quantity=100, price=10.0, current_price=12.5,
                 date=months_ago(no_market, 3))

        evolution = history(client, auth, months=6)
        before, after = evolution[:2], evolution[2:]

        for month in before:
            assert month["valorAplicado"] == 0
            assert month["patrimonio"] == 0
        for month in after:
            assert month["valorAplicado"] == pytest.approx(1000.0)
            assert month["patrimonio"] == pytest.approx(1250.0)
            assert month["ganhoCapitalReal"] == pytest.approx(250.0)

    def test_a_loss_is_reported_negative(self, client, auth, no_market):
        post_buy(client, auth, ticker="VALE3", quantity=10, price=50.0, current_price=40.0,
                 date=months_ago(no_market, 1))

        current = history(client, auth, months=2)[-1]
        assert current["valorAplicado"] == pytest.approx(500.0)
        assert current["patrimonio"] == pytest.approx(400.0)
        assert current["ganhoCapitalReal"] == pytest.approx(-100.0)


class TestIsolation:
    def test_another_users_investments_do_not_appear(self, client, auth, other_user, no_market):
        post_buy(client, auth, ticker="ITUB4", quantity=10, price=30.0, current_price=30.0,
                 date=months_ago(no_market, 2))

        for month in history(client, other_user["headers"], months=3):
            assert month["valorAplicado"] == 0
            assert month["patrimonio"] == 0


class TestFixedIncomeHistory:
    """Renda fixa nos meses passados (Fase 6): corrigida pela serie ate o fim do mes."""

    def cdi_title(self, client, auth, date):
        response = client.post(
            "/api/investments", headers=auth,
            json=[{
                "asset_class": "FIXED_INCOME", "ticker_or_name": "CDB HIST", "quantity": 1,
                "average_price": 10000, "current_price": 10000,
                "metadata": {"fixed_income_type": "CDB", "rate_type": "POS", "indexer": "CDI",
                             "cdi_percentage": 1.0, "purchase_date": date},
            }],
        )
        assert response.status_code in (200, 201), response.get_data(as_text=True)

    def test_past_months_accrue_with_the_cdi(self, client, auth, no_market, monkeypatch):
        fixed_income = importlib.import_module("services.fixed_income")
        fixed_income._index_history_cache.clear()
        from datetime import timedelta

        def fake_series(code, start, end=None):
            end = end or datetime.now()
            days, day = [], start
            while day <= end:
                if day.weekday() < 5:
                    days.append((day, 0.0005))
                day += timedelta(days=1)
            return days

        monkeypatch.setattr(fixed_income, "fetch_bcb_series", fake_series)
        self.cdi_title(client, auth, months_ago(no_market, 4))
        series = history(client, auth, months=6)
        past = [item for item in series if item["valorAplicado"] > 0][:-1]
        assert len(past) >= 3
        gains = [item["ganhoCapitalReal"] for item in past]
        # Cresce mes a mes, em vez de ficar no custo ate o mes atual.
        assert all(gain > 0 for gain in gains)
        assert gains == sorted(gains)
        # O mes atual vale o que a Posicao mostra: a cotacao gravada (aqui o
        # preco da compra, sem correcao do BCB ainda), nao a serie recalculada.
        portfolio = client.get(
            "/api/investments/portfolio?refresh_prices=false", headers=auth,
        ).get_json()
        assert series[-1]["patrimonio"] == portfolio["current_net_balance"] == pytest.approx(10000.0)

    def test_without_the_series_past_months_stay_at_cost(self, client, auth, no_market, monkeypatch):
        fixed_income = importlib.import_module("services.fixed_income")
        fixed_income._index_history_cache.clear()

        def offline(*args, **kwargs):
            raise RuntimeError("sem rede")

        monkeypatch.setattr(fixed_income, "fetch_bcb_series", offline)
        self.cdi_title(client, auth, months_ago(no_market, 4))
        past = [item for item in history(client, auth, months=6) if item["valorAplicado"] > 0][:-1]
        assert all(item["ganhoCapitalReal"] == 0 for item in past)


class TestGrossAndNet:
    """Duas bases na serie: bruta (a do "Carteira" da Posicao) e liquida do IR
    estimado da renda fixa. O grafico mostra a bruta; o tooltip, as duas."""

    def test_a_stock_has_the_same_gross_and_net(self, client, auth, no_market):
        post_buy(client, auth, ticker="PETR4", quantity=100, price=10.0, current_price=12.5,
                 date=months_ago(no_market, 2))

        current = history(client, auth, months=3)[-1]
        assert current["patrimonioBruto"] == pytest.approx(1250.0)
        assert current["patrimonio"] == pytest.approx(1250.0)
        assert current["ganhoCapitalBruto"] == pytest.approx(250.0)
        assert current["ganhoCapitalReal"] == pytest.approx(250.0)

    def test_fixed_income_gross_matches_the_portfolio_headline(self, client, auth, no_market, monkeypatch):
        fixed_income = importlib.import_module("services.fixed_income")
        fixed_income._index_history_cache.clear()

        def offline(*args, **kwargs):
            raise RuntimeError("sem rede")

        monkeypatch.setattr(fixed_income, "fetch_bcb_series", offline)
        response = client.post(
            "/api/investments", headers=auth,
            json=[{
                "asset_class": "FIXED_INCOME", "ticker_or_name": "CDB BRUTO", "quantity": 1,
                "average_price": 10000, "current_price": 11000,
                "metadata": {"fixed_income_type": "CDB", "rate_type": "POS", "indexer": "CDI",
                             "cdi_percentage": 1.0, "purchase_date": months_ago(no_market, 2)},
            }],
        )
        assert response.status_code in (200, 201), response.get_data(as_text=True)

        current = history(client, auth, months=3)[-1]
        portfolio = client.get("/api/investments/portfolio", headers=auth).get_json()

        # O IR estimado separa as duas bases...
        assert current["patrimonioBruto"] > current["patrimonio"]
        assert current["ganhoCapitalBruto"] == pytest.approx(
            current["patrimonioBruto"] - current["valorAplicado"], abs=0.01,
        )
        # ...e cada uma bate com o numero da Posicao na mesma base.
        assert current["patrimonioBruto"] == pytest.approx(portfolio["current_balance"], abs=0.01)
        assert current["patrimonio"] == pytest.approx(portfolio["current_net_balance"], abs=0.01)
