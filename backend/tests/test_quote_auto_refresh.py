"""Cotacoes da renda variavel atualizadas sozinhas de hora em hora (services/quote_refresh.py).

A thread chama, para cada usuario, o mesmo `refresh_market_prices(force=True)`
do botao "Atualizar cotacoes". Os testes rodam uma rodada direto
(`refresh_all_users()`); a thread fica desligada (QUOTE_AUTO_REFRESH_SECONDS=0
em conftest.py).
"""

import importlib


def buy(client, auth, ticker, quantity, price, *, asset_class="STOCKS"):
    response = client.post("/api/investments", headers=auth, json={
        "asset_class": asset_class,
        "ticker_or_name": ticker,
        "quantity": quantity,
        "average_price": price,
        "current_price": price,
        "metadata": {"purchase_date": "2025-01-10"},
    })
    assert response.status_code in (200, 201), response.get_data(as_text=True)


def fake_market(prices):
    calls = []

    def fetch(tickers, *, force=False, foreign=(), **kwargs):
        calls.append({"tickers": sorted(tickers), "force": force, "timeout": kwargs.get("timeout")})
        found = {ticker: prices[ticker] for ticker in tickers if ticker in prices}
        return {
            "prices": found,
            "source_by_ticker": {ticker: "market" for ticker in found},
            "failed_tickers": sorted(set(tickers) - set(found)),
            "errors": {},
        }

    return fetch, calls


def latest_market_price(db_module, user_id, ticker):
    with db_module.get_db() as conn:
        row = conn.execute(
            """
            SELECT q.price FROM price_quotes q JOIN assets a ON a.id = q.asset_id
            WHERE q.user_id = ? AND a.ticker = ? AND q.source = 'market'
            ORDER BY q.quoted_at DESC, q.created_at DESC LIMIT 1
            """,
            (user_id, ticker),
        ).fetchone()
    return row["price"] if row else None


def test_a_round_refreshes_every_user_with_force(client, user, other_user, db_module, portfolio_module, monkeypatch):
    quote_refresh = importlib.import_module("services.quote_refresh")
    buy(client, user["headers"], "PETR4", 10, 30.0)
    buy(client, other_user["headers"], "HGLG11", 5, 160.0, asset_class="REIT")
    fetch, calls = fake_market({"PETR4": 38.42, "HGLG11": 171.15})
    monkeypatch.setattr(portfolio_module, "get_market_prices_with_status", fetch)

    results = quote_refresh.refresh_all_users()

    assert results[user["id"]] == 1
    assert results[other_user["id"]] == 1
    assert all(call["force"] for call in calls)
    # A rodada de hora em hora espera o provedor mais que a leitura da carteira (6 s).
    assert all(call["timeout"] == quote_refresh.PRICE_REFRESH_TIMEOUT_SECONDS for call in calls)
    assert latest_market_price(db_module, user["id"], "PETR4") == 38.42
    assert latest_market_price(db_module, other_user["id"], "HGLG11") == 171.15
    # Cada usuario so pede os proprios ativos.
    assert ["PETR4"] in [call["tickers"] for call in calls]
    assert ["HGLG11"] in [call["tickers"] for call in calls]


def test_fixed_income_is_not_quoted(client, user, portfolio_module, monkeypatch):
    quote_refresh = importlib.import_module("services.quote_refresh")
    buy(client, user["headers"], "CDB Banco X", 1, 1000.0, asset_class="FIXED_INCOME")
    fetch, calls = fake_market({})
    monkeypatch.setattr(portfolio_module, "get_market_prices_with_status", fetch)

    results = quote_refresh.refresh_all_users()

    assert results[user["id"]] == 0
    # O banco dos testes e um so: os usuarios de outros testes tambem passam pela rodada.
    assert not any("CDB BANCO X" in " ".join(call["tickers"]).upper() for call in calls)


def test_one_user_failing_does_not_stop_the_others(client, user, other_user, monkeypatch):
    quote_refresh = importlib.import_module("services.quote_refresh")
    seen = []

    def refresh(current_user_id, *, force=False, **kwargs):
        seen.append(current_user_id)
        if current_user_id == user["id"]:
            raise RuntimeError("provedor fora do ar")
        return {"updated_count": 0, "requested_tickers": 0, "failed_tickers": []}

    monkeypatch.setattr(quote_refresh, "refresh_market_prices", refresh)
    results = quote_refresh.refresh_all_users()

    assert user["id"] in seen and other_user["id"] in seen
    assert user["id"] not in results
    assert results[other_user["id"]] == 0


def test_the_thread_is_off_with_interval_zero(app_module):
    quote_refresh = importlib.import_module("services.quote_refresh")
    assert quote_refresh.start_auto_refresh(interval_seconds=0) is False
    assert quote_refresh._auto_refresh_started is False


def test_a_quote_that_arrives_after_the_timeout_is_still_recorded(client, user, db_module, portfolio_module, prices_module, monkeypatch):
    """Fora do pregao o yfinance faz duas consultas e passa do tempo do pedido: a resposta
    diz `late` e a cotacao que chega depois e gravada, nao so posta no cache."""
    import threading

    buy(client, user["headers"], "VALE3", 10, 60.0)
    release = threading.Event()

    def slow_download(tickers, foreign=()):
        release.wait(5)
        return {ticker: 61.37 for ticker in tickers}

    monkeypatch.setattr(prices_module, "download_market_prices", slow_download)
    monkeypatch.setattr(prices_module, "yf", object())
    monkeypatch.setattr(prices_module, "_price_cache", {})
    outcome = portfolio_module.refresh_market_prices(user["id"], force=True, asset_id=None, timeout=0.05)

    assert outcome["late"] is True
    assert outcome["updated_count"] == 0
    failed = [asset for asset in outcome["failed_assets"] if asset["ticker"] == "VALE3"]
    assert failed and "gravada quando chegar" in failed[0]["error"]

    release.set()
    for _ in range(50):
        if latest_market_price(db_module, user["id"], "VALE3") == 61.37:
            break
        threading.Event().wait(0.05)
    assert latest_market_price(db_module, user["id"], "VALE3") == 61.37
