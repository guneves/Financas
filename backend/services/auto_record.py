"""Gravar sozinho (045, dono 2026-10-27): a notificacao vira lancamento na hora.

Dono, 2026-10-30: so o Flash ainda chega por notificacao (os bancos vem pela
Pluggy; services/inbox.py responde `ignored` ao resto). O gasto que vira um item
(pareamento do app do Flash com o Samsung Wallet) e gravado logo depois, pela
mesma aprovacao da tela (`inbox_decisions.approve_item`, sem
lembrar escolhas). O que o item nao sabe vira palpite
(services/inbox_defaults.py) e o lancamento nasce a revisar
(services/review.py): o dono so confirma que e dele e a categoria.

A compra so do Samsung Wallet grava na hora: nenhum banco vai avisar dela. Se o
app do Flash chegar depois com a mesma compra, junta (uma linha so); se chegar
com a negativa, o lancamento intocado sai (`undo_declined()`).

Espera, so:
- a transferencia entre contas do dono com uma ponta so, ate a outra ponta
  chegar e fazer dela UMA transferencia (fica no Aprovar, que o Extrato aponta);
- o valor em outra moeda: nunca grava (o valor em reais vem do banco).

Um parecido que o dono digitou antes (`candidates`) e LIGADO, nunca duplicado.
O item guarda como o lancamento nasceu (`recorded_snapshot`): o que uma
notificacao de banco gravou antes de 2026-10-30 a Pluggy ainda confere, e
open_finance_inbox refaz o intocado do jeito do banco.

O interruptor e `auto_record_notifications` em user_settings (GET/PATCH
/api/inbox/settings); sem escolha, vale AUTO_RECORD_DEFAULT (ligado). A
passada roda depois de cada envio do celular e nas leituras do Extrato,
Inicio e Revisar.
"""

import json

from config import AUTO_RECORD_DEFAULT
from db import utc_timestamp
from services import inbox, inbox_decisions, open_finance_auto, open_finance_inbox, review
import services.invoices as invoices
from services.inbox_defaults import fill_defaults, free_candidates
from validators import ValidationError

SETTING = "auto_record_notifications"


def enabled(conn, current_user_id):
    value = inbox.setting_value(conn, current_user_id, SETTING)
    return AUTO_RECORD_DEFAULT if value is None else value == "1"


def _source_detections(conn, current_user_id, item_id):
    return [row for row in inbox.item_detections(conn, current_user_id, item_id) if row["role"] == inbox.SOURCE]


def hold_reason(item):
    """Por que o item ainda espera (o par, o valor em reais), ou None se grava ja."""
    if "amount" in (item.get("needs") or []):
        return "foreign_currency"
    if item.get("entry_type") == "TRANSFER" and not (item.get("account_id") and item.get("transfer_account_id")):
        return "awaiting_transfer"
    return None


def remember_recording(conn, current_user_id, item_id, table, target_id):
    """O lancamento nasce a revisar, e o item guarda como ele nasceu."""
    review.mark_for_review(conn, current_user_id, table, target_id)
    row = inbox.fetch_item(conn, current_user_id, item_id)
    snapshot = open_finance_inbox.target_snapshot(conn, current_user_id, table, target_id)
    inbox.save_item(
        conn, current_user_id, inbox.item_dict(row),
        {"auto_recorded_at": utc_timestamp(), "recorded_snapshot": json.dumps(snapshot, sort_keys=True)},
        bump=False,
    )


def approve_alone(conn, current_user_id, item):
    """Completa o item com os palpites e o aprova (ou liga ao parecido).
    Devolve recorded, linked ou held."""
    changes = fill_defaults(conn, current_user_id, item)
    if changes is None:
        return "held"
    if changes:
        inbox.save_item(conn, current_user_id, item, changes)
    payload = {"version": item["version"], "remember": False}
    free = free_candidates(conn, current_user_id, item)
    if free:
        payload["candidate"] = free[0]
    try:
        decided = inbox_decisions.approve_item(conn, current_user_id, item["id"], payload)
    except (ValidationError, inbox_decisions.Conflict, LookupError):
        return "held"
    if free:
        return "linked"
    remember_recording(conn, current_user_id, item["id"], decided["target_table"], decided["target_id"])
    return "recorded"


def record_item(conn, current_user_id, row):
    """Um item pendente de notificacao: recorded, linked, held ou skipped (o
    que a Pluggy alimenta e de services/open_finance_auto.py)."""
    item = inbox.item_dict(row)
    if inbox.open_finance_sources(conn, current_user_id, item["id"], roles=(inbox.SOURCE,)):
        return "skipped"
    if not _source_detections(conn, current_user_id, item["id"]):
        return "skipped"
    if hold_reason(item):
        return "held"
    return approve_alone(conn, current_user_id, item)


def record_notifications(conn, current_user_id):
    """Todo item pendente que veio de notificacao, na ordem do tempo.
    Devolve {recorded, linked, held}."""
    counts = {"recorded": 0, "linked": 0, "held": 0}
    if not enabled(conn, current_user_id):
        return counts
    rows = conn.execute(
        """
        SELECT DISTINCT i.id FROM inbox_items i
        JOIN notify_detections d ON d.item_id = i.id AND d.user_id = i.user_id AND d.role = 'SOURCE'
        WHERE i.user_id = ? AND i.state = 'PENDING'
        ORDER BY i.occurred_at, i.created_at, i.id
        """,
        (current_user_id,),
    ).fetchall()
    for entry in rows:
        fresh = inbox.fetch_item(conn, current_user_id, entry["id"])
        if not fresh or fresh["state"] != inbox.PENDING:
            continue
        status = record_item(conn, current_user_id, fresh)
        if status in counts:
            counts[status] += 1
    return counts


def undo_declined(conn, current_user_id, results):
    """O Flash negou a compra que o Samsung avisou e que ja virou lancamento: o
    intocado sai. Revisado ou editado, fica (o dono ja disse que e dele). Devolve
    quantos sairam."""
    undone = 0
    for result in results:
        if result.get("status") != "declined" or not result.get("item_id"):
            continue
        row = inbox.fetch_item(conn, current_user_id, result["item_id"])
        if not row or row["state"] != inbox.APPROVED:
            continue
        item = inbox.item_dict(row)
        if not open_finance_inbox.notification_untouched(conn, current_user_id, item):
            continue
        open_finance_inbox._drop_target(conn, current_user_id, item)
        inbox.save_item(
            conn, current_user_id, item,
            {"state": inbox.REMOVED, "reason": "declined", "target_table": None, "target_id": None,
             "decided_at": utc_timestamp()},
        )
        undone += 1
    return undone


def record_due(conn, current_user_id, today=None):
    """A passada das leituras: o que ficou pendente grava aqui. A Pluggy, se o
    interruptor dela esta ligado, tambem (o par de transferencia que venceu)."""
    today = today or invoices.local_today()
    counts = record_notifications(conn, current_user_id)
    if open_finance_auto.enabled(conn, current_user_id):
        for key, value in open_finance_auto.record_pending(conn, current_user_id, today).items():
            counts[key] = counts.get(key, 0) + value
    return counts
