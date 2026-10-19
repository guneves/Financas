"""Orcamento por categoria (009) e a base do plano do mes (025, 038).

Um orcamento e um plano, nao um registro: a linha e chaveada por
(categoria, mes), apagar nao exige confirmacao, e o saldo que acumula
(`rollover`) e calculado na leitura, nunca gravado.

Desde a 038 o plano parte da renda. A linha do plano guarda a renda (R$) e dois
percentuais dela, Investir e Gastar; cada categoria guarda o seu percentual *do
Gastar*. Todo valor em reais sai daqui, na leitura:

    Gastar R$    = renda x Gastar %            (percent_of, ROUND_HALF_UP)
    categoria R$ = Gastar R$ x % da categoria

A base e sempre a renda planejada; a recebida so aparece para comparar.

Heranca. Um mes sem plano proprio usa o mais recente anterior a ele, e as
categorias vem junto: o conjunto de categorias de um mes e o do mes mais recente
(ate ele) que tenha linha de plano ou linha de orcamento
(`category_source_month()`). Mexer numa categoria de um mes herdado primeiro
faz do mes um plano proprio — copia o plano e as categorias herdadas
(`materialize_month()`) — e so entao aplica a mudanca; assim a mudanca nao vaza
para os meses de antes, e apagar a ultima categoria do mes nao traz de volta as
herdadas.

Linha antiga. Percentual NULL e uma linha de antes da 038 que a migration nao
conseguiu converter (o plano do mes nao tinha renda): `needs_income`, nada e
calculado dela, e o PUT do plano que traz a renda converte com as mesmas formulas
(`convert_legacy_budgets()`). As colunas em reais (`planned_amount`,
`spend_amount`, `invest_amount`) so sao lidas para isso.

O plano em si (realizado, alertas) fica em services/monthly_plan.py; aqui esta o
que as duas telas dividem: a linha do plano que vale no mes e o Gastar em reais.
"""

from decimal import Decimal

from db import new_id, row_to_dict, utc_timestamp
from money import percent_of, rounded_money
from services.accounts import category_ids_by_name, fetch_category
from services.invoices import signed_amount_sql
from services.sharing import own_amount_sql
from source_types import INVESTMENT_SOURCE_TYPES, INVOICE_PAYMENT_SOURCE_TYPES
from validators import ValidationError, safe_float, shift_month, to_percent

HUNDRED = Decimal(100)
# Gasto a partir deste percentual do disponivel: "Perto do limite".
BUDGET_WARNING_PERCENT = 80


def stored_percent(value):
    """O percentual guardado (TEXT, 038) como Decimal; None numa linha antiga."""
    if value is None or value == "":
        return None
    return to_percent(value)


def percent_json(value):
    return float(value) if value is not None else None


# --- a linha do plano -------------------------------------------------------


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


def plan_figures(row):
    """Os niveis de um plano em % e em reais, ou None se ele ainda precisa da renda."""
    if not row or row["spend_percent"] is None or row["invest_percent"] is None:
        return None
    income = rounded_money(row["income_amount"])
    if income <= 0:
        return None
    invest_percent = stored_percent(row["invest_percent"])
    spend_percent = stored_percent(row["spend_percent"])
    invest_amount = percent_of(income, invest_percent)
    spend_amount = percent_of(income, spend_percent)
    return {
        "income": income,
        "invest_percent": invest_percent,
        "spend_percent": spend_percent,
        "invest_amount": invest_amount,
        "spend_amount": spend_amount,
        # Sem destino: o resto da renda. Os reais saem da subtracao dos reais ja
        # arredondados, entao os tres niveis somam a renda ao centavo.
        "unallocated_percent": HUNDRED - invest_percent - spend_percent,
        "unallocated_amount": rounded_money(income - invest_amount - spend_amount),
    }


def planned_spend(conn, current_user_id, month):
    """Gastar do mes em reais, ou None quando o plano do mes nao tem renda."""
    figures = plan_figures(fetch_plan_for_month(conn, current_user_id, month))
    return figures["spend_amount"] if figures else None


# --- o conjunto de categorias do mes ---------------------------------------


def category_source_month(conn, current_user_id, month):
    """De que mes vem as categorias de `month` (ele mesmo, ou o que ele herda)."""
    row = conn.execute(
        """
        SELECT MAX(month) AS month FROM (
            SELECT month FROM monthly_plans WHERE user_id = ? AND month <= ?
            UNION ALL
            SELECT month FROM budgets WHERE user_id = ? AND month <= ?
        )
        """,
        (current_user_id, month, current_user_id, month),
    ).fetchone()
    return row["month"] if row else None


def budget_rows_for_month(conn, current_user_id, month):
    """As linhas guardadas *em* `month` (sem heranca)."""
    return conn.execute(
        """
        SELECT b.*, c.name AS category_name, c.kind AS category_kind,
               c.parent_id AS category_parent_id, c.archived_at AS category_archived_at,
               parent.name AS parent_name
        FROM budgets b
        JOIN categories c ON c.id = b.category_id AND c.user_id = b.user_id
        LEFT JOIN categories parent ON parent.id = c.parent_id
        WHERE b.user_id = ? AND b.month = ?
        ORDER BY COALESCE(parent.name, c.name) COLLATE NOCASE,
                 c.parent_id IS NOT NULL,
                 c.name COLLATE NOCASE
        """,
        (current_user_id, month),
    ).fetchall()


def effective_budget_rows(conn, current_user_id, month):
    """(mes de origem, linhas) das categorias que valem em `month`."""
    source = category_source_month(conn, current_user_id, month)
    if not source:
        return None, []
    return source, budget_rows_for_month(conn, current_user_id, source)


def effective_budget_row(conn, current_user_id, category_id, month):
    """A linha da categoria que vale em `month`, propria ou herdada."""
    source = category_source_month(conn, current_user_id, month)
    if not source:
        return None
    return conn.execute(
        "SELECT * FROM budgets WHERE user_id = ? AND category_id = ? AND month = ?",
        (current_user_id, category_id, source),
    ).fetchone()


def assigned_percent(rows, *, exclude_id=None):
    """Soma dos percentuais das categorias (as linhas antigas, sem %, ficam fora)."""
    total = Decimal(0)
    for row in rows:
        if row["id"] == exclude_id:
            continue
        percent = stored_percent(row["planned_percent"])
        if percent is not None:
            total += percent
    return total


def ensure_categories_fit(total):
    if total > HUNDRED:
        raise ValidationError(
            f"As categorias passam de 100% do Gastar ({float(total):g}%). Reduza alguma antes."
        )


def copy_budget_rows(conn, current_user_id, source_month, to_month):
    """Copia as categorias de `source_month` para `to_month` (que nao tem nenhuma)."""
    for row in budget_rows_for_month(conn, current_user_id, source_month):
        conn.execute(
            """
            INSERT INTO budgets (id, user_id, category_id, month, planned_amount,
                                 planned_percent, rollover, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id(),
                current_user_id,
                row["category_id"],
                to_month,
                row["planned_amount"],
                row["planned_percent"],
                row["rollover"],
                row["note"],
            ),
        )


def materialize_categories(conn, current_user_id, month):
    """Se `month` herda as categorias, grava a copia delas nele."""
    source = category_source_month(conn, current_user_id, month)
    if source and source != month:
        copy_budget_rows(conn, current_user_id, source, month)


def materialize_month(conn, current_user_id, month):
    """Faz de `month` um plano proprio: copia as categorias e o plano herdados.

    Chamado antes de qualquer mudanca nas categorias de um mes herdado. O plano
    vem junto para o conjunto do mes ficar dele mesmo quando esvazia: sem a
    linha do plano, apagar a ultima categoria faria o mes voltar a herdar.
    """
    materialize_categories(conn, current_user_id, month)
    plan = fetch_plan_for_month(conn, current_user_id, month)
    if plan and plan["month"] != month:
        conn.execute(
            """
            INSERT INTO monthly_plans (id, user_id, month, spend_amount, invest_amount,
                                       income_amount, invest_percent, spend_percent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id(),
                current_user_id,
                month,
                plan["spend_amount"],
                plan["invest_amount"],
                plan["income_amount"],
                plan["invest_percent"],
                plan["spend_percent"],
            ),
        )


def convert_legacy_budgets(conn, current_user_id, from_month, spend_amount):
    """Converte as categorias antigas (sem %) dos meses que o plano de `from_month` rege.

    Mesma formula da 038: planned% = planned_amount / Gastar do mes. Os meses
    regidos vao de `from_month` ate o proximo plano gravado (exclusive). Sem
    Gastar em reais nao ha base, e a linha continua esperando.
    """
    if not spend_amount or spend_amount <= 0:
        return 0
    next_plan = conn.execute(
        "SELECT MIN(month) AS month FROM monthly_plans WHERE user_id = ? AND month > ?",
        (current_user_id, from_month),
    ).fetchone()["month"]
    rows = conn.execute(
        """
        SELECT id, planned_amount FROM budgets
        WHERE user_id = ? AND planned_percent IS NULL AND month >= ?
          AND (? IS NULL OR month < ?)
        """,
        (current_user_id, from_month, next_plan, next_plan),
    ).fetchall()
    base = Decimal(str(spend_amount))
    for row in rows:
        percent = to_percent(Decimal(str(safe_float(row["planned_amount"]))) * HUNDRED / base)
        conn.execute(
            "UPDATE budgets SET planned_percent = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (format(percent, "f"), utc_timestamp(), row["id"], current_user_id),
        )
    return len(rows)


# --- realizado ---------------------------------------------------------------


def budget_month_lines(conn, current_user_id, month):
    """Cada lancamento que entra no realizado do mes, com a categoria resolvida.

    Lancamentos e compras no cartao com category_id preenchido contam direto
    nessa categoria — "Lazer › Outros" nao e o "Outros" da raiz (035); os que so
    tem o texto (categoria livre) sao resolvidos pelo nome, a raiz antes.
    TRANSFER fica de fora: mover dinheiro entre contas proprias nao e gasto nem
    receita.

    Cartao (decisao 1, 2026-09-23): a compra conta inteira, na categoria dela,
    no mes em que foi feita — todas as parcelas, a mesma regra de "Despesas por
    categoria" no Inicio. Por isso o pagamento da fatura nao conta: ele e a soma
    de compras ja contadas. Pagamento de fatura e o lancamento com source_type
    de fatura, ou, nos anteriores ao pagamento pelo servidor, a categoria
    "Pagamento Fatura...". As parcelas de uma compra viram uma linha so.

    De quem e (032): conta so a parte do dono — a pizza dividida pesa no
    orcamento so pela fatia dele (services/sharing.py). `amount` e essa parte;
    `total_amount`, o valor cheio da linha.

    E desta lista que sai o realizado (`budget_spend_by_category`), entao o que
    a tela abre debaixo de uma categoria sempre soma o valor que ela mostra.
    """
    name_to_id = category_ids_by_name(conn, current_user_id)

    skipped_types = (*sorted(INVOICE_PAYMENT_SOURCE_TYPES), *INVESTMENT_SOURCE_TYPES)
    skipped_placeholders = ", ".join("?" for _ in skipped_types)
    rows = conn.execute(
        f"""
        SELECT t.id, t.type, t.category_id, t.category, t.date, t.description,
               t.amount AS total_amount, {own_amount_sql("t.")} AS own_amount,
               t.share_mode, a.name AS account_name
        FROM transactions t
        LEFT JOIN accounts a ON a.id = t.account_id AND a.user_id = t.user_id
        WHERE t.user_id = ?
          AND t.type <> 'TRANSFER'
          AND substr(t.date, 1, 7) = ?
          AND COALESCE(t.source_type, '') NOT IN ({skipped_placeholders})
          AND COALESCE(t.category, '') NOT LIKE 'Pagamento Fatura%'
        ORDER BY t.date, t.created_at, t.id
        """,
        (current_user_id, month, *skipped_types),
    ).fetchall()
    card_rows = conn.execute(
        f"""
        SELECT e.id, e.card_id, e.category, e.category_id, e.purchase_date, e.description, e.kind,
               e.installment_info, e.client_id, e.share_mode,
               e.amount * {signed_amount_sql("e.")} AS total_amount,
               {signed_amount_sql("e.")} * {own_amount_sql("e.")} AS own_amount,
               c.name AS card_name
        FROM cc_expenses e
        LEFT JOIN credit_cards c ON c.id = e.card_id AND c.user_id = e.user_id
        WHERE e.user_id = ?
          AND substr(e.purchase_date, 1, 7) = ?
        ORDER BY e.purchase_date, e.created_at, e.id
        """,
        (current_user_id, month),
    ).fetchall()

    lines = []
    for row in rows:
        lines.append(
            {
                "id": row["id"],
                "source": "TRANSACTION",
                "type": row["type"],
                "category_id": row["category_id"] or name_to_id.get(row["category"]),
                "category": row["category"],
                "date": row["date"],
                "description": row["description"],
                "amount": safe_float(row["own_amount"]),
                "total_amount": safe_float(row["total_amount"]),
                "shared": bool(row["share_mode"]),
                "account_name": row["account_name"],
            }
        )

    purchases = {}
    for row in card_rows:
        installments = str(row["installment_info"] or "1/1").split("/")[-1]
        key = (
            row["card_id"],
            row["kind"],
            row["purchase_date"],
            row["description"],
            row["category"],
            row["client_id"] or "",
            installments,
        )
        line = purchases.get(key)
        if line is None:
            line = purchases[key] = {
                "id": row["id"],
                "source": "CARD",
                "type": "EXPENSE",
                "category_id": row["category_id"] or name_to_id.get(row["category"]),
                "category": row["category"],
                "date": row["purchase_date"],
                "description": row["description"],
                "amount": 0.0,
                "total_amount": 0.0,
                "shared": False,
                "card_name": row["card_name"],
                "refund": row["kind"] == "REFUND",
                "installments": 0,
            }
            lines.append(line)
        line["amount"] += safe_float(row["own_amount"])
        line["total_amount"] += safe_float(row["total_amount"])
        line["shared"] = line["shared"] or bool(row["share_mode"])
        line["installments"] += 1
    lines.sort(key=lambda line: (line["date"] or "", line["source"]))
    return lines


def budget_spend_by_category(conn, current_user_id, month):
    """Realizado do mes por categoria: {category_id: {"EXPENSE": x, "INCOME": y}}.

    A soma de `budget_month_lines()` — as regras do que conta estao la.
    """
    totals = {}
    for line in budget_month_lines(conn, current_user_id, month):
        category_id = line["category_id"]
        if not category_id:
            continue
        bucket = totals.setdefault(category_id, {"EXPENSE": 0.0, "INCOME": 0.0})
        bucket[line["type"]] = bucket.get(line["type"], 0.0) + line["amount"]
    return totals


def budget_realized(category, spend):
    """Quanto a categoria realizou: receita se kind=INCOME, despesa nos demais."""
    if not category:
        return 0.0
    bucket = spend.get(category["id"], {}) if spend else {}
    if category["kind"] == "INCOME":
        return safe_float(bucket.get("INCOME"))
    return safe_float(bucket.get("EXPENSE"))


def fetch_budget(conn, current_user_id, budget_id):
    return conn.execute(
        "SELECT * FROM budgets WHERE id = ? AND user_id = ?",
        (budget_id, current_user_id),
    ).fetchone()


def budget_children_by_parent(conn, current_user_id):
    children = {}
    for row in conn.execute(
        "SELECT id, parent_id FROM categories WHERE user_id = ? AND parent_id IS NOT NULL",
        (current_user_id,),
    ).fetchall():
        children.setdefault(row["parent_id"], []).append(row["id"])
    return children


def budgeted_ids_for_month(conn, current_user_id, month):
    """As categorias com orcamento que vale em `month` (proprio ou herdado)."""
    _, rows = effective_budget_rows(conn, current_user_id, month)
    return {row["category_id"] for row in rows}


def budget_month_spent(conn, current_user_id, category_id, month, *, spend=None, budgeted_ids=None, children=None):
    """Realizado de uma categoria no mes, do jeito que a tela mostra.

    Subcategoria sem orcamento proprio soma no orcamento do pai: orcar
    "Alimentacao" precisa cobrir o que foi gasto em "Alimentacao > Delivery",
    senao o planejado no pai nunca bate com o extrato. Assim que a subcategoria
    ganha orcamento proprio (no conjunto que vale no mes), ela para de somar no pai.

    Esta e a unica definicao de "realizado" — a tela e o rollover chamam as duas
    a mesma funcao. Calcular a sobra do mes anterior por outra regra fazia o
    rollover transportar dinheiro ja gasto.
    """
    category = fetch_category(conn, current_user_id, category_id)
    if not category:
        return 0.0
    if spend is None:
        spend = budget_spend_by_category(conn, current_user_id, month)
    if budgeted_ids is None:
        budgeted_ids = budgeted_ids_for_month(conn, current_user_id, month)
    if children is None:
        children = budget_children_by_parent(conn, current_user_id)

    total = budget_realized(category, spend)
    for child_id in children.get(category_id, []):
        if child_id in budgeted_ids:
            continue
        total += budget_realized(fetch_category(conn, current_user_id, child_id), spend)
    return total


def budget_carryover(conn, current_user_id, budget_row, month):
    """Sobra do mes anterior a `month`, quando rollover esta ligado.

    Um nivel so: le a categoria no mes anterior (o orcamento que valia nele,
    proprio ou herdado) e devolve o que sobrou dela (nunca negativo — estourar um
    mes nao vira divida do seguinte). O planejado do mes anterior e o Gastar
    daquele mes x o % da categoria naquele mes; sem renda la, nao ha sobra.
    Encadear a cadeia inteira exigiria recalcular todo o historico a cada
    lancamento retroativo, o que nao paga o que entrega.
    """
    if not budget_row["rollover"]:
        return 0.0
    previous_month = shift_month(month, -1)
    previous = effective_budget_row(conn, current_user_id, budget_row["category_id"], previous_month)
    if not previous:
        return 0.0
    percent = stored_percent(previous["planned_percent"])
    base = planned_spend(conn, current_user_id, previous_month)
    if percent is None or base is None:
        return 0.0
    spent = budget_month_spent(conn, current_user_id, budget_row["category_id"], previous_month)
    leftover = percent_of(base, percent) - spent
    return rounded_money(max(leftover, 0.0))


def budget_status(spent, available):
    remaining = rounded_money(available - spent)
    percent = rounded_money((spent / available) * 100) if available > 0 else 0.0
    if remaining < 0:
        return "OVER", percent
    if available > 0 and percent >= BUDGET_WARNING_PERCENT:
        return "WARNING", percent
    return "OK", percent


def serialize_budget(row, *, month, spend_amount, spent=0.0, carryover=0.0):
    """A categoria em `month`: o %, os reais sobre o Gastar do mes e o realizado.

    Sem base (linha antiga sem %, ou o plano do mes sem renda) nada e
    calculado: `needs_income`, status NEEDS_INCOME, e so o realizado.
    """
    percent = stored_percent(row["planned_percent"])
    spent = rounded_money(spent)
    item = row_to_dict(row)
    item.update(
        {
            # O mes que a tela pediu; `source_month` e o da linha (heranca).
            "month": month,
            "source_month": row["month"],
            "inherited": row["month"] != month,
            "planned_percent": percent_json(percent),
            "rollover": bool(row["rollover"]),
            "spent": spent,
            # O valor antigo, em reais, de uma linha que ainda nao virou %.
            "legacy_amount": rounded_money(row["planned_amount"]) if percent is None else None,
        }
    )
    if percent is None or spend_amount is None:
        item.update(
            {
                "needs_income": True,
                "planned_amount": None,
                "carryover": 0.0,
                "available": None,
                "remaining": None,
                "percent": None,
                "status": "NEEDS_INCOME",
            }
        )
        return item

    planned = percent_of(spend_amount, percent)
    available = rounded_money(planned + carryover)
    status, used_percent = budget_status(spent, available)
    item.update(
        {
            "needs_income": False,
            "planned_amount": planned,
            "carryover": rounded_money(carryover),
            "available": available,
            "remaining": rounded_money(available - spent),
            "percent": used_percent,
            "status": status,
        }
    )
    return item


def build_budget_month(conn, current_user_id, month):
    """As categorias que valem em `month`, com os reais e o realizado de cada uma."""
    source, rows = effective_budget_rows(conn, current_user_id, month)
    spend_amount = planned_spend(conn, current_user_id, month)
    spend = budget_spend_by_category(conn, current_user_id, month)
    budgeted_ids = {row["category_id"] for row in rows}
    children_by_parent = budget_children_by_parent(conn, current_user_id)

    items = []
    for row in rows:
        spent = budget_month_spent(
            conn,
            current_user_id,
            row["category_id"],
            month,
            spend=spend,
            budgeted_ids=budgeted_ids,
            children=children_by_parent,
        )
        items.append(
            serialize_budget(
                row,
                month=month,
                spend_amount=spend_amount,
                spent=spent,
                carryover=budget_carryover(conn, current_user_id, row, month),
            )
        )

    computed = [item for item in items if not item["needs_income"]]
    planned_total = rounded_money(sum(item["planned_amount"] for item in computed))
    carryover_total = rounded_money(sum(item["carryover"] for item in computed))
    spent_total = rounded_money(sum(item["spent"] for item in items))
    available_total = rounded_money(planned_total + carryover_total)
    assigned = assigned_percent(rows)
    return {
        "month": month,
        "source_month": source,
        "inherited": bool(source) and source != month,
        "needs_income": any(item["needs_income"] for item in items),
        "items": items,
        "totals": {
            # Gastar do plano em reais (None sem renda) e quanto dele as
            # categorias levam; "Sem categoria" e o resto.
            "spend_amount": spend_amount,
            "assigned_percent": float(assigned),
            "unassigned_percent": float(HUNDRED - assigned),
            "unassigned_amount": (
                rounded_money(spend_amount - planned_total) if spend_amount is not None else None
            ),
            "planned": planned_total,
            "carryover": carryover_total,
            "available": available_total,
            "spent": spent_total,
            # O que sobra *nas categorias* (disponivel - realizado delas). O
            # "Saldo do plano" e outro numero: Gastar - gasto do mes inteiro
            # (services/monthly_plan.py, `plan_balance`).
            "remaining": rounded_money(available_total - spent_total),
            "over_count": sum(1 for item in items if item["status"] == "OVER"),
        },
    }
