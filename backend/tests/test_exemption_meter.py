"""Isentometro (GET /api/tax-report/exemption): vendas de acoes no mes x R$ 20 mil.

O que estes testes fixam:

- soma as vendas de acoes em reais do mes, com a mesma apuracao do relatorio
  anual (o mes passa a ser tributado acima de R$ 20.000, e ate 20.000 inclusive
  e isento);
- FII nao entra na conta da isencao;
- `planned_sale` simula uma venda: diz se ela faria o mes passar do limite;
- o saldo de prejuizo sai certo mesmo num mes sem venda;
- nada de outro usuario entra.
"""

import importlib
from datetime import timedelta

import pytest


@pytest.fixture(autouse=True)
def offline(app_module, monkeypatch):
    fx = importlib.import_module("services.fx")
    fx.reset_fetch_throttle()

    def ptax(series, start, end):
        rows, day = [], start.date()
        while day <= end.date():
            if day.weekday() < 5:
                rows.append({"data": day.strftime("%d/%m/%Y"), "valor": "5.0000"})
            day += timedelta(days=1)
        return rows

    monkeypatch.setattr(fx, "fetch_bcb_window", ptax)


def trade(client, auth, ticker, quantity, price, date, *, asset_class="STOCKS"):
    sale = quantity < 0
    response = client.post("/api/investments", headers=auth, json={
        "asset_class": asset_class,
        "ticker_or_name": ticker,
        "quantity": quantity,
        "average_price": price,
        "current_price": price,
        "metadata": {"sale_date": date, "sale_price": price} if sale else {"purchase_date": date},
    })
    assert response.status_code in (200, 201), response.get_data(as_text=True)


def meter(client, auth, month, **query):
    response = client.get("/api/tax-report/exemption", headers=auth, query_string={"month": month, **query})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def test_sales_in_the_month_against_the_limit(client, auth):
    trade(client, auth, "PETR4", 1000, 10.0, "2025-01-10")
    trade(client, auth, "PETR4", -300, 12.0, "2025-02-05")   # 3.600
    trade(client, auth, "PETR4", -200, 12.0, "2025-02-20")   # 2.400
    body = meter(client, auth, "2025-02")
    assert body["stock_sales"] == 6000
    assert body["remaining"] == 14000
    assert body["percent"] == 30
    assert body["exempt"] is True
    assert body["stock_result"] == 1000
    assert body["stock_tax"] == 0


def test_exactly_20k_is_still_exempt_and_above_is_taxed(client, auth):
    trade(client, auth, "PETR4", 3000, 10.0, "2025-01-10")
    trade(client, auth, "PETR4", -1000, 20.0, "2025-02-10")   # 20.000 cravados
    assert meter(client, auth, "2025-02")["exempt"] is True
    trade(client, auth, "PETR4", -1, 20.0, "2025-03-10")
    trade(client, auth, "PETR4", -1000, 20.01, "2025-03-11")   # 20.030
    march = meter(client, auth, "2025-03")
    assert march["exempt"] is False and march["remaining"] == 0
    assert march["stock_tax"] == pytest.approx(march["stock_result"] * 0.15, abs=0.01)


def test_reit_sales_do_not_count_toward_the_exemption(client, auth):
    trade(client, auth, "MXRF11", 5000, 10.0, "2025-01-10", asset_class="REIT")
    trade(client, auth, "MXRF11", -3000, 11.0, "2025-02-10", asset_class="REIT")   # 33.000 em FII
    body = meter(client, auth, "2025-02")
    assert body["stock_sales"] == 0 and body["exempt"] is True
    assert body["reit_sales"] == 33000
    assert body["reit_tax"] == 600   # 20% de 3.000


def test_planned_sale_warns_before_crossing_the_limit(client, auth):
    trade(client, auth, "PETR4", 2000, 10.0, "2025-01-10")
    trade(client, auth, "PETR4", -1500, 10.0, "2025-02-10")   # 15.000
    ok = meter(client, auth, "2025-02", planned_sale=5000)
    assert ok["would_exceed"] is False and ok["sales_after"] == 20000
    over = meter(client, auth, "2025-02", planned_sale=5000.01)
    assert over["would_exceed"] is True


def test_loss_balance_carries_into_a_month_without_sales(client, auth):
    trade(client, auth, "PETR4", 3000, 10.0, "2025-01-10")
    trade(client, auth, "PETR4", -2500, 9.0, "2025-02-10")   # 22.500, prejuizo 2.500
    assert meter(client, auth, "2025-02")["stock_loss_balance"] == 2500
    quiet = meter(client, auth, "2025-04")
    assert quiet["stock_sales"] == 0 and quiet["stock_loss_balance"] == 2500


def test_invalid_month_is_refused(client, auth):
    assert client.get("/api/tax-report/exemption?month=2025-13", headers=auth).status_code == 400


def test_another_users_sales_do_not_count(client, auth, other_user):
    trade(client, auth, "PETR4", 1000, 10.0, "2025-01-10")
    trade(client, auth, "PETR4", -500, 10.0, "2025-02-10")
    stranger = meter(client, other_user["headers"], "2025-02")
    assert stranger["stock_sales"] == 0
