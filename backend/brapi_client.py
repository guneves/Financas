"""Cliente da brapi (https://brapi.dev) para cotacoes de ativos da B3.

Modulo sem banco de dados, no mesmo formato de `statement_import.py` e
`export_csv.py`: funcoes puras mais um cache em memoria. Quem grava cotacao no
banco e o `app.py`.

O plano gratuito da brapi tem um limite diario de creditos, entao tudo aqui
existe para gastar o minimo possivel:

* **Lote** — uma consulta com `PETR4,VALE3,BBAS3` custa 1 credito, nao 3.
* **Cache** — TTL de 5 minutos por ticker (`BRAPI_CACHE_TTL_SECONDS`).
* **Fora do pregao** — o preco de PETR4 nao muda as 23h de um sabado. Com o
  mercado fechado a entrada nao expira por tempo: ela vale ate a proxima
  abertura da B3 (seg-sex, 10:00-18:00 no horario de Brasilia).
* **Deduplicacao** — duas telas pedindo o mesmo ticker ao mesmo tempo, com o
  cache vazio, fazem *uma* requisicao; a segunda espera a primeira terminar.

O token vem de `BRAPI_TOKEN` (arquivo `backend/.env`, gitignored) e vai no
cabecalho `Authorization: Bearer <token>`. Ele nunca e devolvido ao cliente:
quem fala com a brapi e o backend, o frontend so ve o preco.
"""

import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

BRAPI_BASE_URL = os.getenv("BRAPI_BASE_URL", "https://brapi.dev/api").rstrip("/")
QUOTE_PATH = "/v2/stocks/quote"

# Horario de Brasilia nao tem mais horario de verao desde 2019, entao um offset
# fixo de -03:00 basta e evita uma dependencia de tzdata.
BRT = timezone(timedelta(hours=-3))
MARKET_OPEN_HOUR = 10
MARKET_CLOSE_HOUR = 18

# Quantos tickers cabem em uma consulta. A brapi aceita listas longas, mas uma
# URL gigante e fragil e um erro derruba o lote inteiro.
MAX_SYMBOLS_PER_REQUEST = 20


def _read_int_env(name, default, minimum=None):
    try:
        value = int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        return default
    if minimum is not None and value < minimum:
        return minimum
    return value


def _read_float_env(name, default, minimum=None, maximum=None):
    try:
        value = float(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        return default
    if minimum is not None and value < minimum:
        return minimum
    if maximum is not None and value > maximum:
        return maximum
    return value


# O minimo de 300s e proposital: o requisito e "pelo menos 5 minutos".
CACHE_TTL_SECONDS = _read_int_env("BRAPI_CACHE_TTL_SECONDS", 300, minimum=300)
REQUEST_TIMEOUT_SECONDS = _read_float_env(
    "BRAPI_TIMEOUT_SECONDS", 8.0, minimum=1.0, maximum=30.0
)


class BrapiError(RuntimeError):
    """Base de todos os erros do cliente — o app.py filtra por ela."""


class BrapiNotConfiguredError(BrapiError):
    """BRAPI_TOKEN ausente."""


class BrapiHTTPError(BrapiError):
    """Resposta com status fora da faixa 2xx."""

    def __init__(self, status, detail="", symbols=None):
        self.status = int(status)
        self.detail = str(detail or "")[:500]
        self.symbols = list(symbols or [])
        super().__init__(f"brapi respondeu {self.status}: {self.detail or 'sem detalhe'}")


class BrapiUnavailableError(BrapiError):
    """Timeout ou falha de rede."""


class BrapiResponseError(BrapiError):
    """Corpo 2xx que nao tem o formato documentado."""


@dataclass(frozen=True)
class StockQuote:
    """Um item de `results[]` da brapi, com os campos que o app usa.

    `raw` guarda o objeto original para quem precisar de um campo que ainda nao
    foi promovido a atributo — assim acrescentar um campo novo nao quebra nada.
    """

    symbol: str
    short_name: str = ""
    long_name: str = ""
    currency: str = ""
    regular_market_price: float = None
    regular_market_change: float = None
    regular_market_change_percent: float = None
    regular_market_day_high: float = None
    regular_market_day_low: float = None
    regular_market_previous_close: float = None
    regular_market_volume: float = None
    regular_market_time: str = ""
    market_cap: float = None
    logo_url: str = ""
    raw: dict = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_payload(cls, payload):
        if not isinstance(payload, dict):
            raise BrapiResponseError("Item de results[] nao e um objeto")
        # Formato novo da brapi (visto em 2026-09-23): os campos da cotacao
        # vem dentro de `data`, e o item so traz symbol/requestedSymbol/changed.
        # O antigo trazia tudo no proprio item. Aceita os dois.
        nested = payload.get("data")
        if isinstance(nested, dict):
            payload = {**nested, **{key: value for key, value in payload.items() if key != "data"}}
        symbol = normalize_symbol(payload.get("symbol"))
        if not symbol:
            raise BrapiResponseError("Item de results[] sem symbol")
        return cls(
            symbol=symbol,
            short_name=str(payload.get("shortName") or ""),
            long_name=str(payload.get("longName") or ""),
            currency=str(payload.get("currency") or ""),
            regular_market_price=_safe_price(payload.get("regularMarketPrice")),
            regular_market_change=_safe_float(payload.get("regularMarketChange")),
            regular_market_change_percent=_safe_float(
                payload.get("regularMarketChangePercent")
            ),
            regular_market_day_high=_safe_price(payload.get("regularMarketDayHigh")),
            regular_market_day_low=_safe_price(payload.get("regularMarketDayLow")),
            regular_market_previous_close=_safe_price(
                payload.get("regularMarketPreviousClose")
            ),
            regular_market_volume=_safe_float(payload.get("regularMarketVolume")),
            regular_market_time=str(payload.get("regularMarketTime") or ""),
            market_cap=_safe_float(payload.get("marketCap")),
            logo_url=str(payload.get("logourl") or ""),
            raw=dict(payload),
        )

    def as_dict(self):
        return {
            "symbol": self.symbol,
            "short_name": self.short_name,
            "long_name": self.long_name,
            "currency": self.currency,
            "regular_market_price": self.regular_market_price,
            "regular_market_change": self.regular_market_change,
            "regular_market_change_percent": self.regular_market_change_percent,
            "regular_market_previous_close": self.regular_market_previous_close,
            "regular_market_time": self.regular_market_time,
        }


def _safe_float(value, default=None):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if numeric != numeric or numeric in (float("inf"), float("-inf")):  # NaN/inf
        return default
    return numeric


def _safe_price(value):
    """Preco em centavos com ROUND_HALF_UP — nunca o round() do Python."""
    numeric = _safe_float(value)
    if numeric is None or numeric < 0:
        return None
    try:
        return float(Decimal(str(numeric)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return None


def normalize_symbol(symbol):
    """`petr4.sa ` -> `PETR4`. A brapi usa o ticker puro da B3, sem sufixo."""
    value = str(symbol or "").strip().upper()
    if value.endswith(".SA"):
        value = value[:-3]
    return value


def normalize_symbols(symbols):
    """Aceita lista, tupla ou string separada por virgula; devolve lista unica.

    A ordem do pedido e preservada — `get_stock_quote()` devolve o primeiro.
    """
    if symbols is None:
        return []
    if isinstance(symbols, str):
        candidates = symbols.split(",")
    else:
        candidates = list(symbols)

    ordered = []
    seen = set()
    for candidate in candidates:
        symbol = normalize_symbol(candidate)
        if symbol and symbol not in seen:
            seen.add(symbol)
            ordered.append(symbol)
    return ordered


def brapi_token():
    return str(os.getenv("BRAPI_TOKEN", "") or "").strip()


def is_configured():
    return bool(brapi_token())


# ---------------------------------------------------------------------------
# Pregao da B3
# ---------------------------------------------------------------------------

def is_market_open(now=None):
    """Seg-sex, 10:00 <= hora < 18:00 no horario de Brasilia.

    Feriado da B3 nao entra na conta: tratar um feriado como pregao aberto so
    encurta o cache, o que custa creditos mas nunca devolve preco errado.
    """
    moment = _to_brt(now)
    if moment.weekday() >= 5:
        return False
    return MARKET_OPEN_HOUR <= moment.hour < MARKET_CLOSE_HOUR


def next_market_open(now=None):
    """Proxima abertura da B3 a partir de `now` (datetime com fuso BRT)."""
    moment = _to_brt(now)
    candidate = moment.replace(
        hour=MARKET_OPEN_HOUR, minute=0, second=0, microsecond=0
    )
    if candidate <= moment:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def _to_brt(now=None):
    if now is None:
        return datetime.now(BRT)
    if now.tzinfo is None:
        return now.replace(tzinfo=BRT)
    return now.astimezone(BRT)


def cache_expiry(now=None):
    """Instante (epoch) em que uma entrada gravada agora deixa de valer.

    Pregao aberto: agora + TTL. Pregao fechado: a proxima abertura — o preco de
    fechamento nao muda ate la, entao nao ha motivo para gastar credito.
    """
    moment = _to_brt(now)
    epoch_now = moment.timestamp()
    if is_market_open(moment):
        return epoch_now + CACHE_TTL_SECONDS
    return next_market_open(moment).timestamp()


# ---------------------------------------------------------------------------
# Cache e deduplicacao
# ---------------------------------------------------------------------------

_cache = {}           # symbol -> {"quote": StockQuote, "expires_at": float}
_inflight = {}        # symbol -> _Fetch em andamento
_lock = threading.Lock()


class _Fetch:
    """Uma busca em voo. Quem chega depois espera este evento, nao a rede."""

    def __init__(self, symbols):
        self.symbols = list(symbols)
        self.event = threading.Event()
        self.quotes = {}
        self.error = None

    def finish(self, quotes=None, error=None):
        self.quotes = quotes or {}
        self.error = error
        self.event.set()


def clear_cache():
    """Usado pelos testes e por um refresh forcado."""
    with _lock:
        _cache.clear()


def cached_quote(symbol, now=None):
    """Cotacao ainda valida no cache, ou None. Nao vai a rede."""
    epoch_now = _to_brt(now).timestamp()
    with _lock:
        entry = _cache.get(normalize_symbol(symbol))
        if entry and entry["expires_at"] > epoch_now:
            return entry["quote"]
    return None


def _store(quotes, now=None):
    expires_at = cache_expiry(now)
    with _lock:
        for symbol, quote in quotes.items():
            _cache[symbol] = {"quote": quote, "expires_at": expires_at}


def _read_cache(symbols, now=None):
    epoch_now = _to_brt(now).timestamp()
    hits = {}
    misses = []
    with _lock:
        for symbol in symbols:
            entry = _cache.get(symbol)
            if entry and entry["expires_at"] > epoch_now:
                hits[symbol] = entry["quote"]
            else:
                misses.append(symbol)
    return hits, misses


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _request_quotes(symbols, timeout=None):
    """Uma chamada HTTP, um credito. Sem cache e sem deduplicacao."""
    token = brapi_token()
    if not token:
        raise BrapiNotConfiguredError(
            "BRAPI_TOKEN nao configurado; defina-o em backend/.env"
        )

    query = urllib.parse.urlencode({"symbols": ",".join(symbols)})
    url = f"{BRAPI_BASE_URL}{QUOTE_PATH}?{query}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "FinanceMVP/1.0",
        },
    )

    try:
        with urllib.request.urlopen(
            req, timeout=timeout or REQUEST_TIMEOUT_SECONDS
        ) as response:
            body = response.read().decode("utf-8", errors="replace")
            status = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        except Exception:  # noqa: BLE001 - detalhe e opcional, o status basta
            detail = ""
        raise BrapiHTTPError(exc.code, _error_message(detail), symbols) from exc
    except urllib.error.URLError as exc:
        raise BrapiUnavailableError(f"Falha de rede ao consultar a brapi: {exc.reason}") from exc
    except TimeoutError as exc:
        raise BrapiUnavailableError("Tempo limite ao consultar a brapi") from exc

    if not 200 <= int(status) < 300:
        raise BrapiHTTPError(status, _error_message(body), symbols)

    try:
        payload = json.loads(body) if body.strip() else {}
    except ValueError as exc:
        raise BrapiResponseError("Resposta da brapi nao e JSON valido") from exc

    if not isinstance(payload, dict):
        raise BrapiResponseError("Resposta da brapi nao e um objeto")

    results = payload.get("results")
    if not isinstance(results, list):
        message = _error_message(payload)
        raise BrapiResponseError(f"Resposta da brapi sem results[]: {message or 'formato desconhecido'}")

    quotes = {}
    for item in results:
        try:
            quote = StockQuote.from_payload(item)
        except BrapiResponseError:
            continue
        quotes[quote.symbol] = quote
    return quotes


def _error_message(payload):
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return ""
        try:
            payload = json.loads(text)
        except ValueError:
            return text[:200]
    if isinstance(payload, dict):
        for key in ("message", "error", "erro", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:200]
    return ""


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------

def get_stock_quotes(symbols, *, force=False, timeout=None, now=None):
    """Cotacoes de varios tickers em um mapa {ticker: StockQuote}.

    Custa no maximo um credito por lote de `MAX_SYMBOLS_PER_REQUEST`, e zero se
    tudo estiver em cache. Tickers que a brapi nao conhece simplesmente nao
    aparecem no resultado — isso nao e erro.
    """
    wanted = normalize_symbols(symbols)
    if not wanted:
        return {}

    quotes = {}
    pending = wanted
    if not force:
        quotes, pending = _read_cache(wanted, now)
    if not pending:
        return {symbol: quotes[symbol] for symbol in wanted if symbol in quotes}

    for batch in _batches(pending, MAX_SYMBOLS_PER_REQUEST):
        quotes.update(_fetch_deduplicated(batch, timeout=timeout, now=now))

    return {symbol: quotes[symbol] for symbol in wanted if symbol in quotes}


def get_stock_quote(symbols, *, force=False, timeout=None, now=None):
    """A cotacao do primeiro ticker pedido (`results[0]`), ou None.

    Aceita `"PETR4"`, `"PETR4,VALE3"` ou `["PETR4", "VALE3"]`. Passar a lista
    inteira de uma vez e o caminho barato: um credito em vez de N.
    """
    wanted = normalize_symbols(symbols)
    if not wanted:
        return None
    quotes = get_stock_quotes(wanted, force=force, timeout=timeout, now=now)
    for symbol in wanted:
        if symbol in quotes:
            return quotes[symbol]
    return None


def get_market_prices(symbols, *, force=False, timeout=None, now=None):
    """Adaptador para o `app.py`: {ticker: preco}, sem os demais campos."""
    prices = {}
    for symbol, quote in get_stock_quotes(
        symbols, force=force, timeout=timeout, now=now
    ).items():
        if quote.regular_market_price is not None:
            prices[symbol] = quote.regular_market_price
    return prices


# ---------------------------------------------------------------------------
# Setores (/quote/list)
# ---------------------------------------------------------------------------
#
# A cotacao (/v2/stocks/quote) nao traz setor; a listagem (/quote/list) traz
# `sector` (taxonomia em ingles, ex. "Finance") e `subsector` (em portugues,
# ex. "Bancos Diversificados"; para FII, o segmento: "Logistica", "Shoppings").
# Visto em 2026-09-26: uma pagina de ate 2000 papeis, ~2300 no total — duas
# paginas cobrem a B3 inteira, entao preencher o setor da carteira toda custa
# no maximo dois creditos, nao um por ticker. O setor muda raramente: a lista
# fica em memoria por um dia.

LIST_PATH = "/quote/list"
LIST_PAGE_SIZE = 2000
LIST_MAX_PAGES = 5
SECTOR_CACHE_TTL_SECONDS = _read_int_env("BRAPI_SECTOR_CACHE_TTL_SECONDS", 86400, minimum=3600)


@dataclass(frozen=True)
class SectorInfo:
    """Um item de `stocks[]` da /quote/list, so com o que a alocacao usa."""

    symbol: str
    sector: str = ""
    subsector: str = ""
    type: str = ""
    sub_type: str = ""

    @classmethod
    def from_payload(cls, payload):
        if not isinstance(payload, dict):
            return None
        symbol = normalize_symbol(payload.get("stock"))
        if not symbol:
            return None
        return cls(
            symbol=symbol,
            sector=str(payload.get("sector") or "").strip(),
            subsector=str(payload.get("subsector") or "").strip(),
            type=str(payload.get("type") or "").strip().lower(),
            sub_type=str(payload.get("subType") or "").strip().lower(),
        )


_sector_cache = {"entries": {}, "expires_at": 0.0, "complete": False}


def clear_sector_cache():
    with _lock:
        _sector_cache["entries"] = {}
        _sector_cache["expires_at"] = 0.0
        _sector_cache["complete"] = False


def _request_json(path, params, timeout=None):
    token = brapi_token()
    if not token:
        raise BrapiNotConfiguredError(
            "BRAPI_TOKEN nao configurado; defina-o em backend/.env"
        )
    url = f"{BRAPI_BASE_URL}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "FinanceMVP/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout or REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8", errors="replace")
            status = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        except Exception:  # noqa: BLE001 - detalhe e opcional, o status basta
            detail = ""
        raise BrapiHTTPError(exc.code, _error_message(detail)) from exc
    except urllib.error.URLError as exc:
        raise BrapiUnavailableError(f"Falha de rede ao consultar a brapi: {exc.reason}") from exc
    except TimeoutError as exc:
        raise BrapiUnavailableError("Tempo limite ao consultar a brapi") from exc

    if not 200 <= int(status) < 300:
        raise BrapiHTTPError(status, _error_message(body))
    try:
        payload = json.loads(body) if body.strip() else {}
    except ValueError as exc:
        raise BrapiResponseError("Resposta da brapi nao e JSON valido") from exc
    if not isinstance(payload, dict):
        raise BrapiResponseError("Resposta da brapi nao e um objeto")
    return payload


def _request_sector_page(page, timeout=None):
    """Uma pagina da /quote/list: ({ticker: SectorInfo}, tem_proxima)."""
    payload = _request_json(LIST_PATH, {"limit": LIST_PAGE_SIZE, "page": page}, timeout=timeout)
    stocks = payload.get("stocks")
    if not isinstance(stocks, list):
        raise BrapiResponseError("Resposta da brapi sem stocks[]")
    entries = {}
    for item in stocks:
        info = SectorInfo.from_payload(item)
        if info is not None:
            entries[info.symbol] = info
    return entries, bool(payload.get("hasNextPage"))


def get_sectors(symbols, *, force=False, timeout=None, now=None):
    """Setor de cada ticker pedido: {ticker: SectorInfo}.

    Le a listagem pagina a pagina ate achar todos os pedidos ou acabar a lista
    (no maximo `LIST_MAX_PAGES`). Ticker que a brapi nao conhece nao aparece —
    isso nao e erro. Com a lista inteira em cache, nao vai a rede.
    """
    wanted = normalize_symbols(symbols)
    if not wanted:
        return {}
    epoch_now = _to_brt(now).timestamp()

    with _lock:
        fresh = not force and _sector_cache["expires_at"] > epoch_now
        entries = dict(_sector_cache["entries"]) if fresh else {}
        complete = fresh and _sector_cache["complete"]

    if not complete and any(symbol not in entries for symbol in wanted):
        page = 1
        fetched = {}
        has_next = True
        while has_next and page <= LIST_MAX_PAGES:
            page_entries, has_next = _request_sector_page(page, timeout=timeout)
            fetched.update(page_entries)
            if all(symbol in fetched for symbol in wanted):
                break
            page += 1
        with _lock:
            _sector_cache["entries"] = fetched
            _sector_cache["expires_at"] = epoch_now + SECTOR_CACHE_TTL_SECONDS
            _sector_cache["complete"] = not has_next
        entries = fetched

    return {symbol: entries[symbol] for symbol in wanted if symbol in entries}


def _batches(symbols, size):
    for start in range(0, len(symbols), size):
        yield symbols[start:start + size]


def _fetch_deduplicated(symbols, *, timeout=None, now=None):
    """Garante uma unica ida a rede por ticker concorrente.

    Se outra thread ja esta buscando algum destes tickers, esta espera o
    resultado dela em vez de abrir uma segunda requisicao. O que sobrar (ticker
    que ninguem esta buscando) vira uma requisicao propria, e essa thread passa
    a ser a dona dela.
    """
    waiting_on = {}
    owned = []
    with _lock:
        for symbol in symbols:
            existing = _inflight.get(symbol)
            if existing is not None:
                waiting_on[symbol] = existing
            else:
                owned.append(symbol)

        fetch = _Fetch(owned) if owned else None
        for symbol in owned:
            _inflight[symbol] = fetch

    quotes = {}
    error = None
    if fetch is not None:
        try:
            fetched = _request_quotes(owned, timeout=timeout)
        except BrapiError as exc:
            error = exc
            with _lock:
                for symbol in owned:
                    if _inflight.get(symbol) is fetch:
                        del _inflight[symbol]
            fetch.finish(error=exc)
        else:
            _store(fetched, now)
            with _lock:
                for symbol in owned:
                    if _inflight.get(symbol) is fetch:
                        del _inflight[symbol]
            fetch.finish(quotes=fetched)
            quotes.update(fetched)

    # Os tickers que outra thread ja estava buscando.
    for symbol, pending_fetch in waiting_on.items():
        pending_fetch.event.wait(timeout or REQUEST_TIMEOUT_SECONDS)
        if symbol in pending_fetch.quotes:
            quotes[symbol] = pending_fetch.quotes[symbol]
        elif error is None and pending_fetch.error is not None:
            error = pending_fetch.error

    if not quotes and error is not None:
        raise error
    return quotes
