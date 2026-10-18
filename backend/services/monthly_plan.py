"""Plano do mes (025): quanto gastar e quanto investir, em reais, e os alertas.

A linha guarda so o plano (gasto, aporte e, opcional, a renda esperada). Um
mes sem linha propria herda o plano mais recente anterior a ele: o usuario
define uma vez e o plano vale ate ser trocado. Tudo o mais e calculado na
leitura:

- gasto do mes = saidas das contas (EXPENSE), sem transferencias, sem
  pagamento de fatura e sem aporte (lancamento ligado a uma operacao ou na
  categoria "Investimento" — a mesma regra de `isInvestmentOutflow()` do
  Inicio), mais as compras no cartao, inteiras, no mes da compra (decisao 1,
  a mesma do orcamento por categoria);
- receita do mes = entradas das contas (INCOME), sem resgate de investimento;
- aporte do mes = aportes - resgates das operacoes da carteira no mes (o
  mesmo fluxo do grafico de Operacoes, `movement_flow()`): dinheiro novo que
  ficou investido. O caixa ligado nao entra, senao o aporte contaria duas vezes;
- alertas (`flags`): cada um e um codigo, um tom (loss, warning, gain, info) e
  os valores de que a tela monta o texto. As metas com data entram como
  alertas por meta, nao somadas: um mesmo aporte alimenta a meta da carteira e
  a do patrimonio, entao somar o necessario de cada uma contaria duas vezes.
"""

import calendar

from dates import month_key
from db import get_db, new_id, row_to_dict, utc_timestamp
from money import rounded_money
from services.contributions import movement_flow
from services.goals import list_goals
from services.investments import fetch_investments, investment_operation_date
from services.invoices import local_today
from services.sharing import own_amount_sql
from source_types import INVESTMENT_CASH_SOURCE_TYPE, INVOICE_PAYMENT_SOURCE_TYPES
from validators import (
    normalize_month,
    parse_number,
    parse_optional_number,
    require_month,
    safe_float,
)

INVESTMENT_CATEGORY = "Investimento"
# Gasto a partir deste percentual do plano: alerta de "quase no limite"
# (o mesmo limiar do orcamento por categoria).
SPEND_WARNING_PERCENT = 80
# Ritmo: o gasto ate hoje passa do proporcional ao dia em mais de 10%.
PACE_TOLERANCE = 1.10
# Nos primeiros dias o ritmo nao diz nada (aluguel e contas fixas caem cedo).
PACE_MIN_DAY = 8
# Nos ultimos dias do mes o aporte que falta vira alerta, nao lembrete.
INVEST_DEADLINE_DAYS = 7


def fetch_plan_for_month(conn, current_user_id, month):
    """O plano que vale em `month`: o do proprio mes ou o mais recente anterior."""
    return conn.execute(
        """
        SELECT * FROM monthly_plans
        WHERE user_id = ? AND month <= ?
        ORDER BY month DESC
        LIMIT 1
        """,
        (current_user_id, month),
    ).fetchone()


def month_banking_totals(conn, current_user_id, month):
    """(gasto nas contas, gasto no cartao, receita) do mes, em reais.

    So a parte do dono (032): o que era de outra pessoa nao e gasto nem renda dele.
    """
    own = own_amount_sql()
    invoice_types = sorted(INVOICE_PAYMENT_SOURCE_TYPES)
    invoice_placeholders = ", ".join("?" for _ in invoice_types)
    row = conn.execute(
        f"""
        SELECT
          SUM(CASE WHEN type = 'EXPENSE' THEN {own} ELSE 0 END) AS spent,
          SUM(CASE WHEN type = 'INCOME' THEN {own} ELSE 0 END) AS income
        FROM transactions
        WHERE user_id = ?
          AND type IN ('EXPENSE', 'INCOME')
          AND substr(date, 1, 7) = ?
          AND COALESCE(source_type, '') NOT IN ({invoice_placeholders})
          AND COALESCE(category, '') NOT LIKE 'Pagamento Fatura%'
          AND COALESCE(source_type, '') <> ?
          AND COALESCE(category, '') <> ?
        """,
        (current_user_id, month, *invoice_types, INVESTMENT_CASH_SOURCE_TYPE, INVESTMENT_CATEGORY),
    ).fetchone()
    card = conn.execute(
        f"""
        SELECT SUM({own}) AS spent FROM cc_expenses
        WHERE user_id = ? AND substr(purchase_date, 1, 7) = ?
        """,
        (current_user_id, month),
    ).fetchone()
    return safe_float(row["spent"]), safe_float(card["spent"]), safe_float(row["income"])


def month_investment_flow(investments, month):
    """(aportes, resgates) brutos do mes, a partir das operacoes em reais."""
    aportes = 0.0
    resgates = 0.0
    for investment in investments:
        flow = movement_flow(investment)
        if not flow or investment_operation_date(investment)[:7] != month:
            continue
        side, amount = flow
        if amount <= 0:
            continue
        if side == "aportes":
            aportes += amount
        else:
            resgates += amount
    return rounded_money(aportes), rounded_money(resgates)


def month_period(month, today):
    this_month = month_key(today)
    if month < this_month:
        return "PAST"
    if month > this_month:
        return "FUTURE"
    return "CURRENT"


def serialize_plan(row, month):
    if not row:
        return None
    item = row_to_dict(row)
    spend = rounded_money(row["spend_amount"])
    invest = rounded_money(row["invest_amount"])
    income = rounded_money(row["income_amount"]) if row["income_amount"] is not None else None
    item.update({
        "spend_amount": spend,
        "invest_amount": invest,
        "income_amount": income,
        "source_month": row["month"],
        "month": month,
        "inherited": row["month"] != month,
        # O que sobra da renda esperada depois de gastar e investir o planejado.
        "planned_leftover": rounded_money(income - spend - invest) if income is not None else None,
    })
    return item


def spend_flags(plan, spent, period, day, days_in_month):
    planned = plan["spend_amount"]
    if spent > planned:
        return [{"code": "SPEND_OVER", "tone": "loss", "amount": rounded_money(spent - planned)}]
    if period == "CURRENT" and day >= PACE_MIN_DAY and planned > 0:
        expected = planned * day / days_in_month
        projected = rounded_money(spent / day * days_in_month)
        if spent > expected * PACE_TOLERANCE and projected > planned:
            return [{
                "code": "SPEND_PACE",
                "tone": "warning",
                "amount": projected,
                "over": rounded_money(projected - planned),
            }]
    if planned > 0 and spent / planned * 100 >= SPEND_WARNING_PERCENT:
        return [{"code": "SPEND_NEAR", "tone": "warning", "amount": rounded_money(planned - spent)}]
    if period == "PAST":
        return [{"code": "SPEND_KEPT", "tone": "gain", "amount": rounded_money(planned - spent)}]
    return []


def invest_flags(plan, invested, period, day, days_in_month):
    planned = plan["invest_amount"]
    if planned <= 0:
        return []
    missing = rounded_money(planned - invested)
    if missing <= 0:
        return [{"code": "INVEST_DONE", "tone": "gain", "amount": rounded_money(invested)}]
    if period == "PAST":
        return [{"code": "INVEST_MISSED", "tone": "loss", "amount": missing}]
    if period == "CURRENT":
        days_left = days_in_month - day
        tone = "warning" if days_left < INVEST_DEADLINE_DAYS else "info"
        return [{"code": "INVEST_PENDING", "tone": tone, "amount": missing, "days_left": days_left}]
    return []


def income_flags(plan):
    income = plan["income_amount"]
    if income is None:
        return []
    committed = rounded_money(plan["spend_amount"] + plan["invest_amount"])
    if committed > income:
        return [{"code": "PLAN_OVER_INCOME", "tone": "loss", "amount": rounded_money(committed - income)}]
    return []


def goal_flags(plan, goals):
    """Uma por meta com data e ainda nao alcancada: o plano cobre o aporte necessario?"""
    flags = []
    for goal in goals:
        needed = goal.get("required_contribution")
        if needed is None or goal.get("reached"):
            continue
        covered = plan["invest_amount"] >= needed
        flags.append({
            "code": "GOAL_COVERED" if covered else "GOAL_SHORT",
            "tone": "gain" if covered else "warning",
            "goal_id": goal["id"],
            "goal_name": goal["name"],
            "target_month": goal.get("target_month"),
            "amount": rounded_money(needed),
            "missing": rounded_money(max(needed - plan["invest_amount"], 0.0)),
        })
    return flags


def build_monthly_plan(current_user_id, month):
    today = local_today()
    period = month_period(month, today)
    year, month_number = (int(part) for part in month.split("-"))
    days_in_month = calendar.monthrange(year, month_number)[1]
    day = today.day if period == "CURRENT" else (days_in_month if period == "PAST" else 0)

    with get_db() as conn:
        row = fetch_plan_for_month(conn, current_user_id, month)
        spent_accounts, spent_cards, income = month_banking_totals(conn, current_user_id, month)
    aportes, resgates = month_investment_flow(fetch_investments(current_user_id), month)

    spent = rounded_money(spent_accounts + spent_cards)
    invested = rounded_money(aportes - resgates)
    plan = serialize_plan(row, month)

    result = {
        "month": month,
        "period": period,
        "day": day,
        "days_in_month": days_in_month,
        "plan": plan,
        "actual": {
            "spent": spent,
            "spent_accounts": rounded_money(spent_accounts),
            "spent_cards": rounded_money(spent_cards),
            "income": rounded_money(income),
            "aportes": aportes,
            "resgates": resgates,
            "invested": invested,
        },
        "progress": None,
        "flags": [],
    }
    if not plan:
        return result

    spend_planned = plan["spend_amount"]
    invest_planned = plan["invest_amount"]
    result["progress"] = {
        "spend_percent": rounded_money(spent / spend_planned * 100) if spend_planned > 0 else None,
        "spend_remaining": rounded_money(spend_planned - spent),
        "invest_percent": rounded_money(max(invested, 0.0) / invest_planned * 100) if invest_planned > 0 else None,
        "invest_remaining": rounded_money(max(invest_planned - invested, 0.0)),
        # Quanto do gasto planejado "cabe" ate hoje, no ritmo uniforme do mes.
        "spend_expected_to_date": (
            rounded_money(spend_planned * day / days_in_month) if period == "CURRENT" else None
        ),
    }

    flags = [
        *income_flags(plan),
        *spend_flags(plan, spent, period, day, days_in_month),
        *invest_flags(plan, invested, period, day, days_in_month),
    ]
    # As metas olham de hoje para a frente: num mes passado nao ha o que cobrir.
    if period != "PAST":
        flags.extend(goal_flags(plan, list_goals(current_user_id)))
    result["flags"] = flags
    return result


def save_monthly_plan(current_user_id, payload):
    """Grava (ou troca) o plano do mes do payload; vale dali para a frente."""
    month = require_month(payload, "month", "Mes do plano")
    spend = rounded_money(parse_number(payload, "spend_amount", "Valor para gastar", minimum=0))
    invest = rounded_money(parse_number(payload, "invest_amount", "Valor para investir", minimum=0))
    raw_income = parse_optional_number(payload, "income_amount", "Renda esperada", minimum=0)
    income = rounded_money(raw_income) if raw_income is not None else None

    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM monthly_plans WHERE user_id = ? AND month = ?",
            (current_user_id, month),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE monthly_plans
                SET spend_amount = ?, invest_amount = ?, income_amount = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (spend, invest, income, utc_timestamp(), existing["id"], current_user_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO monthly_plans (id, user_id, month, spend_amount, invest_amount, income_amount)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (new_id(), current_user_id, month, spend, invest, income),
            )
    return build_monthly_plan(current_user_id, month)


def delete_monthly_plan(current_user_id, raw_month):
    """Apaga o plano gravado *neste* mes; o mes volta a herdar o anterior."""
    month = normalize_month(raw_month, "Mes do plano")
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM monthly_plans WHERE user_id = ? AND month = ?",
            (current_user_id, month),
        )
    if cursor.rowcount == 0:
        return None
    return build_monthly_plan(current_user_id, month)


def parse_month_arg(raw_month):
    if not raw_month:
        return month_key(local_today())
    return normalize_month(raw_month, "Mes do plano")

