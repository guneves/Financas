"""As compras no debito de cada cartao, para a tela Cartoes (049).

Uma compra no debito (041) e uma despesa comum na conta do cartao: mexe no
saldo da conta, nunca numa fatura. Aqui elas so se agrupam sob o cartao que as
fez, para aparecerem na mesma tela das compras no credito.

- `transactions.card_id` diz o cartao (o "+ Novo" e o Aprovar o gravam).
- Um cartao so debito (o Flash) tambem lista as despesas sem cartao da conta
  dele, desde que nenhum outro cartao debite dessa conta: as compras gravadas
  antes de 049 e as que chegaram sem dizer o cartao. Um cartao com credito e
  debito numa conta corrente lista so as marcadas (a conta tem Pix, boleto...).
- O pagamento de fatura nunca e compra no debito.

A janela e o mes corrente e o anterior; `month_total` e o do mes corrente.
"""

from decimal import Decimal

from money import rounded_money
from source_types import INVOICE_PAYMENT_SOURCE_TYPES

LIST_LIMIT = 200


def window_start(today):
    """O primeiro dia do mes anterior a `today` (AAAA-MM-DD)."""
    year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    return f"{year:04d}-{month:02d}-01"


def debit_cards(conn, current_user_id):
    """Os cartoes ativos com a funcao debito, por nome."""
    return conn.execute(
        """
        SELECT c.id, c.name, c.credit_enabled, c.debit_account_id, a.name AS account_name
        FROM credit_cards c
        JOIN accounts a ON a.id = c.debit_account_id AND a.user_id = c.user_id
        WHERE c.user_id = ? AND c.archived_at IS NULL
        ORDER BY c.name
        """,
        (current_user_id,),
    ).fetchall()


def _serialize(row):
    return {
        "id": row["id"],
        "date": row["date"],
        "description": row["description"],
        "category": row["category"],
        "category_id": row["category_id"],
        "amount": rounded_money(row["amount"]),
        "account_id": row["account_id"],
        "attachment_count": int(row["attachment_count"] or 0),
        "needs_review": int(row["needs_review"] or 0),
        "share_mode": row["share_mode"],
        "share_person": row["share_person"],
        "share_others_amount": rounded_money(row["share_others_amount"]) if row["share_others_amount"] is not None else None,
        "linked": bool(row["card_id"]),
    }


def build_debit_purchases(conn, current_user_id, today):
    """[{card_id, card_name, credit_enabled, account_id, account_name,
    month_total, purchases}] para GET /api/cc-invoices."""
    cards = debit_cards(conn, current_user_id)
    if not cards:
        return []
    accounts_in_use = {}
    for card in cards:
        accounts_in_use[card["debit_account_id"]] = accounts_in_use.get(card["debit_account_id"], 0) + 1

    since = window_start(today)
    month_prefix = today.strftime("%Y-%m")
    payment_types = sorted(INVOICE_PAYMENT_SOURCE_TYPES)
    payment_placeholders = ",".join("?" for _ in payment_types)
    result = []
    for card in cards:
        # So debito e dono unico da conta: as despesas sem cartao dela tambem.
        unlinked = not card["credit_enabled"] and accounts_in_use[card["debit_account_id"]] == 1
        rows = conn.execute(
            f"""
            SELECT t.*,
                (SELECT COUNT(*) FROM transaction_attachments ta
                 WHERE ta.user_id = t.user_id AND ta.transaction_id = t.id) AS attachment_count
            FROM transactions t
            WHERE t.user_id = ? AND t.type = 'EXPENSE' AND t.date >= ?
              AND COALESCE(t.source_type, '') NOT IN ({payment_placeholders})
              AND (t.card_id = ? OR (? AND t.card_id IS NULL AND t.account_id = ?))
            ORDER BY t.date DESC, t.created_at DESC, t.id DESC
            LIMIT ?
            """,
            (
                current_user_id, since, *payment_types, card["id"], 1 if unlinked else 0,
                card["debit_account_id"], LIST_LIMIT,
            ),
        ).fetchall()
        month_total = sum(
            (Decimal(str(row["amount"] or 0)) for row in rows if str(row["date"]).startswith(month_prefix)),
            Decimal("0"),
        )
        result.append({
            "card_id": card["id"],
            "card_name": card["name"],
            "credit_enabled": bool(card["credit_enabled"]),
            "account_id": card["debit_account_id"],
            "account_name": card["account_name"],
            "since": since,
            "month_total": rounded_money(month_total),
            "purchases": [_serialize(row) for row in rows],
        })
    return result
