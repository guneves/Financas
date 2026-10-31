"""Os quatro paineis de historico do Inicio (GET /api/home/panels).

O que `pages/Dashboard.jsx` montava no cliente sobre todo o historico, aqui,
para o Inicio nativo (que nao baixa `/api/transactions`):

1. **Despesas por categoria** do mes atual, com a seta contra o mes passado
   inteiro (`buildSpending()`): saidas de conta na visao bancaria (sem
   Corretora, sem pagamento de fatura, sem o caixa da carteira, so a parte do
   dono) mais as compras no cartao pelo total da compra, no dia da compra; o
   estorno abate. Agrupa pelo nome da categoria, como a web.
2. **Ritmo de gastos**: o acumulado dia a dia deste mes contra a media dos
   `PACE_MONTHS` meses anteriores no mesmo dia; mes sem gasto fica fora da
   media.
3. **Proximas faturas**: o comprometido por mes de fatura, `INVOICE_MONTHS`
   meses a partir da primeira proxima fatura; a vencida fica fora (ela e o
   aviso). E as compras das proximas faturas.
4. **Parcelamentos abertos**: compras com mais de uma parcela em aberto,
   agrupadas pela compra (`same_purchase_sql()`), na ordem da proxima fatura.

Tudo em centavos inteiros; reais so na saida. `local_today()` e lido por nome
aqui (os testes o congelam neste modulo).
"""

import calendar
from decimal import ROUND_HALF_UP, Decimal

from money import rounded_money
from services.card_invoices import fold, next_invoices, open_invoices, parse_installment
from services.home import (
    INVOICE_PAYMENT_CATEGORY_PREFIX,
    _cents,
    _others_cents,
    _quoted,
    investment_flow_sql,
    prepare_reads,
)
from services.invoices import local_today
from source_types import MONTH_SUMMARY_SOURCE_TYPE, INVOICE_PAYMENT_SOURCE_TYPES
from validators import shift_month

INVOICE_MONTHS = 6
PACE_MONTHS = 3
PACE_DAYS = 31
OTHER_CATEGORY = "Outros"


def _reais(cents):
    return rounded_money(Decimal(int(cents or 0)) / 100)


def _percent_change(current, previous):
    """(atual - anterior) / |anterior| em %, uma casa; None sem anterior."""
    if not previous:
        return None
    value = (Decimal(current) - Decimal(previous)) * 100 / abs(Decimal(previous))
    return float(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _empty_month():
    return {"by_day": {}, "by_category": {}, "total": 0}


def _add(month, day, category, channel, cents):
    month["by_day"][day] = month["by_day"].get(day, 0) + cents
    name = category or OTHER_CATEGORY
    totals = month["by_category"].setdefault(name, {"cash": 0, "credit": 0})
    totals[channel] += cents
    month["total"] += cents


def _purchase_key(row):
    """A compra de uma linha do cartao: o client_id, senao a chave antiga de
    `same_purchase_sql()` (cartao, descricao, data, categoria, tipo)."""
    if row["client_id"]:
        return ("client", row["client_id"])
    return ("legacy", row["card_id"], row["description"], row["purchase_date"], row["category"], row["kind"])


def monthly_spending(conn, current_user_id, keys):
    """{mes: {by_day, by_category, total}} em centavos, para os meses `keys`."""
    months = {key: _empty_month() for key in keys}
    cases = investment_flow_sql()
    invoice_payment = (
        f"(COALESCE(t.source_type, '') IN ({_quoted(INVOICE_PAYMENT_SOURCE_TYPES)})"
        f" OR substr(COALESCE(t.category, ''), 1, {len(INVOICE_PAYMENT_CATEGORY_PREFIX)})"
        f" = '{INVOICE_PAYMENT_CATEGORY_PREFIX}')"
    )
    placeholders = ", ".join("?" for _ in keys)
    rows = conn.execute(
        f"""
        SELECT substr(t.date, 1, 7) AS month, CAST(substr(t.date, 9, 2) AS INTEGER) AS day,
               NULLIF(t.category, '') AS category,
               {_cents("t.amount")} - {_others_cents("t.")} AS own
        FROM transactions t
        LEFT JOIN accounts origin ON origin.id = t.account_id AND origin.user_id = t.user_id
        WHERE t.user_id = ? AND t.type = 'EXPENSE' AND {cases['from_bank']}
          AND COALESCE(origin.currency, 'BRL') = 'BRL'
          AND NOT {cases['portfolio_cash']} AND NOT {invoice_payment}
          AND COALESCE(t.source_type, '') <> '{MONTH_SUMMARY_SOURCE_TYPE}'
          AND substr(t.date, 1, 7) IN ({placeholders})
        ORDER BY t.date, t.id
        """,
        (current_user_id, *keys),
    ).fetchall()
    for row in rows:
        own = int(row["own"] or 0)
        if own > 0:
            _add(months[row["month"]], row["day"], row["category"], "cash", own)

    card_rows = conn.execute(
        f"""
        SELECT id, client_id, card_id, description, purchase_date, category, kind,
               substr(purchase_date, 1, 7) AS month, CAST(substr(purchase_date, 9, 2) AS INTEGER) AS day,
               CASE WHEN kind = 'REFUND' THEN -{_cents("amount")}
                    ELSE {_cents("amount")} - {_others_cents()} END AS signed_own
        FROM cc_expenses
        WHERE user_id = ? AND substr(purchase_date, 1, 7) IN ({placeholders})
        ORDER BY id
        """,
        (current_user_id, *keys),
    ).fetchall()
    purchases = {}
    for row in card_rows:
        key = _purchase_key(row)
        purchase = purchases.get(key)
        if purchase is None:
            purchase = purchases[key] = {
                "month": row["month"], "day": row["day"], "category": row["category"], "cents": 0,
            }
        purchase["cents"] += int(row["signed_own"] or 0)
    for purchase in purchases.values():
        if purchase["cents"] != 0:
            _add(months[purchase["month"]], purchase["day"], purchase["category"], "credit", purchase["cents"])
    return months


def category_breakdown(current, previous):
    items = []
    for name, totals in current["by_category"].items():
        value = totals["cash"] + totals["credit"]
        if value <= 0:
            continue
        before = previous["by_category"].get(name)
        before_value = before["cash"] + before["credit"] if before else 0
        items.append({
            "name": name,
            "value": _reais(value),
            "cash": _reais(totals["cash"]),
            "credit": _reais(totals["credit"]),
            "delta": _percent_change(value, before_value),
            "_cents": value,
        })
    items.sort(key=lambda item: (-item["_cents"], fold(item["name"])))
    for item in items:
        del item["_cents"]
    return items


def spending_pace(current, past, today):
    """O "Ritmo de gastos": `rows` dia 1..31 com `current` (ate hoje) e
    `average` (dos meses anteriores com gasto), em reais."""
    today_day = today.day
    baseline = [month for month in past if month["total"] > 0]
    running = [0] * len(baseline)
    total = 0
    current_to_date = 0
    months_to_date = [0] * len(baseline)
    average_to_date = Decimal("0")
    rows = []
    for day in range(1, PACE_DAYS + 1):
        total += current["by_day"].get(day, 0)
        for index, month in enumerate(baseline):
            running[index] += month["by_day"].get(day, 0)
        average = Decimal(sum(running)) / len(baseline) if baseline else None
        if day == today_day:
            current_to_date = total
            average_to_date = average or Decimal("0")
            months_to_date = list(running)
        rows.append({
            "day": day,
            "current": _reais(total) if day <= today_day else None,
            "average": rounded_money(average / 100) if average is not None else None,
        })
    average_month = (
        Decimal(sum(month["total"] for month in baseline)) / len(baseline) if baseline else Decimal("0")
    )
    average_to_date_reais = rounded_money(average_to_date / 100)
    return {
        "today_day": today_day,
        "days_in_month": calendar.monthrange(today.year, today.month)[1],
        "rows": rows,
        "current_to_date": _reais(current_to_date),
        "average_to_date": average_to_date_reais,
        "average_month": rounded_money(average_month / 100),
        "vs_average": _percent_change(current_to_date, average_to_date) if baseline else None,
        "months": [
            {"month": month["key"], "to_date": _reais(months_to_date[index])}
            for index, month in enumerate(baseline)
        ],
    }


def invoice_panels(conn, current_user_id, today, current_key):
    data = open_invoices(conn, current_user_id, today)
    invoices = data["invoices"]
    upcoming = next_invoices(invoices)
    next_keys = sorted({item["key"] for item in upcoming})
    first = next_keys[0] if next_keys else current_key
    keys = [shift_month(first, offset) for offset in range(INVOICE_MONTHS)]
    by_key = dict.fromkeys(keys, Decimal("0"))
    for invoice in invoices:
        if not invoice["past_due"] and invoice["key"] in by_key:
            by_key[invoice["key"]] += invoice["total"]
    projection = [
        {"month": key, "value": rounded_money(by_key[key]), "next": key in next_keys}
        for key in keys
    ]
    next_items = [
        {
            "id": row["id"],
            "kind": row["kind"] or "PURCHASE",
            "description": row["description"],
            "card_id": invoice["card_id"],
            "card_name": invoice["card_name"],
            "invoice_month": invoice["invoice_month"],
            "invoice_year": invoice["invoice_year"],
            "installment_info": row["installment_info"],
            "amount": rounded_money(row["amount"]),
        }
        for invoice in upcoming
        for row in invoice["rows"]
    ]

    grouped = {}
    for invoice in invoices:
        for row in invoice["rows"]:
            _, total = parse_installment(row["installment_info"])
            if total <= 1:
                continue
            key = _purchase_key(row)
            group = grouped.get(key)
            if group is None:
                group = grouped[key] = {
                    "description": row["description"],
                    "card_id": invoice["card_id"],
            "card_name": invoice["card_name"],
            "invoice_month": invoice["invoice_month"],
            "invoice_year": invoice["invoice_year"],
                    "installment_amount": Decimal(str(row["amount"] or 0)),
                    "remaining": 0,
                    "total_installments": total,
                    "next_invoice_month": invoice["invoice_month"],
                    "next_invoice_year": invoice["invoice_year"],
                }
            group["remaining"] += 1
            if (invoice["invoice_year"], invoice["invoice_month"]) < (group["next_invoice_year"], group["next_invoice_month"]):
                group["next_invoice_year"] = invoice["invoice_year"]
                group["next_invoice_month"] = invoice["invoice_month"]
                group["installment_amount"] = Decimal(str(row["amount"] or 0))
    installments = sorted(
        grouped.values(),
        key=lambda item: (item["next_invoice_year"], item["next_invoice_month"], fold(item["description"])),
    )
    installments_total = Decimal("0")
    serialized = []
    for item in installments:
        remaining_amount = item["installment_amount"] * item["remaining"]
        installments_total += remaining_amount
        serialized.append({
            **item,
            "installment_amount": rounded_money(item["installment_amount"]),
            "remaining_amount": rounded_money(remaining_amount),
            "paid": item["total_installments"] - item["remaining"],
        })
    return {
        "invoice_projection": projection,
        "next_invoice_months": next_keys,
        "next_invoice_items": next_items,
        "installments": serialized,
        "installments_total": rounded_money(installments_total),
    }


def build_home_panels(conn, current_user_id):
    today = local_today()
    prepare_reads(conn, current_user_id, today)
    current_key = today.strftime("%Y-%m")
    past_keys = [shift_month(current_key, -(index + 1)) for index in range(PACE_MONTHS)]
    spending = monthly_spending(conn, current_user_id, [current_key, *past_keys])
    for key, month in spending.items():
        month["key"] = key
    current = spending[current_key]
    past = [spending[key] for key in past_keys]
    return {
        "today": today.strftime("%Y-%m-%d"),
        "month": current_key,
        "categories": category_breakdown(current, past[0]),
        "spending_total": _reais(current["total"]),
        "pace": spending_pace(current, past, today),
        **invoice_panels(conn, current_user_id, today, current_key),
    }
