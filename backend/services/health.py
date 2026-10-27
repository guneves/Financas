"""Healthcheck das integracoes: yfinance, brapi, BCB, o Tesouro e a Pluggy.

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
import tesouro_client
from applog import get_logger
from config import PRICE_FETCH_TIMEOUT_SECONDS
from integrations import provider_snapshot
from services import fixed_income, open_finance, prices

logger = get_logger(__name__)

HEALTH_CACHE_SECONDS = 600
# Ticker de referencia: liquido, negociado todo dia, nos dois provedores.
PROBE_TICKER = "PETR4"
# Cotacao mais velha que isso (dias corridos) e sinal de dado parado.
STALE_QUOTE_DAYS = 5

_executor = ThreadPoolExecutor(max_workers=3)
_cache_lock = threading.Lock()
_cache = {"at": 0.0, "result": None}


def _timed(fn, timeout=PRICE_FETCH_TIMEOUT_SECONDS):
    """(resultado, erro, ms) de fn(), com o limite de tempo das buscas reais."""
    started = time.monotonic()
    future = _executor.submit(fn)
    try:
        value = future.result(timeout=timeout)
        error = None
    except FutureTimeoutError:
        value, error = None, f"Sem resposta em {timeout:g} s"
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
    # O limite das cotacoes (6 s) e curto para o SGS, que leva varios segundos
    # num dia comum: o teste esperava menos que a busca real e dava "erro".
    value, error, elapsed = _timed(
        lambda: fixed_income.fetch_bcb_series(fixed_income.BCB_SERIES_CDI, start),
        timeout=fixed_income.BCB_TIMEOUT_SECONDS,
    )
    if error:
        return {"status": "error", "latency_ms": elapsed, "detail": error}
    if not value:
        return {"status": "error", "latency_ms": elapsed, "detail": "CDI sem valores nos últimos 15 dias."}
    last_date, _rate = value[-1]
    detail = f"CDI até {last_date.strftime('%d/%m/%Y')}"
    if (datetime.now() - last_date).days > STALE_QUOTE_DAYS:
        return {"status": "stale", "latency_ms": elapsed, "detail": detail + " (atrasado)"}
    return {"status": "ok", "latency_ms": elapsed, "detail": detail}


def check_tesouro():
    """Sem teste ativo: o arquivo tem dezenas de MB. Le o cache (e, sem ele,
    pede o download em segundo plano) e o ultimo resultado das buscas."""
    if not tesouro_client.TESOURO_PRICES_URL:
        return {"status": "not_configured", "detail": "TESOURO_PRICES_URL vazio; o Tesouro Direto fica na curva."}
    loaded = tesouro_client.get_prices()
    last = provider_snapshot("tesouro")
    if loaded is None:
        if last.get("last_error"):
            return {"status": "error", "detail": last["last_error"]}
        return {"status": "stale", "detail": "Preços do Tesouro ainda não baixados; o Tesouro Direto fica na curva."}
    detail = f"Preços até {loaded.latest_date.strftime('%d/%m/%Y')}" if loaded.latest_date else "Preços sem data"
    if loaded.latest_date is None or (datetime.now().date() - loaded.latest_date).days > STALE_QUOTE_DAYS:
        return {"status": "stale", "detail": detail + " (atrasado)"}
    return {"status": "ok", "detail": detail}


def check_pluggy():
    """Sem teste ativo: o POST /auth da Pluggy tem limite proprio. Le o ultimo
    resultado das chamadas de verdade (conectar, Atualizar, a thread)."""
    if not open_finance.is_configured():
        return {"status": "not_configured", "detail": "PLUGGY_CLIENT_ID/SECRET vazios; o Open Finance fica desligado."}
    last = provider_snapshot("pluggy")
    if last.get("consecutive_failures"):
        return {"status": "error", "detail": last.get("last_error") or "A última chamada falhou."}
    if not last.get("last_success"):
        return {"status": "ok", "detail": "Configurada; nenhuma chamada desde que o servidor subiu."}
    return {"status": "ok", "detail": "Última chamada respondeu."}


CHECKS = {
    "yfinance": ("Yahoo Finance (yfinance)", "Cotações de ações e FIIs", check_yfinance),
    "brapi": ("brapi", "Cotações da B3 (primário quando há token)", check_brapi),
    "bcb": ("Banco Central (SGS)", "CDI e IPCA da renda fixa", check_bcb),
    "tesouro": ("Tesouro Transparente", "Preço de mercado do Tesouro Direto", check_tesouro),
    "pluggy": ("Pluggy (Open Finance)", "Movimentos das contas e cartões para o Aprovar", check_pluggy),
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
