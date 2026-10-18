"""Aprovar: o que o dono decide sobre um item (services/inbox.py, 028).

- `update_item`: corrige o rascunho (tipo, valor, data e hora, descricao,
  categoria, conta, cartao, parcelas). Fica no servidor: o computador e o
  celular veem a mesma correcao.
- `approve_item`: grava o lancamento com o rascunho, na data local da hora que
  a fonte disse (ou da que o dono corrigiu), e guarda essa hora em
  `occurred_at`. O lancamento nasce como digitado pelo dono, com o client_id da primeira notificacao — confirmar pelo celular depois cai
  no mesmo lancamento. Uma transferencia entre contas do dono e uma linha
  TRANSFER so. Com um lancamento parecido escolhido ("e este"), nada e gravado:
  as notificacoes passam a confirmar ele.
- `deny_item` / `restore_item`: recusar e desfazer a recusa.
- `split_item`: "nao e a mesma compra" — uma fonte sai para um item proprio.
- `absorb_created`: o dono lancou pelo "+ Novo" algo que ja esperava aqui; o
  item vira esse lancamento em vez de ficar como duplicata.

Cada mudanca confere a versao do item: o que um aparelho decidiu o outro nao
desfaz sem ver (409, com o item como esta).
"""

import sqlite3

from config import INBOX_MATCH_DAYS
from dates import parse_iso_date
from db import new_id, row_to_dict, utc_timestamp
from money import rounded_money
from services import inbox, recurring
from services.accounts import category_id_for_name, fetch_category, fetch_transaction_by_client_id
from services.import_rules import DEFAULT_IMPORT_CATEGORIES
from services.invoices import build_installment_rows, purchase_invoice_start, require_active_card
from validators import ValidationError, parse_number

EDITABLE_FIELDS = (
    "entry_type", "amount", "occurred_at", "description", "category", "category_id",
    "account_id", "card_id", "transfer_account_id", "installments",
)
NEED_OF_FIELD = {"card_id": "card", "account_id": "account", "transfer_account_id": "transfer_account"}
DIRECTION_OF_TYPE = {"EXPENSE": "OUT", "CARD": "OUT", "TRANSFER": "OUT", "INCOME": "IN"}


class Conflict(Exception):
    """O item mudou em outro aparelho (ou ja foi decidido)."""

    def __init__(self, message, item_row):
        super().__init__(message)
        self.item_row = item_row


def _load(conn, current_user_id, item_id, *, version=None, states=(inbox.PENDING,)):
    row = inbox.fetch_item(conn, current_user_id, item_id)
    if not row:
        raise LookupError("Item nao encontrado.")
    if row["state"] not in states:
        raise Conflict("Este item ja foi decidido (talvez em outro aparelho).", row)
    if version is not None:
        try:
            wanted = int(version)
        except (TypeError, ValueError) as exc:
            raise ValidationError("Versao invalida.") from exc
        if wanted != int(row["version"]):
            raise Conflict("Este item mudou em outro aparelho. Confira antes de decidir.", row)
    return inbox.item_dict(row)


# ---------------------------------------------------------------------------
# O rascunho
# ---------------------------------------------------------------------------

def _account(conn, current_user_id, account_id, label):
    row = conn.execute(
        "SELECT * FROM accounts WHERE id = ? AND user_id = ?",
        (account_id, current_user_id),
    ).fetchone()
    if not row:
        raise ValidationError(f"{label} nao encontrada.")
    if row["archived_at"]:
        raise ValidationError(f"{label} esta arquivada.")
    if (row["currency"] or "BRL") != "BRL":
        raise ValidationError(f"{label} nao e em reais.")
    return row


def _card(conn, current_user_id, card_id):
    # Um cartao excluido (arquivado, 037) nao recebe compra aprovada.
    return require_active_card(conn, current_user_id, card_id)


def _text_or_none(value, max_length):
    if value is None:
        return None
    text = str(value).strip()
    if len(text) > max_length:
        raise ValidationError(f"Texto com mais de {max_length} caracteres.")
    return text or None


def parse_changes(conn, current_user_id, item, payload):
    """Os campos do rascunho que o payload troca, validados. Um cartao/conta
    enviado igual ao palpite nao e mudanca, mas confirma o palpite
    (`_touched`)."""
    changes = {}
    for field in EDITABLE_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if field == "entry_type":
            value = str(value or "").strip().upper()
            if value not in inbox.ENTRY_TYPES:
                raise ValidationError("Tipo invalido.")
        elif field == "amount":
            value = rounded_money(parse_number(payload, "amount", "Valor", minimum=0, allow_zero=False))
        elif field == "occurred_at":
            fallback = inbox.offset_of(item["occurred_at"]) or inbox.offset_of(item["source_occurred_at"])
            value = inbox.normalize_occurred_at(value, fallback)
        elif field == "description":
            value = _text_or_none(value, 500)
        elif field == "category":
            value = _text_or_none(value, 255)
        elif field == "category_id":
            value = _text_or_none(value, 64)
            if value:
                category = fetch_category(conn, current_user_id, value)
                if not category:
                    raise ValidationError("Categoria nao encontrada.")
                if category["archived_at"]:
                    raise ValidationError("Categoria esta arquivada.")
                changes["category"] = category["name"]
        elif field in ("account_id", "transfer_account_id"):
            value = _text_or_none(value, 64)
            if value:
                _account(conn, current_user_id, value, "Conta")
        elif field == "card_id":
            value = _text_or_none(value, 64)
            if value:
                _card(conn, current_user_id, value)
        elif field == "installments":
            try:
                value = int(value)
            except (TypeError, ValueError) as exc:
                raise ValidationError("Parcelas invalidas.") from exc
            if not 1 <= value <= 72:
                raise ValidationError("Parcelas invalidas.")
        changes[field] = value
    if "category" in changes and "category_id" not in changes:
        # So o nome (a tela manda o id): o mesmo nome do rascunho fica com o id
        # dele; outro, o da categoria com esse nome (a raiz antes).
        if changes["category"] == item.get("category"):
            changes["category_id"] = item.get("category_id")
        else:
            changes["category_id"] = category_id_for_name(conn, current_user_id, changes["category"])
    touched = {field for field in changes if field in NEED_OF_FIELD and changes[field]}
    changes = {field: value for field, value in changes.items() if item.get(field) != value}
    if touched - set(changes):
        changes["_touched"] = touched
    return changes


def _with_changes(conn, current_user_id, item, changes):
    """O item com as mudancas do dono, mais o que elas arrastam (direcao,
    categoria de transferencia, o que falta, o que deixou de ser palpite)."""
    touched = set(changes.pop("_touched", ())) | {field for field in changes if field in NEED_OF_FIELD}
    if not changes and not touched:
        return {}
    full = dict(changes)
    merged = {**item, **changes}
    if "entry_type" in changes:
        full["direction"] = DIRECTION_OF_TYPE[changes["entry_type"]]
        merged["direction"] = full["direction"]
        if changes["entry_type"] != "TRANSFER":
            full.setdefault("transfer_account_id", None)
        if changes["entry_type"] != "CARD":
            full.setdefault("installments", 1)
        if "category" not in changes:
            if changes["entry_type"] == "TRANSFER":
                full["category"], full["category_id"] = inbox.TRANSFER_CATEGORY, None
            elif item.get("entry_type") == "TRANSFER" or not item.get("category"):
                full["category"], full["category_id"] = inbox.suggest_category(
                    conn, current_user_id, merged.get("description"), changes["entry_type"], merged["amount"],
                    merged.get("account_id"),
                )
        merged.update(full)
    edited = list(item.get("edited") or [])
    for field in changes:
        if field not in edited:
            edited.append(field)
    full["edited"] = edited
    confirmed = {NEED_OF_FIELD[field] for field in touched}
    full["guessed"] = [guess for guess in item.get("guessed") or [] if guess not in confirmed]
    merged.update(full)
    full["needs"] = inbox.recompute_needs(merged)
    return full


def update_item(conn, current_user_id, item_id, payload):
    item = _load(conn, current_user_id, item_id, version=payload.get("version"))
    changes = parse_changes(conn, current_user_id, item, payload)
    full = _with_changes(conn, current_user_id, item, changes)
    if "recurring" in payload and payload["recurring"] in (True, False, None):
        # "Nao e esta recorrencia" (false) e desfazer (true): vale tambem para
        # o "Aprovar todos".
        off = 0 if payload["recurring"] else 1
        if off != int(item.get("recurring_off") or 0):
            full["recurring_off"] = off
    if full:
        inbox.save_item(conn, current_user_id, item, full)
    return inbox.fetch_item(conn, current_user_id, item_id)


# ---------------------------------------------------------------------------
# Aprovar
# ---------------------------------------------------------------------------

NEED_MESSAGES = {
    "method": "Diga se foi no crédito (cartão) ou no débito (conta).",
    "card": "Escolha o cartão.",
    "account": "Escolha a conta.",
    "transfer_account": "Escolha a conta de destino.",
    "amount": "Confira o valor em reais (a compra foi em outra moeda).",
}


def _ensure_complete(conn, current_user_id, item):
    if item.get("needs"):
        raise ValidationError(NEED_MESSAGES.get(item["needs"][0], "Complete o item antes de aprovar."))
    entry_type = item["entry_type"]
    if entry_type == "CARD":
        _card(conn, current_user_id, item["card_id"])
    else:
        _account(conn, current_user_id, item["account_id"], "Conta")
    if entry_type == "TRANSFER":
        _account(conn, current_user_id, item["transfer_account_id"], "Conta de destino")
        if item["account_id"] == item["transfer_account_id"]:
            raise ValidationError("Origem e destino devem ser contas diferentes.")
    if not item.get("category"):
        item["category"], item["category_id"] = inbox.suggest_category(
            conn, current_user_id, item.get("description"), entry_type, item["amount"], item.get("account_id"),
        )


def _existing_by_client_key(conn, current_user_id, item):
    """O lancamento que o celular ja gravou com o client_id deste item."""
    key = item.get("client_key")
    if not key:
        return None
    if item["entry_type"] == "CARD":
        row = conn.execute(
            "SELECT id FROM cc_expenses WHERE user_id = ? AND client_id = ? ORDER BY invoice_year, invoice_month LIMIT 1",
            (current_user_id, key),
        ).fetchone()
        return ("cc_expenses", row["id"]) if row else None
    row = fetch_transaction_by_client_id(conn, current_user_id, key)
    return ("transactions", row["id"]) if row else None


def create_entry(conn, current_user_id, item):
    """O lancamento do rascunho, como se o dono o tivesse digitado."""
    existing = _existing_by_client_key(conn, current_user_id, item)
    if existing:
        return existing
    entry_type = item["entry_type"]
    date_text = inbox.date_of(item["occurred_at"])
    amount = rounded_money(item["amount"])
    client_id = item.get("client_key")
    try:
        if entry_type == "CARD":
            card = _card(conn, current_user_id, item["card_id"])
            rows = build_installment_rows(
                {
                    "card_id": card["id"],
                    "category": item["category"],
                    "category_id": item.get("category_id"),
                    "description": item.get("description") or "Compra no cartão",
                    "total_amount": amount,
                    "purchase_date": date_text,
                    "installments": int(item.get("installments") or 1),
                },
                card,
                # Fatura ja paga nao recebe a compra (ficaria aberta para sempre).
                purchase_invoice_start(conn, current_user_id, card, date_text),
            )
            first = None
            # O client_id e a compra (035): sem o da notificacao, um novo.
            purchase_id = client_id or new_id()
            for row in rows:
                row_id = new_id()
                first = first or row_id
                conn.execute(
                    """
                    INSERT INTO cc_expenses
                    (id, user_id, card_id, category, category_id, description, amount, purchase_date,
                     invoice_month, invoice_year, installment_info, status, client_id, occurred_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row_id, current_user_id, row["card_id"], row["category"], row["category_id"],
                        row["description"], row["amount"], row["purchase_date"], row["invoice_month"],
                        row["invoice_year"], row["installment_info"], row["status"], purchase_id,
                        item["occurred_at"],
                    ),
                )
            return "cc_expenses", first

        row_id = new_id()
        if entry_type == "TRANSFER":
            conn.execute(
                """
                INSERT INTO transactions
                (id, user_id, account_id, transfer_account_id, amount, date, category, category_id,
                 description, type, client_id, occurred_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'TRANSFER', ?, ?)
                """,
                (
                    row_id, current_user_id, item["account_id"], item["transfer_account_id"], amount, date_text,
                    item["category"] or inbox.TRANSFER_CATEGORY, item.get("category_id"),
                    item.get("description"), client_id, item["occurred_at"],
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO transactions
                (id, user_id, account_id, amount, date, category, category_id, description, type,
                 client_id, occurred_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_id, current_user_id, item["account_id"], amount, date_text, item["category"],
                    item.get("category_id"), item.get("description"), entry_type, client_id,
                    item["occurred_at"],
                ),
            )
        return "transactions", row_id
    except sqlite3.IntegrityError as exc:
        raise ValidationError("Nao foi possivel gravar o lancamento.") from exc


def _source_description(conn, current_user_id, item):
    """A descricao como a fonte disse (o estabelecimento da notificacao), para
    a chave lembrada de uma transferencia."""
    for row in inbox.item_detections(conn, current_user_id, item["id"]):
        description = inbox.detection_description(inbox.detection_from_row(row))
        if description:
            return description
    return item.get("description")


def remember_choice(conn, current_user_id, item, before):
    """Lembra o cartao/conta escolhido (e o credito/debito), e a transferencia
    de uma ponta so, para o proximo item decidir sozinho."""
    remembered = []
    entry_type = item["entry_type"]
    key = item.get("hint_key")
    had_decision = bool(before.get("needs") or before.get("guessed") or set(item.get("edited") or []) & {
        "entry_type", "card_id", "account_id",
    })
    # Ambiguo (mais de uma conta/cartao no banco, a notificacao sem o final):
    # nada fica lembrado, o proximo item pergunta de novo.
    if (
        key and entry_type in ("CARD", "EXPENSE", "INCOME")
        and not inbox.ambiguous_target(conn, current_user_id, key, entry_type)
        and (had_decision or not inbox.fetch_hint(conn, current_user_id, key))
    ):
        inbox.remember(
            conn, current_user_id, key, item.get("hint_label"),
            entry_type=entry_type,
            account_id=item["account_id"] if entry_type != "CARD" else None,
            card_id=item["card_id"] if entry_type == "CARD" else None,
        )
        inbox.apply_hint_to_pending(conn, current_user_id, key, exclude_id=item["id"])
        remembered.append(key)
    if entry_type == "TRANSFER":
        # Cada notificacao fica lembrada na conta do lado dela.
        for detection in inbox.item_detections(conn, current_user_id, item["id"]):
            if detection["role"] != inbox.SOURCE or detection["kind"] not in inbox.KIND_SHAPES:
                continue
            side, side_type, _method = inbox.KIND_SHAPES[detection["kind"]]
            side_account = item["account_id"] if side == "OUT" else item["transfer_account_id"]
            parsed = inbox.detection_from_row(detection)
            side_key = inbox.detection_hint_key(parsed)
            if (
                side_type in ("EXPENSE", "INCOME") and side_account and side_key not in remembered
                and not inbox.ambiguous_target(conn, current_user_id, side_key, side_type)
            ):
                inbox.remember(
                    conn, current_user_id, side_key, inbox.detection_hint_label(parsed),
                    entry_type=side_type, account_id=side_account,
                )
                remembered.append(side_key)
        # O dono disse que e entre as contas dele: quem a notificacao citou do
        # outro lado e ele mesmo (031), e o proximo Pix assim ja vem transferencia.
        inbox.learn_self(conn, current_user_id, inbox._movement_sources(conn, current_user_id, item["id"]))
        sides = inbox._source_directions(conn, current_user_id, item["id"])
        if len(sides) == 1:
            side = next(iter(sides))
            account_id = item["account_id"] if side == "OUT" else item["transfer_account_id"]
            other = item["transfer_account_id"] if side == "OUT" else item["account_id"]
            transfer_key = inbox.transfer_hint_key(account_id, side, _source_description(conn, current_user_id, item))
            if transfer_key:
                inbox.remember(
                    conn, current_user_id, transfer_key, item.get("description"),
                    entry_type="TRANSFER", account_id=account_id, transfer_account_id=other,
                )
                remembered.append(transfer_key)
    return remembered


def _link_detections(conn, current_user_id, item_id, table, target_id):
    conn.execute(
        "UPDATE notify_detections SET target_table = ?, target_id = ? WHERE user_id = ? AND item_id = ?",
        (table, target_id, current_user_id, item_id),
    )


def _close(conn, current_user_id, item, state, table, target_id, reason=None):
    changes = {"state": state, "target_table": table, "target_id": target_id, "decided_at": utc_timestamp()}
    if reason:
        changes["reason"] = reason
    inbox.save_item(conn, current_user_id, item, changes)


def approve_item(conn, current_user_id, item_id, payload):
    """Aprova: grava o lancamento (ou, com `candidate`, confirma um que ja
    existe). `remember` (padrao sim) guarda a escolha de cartao/conta."""
    item = _load(conn, current_user_id, item_id, version=payload.get("version"))
    before = dict(item)
    changes = parse_changes(conn, current_user_id, item, payload)
    full = _with_changes(conn, current_user_id, item, changes)
    if full:
        inbox.save_item(conn, current_user_id, item, full)
    remember = payload.get("remember", True) is not False

    candidate = payload.get("candidate")
    if candidate:
        return _match_candidate(conn, current_user_id, item, before, candidate, remember, payload)

    _ensure_complete(conn, current_user_id, item)
    occurrence = recurring_choice(conn, current_user_id, item, payload)
    if occurrence:
        _adopt_recurring_category(item, occurrence)
    table, target_id = create_entry(conn, current_user_id, item)
    _link_detections(conn, current_user_id, item["id"], table, target_id)
    if occurrence:
        _settle(conn, current_user_id, item, occurrence, table, target_id)
    if remember:
        remember_choice(conn, current_user_id, item, before)
    _close(conn, current_user_id, item, inbox.APPROVED, table, target_id)
    return inbox.fetch_item(conn, current_user_id, item_id)


def recurring_choice(conn, current_user_id, item, payload):
    """A ocorrencia de recorrencia que aprovar este item da como feita (034).

    `recurring` no payload: ausente, a que a tela mostra (a sugestao, salvo
    "nao e esta"); false/null, nenhuma; {recurring_id, date}, essa — conferida
    aqui, antes de gravar qualquer coisa.
    """
    if "recurring" not in payload:
        if item.get("recurring_off"):
            return None
        return recurring.suggest_for_item(conn, current_user_id, item)
    chosen = payload["recurring"]
    if not chosen:
        return None
    if not isinstance(chosen, dict):
        raise ValidationError("Recorrencia invalida.")
    row = recurring.fetch_recurring(conn, current_user_id, str(chosen.get("recurring_id") or ""))
    occurrence = parse_iso_date(str(chosen.get("date") or ""))
    if not row or not occurrence:
        raise ValidationError("Recorrencia nao encontrada.")
    if not row["active"] or row["type"] != recurring.recurring_type_of_item(item):
        raise ValidationError("Esta recorrencia nao combina com o lancamento.")
    if occurrence not in recurring.open_occurrences(conn, current_user_id, row, occurrence, occurrence):
        raise ValidationError("Esta ocorrencia da recorrencia ja foi lancada.")
    return recurring.occurrence_dict(row, occurrence.strftime("%Y-%m-%d"))


def _adopt_recurring_category(item, occurrence):
    """Sem regra do extrato (a categoria padrao) e sem o dono ter escolhido, o
    lancamento fica na categoria da recorrencia."""
    if "category" in (item.get("edited") or []) or item["entry_type"] == "TRANSFER":
        return
    if item.get("category") and item["category"] not in DEFAULT_IMPORT_CATEGORIES.values():
        return
    item["category"], item["category_id"] = occurrence["category"], occurrence["category_id"]


def _settle(conn, current_user_id, item, occurrence, table, target_id):
    try:
        recurring.settle_occurrence(
            conn, current_user_id, occurrence["recurring_id"], occurrence["date"],
            item=item, target_table=table, target_id=target_id,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


def _target_shape(conn, current_user_id, table, target_id):
    if table == "cc_expenses":
        row = conn.execute(
            "SELECT id, card_id FROM cc_expenses WHERE id = ? AND user_id = ?",
            (target_id, current_user_id),
        ).fetchone()
        return row, ("CARD" if row else None)
    row = conn.execute(
        "SELECT id, type, account_id, transfer_account_id, source_type FROM transactions WHERE id = ? AND user_id = ?",
        (target_id, current_user_id),
    ).fetchone()
    return row, (row["type"] if row else None)


def _match_candidate(conn, current_user_id, item, before, candidate, remember, payload):
    table = str(candidate.get("table") or "") if isinstance(candidate, dict) else ""
    target_id = str(candidate.get("id") or "") if isinstance(candidate, dict) else ""
    listed = next(
        (entry for entry in item.get("candidates") or [] if entry.get("table") == table and entry.get("id") == target_id),
        None,
    )
    if not listed:
        raise ValidationError("Escolha um dos lancamentos parecidos.")
    row, row_type = _target_shape(conn, current_user_id, table, target_id)
    if not row:
        raise ValidationError("Este lancamento nao existe mais.")
    kind = listed.get("kind") or "entry"
    occurrence = None
    if kind in ("entry", "card_purchase") and row_type in ("EXPENSE", "INCOME", "CARD"):
        # O lancamento que ja existia (digitado a mao) faz a ocorrencia, como
        # um aprovado faria — com o tipo dele, nao o do rascunho.
        occurrence = recurring_choice(conn, current_user_id, {**item, "entry_type": row_type}, payload)
    _link_detections(conn, current_user_id, item["id"], table, target_id)
    if occurrence:
        _settle(conn, current_user_id, {**item, "entry_type": row_type}, occurrence, table, target_id)
    if remember and kind in ("entry", "card_purchase") and row_type in ("EXPENSE", "INCOME", "CARD"):
        chosen = {
            **item,
            "entry_type": row_type,
            "card_id": row["card_id"] if row_type == "CARD" else None,
            "account_id": row["account_id"] if row_type != "CARD" else None,
        }
        remember_choice(conn, current_user_id, chosen, before)
    _close(conn, current_user_id, item, inbox.MATCHED, table, target_id, reason="owner_matched")
    return inbox.fetch_item(conn, current_user_id, item["id"])


def approve_ready(conn, current_user_id, item_ids):
    """"Aprovar todos": so os itens prontos (nada a escolher, nenhum palpite a
    confirmar); o resto fica, com o motivo."""
    approved, skipped = [], []
    ask = inbox.always_ask(conn, current_user_id)
    for item_id in item_ids:
        row = inbox.fetch_item(conn, current_user_id, item_id)
        if not row or row["state"] != inbox.PENDING:
            skipped.append({"id": item_id, "reason": "decided"})
            continue
        item = inbox.item_dict(row)
        if item["needs"] or inbox.confirm_targets(item, ask):
            skipped.append({"id": item_id, "reason": "needs_decision"})
            continue
        try:
            approve_item(conn, current_user_id, item_id, {"version": row["version"]})
        except (ValidationError, Conflict) as exc:
            skipped.append({"id": item_id, "reason": "refused", "error": str(exc)})
            continue
        approved.append(item_id)
    return {"approved": approved, "skipped": skipped}


# ---------------------------------------------------------------------------
# Recusar, desfazer, separar
# ---------------------------------------------------------------------------

def deny_item(conn, current_user_id, item_id, payload):
    item = _load(conn, current_user_id, item_id, version=payload.get("version"))
    _close(conn, current_user_id, item, inbox.DENIED, None, None, reason="owner")
    return inbox.fetch_item(conn, current_user_id, item_id)


def restore_item(conn, current_user_id, item_id, payload):
    item = _load(conn, current_user_id, item_id, version=payload.get("version"), states=(inbox.DENIED,))
    inbox.save_item(conn, current_user_id, item, {"state": inbox.PENDING, "decided_at": None, "reason": "restored"})
    return inbox.fetch_item(conn, current_user_id, item_id)


def _live_sources(conn, current_user_id, item_id):
    return [
        row for row in inbox.item_detections(conn, current_user_id, item_id) if row["role"] in (inbox.SOURCE, inbox.PAIRED)
    ]


def _back_to_one_side(conn, current_user_id, item):
    """Uma transferencia que perdeu uma ponta volta a despesa ou receita da
    ponta que ficou (o dono disse que nao era a mesma coisa)."""
    if item["entry_type"] != "TRANSFER" or "entry_type" in (item.get("edited") or []):
        return
    sides = inbox._source_directions(conn, current_user_id, item["id"])
    if len(sides) != 1:
        return
    side = next(iter(sides))
    account_id = item["account_id"] if side == "OUT" else item["transfer_account_id"]
    entry_type = "EXPENSE" if side == "OUT" else "INCOME"
    changes = {
        "entry_type": entry_type, "direction": side, "account_id": account_id,
        "transfer_account_id": None, "reason": "split",
    }
    if "category" not in (item.get("edited") or []):
        changes["category"], changes["category_id"] = inbox.suggest_category(
            conn, current_user_id, item.get("description"), entry_type, item["amount"], account_id,
        )
    changes["needs"] = inbox.recompute_needs({**item, **changes})
    inbox.save_item(conn, current_user_id, item, changes)


def split_item(conn, current_user_id, item_id, payload):
    """"Nao e a mesma": a fonte escolhida sai para um item so dela."""
    item = _load(conn, current_user_id, item_id, version=payload.get("version"))
    source = str(payload.get("source") or "")
    source_id = str(payload.get("source_id") or "")
    detections = _live_sources(conn, current_user_id, item["id"])
    if len(detections) < 2:
        raise ValidationError("Este item tem uma fonte so.")
    if source == "notification":
        row = next((entry for entry in detections if entry["id"] == source_id), None)
        if not row:
            raise ValidationError("Fonte nao encontrada neste item.")
        detection = inbox.detection_from_row(row)
        new_id_ = inbox.new_item_for_detection(conn, current_user_id, detection)
        conn.execute(
            """
            UPDATE notify_detections SET role = 'SOURCE', paired_with = NULL, item_id = ?
            WHERE id = ? AND user_id = ?
            """,
            (new_id_, row["id"], current_user_id),
        )
        conn.execute(
            "UPDATE notify_detections SET paired_with = NULL WHERE user_id = ? AND paired_with = ?",
            (current_user_id, row["id"]),
        )
        if item.get("client_key") == row["dedup_key"]:
            remaining = next((entry for entry in detections if entry["id"] != row["id"]), None)
            inbox.save_item(conn, current_user_id, item, {"client_key": remaining["dedup_key"] if remaining else None})
    else:
        raise ValidationError("Fonte invalida.")
    item = inbox.item_dict(inbox.fetch_item(conn, current_user_id, item["id"]))
    _back_to_one_side(conn, current_user_id, item)
    inbox.save_item(conn, current_user_id, item, {"reason": item.get("reason") or "split"})
    return inbox.fetch_item(conn, current_user_id, item_id), inbox.fetch_item(conn, current_user_id, new_id_)


# ---------------------------------------------------------------------------
# Lancado por outro caminho
# ---------------------------------------------------------------------------

def _absorb(conn, current_user_id, item_row, table, target_id):
    item = inbox.item_dict(item_row)
    _link_detections(conn, current_user_id, item["id"], table, target_id)
    _close(conn, current_user_id, item, inbox.MATCHED, table, target_id, reason="created_elsewhere")
    return item["id"]


def _exact_pending(conn, current_user_id, *, cents, date_text, direction, accept):
    rows = inbox._pending_items(
        conn, current_user_id, cents=cents, date_text=date_text, days=INBOX_MATCH_DAYS, direction=direction,
    )
    found = [row for row in rows if accept(row)]
    return found[0] if len(found) == 1 else None


def absorb_created(conn, current_user_id, table, row, installments=None):
    """O dono lancou pelo "+ Novo" (ou o celular enviou) um movimento que ja
    esperava em Aprovar, na mesma conta (ou cartao), mesmo valor e data
    proxima: o item vira esse lancamento. Um so candidato, ou nada muda.
    `installments`: no cartao, todas as parcelas da compra (row e a primeira).
    Devolve os ids dos itens absorvidos."""
    if not row:
        return []
    absorbed = []
    if row["client_id"]:
        # O celular confirmou pela notificacao: o client_id e o do item.
        same = conn.execute(
            "SELECT * FROM inbox_items WHERE user_id = ? AND state = 'PENDING' AND client_key = ?",
            (current_user_id, row["client_id"]),
        ).fetchone()
        if same:
            return [_absorb(conn, current_user_id, same, table, row["id"])]
    if table == "cc_expenses":
        card_id = row["card_id"]
        cents = sum(inbox._cents(entry["amount"]) for entry in (installments or [row]))
        match = _exact_pending(
            conn, current_user_id, cents=cents, date_text=row["purchase_date"], direction="OUT",
            accept=lambda item: item["entry_type"] == "CARD" and item["card_id"] == card_id
            and "card" not in inbox._jlist(item["guessed"]),
        )
        if match:
            absorbed.append(_absorb(conn, current_user_id, match, table, row["id"]))
        return absorbed

    cents = inbox._cents(row["amount"])
    if row["type"] == "TRANSFER":
        match = _exact_pending(
            conn, current_user_id, cents=cents, date_text=row["date"], direction="OUT",
            accept=lambda item: item["entry_type"] == "TRANSFER" and item["account_id"] == row["account_id"]
            and item["transfer_account_id"] == row["transfer_account_id"],
        )
        if match:
            return [_absorb(conn, current_user_id, match, table, row["id"])]
        for direction, account_id, entry_type in (
            ("OUT", row["account_id"], "EXPENSE"), ("IN", row["transfer_account_id"], "INCOME"),
        ):
            side = _exact_pending(
                conn, current_user_id, cents=cents, date_text=row["date"], direction=direction,
                accept=lambda item, account_id=account_id, entry_type=entry_type: item["entry_type"] == entry_type
                and item["account_id"] == account_id and "account" not in inbox._jlist(item["guessed"]),
            )
            if side:
                absorbed.append(_absorb(conn, current_user_id, side, table, row["id"]))
        return absorbed

    direction = "IN" if row["type"] == "INCOME" else "OUT"
    match = _exact_pending(
        conn, current_user_id, cents=cents, date_text=row["date"], direction=direction,
        accept=lambda item: item["entry_type"] == row["type"] and item["account_id"] == row["account_id"]
        and "account" not in inbox._jlist(item["guessed"]),
    )
    if match:
        absorbed.append(_absorb(conn, current_user_id, match, table, row["id"]))
    return absorbed


def serialize_target(conn, current_user_id, table, target_id):
    if not table or not target_id:
        return None
    if table == "cc_expenses":
        row = conn.execute(
            "SELECT * FROM cc_expenses WHERE id = ? AND user_id = ?", (target_id, current_user_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM transactions WHERE id = ? AND user_id = ?", (target_id, current_user_id),
        ).fetchone()
    return {"table": table, **row_to_dict(row)} if row else None
