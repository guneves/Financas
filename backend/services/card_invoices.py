"""As faturas em aberto de cada cartao, somadas no servidor.

Uma leitura so para tres telas (proposta home-attention-invoices.md): a tela
Cartoes (`GET /api/cc-invoices`), a proxima fatura do Inicio (`/api/home`) e
os avisos de fatura (`/api/attention`). Todas leem `open_invoices()`, entao
"proxima", "vencida" e "pagavel" sao a mesma regra nas tres.

- So linhas `OPEN`; o total de cada fatura e a soma com sinal em `Decimal`
  (um estorno, 033, abate: `signed_amount()`).
- `past_due`: venceu ontem ou antes (no dia do vencimento ainda se paga em dia).
- `payable`: fechada e com total >= 0 (em credito nao se paga).
- `next`: por cartao, a que vence primeiro de hoje em diante.
- `nearest`: a vencida mais antiga com total > 0, senao a primeira `next`
  pelo vencimento — a que a tela Cartoes abre e paga do topo.
- `future`: depois da primeira fatura ainda aberta do cartao (a tela a dobra).

A ordem das listas segue a das linhas (fatura, depois criacao), como a do
cliente que esta leitura substitui: dois vencimentos iguais ficam na ordem em
que apareceram.

`local_today()` e lido por nome aqui: os testes o congelam neste modulo.
"""

import unicodedata
from decimal import Decimal

from money import rounded_money
from services.attachments import same_purchase_sql
from services.invoices import invoice_closing_date, invoice_due_date, local_today, signed_amount


def fold(text):
    """Chave de ordenacao sem acento nem caixa (o localeCompare do cliente)."""
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


def invoice_id(card_id, year, month):
    """`<cartao>|<ano>-<mes>` com o mes SEM zero a esquerda: e o `invoiceId()`
    do cliente, e as chaves dos avisos ja dispensados nos aparelhos dependem dele."""
    return f"{card_id}|{int(year)}-{int(month)}"


def open_rows(conn, current_user_id):
    return conn.execute(
        f"""
        SELECT
            cce.*,
            cc.name AS card_name,
            cc.due_day AS card_due_day,
            cc.closing_day AS card_closing_day,
            cc.autopay_account_id AS card_autopay_account_id,
            cc.credit_enabled AS card_credit_enabled,
            (
                SELECT COUNT(*) FROM cc_expense_attachments a
                JOIN cc_expenses sib ON sib.id = a.cc_expense_id AND sib.user_id = a.user_id
                WHERE a.user_id = cce.user_id AND {same_purchase_sql("sib.", "cce.")}
            ) AS attachment_count,
            (
                SELECT COUNT(*) FROM cc_expenses sib
                WHERE sib.user_id = cce.user_id AND sib.status = 'OPEN'
                  AND {same_purchase_sql("sib.", "cce.")}
            ) AS installments_open,
            (
                SELECT COUNT(*) FROM cc_expenses sib
                WHERE sib.user_id = cce.user_id AND sib.status = 'PAID'
                  AND {same_purchase_sql("sib.", "cce.")}
            ) AS installments_paid
        FROM cc_expenses cce
        JOIN credit_cards cc ON cc.id = cce.card_id AND cc.user_id = cce.user_id
        WHERE cce.user_id = ? AND cce.status = 'OPEN'
        ORDER BY cce.invoice_year ASC, cce.invoice_month ASC, cce.created_at ASC
        """,
        (current_user_id,),
    ).fetchall()


def parse_installment(info):
    try:
        current, total = (int(part) for part in str(info).split("/"))
        return current, total
    except (TypeError, ValueError):
        return 1, 1


def serialize_purchase(row):
    current, total = parse_installment(row["installment_info"])
    others = row["share_others_amount"]
    return {
        "id": row["id"],
        "client_id": row["client_id"],
        "kind": row["kind"] or "PURCHASE",
        "description": row["description"],
        "category": row["category"],
        "category_id": row["category_id"],
        "purchase_date": row["purchase_date"],
        "amount": rounded_money(row["amount"]),
        "installment_info": row["installment_info"],
        "installment_current": current,
        "installment_total": total,
        "attachment_count": int(row["attachment_count"] or 0),
        "share_mode": row["share_mode"],
        "share_person": row["share_person"],
        "share_others_amount": rounded_money(others) if others is not None else None,
        "installments_open": int(row["installments_open"] or 0),
        "installments_paid": int(row["installments_paid"] or 0),
    }


def open_invoices(conn, current_user_id, today=None):
    """{"today", "cards": [...], "invoices": [...] na ordem das linhas}.

    Cada fatura guarda `total` em Decimal (arredonda quem serializa) e as
    linhas dela; cada cartao, as faturas em ordem de (ano, mes).
    """
    today = today or local_today()
    today_text = today.strftime("%Y-%m-%d")
    cards = {}
    invoices = {}
    for row in open_rows(conn, current_user_id):
        card_id = row["card_id"]
        card = cards.get(card_id)
        if card is None:
            card = cards[card_id] = {
                "card_id": card_id,
                "card_name": row["card_name"] or "Cartão",
                "due_day": row["card_due_day"],
                "closing_day": row["card_closing_day"],
                "autopay_account_id": row["card_autopay_account_id"],
                "credit_enabled": bool(row["card_credit_enabled"]),
                "invoices": [],
            }
        key = (card_id, int(row["invoice_year"]), int(row["invoice_month"]))
        invoice = invoices.get(key)
        if invoice is None:
            month, year = key[2], key[1]
            closing = invoice_closing_date(month, year, card["due_day"], card["closing_day"])
            due = invoice_due_date(month, year, card["due_day"])
            invoice = invoices[key] = {
                "card_id": card_id,
                "card_name": card["card_name"],
                "invoice_month": month,
                "invoice_year": year,
                "key": f"{year:04d}-{month:02d}",
                "closing_date": closing.strftime("%Y-%m-%d"),
                "due_date": due.strftime("%Y-%m-%d"),
                "closed": today >= closing,
                "past_due": due.strftime("%Y-%m-%d") < today_text,
                "total": Decimal("0"),
                "rows": [],
            }
            card["invoices"].append(invoice)
        invoice["total"] += signed_amount(row)
        invoice["rows"].append(row)

    for invoice in invoices.values():
        invoice["payable"] = invoice["closed"] and invoice["total"] >= 0
        invoice["next"] = invoice["nearest"] = invoice["future"] = False

    for card in cards.values():
        card["invoices"].sort(key=lambda item: (item["invoice_year"], item["invoice_month"]))
        first_open = next((index for index, item in enumerate(card["invoices"]) if not item["closed"]), None)
        if first_open is not None:
            for item in card["invoices"][first_open + 1:]:
                item["future"] = True

    ordered = list(invoices.values())
    for invoice in next_invoices(ordered):
        invoice["next"] = True
    nearest = nearest_invoice(ordered)
    if nearest:
        nearest["nearest"] = True
    return {"today": today_text, "cards": list(cards.values()), "invoices": ordered}


def overdue_invoices(invoices):
    """As vencidas que ainda cobram algo (total > 0), pelo vencimento."""
    return sorted(
        (item for item in invoices if item["past_due"] and item["total"] > 0),
        key=lambda item: item["due_date"],
    )


def next_invoices(invoices):
    """A proxima fatura de cada cartao: a que vence primeiro de hoje em diante.
    Nao e "a do mes que vem": quem fecha antes de vencer paga a do proprio mes."""
    by_card = {}
    for item in invoices:
        if item["past_due"]:
            continue
        known = by_card.get(item["card_id"])
        if known is None or item["due_date"] < known["due_date"]:
            by_card[item["card_id"]] = item
    return sorted(by_card.values(), key=lambda item: item["due_date"])


def nearest_invoice(invoices):
    overdue = overdue_invoices(invoices)
    if overdue:
        return overdue[0]
    upcoming = next_invoices(invoices)
    return upcoming[0] if upcoming else None


def invoice_summary(invoice):
    """A fatura sem as linhas, para /api/home."""
    return {
        "card_id": invoice["card_id"],
        "card_name": invoice["card_name"],
        "invoice_month": invoice["invoice_month"],
        "invoice_year": invoice["invoice_year"],
        "due_date": invoice["due_date"],
        "closing_date": invoice["closing_date"],
        "closed": invoice["closed"],
        "payable": invoice["payable"],
        "total": rounded_money(invoice["total"]),
        "item_count": len(invoice["rows"]),
    }


def build_cc_invoices(conn, current_user_id, today=None):
    """GET /api/cc-invoices."""
    data = open_invoices(conn, current_user_id, today)
    cards = sorted(data["cards"], key=lambda card: fold(card["card_name"]))
    nearest = next((item for item in data["invoices"] if item["nearest"]), None)
    open_total = Decimal("0")
    result_cards = []
    for card in cards:
        card_total = sum((item["total"] for item in card["invoices"]), Decimal("0"))
        open_total += card_total
        result_cards.append({
            "card_id": card["card_id"],
            "card_name": card["card_name"],
            "due_day": card["due_day"],
            "closing_day": card["closing_day"],
            "autopay_account_id": card["autopay_account_id"],
            "credit_enabled": card["credit_enabled"],
            "total": rounded_money(card_total),
            "invoices": [
                {
                    "invoice_month": item["invoice_month"],
                    "invoice_year": item["invoice_year"],
                    "key": item["key"],
                    "closing_date": item["closing_date"],
                    "due_date": item["due_date"],
                    "closed": item["closed"],
                    "past_due": item["past_due"],
                    "payable": item["payable"],
                    "next": item["next"],
                    "nearest": item["nearest"],
                    "future": item["future"],
                    "total": rounded_money(item["total"]),
                    "item_count": len(item["rows"]),
                    "purchases": [
                        serialize_purchase(row)
                        for row in sorted(item["rows"], key=lambda row: fold(row["description"]))
                    ],
                }
                for item in card["invoices"]
            ],
        })
    return {
        "today": data["today"],
        "nearest": {
            "card_id": nearest["card_id"],
            "invoice_month": nearest["invoice_month"],
            "invoice_year": nearest["invoice_year"],
        } if nearest else None,
        "open_total": rounded_money(open_total),
        "cards": result_cards,
    }
