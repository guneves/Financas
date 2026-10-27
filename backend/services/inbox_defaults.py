"""O que falta num item para ele virar lancamento sem o dono (045).

Gravar sozinho (services/auto_record.py para a notificacao,
services/open_finance_auto.py para a Pluggy) nao espera ninguem escolher: o
que o item nao sabe vira o palpite mais provavel, marcado em `guessed`, e o
lancamento nasce "a revisar" (services/review.py). O dono corrige na revisao.

- sem credito/debito: o cartao, se ha um palpite de cartao; senao debito na conta;
- sem cartao: o cartao do emissor que a notificacao cita (o primeiro, se ha
  varios), senao o primeiro cartao de credito; sem nenhum, despesa na conta;
- sem conta: a conta do emissor, senao a conta padrao (nunca a Corretora).

Sem palpite: outra moeda (`needs` com "amount": o valor em reais so o banco
ou o dono sabem) e a transferencia entre contas do dono com uma ponta so (a
outra ponta decide).
"""

from services import inbox
from services.accounts import ensure_default_account


def _source_detection(conn, current_user_id, item_id):
    for row in inbox.item_detections(conn, current_user_id, item_id):
        if row["role"] == inbox.SOURCE:
            return inbox.detection_from_row(row)
    return None


def _issuer_rows(rows, detection, *fields):
    issuer = inbox.issuer_of(detection) if detection else None
    aliases = inbox.ISSUER_ALIASES.get(issuer)
    if not aliases:
        return []
    return [row for row in rows if any(inbox._mentions(row[field], aliases) for field in fields)]


def fallback_card(conn, current_user_id, detection):
    cards = inbox._cards(conn, current_user_id)
    if not cards:
        return None
    if detection:
        picked = inbox.pick_card(cards, detection)
        if picked:
            return picked
    by_issuer = _issuer_rows(cards, detection, "name")
    return (by_issuer or cards)[0]["id"]


def fallback_account(conn, current_user_id, detection):
    if detection:
        guessed = inbox.guess_account(conn, current_user_id, detection)
        if guessed:
            return guessed
        usable = inbox._usable_accounts(conn, current_user_id, detection.get("app"))
        by_issuer = _issuer_rows(usable, detection, "name", "institution")
        if by_issuer:
            return by_issuer[0]["id"]
    return ensure_default_account(conn, current_user_id)


def fill_defaults(conn, current_user_id, item):
    """As mudancas que completam o item ({} se ja esta completo), ou None se
    nao ha palpite possivel (outra moeda, transferencia de uma ponta so)."""
    if "amount" in (item.get("needs") or []):
        return None
    draft = dict(item)
    guessed = list(item.get("guessed") or [])
    detection = _source_detection(conn, current_user_id, item["id"])

    if draft.get("entry_type") is None:
        draft["entry_type"] = "CARD" if draft.get("card_id") else "EXPENSE"
    if draft["entry_type"] == "TRANSFER" and not (draft.get("account_id") and draft.get("transfer_account_id")):
        # Uma ponta so: espera a outra (quem chama segura antes).
        return None
    if draft["entry_type"] == "CARD" and not draft.get("card_id"):
        card_id = fallback_card(conn, current_user_id, detection)
        if card_id:
            draft["card_id"] = card_id
            guessed.append("card")
        else:
            draft["entry_type"] = "INCOME" if draft.get("direction") == "IN" else "EXPENSE"
    if draft["entry_type"] in ("EXPENSE", "INCOME") and not draft.get("account_id"):
        draft["account_id"] = fallback_account(conn, current_user_id, detection)
        guessed.append("account")
    if draft["entry_type"] == "CARD":
        draft["account_id"] = None
    else:
        draft["card_id"] = None

    fields = ("entry_type", "direction", "account_id", "card_id", "transfer_account_id")
    changes = {field: draft.get(field) for field in fields if draft.get(field) != item.get(field)}
    if not changes:
        return {}
    changes["guessed"] = list(dict.fromkeys(guessed))
    if "entry_type" in changes:
        changes["category"], changes["category_id"] = inbox.suggest_category(
            conn, current_user_id, draft.get("description"), draft["entry_type"], draft["amount"],
            draft.get("account_id"),
        )
    changes["needs"] = inbox.recompute_needs({**item, **changes})
    return changes


def free_candidates(conn, current_user_id, item):
    """Os parecidos do item que ainda sao so dele: existem e nenhuma outra
    fonte (notificacao, transacao da Pluggy, outro item) ja os explica."""
    free = []
    for candidate in item.get("candidates") or []:
        table, target_id = candidate.get("table"), candidate.get("id")
        if table not in ("transactions", "cc_expenses") or not target_id:
            continue
        if not conn.execute(
            f"SELECT 1 FROM {table} WHERE id = ? AND user_id = ?", (target_id, current_user_id),
        ).fetchone():
            continue
        params = (current_user_id, table, target_id, item["id"])
        taken = conn.execute(
            """
            SELECT 1 FROM open_finance_transactions
            WHERE user_id = ? AND target_table = ? AND target_id = ? AND role <> 'REMOVED'
              AND COALESCE(item_id, '') <> ?
            """,
            params,
        ).fetchone() or conn.execute(
            """
            SELECT 1 FROM inbox_items
            WHERE user_id = ? AND target_table = ? AND target_id = ? AND id <> ?
              AND state IN ('APPROVED', 'MATCHED')
            """,
            params,
        ).fetchone()
        if not taken:
            free.append(candidate)
    return free
