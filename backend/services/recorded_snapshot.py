"""Como um lancamento gravado sozinho nasceu (044, 045): o snapshot.

Modulo baixo: nao importa services.inbox nem services.open_finance_inbox, para
os dois o usarem (inbox.absorb_recorded_side() decide "intocado" por aqui, e
open_finance_inbox reexporta tudo para quem ja chamava de la).

"Intocado" e decidido pelo snapshot, nunca por `needs_review`: revisar nao muda
conta, valor nem data, e a Fase 4 tira da revisao sozinha.
"""

import json

from db import utc_timestamp

TRANSACTION_SNAPSHOT_COLUMNS = (
    "account_id", "transfer_account_id", "amount", "date", "category_id", "description", "type",
    "share_mode", "share_others_amount", "share_person",
)
CARD_SNAPSHOT_COLUMNS = (
    "card_id", "amount", "purchase_date", "category_id", "description", "kind",
    "share_mode", "share_others_amount", "share_person",
)


def _snapshot_cents(value):
    return int(round(float(value) * 100))


def target_snapshot(conn, current_user_id, table, target_id):
    """O que o dono pode mudar num lancamento, como esta agora (None se nao
    existe): os campos, os comprovantes e se ja e ocorrencia de recorrencia.
    Na compra no cartao, todas as parcelas da compra (o client_id)."""
    if table == "transactions":
        row = conn.execute(
            f"SELECT {', '.join(TRANSACTION_SNAPSHOT_COLUMNS)}, transfer_amount FROM transactions WHERE id = ? AND user_id = ?",
            (target_id, current_user_id),
        ).fetchone()
        if not row:
            return None
        snapshot = {column: row[column] for column in TRANSACTION_SNAPSHOT_COLUMNS}
        snapshot["amount"] = _snapshot_cents(snapshot["amount"])
        if row["transfer_amount"] is not None:
            # Entre moedas (047); so quando existe, para os snapshots de antes
            # continuarem iguais.
            snapshot["transfer_amount"] = _snapshot_cents(row["transfer_amount"])
        snapshot["attachments"] = conn.execute(
            "SELECT COUNT(*) FROM transaction_attachments WHERE user_id = ? AND transaction_id = ?",
            (current_user_id, target_id),
        ).fetchone()[0]
    elif table == "cc_expenses":
        first = conn.execute(
            "SELECT client_id FROM cc_expenses WHERE id = ? AND user_id = ?", (target_id, current_user_id),
        ).fetchone()
        if not first:
            return None
        rows = conn.execute(
            f"""
            SELECT id, {', '.join(CARD_SNAPSHOT_COLUMNS)} FROM cc_expenses
            WHERE user_id = ? AND client_id = ? ORDER BY invoice_year, invoice_month, id
            """,
            (current_user_id, first["client_id"]),
        ).fetchall()
        snapshot = {"rows": [
            [_snapshot_cents(row[column]) if column == "amount" else row[column] for column in CARD_SNAPSHOT_COLUMNS]
            for row in rows
        ]}
        ids = [row["id"] for row in rows]
        snapshot["attachments"] = conn.execute(
            f"SELECT COUNT(*) FROM cc_expense_attachments WHERE user_id = ? AND cc_expense_id IN ({', '.join('?' for _ in ids)})",
            (current_user_id, *ids),
        ).fetchone()[0]
    else:
        return None
    snapshot["settled"] = conn.execute(
        "SELECT COUNT(*) FROM recurring_settlements WHERE user_id = ? AND target_table = ? AND target_id = ?",
        (current_user_id, table, target_id),
    ).fetchone()[0]
    return snapshot


def _dump(snapshot):
    return json.dumps(snapshot, sort_keys=True)


def _load(text):
    try:
        return json.loads(text) if text else None
    except (TypeError, ValueError):
        return None


def untouched(conn, current_user_id, row):
    """O lancamento que esta transacao da Pluggy gravou sozinha esta como nasceu."""
    if not row.get("auto_recorded_at") or not row.get("recorded_snapshot") or not row.get("target_id"):
        return False
    recorded = _load(row["recorded_snapshot"])
    if recorded is None:
        return False
    current = target_snapshot(conn, current_user_id, row["target_table"], row["target_id"])
    return current is not None and current == recorded


def snapshot_unchanged(conn, current_user_id, item):
    """O lancamento que o item (da notificacao) gravou esta como nasceu: o
    snapshot do item, sem olhar a revisao."""
    table, target_id = item.get("target_table"), item.get("target_id")
    recorded = _load(item.get("recorded_snapshot"))
    if recorded is None or not table or not target_id:
        return False
    return target_snapshot(conn, current_user_id, table, target_id) == recorded


def snapshot_amount_cents(snapshot_text, table):
    """O valor (centavos) com que o lancamento nasceu, ou None: na compra no
    cartao, so a de uma linha (1/1)."""
    snapshot = _load(snapshot_text)
    if not snapshot:
        return None
    if table == "transactions":
        return snapshot.get("amount")
    rows = snapshot.get("rows") or []
    if len(rows) != 1:
        return None
    return rows[0][CARD_SNAPSHOT_COLUMNS.index("amount")]


def mark_auto_recorded(conn, current_user_id, item_id, table, target_id, stamp=None):
    """As fontes da Pluggy de um item que o app gravou sozinho guardam como o
    lancamento nasceu. (A ocorrencia de recorrencia que a aprovacao deu ja esta no snapshot.)"""
    conn.execute(
        """
        UPDATE open_finance_transactions SET auto_recorded_at = ?, recorded_snapshot = ?, updated_at = ?
        WHERE user_id = ? AND item_id = ? AND role = 'SOURCE'
        """,
        (stamp or utc_timestamp(), _dump(target_snapshot(conn, current_user_id, table, target_id)), utc_timestamp(),
         current_user_id, item_id),
    )


def refresh_snapshots(conn, current_user_id, item_id, table, target_id):
    """O lancamento mudou pelo app (nao pelo dono): o snapshot das fontes da
    Pluggy do item e o do item (notificacao) passam a ser o de agora."""
    if not item_id or not table or not target_id:
        return
    snapshot = _dump(target_snapshot(conn, current_user_id, table, target_id))
    conn.execute(
        """
        UPDATE open_finance_transactions SET recorded_snapshot = ?, updated_at = ?
        WHERE user_id = ? AND item_id = ? AND role <> 'REMOVED' AND recorded_snapshot IS NOT NULL
        """,
        (snapshot, utc_timestamp(), current_user_id, item_id),
    )
    conn.execute(
        """
        UPDATE inbox_items SET recorded_snapshot = ?, updated_at = ?
        WHERE id = ? AND user_id = ? AND recorded_snapshot IS NOT NULL
        """,
        (snapshot, utc_timestamp(), item_id, current_user_id),
    )
