"""A B3 inteira para a busca de ativos: o catalogo fixo mais a /quote/list da brapi.

O catalogo de `market_catalog` so tem Ibovespa, ETFs, FIIs e BDRs mais
negociados; papel fora dele (LEVE3, FESA4...) nao podia ser comprado. A
listagem da brapi cobre os ~2300 papeis e vale por um dia (o cache e o mesmo
do setor, em `brapi_client`).

Sem token, sem rede ou com a brapi fora do ar, a busca cai no catalogo fixo --
nunca falha por causa disso. Depois de uma falha, a listagem so e tentada de
novo apos `RETRY_AFTER_SECONDS`, para o autocomplete nao esperar o timeout a
cada tecla.
"""

import threading
import time

import brapi_client
from applog import get_logger
from integrations import record_provider_result
import market_catalog

log = get_logger(__name__)

LISTING_TTL_SECONDS = 86400
RETRY_AFTER_SECONDS = 600

_lock = threading.Lock()
_state = {"entries": {}, "expires_at": 0.0, "retry_at": 0.0}


def reset_cache():
    with _lock:
        _state["entries"] = {}
        _state["expires_at"] = 0.0
        _state["retry_at"] = 0.0


def live_listing():
    """{ticker: entrada do catalogo} da B3 inteira; {} quando a brapi nao responde."""
    now = time.time()
    with _lock:
        if _state["expires_at"] > now:
            return _state["entries"]
        if _state["retry_at"] > now:
            return _state["entries"]
    if not brapi_client.is_configured():
        return {}

    try:
        listing = brapi_client.get_listing()
    except brapi_client.BrapiError as exc:
        log.warning("listagem da B3 indisponivel", extra={"error": str(exc)})
        record_provider_result("brapi", False, str(exc))
        with _lock:
            _state["retry_at"] = now + RETRY_AFTER_SECONDS
            return _state["entries"]

    entries = {}
    for info in listing.values():
        # Mercado fracionario (LEVE3F) e o mesmo papel que LEVE3: uma posicao so.
        if info.symbol.endswith("F") and info.symbol[:-1] in listing:
            continue
        entry = market_catalog.entry_from_listing(info.symbol, info.name, info.type, info.sub_type)
        if entry is not None:
            entries[entry["ticker"]] = entry
    record_provider_result("brapi", True)
    with _lock:
        _state["entries"] = entries
        _state["expires_at"] = now + LISTING_TTL_SECONDS
        _state["retry_at"] = 0.0
    return entries


def lookup(ticker):
    """Como `market_catalog.lookup`, com a B3 inteira. So vai a rede se o fixo nao conhece."""
    entry = market_catalog.lookup(ticker)
    if entry is not None:
        return entry
    return market_catalog.lookup(ticker, extra=live_listing())


def tax_kind(ticker, asset_class):
    """O tipo do papel para o IR (`market_catalog.tax_kind`). So vai a rede para
    um papel da classe Acoes que o catalogo fixo nao conhece (um ETF fora dele)."""
    if asset_class == "STOCKS" and market_catalog.lookup(ticker) is None:
        return market_catalog.tax_kind(ticker, asset_class, extra=live_listing())
    return market_catalog.tax_kind(ticker, asset_class)


def search(query="", asset_class=None, kind=None, limit=20):
    return market_catalog.search(
        query=query, asset_class=asset_class, kind=kind, limit=limit, extra=live_listing()
    )
