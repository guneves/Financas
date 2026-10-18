"""Orcamento mensal por categoria (`/api/budgets`).

Um orcamento e um plano, nao um registro: a linha e chaveada por
(categoria, mes), apagar nao exige confirmacao, e o saldo que acumula
(`rollover`) e calculado na leitura, nunca gravado.
"""

import sqlite3
from datetime import datetime

from flask import Blueprint, jsonify, request

from auth import token_required
from dates import month_key
from db import get_db, new_id, row_to_dict, utc_timestamp
from money import rounded_money
from services.accounts import fetch_category
from services.invoices import signed_amount_sql
from services.sharing import own_amount_sql
from source_types import INVOICE_PAYMENT_SOURCE_TYPES
from validators import (
    ValidationError,
    normalize_month,
    optional_string,
    parse_json_body,
    parse_number,
    require_month,
    safe_float,
    shift_month,
    validation_error,
)

bp = Blueprint("budgets", __name__)


def budget_spend_by_category(conn, current_user_id, month):
    """Realizado do mes por categoria: {category_id: {"EXPENSE": x, "INCOME": y}}.

    Lancamentos com category_id preenchido contam direto; os que so tem o texto
    (categoria livre, ou lancamento anterior a migration 008) sao resolvidos
    pelo nome. TRANSFER fica de fora: mover dinheiro entre contas proprias nao e
    gasto nem receita.

    Cartao (decisao 1, 2026-09-23): a compra conta inteira, na categoria dela,
    no mes em que foi feita — todas as parcelas, a mesma regra de "Despesas por
    categoria" no Inicio. Por isso o pagamento da fatura nao conta: ele e a soma
    de compras ja contadas. Pagamento de fatura e o lancamento com source_type
    de fatura, ou, nos anteriores ao pagamento pelo servidor, a categoria
    "Pagamento Fatura...".

    De quem e (032): conta so a parte do dono — a pizza dividida pesa no
    orcamento so pela fatia dele (services/sharing.py).
    """
    name_to_id = {}
    for row in conn.execute(
        """
        SELECT id, name, parent_id FROM categories
        WHERE user_id = ?
        ORDER BY parent_id IS NOT NULL, created_at, id
        """,
        (current_user_id,),
    ).fetchall():
        name_to_id.setdefault(row["name"], row["id"])

    invoice_types = sorted(INVOICE_PAYMENT_SOURCE_TYPES)
    invoice_placeholders = ", ".join("?" for _ in invoice_types)
    totals = {}
    rows = conn.execute(
        f"""
        SELECT type, category_id, category, SUM({own_amount_sql()}) AS total
        FROM transactions
        WHERE user_id = ?
          AND type <> 'TRANSFER'
          AND substr(date, 1, 7) = ?
          AND COALESCE(source_type, '') NOT IN ({invoice_placeholders})
          AND COALESCE(category, '') NOT LIKE 'Pagamento Fatura%'
        GROUP BY type, category_id, category
        """,
        (current_user_id, month, *invoice_types),
    ).fetchall()
    card_rows = conn.execute(
        f"""
        SELECT 'EXPENSE' AS type, NULL AS category_id, category,
               SUM({signed_amount_sql()} * {own_amount_sql()}) AS total
        FROM cc_expenses
        WHERE user_id = ?
          AND substr(purchase_date, 1, 7) = ?
        GROUP BY category
        """,
        (current_user_id, month),
    ).fetchall()
    for row in [*rows, *card_rows]:
        category_id = row["category_id"] or name_to_id.get(row["category"])
        if not category_id:
            continue
        bucket = totals.setdefault(category_id, {"EXPENSE": 0.0, "INCOME": 0.0})
        bucket[row["type"]] = bucket.get(row["type"], 0.0) + safe_float(row["total"])
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


def budget_rows_for_month(conn, current_user_id, month):
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


def budget_children_by_parent(conn, current_user_id):
    children = {}
    for row in conn.execute(
        "SELECT id, parent_id FROM categories WHERE user_id = ? AND parent_id IS NOT NULL",
        (current_user_id,),
    ).fetchall():
        children.setdefault(row["parent_id"], []).append(row["id"])
    return children


def budget_month_spent(conn, current_user_id, category_id, month, *, spend=None, budgeted_ids=None, children=None):
    """Realizado de uma categoria no mes, do jeito que a tela mostra.

    Subcategoria sem orcamento proprio soma no orcamento do pai: orcar
    "Alimentacao" precisa cobrir o que foi gasto em "Alimentacao > Delivery",
    senao o planejado no pai nunca bate com o extrato. Assim que a subcategoria
    ganha orcamento proprio, ela para de somar no pai.

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
        budgeted_ids = {
            row["category_id"]
            for row in conn.execute(
                "SELECT category_id FROM budgets WHERE user_id = ? AND month = ?",
                (current_user_id, month),
            ).fetchall()
        }
    if children is None:
        children = budget_children_by_parent(conn, current_user_id)

    total = budget_realized(category, spend)
    for child_id in children.get(category_id, []):
        if child_id in budgeted_ids:
            continue
        total += budget_realized(fetch_category(conn, current_user_id, child_id), spend)
    return total


def budget_carryover(conn, current_user_id, budget_row):
    """Sobra do mes anterior, quando rollover esta ligado.

    Um nivel so: le o orcamento do mes anterior da mesma categoria e devolve o
    que sobrou dele (nunca negativo — estourar um mes nao vira divida do
    seguinte). Encadear a cadeia inteira exigiria recalcular todo o historico a
    cada lancamento retroativo, o que nao paga o que entrega.
    """
    if not budget_row["rollover"]:
        return 0.0
    previous_month = shift_month(budget_row["month"], -1)
    previous = conn.execute(
        "SELECT * FROM budgets WHERE user_id = ? AND category_id = ? AND month = ?",
        (current_user_id, budget_row["category_id"], previous_month),
    ).fetchone()
    if not previous:
        return 0.0
    spent = budget_month_spent(
        conn, current_user_id, budget_row["category_id"], previous_month
    )
    leftover = safe_float(previous["planned_amount"]) - spent
    return rounded_money(max(leftover, 0.0))


def serialize_budget(row, *, spent=0.0, carryover=0.0):
    planned = rounded_money(row["planned_amount"])
    available = rounded_money(planned + carryover)
    spent = rounded_money(spent)
    remaining = rounded_money(available - spent)
    percent = rounded_money((spent / available) * 100) if available > 0 else 0.0
    if remaining < 0:
        status = "OVER"
    elif available > 0 and percent >= 80:
        status = "WARNING"
    else:
        status = "OK"
    item = row_to_dict(row)
    item.update(
        {
            "planned_amount": planned,
            "rollover": bool(row["rollover"]),
            "carryover": rounded_money(carryover),
            "available": available,
            "spent": spent,
            "remaining": remaining,
            "percent": percent,
            "status": status,
        }
    )
    return item


def build_budget_month(conn, current_user_id, month):
    rows = budget_rows_for_month(conn, current_user_id, month)
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
                spent=spent,
                carryover=budget_carryover(conn, current_user_id, row),
            )
        )

    planned_total = rounded_money(sum(item["planned_amount"] for item in items))
    carryover_total = rounded_money(sum(item["carryover"] for item in items))
    spent_total = rounded_money(sum(item["spent"] for item in items))
    available_total = rounded_money(planned_total + carryover_total)
    return {
        "month": month,
        "items": items,
        "totals": {
            "planned": planned_total,
            "carryover": carryover_total,
            "available": available_total,
            "spent": spent_total,
            "remaining": rounded_money(available_total - spent_total),
            "over_count": sum(1 for item in items if item["status"] == "OVER"),
        },
    }


@bp.route("/api/budgets", methods=["GET", "POST"])
@token_required
def budgets(current_user_id):
    if request.method == "GET":
        raw_month = request.args.get("month") or month_key(datetime.now())
        try:
            month = normalize_month(raw_month)
        except ValidationError as exc:
            return validation_error(str(exc))
        with get_db() as conn:
            return jsonify(build_budget_month(conn, current_user_id, month)), 200

    payload = parse_json_body()
    with get_db() as conn:
        try:
            month = require_month(payload, "month", "Mes do orcamento")
            planned_amount = rounded_money(
                parse_number(payload, "planned_amount", "Valor planejado", minimum=0)
            )
            category_id = str(payload.get("category_id") or "").strip()
            if not category_id:
                raise ValidationError("Informe a categoria do orcamento.")
            category = fetch_category(conn, current_user_id, category_id)
            if not category:
                raise ValidationError("Categoria nao encontrada.")
            if category["archived_at"]:
                raise ValidationError("Categoria esta arquivada.")
            rollover = 1 if payload.get("rollover") in (True, 1, "1", "true", "True") else 0
            note = optional_string(payload, "note", max_length=255) or None
        except ValidationError as exc:
            return validation_error(str(exc))

        budget_id = new_id()
        try:
            conn.execute(
                """
                INSERT INTO budgets (id, user_id, category_id, month, planned_amount, rollover, note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (budget_id, current_user_id, category["id"], month, planned_amount, rollover, note),
            )
        except sqlite3.IntegrityError:
            return validation_error("Ja existe um orcamento para esta categoria neste mes.", 409)
        row = fetch_budget(conn, current_user_id, budget_id)
        item = serialize_budget(
            row,
            spent=budget_month_spent(conn, current_user_id, category["id"], month),
            carryover=budget_carryover(conn, current_user_id, row),
        )
        item["category_name"] = category["name"]
        item["category_kind"] = category["kind"]
    return jsonify(item), 201


@bp.route("/api/budgets/<budget_id>", methods=["PATCH", "DELETE"])
@token_required
def budget_detail(current_user_id, budget_id):
    with get_db() as conn:
        row = fetch_budget(conn, current_user_id, budget_id)
        if not row:
            return jsonify({"error": "Orcamento nao encontrado."}), 404

        if request.method == "DELETE":
            # Orcamento e plano, nao registro financeiro: apagar nao desfaz
            # nenhum lancamento, por isso aqui o DELETE e real e sem guarda.
            conn.execute(
                "DELETE FROM budgets WHERE id = ? AND user_id = ?",
                (budget_id, current_user_id),
            )
            return jsonify({"deleted": True}), 200

        payload = parse_json_body()
        updates = {}
        try:
            if "planned_amount" in payload:
                updates["planned_amount"] = rounded_money(
                    parse_number(payload, "planned_amount", "Valor planejado", minimum=0)
                )
            if "rollover" in payload:
                updates["rollover"] = (
                    1 if payload.get("rollover") in (True, 1, "1", "true", "True") else 0
                )
            if "note" in payload:
                updates["note"] = optional_string(payload, "note", max_length=255) or None
            if "month" in payload:
                updates["month"] = require_month(payload, "month", "Mes do orcamento")
            if "category_id" in payload:
                category = fetch_category(conn, current_user_id, str(payload.get("category_id") or ""))
                if not category:
                    raise ValidationError("Categoria nao encontrada.")
                if category["archived_at"]:
                    raise ValidationError("Categoria esta arquivada.")
                updates["category_id"] = category["id"]
        except ValidationError as exc:
            return validation_error(str(exc))

        if not updates:
            return validation_error("Informe ao menos um campo para atualizar.")

        updates["updated_at"] = utc_timestamp()
        assignments = ", ".join(f"{column} = ?" for column in updates)
        try:
            conn.execute(
                f"UPDATE budgets SET {assignments} WHERE id = ? AND user_id = ?",
                (*updates.values(), budget_id, current_user_id),
            )
        except sqlite3.IntegrityError:
            return validation_error("Ja existe um orcamento para esta categoria neste mes.", 409)
        updated = fetch_budget(conn, current_user_id, budget_id)
        category = fetch_category(conn, current_user_id, updated["category_id"])
        item = serialize_budget(
            updated,
            spent=budget_month_spent(
                conn, current_user_id, updated["category_id"], updated["month"]
            ),
            carryover=budget_carryover(conn, current_user_id, updated),
        )
        item["category_name"] = category["name"] if category else None
    return jsonify(item), 200


@bp.route("/api/budgets/copy", methods=["POST"])
@token_required
def copy_budgets(current_user_id):
    """Copia o planejado de um mes para outro — o atalho de "mesmo de sempre"."""
    payload = parse_json_body()
    with get_db() as conn:
        try:
            to_month = require_month(payload, "to_month", "Mes de destino")
            raw_from = payload.get("from_month")
            from_month = (
                normalize_month(raw_from, "Mes de origem")
                if raw_from not in (None, "")
                else shift_month(to_month, -1)
            )
        except ValidationError as exc:
            return validation_error(str(exc))
        if from_month == to_month:
            return validation_error("Os meses de origem e destino sao iguais.")

        overwrite = payload.get("overwrite") in (True, 1, "1", "true", "True")
        source_rows = conn.execute(
            "SELECT * FROM budgets WHERE user_id = ? AND month = ?",
            (current_user_id, from_month),
        ).fetchall()

        created = 0
        updated = 0
        skipped = 0
        for source in source_rows:
            existing = conn.execute(
                "SELECT id FROM budgets WHERE user_id = ? AND category_id = ? AND month = ?",
                (current_user_id, source["category_id"], to_month),
            ).fetchone()
            if existing:
                if not overwrite:
                    skipped += 1
                    continue
                conn.execute(
                    """
                    UPDATE budgets SET planned_amount = ?, rollover = ?, note = ?, updated_at = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (
                        rounded_money(source["planned_amount"]),
                        source["rollover"],
                        source["note"],
                        utc_timestamp(),
                        existing["id"],
                        current_user_id,
                    ),
                )
                updated += 1
                continue
            conn.execute(
                """
                INSERT INTO budgets (id, user_id, category_id, month, planned_amount, rollover, note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id(),
                    current_user_id,
                    source["category_id"],
                    to_month,
                    rounded_money(source["planned_amount"]),
                    source["rollover"],
                    source["note"],
                ),
            )
            created += 1

        result = build_budget_month(conn, current_user_id, to_month)
    result.update(
        {"from_month": from_month, "created": created, "updated": updated, "skipped": skipped}
    )
    return jsonify(result), 200
