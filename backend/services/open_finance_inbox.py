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
   - pagamento de fatura (na conta ou no cartao): nunca despesa; na conta ele
     paga a fatura depois do pull (services/open_finance_invoices.py);
   - credito no cartao (estorno): item CARD de entrada, vira kind REFUND (033);
   - o resto: item novo, com os lancamentos parecidos ja gravados.
   - A categoria: a regra de importacao do dono pela descricao; senao a da
     Pluggy traduzida (open_finance_categories.py); senao a padrao.
   - Na Corretora (a conta "BTG Investimentos"), so a transferencia com o
     banco vira item (aporte/resgate, 039); o resto e do caixa da carteira
     (services/broker_statement.py): as operacoes explicam o bruto do pregao,
     o resto vira linha, e o saldo da Corretora fica o do banco.
   - O pagamento de fatura na conta liga ao pagamento que o app ja tem
     (pay-invoice), nunca grava outro; sem ele, o pull o grava pela baixa da
     fatura (services/open_finance_invoices.py).

Com o interruptor ligado (044, services/open_finance_auto.py), o item pronto
nao espera o dono: e aprovado na hora. Uma transacao ja gravada sozinha que
muda de valor ou some e corrigida/apagada so se o lancamento esta como nasceu
(`apply_change()` / `apply_vanish()`); editado, fica `conflict`.

Idempotente pela chave `pluggy:<id>` por usuario: puxar de novo, a folga de
dias e reconectar nao duplicam. Uma transacao que some, ou muda de valor,
antes da aprovacao faz o que o Aprovar ja faz quando a fonte some: o item
sai (REMOVED) se nao tiver outra fonte.
"""

import calendar
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import statement_import
from db import new_id, row_to_dict, utc_timestamp
from open_finance_categories import (
    cnae_categories,
    display_name,
    expected_type,
    keyword_categories,
    plain_text,
    pluggy_category_names,
)
from services import broker_statement, global_account, inbox, review
from services.accounts import category_id_for_name, fetch_category
from services.import_rules import import_rules_for_matching
from source_types import BANK_INVESTMENT_SOURCE_TYPE, INVOICE_PAYMENT_SOURCE_TYPES, OPEN_FINANCE_SOURCE_TYPE

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
    r"PAGTO CARTAO|PAGAMENTO CARTAO|PGTO CARTAO|CARDBANKSLIP|PGTO\s+DEBITO CONTA|PGTO\s+CASH)\b",
)
# Dinheiro que entra como renda (01 na arvore da Pluggy, ou o texto do banco):
# um salario por TED nunca e transferencia entre contas do dono.
INCOME_CATEGORY_PREFIX = "01"
SALARY_TEXT = re.compile(r"SALARI|SALARY|\b(FOLHA|HOLERITE|VENCIMENTOS|PRO LABORE)\b")
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


def is_income_row(raw):
    if str(raw.get("categoryId") or "").startswith(INCOME_CATEGORY_PREFIX):
        return True
    return bool(SALARY_TEXT.search(inbox.normalized(raw.get("description") or raw.get("descriptionRaw")).upper()))


def movement_of(raw, account_type, direction):
    """TRANSFER, SELF_TRANSFER, INVOICE_PAYMENT ou None."""
    category_id = str(raw.get("categoryId") or "")
    if is_invoice_payment(raw) and (account_type == "BANK") == (direction == "OUT"):
        return "INVOICE_PAYMENT"
    if account_type != "BANK":
        return None
    if direction == "IN" and is_income_row(raw):
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


def normalize_transaction(raw, account_type, charge_sign=1, include_pending=False, account_currency="BRL"):
    """Os campos do app de uma transacao da Pluggy, ou Skip.

    O valor fica na moeda da conta: a compra no exterior de um cartao em reais
    vem em `amountInAccountCurrency`; na conta global (USD) o valor em dolar ja
    e o da conta e nunca vira real."""
    if not isinstance(raw, dict) or not raw.get("id"):
        raise Skip("sem id")
    if not include_pending and str(raw.get("status") or "POSTED").upper() == "PENDING":
        # Ainda nao liquidada (compra na fatura aberta, parcela futura): pula,
        # salvo "Trazer pendentes" (Ajustes); chega de novo quando liquidar.
        # Ligado, a mesma id liquidada atualiza a linha (ingest); uma id nova
        # faz a velha sumir do pull e o item ir para REMOVED (vanish_missing).
        raise Skip(STATUS_SKIPPED_PENDING)
    amount = raw.get("amount")
    account_currency = str(account_currency or "BRL").upper()
    currency = str(raw.get("currencyCode") or account_currency).upper()
    if currency != account_currency and raw.get("amountInAccountCurrency") is not None:
        amount, currency = raw["amountInAccountCurrency"], account_currency
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
    merchant = raw.get("merchant") if isinstance(raw.get("merchant"), dict) else {}
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
        "merchant_name": _text(merchant.get("name") or merchant.get("businessName"), 120),
        "merchant_cnpj": _digits(merchant.get("cnpj"))[:14] or None,
        "merchant_cnae": _digits(merchant.get("cnae"))[:7] or None,
        "posted_on": local_moment(raw.get("date"))[0] if raw.get("date") else date_text,
        "bill_month": _bill_month(metadata.get("billForecastDate")),
    }


def _bill_month(value):
    text = str(value or "")[:7]
    return text if re.fullmatch(r"\d{4}-\d{2}", text) else None


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
    "installment_number", "total_installments", "counterparty", "counterparty_doc", "merchant_name",
    "merchant_cnpj", "merchant_cnae", "posted_on", "bill_month",
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
    if changed and existing["role"] == "INVOICE_PAYMENT" and existing["target_id"]:
        return apply_payment_change(conn, current_user_id, existing, tx)
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
        account["type"] == "BANK" and not is_broker_transfer(row)
        and is_brokerage(conn, current_user_id, account["account_id"])
    ):
        # O caixa da carteira (services/broker_statement.py): compra, venda e
        # provento ja tem o caminho deles; a taxa, o IR e a renda fixa viram linha.
        role, entry = broker_statement.settle_line(conn, current_user_id, row, account["account_id"])
        _update_row(
            conn, current_user_id, row["id"], role=role, item_id=None,
            target_table="transactions" if entry else None, target_id=entry,
        )
        return "matched" if entry else "covered"
    if account["type"] == "CREDIT" and row["direction"] == "OUT" and (row["installment_number"] or 1) > 1:
        _update_row(conn, current_user_id, row["id"], role="COVERED", item_id=None)
        return "covered"
    if account["type"] == "BANK" and is_auto_invest_row(row):
        if inbox.is_auto_invest(row["description"]) or not SOLD_INVESTMENT_TEXT.search(inbox.normalized(row["description"])):
            # A aplicacao automatica (Rende Facil, conta remunerada): nunca no app,
            # nem na conferencia.
            _update_row(conn, current_user_id, row["id"], role="COVERED", item_id=None)
            return "covered"
        # O resgate de outra aplicacao (Tesouro Reserva) e dinheiro de verdade.
        entry = broker_statement.write_line(conn, current_user_id, row, account["account_id"])
        _update_row(conn, current_user_id, row["id"], role="MATCHED", item_id=None, target_table="transactions", target_id=entry)
        return "matched"

    entry_type = _entry_type(account, row["direction"])
    _, account_id, card_id = target
    cents = int(row["amount_cents"])

    # 1. Uma notificacao ja trouxe este movimento: o mesmo item.
    partner = inbox.notification_item_for_open_finance(
        conn, current_user_id, entry_type=entry_type, direction=row["direction"], cents=cents,
        date_text=row["date"], account_id=account_id, card_id=card_id,
        rounds_up=inbox.open_finance_rounds_up(conn, current_user_id, account["id"]),
    )
    if partner:
        return _join_item(conn, current_user_id, row, inbox.item_dict(partner), entry_type, account_id, card_id)

    # 1b. Uma transferencia que o app ja tem com uma conta sem Pluggy (a Flash):
    #     esta transacao e a ponta do banco dela, nunca um segundo movimento.
    if account["type"] == "BANK":
        recorded = recorded_transfer_for_row(conn, current_user_id, row, account_id, cents)
        if recorded:
            _update_row(
                conn, current_user_id, row["id"], role="MATCHED", item_id=None,
                target_table="transactions", target_id=recorded,
            )
            return "matched"

    # 2. A outra ponta de uma transferencia para a conta global (em dolar):
    #    o par e pela contraparte e pelo dia, nunca pelos centavos.
    if account["type"] == "BANK":
        crossed = _place_cross_currency(conn, current_user_id, row, account_id, cents)
        if crossed:
            return crossed

    # 3. A outra ponta de uma transferencia entre contas do dono.
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

    # 4. Um item novo.
    new_item_for_row(conn, current_user_id, row, account, rules)
    return "new"


def recorded_transfer_for_row(conn, current_user_id, row, account_id, cents):
    """A transferencia ja gravada (esta conta deste lado, mesmo valor, ate
    TRANSFER_MATCH_DAYS dias) que so espera esta ponta: a outra conta nao tem
    Pluggy, entao ela nunca vem, ou o dono apontou como transferencia uma linha
    que a Pluggy trouxe da outra ponta. Uma por transacao: a que nenhuma outra
    deste lado ja explica."""
    if row["direction"] == "OUT":
        side, other, value = "t.account_id", "t.transfer_account_id", "t.amount"
    else:
        side, other, value = "t.transfer_account_id", "t.account_id", "COALESCE(t.transfer_amount, t.amount)"
    found = conn.execute(
        f"""
        SELECT t.id, t.date FROM transactions t
        WHERE t.user_id = ? AND t.type = 'TRANSFER' AND {side} = ? AND {other} IS NOT NULL
          AND CAST(ROUND({value} * 100) AS INTEGER) = ? AND t.date BETWEEN ? AND ?
          AND (
              NOT EXISTS (
                  SELECT 1 FROM open_finance_accounts a
                  JOIN open_finance_items i ON i.id = a.of_item_id AND i.user_id = a.user_id
                  WHERE a.user_id = t.user_id AND a.account_id = {other} AND i.archived_at IS NULL
              )
              OR EXISTS (
                  SELECT 1 FROM open_finance_transactions o
                  WHERE o.user_id = t.user_id AND o.target_table = 'transactions' AND o.target_id = t.id
                    AND o.direction <> ? AND o.role <> 'REMOVED'
              )
          )
          AND NOT EXISTS (
              SELECT 1 FROM open_finance_transactions o
              WHERE o.user_id = t.user_id AND o.target_table = 'transactions' AND o.target_id = t.id
                AND o.id <> ? AND o.direction = ? AND o.role <> 'REMOVED'
          )
        """,
        (
            current_user_id, account_id, cents, inbox._shift(row["date"], -inbox.TRANSFER_MATCH_DAYS),
            inbox._shift(row["date"], inbox.TRANSFER_MATCH_DAYS), row["direction"], row["id"], row["direction"],
        ),
    ).fetchall()
    found = sorted(found, key=lambda entry: (inbox._date_gap(entry["date"], row["date"]), entry["date"], entry["id"]))
    return found[0]["id"] if found else None


def _place_cross_currency(conn, current_user_id, row, account_id, cents):
    """A conta global (services/global_account.py): a entrada em dolar acha a
    saida em reais que a espera (ou a transferencia ja no app), e a saida em
    reais acha a entrada em dolar. Devolve o status, ou None (segue o resto)."""
    if global_account.is_foreign(conn, current_user_id, account_id):
        if row["direction"] != "IN":
            return None
        target = _app_account(conn, current_user_id, account_id)
        recorded = global_account.recorded_transfer(conn, current_user_id, target, cents, row["date"])
        if recorded:
            if recorded["transfer_amount"] is None:
                # A conta virou global depois: o valor em dolar e o do banco.
                conn.execute(
                    "UPDATE transactions SET transfer_amount = ? WHERE id = ? AND user_id = ?",
                    (inbox._reais(cents), recorded["id"], current_user_id),
                )
            _update_row(
                conn, current_user_id, row["id"], role="MATCHED", item_id=None,
                target_table="transactions", target_id=recorded["id"],
            )
            return "matched"
        waiting = global_account.awaiting_real_side(conn, current_user_id, target, cents, row["date"])
        if not waiting:
            return None
        item = inbox.item_dict(waiting)
        _update_row(conn, current_user_id, row["id"], role="SOURCE", item_id=item["id"])
        changes = {
            "transfer_account_id": target["id"],
            "transfer_amount": inbox._reais(cents),
            "guessed": [guess for guess in item.get("guessed") or [] if guess != "transfer_account"],
            "description": global_account.transfer_description(
                global_account.account_name(conn, current_user_id, item["account_id"]), target["name"],
            ),
        }
        changes["needs"] = inbox.recompute_needs({**item, **changes})
        inbox.save_item(conn, current_user_id, item, changes)
        return "merged"

    destination = global_account.destination_for_row(conn, current_user_id, row, account_id)
    if destination is None:
        return None
    waiting = global_account.awaiting_foreign_side(conn, current_user_id, destination, cents, row["date"])
    if not waiting:
        return _absorb_recorded_dollar_income(conn, current_user_id, row, account_id, destination, cents)
    item = inbox.item_dict(waiting)
    _update_row(conn, current_user_id, row["id"], role="SOURCE", item_id=item["id"])
    changes = {
        "entry_type": "TRANSFER",
        "direction": "OUT",
        "account_id": account_id,
        "transfer_account_id": destination["id"],
        "amount": inbox._reais(cents),
        "currency": "BRL",
        "transfer_amount": item["amount"],
        # A data da transferencia e a da saida.
        "occurred_at": row["occurred_at"],
        "category": inbox.TRANSFER_CATEGORY,
        "category_id": None,
        "edited": [field for field in item.get("edited") or [] if field != "amount"],
        "reason": "own_transfer",
        "description": global_account.transfer_description(
            global_account.account_name(conn, current_user_id, account_id), destination["name"],
        ),
    }
    changes["needs"] = inbox.recompute_needs({**item, **changes})
    inbox.save_item(conn, current_user_id, item, changes)
    return "merged"


def _absorb_recorded_dollar_income(conn, current_user_id, row, account_id, destination, cents):
    """O credito em dolar ja virou receita sozinho (puxado antes, sem par em
    TRANSFER_HOLD_DAYS) e ainda esta como nasceu: a mesma linha vira a
    transferencia — nunca receita em dolar mais despesa em reais."""
    candidates = []
    for entry in conn.execute(
        """
        SELECT o.*, i.id AS the_item, i.target_id AS the_target, t.amount AS dollars,
               substr(i.occurred_at, 1, 10) AS item_date
        FROM open_finance_transactions o
        JOIN inbox_items i ON i.id = o.item_id AND i.user_id = o.user_id
        JOIN transactions t ON t.id = i.target_id AND t.user_id = i.user_id
        WHERE o.user_id = ? AND o.role = 'SOURCE' AND o.direction = 'IN' AND o.auto_recorded_at IS NOT NULL
          AND i.state = 'APPROVED' AND i.target_table = 'transactions'
          AND t.type = 'INCOME' AND t.account_id = ?
        """,
        (current_user_id, destination["id"]),
    ).fetchall():
        source = row_to_dict(entry)
        source.update(target_table="transactions", target_id=source["the_target"])
        if untouched(conn, current_user_id, source):
            candidates.append({**source, "id": source["the_item"], "date": source["item_date"]})
    best = global_account._best(
        conn, current_user_id, normalize_currency_of(destination), row["date"], candidates,
        brl_of=lambda candidate: cents, foreign_of=lambda candidate: inbox._cents(candidate["dollars"]),
    )
    if not best:
        return None
    item = inbox.item_dict(inbox.fetch_item(conn, current_user_id, best["the_item"]))
    target_id = best["the_target"]
    description = global_account.transfer_description(
        global_account.account_name(conn, current_user_id, account_id), destination["name"],
    )
    conn.execute(
        """
        UPDATE transactions SET type = 'TRANSFER', account_id = ?, transfer_account_id = ?, amount = ?,
            transfer_amount = ?, date = ?, occurred_at = ?, category = ?, category_id = NULL, description = ?,
            source_id = ?
        WHERE id = ? AND user_id = ?
        """,
        (account_id, destination["id"], inbox._reais(cents), best["dollars"], row["date"], row["occurred_at"],
         inbox.TRANSFER_CATEGORY, description, row["pluggy_transaction_id"], target_id, current_user_id),
    )
    _update_row(conn, current_user_id, row["id"], role="SOURCE", item_id=item["id"])
    inbox.save_item(conn, current_user_id, item, {
        "entry_type": "TRANSFER", "direction": "OUT", "account_id": account_id,
        "transfer_account_id": destination["id"], "amount": inbox._reais(cents), "currency": "BRL",
        "transfer_amount": best["dollars"], "occurred_at": row["occurred_at"],
        "category": inbox.TRANSFER_CATEGORY, "category_id": None, "description": description,
    })
    mark_auto_recorded(conn, current_user_id, item["id"], "transactions", target_id)
    return "merged"


def normalize_currency_of(account):
    return str(account["currency"] or "BRL").upper()


def _app_account(conn, current_user_id, account_id):
    return conn.execute(
        "SELECT id, name, institution, currency FROM accounts WHERE id = ? AND user_id = ?",
        (account_id, current_user_id),
    ).fetchone()


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
        "description": display_name(
            row["description"], row.get("merchant_name"), row.get("counterparty"), row["movement"], direction,
        ),
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
        to_global = global_account.destination_for_row(conn, current_user_id, row, account_id) is not None
        own = to_global or hint is not None or row["movement"] == "SELF_TRANSFER" or _is_self(conn, current_user_id, row)
        if own:
            # Para a conta global, o destino so entra com a ponta em dolar
            # (_place_cross_currency): ate la a transferencia espera.
            other = hint["transfer_account_id"] if hint and not to_global else None
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
    if (row["currency"] or "BRL") != "BRL" and account_id and (
        global_account.account_currency(conn, current_user_id, account_id) == row["currency"]
    ):
        # A conta global: o valor ja e o da conta, nada a converter.
        values["edited"] = ["amount"]
    if "category" not in values:
        values["category"], values["category_id"] = category_for_row(
            conn, current_user_id, row, values["entry_type"], amount, values["account_id"], rules,
        )
    values["needs"] = inbox.recompute_needs(values)
    item_id = inbox.insert_item(conn, current_user_id, values)
    _update_row(conn, current_user_id, row["id"], role="SOURCE", item_id=item_id, target_table=None, target_id=None)
    return item_id


def _first_active_category(conn, current_user_id, names, transaction_type):
    """(nome, id) do primeiro nome que o dono tem ativo, ou None."""
    for name in names:
        if expected_type(name) != transaction_type:
            continue
        category_id = category_id_for_name(conn, current_user_id, name)
        category = fetch_category(conn, current_user_id, category_id) if category_id else None
        if category and not category["archived_at"]:
            return name, category_id
    return None


CONFIDENT_CATEGORY_SOURCES = ("rule", "merchant", "cnae")


def category_decision(conn, current_user_id, row, entry_type, amount, account_id=None, rules=None):
    """(nome, id, de onde veio): a regra do dono (`rule`), a tabela de
    comerciantes (`merchant`), o CNAE (`cnae`), a categoria da Pluggy (`pluggy`),
    a padrao (`default`). Os tres primeiros dizem o que a compra e
    (CONFIDENT_CATEGORY_SOURCES); os outros sao palpites largos."""
    if entry_type == "TRANSFER":
        return inbox.TRANSFER_CATEGORY, None, "transfer"
    transaction_type = "INCOME" if entry_type == "INCOME" else "EXPENSE"
    if rules is None:
        rules = import_rules_for_matching(conn, current_user_id)
    merchant = row.get("merchant_name")
    named = display_name(row.get("description"))
    for text in dict.fromkeys(filter(None, (row.get("description"), merchant, named))):
        rule = statement_import.first_matching_rule(
            rules, text, transaction_type, amount, account_id if entry_type != "CARD" else None,
        )
        if rule:
            return rule["category"], rule["category_id"], "rule"
    if transaction_type == "EXPENSE":
        found = _first_active_category(
            conn, current_user_id, keyword_categories(merchant, row.get("counterparty"), named), transaction_type,
        )
        if found:
            return (*found, "merchant")
        found = _first_active_category(conn, current_user_id, cnae_categories(row.get("merchant_cnae")), transaction_type)
        if found:
            return (*found, "cnae")
    found = _first_active_category(
        conn, current_user_id, pluggy_category_names(row.get("pluggy_category_id")), transaction_type,
    )
    if found:
        return (*found, "pluggy")
    return (*inbox.suggest_category(conn, current_user_id, None, entry_type, amount, account_id, rules=[]), "default")


def category_for_row(conn, current_user_id, row, entry_type, amount, account_id=None, rules=None):
    """(nome, id) de category_decision()."""
    return category_decision(conn, current_user_id, row, entry_type, amount, account_id, rules)[:2]


# "Automatic investment" da Pluggy (03010000): a aplicacao automatica que o
# banco faz sozinho, como o texto de inbox.is_auto_invest().
AUTO_INVEST_CATEGORY_PREFIX = "0301"
FIXED_INCOME_CATEGORY_PREFIX = "0302"

# No caixa da corretora a Pluggy chama de "Same person transfer" tambem a
# compra e a venda de renda fixa, o IR e o IOF (BTG, 2026-10-28): so a
# transferencia de verdade e aporte/resgate; o resto e da carteira.
BROKER_TRANSFER_TEXT = re.compile(r"\b(transferencia|pix|ted|doc|tef)\b")
SOLD_INVESTMENT_TEXT = re.compile(r"\bvend")


def mark_bank_investments(conn, current_user_id):
    """Aplicacao e resgate num fundo do banco (Pluggy 03020000, RF High, Tesouro
    Reserva): saiu ou voltou do saldo como aporte/resgate, nunca despesa ou receita.
    Nao ha o que revisar. Idempotente: roda depois de gravar o pull."""
    conn.execute(
        f"""
        UPDATE transactions SET source_type = ?, needs_review = 0
        WHERE user_id = ? AND source_type = ? AND type IN ('EXPENSE', 'INCOME')
          AND id IN (
              SELECT o.target_id FROM open_finance_transactions o
              WHERE o.user_id = ? AND o.target_table = 'transactions' AND o.role <> 'REMOVED'
                AND o.pluggy_category_id LIKE '{FIXED_INCOME_CATEGORY_PREFIX}%'
          )
          AND NOT EXISTS (
              SELECT 1 FROM accounts a WHERE a.id = transactions.account_id AND a.type = 'BROKERAGE'
          )
        """,
        (BANK_INVESTMENT_SOURCE_TYPE, current_user_id, OPEN_FINANCE_SOURCE_TYPE, current_user_id),
    )


def is_auto_invest_row(row):
    return inbox.is_auto_invest(row["description"]) or str(row["pluggy_category_id"] or "").startswith(
        AUTO_INVEST_CATEGORY_PREFIX
    )


def is_broker_transfer(row):
    """Uma linha do caixa da corretora que e transferencia com o dono."""
    return row["movement"] in ("TRANSFER", "SELF_TRANSFER") and bool(
        BROKER_TRANSFER_TEXT.search(inbox.normalized(row["description"]))
    )


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
    INVOICE_PAYMENT_LINK_DAYS dias) e que nenhuma outra transacao explica.
    No banco que arredonda (inbox.ROUNDS_UP_ISSUERS), o valor que arredonda
    para o do banco tambem."""
    if row["direction"] != "OUT" or not account["account_id"]:
        return None
    kinds = sorted(INVOICE_PAYMENT_SOURCE_TYPES)
    cents = int(row["amount_cents"])
    lowest = cents - 99 if inbox.open_finance_rounds_up(conn, current_user_id, account["id"]) and cents % 100 == 0 else cents
    found = conn.execute(
        f"""
        SELECT t.id, t.date, CAST(ROUND(t.amount * 100) AS INTEGER) AS cents FROM transactions t
        WHERE t.user_id = ? AND t.account_id = ? AND t.source_type IN ({', '.join('?' for _ in kinds)})
          AND CAST(ROUND(t.amount * 100) AS INTEGER) BETWEEN ? AND ? AND t.date BETWEEN ? AND ?
          AND NOT EXISTS (
              SELECT 1 FROM open_finance_transactions o
              WHERE o.user_id = t.user_id AND o.target_table = 'transactions' AND o.target_id = t.id
                AND o.id <> ? AND o.role <> 'REMOVED'
          )
        """,
        (
            current_user_id, account["account_id"], *kinds, lowest, cents,
            inbox._shift(row["date"], -INVOICE_PAYMENT_LINK_DAYS), inbox._shift(row["date"], INVOICE_PAYMENT_LINK_DAYS),
            row["id"],
        ),
    ).fetchall()
    found = sorted(
        found,
        key=lambda entry: (entry["cents"] != cents, inbox._date_gap(entry["date"], row["date"]), entry["date"], entry["id"]),
    )
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
          AND (role IN ('SOURCE', 'UNMAPPED') OR (role = 'MATCHED' AND target_id LIKE ?))
        """,
        (current_user_id, account["id"], date_from, date_to, f"{broker_statement.ID_PREFIX}%"),
    ).fetchall()
    count = 0
    for row in rows:
        if row["pluggy_transaction_id"] in seen_ids:
            continue
        row = row_to_dict(row)
        if row["role"] == "MATCHED":
            if seen_ids:
                broker_statement.remove_line(conn, current_user_id, row)
                _update_row(conn, current_user_id, row["id"], role="REMOVED", target_table=None, target_id=None)
                count += 1
            continue
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
        return bool(target) and target["source_id"] == row["pluggy_transaction_id"] and target["source_type"] in (
            OPEN_FINANCE_SOURCE_TYPE, BANK_INVESTMENT_SOURCE_TYPE,
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


def apply_payment_change(conn, current_user_id, row, tx):
    """O banco mudou o valor de um pagamento de fatura ja gravado: nunca um
    segundo pagamento. O que esta transacao gravou acompanha; o pagamento feito no
    app (so ligado) fica como esta, apontado na Conferencia."""
    target = conn.execute(
        "SELECT source_type, source_id FROM transactions WHERE id = ? AND user_id = ?",
        (row["target_id"], current_user_id),
    ).fetchone()
    mine = (
        target and tx["direction"] == row["direction"] and target["source_type"] in INVOICE_PAYMENT_SOURCE_TYPES
        and str(target["source_id"] or "").endswith(str(row["pluggy_transaction_id"]))
    )
    if not mine:
        return _flag(conn, current_user_id, row, "changed", tx["amount_cents"])
    conn.execute(
        "UPDATE transactions SET amount = ? WHERE id = ? AND user_id = ?",
        (inbox._reais(tx["amount_cents"]), row["target_id"], current_user_id),
    )
    _update_row(
        conn, current_user_id, row["id"], conflict=None, conflict_amount_cents=None,
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


def _months_back(date_text, months):
    year, month, day = (int(part) for part in date_text[:10].split("-"))
    index = year * 12 + (month - 1) - months
    year, month = index // 12, index % 12 + 1
    return f"{year:04d}-{month:02d}-{min(day, calendar.monthrange(year, month)[1]):02d}"


def _installment_cents(row):
    count = int(row["total_installments"])
    return int(row["amount_cents"]) // count if (row["installment_number"] or 1) == 1 else int(row["amount_cents"])


def adopt_orphan_installments(conn, current_user_id, account, rules=None):
    """No historico, as parcelas de uma compra feita antes do que a Pluggy
    guarda: a parcela 1 nunca chega e parcela 2..n e COVERED, entao a compra
    sumiria (com as parcelas que ainda vao vencer). A menor parcela vista vira o
    item da compra inteira, parcela x n, na data da compra; o valor gravado na
    linha da Pluggy nao muda (o proximo pull compara com ele). Devolve quantas."""
    if account["type"] != "CREDIT":
        return 0
    rows = [row_to_dict(row) for row in conn.execute(
        """
        SELECT * FROM open_finance_transactions
        WHERE user_id = ? AND of_account_id = ? AND direction = 'OUT' AND total_installments > 1
          AND role <> 'REMOVED'
        ORDER BY date, posted_on, id
        """,
        (current_user_id, account["id"]),
    ).fetchall()]
    purchases = {}
    for row in rows:
        count = int(row["total_installments"])
        group = purchases.setdefault((plain_text(display_name(row["description"])), count), [])
        cents = _installment_cents(row)
        series = next((entry for entry in group if abs(entry["cents"] - cents) <= count), None)
        if series is None:
            series = {"cents": cents, "rows": []}
            group.append(series)
        series["rows"].append(row)
    adopted = 0
    for group in purchases.values():
        for series in group:
            members = series["rows"]
            if any((row["installment_number"] or 1) == 1 or row["role"] != "COVERED" for row in members):
                continue
            lowest = min(row["installment_number"] for row in members)
            for row in members:
                if row["installment_number"] != lowest:
                    continue
                date_text = row["date"]
                if row.get("posted_on") in (None, date_text):
                    # O conector nao mandou a data da compra: a parcela k caiu
                    # k-1 meses depois da primeira.
                    date_text = _months_back(date_text, lowest - 1)
                draft = {**row, "date": date_text, "occurred_at": date_text, "installment_number": 1,
                         "amount_cents": int(row["amount_cents"]) * int(row["total_installments"])}
                new_item_for_row(conn, current_user_id, draft, account, rules)
                adopted += 1
    return adopted


def place_unmapped(conn, current_user_id, account, rules=None):
    """Mapeada a conta, o que ja foi puxado sem mapeamento entra no Aprovar."""
    rows = conn.execute(
        "SELECT * FROM open_finance_transactions WHERE user_id = ? AND of_account_id = ? AND role = 'UNMAPPED'"
        " ORDER BY date, created_at, id",
        (current_user_id, account["id"]),
    ).fetchall()
    return [place(conn, current_user_id, row_to_dict(row), account, rules) for row in rows]
