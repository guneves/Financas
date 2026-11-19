"""Conflitos que se resolvem sozinhos (automation-prompt 1.4, dono 2026-11-18).

O mutation guard (044) nunca muda nem apaga o lancamento que o dono mexeu: a
transacao da Pluggy fica com `conflict` e a Conferencia aponta. Ninguem mais
precisa resolver:

- `changed` (o banco mudou o valor de uma linha que o dono editou): passados
  CHANGED_WAIT_DAYS desde que apontou, o valor do banco vale — menos com
  comprovante, divisao, "Aconteceu" ou um valor que o dono digitou (o atual
  diferente do snapshot: a escolha explicita dele), e so na mesma direcao,
  numa despesa/receita ou numa compra 1/1 em aberto. A data fica (o conflito
  guarda so o valor do banco).
- `vanished` (a linha sumiu do banco e o dono a tinha mexido): sai so pela
  prova do saldo, a mesma das orfas (open_finance_orphans: velha o bastante,
  o banco ja falou depois, a diferenca banco - app e exatamente o conserto).
  So conta bancaria em reais, so despesa/receita, nunca a protegida.

Roda no fim do pull, depois das orfas. Cada resolucao vai para o registro
(auto_decisions `conflict_changed` / `conflict_vanished`, com o antes) e o log;
"Desfazer" volta o valor ou devolve a linha apagada.
"""

from datetime import timedelta

import money
from db import row_to_dict, utc_timestamp
from services import auto_decisions, inbox, open_finance_orphans
from services.recorded_snapshot import refresh_snapshots, snapshot_amount_cents

CHANGED_WAIT_DAYS = 7


def _protected_target(conn, current_user_id, table, target_id):
    """Comprovante, divisao ou "Aconteceu": o dono pos e nao recupera."""
    if table == "transactions":
        row = conn.execute(
            "SELECT share_mode FROM transactions WHERE id = ? AND user_id = ?", (target_id, current_user_id),
        ).fetchone()
        attachments = "SELECT 1 FROM transaction_attachments WHERE user_id = ? AND transaction_id = ? LIMIT 1"
        same = (current_user_id, target_id)
    else:
        row = conn.execute(
            "SELECT share_mode, client_id FROM cc_expenses WHERE id = ? AND user_id = ?", (target_id, current_user_id),
        ).fetchone()
        attachments = """
            SELECT 1 FROM cc_expense_attachments a JOIN cc_expenses e ON e.id = a.cc_expense_id AND e.user_id = a.user_id
            WHERE a.user_id = ? AND e.client_id = ? LIMIT 1
        """
        same = (current_user_id, row["client_id"] if row else None)
    if not row or row["share_mode"]:
        return True
    if conn.execute(attachments, same).fetchone():
        return True
    return conn.execute(
        "SELECT 1 FROM open_finance_confirmed WHERE user_id = ? AND target_table = ? AND target_id = ?",
        (current_user_id, table, target_id),
    ).fetchone() is not None


def _snapshot_text(conn, current_user_id, row):
    if row.get("recorded_snapshot"):
        return row["recorded_snapshot"]
    if row.get("item_id"):
        item = inbox.fetch_item(conn, current_user_id, row["item_id"])
        if item and item["recorded_snapshot"]:
            return item["recorded_snapshot"]
    return None


def _current_cents(conn, current_user_id, table, target_id):
    if table == "transactions":
        target = conn.execute(
            "SELECT amount, type, source_type FROM transactions WHERE id = ? AND user_id = ?",
            (target_id, current_user_id),
        ).fetchone()
        if not target or target["type"] not in ("EXPENSE", "INCOME"):
            return None
        return money.to_cents(target["amount"])
    rows = conn.execute(
        """
        SELECT amount, status, kind FROM cc_expenses
        WHERE user_id = ? AND client_id = (SELECT client_id FROM cc_expenses WHERE id = ? AND user_id = ?)
        """,
        (current_user_id, target_id, current_user_id),
    ).fetchall()
    if len(rows) != 1 or rows[0]["status"] != "OPEN" or rows[0]["kind"] == "REFUND":
        return None
    return money.to_cents(rows[0]["amount"])


def _ripe_changed(row, today):
    stamp = str(row.get("conflict_at") or "")[:10]
    return bool(stamp) and stamp <= (today - timedelta(days=CHANGED_WAIT_DAYS)).isoformat()


def resolve_changed(conn, current_user_id, of_item_id, today):
    """O valor do banco vale, passado o prazo. Devolve quantos."""
    resolved = 0
    rows = conn.execute(
        """
        SELECT o.* FROM open_finance_transactions o
        JOIN open_finance_accounts a ON a.id = o.of_account_id AND a.user_id = o.user_id
        WHERE o.user_id = ? AND a.of_item_id = ? AND o.conflict = 'changed' AND o.role <> 'REMOVED'
          AND o.target_id IS NOT NULL AND o.conflict_amount_cents IS NOT NULL AND o.conflict_direction = o.direction
        ORDER BY o.date, o.id
        """,
        (current_user_id, of_item_id),
    ).fetchall()
    for entry in rows:
        row = row_to_dict(entry)
        table, target_id = row["target_table"], row["target_id"]
        if not _ripe_changed(row, today):
            continue
        if auto_decisions.was_undone(conn, current_user_id, auto_decisions.CONFLICT_CHANGED, table, target_id):
            continue
        current = _current_cents(conn, current_user_id, table, target_id)
        if current is None or _protected_target(conn, current_user_id, table, target_id):
            continue
        born = snapshot_amount_cents(_snapshot_text(conn, current_user_id, row), table)
        if born is None or int(born) != current:
            continue  # sem snapshot (o digitado ligado) ou valor que o dono digitou
        bank = int(row["conflict_amount_cents"])
        amount = money.from_cents(bank)
        if table == "transactions":
            conn.execute("UPDATE transactions SET amount = ? WHERE id = ? AND user_id = ?",
                         (amount, target_id, current_user_id))
        else:
            conn.execute("UPDATE cc_expenses SET amount = ? WHERE id = ? AND user_id = ?",
                         (amount, target_id, current_user_id))
        conn.execute(
            """
            UPDATE open_finance_transactions
            SET amount_cents = ?, conflict = NULL, conflict_amount_cents = NULL, conflict_at = NULL,
                conflict_direction = NULL, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (bank, utc_timestamp(), row["id"], current_user_id),
        )
        if row.get("item_id"):
            item = inbox.fetch_item(conn, current_user_id, row["item_id"])
            if item:
                inbox.save_item(conn, current_user_id, inbox.item_dict(item), {"amount": amount})
            refresh_snapshots(conn, current_user_id, row["item_id"], table, target_id)
        auto_decisions.record(
            conn, current_user_id, auto_decisions.CONFLICT_CHANGED, table, target_id,
            {"before_cents": current, "after_cents": bank, "item_id": row.get("item_id"),
             "of_transaction_id": row["id"], "date": row["date"]},
        )
        resolved += 1
    return resolved


def _vanished_rows(conn, current_user_id, account_id):
    """Os lancamentos da conta que so uma transacao sumida (`vanished`) da
    Pluggy sustentava, como as orfas de open_finance_orphans.notified_rows()."""
    rows = conn.execute(
        """
        SELECT t.id, t.type, t.amount, t.date, t.created_at, t.share_mode,
               o.id AS of_id, o.item_id, o.recorded_snapshot AS of_snapshot
        FROM open_finance_transactions o
        JOIN transactions t ON t.id = o.target_id AND t.user_id = o.user_id
        WHERE o.user_id = ? AND o.conflict = 'vanished' AND o.role <> 'REMOVED' AND o.target_table = 'transactions'
          AND t.account_id = ? AND t.type IN ('EXPENSE', 'INCOME')
        ORDER BY t.date, t.created_at, t.id
        """,
        (current_user_id, account_id),
    ).fetchall()
    found = []
    for entry in rows:
        row = dict(entry)
        if inbox.pluggy_claimed(conn, current_user_id, "transactions", row["id"]):
            continue
        row["recorded_snapshot"] = row.pop("of_snapshot") or _snapshot_text(conn, current_user_id, row)
        found.append(row)
    return found


def _remove_vanished(conn, current_user_id, row):
    full = row_to_dict(conn.execute(
        "SELECT * FROM transactions WHERE id = ? AND user_id = ?", (row["id"], current_user_id),
    ).fetchone())
    if not full:
        return False
    conn.execute(
        "DELETE FROM recurring_settlements WHERE user_id = ? AND target_table = 'transactions' AND target_id = ?",
        (current_user_id, row["id"]),
    )
    conn.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (row["id"], current_user_id))
    conn.execute(
        """
        UPDATE open_finance_transactions SET role = 'REMOVED', target_table = NULL, target_id = NULL, updated_at = ?
        WHERE id = ? AND user_id = ?
        """,
        (utc_timestamp(), row["of_id"], current_user_id),
    )
    if row.get("item_id"):
        item = inbox.fetch_item(conn, current_user_id, row["item_id"])
        if item and item["target_id"] == row["id"]:
            inbox.save_item(
                conn, current_user_id, inbox.item_dict(item),
                {"state": inbox.REMOVED, "reason": "vanished", "target_table": None, "target_id": None,
                 "decided_at": utc_timestamp()},
            )
    auto_decisions.record(
        conn, current_user_id, auto_decisions.CONFLICT_VANISHED, "transactions", row["id"],
        {"row": full, "of_transaction_id": row["of_id"], "item_id": row.get("item_id")},
    )
    return True


def resolve_vanished(conn, current_user_id, of_item_id, today):
    """A linha sumida sai so pela prova do saldo. Devolve quantas."""
    today_text = today.strftime("%Y-%m-%d") if hasattr(today, "strftime") else str(today)[:10]
    removed = 0
    for of_account in open_finance_orphans.bank_accounts(conn, current_user_id, of_item_id):
        candidates = [
            row for row in _vanished_rows(conn, current_user_id, of_account["account_id"])
            if open_finance_orphans.ripe(conn, current_user_id, row, today_text)
            and not open_finance_orphans.protected(conn, current_user_id, row)
        ]
        if not candidates:
            continue
        difference = open_finance_orphans.account_difference(conn, current_user_id, of_account, today_text)
        for row in open_finance_orphans.choose(candidates, difference):
            removed += 1 if _remove_vanished(conn, current_user_id, row) else 0
    return removed


def resolve(conn, current_user_id, of_item_id, today):
    return {
        "changed": resolve_changed(conn, current_user_id, of_item_id, today),
        "vanished": resolve_vanished(conn, current_user_id, of_item_id, today),
    }


def undo_changed(conn, current_user_id, decision):
    """O valor volta ao de antes (se ainda e o do banco) e o conflito volta a
    ser apontado."""
    detail, table, target_id = decision["detail"], decision["table"], decision["target_id"]
    current = _current_cents(conn, current_user_id, table, target_id)
    if current is None or current != detail.get("after_cents"):
        return
    if table not in ("transactions", "cc_expenses"):
        return
    amount = money.from_cents(int(detail["before_cents"]))
    conn.execute(f"UPDATE {table} SET amount = ? WHERE id = ? AND user_id = ?", (amount, target_id, current_user_id))
    if detail.get("item_id"):
        refresh_snapshots(conn, current_user_id, detail["item_id"], table, target_id)
    if detail.get("of_transaction_id"):
        conn.execute(
            """
            UPDATE open_finance_transactions SET conflict = 'changed', conflict_amount_cents = ?, conflict_at = ?,
                   updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (detail["after_cents"], utc_timestamp(), utc_timestamp(), detail["of_transaction_id"], current_user_id),
        )


def undo_vanished(conn, current_user_id, decision):
    """A linha apagada volta, como era (mesma id); fica do dono, sem a Pluggy."""
    row = decision["detail"].get("row") or {}
    if not row.get("id") or row.get("user_id") != current_user_id:
        return
    if conn.execute("SELECT 1 FROM transactions WHERE id = ? AND user_id = ?", (row["id"], current_user_id)).fetchone():
        return
    columns = [name for name in row]
    conn.execute(
        f"INSERT INTO transactions ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
        [row[name] for name in columns],
    )

