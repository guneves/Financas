"""Proventos: leitura, posicao na data com e os resumos (total e por ativo).

A escrita (validar e gravar um provento) fica no blueprint `routes/proceeds.py`;
aqui fica o que outros servicos tambem leem — a carteira usa
`paid_proceeds_by_asset()` para a rentabilidade com proventos.

`investment_position_at_date()` da a quantidade elegivel e o custo na data com;
o status (PAID / SCHEDULED) vem da data de pagamento e e calculado na leitura.
Provento de ativo em moeda estrangeira e somado como esta gravado (em reais,
regra atual): nao ha conversao aqui.
"""

from datetime import date, datetime, timedelta

from dates import parse_iso_date
from db import serialize_metadata_row
from money import rounded_money
from validators import ValidationError, require_date, safe_float


ALLOWED_PROCEEDS_TYPES = {"DIVIDEND", "JCP", "AMORTIZATION"}

# Janela do "ultimos 12 meses": pagamento em (hoje - 365 dias, hoje], a mesma
# de `income_last_12_months()` das metas.
TRAILING_DAYS = 365


def trailing_window(today=None):
    today = today or date.today()
    return (today - timedelta(days=TRAILING_DAYS)).isoformat(), today.isoformat()


def investment_position_at_date(conn, current_user_id, asset_id, date_value):
    target_date = require_date({"date": date_value}, "date", "Data de referencia")
    rows = conn.execute(
        """
        SELECT
            id,
            movement_type,
            quantity,
            unit_price,
            fee_amount,
            transaction_date,
            metadata,
            created_at
        FROM investment_transactions
        WHERE user_id = ?
          AND asset_id = ?
          AND transaction_date <= ?
        ORDER BY transaction_date ASC, created_at ASC, id ASC
        """,
        (current_user_id, asset_id, target_date),
    ).fetchall()

    quantity = 0.0
    cost_basis = 0.0
    for row in rows:
        item = serialize_metadata_row(row)
        movement_type = item.get("movement_type")
        movement_quantity = safe_float(item.get("quantity"))
        unit_price = safe_float(item.get("unit_price"))
        fee_amount = max(safe_float(item.get("fee_amount")), 0)

        if movement_type in {"BUY", "ADJUSTMENT"} and movement_quantity > 0:
            quantity += movement_quantity
            cost_basis += (movement_quantity * unit_price) + fee_amount
            continue

        if movement_type in {"SELL", "REDEMPTION"} or movement_quantity < 0:
            reduction_quantity = min(abs(movement_quantity), max(quantity, 0))
            average_cost = cost_basis / quantity if quantity > 0 else unit_price
            quantity -= reduction_quantity
            cost_basis -= reduction_quantity * average_cost
            if quantity <= 0.000001:
                quantity = 0.0
                cost_basis = 0.0

    average_cost = cost_basis / quantity if quantity > 0 else 0
    return {
        "quantity": round(quantity, 6),
        "cost_basis": rounded_money(cost_basis),
        "average_cost": rounded_money(average_cost),
    }


def proceed_status(payment_date):
    parsed_payment = parse_iso_date(payment_date)
    today = datetime.now().date()
    if parsed_payment and parsed_payment.date() > today:
        return "SCHEDULED"
    return "PAID"


def serialize_investment_proceed(row, conn=None, current_user_id=None):
    item = serialize_metadata_row(row)
    if not item:
        return None

    item["asset"] = {
        "id": item.get("asset_id"),
        "asset_class": item.pop("asset_class", None),
        "ticker": item.pop("ticker", None),
        "name": item.pop("asset_name", None),
    }
    item["status"] = proceed_status(item.get("payment_date"))

    position = None
    if conn is not None and current_user_id is not None and item.get("asset_id") and item.get("record_date"):
        try:
            position = investment_position_at_date(
                conn,
                current_user_id,
                item["asset_id"],
                item["record_date"],
            )
        except ValidationError:
            position = None

    eligible_quantity = safe_float(item.get("eligible_quantity"))
    average_cost = safe_float((position or {}).get("average_cost"))
    cost_basis = average_cost * eligible_quantity if eligible_quantity > 0 else 0
    gross_amount = safe_float(item.get("gross_amount"))
    net_amount = safe_float(item.get("net_amount"))
    tax_amount = safe_float(item.get("tax_amount"))

    item["cost_basis_at_record_date"] = rounded_money(cost_basis)
    item["average_cost_at_record_date"] = rounded_money(average_cost)
    item["gross_yield_on_cost_percent"] = round((gross_amount / cost_basis) * 100, 4) if cost_basis > 0 else 0
    item["yield_on_cost_percent"] = round((net_amount / cost_basis) * 100, 4) if cost_basis > 0 else 0
    item["effective_tax_rate_percent"] = round((tax_amount / gross_amount) * 100, 2) if gross_amount > 0 else 0
    return item


def fetch_investment_proceeds(conn, current_user_id, filters=None):
    filters = filters or {}
    query = """
        SELECT
            proceeds.*,
            asset.asset_class,
            asset.ticker,
            asset.name AS asset_name
        FROM investment_proceeds proceeds
        JOIN assets asset ON asset.id = proceeds.asset_id AND asset.user_id = proceeds.user_id
        WHERE proceeds.user_id = ?
    """
    params = [current_user_id]

    if filters.get("asset_id"):
        query += " AND proceeds.asset_id = ?"
        params.append(filters["asset_id"])
    if filters.get("proceeds_type"):
        query += " AND proceeds.proceeds_type = ?"
        params.append(filters["proceeds_type"])
    if filters.get("date_from"):
        query += " AND proceeds.payment_date >= ?"
        params.append(filters["date_from"])
    if filters.get("date_after"):
        query += " AND proceeds.payment_date > ?"
        params.append(filters["date_after"])
    if filters.get("date_to"):
        query += " AND proceeds.payment_date <= ?"
        params.append(filters["date_to"])

    today = datetime.now().strftime("%Y-%m-%d")
    if filters.get("status") == "PAID":
        query += " AND proceeds.payment_date <= ?"
        params.append(today)
    elif filters.get("status") == "SCHEDULED":
        query += " AND proceeds.payment_date > ?"
        params.append(today)

    direction = "ASC" if filters.get("ascending") else "DESC"
    query += f" ORDER BY proceeds.payment_date {direction}, proceeds.created_at {direction}"
    return conn.execute(query, params).fetchall()


def paid_proceeds_in_year(conn, current_user_id, year):
    """Proventos pagos no ano civil (1/1 a 31/12, inclusive), do mais antigo ao mais novo.

    E o que o relatorio de IR le. Pago = pagamento ate hoje (agendado fica de
    fora mesmo dentro do ano); empate na data segue a ordem de gravacao.
    """
    year = int(year)
    return fetch_investment_proceeds(conn, current_user_id, {
        "date_from": f"{year:04d}-01-01",
        "date_to": f"{year:04d}-12-31",
        "status": "PAID",
        "ascending": True,
    })


def fetch_investment_proceed_by_id(conn, current_user_id, proceed_id):
    return conn.execute(
        """
        SELECT
            proceeds.*,
            asset.asset_class,
            asset.ticker,
            asset.name AS asset_name
        FROM investment_proceeds proceeds
        JOIN assets asset ON asset.id = proceeds.asset_id
        WHERE proceeds.user_id = ?
          AND proceeds.id = ?
        """,
        (current_user_id, proceed_id),
    ).fetchone()


def serialized_proceeds(conn, current_user_id, filters=None):
    rows = fetch_investment_proceeds(conn, current_user_id, filters)
    return [serialize_investment_proceed(row, conn, current_user_id) for row in rows]


def trailing_net_by_asset(conn, current_user_id, filters=None, today=None):
    """Liquido pago nos ultimos 12 meses, por ativo.

    Respeita o ativo e o tipo filtrados, mas nao o periodo nem o status: e uma
    janela movel que termina hoje, comparavel entre ativos seja qual for o
    periodo da tela.
    """
    start, end = trailing_window(today)
    trailing_filters = {
        key: value for key, value in (filters or {}).items()
        if key in ("asset_id", "proceeds_type")
    }
    trailing_filters.update({"date_after": start, "date_to": end})
    totals = {}
    for row in fetch_investment_proceeds(conn, current_user_id, trailing_filters):
        totals[row["asset_id"]] = totals.get(row["asset_id"], 0.0) + safe_float(row["net_amount"])
    return totals


def build_proceeds_by_asset(items, total_net, trailing_net=None):
    """Proventos agrupados por ativo, do maior liquido para o menor.

    `cost_basis` e a media dos `cost_basis_at_record_date` dos eventos que
    tem custo: o custo da posicao entra uma vez, nao uma por pagamento (um FII
    que paga todo mes nao divide o liquido por 12 vezes o custo).
    `yield_on_cost_percent` e o liquido dividido por esse custo;
    `share_percent` e a fatia do liquido total do periodo.
    """
    trailing_net = trailing_net or {}
    buckets = {}
    for item in items:
        asset = item.get("asset") or {}
        asset_id = item.get("asset_id")
        bucket = buckets.setdefault(asset_id, {
            "asset_id": asset_id,
            "ticker": asset.get("ticker"),
            "name": asset.get("name"),
            "asset_class": asset.get("asset_class"),
            "event_count": 0,
            "gross_amount": 0.0,
            "tax_amount": 0.0,
            "net_amount": 0.0,
            "paid_net_amount": 0.0,
            "scheduled_net_amount": 0.0,
            "cost_basis_total": 0.0,
            "cost_events": 0,
            "last_payment_date": None,
        })
        net = safe_float(item.get("net_amount"))
        bucket["event_count"] += 1
        bucket["gross_amount"] += safe_float(item.get("gross_amount"))
        bucket["tax_amount"] += safe_float(item.get("tax_amount"))
        bucket["net_amount"] += net
        event_cost = safe_float(item.get("cost_basis_at_record_date"))
        if event_cost > 0:
            bucket["cost_basis_total"] += event_cost
            bucket["cost_events"] += 1
        if item.get("status") == "SCHEDULED":
            bucket["scheduled_net_amount"] += net
        else:
            bucket["paid_net_amount"] += net
        payment_date = item.get("payment_date")
        if payment_date and (bucket["last_payment_date"] is None or payment_date > bucket["last_payment_date"]):
            bucket["last_payment_date"] = payment_date

    result = []
    for bucket in buckets.values():
        cost_events = bucket.pop("cost_events")
        cost_total = bucket.pop("cost_basis_total")
        bucket["cost_basis"] = cost_total / cost_events if cost_events else 0.0
        for key in ("gross_amount", "tax_amount", "net_amount", "paid_net_amount", "scheduled_net_amount", "cost_basis"):
            bucket[key] = rounded_money(bucket[key])
        bucket["net_12m"] = rounded_money(trailing_net.get(bucket["asset_id"], 0))
        # Percentuais nao sao dinheiro: round() comum.
        bucket["yield_on_cost_percent"] = (
            round(bucket["net_amount"] / bucket["cost_basis"] * 100, 4) if bucket["cost_basis"] > 0 else 0
        )
        bucket["share_percent"] = round(bucket["net_amount"] / total_net * 100, 2) if total_net > 0 else 0
        result.append(bucket)

    result.sort(key=lambda item: (-item["net_amount"], item.get("ticker") or ""))
    return result


def build_investment_proceeds_summary(items, trailing_net=None):
    summary = {
        "event_count": len(items),
        "gross_amount": 0,
        "tax_amount": 0,
        "net_amount": 0,
        "cost_basis": 0,
        "yield_on_cost_percent": 0,
        "paid_net_amount": 0,
        "scheduled_net_amount": 0,
        "by_type": {},
        "by_month": {},
        "by_asset": [],
        "next_events": [],
    }

    for item in items:
        gross = safe_float(item.get("gross_amount"))
        tax = safe_float(item.get("tax_amount"))
        net = safe_float(item.get("net_amount"))
        proceeds_type = item.get("proceeds_type") or "OTHER"
        month_key = str(item.get("payment_date") or "")[:7]

        summary["gross_amount"] += gross
        summary["tax_amount"] += tax
        summary["net_amount"] += net
        if item.get("status") == "SCHEDULED":
            summary["scheduled_net_amount"] += net
            summary["next_events"].append(item)
        else:
            summary["paid_net_amount"] += net

        type_bucket = summary["by_type"].setdefault(proceeds_type, {
            "proceeds_type": proceeds_type,
            "event_count": 0,
            "gross_amount": 0,
            "tax_amount": 0,
            "net_amount": 0,
        })
        type_bucket["event_count"] += 1
        type_bucket["gross_amount"] += gross
        type_bucket["tax_amount"] += tax
        type_bucket["net_amount"] += net

        if month_key:
            month_bucket = summary["by_month"].setdefault(month_key, {
                "month": month_key,
                "event_count": 0,
                "gross_amount": 0,
                "tax_amount": 0,
                "net_amount": 0,
            })
            month_bucket["event_count"] += 1
            month_bucket["gross_amount"] += gross
            month_bucket["tax_amount"] += tax
            month_bucket["net_amount"] += net

    for key in ("gross_amount", "tax_amount", "net_amount", "paid_net_amount", "scheduled_net_amount"):
        summary[key] = rounded_money(summary[key])

    for bucket in summary["by_type"].values():
        for key in ("gross_amount", "tax_amount", "net_amount"):
            bucket[key] = rounded_money(bucket[key])
    for bucket in summary["by_month"].values():
        for key in ("gross_amount", "tax_amount", "net_amount"):
            bucket[key] = rounded_money(bucket[key])

    summary["by_type"] = sorted(summary["by_type"].values(), key=lambda item: item["proceeds_type"])
    summary["by_month"] = sorted(summary["by_month"].values(), key=lambda item: item["month"])
    summary["by_asset"] = build_proceeds_by_asset(items, summary["net_amount"], trailing_net)
    # O custo de cada ativo entra uma vez (o mesmo do by_asset), nao uma por evento.
    summary["cost_basis"] = rounded_money(sum(item["cost_basis"] for item in summary["by_asset"]))
    summary["yield_on_cost_percent"] = round(
        (summary["net_amount"] / summary["cost_basis"]) * 100,
        4,
    ) if summary["cost_basis"] > 0 else 0
    summary["next_events"] = sorted(
        summary["next_events"],
        key=lambda item: (item.get("payment_date") or "", item.get("asset", {}).get("ticker") or ""),
    )[:8]
    return summary


def paid_proceeds_by_asset(conn, current_user_id, today=None):
    """Liquido pago por ativo (pagamento <= hoje): o total e os ultimos 12 meses.

    E o que a carteira soma na rentabilidade com proventos. Agendado nao conta
    como recebido.
    """
    today = today or date.today()
    start, end = trailing_window(today)
    rows = conn.execute(
        """
        SELECT
            asset_id,
            proceeds_type,
            COALESCE(SUM(net_amount), 0) AS net_total,
            COALESCE(SUM(CASE WHEN payment_date > ? THEN net_amount ELSE 0 END), 0) AS net_12m
        FROM investment_proceeds
        WHERE user_id = ?
          AND payment_date <= ?
        GROUP BY asset_id, proceeds_type
        """,
        (start, current_user_id, end),
    ).fetchall()

    by_asset = {}
    for row in rows:
        bucket = by_asset.setdefault(row["asset_id"], {"net": 0.0, "net_12m": 0.0, "by_type": {}})
        net_total = safe_float(row["net_total"])
        net_12m = safe_float(row["net_12m"])
        bucket["net"] += net_total
        bucket["net_12m"] += net_12m
        type_bucket = bucket["by_type"].setdefault(row["proceeds_type"], {"net": 0.0, "net_12m": 0.0})
        type_bucket["net"] += net_total
        type_bucket["net_12m"] += net_12m
    return by_asset
