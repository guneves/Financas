"""Liquidacao das operacoes na conta da corretora (049).

O dinheiro de uma compra ou venda na B3 so sai ou entra no caixa da corretora
na liquidacao: D+2 dias uteis para acoes, FIIs, ETFs e BDRs (`STOCKS`,
`REIT`), D+1 para ativo no exterior, no dia para o resto (renda fixa,
Tesouro, cripto). O lancamento ligado a operacao fica na data da liquidacao,
com o valor liquidado de verdade quando o dono (ou a Pluggy) o informa
(`settlement_amount`, com taxas e a LIQ BOLSA); `settlement_date` no metadata
manda sobre a conta.

Um ETF de renda fixa (`market_catalog.FIXED_INCOME_ETFS`) liquida em D+1: o extrato
da BTG mostra AUPO11 vendido num dia e pago no seguinte.

Modulo puro: so datas e numeros, sem banco.
"""

from datetime import date, timedelta

from dates import parse_iso_date
from market_catalog import FIXED_INCOME_ETFS
from money import rounded_money
from validators import safe_float

SETTLEMENT_DATE_KEY = "settlement_date"
SETTLEMENT_AMOUNT_KEY = "settlement_amount"
B3_SETTLEMENT_DAYS = 2
FOREIGN_SETTLEMENT_DAYS = 1
FIXED_INCOME_ETF_SETTLEMENT_DAYS = 1
B3_SETTLED_CLASSES = {"STOCKS", "REIT"}

# Feriados nacionais fixos sem pregao nem liquidacao, mais 24 e 31/12 (a B3
# nao abre). Os moveis (Carnaval, Sexta-feira Santa, Corpus Christi) saem da Pascoa.
FIXED_HOLIDAYS = {(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 24), (12, 25), (12, 31)}


def easter(year):
    """Domingo de Pascoa (algoritmo de Meeus/Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def b3_holidays(year):
    sunday = easter(year)
    moving = {
        sunday - timedelta(days=48),  # segunda de Carnaval
        sunday - timedelta(days=47),  # terca de Carnaval
        sunday - timedelta(days=2),   # Sexta-feira Santa
        sunday + timedelta(days=60),  # Corpus Christi
    }
    return moving | {date(year, month, day) for month, day in FIXED_HOLIDAYS}


def is_business_day(day):
    return day.weekday() < 5 and day not in b3_holidays(day.year)


def add_business_days(day, count):
    current = day
    left = count
    while left > 0:
        current += timedelta(days=1)
        if is_business_day(current):
            left -= 1
    return current


def settlement_days(asset_class, currency="BRL", ticker=None):
    if asset_class not in B3_SETTLED_CLASSES:
        return 0
    if (currency or "BRL").upper() != "BRL":
        return FOREIGN_SETTLEMENT_DAYS
    if ticker in FIXED_INCOME_ETFS:
        return FIXED_INCOME_ETF_SETTLEMENT_DAYS
    return B3_SETTLEMENT_DAYS


def settlement_date(trade_date, asset_class, currency="BRL", metadata=None, ticker=None):
    """A data da liquidacao (AAAA-MM-DD): a do metadata, ou a conta pela classe."""
    explicit = parse_iso_date((metadata or {}).get(SETTLEMENT_DATE_KEY))
    if explicit:
        return explicit.strftime("%Y-%m-%d")
    parsed = parse_iso_date(trade_date)
    if not parsed:
        return trade_date
    return add_business_days(parsed.date(), settlement_days(asset_class, currency, ticker)).isoformat()


def settlement_amount(metadata):
    """O valor liquidado informado (positivo), ou None para usar o da operacao."""
    value = safe_float((metadata or {}).get(SETTLEMENT_AMOUNT_KEY), None)
    if value is None or value <= 0:
        return None
    return rounded_money(value)
