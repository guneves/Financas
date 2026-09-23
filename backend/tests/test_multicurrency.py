"""Multimoeda (Fase 6, 018): ativos e contas em moeda estrangeira.

O que estes testes fixam:

- a operacao guarda o cambio da data (PTAX do dia util anterior, ou o que o
  usuario informou) e o caixa ligado sai em reais;
- custo em reais pelo cambio da compra, valor atual pelo cambio de hoje, e o
  resultado da venda em reais (venda pelo cambio dela menos o custo da compra);
- acao do exterior nao passa pelo catalogo da B3; renda fixa nao aceita moeda;
- conta em dolar mostra o saldo em reais, e transferencia entre moedas e
  recusada;
- sem cambio (nem guardado, nem no BCB, nem informado) a operacao e recusada;
- nada de outro usuario: o cambio guardado e por usuario.
"""

import importlib
from datetime import date, datetime, timedelta

import pytest

TODAY = date.today()


def fake_ptax(series, start, end):
    """Dias uteis de [start, end]: 5,00 antes de junho/2026, 5,50 depois."""
    rows = []
    day = start.date() if isinstance(start, datetime) else start
    last = end.date() if isinstance(end, datetime) else end
    while day <= last:
        if day.weekday() < 5:
            rate = 5.0 if day < date(2026, 6, 1) else 5.5
            rows.append({"data": day.strftime("%d/%m/%Y"), "valor": f"{rate:.4f}"})
        day += timedelta(days=1)
    return rows


@pytest.fixture(autouse=True)
def ptax(app_module, monkeypatch):
    fx = importlib.import_module("services.fx")
    fx.reset_fetch_throttle()
    monkeypatch.setattr(fx, "fetch_bcb_window", fake_ptax)
    # Nada de rede para cotacao nem historico.
    prices = importlib.import_module("services.prices")
    monkeypatch.setattr(prices, "download_close_prices", lambda symbols, **kwargs: {})
    return fx


def buy_usd(client, auth, *, quantity=10, price=100.0, date_value="2026-03-02", current=120.0, **meta):
    return client.post(
        "/api/investments",
        headers=auth,
        json={
            "asset_class": "STOCKS",
            "ticker_or_name": "AAPL",
            "currency": "USD",
            "quantity": quantity,
            "average_price": price,
            "current_price": current,
            "metadata": {"purchase_date": date_value, **meta},
        },
    )


def sell_usd(client, auth, *, quantity=10, price=130.0, date_value="2026-07-01"):
    return client.post(
        "/api/investments",
        headers=auth,
        json={
            "asset_class": "STOCKS",
            "ticker_or_name": "AAPL",
            "currency": "USD",
            "quantity": -quantity,
            "average_price": price,
            "current_price": price,
            "metadata": {"sale_date": date_value, "sale_price": price},
        },
    )


def cash(client, auth):
    return sorted(
        (item["type"], item["amount"]) for item in client.get("/api/transactions", headers=auth).get_json()
        if item.get("source_type") == "INVESTMENT_TRANSACTION"
    )


def portfolio_asset(client, auth, ticker="AAPL"):
    body = client.get("/api/investments/portfolio?refresh_prices=false", headers=auth).get_json()
    return next(asset for asset in body["assets"] if asset["ticker"] == ticker)


def test_a_usd_buy_stores_the_ptax_and_debits_reais(client, auth):
    response = buy_usd(client, auth)
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    movement = response.get_json()[0]
    assert movement["metadata"]["fx_rate"] == 5.0
    assert movement["metadata"]["fx_source"] == "ptax"
    assert movement["average_price"] == 100.0  # na moeda do ativo
    assert cash(client, auth) == [("EXPENSE", 5000.0)]


def test_an_informed_rate_wins_over_the_ptax(client, auth):
    buy_usd(client, auth, fx_rate=5.2)
    assert cash(client, auth) == [("EXPENSE", 5200.0)]


def test_portfolio_values_cost_at_purchase_rate_and_value_at_todays(client, auth):
    buy_usd(client, auth)
    asset = portfolio_asset(client, auth)
    today_rate = 5.0 if TODAY < date(2026, 6, 1) else 5.5
    assert asset["average_price"] == pytest.approx(500.0)
    assert asset["current_value"] == pytest.approx(10 * 120 * today_rate)
    assert asset["currency"] == "USD"
    assert asset["native_current_price"] == 120.0


def test_the_sale_result_is_in_reais(client, auth):
    buy_usd(client, auth)
    response = sell_usd(client, auth)
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    sale = next(item for item in client.get("/api/investments", headers=auth).get_json() if item["quantity"] < 0)
    # 10 x 130 x 5,50 - 10 x 100 x 5,00
    assert sale["realized_profit"] == pytest.approx(2150.0)
    assert ("INCOME", 7150.0) in cash(client, auth)


def test_foreign_stock_skips_the_b3_catalog(client, auth):
    # Em reais, um ticker fora do catalogo da B3 e recusado; em dolar, nao.
    response = client.post(
        "/api/investments", headers=auth,
        json={"asset_class": "STOCKS", "ticker_or_name": "AAPL", "quantity": 1, "average_price": 10,
              "metadata": {"purchase_date": "2026-03-02"}},
    )
    assert response.status_code == 400
    assert buy_usd(client, auth).status_code in (200, 201)


@pytest.mark.parametrize("payload, message", [
    ({"asset_class": "FIXED_INCOME", "currency": "USD"}, "estrangeira"),
    ({"asset_class": "STOCKS", "currency": "JPY"}, "Moeda nao suportada"),
])
def test_invalid_currency_combinations_are_refused(client, auth, payload, message):
    body = {"ticker_or_name": "XPTO", "quantity": 1, "average_price": 10, "metadata": {"purchase_date": "2026-03-02"}}
    body.update(payload)
    response = client.post("/api/investments", headers=auth, json=body)
    assert response.status_code == 400
    assert message in response.get_json()["error"]


def test_the_same_ticker_cannot_change_currency(client, auth):
    buy_usd(client, auth)
    response = client.post(
        "/api/investments", headers=auth,
        json={"asset_class": "STOCKS", "ticker_or_name": "AAPL", "currency": "EUR", "quantity": 1,
              "average_price": 10, "metadata": {"purchase_date": "2026-03-02"}},
    )
    assert response.status_code == 400
    assert "USD" in response.get_json()["error"]


def test_without_any_rate_the_buy_asks_for_one(client, auth, ptax, monkeypatch):
    def offline(*args, **kwargs):
        raise RuntimeError("sem rede")

    monkeypatch.setattr(ptax, "fetch_bcb_window", offline)
    response = buy_usd(client, auth)
    assert response.status_code == 400
    assert "Informe o cambio" in response.get_json()["error"]
    assert buy_usd(client, auth, fx_rate=5.1).status_code in (200, 201)


def test_weekend_uses_the_previous_business_day(app_module, user, ptax):
    db = importlib.import_module("db")
    with db.get_db() as conn:
        # 2026-05-30 e sabado; a PTAX valida e a de sexta, 29.
        assert ptax.rate_on(conn, user["id"], "USD", "2026-05-30") == 5.0
        assert ptax.rate_on(conn, user["id"], "BRL", "2026-05-30") == 1.0


def test_usd_account_shows_its_balance_in_reais(client, auth):
    account = client.post(
        "/api/accounts", headers=auth,
        json={"name": "Conta EUA", "type": "CHECKING", "currency": "USD", "initial_balance": 100},
    ).get_json()
    listed = next(item for item in client.get("/api/accounts", headers=auth).get_json() if item["id"] == account["id"])
    today_rate = 5.0 if TODAY < date(2026, 6, 1) else 5.5
    assert listed["balance"] == 100
    assert listed["balance_brl"] == pytest.approx(100 * today_rate)


def test_transfer_between_currencies_is_refused(client, auth):
    usd = client.post(
        "/api/accounts", headers=auth, json={"name": "Conta EUA", "type": "CHECKING", "currency": "USD"},
    ).get_json()
    brl = client.post("/api/accounts", headers=auth, json={"name": "Conta BR", "type": "CHECKING"}).get_json()
    response = client.post(
        "/api/transfers", headers=auth,
        json={"account_id": brl["id"], "transfer_account_id": usd["id"], "amount": 100, "date": "2026-03-02"},
    )
    assert response.status_code == 400
    assert "moedas diferentes" in response.get_json()["error"]


def test_stored_rates_are_per_user(client, user, other_user):
    buy_usd(client, user["headers"])
    db = importlib.import_module("db")
    with db.get_db() as conn:
        mine = conn.execute("SELECT COUNT(*) FROM fx_rates WHERE user_id = ?", (user["id"],)).fetchone()[0]
        theirs = conn.execute("SELECT COUNT(*) FROM fx_rates WHERE user_id = ?", (other_user["id"],)).fetchone()[0]
    assert mine > 0
    assert theirs == 0
