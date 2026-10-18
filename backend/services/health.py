"""Healthcheck das integracoes: yfinance, brapi e BCB.

`check_integrations()` faz um teste ativo em cada provedor (um ticker, uma
serie curta), com o mesmo limite de tempo das buscas reais, e junta o ultimo
resultado das buscas de verdade (integrations.py). O resultado fica em cache
por HEALTH_CACHE_SECONDS: abrir Ajustes varias vezes nao martela o Yahoo.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta, timezone

import brapi_client
from applog import get_logger
from config import PRICE_FETCH_TIMEOUT_SECONDS
from integrations import provider_snapshot
from services import fixed_income, prices

logger = get_logger(__name__)

HEALTH_CACHE_SECONDS = 600
# Ticker de referencia: liquido, negociado todo dia, nos dois provedores.
PROBE_TICKER = "PETR4"
# Cotacao mais velha que isso (dias corridos) e sinal de dado parado.
STALE_QUOTE_DAYS = 5

_executor = ThreadPoolExecutor(max_workers=3)
_cache_lock = threading.Lock()
_cache = {"at": 0.0, "result": None}


def _timed(fn):
    """(resultado, erro, ms) de fn(), com o limite de tempo das buscas reais."""
    started = time.monotonic()
    future = _executor.submit(fn)
    try:
        value = future.result(timeout=PRICE_FETCH_TIMEOUT_SECONDS)
        error = None
    except FutureTimeoutError:
        value, error = None, f"Sem resposta em {PRICE_FETCH_TIMEOUT_SECONDS:g} s"
    except Exception as exc:  # o provedor pode falhar de qualquer jeito
        value, error = None, str(exc) or exc.__class__.__name__
    return value, error, round((time.monotonic() - started) * 1000)


def check_yfinance():
    if prices.yf is None:
        return {"status": "unavailable", "detail": "Pacote yfinance não instalado."}
    symbol = prices.yahoo_symbol(PROBE_TICKER)
    value, error, elapsed = _timed(
        lambda: prices.download_close_prices([symbol], period="5d", interval="1d")
    )
    price = (value or {}).get(symbol)
    if error or price is None:
        return {"status": "error", "latency_ms": elapsed, "detail": error or f"Sem cotação de {PROBE_TICKER}."}
    return {"status": "ok", "latency_ms": elapsed, "detail": f"{PROBE_TICKER} a R$ {price:.2f}".replace(".", ",")}


def check_brapi():
    if not brapi_client.is_configured():
        return {"status": "not_configured", "detail": "BRAPI_TOKEN vazio em backend/.env; o yfinance cobre as cotações."}
    value, error, elapsed = _timed(lambda: brapi_client.get_market_prices([PROBE_TICKER], force=True))
    price = (value or {}).get(PROBE_TICKER)
    if error or price is None:
        return {"status": "error", "latency_ms": elapsed, "detail": error or f"Sem cotação de {PROBE_TICKER}."}
    return {"status": "ok", "latency_ms": elapsed, "detail": f"{PROBE_TICKER} a R$ {float(price):.2f}".replace(".", ",")}


def check_bcb():
    start = datetime.now() - timedelta(days=15)
    value, error, elapsed = _timed(lambda: fixed_income.fetch_bcb_series(fixed_income.BCB_SERIES_CDI, start))
    if error:
        return {"status": "error", "latency_ms": elapsed, "detail": error}
    if not value:
        return {"status": "error", "latency_ms": elapsed, "detail": "CDI sem valores nos últimos 15 dias."}
    last_date, _rate = value[-1]
    detail = f"CDI até {last_date.strftime('%d/%m/%Y')}"
    if (datetime.now() - last_date).days > STALE_QUOTE_DAYS:
        return {"status": "stale", "latency_ms": elapsed, "detail": detail + " (atrasado)"}
    return {"status": "ok", "latency_ms": elapsed, "detail": detail}


CHECKS = {
    "yfinance": ("Yahoo Finance (yfinance)", "Cotações de ações e FIIs", check_yfinance),
    "brapi": ("brapi", "Cotações da B3 (primário quando há token)", check_brapi),
    "bcb": ("Banco Central (SGS)", "CDI e IPCA da renda fixa", check_bcb),
}


def overall_status(items):
    statuses = [item["status"] for item in items]
    if all(status in ("ok", "not_configured") for status in statuses):
        return "ok"
    # Sem nenhum provedor de cotacao o app fica sem precos: isso e "down".
    quotes = [item["status"] for item in items if item["key"] in ("yfinance", "brapi")]
    if not any(status == "ok" for status in quotes):
        return "down"
    return "degraded"


def check_integrations(force=False):
    with _cache_lock:
        cached = _cache["result"]
        if cached and not force and time.monotonic() - _cache["at"] < HEALTH_CACHE_SECONDS:
            return {**cached, "cached": True}

    items = []
    for key, (label, purpose, check) in CHECKS.items():
        result = check()
        item = {"key": key, "label": label, "purpose": purpose, **result, **provider_snapshot(key)}
        if result["status"] == "error":
            logger.warning("Integracao com problema", extra={"provider": key, "detail": result.get("detail")})
        items.append(item)

    result = {
        "status": overall_status(items),
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "items": items,
    }
    with _cache_lock:
        _cache["at"] = time.monotonic()
        _cache["result"] = result
    return {**result, "cached": False}
