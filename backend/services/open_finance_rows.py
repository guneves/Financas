"""Ler a Pluggy: o que uma transacao dela e para o app (puro, sem banco de dados).

Centavos, sinal da cobranca do cartao (aprendido por conta: a sandbox contradiz
a documentacao), parcelas, contraparte, a chave `pluggy:<id>` e
`normalize_transaction()`, que devolve os campos do app ou `Skip`.

Saiu de services/open_finance_inbox.py (2026-11-13), que continua reexportando
todos estes nomes.
"""

import re
from datetime import datetime, timedelta, timezone

import money
from services.inbox_rules import normalized

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


def to_cents(value):
    """Reais (numero da Pluggy, com sinal) em centavos inteiros, ROUND_HALF_UP
    (o mesmo de rounded_money)."""
    try:
        return money.to_cents(value)
    except (TypeError, ValueError) as exc:
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
    description = normalized(raw.get("description") or raw.get("descriptionRaw")).upper()
    return bool(INVOICE_PAYMENT_TEXT.search(description))


def is_income_row(raw):
    if str(raw.get("categoryId") or "").startswith(INCOME_CATEGORY_PREFIX):
        return True
    return bool(SALARY_TEXT.search(normalized(raw.get("description") or raw.get("descriptionRaw")).upper()))


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
    # A compra no exterior que a Pluggy ja converteu: a moeda dela fica (o par
    # aproximado a trata como internacional).
    original_currency = currency if currency != account_currency else None
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
        "original_currency": original_currency,
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
