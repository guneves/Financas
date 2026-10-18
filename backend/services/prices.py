"""Cotacoes de mercado: download (brapi e yfinance), cache em memoria e gravacao.

`download_market_prices()` pergunta ao brapi primeiro (quando ha token) e manda
ao yfinance so o que faltou. Os caches `_price_cache` / `_history_cache` sao do
processo, protegidos por `_price_cache_lock`; `_price_fetch_executor` limita o
tempo de espera de um download travado. `record_price_quote()` grava a cotacao
em `price_quotes` — e o unico caminho que escreve la.

Os testes trocam `yf` e `download_close_prices` aqui; `routes/investments.py`
tambem le `yf` (o historico), entao o teste de evolucao troca os dois.
"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
import math
import threading
import time

try:
    import yfinance as yf
except ImportError:
    yf = None

from asset_classes import QUOTED_ASSET_CLASSES
import brapi_client
from integrations import record_provider_result
from config import (
    HISTORY_CACHE_TTL_SECONDS,
    PRICE_CACHE_TTL_SECONDS,
    PRICE_DOWNLOAD_TIMEOUT_SECONDS,
    PRICE_FETCH_TIMEOUT_SECONDS,
    PRICE_FETCH_WORKERS,
    PRICE_QUOTE_STALE_HOURS,
)
from dates import parse_iso_date, parse_iso_datetime
from db import encode_metadata, new_id, utc_timestamp
from money import rounded_money
from validators import safe_float
from applog import get_logger

logger = get_logger(__name__)


_price_cache = {}
_history_cache = {}
_price_cache_lock = threading.Lock()
_price_fetch_executor = ThreadPoolExecutor(max_workers=PRICE_FETCH_WORKERS)


def quote_timestamp(date_value=None):
    parsed = parse_iso_date(date_value)
    if parsed:
        return f"{parsed.strftime('%Y-%m-%d')}T00:00:00Z"
    return utc_timestamp()


def quote_transaction_id(asset_class, transaction_id):
    return None if asset_class in QUOTED_ASSET_CLASSES else transaction_id


def record_price_quote(
    conn,
    current_user_id,
    asset_id,
    price,
    *,
    asset_class=None,
    transaction_id=None,
    quoted_at=None,
    source="manual",
    metadata=None,
):
    if price is None:
        return None

    numeric_price = safe_float(price, None)
    if numeric_price is None or not math.isfinite(numeric_price) or numeric_price < 0:
        return None

    row = conn.execute(
        "SELECT asset_class FROM assets WHERE id = ? AND user_id = ?",
        (asset_id, current_user_id),
    ).fetchone()
    resolved_asset_class = asset_class or (row["asset_class"] if row else None)
    scoped_transaction_id = quote_transaction_id(resolved_asset_class, transaction_id)

    quote_id = new_id()
    conn.execute(
        """
        INSERT INTO price_quotes
        (id, user_id, asset_id, transaction_id, price, quoted_at, source, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            quote_id,
            current_user_id,
            asset_id,
            scoped_transaction_id,
            round(numeric_price, 6),
            quoted_at or utc_timestamp(),
            source,
            encode_metadata(metadata),
        ),
    )
    return quote_id


def yahoo_symbol(ticker_symbol, foreign=False):
    """PETR4 -> PETR4.SA. Ticker estrangeiro (ou que ja traz a bolsa, como
    7203.T) vai como veio."""
    yf_symbol = str(ticker_symbol or "").strip().upper()
    if foreign or "." in yf_symbol:
        return yf_symbol
    if any(char.isdigit() for char in yf_symbol):
        return f"{yf_symbol}.SA"
    return yf_symbol


def quote_age_hours(quoted_at):
    parsed = parse_iso_datetime(quoted_at)
    if not parsed:
        return None
    return max((datetime.now(timezone.utc) - parsed).total_seconds() / 3600, 0)


def quote_status(quoted_at):
    age_hours = quote_age_hours(quoted_at)
    if age_hours is None:
        return "missing"
    if age_hours > PRICE_QUOTE_STALE_HOURS:
        return "stale"
    return "fresh"


def quote_info_from_investment(investment):
    quoted_at = investment.get("current_quote_quoted_at")
    status = quote_status(quoted_at)
    age_hours = quote_age_hours(quoted_at)
    return {
        "id": investment.get("current_quote_id"),
        "source": investment.get("current_quote_source") or "fallback",
        "quoted_at": quoted_at,
        "metadata": investment.get("current_quote_metadata") or {},
        "age_hours": round(age_hours, 2) if age_hours is not None else None,
        "stale_after_hours": PRICE_QUOTE_STALE_HOURS,
        "status": status,
        "is_stale": status != "fresh",
    }


def ticker_key(ticker_symbol):
    return str(ticker_symbol or "").strip().upper()


def read_price_cache(tickers):
    now = time.time()
    fresh_prices = {}
    fallback_prices = {}
    stale_tickers = []

    with _price_cache_lock:
        for ticker in tickers:
            entry = _price_cache.get(ticker)
            if not entry:
                stale_tickers.append(ticker)
                continue

            price = entry.get("price")
            updated_at = entry.get("updated_at", 0)
            if price is None:
                stale_tickers.append(ticker)
                continue

            fallback_prices[ticker] = price
            if now - updated_at <= PRICE_CACHE_TTL_SECONDS:
                fresh_prices[ticker] = price
            else:
                stale_tickers.append(ticker)

    return fresh_prices, fallback_prices, stale_tickers


def update_price_cache(price_by_ticker):
    if not price_by_ticker:
        return

    now = time.time()
    with _price_cache_lock:
        for ticker, price in price_by_ticker.items():
            try:
                numeric_price = float(price)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(numeric_price) or numeric_price < 0:
                continue

            _price_cache[ticker] = {
                "price": numeric_price,
                "updated_at": now,
            }


def cache_market_prices_from_future(future):
    try:
        update_price_cache(future.result())
    except Exception as exc:
        logger.exception(f"Erro ao finalizar cache de cotacoes: {exc}")


def extract_close_values(data, yf_symbol):
    if data is None or getattr(data, "empty", True):
        return None

    columns = getattr(data, "columns", None)
    if columns is None:
        return None

    close_values = None
    try:
        if getattr(columns, "nlevels", 1) > 1:
            if (yf_symbol, "Close") in columns:
                close_values = data[(yf_symbol, "Close")]
            elif ("Close", yf_symbol) in columns:
                close_values = data[("Close", yf_symbol)]
            elif yf_symbol in columns.get_level_values(0):
                symbol_frame = data[yf_symbol]
                if "Close" in symbol_frame:
                    close_values = symbol_frame["Close"]
            elif "Close" in columns.get_level_values(0):
                close_frame = data["Close"]
                if yf_symbol in getattr(close_frame, "columns", []):
                    close_values = close_frame[yf_symbol]
        elif "Close" in columns:
            close_values = data["Close"]
    except Exception:
        return None

    if close_values is None:
        return None
    if hasattr(close_values, "columns"):
        if getattr(close_values, "empty", True):
            return None
        close_values = close_values.iloc[:, 0]

    if not hasattr(close_values, "dropna"):
        return None

    close_values = close_values.dropna()
    if close_values.empty:
        return None
    return close_values


def extract_latest_close(data, yf_symbol):
    close_values = extract_close_values(data, yf_symbol)
    if close_values is None:
        return None

    try:
        price = float(close_values.iloc[-1])
    except (TypeError, ValueError):
        return None

    if not math.isfinite(price) or price < 0:
        return None
    return price


def download_close_prices(yf_symbols, *, period, interval):
    if yf is None or not yf_symbols:
        return {}

    try:
        data = yf.download(
            tickers=" ".join(yf_symbols),
            period=period,
            interval=interval,
            group_by="ticker",
            threads=True,
            progress=False,
            auto_adjust=False,
            timeout=PRICE_DOWNLOAD_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.exception(f"Erro ao consultar yfinance ({period}/{interval}): {exc}")
        record_provider_result("yfinance", False, exc)
        return {}

    prices = {}
    for yf_symbol in yf_symbols:
        price = extract_latest_close(data, yf_symbol)
        if price is not None:
            prices[yf_symbol] = price
    # Nenhum preco para nenhum simbolo e falha do provedor (fora do ar, bloqueio);
    # so parte deles e ticker que o Yahoo nao conhece.
    if prices:
        record_provider_result("yfinance", True)
    else:
        record_provider_result("yfinance", False, f"Sem cotacao para {', '.join(yf_symbols[:5])}")
    return prices


def download_brapi_prices(tickers):
    """Cotacoes na brapi: um credito por lote, cache e dedupe no brapi_client.

    Sem BRAPI_TOKEN configurado o provedor simplesmente nao existe e o yfinance
    continua sendo o unico caminho; qualquer falha aqui tambem cai para ele.
    """
    if not tickers or not brapi_client.is_configured():
        return {}

    try:
        prices = brapi_client.get_market_prices(tickers)
    except brapi_client.BrapiError as exc:
        if brapi_client.QUOTES_PER_REQUEST_EXCEEDED in str(exc):
            # Nao e a brapi fora do ar: o plano aceita menos tickers por consulta.
            exc = brapi_client.BrapiError(
                f"O plano da brapi aceita menos tickers por consulta que os "
                f"{brapi_client.MAX_SYMBOLS_PER_REQUEST} enviados: defina "
                "BRAPI_MAX_SYMBOLS_PER_REQUEST=1 no .env (um crédito por ticker). "
                "Até lá, as cotações vêm do yfinance."
            )
        logger.exception(f"Erro ao consultar cotacoes na brapi: {exc}")
        record_provider_result("brapi", False, exc)
        return {}
    record_provider_result("brapi", True)

    valid = {}
    for ticker, price in prices.items():
        numeric = safe_float(price, None)
        if numeric is None or not math.isfinite(numeric) or numeric <= 0:
            continue
        valid[ticker_key(ticker)] = rounded_money(numeric)
    return valid


def market_price_provider(ticker):
    """Quem entregou a cotacao mais recente deste ticker, para o metadata."""
    if brapi_client.cached_quote(ticker) is not None:
        return "brapi"
    return "yfinance"


def download_market_prices(tickers, foreign=()):
    # A brapi e o provedor primario quando ha token; o yfinance cobre o resto
    # (ticker fora da B3, token ausente, brapi fora do ar). Ativo em moeda
    # estrangeira (`foreign`) vai direto ao yfinance: a brapi e so B3.
    foreign = set(foreign or ())
    prices = download_brapi_prices([ticker for ticker in tickers if ticker not in foreign])
    tickers = [ticker for ticker in tickers if ticker not in prices]
    if not tickers:
        return prices
    if yf is None:
        return prices

    symbols_by_ticker = {ticker: yahoo_symbol(ticker, foreign=ticker in foreign) for ticker in tickers}
    yf_symbols = sorted(set(symbols_by_ticker.values()))

    symbol_prices = download_close_prices(yf_symbols, period="1d", interval="1m")
    missing_symbols = [symbol for symbol in yf_symbols if symbol not in symbol_prices]
    if missing_symbols:
        symbol_prices.update(download_close_prices(missing_symbols, period="5d", interval="1d"))

    for ticker, yf_symbol in symbols_by_ticker.items():
        price = symbol_prices.get(yf_symbol)
        if price is not None:
            prices[ticker] = rounded_money(price)
    return prices


def download_monthly_history(tickers, start_date):
    historical_prices = {ticker: {} for ticker in tickers}
    if yf is None or not tickers:
        return historical_prices

    symbols_by_ticker = {ticker: yahoo_symbol(ticker) for ticker in tickers}
    yf_symbols = sorted(set(symbols_by_ticker.values()))

    try:
        data = yf.download(
            tickers=" ".join(yf_symbols),
            start=start_date,
            interval="1mo",
            group_by="ticker",
            threads=True,
            progress=False,
            auto_adjust=False,
            timeout=PRICE_DOWNLOAD_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.exception(f"Erro ao consultar historico no yfinance: {exc}")
        return historical_prices

    for ticker, yf_symbol in symbols_by_ticker.items():
        close_values = extract_close_values(data, yf_symbol)
        if close_values is None:
            continue

        for date, price in close_values.items():
            try:
                numeric_price = float(price)
            except (TypeError, ValueError):
                continue
            if math.isfinite(numeric_price):
                historical_prices[ticker][date.strftime("%Y-%m")] = rounded_money(numeric_price)

    return historical_prices


def get_monthly_history(tickers, start_date):
    normalized_tickers = tuple(sorted({ticker_key(ticker) for ticker in tickers if ticker_key(ticker)}))
    if not normalized_tickers:
        return {}

    cache_key = (normalized_tickers, start_date)
    now = time.time()
    with _price_cache_lock:
        cached = _history_cache.get(cache_key)
        if cached and now - cached.get("updated_at", 0) <= HISTORY_CACHE_TTL_SECONDS:
            return {
                ticker: dict(prices)
                for ticker, prices in cached.get("prices", {}).items()
            }

    prices = download_monthly_history(list(normalized_tickers), start_date)
    with _price_cache_lock:
        _history_cache[cache_key] = {
            "prices": {
                ticker: dict(monthly_prices)
                for ticker, monthly_prices in prices.items()
            },
            "updated_at": now,
        }
    return prices


def extract_split_events(data, yf_symbol):
    """[(AAAA-MM-DD, fator)] da coluna "Stock Splits" (download com actions=True).

    O Yahoo registra a bonificacao da B3 como desdobramento (KLBN4 1.1 em
    2024-05-07, SOJA3 1.048629 em 2025-12-19) e ajusta o fechamento anterior
    por ela; `restore_quantity_basis()` desfaz isso."""
    if data is None or getattr(data, "empty", True):
        return []
    try:
        columns = data.columns
        if getattr(columns, "nlevels", 1) > 1:
            if yf_symbol not in columns.get_level_values(0):
                return []
            frame = data[yf_symbol]
        else:
            frame = data
        if "Stock Splits" not in frame:
            return []
        splits = frame["Stock Splits"].dropna()
    except Exception:
        return []
    events = []
    for date, ratio in splits.items():
        ratio = safe_float(ratio, 0.0)
        if math.isfinite(ratio) and ratio > 0 and abs(ratio - 1) > 1e-9:
            events.append((date.strftime("%Y-%m-%d"), ratio))
    return events


def download_daily_history(tickers, start_date):
    """{"prices": {ticker: {AAAA-MM-DD: fechamento}}, "splits": {ticker: [(AAAA-MM-DD, fator)]}}.

    Fechamento sem ajuste de proventos (auto_adjust=False), mas ajustado pelos
    desdobramentos que o Yahoo conhece — inclusive as bonificacoes."""
    result = {"prices": {ticker: {} for ticker in tickers}, "splits": {ticker: [] for ticker in tickers}}
    if yf is None or not tickers:
        return result

    symbols_by_ticker = {ticker: yahoo_symbol(ticker) for ticker in tickers}
    yf_symbols = sorted(set(symbols_by_ticker.values()))
    try:
        data = yf.download(
            tickers=" ".join(yf_symbols),
            start=start_date,
            interval="1d",
            group_by="ticker",
            threads=True,
            progress=False,
            auto_adjust=False,
            actions=True,
            timeout=PRICE_DOWNLOAD_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.exception(f"Erro ao consultar historico diario no yfinance: {exc}")
        return result

    for ticker, yf_symbol in symbols_by_ticker.items():
        result["splits"][ticker] = extract_split_events(data, yf_symbol)
        close_values = extract_close_values(data, yf_symbol)
        if close_values is None:
            continue
        for date, price in close_values.items():
            numeric_price = safe_float(price, None)
            if numeric_price is not None and math.isfinite(numeric_price) and numeric_price > 0:
                result["prices"][ticker][date.strftime("%Y-%m-%d")] = numeric_price
    return result


def get_daily_history(tickers, start_date):
    """`download_daily_history()` com o cache de historico do processo."""
    normalized_tickers = tuple(sorted({ticker_key(ticker) for ticker in tickers if ticker_key(ticker)}))
    if not normalized_tickers:
        return {"prices": {}, "splits": {}}

    cache_key = ("daily", normalized_tickers, start_date)
    now = time.time()
    with _price_cache_lock:
        cached = _history_cache.get(cache_key)
        if cached and now - cached.get("updated_at", 0) <= HISTORY_CACHE_TTL_SECONDS:
            return {
                "prices": {ticker: dict(days) for ticker, days in cached["prices"].items()},
                "splits": {ticker: list(events) for ticker, events in cached["splits"].items()},
            }

    history = download_daily_history(list(normalized_tickers), start_date)
    with _price_cache_lock:
        _history_cache[cache_key] = {
            "prices": {ticker: dict(days) for ticker, days in history["prices"].items()},
            "splits": {ticker: list(events) for ticker, events in history["splits"].items()},
            "updated_at": now,
        }
    return history


# Um evento do Yahoo e o mesmo desdobramento/grupamento registrado quando cai
# ate tantos dias da data ex e o fator difere menos que isto.
SPLIT_MATCH_DAYS = 7
SPLIT_MATCH_TOLERANCE = 0.02


def restore_quantity_basis(prices_by_ticker, splits_by_ticker, registered_splits):
    """Fechamentos na base das quantidades gravadas.

    Um desdobramento ou grupamento registrado reescala as operacoes anteriores
    (services/corporate_actions.py): o ajuste do Yahoo por ele esta certo. Uma
    bonificacao nao reescala nada (e uma compra de custo zero na data), e um
    evento nao registrado deixa as quantidades na base antiga: nos dois casos o
    preco anterior ao evento volta a ser o negociado (vezes o fator), senao cada
    compra feita antes dele pareceria perder 1 - 1/fator no mesmo dia.

    `prices_by_ticker` e {ticker: {AAAA-MM-DD ou AAAA-MM: preco}};
    `registered_splits`, {ticker: [(AAAA-MM-DD, fator)]}. Chave mensal: o evento
    vale para os meses anteriores ao dele (o fechamento do mes ja e depois dele).
    """
    restored = {}
    for ticker, prices in prices_by_ticker.items():
        pending = []
        for event_date, ratio in splits_by_ticker.get(ticker) or []:
            event_day = parse_iso_date(event_date)
            matched = any(
                event_day and parse_iso_date(day)
                and abs((event_day - parse_iso_date(day)).days) <= SPLIT_MATCH_DAYS
                and abs(ratio / factor - 1) < SPLIT_MATCH_TOLERANCE
                for day, factor in registered_splits.get(ticker) or []
                if factor
            )
            if not matched:
                pending.append((event_date, ratio))
        if not pending:
            restored[ticker] = dict(prices)
            continue
        adjusted = {}
        for key, price in prices.items():
            factor = 1.0
            for event_date, ratio in pending:
                if key < event_date[:len(key)]:
                    factor *= ratio
            adjusted[key] = price * factor
        restored[ticker] = adjusted
    return restored


def monthly_closes(daily_prices):
    """{ticker: {AAAA-MM: ultimo fechamento do mes}} a partir do historico diario."""
    monthly = {}
    for ticker, days in daily_prices.items():
        months = {}
        for day in sorted(days):
            months[day[:7]] = days[day]
        monthly[ticker] = months
    return monthly


def get_market_prices(tickers, *, force=False):
    normalized_tickers = sorted({ticker_key(ticker) for ticker in tickers if ticker_key(ticker)})
    if not normalized_tickers:
        return {}
    if yf is None and not brapi_client.is_configured():
        logger.warning("Nenhum provedor de cotacao disponivel (sem yfinance e sem BRAPI_TOKEN).")
        return {}

    fresh_prices, fallback_prices, stale_tickers = read_price_cache(normalized_tickers)
    prices = {} if force else dict(fresh_prices)
    tickers_to_fetch = normalized_tickers if force else stale_tickers
    if not tickers_to_fetch:
        return prices

    future = _price_fetch_executor.submit(download_market_prices, tickers_to_fetch)
    try:
        fetched_prices = future.result(timeout=PRICE_FETCH_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        future.add_done_callback(cache_market_prices_from_future)
        logger.warning(
            "Tempo limite ao consultar yfinance; usando cotacoes em cache "
            "ou valores ja gravados."
        )
        for ticker in tickers_to_fetch:
            if ticker in fallback_prices:
                prices[ticker] = fallback_prices[ticker]
        return prices
    except Exception as exc:
        logger.exception(f"Erro ao consultar cotacoes no yfinance: {exc}")
        for ticker in tickers_to_fetch:
            if ticker in fallback_prices:
                prices[ticker] = fallback_prices[ticker]
        return prices

    update_price_cache(fetched_prices)
    prices.update(fetched_prices)
    for ticker in tickers_to_fetch:
        if ticker not in prices and ticker in fallback_prices:
            prices[ticker] = fallback_prices[ticker]
    return prices


def get_market_prices_with_status(tickers, *, force=False, foreign=()):
    normalized_tickers = sorted({ticker_key(ticker) for ticker in tickers if ticker_key(ticker)})
    result = {
        "prices": {},
        "source_by_ticker": {},
        "failed_tickers": [],
        "errors": {},
    }
    if not normalized_tickers:
        return result
    if yf is None and not brapi_client.is_configured():
        logger.warning("Nenhum provedor de cotacao disponivel (sem yfinance e sem BRAPI_TOKEN).")
        result["failed_tickers"] = normalized_tickers
        result["errors"] = {ticker: "Provedor de cotacao indisponivel" for ticker in normalized_tickers}
        return result

    fresh_prices, fallback_prices, stale_tickers = read_price_cache(normalized_tickers)
    if not force:
        for ticker, price in fresh_prices.items():
            result["prices"][ticker] = price
            result["source_by_ticker"][ticker] = "cache"

    tickers_to_fetch = normalized_tickers if force else stale_tickers
    if not tickers_to_fetch:
        return result

    fetch_error = None
    future = _price_fetch_executor.submit(download_market_prices, tickers_to_fetch, foreign)
    try:
        fetched_prices = future.result(timeout=PRICE_FETCH_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        future.add_done_callback(cache_market_prices_from_future)
        fetch_error = "Tempo limite ao consultar yfinance"
        logger.warning("Tempo limite ao consultar yfinance; usando cache quando disponivel.")
        fetched_prices = {}
    except Exception as exc:
        fetch_error = f"Erro ao consultar yfinance: {exc}"
        logger.warning(fetch_error)
        fetched_prices = {}

    update_price_cache(fetched_prices)
    for ticker, price in fetched_prices.items():
        result["prices"][ticker] = price
        result["source_by_ticker"][ticker] = "market"

    for ticker in tickers_to_fetch:
        if ticker in result["prices"]:
            continue
        if ticker in fallback_prices:
            result["prices"][ticker] = fallback_prices[ticker]
            result["source_by_ticker"][ticker] = "cache_stale"
        else:
            result["failed_tickers"].append(ticker)
            result["errors"][ticker] = fetch_error or "Cotacao nao encontrada"

    return result
