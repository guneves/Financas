"""Gravar sozinho (045, dono 2026-10-27): a notificacao vira lancamento na hora.

Toda notificacao lida pelo celular (Flash e todos os bancos) que vira um item
(services/inbox.py: pareamento Samsung/banco, as duas pontas de uma
transferencia, o Open Finance que ja trouxe o mesmo movimento) e gravada logo
depois, pela mesma aprovacao da tela (`inbox_decisions.approve_item`, sem
lembrar escolhas). O que o item nao sabe vira palpite
(services/inbox_defaults.py) e o lancamento nasce a revisar
(services/review.py): o dono so confirma que e dele e a categoria.

Espera um pouco (e ninguem decide por ele), so:
- a compra que so o Samsung Wallet avisou, ate NOTIFY_WINDOW_MS: o aviso do
  banco (credito/debito, o cartao) costuma chegar logo depois e vira a fonte;
- a transferencia entre contas do dono com uma ponta so, ate a outra ponta
  (notificacao ou Pluggy) chegar e fazer dela UMA transferencia (fica no
  Aprovar, que o Extrato aponta: uma conta que nao notifica nem esta conectada
  pede o dono);
- o valor em outra moeda: nunca grava (o valor em reais vem do banco).

Um parecido que o dono digitou antes (`candidates`) e LIGADO, nunca duplicado.
O item guarda como o lancamento nasceu (`recorded_snapshot`): quando a Pluggy
trouxer o mesmo movimento com outra data ou outra conta/cartao,
open_finance_inbox refaz o intocado do jeito do banco.

O interruptor e `auto_record_notifications` em user_settings (GET/PATCH
/api/inbox/settings); sem escolha, vale AUTO_RECORD_DEFAULT (ligado). A
passada roda depois de cada envio do celular e nas leituras do Extrato,
Inicio e Revisar (o que esperava o prazo grava ai).
"""

import json
import time

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


def hold_reason(conn, current_user_id, item, detections, now_ms, today):
    """Por que o item ainda espera (o par, o banco), ou None se grava ja."""
    if "amount" in (item.get("needs") or []):
        return "foreign_currency"
    if all(row["app"] == inbox.SAMSUNG_WALLET for row in detections) and max(
        int(row["posted_ms"]) for row in detections
    ) > now_ms - inbox.NOTIFY_WINDOW_MS:
        return "awaiting_bank"
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


def record_item(conn, current_user_id, row, now_ms, today):
    """Um item pendente de notificacao: recorded, linked, held ou skipped (o
    que a Pluggy alimenta e de services/open_finance_auto.py)."""
    item = inbox.item_dict(row)
    if inbox.open_finance_sources(conn, current_user_id, item["id"], roles=(inbox.SOURCE,)):
        return "skipped"
    detections = _source_detections(conn, current_user_id, item["id"])
    if not detections:
        return "skipped"
    if hold_reason(conn, current_user_id, item, detections, now_ms, today):
        return "held"
    return approve_alone(conn, current_user_id, item)


def record_notifications(conn, current_user_id, now_ms=None, today=None):
    """Todo item pendente que veio de notificacao, na ordem do tempo.
    Devolve {recorded, linked, held}."""
    counts = {"recorded": 0, "linked": 0, "held": 0}
    if not enabled(conn, current_user_id):
        return counts
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    today = today or invoices.local_today()
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
        status = record_item(conn, current_user_id, fresh, now_ms, today)
        if status in counts:
            counts[status] += 1
    return counts


def record_due(conn, current_user_id, now_ms=None, today=None):
    """A passada das leituras: o que esperava o prazo (o Samsung sem o banco,
    a transferencia sem par) grava quando o prazo passa. A Pluggy, se o
    interruptor dela esta ligado, tambem (o par de transferencia que venceu)."""
    today = today or invoices.local_today()
    counts = record_notifications(conn, current_user_id, now_ms, today)
    if open_finance_auto.enabled(conn, current_user_id):
        for key, value in open_finance_auto.record_pending(conn, current_user_id, today).items():
            counts[key] = counts.get(key, 0) + value
    return counts
