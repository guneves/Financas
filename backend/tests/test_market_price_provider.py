"""Precedencia entre os provedores de cotacao dentro do app.py.

`test_brapi_client.py` cobre o cliente isolado. O que se testa aqui e a
costura: a brapi vem primeiro, o yfinance so e consultado para o que sobrou, e
o metadata gravado diz quem realmente entregou o preco — um "provider" errado
no `price_quotes` estraga a auditoria da cotacao que alimenta o ganho nao
realizado.
"""

import pytest

import brapi_client


@pytest.fixture()
def brapi_on(app_module, monkeypatch):
    monkeypatch.setattr(app_module.brapi_client, "is_configured", lambda: True)
    # O caminho do yfinance so roda quando `yf` existe; o modulo real nunca e
    # chamado porque `download_close_prices` esta substituido nos testes.
    monkeypatch.setattr(app_module, "yf", object(), raising=False)
    return app_module


def track_yfinance(app_module, monkeypatch, prices_by_symbol):
    calls = []

    def _download(yf_symbols, *, period, interval):
        calls.append(list(yf_symbols))
        return {
            symbol: prices_by_symbol[symbol]
            for symbol in yf_symbols
            if symbol in prices_by_symbol
        }

    monkeypatch.setattr(app_module, "download_close_prices", _download)
    return calls


def test_brapi_serves_the_ticker_and_yfinance_is_not_consulted(brapi_on, monkeypatch):
    app_module = brapi_on
    monkeypatch.setattr(
        app_module.brapi_client, "get_market_prices", lambda tickers: {"PETR4": 38.42}
    )
    calls = track_yfinance(app_module, monkeypatch, {})

    prices = app_module.download_market_prices(["PETR4"])

    assert prices == {"PETR4": 38.42}
    assert calls == []


def test_mixed_batch_splits_between_the_two_providers(brapi_on, monkeypatch):
    app_module = brapi_on
    monkeypatch.setattr(
        app_module.brapi_client, "get_market_prices", lambda tickers: {"PETR4": 38.42}
    )
    calls = track_yfinance(app_module, monkeypatch, {"AAPL": 210.5})

    prices = app_module.download_market_prices(["PETR4", "AAPL"])

    assert prices == {"PETR4": 38.42, "AAPL": 210.5}
    # O ticker que a brapi resolveu nao chega ao yfinance.
    assert calls and all("PETR4" not in symbols for symbols in calls)


def test_brapi_failure_falls_back_to_yfinance(brapi_on, monkeypatch):
    app_module = brapi_on

    def _boom(tickers):
        raise brapi_client.BrapiHTTPError(402, "creditos esgotados", tickers)

    monkeypatch.setattr(app_module.brapi_client, "get_market_prices", _boom)
    calls = track_yfinance(app_module, monkeypatch, {"PETR4.SA": 38.40})

    prices = app_module.download_market_prices(["PETR4"])

    assert prices == {"PETR4": 38.40}
    assert calls


def test_brapi_price_is_rounded_half_up(brapi_on, monkeypatch):
    app_module = brapi_on
    monkeypatch.setattr(
        app_module.brapi_client, "get_market_prices", lambda tickers: {"PETR4": 38.425}
    )
    track_yfinance(app_module, monkeypatch, {})

    assert app_module.download_market_prices(["PETR4"]) == {"PETR4": 38.43}


def test_zero_or_negative_price_from_brapi_is_ignored(brapi_on, monkeypatch):
    app_module = brapi_on
    monkeypatch.setattr(
        app_module.brapi_client,
        "get_market_prices",
        lambda tickers: {"PETR4": 0, "VALE3": -1},
    )
    calls = track_yfinance(app_module, monkeypatch, {"PETR4.SA": 38.40})

    prices = app_module.download_market_prices(["PETR4", "VALE3"])

    assert prices == {"PETR4": 38.40}
    assert calls and "VALE3.SA" in calls[0]


def test_without_token_the_brapi_path_is_skipped(app_module, monkeypatch):
    monkeypatch.setattr(app_module.brapi_client, "is_configured", lambda: False)

    def _never(tickers):
        raise AssertionError("a brapi nao deveria ser consultada sem token")

    monkeypatch.setattr(app_module.brapi_client, "get_market_prices", _never)
    monkeypatch.setattr(app_module, "yf", object(), raising=False)
    track_yfinance(app_module, monkeypatch, {"PETR4.SA": 38.40})

    assert app_module.download_market_prices(["PETR4"]) == {"PETR4": 38.40}


# --- metadata gravado no price_quotes ---------------------------------------

def test_provider_label_follows_the_brapi_cache(app_module, monkeypatch):
    """Ticker servido pela brapi grava provider=brapi; o resto, yfinance."""
    quote = brapi_client.StockQuote(symbol="PETR4", regular_market_price=38.42)
    monkeypatch.setattr(
        app_module.brapi_client,
        "cached_quote",
        lambda ticker: quote if app_module.ticker_key(ticker) == "PETR4" else None,
    )

    assert app_module.market_price_provider("PETR4") == "brapi"
    assert app_module.market_price_provider("petr4") == "brapi"
    assert app_module.market_price_provider("VALE3") == "yfinance"
