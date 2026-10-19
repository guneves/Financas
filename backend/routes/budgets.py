"""Orcamento mensal por categoria (`/api/budgets`), regras em services/budgets.py.

Um orcamento e um plano, nao um registro: a linha e chaveada por
(categoria, mes), apagar nao exige confirmacao, e o saldo que acumula
(`rollover`) e calculado na leitura, nunca gravado.

Desde a 038 cada categoria e um % do Gastar do plano do mes (`planned_percent`),
nunca reais. As categorias somam no maximo 100% do Gastar. Um mes sem
categorias proprias herda as do plano anterior; PATCH e DELETE levam
`?month=` (o mes que a tela mostra) e, se a linha for herdada, o mes vira um
plano proprio antes da mudanca (`materialize_month()`).
"""

import sqlite3
from datetime import datetime

from flask import Blueprint, jsonify, request

from auth import token_required
from dates import month_key
from db import get_db, new_id, utc_timestamp
from money import rounded_money
from services.accounts import fetch_category
from services.budgets import (
    assigned_percent,
    budget_carryover,
    budget_children_by_parent,
    budget_month_lines,
    budget_month_spent,
    budget_rows_for_month,
    budgeted_ids_for_month,
    category_source_month,
    effective_budget_rows,
    ensure_categories_fit,
    fetch_budget,
    materialize_month,
    planned_spend,
    serialize_budget,
    stored_percent,
)
from services.monthly_plan import build_budget_view
from validators import (
    ValidationError,
    normalize_month,
    optional_string,
    parse_json_body,
    parse_percent,
    require_month,
    shift_month,
    validation_error,
)

bp = Blueprint("budgets", __name__)

PERCENT_LABEL = "Percentual do Gastar"
NOT_IN_MONTH = "Orcamento nao encontrado neste mes."


def budget_item(conn, current_user_id, row, month):
    """Uma categoria em `month`, como a lista do mes a mostra."""
    item = serialize_budget(
        row,
        month=month,
        spend_amount=planned_spend(conn, current_user_id, month),
        spent=budget_month_spent(conn, current_user_id, row["category_id"], month),
        carryover=budget_carryover(conn, current_user_id, row, month),
    )
    category = fetch_category(conn, current_user_id, row["category_id"])
    item["category_name"] = category["name"] if category else None
    item["category_kind"] = category["kind"] if category else None
    return item


def view_month_for(conn, current_user_id, row):
    """O mes do `?month=` (o que a tela mostra), conferido contra a linha.

    Sem o parametro, o mes da propria linha. Com ele, a linha tem de ser a que
    vale naquele mes — a dele mesmo ou a herdada —, senao None (404).
    """
    raw = request.args.get("month")
    if not raw:
        return row["month"]
    month = normalize_month(raw, "Mes do orcamento")
    if month != row["month"] and category_source_month(conn, current_user_id, month) != row["month"]:
        return None
    return month


def own_row(conn, current_user_id, category_id, month):
    return conn.execute(
        "SELECT * FROM budgets WHERE user_id = ? AND category_id = ? AND month = ?",
        (current_user_id, category_id, month),
    ).fetchone()


def parse_rollover(payload):
    return 1 if payload.get("rollover") in (True, 1, "1", "true", "True") else 0


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
            return jsonify(build_budget_view(conn, current_user_id, month)), 200

    payload = parse_json_body()
    with get_db() as conn:
        try:
            month = require_month(payload, "month", "Mes do orcamento")
            planned_percent = parse_percent(payload, "planned_percent", PERCENT_LABEL)
            category_id = str(payload.get("category_id") or "").strip()
            if not category_id:
                raise ValidationError("Informe a categoria do orcamento.")
            category = fetch_category(conn, current_user_id, category_id)
            if not category:
                raise ValidationError("Categoria nao encontrada.")
            if category["archived_at"]:
                raise ValidationError("Categoria esta arquivada.")
            rollover = parse_rollover(payload)
            note = optional_string(payload, "note", max_length=255) or None
            _, rows = effective_budget_rows(conn, current_user_id, month)
            if any(row["category_id"] == category["id"] for row in rows):
                return validation_error("Ja existe um orcamento para esta categoria neste mes.", 409)
            ensure_categories_fit(assigned_percent(rows) + planned_percent)
        except ValidationError as exc:
            return validation_error(str(exc))

        materialize_month(conn, current_user_id, month)
        budget_id = new_id()
        try:
            # planned_amount e a coluna antiga (NOT NULL): 0, nunca lida numa linha com %.
            conn.execute(
                """
                INSERT INTO budgets (id, user_id, category_id, month, planned_amount,
                                     planned_percent, rollover, note)
                VALUES (?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (budget_id, current_user_id, category["id"], month,
                 format(planned_percent, "f"), rollover, note),
            )
        except sqlite3.IntegrityError:
            return validation_error("Ja existe um orcamento para esta categoria neste mes.", 409)
        item = budget_item(conn, current_user_id, fetch_budget(conn, current_user_id, budget_id), month)
    return jsonify(item), 201


@bp.route("/api/budgets/<budget_id>", methods=["PATCH", "DELETE"])
@token_required
def budget_detail(current_user_id, budget_id):
    try:
        with get_db() as conn:
            row = fetch_budget(conn, current_user_id, budget_id)
            if not row:
                return jsonify({"error": "Orcamento nao encontrado."}), 404
            month = view_month_for(conn, current_user_id, row)
            if month is None:
                return jsonify({"error": NOT_IN_MONTH}), 404

            if request.method == "DELETE":
                # Orcamento e plano, nao registro financeiro: apagar nao desfaz
                # nenhum lancamento, por isso aqui o DELETE e real e sem guarda.
                materialize_month(conn, current_user_id, month)
                target = own_row(conn, current_user_id, row["category_id"], month)
                conn.execute(
                    "DELETE FROM budgets WHERE id = ? AND user_id = ?",
                    (target["id"], current_user_id),
                )
                return jsonify({"deleted": True}), 200

            payload = parse_json_body()
            updates = {}
            if "planned_percent" in payload:
                updates["planned_percent"] = parse_percent(payload, "planned_percent", PERCENT_LABEL)
            if "rollover" in payload:
                updates["rollover"] = parse_rollover(payload)
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
            if not updates:
                raise ValidationError("Informe ao menos um campo para atualizar.")

            if {"planned_percent", "month", "category_id"} & updates.keys():
                # As categorias do mes de destino nao passam de 100% do Gastar. Um
                # mes convertido pela 038 ja acima de 100% aceita uma reducao.
                destination = updates.get("month", month)
                category_id = updates.get("category_id", row["category_id"])
                old = stored_percent(row["planned_percent"]) or 0
                new = updates.get("planned_percent", old)
                _, rows = effective_budget_rows(conn, current_user_id, destination)
                others = assigned_percent(
                    [item for item in rows if item["category_id"] not in (category_id, row["category_id"])]
                )
                same_place = destination == month and category_id == row["category_id"]
                if not same_place or new > old:
                    ensure_categories_fit(others + new)

            materialize_month(conn, current_user_id, month)
            target = own_row(conn, current_user_id, row["category_id"], month)
            stored = dict(updates)
            if "planned_percent" in stored:
                stored["planned_percent"] = format(stored["planned_percent"], "f")
            stored["updated_at"] = utc_timestamp()
            assignments = ", ".join(f"{column} = ?" for column in stored)
            try:
                conn.execute(
                    f"UPDATE budgets SET {assignments} WHERE id = ? AND user_id = ?",
                    (*stored.values(), target["id"], current_user_id),
                )
            except sqlite3.IntegrityError:
                conn.rollback()
                return validation_error("Ja existe um orcamento para esta categoria neste mes.", 409)
            updated = fetch_budget(conn, current_user_id, target["id"])
            item = budget_item(conn, current_user_id, updated, updates.get("month", month))
    except ValidationError as exc:
        return validation_error(str(exc))
    return jsonify(item), 200


@bp.route("/api/budgets/<budget_id>/lines", methods=["GET"])
@token_required
def budget_lines(current_user_id, budget_id):
    """Os lancamentos que justificam o realizado de um orcamento.

    A mesma regra de `budget_month_spent()`: a categoria e as subcategorias
    sem orcamento proprio no mes, receita numa categoria INCOME e despesa nas
    demais. `spent` e a soma de `amount` das linhas, o mesmo valor da tela.
    `?month=` le um mes que herda a linha (o padrao e o mes da linha).
    """
    with get_db() as conn:
        row = fetch_budget(conn, current_user_id, budget_id)
        if not row:
            return jsonify({"error": "Orcamento nao encontrado."}), 404
        try:
            month = view_month_for(conn, current_user_id, row)
        except ValidationError as exc:
            return validation_error(str(exc))
        if month is None:
            return jsonify({"error": NOT_IN_MONTH}), 404
        category = fetch_category(conn, current_user_id, row["category_id"])
        budgeted_ids = budgeted_ids_for_month(conn, current_user_id, month)
        children = budget_children_by_parent(conn, current_user_id)
        included = {row["category_id"]} | {
            child_id
            for child_id in children.get(row["category_id"], [])
            if child_id not in budgeted_ids
        }
        wanted_type = "INCOME" if category and category["kind"] == "INCOME" else "EXPENSE"
        lines = []
        for line in budget_month_lines(conn, current_user_id, month):
            if line["category_id"] not in included or line["type"] != wanted_type:
                continue
            line["amount"] = rounded_money(line["amount"])
            line["total_amount"] = rounded_money(line["total_amount"])
            line["subcategory"] = line["category_id"] != row["category_id"]
            lines.append(line)
        spent = budget_month_spent(
            conn, current_user_id, row["category_id"], month,
            budgeted_ids=budgeted_ids, children=children,
        )
    return jsonify(
        {
            "budget_id": budget_id,
            "month": month,
            "category_id": row["category_id"],
            "spent": rounded_money(spent),
            "lines": lines,
        }
    ), 200


@bp.route("/api/budgets/copy", methods=["POST"])
@token_required
def copy_budgets(current_user_id):
    """Copia as categorias (os %) de um mes para outro — o "mesmo de sempre".

    Le as categorias que valem no mes de origem (herdadas inclusive). O destino
    vira um plano proprio antes (o que ele herdava continua la); o que ja existe
    nele fica, a menos que `overwrite`. O resultado nao passa de 100% do Gastar.
    """
    payload = parse_json_body()
    try:
        with get_db() as conn:
            to_month = require_month(payload, "to_month", "Mes de destino")
            raw_from = payload.get("from_month")
            from_month = (
                normalize_month(raw_from, "Mes de origem")
                if raw_from not in (None, "")
                else shift_month(to_month, -1)
            )
            if from_month == to_month:
                raise ValidationError("Os meses de origem e destino sao iguais.")

            overwrite = payload.get("overwrite") in (True, 1, "1", "true", "True")
            _, source_rows = effective_budget_rows(conn, current_user_id, from_month)
            materialize_month(conn, current_user_id, to_month)

            created = 0
            updated = 0
            skipped = 0
            for source in source_rows:
                existing = own_row(conn, current_user_id, source["category_id"], to_month)
                if existing:
                    if not overwrite:
                        skipped += 1
                        continue
                    conn.execute(
                        """
                        UPDATE budgets
                        SET planned_percent = ?, planned_amount = ?, rollover = ?, note = ?, updated_at = ?
                        WHERE id = ? AND user_id = ?
                        """,
                        (
                            source["planned_percent"],
                            source["planned_amount"],
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
                    INSERT INTO budgets (id, user_id, category_id, month, planned_amount,
                                         planned_percent, rollover, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_id(),
                        current_user_id,
                        source["category_id"],
                        to_month,
                        source["planned_amount"],
                        source["planned_percent"],
                        source["rollover"],
                        source["note"],
                    ),
                )
                created += 1

            ensure_categories_fit(assigned_percent(budget_rows_for_month(conn, current_user_id, to_month)))
            result = build_budget_view(conn, current_user_id, to_month)
    except ValidationError as exc:
        return validation_error(str(exc))
    result.update(
        {"from_month": from_month, "created": created, "updated": updated, "skipped": skipped}
    )
    return jsonify(result), 200
