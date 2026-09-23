"""GET /api/investments/history: the monthly series behind "Evolução do Patrimônio".

Each month carries the valor aplicado and the ganho de capital at month end.
yfinance is stubbed out, so a quoted asset falls back to its current price —
the series is deterministic and the suite never touches the network.
"""

from datetime import datetime

import pytest


@pytest.fixture()
def no_market(app_module, prices_module, monkeypatch):
    # A rota le `yf` para decidir se busca historico; o download tambem. Os dois.
    monkeypatch.setattr(app_module, "yf", None)
    monkeypatch.setattr(prices_module, "yf", None)
    return app_module


def months_ago(app_module, months):
    return app_module.subtract_months(datetime.now(), months).replace(day=1).strftime("%Y-%m-%d")


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
