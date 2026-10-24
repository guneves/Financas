"""Paginas do extrato: `GET /api/transactions?limit=N&cursor=...`.

Sem `limit` a rota devolve a lista inteira, como sempre. Com ele, devolve no
maximo N linhas por pagina (keyset, nunca OFFSET), `count` (linhas do filtro
todo) e os totais do filtro todo:
- `totals`: entrou, saiu e investido (aporte menos resgate) de todas as linhas
  do filtro, nao so da pagina; transferencia nao entra.
- `day_totals`: entrou menos saiu de cada dia que aparece na pagina, sobre o
  dia inteiro — um dia partido entre duas paginas mostra o mesmo total nas duas.

A ordem e `date DESC, created_at DESC, id DESC`; o cursor e o base64 da
ultima linha `(date, created_at, id)`.
"""

import base64
import binascii
import re
from decimal import Decimal

from money import rounded_money
from source_types import INVESTMENT_SOURCE_TYPES
from validators import ValidationError

MAX_PAGE_LIMIT = 500
PAGE_ORDER = "date DESC, COALESCE(created_at, '') DESC, id DESC"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def encode_cursor(row):
    raw = "|".join([row["date"] or "", row["created_at"] or "", row["id"]])
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_cursor(value):
    try:
        raw = base64.urlsafe_b64decode(value.encode("ascii")).decode("utf-8")
    except (binascii.Error, UnicodeError, ValueError):
        raise ValidationError("Cursor invalido.")
    parts = raw.split("|")
    if len(parts) != 3 or not _DATE_RE.match(parts[0]) or not parts[2]:
        raise ValidationError("Cursor invalido.")
    return parts


def parse_page_args(args):
    """(limit, cursor) quando a busca pede paginas; None quando nao pede."""
    raw_limit = args.get("limit")
    if raw_limit is None or str(raw_limit).strip() == "":
        if args.get("cursor"):
            raise ValidationError("Cursor sem limite.")
        return None
    try:
        limit = int(str(raw_limit).strip())
    except ValueError:
        raise ValidationError(f"Limite deve ser um numero de 1 a {MAX_PAGE_LIMIT}.")
    if limit < 1 or limit > MAX_PAGE_LIMIT:
        raise ValidationError(f"Limite deve ser um numero de 1 a {MAX_PAGE_LIMIT}.")
    cursor = str(args.get("cursor") or "").strip()
    return limit, (decode_cursor(cursor) if cursor else None)


def cursor_clause(cursor):
    """WHERE das linhas depois do cursor, na ordem da pagina."""
    date, created_at, item_id = cursor
    return (
        "(date < ? OR (date = ? AND COALESCE(created_at, '') < ?)"
        " OR (date = ? AND COALESCE(created_at, '') = ? AND id < ?))",
        [date, date, created_at, date, created_at, item_id],
    )


def _amount(row):
    return Decimal(str(row["amount"] or 0))


def statement_totals(rows):
    """Os totais do extrato (o statementTotals do Extrato.jsx), em Decimal."""
    income = expense = investment = Decimal("0")
    for row in rows:
        amount = _amount(row)
        is_investment = row["source_type"] in INVESTMENT_SOURCE_TYPES
        if row["type"] == "INCOME":
            if is_investment:
                investment -= amount
            else:
                income += amount
        elif row["type"] == "EXPENSE":
            if is_investment:
                investment += amount
            else:
                expense += amount
    return {
        "income": rounded_money(income),
        "expense": rounded_money(expense),
        "investment": rounded_money(investment),
    }


def day_totals(rows, dates):
    """Entrou menos saiu de cada dia em `dates` (o groupByDay do Extrato.jsx)."""
    totals = {date: Decimal("0") for date in dates}
    for row in rows:
        if row["date"] not in totals:
            continue
        if row["type"] == "INCOME":
            totals[row["date"]] += _amount(row)
        elif row["type"] == "EXPENSE":
            totals[row["date"]] -= _amount(row)
    return {date: rounded_money(value) for date, value in totals.items()}


def fetch_page(conn, where, params, limit, cursor, select_sql):
    """Uma pagina do extrato: as linhas, o proximo cursor e os totais do filtro."""
    page_where, page_params = where, list(params)
    if cursor:
        extra, extra_params = cursor_clause(cursor)
        page_where = f"{where} AND {extra}"
        page_params += extra_params
    rows = conn.execute(
        f"{select_sql} WHERE {page_where} ORDER BY {PAGE_ORDER} LIMIT ?",
        page_params + [limit + 1],
    ).fetchall()
    has_more = len(rows) > limit
    rows = rows[:limit]
    summary_rows = conn.execute(
        f"SELECT date, type, amount, source_type FROM transactions WHERE {where}",
        params,
    ).fetchall()
    dates = list(dict.fromkeys(row["date"] for row in rows))
    return {
        "rows": rows,
        "next_cursor": encode_cursor(rows[-1]) if has_more and rows else None,
        "count": len(summary_rows),
        "totals": statement_totals(summary_rows),
        "day_totals": day_totals(summary_rows, dates),
    }
