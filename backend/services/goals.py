"""Metas financeiras (021): quanto falta e quando chega.

A linha guarda so o plano (alvo, aporte mensal, rentabilidade esperada, data
desejada). Tudo o que depende do mercado e calculado na leitura:

- valor atual, por tipo:
  PORTFOLIO      - `current_net_balance` da carteira;
  NET_WORTH      - carteira + saldo das contas em reais (arquivadas inclusive,
                   como o consolidado do Inicio; conta sem cambio fica fora);
  ASSET_CLASS    - soma do liquido das posicoes da classe;
  MONTHLY_INCOME - proventos liquidos pagos nos ultimos 12 meses / 12;
- previsao: meses ate o alvo com o aporte mensal, capitalizando a
  rentabilidade anual esperada em taxa mensal equivalente; sem aporte e sem
  rentabilidade nao ha previsao. Meta de renda nao tem previsao (renda nao
  cresce por aporte de forma direta);
- com data desejada: o aporte mensal necessario para chegar nela.
"""

from asset_classes import ALLOWED_ASSET_CLASSES, ASSET_CLASS_LABELS
from dates import month_key
from db import get_db, new_id, row_to_dict, utc_timestamp
from money import parse_money, rounded_money
from services.accounts import account_balance_rows
from services.fx import FxUnavailable, normalize_currency, rate_on, BASE_CURRENCY
from services.invoices import local_today
from services.portfolio import build_portfolio_snapshot
from services.proceeds import paid_proceeds_by_asset
from validators import (
    ValidationError,
    optional_date,
    parse_optional_number,
    require_choice,
    require_string,
    safe_float,
    shift_month,
)

GOAL_KINDS = {"PORTFOLIO", "NET_WORTH", "ASSET_CLASS", "MONTHLY_INCOME"}
GOAL_KIND_LABELS = {
    "PORTFOLIO": "Carteira de investimentos",
    "NET_WORTH": "Patrimônio total",
    "ASSET_CLASS": "Classe de ativo",
    "MONTHLY_INCOME": "Renda mensal de proventos",
}
# 100 anos: acima disso a meta nao e alcancavel com esse aporte.
MAX_MONTHS = 1200


def monthly_rate(annual_percent):
    annual = safe_float(annual_percent) / 100
    if annual <= -1:
        return 0.0
    return (1 + annual) ** (1 / 12) - 1


def months_to_reach(current, target, contribution, rate):
    """Meses ate `current` chegar a `target`, com aporte no fim de cada mes."""
    if current >= target:
        return 0
    if contribution <= 0 and rate <= 0:
        return None
    value = current
    for month in range(1, MAX_MONTHS + 1):
        value = value * (1 + rate) + contribution
        if value >= target:
            return month
    return None


def required_contribution(current, target, months, rate):
    """Aporte mensal para ir de `current` a `target` em `months` meses."""
    if months <= 0:
        return None
    if current >= target:
        return 0.0
    growth = (1 + rate) ** months
    missing = target - current * growth
    if missing <= 0:
        return 0.0
    if rate == 0:
        return rounded_money(missing / months)
    return rounded_money(missing * rate / (growth - 1))


def months_between(from_month, to_month):
    fy, fm = (int(part) for part in from_month.split("-"))
    ty, tm = (int(part) for part in to_month.split("-"))
    return (ty - fy) * 12 + (tm - fm)


def accounts_total_brl(conn, current_user_id):
    total = 0.0
    for row in account_balance_rows(conn, current_user_id):
        currency = normalize_currency(row["currency"] if "currency" in row.keys() else None)
        balance = safe_float(row["balance"])
        if currency == BASE_CURRENCY:
            total += balance
            continue
        try:
            total += balance * rate_on(conn, current_user_id, currency)
        except FxUnavailable:
            continue
    return total


def income_last_12_months(conn, current_user_id, today):
    # A mesma janela (hoje - 365 dias, hoje] da carteira e do resumo de proventos.
    by_asset = paid_proceeds_by_asset(conn, current_user_id, today)
    return sum(bucket["net_12m"] for bucket in by_asset.values())


def current_values(conn, current_user_id, kinds, today):
    """Valor atual por tipo de meta (so calcula o que as metas pedem)."""
    values = {}
    snapshot = None
    if kinds & {"PORTFOLIO", "NET_WORTH", "ASSET_CLASS"}:
        snapshot = build_portfolio_snapshot(current_user_id)
        values["PORTFOLIO"] = safe_float(snapshot.get("current_net_balance"))
        by_class = {}
        for position in snapshot.get("assets") or []:
            by_class[position.get("class")] = by_class.get(position.get("class"), 0.0) + safe_float(position.get("net_value"))
        values["ASSET_CLASS"] = by_class
    if "NET_WORTH" in kinds:
        values["NET_WORTH"] = values["PORTFOLIO"] + accounts_total_brl(conn, current_user_id)
    if "MONTHLY_INCOME" in kinds:
        values["INCOME_12M"] = income_last_12_months(conn, current_user_id, today)
        values["MONTHLY_INCOME"] = values["INCOME_12M"] / 12
    return values


def goal_current(row, values):
    if row["kind"] == "ASSET_CLASS":
        return safe_float((values.get("ASSET_CLASS") or {}).get(row["asset_class"]))
    return safe_float(values.get(row["kind"]))


def serialize_goal(row, values, today):
    item = row_to_dict(row)
    current = rounded_money(goal_current(row, values))
    target = rounded_money(row["target_amount"])
    contribution = rounded_money(row["monthly_contribution"])
    rate = monthly_rate(row["annual_return_percent"])
    this_month = month_key(today)
    reached = current >= target

    estimated_months = None
    estimated_month = None
    if row["kind"] != "MONTHLY_INCOME":
        estimated_months = months_to_reach(current, target, contribution, rate)
        if estimated_months is not None:
            estimated_month = shift_month(this_month, estimated_months)

    target_month = str(row["target_date"])[:7] if row["target_date"] else None
    needed = None
    on_track = None
    if target_month and row["kind"] != "MONTHLY_INCOME" and not reached:
        months_left = months_between(this_month, target_month)
        needed = required_contribution(current, target, months_left, rate)
        on_track = estimated_month is not None and estimated_month <= target_month
    elif target_month and reached:
        on_track = True

    item.update({
        "kind_label": GOAL_KIND_LABELS[row["kind"]],
        "asset_class_label": ASSET_CLASS_LABELS.get(row["asset_class"]) if row["asset_class"] else None,
        "target_amount": target,
        "monthly_contribution": contribution,
        "current": current,
        "remaining": rounded_money(max(target - current, 0.0)),
        "percent": rounded_money(current / target * 100) if target > 0 else 0.0,
        "reached": reached,
        "estimated_months": estimated_months,
        "estimated_month": estimated_month,
        "target_month": target_month,
        "required_contribution": needed,
        "on_track": on_track,
        # So na meta de renda: o total dos 12 meses de que a media saiu.
        "income_last_12_months": (
            rounded_money(values.get("INCOME_12M")) if row["kind"] == "MONTHLY_INCOME" else None
        ),
    })
    return item


def fetch_goal(conn, current_user_id, goal_id):
    return conn.execute(
        "SELECT * FROM investment_goals WHERE id = ? AND user_id = ?",
        (goal_id, current_user_id),
    ).fetchone()


def list_goals(current_user_id):
    today = local_today()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM investment_goals WHERE user_id = ? ORDER BY target_amount, created_at",
            (current_user_id,),
        ).fetchall()
        values = current_values(conn, current_user_id, {row["kind"] for row in rows}, today)
    return [serialize_goal(row, values, today) for row in rows]


def get_goal(current_user_id, goal_id):
    today = local_today()
    with get_db() as conn:
        row = fetch_goal(conn, current_user_id, goal_id)
        if not row:
            return None
        values = current_values(conn, current_user_id, {row["kind"]}, today)
    return serialize_goal(row, values, today)


def normalize_goal_payload(payload, existing=None):
    """Campos validados para gravar; `existing` preenche o que o PATCH nao mandou."""
    merged = {**(row_to_dict(existing) or {}), **payload}
    name = require_string(merged, "name", "Nome da meta", max_length=120)
    kind = require_choice(merged, "kind", "Tipo da meta", GOAL_KINDS)
    asset_class = None
    if kind == "ASSET_CLASS":
        asset_class = str(merged.get("asset_class") or "").strip().upper()
        if asset_class not in ALLOWED_ASSET_CLASSES:
            raise ValidationError("Escolha a classe de ativo da meta.")
    target_amount = parse_money(merged, "target_amount", "Valor da meta")
    if target_amount <= 0:
        raise ValidationError("Valor da meta deve ser maior que zero.")
    contribution = (
        parse_money(merged, "monthly_contribution", "Aporte mensal", allow_zero=True)
        if merged.get("monthly_contribution") not in (None, "") else 0.0
    )
    annual_return = parse_optional_number(
        merged, "annual_return_percent", "Rentabilidade anual esperada", minimum=-99, maximum=100
    )
    target_date = optional_date(merged, "target_date", "Data desejada")
    stored_date = str(existing["target_date"])[:10] if existing and existing["target_date"] else None
    # So uma data nova precisa ser futura: a guardada chega ao seu mes e a meta segue editavel.
    if target_date and target_date != stored_date and target_date[:7] <= month_key(local_today()):
        raise ValidationError("A data desejada precisa ser depois deste mes.")
    return {
        "name": name,
        "kind": kind,
        "asset_class": asset_class,
        "target_amount": target_amount,
        "monthly_contribution": contribution,
        "annual_return_percent": annual_return,
        "target_date": target_date,
    }


def create_goal(current_user_id, payload):
    fields = normalize_goal_payload(payload)
    goal_id = new_id()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO investment_goals
                (id, user_id, name, kind, asset_class, target_amount,
                 monthly_contribution, annual_return_percent, target_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (goal_id, current_user_id, *fields.values()),
        )
    return get_goal(current_user_id, goal_id)


def update_goal(current_user_id, goal_id, payload):
    with get_db() as conn:
        existing = fetch_goal(conn, current_user_id, goal_id)
        if not existing:
            return None
        fields = normalize_goal_payload(payload, existing)
        assignments = ", ".join(f"{column} = ?" for column in fields)
        conn.execute(
            f"UPDATE investment_goals SET {assignments}, updated_at = ? WHERE id = ? AND user_id = ?",
            (*fields.values(), utc_timestamp(), goal_id, current_user_id),
        )
    return get_goal(current_user_id, goal_id)


def delete_goal(current_user_id, goal_id):
    """Meta e plano, nao registro: apagar nao desfaz nenhum lancamento."""
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM investment_goals WHERE id = ? AND user_id = ?",
            (goal_id, current_user_id),
        )
    return cursor.rowcount > 0
