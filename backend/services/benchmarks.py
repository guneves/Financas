"""Indices de comparacao da Rentabilidade: IPCA, Ibovespa, IFIX e IDIV.

O CDI continua em `services/returns.py` (serie diaria do BCB). Aqui cada indice
vira um retorno por mes (AAAA-MM -> fracao), alinhado aos meses da carteira:

- IPCA: variacao mensal do BCB (SGS 433), pela mesma `fetch_bcb_series` da
  renda fixa. O IPCA de um mes so sai no mes seguinte: o ultimo mes costuma
  faltar.
- Ibovespa, IFIX, IDIV: fechamento do fim de cada mes. O retorno do mes e
  fechamento(mes) / fechamento(mes anterior) - 1; o mes atual usa o ultimo
  fechamento visto (vai ate hoje, como a carteira). Os tres sao indices de
  retorno total (proventos reinvestidos), entao comparam com o TWR.

Fontes (testadas em 2026-09-26): o yfinance tem o historico mensal do
Ibovespa (`^BVSP`), mas de `IFIX.SA` e `IDIV.SA` so o valor do dia; a brapi
gratuita da historico diario de ate 3 meses do `^BVSP` e so o dia do `IFIX`,
e nao conhece o IDIV. Por isso todo fechamento visto e guardado em
`benchmark_closes` (023): o app abre sem rede com o que ja buscou, e o
IFIX/IDIV ganham historico a partir do dia em que a tela foi aberta. Um mes
sem fechamento guardado fica sem retorno, e a resposta diz quantos meses o
indice cobre.

Os testes trocam `download_monthly_history` aqui, `brapi_client.get_history`
/ `is_configured` no modulo `brapi_client` e `fetch_bcb_series` em
`services.fixed_income`; `reset_fetch_throttle()` limpa as tentativas e o
IPCA guardado.
"""

from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import date, datetime, timezone
import calendar
import threading
import time

from applog import get_logger
import brapi_client
from config import HISTORY_CACHE_STALE_MAX_SECONDS, HISTORY_CACHE_TTL_SECONDS, PRICE_FETCH_TIMEOUT_SECONDS
from dates import month_key, month_label, subtract_months
from db import get_db
from integrations import record_provider_result
from services import fixed_income
from services.prices import (
    _price_fetch_executor,
    download_monthly_history,
    history_fetch_floor,
    schedule_history_refresh,
)
from validators import safe_float

logger = get_logger(__name__)

# Ordem de exibicao. O CDI nao esta aqui: ja vem em `cdi_*` da resposta.
BENCHMARKS = (
    ("IPCA", "IPCA"),
    ("IBOV", "Ibovespa"),
    ("IFIX", "IFIX"),
    ("IDIV", "IDIV"),
)
BENCHMARK_LABELS = dict(BENCHMARKS)
CLOSE_BENCHMARKS = ("IBOV", "IFIX", "IDIV")

YF_SYMBOLS = {"IBOV": "^BVSP", "IFIX": "IFIX.SA", "IDIV": "IDIV.SA"}
# A brapi nao conhece o IDIV (404 em 2026-09-26).
BRAPI_SYMBOLS = {"IBOV": "^BVSP", "IFIX": "IFIX"}

# Uma ida aos provedores por usuario a cada HISTORY_CACHE_TTL_SECONDS; no
# meio disso a tela le o banco. Sem rede, nao espera o timeout a cada abertura.
_attempts = {}
_attempts_lock = threading.Lock()


def reset_fetch_throttle():
    """Para os testes."""
    with _attempts_lock:
        _attempts.clear()
    with fixed_income._index_history_lock:
        fixed_income._index_history_cache.pop("ipca", None)


def _may_fetch(key):
    now = time.monotonic()
    with _attempts_lock:
        last = _attempts.get(key)
        if last is not None and now - last < HISTORY_CACHE_TTL_SECONDS:
            return False
        _attempts[key] = now
        return True


def _forget_attempt(key):
    with _attempts_lock:
        _attempts.pop(key, None)


# --- contas (puras) ---------------------------------------------------------------

def previous_month_key(key):
    year, month = int(key[:4]), int(key[5:7])
    return f"{year - 1}-12" if month == 1 else f"{year}-{month - 1:02d}"


def month_end_closes(closes):
    """[(data, fechamento)] -> {AAAA-MM: ultimo fechamento do mes}."""
    by_month = {}
    for day, close in sorted(closes or [], key=lambda item: item[0]):
        value = safe_float(close, None)
        if value is None or value <= 0:
            continue
        by_month[day.strftime("%Y-%m")] = value
    return by_month


def monthly_returns_from_closes(closes, keys):
    """{AAAA-MM: retorno} para cada mes de `keys` com fechamento nele e no anterior."""
    by_month = month_end_closes(closes)
    result = {}
    for key in keys:
        current = by_month.get(key)
        previous = by_month.get(previous_month_key(key))
        if current is not None and previous is not None:
            result[key] = current / previous - 1
    return result


def ipca_monthly_returns(series, keys):
    """Serie mensal do BCB [(data, variacao decimal)] -> {AAAA-MM: variacao}."""
    factors = {}
    for day, rate in series or []:
        key = month_key(day)
        factors[key] = factors.get(key, 1.0) * (1 + safe_float(rate))
    return {key: factors[key] - 1 for key in keys if key in factors}


def close_date_for(key, today):
    """Dia em que se guarda o fechamento mensal de `key`: hoje no mes atual,
    o ultimo dia do mes nos passados."""
    if key == today.strftime("%Y-%m"):
        return today
    year, month = int(key[:4]), int(key[5:7])
    return date(year, month, calendar.monthrange(year, month)[1])


# --- banco ----------------------------------------------------------------------

def store_closes(conn, current_user_id, benchmark, closes, source):
    stored = 0
    for day, close in closes:
        value = safe_float(close, None)
        if value is None or value <= 0:
            continue
        conn.execute(
            """
            INSERT INTO benchmark_closes (user_id, benchmark, close_date, close, source)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, benchmark, close_date) DO UPDATE SET
                close = excluded.close,
                source = excluded.source,
                fetched_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (current_user_id, benchmark, day.isoformat(), value, source),
        )
        stored += 1
    return stored


def stored_closes(conn, current_user_id, benchmark, since):
    rows = conn.execute(
        """
        SELECT close_date, close FROM benchmark_closes
        WHERE user_id = ? AND benchmark = ? AND close_date >= ?
        ORDER BY close_date
        """,
        (current_user_id, benchmark, since.isoformat()),
    ).fetchall()
    return [(date.fromisoformat(row["close_date"]), safe_float(row["close"])) for row in rows]


# --- rede -----------------------------------------------------------------------

def download_index_closes(start_date, today):
    """{benchmark: [(data, fechamento)]} e {benchmark: fonte}, do yfinance e,
    para o que faltou, da brapi. Registra o resultado de cada provedor."""
    closes = {}
    sources = {}
    history = download_monthly_history(list(YF_SYMBOLS.values()), start_date.strftime("%Y-%m-%d"))
    for benchmark, symbol in YF_SYMBOLS.items():
        months = (history or {}).get(symbol) or {}
        points = [(close_date_for(key, today), value) for key, value in months.items()]
        if points:
            closes[benchmark] = points
            sources[benchmark] = "yfinance"
    # download_monthly_history engole os erros: nenhum fechamento e falha.
    if closes:
        record_provider_result("yfinance", True)
    else:
        record_provider_result("yfinance", False, "Sem historico de indices (^BVSP, IFIX.SA, IDIV.SA)")

    today_key = today.strftime("%Y-%m")
    missing = [
        benchmark for benchmark in BRAPI_SYMBOLS
        if not any(day.strftime("%Y-%m") == today_key for day, _ in closes.get(benchmark, []))
    ]
    if missing and brapi_client.is_configured():
        for benchmark in missing:
            try:
                points = brapi_client.get_history(BRAPI_SYMBOLS[benchmark])
            except brapi_client.BrapiError as exc:
                logger.warning(f"brapi sem historico de {benchmark}: {exc}")
                record_provider_result("brapi", False, exc)
                continue
            record_provider_result("brapi", True)
            if points:
                closes[benchmark] = closes.get(benchmark, []) + list(points)
                sources[benchmark] = "brapi" if benchmark not in sources else f"{sources[benchmark]}+brapi"
    return closes, sources


def latest_stored_fetch(conn, current_user_id):
    """Quando os fechamentos do usuario foram buscados pela ultima vez (UTC), ou None."""
    row = conn.execute(
        "SELECT MAX(fetched_at) AS fetched_at FROM benchmark_closes WHERE user_id = ?",
        (current_user_id,),
    ).fetchone()
    value = row["fetched_at"] if row else None
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00").replace(" ", "T"))
    except ValueError:
        return None


def stored_closes_are_recent(current_user_id, now_utc=None):
    """Ha fechamentos guardados, buscados ha menos de HISTORY_CACHE_STALE_MAX_SECONDS.

    E o "servir vencido e atualizar depois" do historico de precos: com eles,
    a tela le o banco e a busca nova corre em segundo plano."""
    with get_db() as conn:
        fetched_at = latest_stored_fetch(conn, current_user_id)
    if fetched_at is None:
        return False
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    now_utc = now_utc or datetime.now(timezone.utc)
    return (now_utc - fetched_at).total_seconds() <= HISTORY_CACHE_STALE_MAX_SECONDS


def refresh_benchmark_closes(current_user_id, start_date, today, *, background=False):
    """Busca os fechamentos (no maximo uma vez por TTL) e guarda. Devolve
    {benchmark: fonte} do que veio agora, ou None quando nao buscou/falhou.

    Busca desde o piso do historico (`history_fetch_floor()`), nao desde a
    janela: uma ida por TTL serve a todos os periodos da tela. Com
    `background`, a busca vai para `schedule_history_refresh()` e a resposta
    nao a espera (devolve None)."""
    fetch_from = min(start_date, history_fetch_floor(today))
    key = ("closes", current_user_id, fetch_from.isoformat())
    if not _may_fetch(key):
        return None
    if background:
        schedule_history_refresh(
            ("benchmarks",) + key,
            lambda: _download_and_store_closes(current_user_id, fetch_from, today, key),
        )
        return None
    return _download_and_store_closes(current_user_id, fetch_from, today, key)


def _download_and_store_closes(current_user_id, fetch_from, today, key):
    future = _price_fetch_executor.submit(download_index_closes, fetch_from, today)
    try:
        closes, sources = future.result(timeout=PRICE_FETCH_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        logger.warning("Tempo limite ao buscar os indices de comparacao.")
        _forget_attempt(key)
        return None
    except Exception as exc:
        logger.warning(f"Indices de comparacao indisponiveis: {exc}")
        return None
    with get_db() as conn:
        for benchmark, points in closes.items():
            store_closes(conn, current_user_id, benchmark, points, sources.get(benchmark, "yfinance"))
    return sources


def start_ipca_fetch(start_date):
    """[(mes, variacao)] do BCB desde o mes de `start_date`, em segundo plano.

    O cache e o da renda fixa (`fixed_income.ipca_since()`), pelo TTL do historico."""
    return fixed_income._index_fetch_executor.submit(fixed_income.ipca_since, start_date)


# --- entrada ----------------------------------------------------------------------

def load_benchmarks(current_user_id, first_month, now=None):
    """Retornos mensais de cada indice desde `first_month` (um datetime no dia 1).

    {codigo: {"label", "monthly": {AAAA-MM: fracao}, "source", "error",
    "stored_since"}}. Um indice que falha nao derruba os outros: fica com
    `monthly` vazio e o motivo em `error`.
    """
    now = now or datetime.now()
    today = now.date()
    keys = []
    cursor = date(first_month.year, first_month.month, 1)
    while cursor <= today:
        keys.append(cursor.strftime("%Y-%m"))
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
    # O retorno do primeiro mes precisa do fechamento do mes anterior.
    since = subtract_months(date(first_month.year, first_month.month, 1), 1)

    # O IPCA (BCB) corre enquanto os fechamentos (yfinance) sao buscados; o
    # prazo de cada um conta do inicio, nao do fim do outro.
    ipca_future = start_ipca_fetch(date(first_month.year, first_month.month, 1))
    ipca_deadline = time.monotonic() + PRICE_FETCH_TIMEOUT_SECONDS
    # Com fechamentos guardados ha pouco, a tela nao espera o Yahoo: le o banco
    # e a busca nova corre em segundo plano (vale na proxima abertura).
    background = stored_closes_are_recent(current_user_id)
    fresh_sources = refresh_benchmark_closes(current_user_id, since, today, background=background) or {}

    result = {}
    try:
        ipca = ipca_future.result(timeout=max(0.0, ipca_deadline - time.monotonic()))
        result["IPCA"] = {"monthly": ipca_monthly_returns(ipca, keys), "source": "bcb", "error": None}
    except FutureTimeoutError:
        result["IPCA"] = {"monthly": {}, "source": None, "error": "Tempo limite ao buscar o IPCA no BCB."}
    except Exception as exc:
        logger.warning(f"IPCA indisponivel para a rentabilidade: {exc}")
        result["IPCA"] = {"monthly": {}, "source": None, "error": "O BCB não respondeu o IPCA."}

    with get_db() as conn:
        for benchmark in CLOSE_BENCHMARKS:
            closes = stored_closes(conn, current_user_id, benchmark, since)
            monthly = monthly_returns_from_closes(closes, keys)
            entry = {
                "monthly": monthly,
                "source": fresh_sources.get(benchmark) or ("cache" if closes else None),
                "error": None,
                "stored_since": closes[0][0].isoformat() if closes else None,
            }
            if not closes:
                entry["error"] = f"Sem cotação do {BENCHMARK_LABELS[benchmark]} nos provedores (yfinance/brapi)."
            result[benchmark] = entry

    for code, label in BENCHMARKS:
        result[code]["label"] = label
    return result


def benchmark_note(code, entry, window_keys, covered_keys):
    """Explicacao curta, em portugues, de um indice incompleto ou ausente."""
    if entry.get("error"):
        return entry["error"]
    if len(covered_keys) == len(window_keys):
        return None
    missing = [key for key in window_keys if key not in covered_keys]
    if code == "IPCA" and missing and missing == window_keys[-len(missing):]:
        first = datetime.strptime(missing[0], "%Y-%m")
        return f"IPCA a partir de {month_label(first)} ainda não divulgado pelo IBGE."
    if code in ("IFIX", "IDIV") and entry.get("stored_since"):
        since = date.fromisoformat(entry["stored_since"])
        return (
            f"Os provedores gratuitos não têm o histórico do {BENCHMARK_LABELS[code]}; "
            f"o app guarda o fechamento de cada mês desde {since.strftime('%d/%m/%Y')}, "
            f"então a comparação cobre {len(covered_keys)} de {len(window_keys)} meses."
        )
    return f"Cobre {len(covered_keys)} de {len(window_keys)} meses do período."
