"""Cambio: PTAX de venda do BCB, guardada por dia em `fx_rates` (018).

`rate_on(conn, user, moeda, data)` devolve quantos reais vale uma unidade da
moeda na data (ou no ultimo dia util antes dela: a PTAX nao sai em fim de
semana e feriado). O que falta no banco e buscado no SGS uma vez e guardado.
Sem rede, vale o ultimo valor guardado; sem nenhum, FxUnavailable.

Real (BRL) e sempre 1: quem chama nao precisa tratar o caso.
"""

import threading
import time
from datetime import date, datetime, timedelta

from applog import get_logger
from dates import parse_iso_date
from money import rounded_money
from services.fixed_income import fetch_bcb_window
from validators import safe_float

logger = get_logger(__name__)

BASE_CURRENCY = "BRL"
# SGS: PTAX de venda, BRL por unidade.
BCB_FX_SERIES = {"USD": 1, "EUR": 21619, "GBP": 21623}
SUPPORTED_CURRENCIES = {BASE_CURRENCY, *BCB_FX_SERIES}
CURRENCY_SYMBOLS = {"BRL": "R$", "USD": "US$", "EUR": "€", "GBP": "£"}
# Janela buscada quando a data pedida nao esta no banco: cobre feriados longos.
LOOKBACK_DAYS = 10
# O SGS limita cada consulta a 10 anos.
MAX_WINDOW_DAYS = 3650


# Sem rede, cada abertura da carteira tentaria o BCB de novo (e esperaria o
# timeout). Uma tentativa por moeda a cada RETRY_SECONDS basta.
RETRY_SECONDS = 1800
_attempts = {}
_attempts_lock = threading.Lock()


def _may_fetch(key):
    now = time.monotonic()
    with _attempts_lock:
        last = _attempts.get(key)
        if last is not None and now - last < RETRY_SECONDS:
            return False
        _attempts[key] = now
        return True


def reset_fetch_throttle():
    """Para os testes."""
    with _attempts_lock:
        _attempts.clear()


class FxUnavailable(RuntimeError):
    """Nenhum cambio para a moeda: nem no banco, nem no BCB."""


def normalize_currency(value):
    return str(value or BASE_CURRENCY).strip().upper() or BASE_CURRENCY


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = parse_iso_date(value)
    return parsed.date() if parsed else date.today()


def _stored_rate(conn, current_user_id, currency, on_date):
    return conn.execute(
        """
        SELECT rate_date, rate FROM fx_rates
        WHERE user_id = ? AND currency = ? AND rate_date <= ?
        ORDER BY rate_date DESC LIMIT 1
        """,
        (current_user_id, currency, on_date.isoformat()),
    ).fetchone()


def fetch_and_store(conn, current_user_id, currency, start, end):
    """Busca a PTAX de [start, end] no BCB e guarda. Devolve quantos dias vieram."""
    series = BCB_FX_SERIES[currency]
    stored = 0
    window_start = start
    while window_start <= end:
        window_end = min(window_start + timedelta(days=MAX_WINDOW_DAYS - 1), end)
        for row in fetch_bcb_window(series, datetime.combine(window_start, datetime.min.time()),
                                    datetime.combine(window_end, datetime.min.time())):
            rate = safe_float(row.get("valor"), None)
            if not rate or rate <= 0:
                continue
            rate_date = datetime.strptime(row["data"], "%d/%m/%Y").date().isoformat()
            conn.execute(
                """
                INSERT INTO fx_rates (user_id, currency, rate_date, rate)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, currency, rate_date) DO UPDATE SET rate = excluded.rate
                """,
                (current_user_id, currency, rate_date, rate),
            )
            stored += 1
        window_start = window_end + timedelta(days=1)
    return stored


def rate_on(conn, current_user_id, currency, on_date=None):
    """BRL por unidade de `currency` em `on_date` (ultimo dia util ate ela)."""
    currency = normalize_currency(currency)
    if currency == BASE_CURRENCY:
        return 1.0
    if currency not in BCB_FX_SERIES:
        raise FxUnavailable(f"Moeda sem cambio configurado: {currency}.")
    target = min(_as_date(on_date), date.today())

    row = _stored_rate(conn, current_user_id, currency, target)
    # O guardado serve se for do proprio dia, ou de ate 4 dias antes quando o
    # dia pedido ja passou (fim de semana + feriado). Para hoje, tenta o BCB:
    # a PTAX do dia sai a tarde.
    fresh_enough = row and (
        row["rate_date"] == target.isoformat()
        or (target < date.today() and (target - _as_date(row["rate_date"])).days <= 4)
    )
    if fresh_enough:
        return safe_float(row["rate"])

    if _may_fetch((current_user_id, currency, target.isoformat())):
        try:
            fetch_and_store(conn, current_user_id, currency, target - timedelta(days=LOOKBACK_DAYS), target)
        except Exception as exc:  # rede, BCB fora do ar: cai no guardado
            logger.warning(f"PTAX de {currency} indisponivel no BCB: {exc}", extra={"currency": currency})
    row = _stored_rate(conn, current_user_id, currency, target)
    if not row:
        raise FxUnavailable(f"Sem cotacao do {currency} ate {target.isoformat()} (BCB indisponivel).")
    return safe_float(row["rate"])


def monthly_rates(conn, current_user_id, currency, month_keys):
    """{AAAA-MM: cambio do ultimo dia util do mes} (mes corrente: hoje)."""
    currency = normalize_currency(currency)
    if currency == BASE_CURRENCY or not month_keys:
        return {key: 1.0 for key in month_keys}
    first = min(month_keys)
    start = date(int(first[:4]), int(first[5:7]), 1)
    have = conn.execute(
        "SELECT MIN(rate_date) AS first_date FROM fx_rates WHERE user_id = ? AND currency = ?",
        (current_user_id, currency),
    ).fetchone()
    missing_history = not have or not have["first_date"] or have["first_date"] > start.isoformat()
    if missing_history and _may_fetch((current_user_id, currency, "monthly", start.isoformat())):
        try:
            fetch_and_store(conn, current_user_id, currency, start - timedelta(days=LOOKBACK_DAYS), date.today())
        except Exception as exc:
            logger.warning(f"Serie mensal de {currency} indisponivel: {exc}", extra={"currency": currency})
    rates = {}
    for key in month_keys:
        year, month = int(key[:4]), int(key[5:7])
        next_month = date(year + (month == 12), month % 12 + 1, 1)
        month_end = min(next_month - timedelta(days=1), date.today())
        row = _stored_rate(conn, current_user_id, currency, month_end)
        rates[key] = safe_float(row["rate"]) if row else None
    return rates


def with_balance_in_brl(conn, current_user_id, item):
    """Conta em moeda estrangeira: saldo tambem em reais, pela PTAX de hoje.

    O consolidado soma balance_brl; sem cambio disponivel, ele fica de fora
    (None) e a tela avisa, em vez de somar dolar como real.
    """
    currency = normalize_currency(item.get("currency"))
    if currency == BASE_CURRENCY:
        item["balance_brl"] = item.get("balance")
        return item
    try:
        rate = rate_on(conn, current_user_id, currency)
        item["fx_rate"] = rate
        item["balance_brl"] = rounded_money(safe_float(item.get("balance")) * rate)
    except FxUnavailable:
        item["fx_rate"] = None
        item["balance_brl"] = None
    return item
