"""O dono resolve uma diferenca da Conferencia (dono, 2026-10-30).

A Conferencia (services/open_finance_check.py) so aponta. Aqui estao os dois
botoes de cada linha dela:

- **Lancar** (`record_bank_row()`): um movimento so no banco vira lancamento, na
  conta ou no cartao mapeado: a transferencia de uma ponta so vira despesa/receita
  pelo lado que o banco viu, e nasce a revisar como o que grava sozinho;
- **Aconteceu** (`confirm_app_row()`): um lancamento que o banco nao mostra fica,
  porque o dono diz que foi feito. Sai de "so no app" e fica listado em
  `confirmed`; `undo` devolve.
"""

from db import row_to_dict
from services import inbox, inbox_decisions, open_finance_inbox, review
from services.inbox_defaults import fill_defaults
from validators import ValidationError

TABLES = ("transactions", "cc_expenses")
CLOSED_ROLES = ("COVERED", "REMOVED", "INVOICE_PAYMENT")


def _bank_row(conn, current_user_id, row_id):
    row = conn.execute(
        "SELECT * FROM open_finance_transactions WHERE id = ? AND user_id = ?", (row_id, current_user_id),
    ).fetchone()
    if not row:
        raise LookupError("Movimento nao encontrado.")
    return row_to_dict(row)


def _open_item(conn, current_user_id, row, account):
    """O item pendente deste movimento: o recusado volta, sem item abre um."""
    item = inbox.fetch_item(conn, current_user_id, row["item_id"]) if row["item_id"] else None
    if item and item["state"] == inbox.DENIED and row["role"] == inbox.SOURCE:
        inbox.save_item(
            conn, current_user_id, inbox.item_dict(item), {"state": inbox.PENDING, "decided_at": None, "reason": "restored"},
        )
        return inbox.fetch_item(conn, current_user_id, item["id"])
    if item and item["state"] == inbox.PENDING:
        return item
    open_finance_inbox.new_item_for_row(conn, current_user_id, row, account)
    fresh = open_finance_inbox._by_id(conn, current_user_id, row["id"])
    return inbox.fetch_item(conn, current_user_id, fresh["item_id"])


def _single_type(conn, current_user_id, row, item, account):
    """A transferencia que so tem esta ponta vira despesa/receita dela."""
    if item["entry_type"] != "TRANSFER" or (item["account_id"] and item["transfer_account_id"]):
        return inbox.fetch_item(conn, current_user_id, item["id"])
    entry_type = "EXPENSE" if row["direction"] == "OUT" else "INCOME"
    name, category_id = open_finance_inbox.category_for_row(
        conn, current_user_id, row, entry_type, item["amount"], account["account_id"],
    )
    changes = {
        "entry_type": entry_type, "direction": row["direction"], "account_id": account["account_id"],
        "transfer_account_id": None, "category": name, "category_id": category_id, "reason": "external_transfer",
        "guessed": [],
    }
    changes["needs"] = inbox.recompute_needs({**item, **changes})
    inbox.save_item(conn, current_user_id, item, changes)
    return inbox.fetch_item(conn, current_user_id, item["id"])


def record_bank_row(conn, current_user_id, row_id):
    """Lanca um movimento so no banco. Devolve {target_table, target_id}."""
    row = _bank_row(conn, current_user_id, row_id)
    if row["role"] in CLOSED_ROLES or row["target_id"]:
        raise ValidationError("Este movimento nao precisa de lancamento.")
    account = open_finance_inbox.fetch_account(conn, current_user_id, row["of_account_id"])
    if not account or account["ignored_at"] or not open_finance_inbox.mapped_target(account):
        raise ValidationError("Escolha o destino desta conta antes de lancar.")
    item = _single_type(
        conn, current_user_id, row, inbox.item_dict(_open_item(conn, current_user_id, row, account)), account,
    )
    fresh = inbox.item_dict(item)
    changes = fill_defaults(conn, current_user_id, fresh)
    if changes is None:
        raise ValidationError("Falta informacao para lancar: resolva em Revisar.")
    if changes:
        inbox.save_item(conn, current_user_id, fresh, changes)
        fresh = inbox.item_dict(inbox.fetch_item(conn, current_user_id, fresh["id"]))
    decided = inbox_decisions.approve_item(
        conn, current_user_id, fresh["id"], {"version": fresh["version"], "remember": False},
    )
    review.mark_for_review(conn, current_user_id, decided["target_table"], decided["target_id"])
    return {"target_table": decided["target_table"], "target_id": decided["target_id"]}


def confirm_app_row(conn, current_user_id, table, target_id, undo=False):
    """Marca (ou desmarca, com `undo`) um lancamento so no app como acontecido."""
    if table not in TABLES:
        raise ValidationError("Lancamento invalido.")
    if undo:
        conn.execute(
            "DELETE FROM open_finance_confirmed WHERE user_id = ? AND target_table = ? AND target_id = ?",
            (current_user_id, table, target_id),
        )
        return
    if not conn.execute(f"SELECT 1 FROM {table} WHERE id = ? AND user_id = ?", (target_id, current_user_id)).fetchone():
        raise LookupError("Lancamento nao encontrado.")
    conn.execute(
        "INSERT OR IGNORE INTO open_finance_confirmed (user_id, target_table, target_id) VALUES (?, ?, ?)",
        (current_user_id, table, target_id),
    )
