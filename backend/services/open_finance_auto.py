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

Fica no Aprovar (o dono decide) o item que:
- tem um campo a escolher (uma transferencia de uma ponta so: a outra conta);
- e investimento numa conta de banco (categoria 03 da Pluggy, salvo provento):
  aporte ou despesa, so o dono sabe;
- e uma transferencia ainda dentro de TRANSFER_HOLD_DAYS dias: a outra ponta
  pode chegar no pull de outro banco (cada banco atualiza numa hora) e as duas
  sao UMA transferencia; passado o prazo, sem par, grava como despesa/receita;
- nao tem fonte do Open Finance (notificacao: Flash).

Um lancamento ja gravado pelo dono que e o mesmo movimento (os "parecidos" do
item, mesmo valor e data proxima) e LIGADO, nunca duplicado nem apagado; um
parecido que outra transacao da Pluggy ja explica nao conta. O que foi gravado
sozinho guarda como nasceu (open_finance_inbox.mark_auto_recorded): se o banco
mudar o valor ou a transacao sumir, so o intocado e corrigido ou apagado.
"""

from datetime import datetime, timezone

from dates import parse_iso_date
from services import inbox, inbox_decisions, open_finance_inbox
from validators import ValidationError

AUTO_RECORD_SETTING = "open_finance_auto_record"
FRESH_PULL_HOURS = 48
TRANSFER_HOLD_DAYS = 2
TRANSFER_MOVEMENTS = ("TRANSFER", "SELF_TRANSFER")
INVESTMENT_CATEGORY_PREFIX = "03"
PROCEEDS_CATEGORY = "03060000"


def enabled(conn, current_user_id):
    return inbox.setting_value(conn, current_user_id, AUTO_RECORD_SETTING) == "1"


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
    """Por que este item espera o dono (ou o par), ou None se grava sozinho."""
    if not sources:
        return "not_open_finance"
    for source in sources:
        account = open_finance_inbox.fetch_account(conn, current_user_id, source["of_account_id"])
        if not account or account["ignored_at"] or not open_finance_inbox.mapped_target(account):
            return "unmapped"
        category = str(source["pluggy_category_id"] or "")
        if (
            account["type"] == "BANK" and category.startswith(INVESTMENT_CATEGORY_PREFIX) and category != PROCEEDS_CATEGORY
            and not open_finance_inbox.is_brokerage(conn, current_user_id, account["account_id"])
        ):
            return "investment"
    is_transfer = any(source["movement"] in TRANSFER_MOVEMENTS for source in sources)
    complete_transfer = item["entry_type"] == "TRANSFER" and not item["needs"]
    if is_transfer and not complete_transfer:
        newest = max(_days_since(source["date"], today) for source in sources)
        if newest < TRANSFER_HOLD_DAYS or item["entry_type"] == "TRANSFER":
            return "awaiting_transfer"
    if item["needs"]:
        return "needs_decision"
    return None


def record_item(conn, current_user_id, row, today):
    """Grava (ou liga) um item pendente sozinho. Devolve recorded, linked ou
    held."""
    item = inbox.item_dict(row)
    sources = inbox.open_finance_sources(conn, current_user_id, item["id"], roles=(inbox.SOURCE,))
    if hold_reason(conn, current_user_id, item, sources, today):
        return "held"
    payload = {"version": row["version"], "remember": False}
    free = [
        candidate for candidate in item.get("candidates") or []
        if not _linked_elsewhere(conn, current_user_id, candidate, item["id"])
    ]
    if free:
        payload["candidate"] = free[0]
    try:
        decided = inbox_decisions.approve_item(conn, current_user_id, item["id"], payload)
    except (ValidationError, inbox_decisions.Conflict, LookupError):
        return "held"
    if free:
        return "linked"
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
