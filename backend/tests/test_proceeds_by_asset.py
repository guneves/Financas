"""Proventos por ativo: o `by_asset` do resumo e a rentabilidade com proventos.

O que estes testes fixam:

- `GET /api/investment-proceeds/summary` agrupa por ativo (eventos, bruto,
  imposto, liquido, fatia do total, YOC sobre o custo na data com e o liquido
  dos ultimos 12 meses), do maior liquido para o menor, respeitando os filtros;
- o liquido de 12 meses e uma janela movel ate hoje: respeita ativo e tipo,
  nao o periodo;
- a carteira ganha `proceeds_net`, `proceeds_12m_net`, `dividend_yield_12m` e
  `total_return_percent`; provento agendado nao conta como recebido;
- rentabilidade com proventos numa venda parcial: base = tudo o que entrou no
  ativo (custo atual + custo das cotas vendidas); `profitability_percent` nao
  muda;
- provento de ativo estrangeiro entra como esta gravado (reais, regra atual);
- renda fixa recebe a amortizacao que aponta para o ativo do titulo;
- nada de outro usuario entra, nem no resumo nem na carteira.
"""

import importlib
from datetime import date, datetime, timedelta

import pytest

TODAY = date.today()


def days(offset):
    return (TODAY + timedelta(days=offset)).isoformat()


def fake_ptax(series, start, end):
    rows = []
    day = start.date() if isinstance(start, datetime) else start
    last = end.date() if isinstance(end, datetime) else end
    while day <= last:
        if day.weekday() < 5:
            rows.append({"data": day.strftime("%d/%m/%Y"), "valor": "5.0000"})
        day += timedelta(days=1)
    return rows


@pytest.fixture(autouse=True)
def offline(app_module, monkeypatch):
    fx = importlib.import_module("services.fx")
    fx.reset_fetch_throttle()
    monkeypatch.setattr(fx, "fetch_bcb_window", fake_ptax)
    prices = importlib.import_module("services.prices")
    monkeypatch.setattr(prices, "download_close_prices", lambda symbols, **kwargs: {})

    def no_bcb(code, start, end=None):
        raise RuntimeError("sem rede nos testes")

    monkeypatch.setattr(importlib.import_module("services.fixed_income"), "fetch_bcb_series", no_bcb)


def trade(client, auth, ticker, quantity, price, when, *, currency=None):
    sale = quantity < 0
    payload = {
        "asset_class": "STOCKS",
        "ticker_or_name": ticker,
        "quantity": quantity,
        "average_price": price,
        "current_price": price,
        "metadata": {"sale_date": when, "sale_price": price} if sale else {"purchase_date": when},
    }
    if currency:
        payload["currency"] = currency
    response = client.post("/api/investments", headers=auth, json=payload)
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    body = response.get_json()
    return (body[0] if isinstance(body, list) else body)["asset_id"]


def provento(client, auth, asset_id, paid_on, *, kind="DIVIDEND", per_unit=None, gross=None, record=None):
    response = client.post(
        "/api/investment-proceeds",
        headers=auth,
        json={
            "asset_id": asset_id,
            "proceeds_type": kind,
            "record_date": record or paid_on,
            "payment_date": paid_on,
            "amount_per_unit": per_unit,
            "gross_amount": gross,
        },
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def summary(client, auth, **params):
    response = client.get("/api/investment-proceeds/summary", headers=auth, query_string=params)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def by_ticker(body):
    return {item["ticker"]: item for item in body["by_asset"]}


def position(portfolio_module, user, ticker):
    snapshot = portfolio_module.build_portfolio_snapshot(user["id"])
    return next(item for item in snapshot["assets"] if item["ticker"] == ticker)


@pytest.fixture()
def two_assets(client, auth):
    """PETR4: 100 a R$ 10, dividendo de R$ 1 e JCP de R$ 0,50 por cota (liquido
    42,50) no ultimo ano. ITSA4: 200 a R$ 5, dividendo de R$ 0,10 ha 400 dias."""
    petr = trade(client, auth, "PETR4", 100, 10.0, days(-800))
    itsa = trade(client, auth, "ITSA4", 200, 5.0, days(-800))
    provento(client, auth, petr, days(-30), per_unit=1.0)
    # data com em 2025: JCP a 15% (com data com em 2026 seria 17,5%)
    provento(client, auth, petr, days(-60), kind="JCP", per_unit=0.5, record="2025-12-01")
    provento(client, auth, itsa, days(-400), per_unit=0.1)
    return {"PETR4": petr, "ITSA4": itsa}


def test_summary_groups_by_asset_sorted_by_net(client, auth, two_assets):
    body = summary(client, auth)
    assert [item["ticker"] for item in body["by_asset"]] == ["PETR4", "ITSA4"]

    petr = by_ticker(body)["PETR4"]
    assert petr["asset_id"] == two_assets["PETR4"]
    assert petr["asset_class"] == "STOCKS"
    assert petr["event_count"] == 2
    assert petr["gross_amount"] == 150.0
    assert petr["tax_amount"] == 7.5
    assert petr["net_amount"] == 142.5
    assert petr["cost_basis"] == 1000.0          # 100 x R$ 10, uma vez so
    assert petr["yield_on_cost_percent"] == 14.25   # 142,50 / 1.000
    assert petr["net_12m"] == 142.5
    assert petr["share_percent"] == 87.69        # 142,50 / 162,50

    itsa = by_ticker(body)["ITSA4"]
    assert itsa["net_amount"] == 20.0
    assert itsa["yield_on_cost_percent"] == 2.0  # 20 / (200 x R$ 5)
    assert itsa["net_12m"] == 0                  # pago ha 400 dias

    assert sum(item["net_amount"] for item in body["by_asset"]) == body["net_amount"] == 162.5
    assert body["cost_basis"] == 2000.0          # 1.000 + 1.000: cada ativo uma vez
    assert body["yield_on_cost_percent"] == 8.125  # 162,50 / 2.000


def test_yield_on_cost_counts_the_position_once_for_monthly_payers(client, auth):
    """Um ativo que paga todo mes: 12 pagamentos de R$ 0,10 sobre 100 cotas a
    R$ 10 rendem 12% sobre o custo, nao 1% (o liquido dividido por 12 custos)."""
    asset = trade(client, auth, "BBAS3", 100, 10.0, days(-400))
    for month in range(12):
        provento(client, auth, asset, days(-30 * (month + 1)), per_unit=0.1)

    body = summary(client, auth)
    bbas = by_ticker(body)["BBAS3"]
    assert bbas["event_count"] == 12
    assert bbas["net_amount"] == 120.0
    assert bbas["cost_basis"] == 1000.0
    assert bbas["yield_on_cost_percent"] == 12.0
    assert body["cost_basis"] == 1000.0
    assert body["yield_on_cost_percent"] == 12.0


def test_yield_on_cost_averages_the_cost_when_the_position_grows(client, auth):
    """100 cotas a R$ 10 no primeiro provento, mais 100 a R$ 20 antes do
    segundo: custo nas datas com de R$ 1.000 e R$ 3.000, media R$ 2.000."""
    asset = trade(client, auth, "PETR4", 100, 10.0, days(-200))
    provento(client, auth, asset, days(-150), per_unit=1.0)   # 100 x R$ 1
    trade(client, auth, "PETR4", 100, 20.0, days(-100))
    provento(client, auth, asset, days(-50), per_unit=1.0)    # 200 x R$ 1

    petr = by_ticker(summary(client, auth))["PETR4"]
    assert petr["net_amount"] == 300.0
    assert petr["cost_basis"] == 2000.0
    assert petr["yield_on_cost_percent"] == 15.0


def test_summary_by_asset_honours_the_filters(client, auth, two_assets):
    jcp = summary(client, auth, proceeds_type="JCP")
    assert [item["ticker"] for item in jcp["by_asset"]] == ["PETR4"]
    assert jcp["by_asset"][0]["net_amount"] == 42.5
    # 12 meses respeita o tipo filtrado.
    assert jcp["by_asset"][0]["net_12m"] == 42.5
    assert jcp["by_asset"][0]["share_percent"] == 100.0

    recent = summary(client, auth, date_from=days(-45))
    assert [item["ticker"] for item in recent["by_asset"]] == ["PETR4"]
    assert recent["by_asset"][0]["net_amount"] == 100.0
    # ...mas nao o periodo: e a janela movel dos ultimos 12 meses.
    assert recent["by_asset"][0]["net_12m"] == 142.5

    only_itsa = summary(client, auth, asset_id=two_assets["ITSA4"])
    assert [item["ticker"] for item in only_itsa["by_asset"]] == ["ITSA4"]


def test_scheduled_provento_is_not_received(client, auth, user, portfolio_module, two_assets):
    provento(client, auth, two_assets["PETR4"], days(30), record=days(-1), per_unit=2.0)

    petr = by_ticker(summary(client, auth))["PETR4"]
    assert petr["net_amount"] == 342.5
    assert petr["scheduled_net_amount"] == 200.0
    assert petr["paid_net_amount"] == 142.5
    assert petr["net_12m"] == 142.5

    asset = position(portfolio_module, user, "PETR4")
    assert asset["proceeds_net"] == 142.5
    assert asset["proceeds_12m_net"] == 142.5


def test_portfolio_carries_proceeds_per_asset(user, portfolio_module, two_assets):
    petr = position(portfolio_module, user, "PETR4")
    assert petr["proceeds_net"] == 142.5
    assert petr["proceeds_12m_net"] == 142.5
    assert petr["dividend_yield_12m"] == 14.25   # 142,50 / 1.000
    assert petr["profitability_percent"] == 0    # so preco: nao mudou
    assert petr["total_return_percent"] == 14.25

    itsa = position(portfolio_module, user, "ITSA4")
    assert itsa["proceeds_net"] == 20.0
    assert itsa["proceeds_12m_net"] == 0
    assert itsa["dividend_yield_12m"] == 0
    assert itsa["total_return_percent"] == 2.0


def test_total_return_with_partial_sale_and_proceeds(client, auth, user, portfolio_module):
    # Compra 100 a R$ 10 (R$ 1.000), vende 40 a R$ 15 (custo FIFO 400, lucro 200,
    # IR estimado 30 -> 170 liquido), recebe R$ 1 por cota nas 60 restantes.
    petr = trade(client, auth, "PETR4", 100, 10.0, days(-200))
    trade(client, auth, "PETR4", -40, 15.0, days(-100))
    provento(client, auth, petr, days(-20), per_unit=1.0)

    asset = position(portfolio_module, user, "PETR4")
    assert asset["quantity"] == 60
    assert asset["net_value"] == 900.0
    assert asset["proceeds_net"] == 60.0
    # Preco so, sobre o total_invested de sempre (1.000 - 600 vendidos): intacto.
    assert asset["profitability_percent"] == 125.0
    # (900 - 600 de custo atual + 60 + 170) / (600 + 400 vendidos) = 53%.
    assert asset["total_return_percent"] == 53.0
    assert asset["dividend_yield_12m"] == 6.67  # 60 / 900


def test_foreign_asset_proceeds_are_taken_as_stored(client, auth, user, portfolio_module):
    # PTAX falsa de 5,00: 10 AAPL a US$ 100 = R$ 5.000 de custo e de valor.
    aapl = trade(client, auth, "AAPL", 10, 100.0, days(-90), currency="USD")
    provento(client, auth, aapl, days(-10), gross=50.0)

    body = summary(client, auth)
    assert by_ticker(body)["AAPL"]["net_amount"] == 50.0

    asset = position(portfolio_module, user, "AAPL")
    assert asset["net_value"] == 5000.0
    assert asset["proceeds_net"] == 50.0   # nao 50 x 5,00
    assert asset["dividend_yield_12m"] == 1.0
    assert asset["total_return_percent"] == 1.0


def test_fixed_income_title_gets_the_amortization_of_its_asset(client, auth, user, portfolio_module):
    response = client.post(
        "/api/investments",
        headers=auth,
        json=[{
            "asset_class": "FIXED_INCOME",
            "ticker_or_name": "CDB AMORTIZA",
            "quantity": 1,
            "average_price": 1000,
            "current_price": 1000,
            "metadata": {"fixed_income_type": "CDB", "rate_type": "PRE", "annual_rate": 0.1, "purchase_date": days(-300)},
        }],
    )
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    asset_id = response.get_json()[0]["asset_id"]
    provento(client, auth, asset_id, days(-10), kind="AMORTIZATION", gross=50.0)

    snapshot = portfolio_module.build_portfolio_snapshot(user["id"])
    [title] = [item for item in snapshot["assets"] if item["asset_id"] == asset_id]
    assert title["proceeds_net"] == 50.0
    assert title["proceeds_12m_net"] == 50.0


def test_another_users_proceeds_never_count(client, auth, user, other_user, portfolio_module, two_assets):
    other_headers = other_user["headers"]
    other_petr = trade(client, other_headers, "PETR4", 100, 10.0, days(-800))
    provento(client, other_headers, other_petr, days(-15), per_unit=9.0)

    mine = by_ticker(summary(client, auth))["PETR4"]
    assert mine["net_amount"] == 142.5
    assert mine["net_12m"] == 142.5
    assert position(portfolio_module, user, "PETR4")["proceeds_net"] == 142.5

    theirs = summary(client, other_headers)
    assert [item["ticker"] for item in theirs["by_asset"]] == ["PETR4"]
    assert theirs["by_asset"][0]["net_amount"] == 900.0
    assert position(portfolio_module, other_user, "PETR4")["proceeds_net"] == 900.0
