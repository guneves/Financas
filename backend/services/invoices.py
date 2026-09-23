"""Cartao de credito: mes da fatura, parcelas, fechamento e pagamento.

As regras moram aqui para que o front nunca tenha uma copia:
- `compute_invoice_start()` decide em que fatura cai uma compra;
- `invoice_closing_date()` decide quando ela fecha — so fatura fechada e paga
  (`ensure_invoice_closed()` guarda todo caminho que marca PAID);
- `settle_invoice()` grava o pagamento e o PAID dos itens juntos;
- `apply_due_autopay()` materializa o debito automatico na leitura.

`local_today()` e o relogio: os testes o congelam com monkeypatch aqui e em
`routes/cards.py`, os dois modulos que o chamam.
"""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from dates import clamped_date, parse_iso_date
from db import new_id, row_to_dict
from money import rounded_money
from source_types import CC_AUTOPAY_SOURCE_TYPE
from validators import ValidationError


def ensure_credit_card_owner(conn, current_user_id, card_id):
    card = conn.execute(
        "SELECT id FROM credit_cards WHERE id = ? AND user_id = ?",
        (card_id, current_user_id),
    ).fetchone()
    if not card:
        raise ValidationError("Cartao nao encontrado.")


def default_closing_day(due_day):
    """Fechamento presumido quando o cartao nao tem dia de fechamento gravado."""
    candidate = int(due_day) - 7
    return candidate if candidate > 0 else 30 + candidate


def add_invoice_months(month, year, months):
    """Avanca (mes, ano) em `months` meses, normalizando a virada de ano."""
    zero_based = (int(month) - 1) + int(months)
    return zero_based % 12 + 1, int(year) + zero_based // 12


def compute_invoice_start(purchase_date, due_day, closing_day=None):
    """Fatura em que uma compra cai, dados o dia de fechamento e o de vencimento.

    Regra: uma compra feita antes do fechamento entra na fatura que fecha neste
    ciclo; a partir do fechamento (inclusive) ela escorrega para a proxima. Quando
    o fechamento cai depois do vencimento no mes, o ciclo ja esta deslocado e a
    compra vai um mes adiante do que essa contagem sugeriria.

    Esta regra vivia em `frontend/src/pages/Carteira.jsx` e foi trazida para ca em
    2026-09-15 para poder ser testada e reusada — o comportamento e o mesmo.
    """
    if isinstance(purchase_date, str):
        purchase_date = datetime.strptime(purchase_date, "%Y-%m-%d").date()

    due_day = int(due_day)
    closing_day = int(closing_day) if closing_day else default_closing_day(due_day)

    purchase_day = purchase_date.day
    offset = 0
    if closing_day < due_day:
        if purchase_day >= closing_day:
            offset = 1
    elif purchase_day < closing_day:
        offset = 1
    else:
        offset = 2

    month, year = add_invoice_months(purchase_date.month, purchase_date.year, offset)
    return {"invoice_month": month, "invoice_year": year}


def split_installments(total_amount, installments_count):
    """Divide um total em parcelas de centavos inteiros, sem perder centavo.

    O resto e distribuido nas primeiras parcelas, entao a soma das parcelas e
    sempre igual ao total informado.
    """
    total_cents = int(Decimal(str(rounded_money(total_amount))).scaleb(2).to_integral_value(rounding=ROUND_HALF_UP))
    base_cents, remainder = divmod(total_cents, installments_count)
    return [
        rounded_money((base_cents + (1 if index < remainder else 0)) / 100)
        for index in range(installments_count)
    ]


def build_installment_rows(purchase, card):
    """Linhas de cc_expenses para uma compra parcelada, ja com a fatura de cada uma."""
    start = compute_invoice_start(
        purchase["purchase_date"],
        card["due_day"],
        card["closing_day"],
    )
    amounts = split_installments(purchase["total_amount"], purchase["installments"])

    rows = []
    for index, amount in enumerate(amounts):
        month, year = add_invoice_months(start["invoice_month"], start["invoice_year"], index)
        rows.append({
            "card_id": purchase["card_id"],
            "category": purchase["category"],
            "description": purchase["description"],
            "amount": amount,
            "purchase_date": purchase["purchase_date"],
            "invoice_month": month,
            "invoice_year": year,
            "installment_info": f"{index + 1}/{purchase['installments']}",
            "status": "OPEN",
        })
    return rows


def serialize_cc_expense(row):
    item = row_to_dict(row)
    if not item:
        return None

    card_name = item.pop("card_name", None)
    due_day = item.pop("card_due_day", None)
    closing_day = item.pop("card_closing_day", None)
    if card_name is not None:
        item["credit_cards"] = {
            "name": card_name,
            "due_day": due_day,
            "closing_day": closing_day,
        }
    if due_day is not None and item.get("invoice_month") and item.get("invoice_year"):
        # O cliente usa estes campos para liberar (ou nao) o botao Pagar; a
        # regra do fechamento continua so aqui.
        closing = invoice_closing_date(item["invoice_month"], item["invoice_year"], due_day, closing_day)
        item["invoice_closing_date"] = closing.strftime("%Y-%m-%d")
        item["invoice_due_date"] = invoice_due_date(
            item["invoice_month"], item["invoice_year"], due_day
        ).strftime("%Y-%m-%d")
        item["invoice_closed"] = local_today() >= closing
    return item


def local_today():
    """Hoje (data local, sem hora). Ponto unico para os testes congelarem o relogio."""
    return datetime.now().date()


def invoice_closing_date(invoice_month, invoice_year, due_day, closing_day=None):
    """Dia em que a fatura (mes, ano) fecha.

    O mes da fatura e o mes do vencimento. Se o fechamento vem antes do
    vencimento no mes, a fatura fecha no proprio mes; senao fecha no mes
    anterior — o mesmo deslocamento que `compute_invoice_start` aplica as
    compras. No dia do fechamento a fatura ja esta fechada: uma compra feita
    nesse dia vai para a proxima.
    """
    due_day = int(due_day)
    closing_day = int(closing_day) if closing_day else default_closing_day(due_day)
    month, year = int(invoice_month), int(invoice_year)
    if closing_day >= due_day:
        month, year = add_invoice_months(month, year, -1)
    return clamped_date(year, month, closing_day)


def invoice_due_date(invoice_month, invoice_year, due_day):
    return clamped_date(invoice_year, invoice_month, due_day)


def invoice_label(invoice_month, invoice_year):
    return f"{int(invoice_month):02d}/{int(invoice_year)}"


class InvoiceStillOpenError(ValidationError):
    """Pagamento de fatura antes do fechamento (respondido com 409)."""


def ensure_invoice_closed(card, invoice_month, invoice_year, today=None):
    """Recusa pagar uma fatura que ainda nao fechou."""
    closing = invoice_closing_date(invoice_month, invoice_year, card["due_day"], card["closing_day"])
    if (today or local_today()) < closing:
        raise InvoiceStillOpenError(
            f"A fatura {invoice_label(invoice_month, invoice_year)} ainda esta aberta. "
            f"O pagamento so e liberado depois do fechamento, em {closing.strftime('%d/%m/%Y')}."
        )


def settle_invoice(conn, current_user_id, card, invoice_month, invoice_year, *,
                   account_id, payment_date, source_type, source_id):
    """Paga os itens em aberto de uma fatura: um EXPENSE na conta + status PAID.

    As duas coisas acontecem na mesma transacao do banco. Devolve o lancamento
    criado, ou None quando nao havia nada em aberto ou quando o source_id ja
    existia (outra chamada pagou primeiro) — nesse caso nada e alterado.
    """
    lines = conn.execute(
        """
        SELECT id, amount FROM cc_expenses
        WHERE user_id = ? AND card_id = ? AND invoice_month = ? AND invoice_year = ?
          AND status = 'OPEN'
        """,
        (current_user_id, card["id"], int(invoice_month), int(invoice_year)),
    ).fetchall()
    if not lines:
        return None

    total = rounded_money(sum(Decimal(str(line["amount"])) for line in lines))
    transaction_id = new_id()
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO transactions
        (id, user_id, account_id, amount, date, category, description, type,
         source_type, source_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'EXPENSE', ?, ?)
        """,
        (
            transaction_id,
            current_user_id,
            account_id,
            total,
            payment_date,
            f"Pagamento Fatura {card['name']}",
            f"Fatura {invoice_label(invoice_month, invoice_year)}",
            source_type,
            source_id,
        ),
    )
    if not cursor.rowcount:
        return None

    line_ids = [line["id"] for line in lines]
    placeholders = ",".join("?" for _ in line_ids)
    conn.execute(
        f"UPDATE cc_expenses SET status = 'PAID' WHERE user_id = ? AND id IN ({placeholders})",
        [current_user_id, *line_ids],
    )
    return conn.execute(
        "SELECT * FROM transactions WHERE id = ? AND user_id = ?",
        (transaction_id, current_user_id),
    ).fetchone()


def autopay_source_id(card_id, invoice_month, invoice_year):
    return f"{card_id}:{int(invoice_year):04d}-{int(invoice_month):02d}"


def apply_due_autopay(conn, current_user_id, today=None):
    """Debito automatico: paga toda fatura vencida de cartao com conta de debito.

    Roda no inicio das leituras que dependem dele (lancamentos, contas,
    cartoes, faturas) — o app e local e nao tem cron. O pagamento sai no dia
    do vencimento, mesmo que o app so seja aberto dias depois. Idempotente
    pelo source_id deterministico '<cartao>:<AAAA-MM>': uma fatura reaberta a
    mao depois do debito nao e paga de novo.
    """
    today = today or local_today()
    cards = conn.execute(
        """
        SELECT cc.*
        FROM credit_cards cc
        JOIN accounts a ON a.id = cc.autopay_account_id AND a.user_id = cc.user_id
        WHERE cc.user_id = ? AND a.archived_at IS NULL
        """,
        (current_user_id,),
    ).fetchall()

    paid = []
    for card in cards:
        start = parse_iso_date(card["autopay_start_date"])
        start = start.date() if start else None
        invoices = conn.execute(
            """
            SELECT DISTINCT invoice_month, invoice_year FROM cc_expenses
            WHERE user_id = ? AND card_id = ? AND status = 'OPEN'
            ORDER BY invoice_year, invoice_month
            """,
            (current_user_id, card["id"]),
        ).fetchall()
        for invoice in invoices:
            due = invoice_due_date(invoice["invoice_month"], invoice["invoice_year"], card["due_day"])
            if due > today or (start and due < start):
                continue
            row = settle_invoice(
                conn,
                current_user_id,
                card,
                invoice["invoice_month"],
                invoice["invoice_year"],
                account_id=card["autopay_account_id"],
                payment_date=due.strftime("%Y-%m-%d"),
                source_type=CC_AUTOPAY_SOURCE_TYPE,
                source_id=autopay_source_id(card["id"], invoice["invoice_month"], invoice["invoice_year"]),
            )
            if row:
                paid.append(row)
    return paid
