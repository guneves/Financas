"""Aportes x resgates por mes (GET /api/investments/contributions).

O que estes testes fixam:

- a janela tem todos os meses ate o atual, inclusive os vazios, e respeita o
  limite (padrao 12, no maximo 60);
- compra e aporte (quantidade x preco, sem custos); venda e resgate de renda
  fixa sao resgates (bruto: preco de venda / valor resgatado);
- a compra de um ativo no exterior entra em reais, pelo cambio da compra;
- a bonificacao (compra sem caixa de um evento corporativo) nao e aporte;
- o filtro por classe, e nada de outro usuario aparece.
"""

import importlib
from datetime import date, timedelta

import pytest

TODAY = date(2026, 9, 15)


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
    prices = importlib.import_module("services.prices")
    monkeypatch.setattr(prices, "download_close_prices", lambda symbols, **kwargs: {})
    # Registrar um evento corporativo busca a cotacao; aqui, sem rede.
    monkeypatch.setattr(
        importlib.import_module("routes.investments"), "refresh_market_prices",
        lambda *args, **kwargs: {"updated_count": 0},
    )
    monkeypatch.setattr(importlib.import_module("services.contributions"), "local_today", lambda: TODAY)


def post(client, auth, payload):
    response = client.post("/api/investments", headers=auth, json=payload)
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    body = response.get_json()
    return body[0] if isinstance(body, list) else body


def buy(client, auth, ticker, quantity, price, day, *, asset_class="STOCKS", currency=None, other_costs=0):
    payload = {
        "asset_class": asset_class,
        "ticker_or_name": ticker,
        "quantity": quantity,
        "average_price": price,
        "current_price": price,
        "metadata": {"purchase_date": day, "other_costs": other_costs},
    }
    if currency:
        payload["currency"] = currency
    return post(client, auth, payload)


def sell(client, auth, ticker, quantity, price, day):
    return post(client, auth, {
        "asset_class": "STOCKS",
        "ticker_or_name": ticker,
        "quantity": -quantity,
        "average_price": price,
        "current_price": price,
        "metadata": {"sale_date": day, "sale_price": price, "other_costs": 5},
    })


def contributions(client, auth, **query):
    response = client.get("/api/investments/contributions", headers=auth, query_string=query)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def month(body, key):
    return next(item for item in body["months"] if item["month"] == key)


def test_every_month_of_the_window_is_listed_even_empty(client, auth):
    body = contributions(client, auth)
    assert [item["month"] for item in body["months"]] == [
        "2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03",
        "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09",
    ]
    assert body["start_month"] == "2025-10" and body["end_month"] == "2026-09"
    assert all(item["aportes"] == 0 and item["resgates"] == 0 for item in body["months"])
    assert body["totals"] == {"aportes": 0, "resgates": 0, "liquido": 0, "count": 0}


def test_months_default_minimum_and_cap(client, auth):
    assert len(contributions(client, auth, months=3)["months"]) == 3
    assert len(contributions(client, auth, months=100)["months"]) == 60
    assert len(contributions(client, auth, months=0)["months"]) == 1
    assert len(contributions(client, auth, months="abc")["months"]) == 12


def test_buys_are_contributions_and_sells_are_gross_withdrawals(client, auth):
    buy(client, auth, "PETR4", 100, 10.0, "2026-03-10", other_costs=7)
    buy(client, auth, "PETR4", 50, 12.0, "2026-03-20")
    sell(client, auth, "PETR4", 40, 15.0, "2026-05-05")
    buy(client, auth, "PETR4", 10, 10.0, "2024-01-10")  # fora da janela

    body = contributions(client, auth)
    march = month(body, "2026-03")
    assert march["aportes"] == 1600 and march["resgates"] == 0 and march["count"] == 2
    may = month(body, "2026-05")
    # Bruto: 40 x 15, sem os custos de 5.
    assert may["resgates"] == 600 and may["aportes"] == 0 and may["liquido"] == -600
    assert body["totals"] == {"aportes": 1600, "resgates": 600, "liquido": 1000, "count": 3}


def test_a_foreign_buy_is_counted_in_reais_at_its_rate(client, auth):
    buy(client, auth, "AAPL", 10, 100.0, "2026-04-06", currency="USD")
    assert month(contributions(client, auth), "2026-04")["aportes"] == 5000  # 10 x US$ 100 x 5,00


def test_a_fixed_income_redemption_counts_its_redeemed_value(client, auth):
    title = buy(client, auth, "CDB BANCO X", 1, 1000.0, "2026-02-02", asset_class="FIXED_INCOME")
    post(client, auth, {
        "asset_class": "FIXED_INCOME",
        "ticker_or_name": "CDB BANCO X",
        "quantity": -1,
        "average_price": 400.0,     # base de custo resgatada
        "current_price": 450.0,     # valor resgatado
        "metadata": {
            "is_redemption": True, "affects_position": True,
            "related_id": title["id"], "redemption_date": "2026-08-03",
        },
    })
    body = contributions(client, auth)
    assert month(body, "2026-02")["aportes"] == 1000
    assert month(body, "2026-08")["resgates"] == 450


def test_a_bonus_is_not_a_contribution(client, auth):
    purchase = buy(client, auth, "ITSA4", 100, 10.0, "2026-03-10")
    response = client.post("/api/corporate-actions", headers=auth, json={
        "asset_id": purchase["asset_id"], "action_type": "BONUS", "ex_date": "2026-06-01",
        "ratio_from": 10, "ratio_to": 1, "bonus_unit_cost": 2,
    })
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    body = contributions(client, auth)
    assert month(body, "2026-06")["aportes"] == 0
    assert body["totals"]["aportes"] == 1000


def test_class_filter(client, auth):
    buy(client, auth, "PETR4", 10, 10.0, "2026-03-10")
    buy(client, auth, "MXRF11", 10, 10.0, "2026-03-10", asset_class="REIT")
    assert contributions(client, auth, asset_class="REIT")["totals"]["aportes"] == 100
    assert contributions(client, auth, asset_class="reit")["asset_class"] == "REIT"
    assert contributions(client, auth)["totals"]["aportes"] == 200
    # Classe desconhecida = sem filtro, como o resto das telas de investimento.
    assert contributions(client, auth, asset_class="XYZ")["totals"]["aportes"] == 200


def test_another_users_operations_do_not_appear(client, auth, other_user):
    buy(client, auth, "PETR4", 100, 10.0, "2026-03-10")
    stranger = contributions(client, other_user["headers"])
    assert stranger["totals"]["aportes"] == 0 and stranger["totals"]["count"] == 0


def test_requires_a_token(client):
    assert client.get("/api/investments/contributions").status_code == 401


def test_aggregation_is_pure_and_rounds_half_up(app_module):
    contributions_module = importlib.import_module("services.contributions")
    rows = [
        {"asset_class": "STOCKS", "quantity": 1, "average_price": 0.125, "movement_type": "BUY",
         "metadata": {"purchase_date": "2026-09-01"}},
        {"asset_class": "STOCKS", "quantity": 1, "average_price": 10.0, "movement_type": "BUY",
         "metadata": {"purchase_date": "2026-09-01", "corporate_action_id": "evento"}},
    ]
    body = contributions_module.aggregate_contributions(rows, 1, TODAY)
    assert body["months"] == [{"month": "2026-09", "aportes": 0.13, "resgates": 0, "liquido": 0.13, "count": 1}]
