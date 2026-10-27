"""Open Finance gravado sozinho (044, dono 2026-10-27): a Pluggy e a fonte das
contas conectadas, e o que ela traz vira lancamento sem passar pelo Aprovar.

O interruptor (`open_finance_auto_record` em user_settings, PATCH
/api/open-finance/settings) so liga com tudo resolvido (`blockers()`): cada
conta BANK/CREDIT ativa de cada conexao mapeada ou marcada "nao usar", e cada
conexao puxada com sucesso nas ultimas FRESH_PULL_HOURS horas. Desligado, tudo
como antes: o Aprovar decide.

Ligado, o pull continua o mesmo (services/open_finance_inbox.py poe cada
transacao num item do Aprovar, com as mesmas regras de transferencia, parcela,
estorno, pagamento de fatura, Corretora); `record_pending()` vem depois e
aprova sozinho cada item que nao precisa do dono, pela mesma aprovacao da tela
(`inbox_decisions.approve_item`, sem lembrar escolhas): o lancamento leva
source_type OPEN_FINANCE + source_id = id da Pluggy; a compra no cartao,
client_id = 'pluggy:<id>'.

Nada espera o dono (045, dono 2026-10-27): o que o item nao sabe vira palpite
(services/inbox_defaults.py) e o lancamento nasce a revisar
(services/review.py). So espera o par a transferencia: um Pix ainda
dentro de TRANSFER_HOLD_DAYS dias (a outra ponta pode chegar no pull de outro
banco, cada banco atualiza numa hora, e as duas sao UMA transferencia; passado
o prazo, sem par, e de outra pessoa: despesa/receita); e a transferencia entre
contas do dono com uma ponta so, ate a outra chegar (gravar uma despesa e
depois uma receita faria de uma transferencia dois movimentos; fica no
Aprovar, que o Extrato aponta). Um investimento numa conta
de banco (categoria 03 da Pluggy, salvo provento) grava como despesa/receita a
revisar. O item sem fonte do Open Finance (notificacao) e de
services/auto_record.py.

O interruptor (`open_finance_auto_record`) sem escolha vale AUTO_RECORD_DEFAULT
(ligado): mapear a conta ja e o consentimento. Desligado, a Pluggy so liga o
que a notificacao ja gravou e o resto espera.

Um lancamento ja gravado pelo dono que e o mesmo movimento (os "parecidos" do
item, mesmo valor e data proxima) e LIGADO, nunca duplicado nem apagado; um
parecido que outra transacao da Pluggy ja explica nao conta. O que foi gravado
sozinho guarda como nasceu (open_finance_inbox.mark_auto_recorded): se o banco
mudar o valor ou a transacao sumir, so o intocado e corrigido ou apagado.
"""

from datetime import datetime, timezone

from config import AUTO_RECORD_DEFAULT
from dates import parse_iso_date
from services import inbox, inbox_decisions, open_finance_inbox, review
from services.inbox_defaults import fill_defaults, free_candidates
from validators import ValidationError

AUTO_RECORD_SETTING = "open_finance_auto_record"
FRESH_PULL_HOURS = 48
TRANSFER_HOLD_DAYS = 2
TRANSFER_MOVEMENTS = ("TRANSFER", "SELF_TRANSFER")


def enabled(conn, current_user_id):
    value = inbox.setting_value(conn, current_user_id, AUTO_RECORD_SETTING)
    return AUTO_RECORD_DEFAULT if value is None else value == "1"


def _seconds(stamp):
    try:
        moment = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return 0
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def account_label(row):
    return row["name"] or row["number"] or "conta"


def blockers(conn, current_user_id, now_seconds):
    """Por que o interruptor nao liga (mensagens em portugues), ou []."""
    items = conn.execute(
        "SELECT * FROM open_finance_items WHERE user_id = ? AND archived_at IS NULL ORDER BY created_at, id",
        (current_user_id,),
    ).fetchall()
    if not items:
        return ["Conecte um banco antes de gravar sozinho."]
    problems = []
    for item in items:
        if not item["last_sync_at"] or now_seconds - _seconds(item["last_sync_at"]) > FRESH_PULL_HOURS * 3600:
            problems.append(
                f"A conexão {item['connector_name'] or 'Open Finance'} não foi atualizada com sucesso nas "
                f"últimas {FRESH_PULL_HOURS} horas: toque em Atualizar."
            )
        for account in conn.execute(
            "SELECT * FROM open_finance_accounts WHERE user_id = ? AND of_item_id = ? ORDER BY type, name, id",
            (current_user_id, item["id"]),
        ).fetchall():
            if account["ignored_at"] or account["account_id"] or account["card_id"]:
                continue
            problems.append(f"Escolha o destino de {account_label(account)} (ou marque \"não usar\").")
    return problems


# ---------------------------------------------------------------------------
# Aprovar sozinho
# ---------------------------------------------------------------------------

def _days_since(date_text, today):
    day = parse_iso_date(str(date_text or "")[:10])
    return (today - day.date()).days if day else 0


def _linked_elsewhere(conn, current_user_id, candidate, item_id):
    """O parecido ja e o lancamento de outra transacao da Pluggy (ou nem existe)."""
    table, target_id = candidate.get("table"), candidate.get("id")
    if table not in ("transactions", "cc_expenses") or not target_id:
        return True
    exists = conn.execute(
        f"SELECT 1 FROM {table} WHERE id = ? AND user_id = ?", (target_id, current_user_id),
    ).fetchone()
    if not exists:
        return True
    return conn.execute(
        """
        SELECT 1 FROM open_finance_transactions
        WHERE user_id = ? AND target_table = ? AND target_id = ? AND role <> 'REMOVED'
          AND COALESCE(item_id, '') <> ?
        """,
        (current_user_id, table, target_id, item_id),
    ).fetchone() is not None


def hold_reason(conn, current_user_id, item, sources, today):
    """Por que este item ainda espera (o par), ou None se grava sozinho."""
    if not sources:
        return "not_open_finance"
    for source in sources:
        account = open_finance_inbox.fetch_account(conn, current_user_id, source["of_account_id"])
        if not account or account["ignored_at"] or not open_finance_inbox.mapped_target(account):
            return "unmapped"
    is_transfer = any(source["movement"] in TRANSFER_MOVEMENTS for source in sources)
    complete_transfer = item["entry_type"] == "TRANSFER" and item.get("account_id") and item.get("transfer_account_id")
    if is_transfer and not complete_transfer:
        newest = max(_days_since(source["date"], today) for source in sources)
        if newest < TRANSFER_HOLD_DAYS or item["entry_type"] == "TRANSFER":
            return "awaiting_transfer"
    if "amount" in (item.get("needs") or []):
        return "foreign_currency"
    return None


def record_item(conn, current_user_id, row, today):
    """Grava (ou liga) um item pendente sozinho. Devolve recorded, linked ou
    held."""
    item = inbox.item_dict(row)
    sources = inbox.open_finance_sources(conn, current_user_id, item["id"], roles=(inbox.SOURCE,))
    if hold_reason(conn, current_user_id, item, sources, today):
        return "held"
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
    review.mark_for_review(conn, current_user_id, decided["target_table"], decided["target_id"])
    open_finance_inbox.mark_auto_recorded(
        conn, current_user_id, item["id"], decided["target_table"], decided["target_id"],
    )
    return "recorded"


def record_pending(conn, current_user_id, today):
    """Todos os itens pendentes que vieram do Open Finance, na ordem do tempo
    (o que ja estava no Aprovar quando o interruptor ligou, numa passada so).
    Devolve {recorded, linked, held}."""
    counts = {"recorded": 0, "linked": 0, "held": 0}
    rows = conn.execute(
        """
        SELECT DISTINCT i.* FROM inbox_items i
        JOIN open_finance_transactions o ON o.item_id = i.id AND o.user_id = i.user_id
        WHERE i.user_id = ? AND i.state = 'PENDING' AND o.role = 'SOURCE'
        ORDER BY i.occurred_at, i.created_at, i.id
        """,
        (current_user_id,),
    ).fetchall()
    for row in rows:
        fresh = inbox.fetch_item(conn, current_user_id, row["id"])
        if not fresh or fresh["state"] != inbox.PENDING:
            continue
        counts[record_item(conn, current_user_id, fresh, today)] += 1
    return counts
