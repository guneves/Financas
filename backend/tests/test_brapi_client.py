"""Cliente da brapi: lote, cache, deduplicacao e erros tipados.

O que se testa aqui e o gasto de credito — quantas vezes o cliente vai a rede
e com qual URL. Nenhum teste faz requisicao real: `urlopen` e substituido.
"""

import io
import json
import threading
import time
import urllib.error
from datetime import datetime

import pytest

import brapi_client


@pytest.fixture(autouse=True)
def clean_client(monkeypatch):
    monkeypatch.setenv("BRAPI_TOKEN", "token-de-teste")
    brapi_client.clear_cache()
    brapi_client._inflight.clear()
    yield
    brapi_client.clear_cache()
    brapi_client._inflight.clear()


class _FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False


def quote_payload(symbol, price):
    return {
        "symbol": symbol,
        "shortName": f"{symbol} ON",
        "longName": f"Empresa {symbol}",
        "currency": "BRL",
        "regularMarketPrice": price,
        "regularMarketChangePercent": 1.5,
        "regularMarketPreviousClose": price - 1,
        "regularMarketTime": "2026-09-22T17:00:00.000Z",
    }


def fake_urlopen(calls, results_by_symbol, *, delay=0.0):
    def _urlopen(request, timeout=None):
        calls.append({
            "url": request.full_url,
            "headers": dict(request.headers),
            "timeout": timeout,
        })
        if delay:
            time.sleep(delay)
        symbols = request.full_url.split("symbols=")[1].split("&")[0].split("%2C")
        results = [
            results_by_symbol[symbol]
            for symbol in symbols
            if symbol in results_by_symbol
        ]
        return _FakeResponse(json.dumps({"results": results}).encode("utf-8"))

    return _urlopen


def install(monkeypatch, calls, results_by_symbol, **kwargs):
    monkeypatch.setattr(
        brapi_client.urllib.request,
        "urlopen",
        fake_urlopen(calls, results_by_symbol, **kwargs),
    )


# --- normalizacao -----------------------------------------------------------

def test_normalize_symbols_accepts_string_and_list():
    assert brapi_client.normalize_symbols("petr4, vale3 ") == ["PETR4", "VALE3"]
    assert brapi_client.normalize_symbols(["PETR4", "petr4.sa", ""]) == ["PETR4"]


# --- autenticacao -----------------------------------------------------------

def test_missing_token_raises_not_configured(monkeypatch):
    monkeypatch.delenv("BRAPI_TOKEN", raising=False)
    assert brapi_client.is_configured() is False
    with pytest.raises(brapi_client.BrapiNotConfiguredError):
        brapi_client.get_stock_quotes(["PETR4"])


def test_token_goes_in_the_authorization_header(monkeypatch):
    calls = []
    install(monkeypatch, calls, {"PETR4": quote_payload("PETR4", 38.42)})

    brapi_client.get_stock_quotes(["PETR4"])

    headers = {key.lower(): value for key, value in calls[0]["headers"].items()}
    assert headers["authorization"] == "Bearer token-de-teste"
    assert calls[0]["url"].startswith("https://brapi.dev/api/v2/stocks/quote?")


# --- lote e cache -----------------------------------------------------------

def test_many_tickers_cost_a_single_request(monkeypatch):
    calls = []
    install(monkeypatch, calls, {
        "PETR4": quote_payload("PETR4", 38.42),
        "VALE3": quote_payload("VALE3", 61.10),
        "BBAS3": quote_payload("BBAS3", 27.05),
    })

    quotes = brapi_client.get_stock_quotes(["PETR4", "VALE3", "BBAS3"])

    assert len(calls) == 1
    assert "symbols=PETR4%2CVALE3%2CBBAS3" in calls[0]["url"]
    assert sorted(quotes) == ["BBAS3", "PETR4", "VALE3"]
    assert quotes["VALE3"].regular_market_price == 61.10


def test_second_call_inside_the_ttl_uses_the_cache(monkeypatch):
    calls = []
    install(monkeypatch, calls, {"PETR4": quote_payload("PETR4", 38.42)})

    brapi_client.get_stock_quotes(["PETR4"])
    again = brapi_client.get_stock_quotes(["PETR4"])

    assert len(calls) == 1
    assert again["PETR4"].regular_market_price == 38.42


def test_only_the_missing_ticker_is_fetched(monkeypatch):
    calls = []
    install(monkeypatch, calls, {
        "PETR4": quote_payload("PETR4", 38.42),
        "VALE3": quote_payload("VALE3", 61.10),
    })

    brapi_client.get_stock_quotes(["PETR4"])
    brapi_client.get_stock_quotes(["PETR4", "VALE3"])

    assert len(calls) == 2
    assert "symbols=VALE3" in calls[1]["url"]


def test_force_ignores_the_cache(monkeypatch):
    calls = []
    install(monkeypatch, calls, {"PETR4": quote_payload("PETR4", 38.42)})

    brapi_client.get_stock_quotes(["PETR4"])
    brapi_client.get_stock_quotes(["PETR4"], force=True)

    assert len(calls) == 2


def test_batches_are_capped(monkeypatch):
    symbols = [f"TST{index}" for index in range(brapi_client.MAX_SYMBOLS_PER_REQUEST + 3)]
    calls = []
    install(monkeypatch, calls, {symbol: quote_payload(symbol, 10.0) for symbol in symbols})

    quotes = brapi_client.get_stock_quotes(symbols)

    assert len(calls) == 2
    assert len(quotes) == len(symbols)


# --- deduplicacao -----------------------------------------------------------

def test_simultaneous_callers_share_one_request(monkeypatch):
    calls = []
    install(
        monkeypatch,
        calls,
        {"PETR4": quote_payload("PETR4", 38.42)},
        delay=0.2,
    )

    results = {}
    barrier = threading.Barrier(4)

    def worker(index):
        barrier.wait()
        results[index] = brapi_client.get_stock_quotes(["PETR4"])

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(calls) == 1
    assert all(result["PETR4"].regular_market_price == 38.42 for result in results.values())


# --- results[0] -------------------------------------------------------------

def test_get_stock_quote_returns_the_first_requested_symbol(monkeypatch):
    calls = []
    install(monkeypatch, calls, {
        "PETR4": quote_payload("PETR4", 38.42),
        "VALE3": quote_payload("VALE3", 61.10),
    })

    quote = brapi_client.get_stock_quote("PETR4,VALE3")

    assert quote.symbol == "PETR4"
    assert quote.short_name == "PETR4 ON"
    assert len(calls) == 1


def test_unknown_ticker_is_absent_not_an_error(monkeypatch):
    calls = []
    install(monkeypatch, calls, {"PETR4": quote_payload("PETR4", 38.42)})

    quotes = brapi_client.get_stock_quotes(["PETR4", "XXXX9"])

    assert "XXXX9" not in quotes
    assert brapi_client.get_stock_quote("XXXX9") is None


# --- precos -----------------------------------------------------------------

def test_price_is_rounded_half_up(monkeypatch):
    calls = []
    install(monkeypatch, calls, {"PETR4": quote_payload("PETR4", 38.425)})

    prices = brapi_client.get_market_prices(["PETR4"])

    # round() do Python devolveria 38.42 (banker's rounding).
    assert prices["PETR4"] == 38.43


def test_nested_data_payload_is_read(monkeypatch):
    # Formato que a brapi passou a devolver: a cotacao dentro de `data`.
    inner = quote_payload("PETR4", 49.6)
    inner.pop("symbol")
    calls = []
    install(monkeypatch, calls, {"PETR4": {"symbol": "PETR4", "requestedSymbol": "PETR4", "changed": False, "data": inner}})

    quote = brapi_client.get_stock_quote("PETR4")
    assert quote.regular_market_price == 49.6
    assert quote.short_name == "PETR4 ON"
    assert brapi_client.get_market_prices(["PETR4"]) == {"PETR4": 49.6}


def test_quote_without_price_stays_out_of_get_market_prices(monkeypatch):
    payload = quote_payload("PETR4", 38.42)
    payload["regularMarketPrice"] = None
    calls = []
    install(monkeypatch, calls, {"PETR4": payload})

    assert brapi_client.get_market_prices(["PETR4"]) == {}


# --- erros tipados ----------------------------------------------------------

def test_non_2xx_raises_a_typed_http_error(monkeypatch):
    def _urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url,
            402,
            "Payment Required",
            {},
            io.BytesIO(json.dumps({"message": "creditos esgotados"}).encode("utf-8")),
        )

    monkeypatch.setattr(brapi_client.urllib.request, "urlopen", _urlopen)

    with pytest.raises(brapi_client.BrapiHTTPError) as excinfo:
        brapi_client.get_stock_quotes(["PETR4"])

    assert excinfo.value.status == 402
    assert "creditos esgotados" in excinfo.value.detail
    assert isinstance(excinfo.value, brapi_client.BrapiError)


def test_network_failure_raises_unavailable(monkeypatch):
    def _urlopen(request, timeout=None):
        raise urllib.error.URLError("conexao recusada")

    monkeypatch.setattr(brapi_client.urllib.request, "urlopen", _urlopen)

    with pytest.raises(brapi_client.BrapiUnavailableError):
        brapi_client.get_stock_quotes(["PETR4"])


def test_body_without_results_raises_response_error(monkeypatch):
    def _urlopen(request, timeout=None):
        return _FakeResponse(json.dumps({"error": True, "message": "token invalido"}).encode("utf-8"))

    monkeypatch.setattr(brapi_client.urllib.request, "urlopen", _urlopen)

    with pytest.raises(brapi_client.BrapiResponseError) as excinfo:
        brapi_client.get_stock_quotes(["PETR4"])

    assert "token invalido" in str(excinfo.value)


def test_a_timeout_is_retried_once_within_the_budget(monkeypatch):
    # A brapi as vezes fica muda na primeira requisicao depois de parada.
    calls = []
    answer = fake_urlopen([], {"PETR4": quote_payload("PETR4", 38.42)})

    def _urlopen(request, timeout=None):
        calls.append(timeout)
        if len(calls) == 1:
            raise TimeoutError("The read operation timed out")
        return answer(request, timeout)

    monkeypatch.setattr(brapi_client.urllib.request, "urlopen", _urlopen)

    assert brapi_client.get_market_prices(["PETR4"], force=True, timeout=6.0) == {"PETR4": 38.42}
    assert calls == [brapi_client.FIRST_ATTEMPT_TIMEOUT_SECONDS, 6.0 - brapi_client.FIRST_ATTEMPT_TIMEOUT_SECONDS]


def test_a_connect_timeout_wrapped_in_urlerror_is_retried_too(monkeypatch):
    calls = []

    def _urlopen(request, timeout=None):
        calls.append(timeout)
        raise urllib.error.URLError(TimeoutError("timed out"))

    monkeypatch.setattr(brapi_client.urllib.request, "urlopen", _urlopen)

    with pytest.raises(brapi_client.BrapiUnavailableError, match="Tempo limite"):
        brapi_client.get_stock_quotes(["PETR4"])
    assert len(calls) == 2


def test_other_failures_are_not_retried(monkeypatch):
    calls = []

    def _urlopen(request, timeout=None):
        calls.append(timeout)
        raise urllib.error.HTTPError(request.full_url, 402, "Payment Required", {}, None)

    monkeypatch.setattr(brapi_client.urllib.request, "urlopen", _urlopen)
    with pytest.raises(brapi_client.BrapiHTTPError):
        brapi_client.get_stock_quotes(["PETR4"])
    assert len(calls) == 1

    calls.clear()

    def _offline(request, timeout=None):
        calls.append(timeout)
        raise urllib.error.URLError("sem rede")

    monkeypatch.setattr(brapi_client.urllib.request, "urlopen", _offline)
    with pytest.raises(brapi_client.BrapiUnavailableError, match="Falha de rede"):
        brapi_client.get_stock_quotes(["PETR4"])
    assert len(calls) == 1


def test_a_failed_fetch_does_not_poison_the_inflight_map(monkeypatch):
    def _failing(request, timeout=None):
        raise urllib.error.URLError("sem rede")

    monkeypatch.setattr(brapi_client.urllib.request, "urlopen", _failing)
    with pytest.raises(brapi_client.BrapiUnavailableError):
        brapi_client.get_stock_quotes(["PETR4"])

    calls = []
    install(monkeypatch, calls, {"PETR4": quote_payload("PETR4", 38.42)})
    assert brapi_client.get_stock_quotes(["PETR4"])["PETR4"].regular_market_price == 38.42


# --- pregao da B3 -----------------------------------------------------------

def test_market_hours():
    # 2026-09-22 e uma terca-feira.
    assert brapi_client.is_market_open(datetime(2026, 9, 22, 11, 0, tzinfo=brapi_client.BRT))
    assert not brapi_client.is_market_open(datetime(2026, 9, 22, 9, 59, tzinfo=brapi_client.BRT))
    assert not brapi_client.is_market_open(datetime(2026, 9, 22, 18, 0, tzinfo=brapi_client.BRT))
    # Sabado.
    assert not brapi_client.is_market_open(datetime(2026, 9, 26, 11, 0, tzinfo=brapi_client.BRT))


def test_next_market_open_skips_the_weekend():
    saturday = datetime(2026, 9, 26, 11, 0, tzinfo=brapi_client.BRT)
    assert brapi_client.next_market_open(saturday) == datetime(
        2026, 9, 28, 10, 0, tzinfo=brapi_client.BRT
    )

    after_close = datetime(2026, 9, 22, 19, 30, tzinfo=brapi_client.BRT)
    assert brapi_client.next_market_open(after_close) == datetime(
        2026, 9, 23, 10, 0, tzinfo=brapi_client.BRT
    )


def test_cache_ttl_while_open_is_the_configured_window():
    open_moment = datetime(2026, 9, 22, 11, 0, tzinfo=brapi_client.BRT)
    expiry = brapi_client.cache_expiry(open_moment)
    assert expiry - open_moment.timestamp() == pytest.approx(brapi_client.CACHE_TTL_SECONDS)
    assert brapi_client.CACHE_TTL_SECONDS >= 300


def test_cache_with_the_market_closed_holds_until_the_next_open(monkeypatch):
    saturday = datetime(2026, 9, 26, 11, 0, tzinfo=brapi_client.BRT)
    calls = []
    install(monkeypatch, calls, {"PETR4": quote_payload("PETR4", 38.42)})

    brapi_client.get_stock_quotes(["PETR4"], now=saturday)
    # Domingo a noite, muito alem do TTL de 5 minutos: ainda e cache.
    sunday_night = datetime(2026, 9, 27, 23, 0, tzinfo=brapi_client.BRT)
    brapi_client.get_stock_quotes(["PETR4"], now=sunday_night)
    assert len(calls) == 1

    # Depois da abertura de segunda, a entrada expirou.
    monday = datetime(2026, 9, 28, 10, 1, tzinfo=brapi_client.BRT)
    brapi_client.get_stock_quotes(["PETR4"], now=monday)
    assert len(calls) == 2
