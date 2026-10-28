"""Conta investimento: o caixa da corretora hoje, em transito e depois (049).

O lancamento de uma compra ou venda fica na data da liquidacao
(`services/settlement.py`), entao o caixa se le direto do extrato da Corretora:

- `settled`: o saldo com o que ja liquidou ate hoje (o que a corretora mostra);
- `in_transit`: cada lancamento datado depois de hoje (operacao a liquidar,
  transferencia agendada) e cada provento anunciado com pagamento futuro;
- `expected`: `settled` + tudo em transito, o saldo depois que tudo liquidar.
"""

from dates import parse_iso_datetime
from money import rounded_money
from services import invoices
from services.accounts import account_balance_rows
from services.proceeds_cash import PROCEED_LABELS, portfolio_account_row, portfolio_since
from source_types import INVESTMENT_CASH_SOURCE_TYPE, INVESTMENT_PROCEED_SOURCE_TYPE
from validators import safe_float


def signed_rows_after(conn, current_user_id, account_id, after):
    """Lancamentos da conta datados depois de `after`, com o sinal do caixa."""
    rows = conn.execute(
        """
        SELECT id, date, description, type, amount, transfer_amount, account_id, transfer_account_id,
               source_type, source_id
        FROM transactions
        WHERE user_id = ? AND (account_id = ? OR transfer_account_id = ?) AND date > ?
        ORDER BY date, description
        """,
        (current_user_id, account_id, account_id, after),
    ).fetchall()
    signed = []
    for row in rows:
        amount = safe_float(row["amount"])
        if row["type"] == "INCOME":
            value = amount
        elif row["type"] == "EXPENSE":
            value = -amount
        elif row["type"] == "TRANSFER" and row["account_id"] == account_id:
            value = -amount
        elif row["type"] == "TRANSFER":
            value = safe_float(row["transfer_amount"], amount) if row["transfer_amount"] is not None else amount
        else:
            continue
        signed.append({
            "id": row["id"],
            "date": str(row["date"])[:10],
            "description": row["description"],
            "amount": rounded_money(value),
            "kind": "operation" if row["source_type"] == INVESTMENT_CASH_SOURCE_TYPE else (
                "proceed" if row["source_type"] == INVESTMENT_PROCEED_SOURCE_TYPE else "other"
            ),
            "investment_id": row["source_id"] if row["source_type"] == INVESTMENT_CASH_SOURCE_TYPE else None,
        })
    return signed


def settled_balance(conn, current_user_id, account_id, as_of):
    """Saldo da conta so com o que esta datado ate `as_of` (AAAA-MM-DD)."""
    row = next((r for r in account_balance_rows(conn, current_user_id) if r["id"] == account_id), None)
    if not row:
        return None
    later = sum(item["amount"] for item in signed_rows_after(conn, current_user_id, account_id, as_of))
    return rounded_money(safe_float(row["balance"]) - later)


def upcoming_proceeds(conn, current_user_id, account, today):
    """Proventos anunciados que ainda vao cair na Corretora (pagamento depois de hoje)."""
    since = portfolio_since(account)
    found = []
    for row in conn.execute(
        """
        SELECT p.id, p.proceeds_type, p.payment_date, p.net_amount, a.ticker
        FROM investment_proceeds p
        JOIN assets a ON a.id = p.asset_id AND a.user_id = p.user_id
        WHERE p.user_id = ? AND substr(p.payment_date, 1, 10) > ?
        ORDER BY p.payment_date, a.ticker
        """,
        (current_user_id, today),
    ).fetchall():
        amount = rounded_money(safe_float(row["net_amount"]))
        day = str(row["payment_date"])[:10]
        if amount <= 0 or day < since:
            continue
        label = PROCEED_LABELS.get(row["proceeds_type"], "Provento")
        found.append({
            "id": f"proceed:{row['id']}",
            "date": day,
            "description": f"{label}: {row['ticker'] or 'ativo'}",
            "amount": amount,
            "kind": "proceed",
            "investment_id": None,
        })
    return found


def pluggy_cash(conn, current_user_id, account_id, today):
    row = conn.execute(
        """
        SELECT a.balance, a.balance_at FROM open_finance_accounts a
        JOIN open_finance_items i ON i.id = a.of_item_id AND i.user_id = a.user_id
        WHERE a.user_id = ? AND a.account_id = ? AND i.archived_at IS NULL AND a.balance IS NOT NULL
        ORDER BY a.balance_at DESC LIMIT 1
        """,
        (current_user_id, account_id),
    ).fetchone()
    if not row:
        return None
    moment = parse_iso_datetime(row["balance_at"])
    # O dia do saldo da Pluggy (local), nunca depois de hoje.
    as_of = min(moment.astimezone().date().isoformat(), today) if moment else None
    app = settled_balance(conn, current_user_id, account_id, as_of) if as_of else None
    return {
        "balance": rounded_money(row["balance"]),
        "balance_at": row["balance_at"],
        "as_of": as_of,
        "app_balance": app,
        "difference": rounded_money(safe_float(row["balance"]) - app) if app is not None else None,
    }


def broker_settlement(conn, current_user_id, today=None):
    """O caixa da conta investimento, ou None sem Corretora."""
    account = portfolio_account_row(conn, current_user_id)
    if not account:
        return None
    today = (today or invoices.local_today()).isoformat()
    settled = settled_balance(conn, current_user_id, account["id"], today)
    in_transit = signed_rows_after(conn, current_user_id, account["id"], today)
    in_transit += upcoming_proceeds(conn, current_user_id, account, today)
    in_transit.sort(key=lambda item: (item["date"], item["description"] or ""))
    transit_total = rounded_money(sum(item["amount"] for item in in_transit))
    return {
        "account_id": account["id"],
        "account_name": account["name"],
        "today": today,
        "settled": settled,
        "in_transit": in_transit,
        "in_transit_total": transit_total,
        "expected": rounded_money(settled + transit_total),
        "pluggy": pluggy_cash(conn, current_user_id, account["id"], today),
    }
