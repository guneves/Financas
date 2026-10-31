"""O extrato da conta da corretora vira o caixa da Corretora no app (dono, 2026-10-30).

O saldo que a Pluggy da da conta BTG Investimentos e o extrato inteiro menos a
"Conta Remunerada" (provado no real: as linhas desde o zero, sem ela, dao o saldo
ao centavo). Entao cada linha tem um lugar:

- `sweep`: a aplicacao automatica (CONTA REMUNERADA ...) e o mesmo dinheiro em
  outra gaveta: COVERED, nunca no app;
- `trade`: o bruto do pregao (VISTA BRUTO) ja e o lancamento das operacoes, na
  liquidacao (services/settlement.py): COVERED;
- o resto (taxa, IR, renda fixa, cupom, cashback): um lancamento BROKER_STATEMENT,
  fora de despesa/receita como o resto do caixa da carteira. Um provento que o
  app ja tem (JCP calculado, cupom digitado) fica com o valor e o dia do banco;
  uma operacao digitada com o mesmo valor so e ligada, nunca duplicada.

Idempotente por `source_type` + `source_id` (o id da Pluggy).
"""

import re
from datetime import date, timedelta

from db import encode_metadata, utc_timestamp
from money import rounded_money
from open_finance_categories import plain_text
from services import proceeds_cash
from source_types import (
    BROKER_STATEMENT_SOURCE_TYPE,
    INVESTMENT_CASH_SOURCE_TYPE,
    INVESTMENT_PROCEED_SOURCE_TYPE,
)
from validators import safe_float

BROKER_LABEL = "Caixa da corretora"
ID_PREFIX = "broker:"
SWEEP_TEXT = re.compile(r"\bconta remunerada\b")
TRADE_TEXT = re.compile(r"\bvista bruto\b")
PROCEED_TEXT = re.compile(r"\b(juros s capital|dividendo|rendimento|cupom|amortiz)")
TICKER_TEXT = re.compile(r"\b[a-z]{4}\d{1,2}\b")
PROCEED_DAYS = 5
TWIN_DAYS = 3
# Um cupom digitado antes do extrato chegar difere do banco em poucos centavos.
PROCEED_TOLERANCE_CENTS = 5


def line_kind(description):
    """Puro: sweep, trade ou cash."""
    text = plain_text(description)
    if SWEEP_TEXT.search(text):
        return "sweep"
    if TRADE_TEXT.search(text):
        return "trade"
    return "cash"


def _cents(value):
    return int(round(safe_float(value) * 100))


def _shifted(date_text, days):
    return (date.fromisoformat(str(date_text)[:10]) + timedelta(days=days)).isoformat()


def _linked(conn, current_user_id, target_id, row_id):
    return conn.execute(
        """
        SELECT 1 FROM open_finance_transactions
        WHERE user_id = ? AND target_table = 'transactions' AND target_id = ? AND id <> ? AND role <> 'REMOVED'
        """,
        (current_user_id, target_id, row_id),
    ).fetchone() is not None


def _proceed_entry(conn, current_user_id, proceed_id):
    return conn.execute(
        "SELECT id FROM transactions WHERE user_id = ? AND source_type = ? AND source_id = ?",
        (current_user_id, INVESTMENT_PROCEED_SOURCE_TYPE, proceed_id),
    ).fetchone()


def _proceed_for_line(conn, current_user_id, row):
    """O provento do app que esta linha paga: pelo ticker do texto, senao pelo
    valor quase igual. Um por linha: o ja ligado a outra nao conta."""
    text = plain_text(row["description"])
    if row["direction"] != "IN" or not PROCEED_TEXT.search(text):
        return None
    found = TICKER_TEXT.search(text)
    ticker = found.group(0).upper() if found else None
    best = None
    for candidate in conn.execute(
        """
        SELECT p.id, p.gross_amount, p.tax_amount, p.net_amount, a.ticker
        FROM investment_proceeds p
        JOIN assets a ON a.id = p.asset_id AND a.user_id = p.user_id
        WHERE p.user_id = ? AND substr(p.payment_date, 1, 10) BETWEEN ? AND ?
        ORDER BY p.payment_date, p.id
        """,
        (current_user_id, _shifted(row["date"], -PROCEED_DAYS), _shifted(row["date"], PROCEED_DAYS)),
    ).fetchall():
        gap = abs(_cents(candidate["net_amount"]) - int(row["amount_cents"]))
        if (ticker and candidate["ticker"] != ticker) or (not ticker and gap > PROCEED_TOLERANCE_CENTS):
            continue
        entry = _proceed_entry(conn, current_user_id, candidate["id"])
        if entry and _linked(conn, current_user_id, entry["id"], row["id"]):
            continue
        if best is None or gap < best[0]:
            best = (gap, candidate)
    return best[1] if best else None


def _settle_proceed(conn, current_user_id, row, proceed):
    """O provento fica com o que o banco pagou: mesma aliquota, travado contra a
    sincronizacao. Devolve o lancamento dele, ou None (pago antes de a conta ser
    a da carteira: esse dinheiro entra como linha do extrato)."""
    net = rounded_money(int(row["amount_cents"]) / 100)
    gross = safe_float(proceed["gross_amount"])
    rate = safe_float(proceed["tax_amount"]) / gross if gross > 0 else 0
    new_gross = rounded_money(net / (1 - rate)) if 0 <= rate < 1 else net
    conn.execute(
        """
        UPDATE investment_proceeds
        SET gross_amount = ?, tax_amount = ?, net_amount = ?, payment_date = ?, sync_locked = 1, updated_at = ?
        WHERE id = ? AND user_id = ?
        """,
        (new_gross, rounded_money(new_gross - net), net, row["date"], utc_timestamp(), proceed["id"], current_user_id),
    )
    proceeds_cash.apply_paid_proceeds(conn, current_user_id)
    entry = _proceed_entry(conn, current_user_id, proceed["id"])
    return entry["id"] if entry else None


def _typed_twin(conn, current_user_id, row, account_id):
    """O lancamento de uma operacao digitada (renda fixa) com o mesmo valor."""
    kind = "EXPENSE" if row["direction"] == "OUT" else "INCOME"
    for candidate in conn.execute(
        """
        SELECT id FROM transactions
        WHERE user_id = ? AND account_id = ? AND source_type = ? AND type = ?
          AND CAST(ROUND(amount * 100) AS INTEGER) = ? AND date BETWEEN ? AND ?
        ORDER BY date, id
        """,
        (
            current_user_id, account_id, INVESTMENT_CASH_SOURCE_TYPE, kind, int(row["amount_cents"]),
            _shifted(row["date"], -TWIN_DAYS), _shifted(row["date"], TWIN_DAYS),
        ),
    ).fetchall():
        if not _linked(conn, current_user_id, candidate["id"], row["id"]):
            return candidate["id"]
    return None


def write_line(conn, current_user_id, row, account_id):
    entry_id = f"{ID_PREFIX}{row['id']}"
    conn.execute(
        """
        INSERT INTO transactions
        (id, user_id, account_id, amount, date, category, description, type, source_type, source_id, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET amount = excluded.amount, date = excluded.date, type = excluded.type
        """,
        (
            entry_id, current_user_id, account_id, rounded_money(int(row["amount_cents"]) / 100), row["date"],
            BROKER_LABEL, (row["description"] or BROKER_LABEL)[:120], "EXPENSE" if row["direction"] == "OUT" else "INCOME",
            BROKER_STATEMENT_SOURCE_TYPE, row["pluggy_transaction_id"], encode_metadata({"of_row": row["id"]}),
        ),
    )
    return entry_id


def settle_line(conn, current_user_id, row, account_id):
    """(papel, id do lancamento) de uma linha do extrato da corretora que nao e
    transferencia com o dono."""
    if line_kind(row["description"]) != "cash":
        return "COVERED", None
    proceed = _proceed_for_line(conn, current_user_id, row)
    entry = _settle_proceed(conn, current_user_id, row, proceed) if proceed else None
    return "MATCHED", (
        entry or _typed_twin(conn, current_user_id, row, account_id)
        or write_line(conn, current_user_id, row, account_id)
    )


def remove_line(conn, current_user_id, row):
    """A Pluggy nao tem mais a linha: sai o lancamento dela."""
    conn.execute(
        "DELETE FROM transactions WHERE id = ? AND user_id = ? AND source_type = ?",
        (row["target_id"], current_user_id, BROKER_STATEMENT_SOURCE_TYPE),
    )
