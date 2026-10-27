"""Open Finance -> Aprovar (043): cada transacao da Pluggy vira, no maximo, um
item do Aprovar — nada e gravado sem o dono aprovar.

Duas metades:

1. **Ler a Pluggy** (puro): `normalize_transaction()` tira de uma transacao da
   API o que o app usa — direcao, valor em centavos, data local, parcela, se e
   transferencia ou pagamento de fatura, quem esta do outro lado.
   - Conta (BANK): `type` DEBIT sai, CREDIT entra (o sinal do valor, se faltar
     o tipo). Visto no sandbox: DEBIT negativo, CREDIT positivo.
   - Cartao (CREDIT): nem `type` nem o sinal valem as cegas. A doc da Pluggy
     diz "positivo e debito"; o sandbox manda compras negativas com type
     CREDIT. Cada cartao aprende o sinal de uma compra (`learn_charge_sign()`):
     um pagamento de fatura no pull (categoria 05100000, entrada por
     definicao) decide; senao a maioria (>= 3 transacoes); senao a doc (+).
   - Data: a Pluggy manda AAAA-MM-DDT03:00:00.000Z (sandbox) ou T00:00:00.000Z
     (doc) para "so a data"; outra hora e um instante, convertido para -03:00.
2. **Por no Aprovar** (`ingest()`), reusando services/inbox.py:
   - a mesma compra que uma notificacao ja trouxe e o MESMO item
     (`inbox.notification_item_for_open_finance()`; o contrario, a notificacao
     depois, em `inbox.open_finance_item_for_detection()`);
   - as duas pontas de uma transferencia entre contas do dono (ambas
     conectadas, ou uma notificada) sao UM item TRANSFER (`transfer_partner`);
   - parcela 2..n de uma compra no cartao: COVERED, nunca item — aprovar a
     compra (`POST /api/cc-expenses/purchases`, a parcela 1 com o total) ja
     gera todas, na fatura que `compute_invoice_start()` diz;
   - pagamento de fatura (na conta ou no cartao): nunca lancamento por aqui;
     pagar e so `POST /api/cc-expenses/pay-invoice`;
   - credito no cartao (estorno): item CARD de entrada, vira kind REFUND (033);
   - o resto: item novo, com os lancamentos parecidos ja gravados.
   - A categoria: a regra de importacao do dono pela descricao; senao a da
     Pluggy traduzida (open_finance_categories.py); senao a padrao.
   - Na Corretora (a conta "BTG Investimentos"), so a transferencia com o
     banco vira item (aporte/resgate, 039); o resto e COVERED: as operacoes
     da carteira explicam aquele dinheiro.
   - O pagamento de fatura na conta liga ao pagamento que o app ja tem
     (pay-invoice ou debito automatico), nunca grava outro.

Com o interruptor ligado (044, services/open_finance_auto.py), o item pronto
nao espera o dono: e aprovado na hora. Uma transacao ja gravada sozinha que
muda de valor ou some e corrigida/apagada so se o lancamento esta como nasceu
(`apply_change()` / `apply_vanish()`); editado, fica `conflict`.

Idempotente pela chave `pluggy:<id>` por usuario: puxar de novo, a folga de
dias e reconectar nao duplicam. Uma transacao que some, ou muda de valor,
antes da aprovacao faz o que o Aprovar ja faz quando a fonte some: o item
sai (REMOVED) se nao tiver outra fonte.
"""

import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import statement_import
from db import new_id, row_to_dict, utc_timestamp
from open_finance_categories import expected_type, pluggy_category_name
from services import inbox, review
from services.accounts import category_id_for_name, fetch_category
from services.import_rules import import_rules_for_matching
from source_types import INVOICE_PAYMENT_SOURCE_TYPES, OPEN_FINANCE_SOURCE_TYPE

BRT = timezone(timedelta(hours=-3))
DEDUP_PREFIX = "pluggy:"

INVOICE_PAYMENT_CATEGORY = "05100000"
SELF_TRANSFER_PREFIX = "04"
# Transferencias (Pix, TED, DOC, mesma instituicao, para terceiros...) — o
# boleto (05010000, 05090001) e conta paga, nao transferencia.
TRANSFER_CATEGORIES = {
    "05000000", "05020000", "05030000", "05040000", "05050000", "05060000", "05070000", "05080000",
    "05090000", "05090002", "05090003", "05090004", "05090005",
}
BILL_CATEGORIES = {"05010000", "05090001"}
TRANSFER_METHODS = {"PIX", "TED", "DOC", "TEF", "TRANSFERENCIA_MESMA_INSTITUICAO"}
INVOICE_PAYMENT_TEXT = re.compile(
    r"\b(PAGAMENTO (DE |DA )?FATURA|PAG(TO)? FATURA|PGTO FATURA|PAGAMENTO RECEBIDO|PAGAMENTO EFETUADO|"
    r"PAGTO CARTAO|PAGAMENTO CARTAO|PGTO CARTAO)\b",
)
MIN_SIGN_SAMPLE = 3

STATUS_SKIPPED_PENDING = "pending"
# O pagamento de fatura do banco e o do app: mesmo valor, ate tantos dias.
INVOICE_PAYMENT_LINK_DAYS = 3


class Skip(Exception):
    """A transacao nao entra (pendente, valor zero): o motivo e a mensagem."""


# ---------------------------------------------------------------------------
# Puro: ler a Pluggy
# ---------------------------------------------------------------------------

def to_cents(value):
    """Reais (numero da Pluggy, com sinal) em centavos inteiros, ROUND_HALF_UP
    (o mesmo de rounded_money)."""
    try:
        return int((Decimal(str(value)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise Skip("valor invalido") from exc


def local_moment(text):
    """(data local, occurred_at) de uma data da Pluggy. Meia-noite UTC ou
    meia-noite em -03:00 e "so a data"; outra hora vira AAAA-MM-DDTHH:MM:SS-03:00."""
    raw = str(text or "").strip()
    if not raw:
        raise Skip("sem data")
    if len(raw) == 10:
        datetime.strptime(raw, "%Y-%m-%d")
        return raw, raw
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Skip("data invalida") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    utc = parsed.astimezone(timezone.utc)
    if (utc.hour, utc.minute, utc.second, utc.microsecond) == (0, 0, 0, 0):
        day = utc.strftime("%Y-%m-%d")
        return day, day
    local = parsed.astimezone(BRT)
    day = local.strftime("%Y-%m-%d")
    if (local.hour, local.minute, local.second) == (0, 0, 0):
        return day, day
    return day, local.isoformat(timespec="seconds")


def _digits(value):
    return re.sub(r"\D", "", str(value or ""))


def counterparty_doc(document):
    """Os digitos do documento do outro lado, como a notificacao os da: de um
    CPF so os seis do meio ("***.378.195-**"), para casar com o que o Aprovar
    ja aprendeu (self:doc:); um CNPJ inteiro."""
    value = document.get("value") if isinstance(document, dict) else document
    digits = _digits(value)
    if len(digits) == 11:
        return digits[3:9]
    return digits if 3 <= len(digits) <= 14 else None


def _text(value, limit):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit] or None


def is_invoice_payment(raw):
    if str(raw.get("categoryId") or "") == INVOICE_PAYMENT_CATEGORY:
        return True
    description = inbox.normalized(raw.get("description") or raw.get("descriptionRaw")).upper()
    return bool(INVOICE_PAYMENT_TEXT.search(description))


def movement_of(raw, account_type, direction):
    """TRANSFER, SELF_TRANSFER, INVOICE_PAYMENT ou None."""
    category_id = str(raw.get("categoryId") or "")
    if is_invoice_payment(raw) and (account_type == "BANK") == (direction == "OUT"):
        return "INVOICE_PAYMENT"
    if account_type != "BANK":
        return None
    if category_id.startswith(SELF_TRANSFER_PREFIX):
        return "SELF_TRANSFER"
    payment = raw.get("paymentData") or {}
    method = str(payment.get("paymentMethod") or raw.get("operationType") or "").upper()
    if category_id in BILL_CATEGORIES or method == "BOLETO":
        return None
    if category_id in TRANSFER_CATEGORIES or method in TRANSFER_METHODS:
        return "TRANSFER"
    return None


def learn_charge_sign(transactions, stored_sign=None, stored_source=None):
    """(sinal de uma compra, como foi aprendido) num cartao. Um pagamento de
    fatura e entrada por definicao; sem ele, a maioria (compras sao a maior
    parte de qualquer fatura); sem amostra, o que ja se sabia ou a doc (+)."""
    payments = []
    others = []
    for raw in transactions:
        try:
            cents = to_cents(raw.get("amount"))
        except Skip:
            continue
        if not cents:
            continue
        (payments if is_invoice_payment(raw) else others).append(cents)
    if payments:
        return (-1 if payments[0] > 0 else 1), "payment"
    if stored_source == "payment" and stored_sign:
        return stored_sign, stored_source
    positive = sum(1 for cents in others if cents > 0)
    negative = len(others) - positive
    if len(others) >= MIN_SIGN_SAMPLE and positive != negative:
        return (1 if positive > negative else -1), "majority"
    if stored_sign:
        return stored_sign, stored_source
    return 1, "default"


def normalize_transaction(raw, account_type, charge_sign=1, include_pending=False):
    """Os campos do app de uma transacao da Pluggy, ou Skip."""
    if not isinstance(raw, dict) or not raw.get("id"):
        raise Skip("sem id")
    if not include_pending and str(raw.get("status") or "POSTED").upper() == "PENDING":
        # Ainda nao liquidada (compra na fatura aberta, parcela futura): pula,
        # salvo "Trazer pendentes" (Ajustes); chega de novo quando liquidar.
        # Ligado, a mesma id liquidada atualiza a linha (ingest); uma id nova
        # faz a velha sumir do pull e o item ir para REMOVED (vanish_missing).
        raise Skip(STATUS_SKIPPED_PENDING)
    amount = raw.get("amount")
    currency = str(raw.get("currencyCode") or "BRL").upper()
    if currency != "BRL" and raw.get("amountInAccountCurrency") is not None:
        amount, currency = raw["amountInAccountCurrency"], "BRL"
    signed = to_cents(amount)
    if not signed:
        raise Skip("valor zero")
    if account_type == "CREDIT":
        direction = "OUT" if (signed > 0) == (charge_sign > 0) else "IN"
    else:
        kind = str(raw.get("type") or "").upper()
        direction = {"DEBIT": "OUT", "CREDIT": "IN"}.get(kind) or ("OUT" if signed < 0 else "IN")
    metadata = raw.get("creditCardMetadata") or {}
    installment_number = _positive_int(metadata.get("installmentNumber"))
    total_installments = _positive_int(metadata.get("totalInstallments"))
    if total_installments and total_installments > 72:
        total_installments = None
    cents = abs(signed)
    when = raw.get("date")
    if account_type == "CREDIT" and direction == "OUT":
        # A compra e o dia em que ela foi feita, nao o da parcela na fatura.
        when = metadata.get("purchaseDate") or metadata.get("transactionDateTime") or when
        if total_installments and total_installments > 1 and (installment_number or 1) == 1:
            total = metadata.get("totalAmount")
            # Conectores Open Finance nao mandam totalAmount (doc): parcela x n.
            cents = abs(to_cents(total)) if total not in (None, 0) else cents * total_installments
    date_text, occurred_at = local_moment(when)
    payment = raw.get("paymentData") or {}
    other = (payment.get("receiver") if direction == "OUT" else payment.get("payer")) or {}
    return {
        "pluggy_transaction_id": str(raw["id"]),
        "dedup_key": DEDUP_PREFIX + str(raw["id"]),
        "direction": direction,
        "amount_cents": cents,
        "raw_amount_cents": signed,
        "currency": currency,
        "date": date_text,
        "occurred_at": occurred_at,
        "description": _text(raw.get("description") or raw.get("descriptionRaw"), 200),
        "pluggy_type": _text(raw.get("type"), 20),
        "pluggy_category": _text(raw.get("category"), 120),
        "pluggy_category_id": _text(raw.get("categoryId"), 20),
        "movement": movement_of(raw, account_type, direction),
        "installment_number": installment_number,
        "total_installments": total_installments,
        "counterparty": _text(other.get("name"), 120),
        "counterparty_doc": counterparty_doc(other.get("documentNumber")),
    }


def _positive_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


# ---------------------------------------------------------------------------
# Por no Aprovar
# ---------------------------------------------------------------------------

ROW_FIELDS = (
    "pluggy_transaction_id", "dedup_key", "direction", "amount_cents", "raw_amount_cents", "currency", "date",
    "occurred_at", "description", "pluggy_type", "pluggy_category", "pluggy_category_id", "movement",
    "installment_number", "total_installments", "counterparty", "counterparty_doc",
)


def fetch_row(conn, current_user_id, dedup_key):
    return conn.execute(
        "SELECT * FROM open_finance_transactions WHERE user_id = ? AND dedup_key = ?",
        (current_user_id, dedup_key),
    ).fetchone()


def fetch_account(conn, current_user_id, of_account_id):
    return conn.execute(
        "SELECT * FROM open_finance_accounts WHERE id = ? AND user_id = ?",
        (of_account_id, current_user_id),
    ).fetchone()


def _update_row(conn, current_user_id, row_id, **changes):
    changes["updated_at"] = utc_timestamp()
    assignments = ", ".join(f"{column} = ?" for column in changes)
    conn.execute(
        f"UPDATE open_finance_transactions SET {assignments} WHERE id = ? AND user_id = ?",
        (*changes.values(), row_id, current_user_id),
    )


def mapped_target(account):
    """(entry_type, account_id, card_id) do mapeamento, ou None sem mapeamento."""
    if account["type"] == "CREDIT":
        return ("CARD", None, account["card_id"]) if account["card_id"] else None
    return (None, account["account_id"], None) if account["account_id"] else None


def _entry_type(account, direction):
    if account["type"] == "CREDIT":
        return "CARD"
    return "EXPENSE" if direction == "OUT" else "INCOME"


def ingest(conn, current_user_id, account, tx, rules=None, seen_at=None):
    """Grava (ou reconhece) uma transacao normalizada e a poe no Aprovar.
    Devolve o status: new, merged, matched, denied, covered, invoice_payment,
    unmapped ou known."""
    seen_at = seen_at or utc_timestamp()
    existing = fetch_row(conn, current_user_id, tx["dedup_key"])
    if existing is None:
        row_id = new_id()
        values = {"id": row_id, "user_id": current_user_id, "of_account_id": account["id"], "role": "UNMAPPED",
                  "last_seen_at": seen_at}
        values.update({field: tx[field] for field in ROW_FIELDS})
        conn.execute(
            f"INSERT INTO open_finance_transactions ({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})",
            tuple(values.values()),
        )
        return place(conn, current_user_id, row_to_dict(_by_id(conn, current_user_id, row_id)), account, rules)

    existing = row_to_dict(existing)
    _update_row(conn, current_user_id, existing["id"], last_seen_at=seen_at)
    changed = (existing["amount_cents"], existing["direction"]) != (tx["amount_cents"], tx["direction"])
    if changed:
        if existing["role"] in ("SOURCE", "PAIRED", "MATCHED") and not _item_pending(conn, current_user_id, existing):
            # Ja decidido: so o gravado sozinho e ainda intocado se corrige;
            # o resto fica como esta, apontado na Conferencia.
            return apply_change(conn, current_user_id, existing, tx)
        if existing["role"] == "SOURCE":
            vanish(conn, current_user_id, existing, reason="changed")
        _update_row(
            conn, current_user_id, existing["id"], role="UNMAPPED", item_id=None, target_table=None, target_id=None,
            **{field: tx[field] for field in ROW_FIELDS if field != "dedup_key"},
        )
        return place(conn, current_user_id, row_to_dict(_by_id(conn, current_user_id, existing["id"])), account, rules)
    details = {field: tx[field] for field in ROW_FIELDS if field != "dedup_key" and existing[field] != tx[field]}
    if details:
        # Mesmo valor, outros detalhes (a pendente que liquidou): a linha
        # acompanha; o item do Aprovar fica como o dono o deixou.
        _update_row(conn, current_user_id, existing["id"], **details)
        existing.update(details)
    if existing["role"] == "REMOVED" or (existing["role"] == "UNMAPPED" and mapped_target(account)):
        return place(conn, current_user_id, existing, account, rules)
    return "known"


def _by_id(conn, current_user_id, row_id):
    return conn.execute(
        "SELECT * FROM open_finance_transactions WHERE id = ? AND user_id = ?", (row_id, current_user_id),
    ).fetchone()


def _item_pending(conn, current_user_id, row):
    if not row.get("item_id"):
        return True
    item = inbox.fetch_item(conn, current_user_id, row["item_id"])
    return bool(item) and item["state"] == inbox.PENDING


def place(conn, current_user_id, row, account, rules=None):
    """Decide o papel de uma linha ja gravada e liga ao item certo."""
    target = mapped_target(account)
    if target is None:
        _update_row(conn, current_user_id, row["id"], role="UNMAPPED", item_id=None)
        return "unmapped"
    if row["movement"] == "INVOICE_PAYMENT":
        link = invoice_payment_link(conn, current_user_id, row, account) if account["type"] == "BANK" else None
        _update_row(
            conn, current_user_id, row["id"], role="INVOICE_PAYMENT", item_id=None,
            target_table="transactions" if link else None, target_id=link,
        )
        return "invoice_payment"
    if (
        account["type"] == "BANK" and row["movement"] not in ("TRANSFER", "SELF_TRANSFER")
        and is_brokerage(conn, current_user_id, account["account_id"])
    ):
        # O caixa da carteira: compra, venda, taxa, provento ja tem o caminho
        # deles (as operacoes e os proventos gravam o lancamento na Corretora).
        _update_row(conn, current_user_id, row["id"], role="COVERED", item_id=None)
        return "covered"
    if account["type"] == "CREDIT" and row["direction"] == "OUT" and (row["installment_number"] or 1) > 1:
        _update_row(conn, current_user_id, row["id"], role="COVERED", item_id=None)
        return "covered"

    entry_type = _entry_type(account, row["direction"])
    _, account_id, card_id = target
    cents = int(row["amount_cents"])

    # 1. Uma notificacao ja trouxe este movimento: o mesmo item.
    partner = inbox.notification_item_for_open_finance(
        conn, current_user_id, entry_type=entry_type, direction=row["direction"], cents=cents,
        date_text=row["date"], account_id=account_id, card_id=card_id,
    )
    if partner:
        return _join_item(conn, current_user_id, row, inbox.item_dict(partner), entry_type, account_id, card_id)

    # 2. A outra ponta de uma transferencia entre contas do dono.
    if account["type"] == "BANK" and row["movement"] in ("TRANSFER", "SELF_TRANSFER"):
        approved = inbox.approved_transfer_awaiting(
            conn, current_user_id, account_id=account_id, direction=row["direction"], cents=cents,
            date_text=row["date"],
        )
        if approved:
            _update_row(
                conn, current_user_id, row["id"], role="MATCHED", item_id=approved["id"],
                target_table="transactions", target_id=approved["target_id"],
            )
            return "matched"
        other = inbox.transfer_partner(
            conn, current_user_id, account_id=account_id, direction=row["direction"], cents=cents,
            date_text=row["date"], detection={"counterparty": row["counterparty"], "counterparty_doc": row["counterparty_doc"]},
        )
        if other and _is_movement_item(conn, current_user_id, other):
            _update_row(conn, current_user_id, row["id"], role="SOURCE", item_id=other["id"])
            inbox.make_transfer(
                conn, current_user_id, inbox.item_dict(other), account_id=account_id, direction=row["direction"],
            )
            return "merged"

    # 3. Um item novo.
    new_item_for_row(conn, current_user_id, row, account, rules)
    return "new"


def _is_movement_item(conn, current_user_id, item_row):
    """So uma transferencia junta com transferencia: o item tem uma fonte que
    e Pix/TED (notificacao ou Open Finance), ou ja e uma transferencia."""
    if item_row["entry_type"] == "TRANSFER":
        return True
    for detection in inbox.item_detections(conn, current_user_id, item_row["id"]):
        if detection["role"] == inbox.SOURCE and detection["kind"] in inbox.MOVEMENT_KINDS:
            return True
    return any(
        source["movement"] in ("TRANSFER", "SELF_TRANSFER")
        for source in inbox.open_finance_sources(conn, current_user_id, item_row["id"], roles=(inbox.SOURCE,))
    )


def _join_item(conn, current_user_id, row, item, entry_type, account_id, card_id):
    """A transacao entra no item que a notificacao abriu. Pendente: o
    cartao/conta do mapeamento (certo) entra onde o dono nao escolheu, e o que
    era palpite deixa de ser."""
    if item["state"] == inbox.APPROVED and item.get("auto_recorded_at"):
        return reconcile_recorded(conn, current_user_id, row, item, entry_type, account_id, card_id)
    if item["state"] != inbox.PENDING:
        role = "PAIRED" if item["state"] == inbox.DENIED else "MATCHED"
        _update_row(
            conn, current_user_id, row["id"], role=role, item_id=item["id"],
            target_table=item.get("target_table"), target_id=item.get("target_id"),
        )
        return "denied" if role == "PAIRED" else "matched"
    _update_row(conn, current_user_id, row["id"], role="SOURCE", item_id=item["id"])
    edited = set(item.get("edited") or [])
    changes = {}
    if item["entry_type"] == "TRANSFER":
        field, need = ("account_id", "account") if row["direction"] == "OUT" else ("transfer_account_id", "transfer_account")
        if field not in edited:
            changes[field] = account_id
            changes["guessed"] = [guess for guess in item.get("guessed") or [] if guess != need]
    elif not ({"entry_type", "card_id", "account_id"} & edited):
        if entry_type == "CARD":
            changes.update({"entry_type": "CARD", "card_id": card_id, "account_id": None})
            if row["direction"] == "IN":
                changes["recurring_off"] = 1
        else:
            changes.update({"entry_type": entry_type, "account_id": account_id, "card_id": None})
        changes["guessed"] = [guess for guess in item.get("guessed") or [] if guess not in ("card", "account")]
    if changes:
        merged = {**item, **changes}
        changes["needs"] = inbox.recompute_needs(merged)
        inbox.save_item(conn, current_user_id, item, changes)
    return "merged"


# ---------------------------------------------------------------------------
# Conferencia do que a notificacao gravou (045)
# ---------------------------------------------------------------------------

def notification_untouched(conn, current_user_id, item):
    """O lancamento que a notificacao gravou sozinha esta como nasceu e ainda
    a revisar (revisado, o dono ja disse que esta certo: o banco nao o refaz)."""
    table, target_id = item.get("target_table"), item.get("target_id")
    if not item.get("recorded_snapshot") or not review.awaiting(conn, current_user_id, table, target_id):
        return False
    try:
        recorded = json.loads(item["recorded_snapshot"])
    except (TypeError, ValueError):
        return False
    return target_snapshot(conn, current_user_id, table, target_id) == recorded


def bank_disagrees(item, row, entry_type, account_id, card_id):
    """O banco diz outra data ou outra conta/cartao do que a notificacao gravou."""
    if inbox.date_of(item["occurred_at"]) != row["date"]:
        return True
    if entry_type == "CARD":
        return item["entry_type"] != "CARD" or item.get("card_id") != card_id
    return item["entry_type"] != entry_type or item.get("account_id") != account_id


def _drop_target(conn, current_user_id, item):
    table, target_id = item["target_table"], item["target_id"]
    conn.execute(
        "DELETE FROM recurring_settlements WHERE user_id = ? AND target_table = ? AND target_id = ?",
        (current_user_id, table, target_id),
    )
    if table == "transactions":
        conn.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (target_id, current_user_id))
    else:
        conn.execute(
            """
            DELETE FROM cc_expenses
            WHERE user_id = ? AND client_id = (SELECT client_id FROM cc_expenses WHERE id = ? AND user_id = ?)
            """,
            (current_user_id, target_id, current_user_id),
        )
    conn.execute(
        "UPDATE notify_detections SET target_table = NULL, target_id = NULL WHERE user_id = ? AND item_id = ?",
        (current_user_id, item["id"]),
    )


def reconcile_recorded(conn, current_user_id, row, item, entry_type, account_id, card_id):
    """A transacao da Pluggy e o movimento que uma notificacao ja gravou
    sozinha. Nunca vira um segundo lancamento:

    - intocado e o banco concorda: a transacao passa a ser a fonte do
      lancamento (origem OPEN_FINANCE, o snapshot), e o que o banco mudar
      depois corrige como no gravado pela Pluggy (apply_change/apply_vanish);
    - intocado e o banco diz outra data ou conta/cartao: o lancamento sai e o
      item volta a esperar com o que o banco diz; a passada da Pluggy logo
      depois do pull o grava de novo, a revisar;
    - revisado ou editado (ou uma transferencia): so liga (MATCHED); a
      Conferencia aponta o que nao bater.
    """
    table, target_id = item["target_table"], item["target_id"]
    if item["entry_type"] == "TRANSFER" or not notification_untouched(conn, current_user_id, item):
        _update_row(
            conn, current_user_id, row["id"], role="MATCHED", item_id=item["id"],
            target_table=table, target_id=target_id,
        )
        return "matched"
    if bank_disagrees(item, row, entry_type, account_id, card_id):
        _drop_target(conn, current_user_id, item)
        _update_row(conn, current_user_id, row["id"], role="SOURCE", item_id=item["id"], target_table=None, target_id=None)
        changes = {
            "state": inbox.PENDING, "target_table": None, "target_id": None, "decided_at": None,
            "auto_recorded_at": None, "recorded_snapshot": None, "occurred_at": row["occurred_at"] or row["date"],
            "client_key": row["dedup_key"],
            "guessed": [guess for guess in item.get("guessed") or [] if guess not in ("card", "account")],
        }
        if entry_type == "CARD":
            changes.update({"entry_type": "CARD", "card_id": card_id, "account_id": None})
        else:
            changes.update({"entry_type": entry_type, "account_id": account_id, "card_id": None})
        if changes["entry_type"] != item["entry_type"]:
            changes["category"], changes["category_id"] = category_for_row(
                conn, current_user_id, row, changes["entry_type"], item["amount"], changes["account_id"],
            )
        changes["needs"] = inbox.recompute_needs({**item, **changes})
        inbox.save_item(conn, current_user_id, item, changes)
        return "merged"
    _update_row(conn, current_user_id, row["id"], role="SOURCE", item_id=item["id"], target_table=table, target_id=target_id)
    if table == "transactions":
        conn.execute(
            "UPDATE transactions SET source_type = ?, source_id = ? WHERE id = ? AND user_id = ? AND source_type IS NULL",
            (OPEN_FINANCE_SOURCE_TYPE, row["pluggy_transaction_id"], target_id, current_user_id),
        )
    else:
        conn.execute(
            """
            UPDATE cc_expenses SET client_id = ?
            WHERE user_id = ? AND client_id = (SELECT client_id FROM cc_expenses WHERE id = ? AND user_id = ?)
            """,
            (row["dedup_key"], current_user_id, target_id, current_user_id),
        )
    mark_auto_recorded(conn, current_user_id, item["id"], table, target_id)
    return "matched"


def new_item_for_row(conn, current_user_id, row, account=None, rules=None):
    """Abre um item so desta transacao (tambem o "nao e a mesma" do split)."""
    row = row_to_dict(row) if not isinstance(row, dict) else row
    if account is None:
        account = fetch_account(conn, current_user_id, row["of_account_id"])
    entry_type = _entry_type(account, row["direction"])
    direction = row["direction"]
    account_id = account["account_id"] if entry_type != "CARD" else None
    card_id = account["card_id"] if entry_type == "CARD" else None
    cents = int(row["amount_cents"])
    amount = inbox._reais(cents)
    candidates = inbox.existing_rows(
        conn, current_user_id, entry_type=entry_type, direction=direction, cents=cents, date_text=row["date"],
        account_id=account_id, card_id=card_id, for_notification=True,
    )
    installments = int(row["total_installments"] or 1) if entry_type == "CARD" and direction == "OUT" else 1
    values = {
        "reason": "several_candidates" if len(candidates) > 1 else ("possible_duplicate" if candidates else "new"),
        "entry_type": entry_type,
        "direction": direction,
        "amount": amount,
        "currency": row["currency"],
        "installments": installments,
        "occurred_at": row["occurred_at"],
        "description": row["description"],
        "account_id": account_id,
        "card_id": card_id,
        "transfer_account_id": None,
        "guessed": [],
        "candidates": candidates,
        "client_key": row["dedup_key"],
    }
    if entry_type == "CARD" and direction == "IN":
        # Estorno (033): a categoria "Estorno", e nunca a ocorrencia de uma
        # recorrencia de despesa.
        values["category"] = "Estorno"
        values["category_id"] = category_id_for_name(conn, current_user_id, "Estorno")
        values["recurring_off"] = 1
    elif entry_type != "CARD" and row["movement"] in ("TRANSFER", "SELF_TRANSFER"):
        hint = inbox.remembered_transfer(
            conn, current_user_id, account_id=account_id, direction=direction, description=row["description"],
        )
        own = hint is not None or row["movement"] == "SELF_TRANSFER" or _is_self(conn, current_user_id, row)
        if own:
            other = hint["transfer_account_id"] if hint else None
            origin, destination = (account_id, other) if direction == "OUT" else (other, account_id)
            values.update({
                "entry_type": "TRANSFER",
                "direction": "OUT",
                "account_id": origin,
                "transfer_account_id": destination,
                "reason": "own_transfer" if values["reason"] == "new" else values["reason"],
                "description": inbox._transfer_description(conn, current_user_id, origin, destination, row["description"]),
            })
        elif (row["counterparty"] or row["counterparty_doc"]) and values["reason"] == "new":
            values["reason"] = "external_transfer"
    if "category" not in values:
        values["category"], values["category_id"] = category_for_row(
            conn, current_user_id, row, values["entry_type"], amount, values["account_id"], rules,
        )
    values["needs"] = inbox.recompute_needs(values)
    item_id = inbox.insert_item(conn, current_user_id, values)
    _update_row(conn, current_user_id, row["id"], role="SOURCE", item_id=item_id, target_table=None, target_id=None)
    return item_id


def category_for_row(conn, current_user_id, row, entry_type, amount, account_id=None, rules=None):
    """(nome, id): a regra do dono pela descricao; senao a categoria da Pluggy
    traduzida, se o dono tem uma ativa com esse nome; senao a padrao."""
    if entry_type == "TRANSFER":
        return inbox.TRANSFER_CATEGORY, None
    transaction_type = "INCOME" if entry_type == "INCOME" else "EXPENSE"
    if rules is None:
        rules = import_rules_for_matching(conn, current_user_id)
    rule = statement_import.first_matching_rule(
        rules, row.get("description") or "", transaction_type, amount, account_id if entry_type != "CARD" else None,
    )
    if rule:
        return rule["category"], rule["category_id"]
    name = pluggy_category_name(row.get("pluggy_category_id"))
    if name and expected_type(name) == transaction_type:
        category_id = category_id_for_name(conn, current_user_id, name)
        category = fetch_category(conn, current_user_id, category_id) if category_id else None
        if category and not category["archived_at"]:
            return name, category_id
    return inbox.suggest_category(conn, current_user_id, None, entry_type, amount, account_id, rules=[])


def is_brokerage(conn, current_user_id, account_id):
    if not account_id:
        return False
    row = conn.execute(
        "SELECT type FROM accounts WHERE id = ? AND user_id = ?", (account_id, current_user_id),
    ).fetchone()
    return bool(row) and row["type"] == "BROKERAGE"


def invoice_payment_link(conn, current_user_id, row, account):
    """O pagamento de fatura que o app ja tem para esta saida do banco (o
    pay-invoice ou o debito automatico, na conta mapeada, mesmo valor, ate
    INVOICE_PAYMENT_LINK_DAYS dias) e que nenhuma outra transacao explica."""
    if row["direction"] != "OUT" or not account["account_id"]:
        return None
    kinds = sorted(INVOICE_PAYMENT_SOURCE_TYPES)
    found = conn.execute(
        f"""
        SELECT t.id, t.date FROM transactions t
        WHERE t.user_id = ? AND t.account_id = ? AND t.source_type IN ({', '.join('?' for _ in kinds)})
          AND CAST(ROUND(t.amount * 100) AS INTEGER) = ? AND t.date BETWEEN ? AND ?
          AND NOT EXISTS (
              SELECT 1 FROM open_finance_transactions o
              WHERE o.user_id = t.user_id AND o.target_table = 'transactions' AND o.target_id = t.id
                AND o.id <> ? AND o.role <> 'REMOVED'
          )
        """,
        (
            current_user_id, account["account_id"], *kinds, int(row["amount_cents"]),
            inbox._shift(row["date"], -INVOICE_PAYMENT_LINK_DAYS), inbox._shift(row["date"], INVOICE_PAYMENT_LINK_DAYS),
            row["id"],
        ),
    ).fetchall()
    found = sorted(found, key=lambda entry: (inbox._date_gap(entry["date"], row["date"]), entry["date"], entry["id"]))
    return found[0]["id"] if found else None


def _is_self(conn, current_user_id, row):
    """O outro lado e o proprio dono, aprendido no Aprovar (031): pelo
    documento quando a Pluggy o da; pelo nome so sem documento."""
    if row["counterparty_doc"]:
        return inbox.fetch_hint(conn, current_user_id, inbox.SELF_DOC_PREFIX + row["counterparty_doc"]) is not None
    name = inbox.normalized(row["counterparty"])
    return bool(name) and inbox.fetch_hint(conn, current_user_id, inbox.SELF_NAME_PREFIX + name) is not None


def vanish(conn, current_user_id, row, reason="vanished"):
    """A transacao sumiu da Pluggy (ou mudou de valor) antes da aprovacao: a
    linha sai e, sem outra fonte viva, o item tambem (REMOVED) — o mesmo que o
    Aprovar faz com a compra que o banco negou. Um item ja decidido fica."""
    item_id = row.get("item_id")
    if item_id and not _item_pending(conn, current_user_id, row):
        return False
    _update_row(conn, current_user_id, row["id"], role="REMOVED")
    if not item_id:
        return True
    item_row = inbox.fetch_item(conn, current_user_id, item_id)
    if item_row and item_row["state"] == inbox.PENDING and not inbox._has_detection_source(conn, current_user_id, item_id):
        inbox.save_item(
            conn, current_user_id, inbox.item_dict(item_row),
            {"state": inbox.REMOVED, "reason": reason, "decided_at": utc_timestamp()},
        )
    return True


def vanish_missing(conn, current_user_id, account, seen_ids, date_from, date_to):
    """Depois de um pull de [date_from, date_to]: o que estava pendente nessa
    janela e a Pluggy nao devolveu mais, sumiu. O que ja foi gravado sozinho
    passa pela guarda de apply_vanish() (so sai se o dono nunca o tocou); um
    pull que voltou vazio nao apaga nada gravado: pode ser a Pluggy, nao o banco."""
    rows = conn.execute(
        """
        SELECT * FROM open_finance_transactions
        WHERE user_id = ? AND of_account_id = ? AND date BETWEEN ? AND ?
          AND role IN ('SOURCE', 'UNMAPPED')
        """,
        (current_user_id, account["id"], date_from, date_to),
    ).fetchall()
    count = 0
    for row in rows:
        if row["pluggy_transaction_id"] in seen_ids:
            continue
        row = row_to_dict(row)
        if row["auto_recorded_at"] and not _item_pending(conn, current_user_id, row):
            if seen_ids and apply_vanish(conn, current_user_id, row) == "removed":
                count += 1
            continue
        if vanish(conn, current_user_id, row):
            count += 1
    return count


# ---------------------------------------------------------------------------
# O que foi gravado sozinho (044): como nasceu, e a guarda de mudanca
# ---------------------------------------------------------------------------

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
            f"SELECT {', '.join(TRANSACTION_SNAPSHOT_COLUMNS)} FROM transactions WHERE id = ? AND user_id = ?",
            (target_id, current_user_id),
        ).fetchone()
        if not row:
            return None
        snapshot = {column: row[column] for column in TRANSACTION_SNAPSHOT_COLUMNS}
        snapshot["amount"] = _snapshot_cents(snapshot["amount"])
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


def mark_auto_recorded(conn, current_user_id, item_id, table, target_id, stamp=None):
    """As fontes de um item que o app gravou sozinho guardam como o lancamento
    nasceu. (A ocorrencia de recorrencia que a aprovacao deu ja esta no snapshot.)"""
    conn.execute(
        """
        UPDATE open_finance_transactions SET auto_recorded_at = ?, recorded_snapshot = ?, updated_at = ?
        WHERE user_id = ? AND item_id = ? AND role = 'SOURCE'
        """,
        (stamp or utc_timestamp(), _dump(target_snapshot(conn, current_user_id, table, target_id)), utc_timestamp(),
         current_user_id, item_id),
    )


def untouched(conn, current_user_id, row):
    """O lancamento que esta transacao gravou sozinha esta como nasceu."""
    if not row.get("auto_recorded_at") or not row.get("recorded_snapshot") or not row.get("target_id"):
        return False
    try:
        recorded = json.loads(row["recorded_snapshot"])
    except (TypeError, ValueError):
        return False
    current = target_snapshot(conn, current_user_id, row["target_table"], row["target_id"])
    return current is not None and current == recorded


def own_target(conn, current_user_id, row):
    """O lancamento foi gravado por esta transacao (nunca um digitado pelo dono
    que ela so ligou): a origem dele e ela."""
    if row.get("target_table") == "transactions":
        target = conn.execute(
            "SELECT source_type, source_id FROM transactions WHERE id = ? AND user_id = ?",
            (row["target_id"], current_user_id),
        ).fetchone()
        return bool(target) and (target["source_type"], target["source_id"]) == (
            OPEN_FINANCE_SOURCE_TYPE, row["pluggy_transaction_id"],
        )
    if row.get("target_table") == "cc_expenses":
        target = conn.execute(
            "SELECT client_id FROM cc_expenses WHERE id = ? AND user_id = ?", (row["target_id"], current_user_id),
        ).fetchone()
        return bool(target) and target["client_id"] == row["dedup_key"]
    return False


def _flag(conn, current_user_id, row, conflict, cents=None):
    _update_row(conn, current_user_id, row["id"], conflict=conflict, conflict_amount_cents=cents)
    return "conflict"


def apply_change(conn, current_user_id, row, tx):
    """O banco mudou o valor de uma transacao ja decidida. Gravada sozinha,
    intocada, na mesma direcao e de uma linha so (um lancamento, ou uma compra
    1/1 em aberto): o lancamento acompanha. Senao nada muda e a Conferencia
    aponta (`conflict = 'changed'`)."""
    if (
        tx["direction"] != row["direction"]
        or not untouched(conn, current_user_id, row)
        or not own_target(conn, current_user_id, row)
    ):
        return _flag(conn, current_user_id, row, "changed", tx["amount_cents"])
    amount = inbox._reais(tx["amount_cents"])
    if row["target_table"] == "transactions":
        conn.execute(
            "UPDATE transactions SET amount = ? WHERE id = ? AND user_id = ?",
            (amount, row["target_id"], current_user_id),
        )
    else:
        rows = conn.execute(
            "SELECT id, status FROM cc_expenses WHERE user_id = ? AND client_id = ?",
            (current_user_id, row["dedup_key"]),
        ).fetchall()
        if len(rows) != 1 or rows[0]["status"] != "OPEN":
            return _flag(conn, current_user_id, row, "changed", tx["amount_cents"])
        conn.execute(
            "UPDATE cc_expenses SET amount = ? WHERE id = ? AND user_id = ?", (amount, rows[0]["id"], current_user_id),
        )
    if row.get("item_id"):
        item_row = inbox.fetch_item(conn, current_user_id, row["item_id"])
        if item_row:
            inbox.save_item(conn, current_user_id, inbox.item_dict(item_row), {"amount": amount})
    _update_row(
        conn, current_user_id, row["id"], conflict=None, conflict_amount_cents=None,
        recorded_snapshot=_dump(target_snapshot(conn, current_user_id, row["target_table"], row["target_id"])),
        **{field: tx[field] for field in ROW_FIELDS if field != "dedup_key"},
    )
    return "corrected"


def apply_vanish(conn, current_user_id, row):
    """A transacao gravada sozinha sumiu do banco. Intocada e de quem ela
    gravou — nunca um digitado, nunca uma transferencia, nunca uma compra com
    parcela ja paga: o lancamento sai. Senao fica (`conflict = 'vanished'`)."""
    if row.get("conflict") == "vanished":
        return "conflict"
    removable = untouched(conn, current_user_id, row) and own_target(conn, current_user_id, row)
    if removable and row["target_table"] == "transactions":
        kind = conn.execute(
            "SELECT type FROM transactions WHERE id = ? AND user_id = ?", (row["target_id"], current_user_id),
        ).fetchone()
        removable = bool(kind) and kind["type"] != "TRANSFER"
    if removable and row["target_table"] == "cc_expenses":
        removable = not conn.execute(
            "SELECT 1 FROM cc_expenses WHERE user_id = ? AND client_id = ? AND status <> 'OPEN'",
            (current_user_id, row["dedup_key"]),
        ).fetchone()
    if not removable:
        return _flag(conn, current_user_id, row, "vanished")
    # A ocorrencia de recorrencia que a aprovacao deu volta a ficar em aberto.
    conn.execute(
        "DELETE FROM recurring_settlements WHERE user_id = ? AND target_table = ? AND target_id = ?",
        (current_user_id, row["target_table"], row["target_id"]),
    )
    if row["target_table"] == "transactions":
        conn.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (row["target_id"], current_user_id))
    else:
        conn.execute("DELETE FROM cc_expenses WHERE user_id = ? AND client_id = ?", (current_user_id, row["dedup_key"]))
    _update_row(conn, current_user_id, row["id"], role="REMOVED", target_table=None, target_id=None)
    if row.get("item_id"):
        item_row = inbox.fetch_item(conn, current_user_id, row["item_id"])
        if item_row:
            inbox.save_item(
                conn, current_user_id, inbox.item_dict(item_row),
                {"state": inbox.REMOVED, "reason": "vanished", "target_table": None, "target_id": None,
                 "decided_at": utc_timestamp()},
            )
    return "removed"


def place_unmapped(conn, current_user_id, account, rules=None):
    """Mapeada a conta, o que ja foi puxado sem mapeamento entra no Aprovar."""
    rows = conn.execute(
        "SELECT * FROM open_finance_transactions WHERE user_id = ? AND of_account_id = ? AND role = 'UNMAPPED'"
        " ORDER BY date, created_at, id",
        (current_user_id, account["id"]),
    ).fetchall()
    return [place(conn, current_user_id, row_to_dict(row), account, rules) for row in rows]
