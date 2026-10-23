""""Precisa de atencao": os avisos do Inicio e do sino (GET /api/attention).

A regra que morava em `lib/attentionRules.js`, na mesma ordem e com as mesmas
condicoes. Cada aviso tem uma `key` que nomeia o caso, nao o tipo, e ela e
byte a byte a do cliente: os avisos ja dispensados em cada aparelho
(localStorage) dependem dela.

  1. fatura vencida — todas juntas, `fatura-vencida:<cartao>|<ano>-<mes>,...`
     (o mes SEM zero a esquerda, como o `invoiceId()` do cliente);
  2. fatura fechada da proxima de cada cartao, so sem vencida;
  3. debito automatico que a conta nao cobre nos proximos 31 dias, um por conta;
  4. recorrencias vencidas, todas juntas;
  5. categoria acima do orcamento do mes, uma por categoria.

So numeros: o texto (titulos, `overdueDetail()`) fica com quem desenha.
`local_today()` e lido por nome aqui.
"""

from datetime import datetime, time, timedelta
from decimal import Decimal

from money import rounded_money
from services.card_invoices import invoice_id, next_invoices, open_invoices, overdue_invoices
from services.home import account_list, is_portfolio, prepare_reads
from services.invoices import local_today
from services.monthly_plan import build_budget_view
from services.recurring import recurring_pending_count, recurring_rows

AUTOPAY_WINDOW_DAYS = 31


def overdue_item(invoices):
    overdue = overdue_invoices(invoices)
    total = sum((item["total"] for item in overdue), Decimal("0"))
    count = sum(len(item["rows"]) for item in overdue)
    if count <= 0 or total <= 0:
        return None
    return {
        "key": "fatura-vencida:" + ",".join(sorted(
            invoice_id(item["card_id"], item["invoice_year"], item["invoice_month"]) for item in overdue
        )),
        "kind": "INVOICE_OVERDUE",
        "tone": "danger",
        "total": rounded_money(total),
        "item_count": count,
        "invoices": [
            {
                "card_id": item["card_id"],
                "card_name": item["card_name"],
                "invoice_month": item["invoice_month"],
                "invoice_year": item["invoice_year"],
                "due_date": item["due_date"],
                "total": rounded_money(item["total"]),
                "count": len(item["rows"]),
            }
            for item in overdue
        ],
    }


def payable_item(invoices):
    """A proxima fatura de cada cartao, quando ja fechou e nao esta em credito."""
    payable = [item for item in next_invoices(invoices) if item["closed"] and item["total"] >= 0]
    total = sum((item["total"] for item in payable), Decimal("0"))
    if total <= 0:
        return None
    return {
        "key": "fatura-fechada:" + ",".join(sorted(
            invoice_id(item["card_id"], item["invoice_year"], item["invoice_month"]) for item in payable
        )),
        "kind": "INVOICE_PAYABLE",
        "tone": "warning",
        "total": rounded_money(total),
        "invoices": [
            {
                "card_id": item["card_id"],
                "invoice_month": item["invoice_month"],
                "invoice_year": item["invoice_year"],
                "total": rounded_money(item["total"]),
            }
            for item in payable
        ],
    }


def autopay_shortfalls(conn, current_user_id, invoices, accounts, today):
    """Debito automatico que a conta nao cobre: as faturas que vencem de hoje
    ate hoje + 31 dias, somadas por conta e comparadas ao saldo em reais."""
    autopay_by_card = {
        row["id"]: row["autopay_account_id"]
        for row in conn.execute(
            """
            SELECT id, autopay_account_id FROM credit_cards
            WHERE user_id = ? AND archived_at IS NULL AND autopay_account_id IS NOT NULL
            """,
            (current_user_id,),
        ).fetchall()
    }
    today_text = today.strftime("%Y-%m-%d")
    limit_text = (today + timedelta(days=AUTOPAY_WINDOW_DAYS)).strftime("%Y-%m-%d")
    by_account = {}
    for invoice in invoices:
        account_id = autopay_by_card.get(invoice["card_id"])
        due = invoice["due_date"]
        if not account_id or due < today_text or due > limit_text:
            continue
        entry = by_account.setdefault(account_id, {"total": Decimal("0"), "first_due": due})
        entry["total"] += invoice["total"]
        entry["first_due"] = min(entry["first_due"], due)

    accounts_by_id = {account["id"]: account for account in accounts}
    items = []
    for account_id, entry in by_account.items():
        account = accounts_by_id.get(account_id)
        # A Corretora nao tem saldo no Inicio; sem cambio hoje nao da para dizer.
        if not account or account.get("archived_at") or is_portfolio(account):
            continue
        if account.get("balance_brl") is None:
            continue
        balance = Decimal(str(account["balance_brl"]))
        if balance >= entry["total"]:
            continue
        items.append({
            "key": f"debito-sem-saldo:{account_id}:{entry['first_due']}",
            "kind": "AUTOPAY_SHORTFALL",
            "tone": "danger",
            "account_id": account_id,
            "account_name": account["name"],
            "total": rounded_money(entry["total"]),
            "first_due": entry["first_due"],
            "balance": rounded_money(balance),
            "missing": rounded_money(entry["total"] - balance),
        })
    return sorted(items, key=lambda item: item["first_due"])


def recurring_item(conn, current_user_id, today):
    """As recorrencias vencidas, a mesma conta do pending_count de GET /api/recurring.
    A ultima ocorrencia lancada entra na chave: um novo atraso volta."""
    moment = datetime.combine(today, time())
    pending = []
    for row in recurring_rows(conn, current_user_id, include_inactive=True):
        count = recurring_pending_count(conn, current_user_id, row, moment)
        if count > 0:
            pending.append((row, count))
    total = sum(count for _, count in pending)
    if total <= 0:
        return None
    ids = sorted(f"{row['id']}@{row['last_occurrence_date'] or ''}x{count}" for row, count in pending)
    return {"key": "recorrencias:" + ",".join(ids), "kind": "RECURRING", "tone": "info", "count": total}


def over_budget_items(conn, current_user_id, today):
    budget = build_budget_view(conn, current_user_id, today.strftime("%Y-%m"))
    over = sorted(
        (item for item in budget.get("items", []) if item.get("status") == "OVER"),
        key=lambda item: -(Decimal(str(item["spent"])) - Decimal(str(item["available"]))),
    )
    month = budget.get("month") or ""
    return [
        {
            "key": f"orcamento:{month}:{item.get('category_id') or item.get('id')}",
            "kind": "OVER_BUDGET",
            "tone": "warning",
            "category_id": item.get("category_id"),
            "category_name": (
                f"{item['parent_name']} › {item['category_name']}"
                if item.get("parent_name") else item.get("category_name")
            ),
            "spent": item["spent"],
            "available": item["available"],
        }
        for item in over
    ]


def build_attention(conn, current_user_id):
    today = local_today()
    prepare_reads(conn, current_user_id, today)
    invoices = open_invoices(conn, current_user_id, today)["invoices"]
    accounts = account_list(conn, current_user_id)

    items = []
    overdue = overdue_item(invoices)
    if overdue:
        items.append(overdue)
    else:
        payable = payable_item(invoices)
        if payable:
            items.append(payable)
    items.extend(autopay_shortfalls(conn, current_user_id, invoices, accounts, today))
    recurring = recurring_item(conn, current_user_id, today)
    if recurring:
        items.append(recurring)
    items.extend(over_budget_items(conn, current_user_id, today))
    return {"today": today.strftime("%Y-%m-%d"), "items": items}
