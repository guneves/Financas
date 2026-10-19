"""Plano do mes (025, 038): a renda, quanto dela investir e gastar, e os alertas.

O plano parte da renda (038). A linha guarda a renda do mes em reais — o unico
valor digitado, obrigatorio — e dois percentuais dela, Investir e Gastar; as
categorias de dentro do Gastar sao os orcamentos (budgets), cada uma com o seu %
do Gastar. "Sem destino" (100% - Investir - Gastar) e "Sem categoria" (100% -
categorias) sao devolvidos, nunca gravados, e todo valor em reais e calculado
na leitura sobre a renda *planejada* (services/budgets.py). A renda recebida
vem so para comparar; nunca muda o plano.

Um mes sem linha propria herda o plano mais recente anterior a ele, categorias
incluidas: o usuario define uma vez e o plano vale ate ser trocado. O realizado
e o de sempre, calculado na leitura:

- gasto do mes = saidas das contas (EXPENSE), sem transferencias, sem
  pagamento de fatura e sem aporte (o caixa de uma operacao; o aporte digitado
  e uma transferencia para a Corretora — a mesma regra de
  `isInvestmentOutflow()` do Inicio), mais as compras no cartao, inteiras, no mes da compra (decisao 1,
  a mesma do orcamento por categoria);
- receita do mes = entradas das contas (INCOME), sem resgate nem provento pago;
- aporte do mes = aportes - resgates vistos das contas, o "Investido" do
  Inicio (dono, 2026-10-19): o que saiu de uma conta para a Corretora
  (transferencia) ou para a carteira (o caixa de uma operacao numa conta que nao
  e Corretora), menos o que voltou dela. Uma compra feita com o dinheiro que ja
  estava na Corretora nao e dinheiro novo e nao conta;
- cada categoria: a regra do orcamento (rollover, subcategoria soma no pai);
- Saldo do plano = Gastar em reais - gasto do mes. E o unico "quanto ainda
  posso gastar": o `spend_remaining` do progresso e o mesmo numero, e
  Disponivel por dia e ele / dias que faltam no mes (hoje incluido);
- alertas (`flags`): cada um e um codigo, um tom (loss, warning, gain, info) e
  os valores de que a tela monta o texto. As metas com data entram como
  alertas por meta, nao somadas: um mesmo aporte alimenta a meta da carteira e
  a do patrimonio, entao somar o necessario de cada uma contaria duas vezes.

Um plano de antes da 038 sem renda nao tem percentuais: `needs_income`, nada e
calculado dele, e o PUT que traz a renda o converte (e as categorias dos meses
que ele rege) com as formulas da migration.
"""

import calendar
from decimal import Decimal

from dates import month_key
from db import get_db, new_id, utc_timestamp
from money import percent_of, rounded_money
from services.budgets import (
    HUNDRED,
    build_budget_month,
    convert_legacy_budgets,
    fetch_plan_for_month,
    materialize_categories,
    percent_json,
    plan_figures,
)
from services.goals import list_goals
from services.investments import PORTFOLIO_ACCOUNT_TYPE
from services.invoices import local_today, signed_amount_sql
from services.sharing import own_amount_sql
from source_types import INVESTMENT_SOURCE_TYPES, INVOICE_PAYMENT_SOURCE_TYPES
from validators import (
    ValidationError,
    normalize_month,
    parse_number,
    parse_percent,
    require_month,
    safe_float,
    to_percent,
)

# Gasto a partir deste percentual do plano: alerta de "quase no limite"
# (o mesmo limiar do orcamento por categoria).
SPEND_WARNING_PERCENT = 80
# Ritmo: o gasto ate hoje passa do proporcional ao dia em mais de 10%.
PACE_TOLERANCE = 1.10
# Nos primeiros dias o ritmo nao diz nada (aluguel e contas fixas caem cedo).
PACE_MIN_DAY = 8
# Nos ultimos dias do mes o aporte que falta vira alerta, nao lembrete.
INVEST_DEADLINE_DAYS = 7


def month_banking_totals(conn, current_user_id, month):
    """(gasto nas contas, gasto no cartao, receita) do mes, em reais.

    So a parte do dono (032): o que era de outra pessoa nao e gasto nem renda dele.
    """
    own = own_amount_sql()
    skipped_types = (*sorted(INVOICE_PAYMENT_SOURCE_TYPES), *INVESTMENT_SOURCE_TYPES)
    skipped_placeholders = ", ".join("?" for _ in skipped_types)
    row = conn.execute(
        f"""
        SELECT
          SUM(CASE WHEN type = 'EXPENSE' THEN {own} ELSE 0 END) AS spent,
          SUM(CASE WHEN type = 'INCOME' THEN {own} ELSE 0 END) AS income
        FROM transactions
        WHERE user_id = ?
          AND type IN ('EXPENSE', 'INCOME')
          AND substr(date, 1, 7) = ?
          AND COALESCE(source_type, '') NOT IN ({skipped_placeholders})
          AND COALESCE(category, '') NOT LIKE 'Pagamento Fatura%'
        """,
        (current_user_id, month, *skipped_types),
    ).fetchone()
    card = conn.execute(
        f"""
        SELECT SUM({signed_amount_sql()} * {own}) AS spent FROM cc_expenses
        WHERE user_id = ? AND substr(purchase_date, 1, 7) = ?
        """,
        (current_user_id, month),
    ).fetchone()
    return safe_float(row["spent"]), safe_float(card["spent"]), safe_float(row["income"])


def month_investment_flow(conn, current_user_id, month):
    """(aportes, resgates) do mes vistos das contas, em reais.

    A regra de `bankingTransactions()` + `buildMonthlyFlow()` do Inicio: a
    transferencia de um banco para a Corretora e aporte (e a de volta,
    resgate), e o caixa da carteira (`INVESTMENT_SOURCE_TYPES`) numa conta que
    nao e Corretora e aporte na saida e resgate na entrada. O que acontece
    dentro da Corretora fica de fora.
    """
    placeholders = ", ".join("?" for _ in INVESTMENT_SOURCE_TYPES)
    from_bank = f"COALESCE(origin.type, '') != '{PORTFOLIO_ACCOUNT_TYPE}'"
    to_portfolio = f"COALESCE(target.type, '') = '{PORTFOLIO_ACCOUNT_TYPE}'"
    portfolio_cash = f"COALESCE(t.source_type, '') IN ({placeholders})"
    row = conn.execute(
        f"""
        SELECT
          SUM(CASE
                WHEN t.type = 'TRANSFER' AND {from_bank} AND {to_portfolio} THEN t.amount
                WHEN t.type = 'EXPENSE' AND {from_bank} AND {portfolio_cash} THEN t.amount
                ELSE 0 END) AS aportes,
          SUM(CASE
                WHEN t.type = 'TRANSFER' AND NOT {from_bank} AND NOT {to_portfolio} THEN t.amount
                WHEN t.type = 'INCOME' AND {from_bank} AND {portfolio_cash} THEN t.amount
                ELSE 0 END) AS resgates
        FROM transactions t
        LEFT JOIN accounts origin ON origin.id = t.account_id
        LEFT JOIN accounts target ON target.id = t.transfer_account_id
        WHERE t.user_id = ? AND substr(t.date, 1, 7) = ?
        """,
        (*INVESTMENT_SOURCE_TYPES, *INVESTMENT_SOURCE_TYPES, current_user_id, month),
    ).fetchone()
    return rounded_money(safe_float(row["aportes"])), rounded_money(safe_float(row["resgates"]))


def month_period(month, today):
    this_month = month_key(today)
    if month < this_month:
        return "PAST"
    if month > this_month:
        return "FUTURE"
    return "CURRENT"


def plan_balance(figures, spent):
    """Saldo do plano: Gastar em reais - gasto do mes. None sem renda no plano."""
    if not figures:
        return None
    return rounded_money(figures["spend_amount"] - spent)


def serialize_plan(row, month, figures):
    if not row:
        return None
    item = {
        "id": row["id"],
        "month": month,
        "source_month": row["month"],
        "inherited": row["month"] != month,
        "needs_income": figures is None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if figures is None:
        # Plano antigo, sem renda: os reais de antes, so para a tela mostrar o
        # que havia e pedir a renda. Nada e calculado deles.
        item.update({
            "income_amount": rounded_money(row["income_amount"]) if row["income_amount"] is not None else None,
            "invest_percent": None,
            "spend_percent": None,
            "unallocated_percent": None,
            "invest_amount": None,
            "spend_amount": None,
            "unallocated_amount": None,
            "planned_leftover": None,
            "legacy": {
                "spend_amount": rounded_money(row["spend_amount"]),
                "invest_amount": rounded_money(row["invest_amount"]),
            },
        })
        return item
    item.update({
        "income_amount": figures["income"],
        "invest_percent": percent_json(figures["invest_percent"]),
        "spend_percent": percent_json(figures["spend_percent"]),
        "unallocated_percent": percent_json(figures["unallocated_percent"]),
        "invest_amount": figures["invest_amount"],
        "spend_amount": figures["spend_amount"],
        "unallocated_amount": figures["unallocated_amount"],
        # O nome antigo de "Sem destino" (a tela de antes le este).
        "planned_leftover": figures["unallocated_amount"],
        "legacy": None,
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
    """So um plano convertido pela 038 passa de 100%: a API recusa os novos."""
    if plan["unallocated_percent"] >= 0:
        return []
    committed = rounded_money(plan["spend_amount"] + plan["invest_amount"])
    return [{"code": "PLAN_OVER_INCOME", "tone": "loss", "amount": rounded_money(committed - plan["income"])}]


def category_flags(plan, categories):
    """Categorias que passam do Gastar (so as convertidas pela 038 chegam aqui)."""
    totals = categories["totals"]
    if totals["unassigned_percent"] >= 0:
        return []
    return [{
        "code": "CATEGORIES_OVER_SPEND",
        "tone": "loss",
        "amount": rounded_money(totals["planned"] - plan["spend_amount"]),
        "percent": totals["assigned_percent"],
    }]


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


def level(percent, amount, realized, remaining):
    return {
        "percent": percent_json(percent),
        "amount": amount,
        "realized": realized,
        "remaining": remaining,
        # Quanto do planejado ja foi realizado, em %.
        "progress_percent": (
            rounded_money(max(realized, 0.0) / amount * 100) if amount else None
        ),
    }


def build_budget_view(conn, current_user_id, month):
    """GET /api/budgets: as categorias do mes e o Saldo do plano, o mesmo do plano."""
    result = build_budget_month(conn, current_user_id, month)
    figures = plan_figures(fetch_plan_for_month(conn, current_user_id, month))
    spent_accounts, spent_cards, _ = month_banking_totals(conn, current_user_id, month)
    spent = rounded_money(spent_accounts + spent_cards)
    result["totals"]["plan_spent"] = spent
    result["totals"]["plan_balance"] = plan_balance(figures, spent)
    return result


def build_monthly_plan(current_user_id, month):
    today = local_today()
    period = month_period(month, today)
    year, month_number = (int(part) for part in month.split("-"))
    days_in_month = calendar.monthrange(year, month_number)[1]
    day = today.day if period == "CURRENT" else (days_in_month if period == "PAST" else 0)
    # Dias que faltam, hoje incluido: a base do "Disponivel por dia".
    days_remaining = {"CURRENT": days_in_month - day + 1, "PAST": 0}.get(period, days_in_month)

    with get_db() as conn:
        row = fetch_plan_for_month(conn, current_user_id, month)
        spent_accounts, spent_cards, income = month_banking_totals(conn, current_user_id, month)
        categories = build_budget_month(conn, current_user_id, month)
        aportes, resgates = month_investment_flow(conn, current_user_id, month)

    spent = rounded_money(spent_accounts + spent_cards)
    invested = rounded_money(aportes - resgates)
    figures = plan_figures(row)
    balance = plan_balance(figures, spent)
    daily = rounded_money(balance / days_remaining) if balance is not None and days_remaining else None
    nothing = {"percent": None, "amount": None}

    result = {
        "month": month,
        "period": period,
        "day": day,
        "days_in_month": days_in_month,
        "days_remaining": days_remaining,
        # Ha algo do mes (o plano ou uma categoria) que so vira reais com a renda.
        "needs_income": (row is not None and figures is None) or categories["needs_income"],
        "plan": serialize_plan(row, month, figures),
        "income": {
            "planned": figures["income"] if figures else None,
            # Regra de sempre (entradas das contas, sem resgate): so compara.
            "received": rounded_money(income),
        },
        "invest": level(
            figures["invest_percent"] if figures else None,
            figures["invest_amount"] if figures else None,
            invested,
            rounded_money(max(figures["invest_amount"] - invested, 0.0)) if figures else None,
        ),
        "spend": level(
            figures["spend_percent"] if figures else None,
            figures["spend_amount"] if figures else None,
            spent,
            balance,
        ),
        # Sem destino: a renda que nao vai nem para investir nem para gastar.
        "unallocated": {
            "percent": percent_json(figures["unallocated_percent"]),
            "amount": figures["unallocated_amount"],
        } if figures else nothing,
        "categories": {
            "source_month": categories["source_month"],
            "inherited": categories["inherited"],
            "needs_income": categories["needs_income"],
            "items": categories["items"],
            "assigned_percent": categories["totals"]["assigned_percent"],
            "assigned_amount": categories["totals"]["planned"],
            # Sem categoria: o Gastar que nenhuma categoria leva.
            "unassigned": {
                "percent": categories["totals"]["unassigned_percent"],
                "amount": categories["totals"]["unassigned_amount"],
            },
            "totals": categories["totals"],
        },
        "plan_balance": balance,
        "daily_available": daily,
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
    if not figures:
        return result

    spend_planned = figures["spend_amount"]
    invest_planned = figures["invest_amount"]
    result["progress"] = {
        "spend_percent": rounded_money(spent / spend_planned * 100) if spend_planned > 0 else None,
        # O Saldo do plano, o mesmo numero de `plan_balance`.
        "spend_remaining": balance,
        "invest_percent": rounded_money(max(invested, 0.0) / invest_planned * 100) if invest_planned > 0 else None,
        "invest_remaining": rounded_money(max(invest_planned - invested, 0.0)),
        # Quanto do gasto planejado "cabe" ate hoje, no ritmo uniforme do mes.
        "spend_expected_to_date": (
            rounded_money(spend_planned * day / days_in_month) if period == "CURRENT" else None
        ),
    }

    flags = [
        *income_flags(figures),
        *category_flags(figures, categories),
        *spend_flags(figures, spent, period, day, days_in_month),
        *invest_flags(figures, invested, period, day, days_in_month),
    ]
    # As metas olham de hoje para a frente: num mes passado nao ha o que cobrir.
    if period != "PAST":
        flags.extend(goal_flags(figures, list_goals(current_user_id)))
    result["flags"] = flags
    return result


def parse_income(payload):
    if payload.get("income_amount") in (None, ""):
        raise ValidationError("Informe a renda do mes: o plano parte dela.")
    income = rounded_money(parse_number(payload, "income_amount", "Renda do mes", minimum=0))
    if income <= 0:
        raise ValidationError("A renda do mes deve ser maior que zero.")
    return income


def legacy_percent(amount, income):
    """A formula da 038: um valor antigo em reais sobre a renda, em %."""
    return to_percent(Decimal(str(safe_float(amount))) * HUNDRED / Decimal(str(income)))


def save_monthly_plan(current_user_id, payload):
    """Grava (ou troca) o plano do mes do payload; vale dali para a frente.

    Pede a renda e os dois percentuais. Num mes cujo plano ainda e o antigo, sem
    renda, os percentuais podem faltar: saem dos reais antigos sobre a renda
    nova (a conversao da 038). Em qualquer caso as categorias antigas dos meses
    que este plano rege viram % do novo Gastar.
    """
    month = require_month(payload, "month", "Mes do plano")
    income = parse_income(payload)
    explicit = any(payload.get(key) not in (None, "") for key in ("invest_percent", "spend_percent"))

    with get_db() as conn:
        current = fetch_plan_for_month(conn, current_user_id, month)
        if not explicit and current is not None and current["spend_percent"] is None:
            invest_percent = legacy_percent(current["invest_amount"], income)
            spend_percent = legacy_percent(current["spend_amount"], income)
        else:
            invest_percent = parse_percent(payload, "invest_percent", "Investir (%)")
            spend_percent = parse_percent(payload, "spend_percent", "Gastar (%)")
        if invest_percent + spend_percent > HUNDRED:
            raise ValidationError(
                f"Investir e Gastar somam {float(invest_percent + spend_percent):g}%: passam de 100% da renda."
            )

        values = (income, format(invest_percent, "f"), format(spend_percent, "f"))
        if current is not None and current["month"] == month:
            conn.execute(
                """
                UPDATE monthly_plans
                SET income_amount = ?, invest_percent = ?, spend_percent = ?, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (*values, utc_timestamp(), current["id"], current_user_id),
            )
        else:
            # O mes deixa de herdar: as categorias herdadas vem junto, senao o
            # plano novo comecaria sem nenhuma. Os reais antigos ficam 0 (NOT NULL).
            materialize_categories(conn, current_user_id, month)
            conn.execute(
                """
                INSERT INTO monthly_plans (id, user_id, month, spend_amount, invest_amount,
                                           income_amount, invest_percent, spend_percent)
                VALUES (?, ?, ?, 0, 0, ?, ?, ?)
                """,
                (new_id(), current_user_id, month, *values),
            )
        convert_legacy_budgets(conn, current_user_id, month, percent_of(income, spend_percent))
    return build_monthly_plan(current_user_id, month)


def delete_monthly_plan(current_user_id, raw_month):
    """Apaga o plano gravado *neste* mes, com as categorias dele.

    O mes volta a herdar o plano anterior, inteiro (categorias incluidas).
    """
    month = normalize_month(raw_month, "Mes do plano")
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM monthly_plans WHERE user_id = ? AND month = ?",
            (current_user_id, month),
        )
        if cursor.rowcount == 0:
            return None
        conn.execute(
            "DELETE FROM budgets WHERE user_id = ? AND month = ?",
            (current_user_id, month),
        )
    return build_monthly_plan(current_user_id, month)


def parse_month_arg(raw_month):
    if not raw_month:
        return month_key(local_today())
    return normalize_month(raw_month, "Mes do plano")
