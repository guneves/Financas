"""Proventos: dividendos, JCP e amortizacoes recebidos (ou a receber).

O imposto padrao do JCP e 15% na fonte (`DEFAULT_JCP_TAX_RATE`); dividendo e
amortizacao nao tem. `investment_position_at_date()` da a quantidade elegivel
na data com, que vezes o valor por cota da o bruto. O status (PAID /
SCHEDULED) vem da data de pagamento e e calculado na leitura.
"""

from datetime import datetime, timedelta
import sqlite3

from flask import Blueprint, jsonify, request

from auth import token_required
from dates import parse_iso_date
from db import encode_metadata, get_db, new_id, parse_metadata_value, serialize_metadata_row
from export_csv import ColumnError
from money import rounded_money
from responses import export_response, read_export_options
from services.investments import ensure_asset_owner, investment_metadata_dict
from validators import (
    ValidationError,
    optional_date,
    optional_string,
    parse_json_body,
    parse_optional_number,
    require_choice,
    require_date,
    require_string,
    safe_float,
    validation_error,
)

bp = Blueprint("proceeds", __name__)


ALLOWED_PROCEEDS_TYPES = {"DIVIDEND", "JCP", "AMORTIZATION"}
DEFAULT_JCP_TAX_RATE = 0.15


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


def default_tax_for_proceed(proceeds_type, gross_amount):
    if proceeds_type == "JCP":
        return gross_amount * DEFAULT_JCP_TAX_RATE
    return 0


def normalize_proceed_payload(conn, current_user_id, payload, existing=None):
    existing = existing or {}
    merged = {
        "asset_id": existing.get("asset_id"),
        "proceeds_type": existing.get("proceeds_type"),
        "declared_date": existing.get("declared_date"),
        "record_date": existing.get("record_date"),
        "ex_date": existing.get("ex_date"),
        "payment_date": existing.get("payment_date"),
        "amount_per_unit": existing.get("amount_per_unit"),
        "eligible_quantity": existing.get("eligible_quantity"),
        "gross_amount": existing.get("gross_amount"),
        "tax_amount": existing.get("tax_amount"),
        "source": existing.get("source") or "manual",
        "notes": existing.get("notes") or "",
        "metadata": parse_metadata_value(existing.get("metadata")),
    }
    for key in merged:
        if key in payload:
            merged[key] = payload.get(key)

    asset_id = require_string(merged, "asset_id", "Ativo")
    ensure_asset_owner(conn, current_user_id, asset_id)
    proceeds_type = require_choice(merged, "proceeds_type", "Tipo de provento", ALLOWED_PROCEEDS_TYPES)
    declared_date = optional_date(merged, "declared_date", "Data de declaracao")
    record_date = require_date(merged, "record_date", "Data com")
    ex_date = optional_date(merged, "ex_date", "Data ex")
    payment_date = require_date(merged, "payment_date", "Data de pagamento")

    amount_per_unit = parse_optional_number(
        merged,
        "amount_per_unit",
        "Valor por cota",
        minimum=0,
    )
    eligible_quantity = parse_optional_number(
        merged,
        "eligible_quantity",
        "Quantidade elegivel",
        minimum=0,
    )
    gross_amount = parse_optional_number(
        merged,
        "gross_amount",
        "Valor bruto",
        minimum=0,
    )

    position = investment_position_at_date(conn, current_user_id, asset_id, record_date)
    if eligible_quantity is None:
        eligible_quantity = position["quantity"]

    if gross_amount is None:
        if amount_per_unit is None:
            raise ValidationError("Informe valor por cota ou valor bruto.")
        if eligible_quantity <= 0:
            # Sem posicao na data com: titulo comprado depois dela ou ja resgatado.
            record_label = datetime.strptime(record_date, "%Y-%m-%d").strftime("%d/%m/%Y")
            raise ValidationError(
                f"Nenhuma posicao neste ativo na data com ({record_label}). "
                "Confira a data com, informe o valor bruto ou a quantidade elegivel."
            )
        gross_amount = amount_per_unit * eligible_quantity

    if amount_per_unit is None and eligible_quantity > 0:
        amount_per_unit = gross_amount / eligible_quantity

    tax_was_provided = "tax_amount" in payload and payload.get("tax_amount") not in (None, "")
    tax_amount = parse_optional_number(
        merged,
        "tax_amount",
        "Imposto",
        minimum=0,
    )
    should_recalculate_tax = (
        not tax_was_provided
        and (
            existing.get("id") is None
            or any(key in payload for key in ("proceeds_type", "amount_per_unit", "eligible_quantity", "gross_amount"))
        )
    )
    if tax_amount is None or should_recalculate_tax:
        tax_amount = default_tax_for_proceed(proceeds_type, gross_amount)

    gross_amount = rounded_money(gross_amount)
    tax_amount = rounded_money(tax_amount)
    if tax_amount - gross_amount > 0.000001:
        raise ValidationError("Imposto nao pode ser maior que o valor bruto.")

    metadata = merged.get("metadata")
    if metadata not in (None, "") and not isinstance(metadata, (dict, str)):
        raise ValidationError("Metadata deve ser um objeto valido.")

    return {
        "asset_id": asset_id,
        "proceeds_type": proceeds_type,
        "declared_date": declared_date,
        "record_date": record_date,
        "ex_date": ex_date,
        "payment_date": payment_date,
        "amount_per_unit": round(safe_float(amount_per_unit), 8) if amount_per_unit is not None else None,
        "eligible_quantity": round(safe_float(eligible_quantity), 6),
        "gross_amount": gross_amount,
        "tax_amount": tax_amount,
        "net_amount": rounded_money(gross_amount - tax_amount),
        "source": optional_string(merged, "source", 100) or "manual",
        "notes": optional_string(merged, "notes", 1000),
        "metadata": investment_metadata_dict(metadata),
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
        JOIN assets asset ON asset.id = proceeds.asset_id
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


def build_investment_proceeds_summary(items):
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
        "next_events": [],
    }

    for item in items:
        gross = safe_float(item.get("gross_amount"))
        tax = safe_float(item.get("tax_amount"))
        net = safe_float(item.get("net_amount"))
        cost_basis = safe_float(item.get("cost_basis_at_record_date"))
        proceeds_type = item.get("proceeds_type") or "OTHER"
        month_key = str(item.get("payment_date") or "")[:7]

        summary["gross_amount"] += gross
        summary["tax_amount"] += tax
        summary["net_amount"] += net
        summary["cost_basis"] += cost_basis
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

    for key in ("gross_amount", "tax_amount", "net_amount", "cost_basis", "paid_net_amount", "scheduled_net_amount"):
        summary[key] = rounded_money(summary[key])
    summary["yield_on_cost_percent"] = round(
        (summary["net_amount"] / summary["cost_basis"]) * 100,
        4,
    ) if summary["cost_basis"] > 0 else 0

    for bucket in summary["by_type"].values():
        for key in ("gross_amount", "tax_amount", "net_amount"):
            bucket[key] = rounded_money(bucket[key])
    for bucket in summary["by_month"].values():
        for key in ("gross_amount", "tax_amount", "net_amount"):
            bucket[key] = rounded_money(bucket[key])

    summary["by_type"] = sorted(summary["by_type"].values(), key=lambda item: item["proceeds_type"])
    summary["by_month"] = sorted(summary["by_month"].values(), key=lambda item: item["month"])
    summary["next_events"] = sorted(
        summary["next_events"],
        key=lambda item: (item.get("payment_date") or "", item.get("asset", {}).get("ticker") or ""),
    )[:8]
    return summary


def parse_investment_proceeds_filters(args):
    filters = {}
    if args.get("asset_id"):
        filters["asset_id"] = str(args.get("asset_id")).strip()
    if args.get("proceeds_type"):
        filters["proceeds_type"] = require_choice(
            {"proceeds_type": args.get("proceeds_type")},
            "proceeds_type",
            "Tipo de provento",
            ALLOWED_PROCEEDS_TYPES,
        )
    if args.get("date_from"):
        filters["date_from"] = require_date({"date_from": args.get("date_from")}, "date_from", "Data inicial")
    if args.get("date_to"):
        filters["date_to"] = require_date({"date_to": args.get("date_to")}, "date_to", "Data final")
    if args.get("status"):
        status = str(args.get("status")).strip().upper()
        if status not in {"PAID", "SCHEDULED", "ALL"}:
            raise ValidationError("Status invalido.")
        if status != "ALL":
            filters["status"] = status
    filters["ascending"] = args.get("ascending") == "true"
    return filters


@bp.route("/api/investment-proceeds", methods=["GET", "POST"])
@token_required
def investment_proceeds(current_user_id):
    if request.method == "GET":
        try:
            filters = parse_investment_proceeds_filters(request.args)
        except ValidationError as exc:
            return validation_error(str(exc))

        with get_db() as conn:
            rows = fetch_investment_proceeds(conn, current_user_id, filters)
            items = [
                serialize_investment_proceed(row, conn, current_user_id)
                for row in rows
            ]
        return jsonify(items), 200

    payload = parse_json_body()
    if not isinstance(payload, dict):
        return validation_error("Provento deve ser um objeto valido.")

    try:
        with get_db() as conn:
            proceed = normalize_proceed_payload(conn, current_user_id, payload)
            proceed_id = new_id()
            conn.execute(
                """
                INSERT INTO investment_proceeds
                (
                    id, user_id, asset_id, proceeds_type, declared_date,
                    record_date, ex_date, payment_date, amount_per_unit,
                    eligible_quantity, gross_amount, tax_amount, net_amount,
                    source, notes, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proceed_id,
                    current_user_id,
                    proceed["asset_id"],
                    proceed["proceeds_type"],
                    proceed["declared_date"],
                    proceed["record_date"],
                    proceed["ex_date"],
                    proceed["payment_date"],
                    proceed["amount_per_unit"],
                    proceed["eligible_quantity"],
                    proceed["gross_amount"],
                    proceed["tax_amount"],
                    proceed["net_amount"],
                    proceed["source"],
                    proceed["notes"],
                    encode_metadata(proceed["metadata"]),
                ),
            )
            row = fetch_investment_proceed_by_id(conn, current_user_id, proceed_id)
            item = serialize_investment_proceed(row, conn, current_user_id)
    except ValidationError as exc:
        return validation_error(str(exc))
    except sqlite3.IntegrityError:
        return jsonify({"error": "Nao foi possivel registrar o provento."}), 400

    return jsonify(item), 201


@bp.route("/api/investment-proceeds/export", methods=["GET"])
@token_required
def export_investment_proceeds(current_user_id):
    """Proventos em CSV ou .xlsx, com os mesmos filtros de GET /api/investment-proceeds."""
    try:
        fmt, columns = read_export_options(request.args, "proceeds")
        filters = parse_investment_proceeds_filters(request.args)
    except (ColumnError, ValidationError) as exc:
        return validation_error(str(exc))

    with get_db() as conn:
        rows = fetch_investment_proceeds(conn, current_user_id, filters)
        items = [serialize_investment_proceed(row, conn, current_user_id) for row in rows]
    return export_response(fmt, columns, items, basename="proventos", sheet_name="Proventos")


@bp.route("/api/investment-proceeds/summary", methods=["GET"])
@token_required
def investment_proceeds_summary(current_user_id):
    try:
        filters = parse_investment_proceeds_filters(request.args)
    except ValidationError as exc:
        return validation_error(str(exc))

    with get_db() as conn:
        rows = fetch_investment_proceeds(conn, current_user_id, filters)
        items = [
            serialize_investment_proceed(row, conn, current_user_id)
            for row in rows
        ]
    return jsonify(build_investment_proceeds_summary(items)), 200


@bp.route("/api/investment-proceeds/calendar", methods=["GET"])
@token_required
def investment_proceeds_calendar(current_user_id):
    try:
        filters = parse_investment_proceeds_filters(request.args)
    except ValidationError as exc:
        return validation_error(str(exc))

    today = datetime.now().strftime("%Y-%m-%d")
    if not filters.get("date_from"):
        filters["date_from"] = today
    if not filters.get("date_to"):
        filters["date_to"] = (datetime.now() + timedelta(days=180)).strftime("%Y-%m-%d")
    filters["ascending"] = True

    with get_db() as conn:
        rows = fetch_investment_proceeds(conn, current_user_id, filters)
        items = [
            serialize_investment_proceed(row, conn, current_user_id)
            for row in rows
        ]
    return jsonify(items), 200


@bp.route("/api/investment-proceeds/<proceed_id>", methods=["PATCH", "DELETE"])
@token_required
def investment_proceed_detail(current_user_id, proceed_id):
    with get_db() as conn:
        existing_row = fetch_investment_proceed_by_id(conn, current_user_id, proceed_id)
        if not existing_row:
            return jsonify({"error": "Provento nao encontrado."}), 404

        if request.method == "DELETE":
            cursor = conn.execute(
                "DELETE FROM investment_proceeds WHERE id = ? AND user_id = ?",
                (proceed_id, current_user_id),
            )
            return jsonify({"deleted": cursor.rowcount}), 200

        payload = parse_json_body()
        if not isinstance(payload, dict):
            return validation_error("Provento deve ser um objeto valido.")

        try:
            existing = serialize_metadata_row(existing_row)
            proceed = normalize_proceed_payload(conn, current_user_id, payload, existing)
            conn.execute(
                """
                UPDATE investment_proceeds
                SET asset_id = ?,
                    proceeds_type = ?,
                    declared_date = ?,
                    record_date = ?,
                    ex_date = ?,
                    payment_date = ?,
                    amount_per_unit = ?,
                    eligible_quantity = ?,
                    gross_amount = ?,
                    tax_amount = ?,
                    net_amount = ?,
                    source = ?,
                    notes = ?,
                    metadata = ?,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ? AND user_id = ?
                """,
                (
                    proceed["asset_id"],
                    proceed["proceeds_type"],
                    proceed["declared_date"],
                    proceed["record_date"],
                    proceed["ex_date"],
                    proceed["payment_date"],
                    proceed["amount_per_unit"],
                    proceed["eligible_quantity"],
                    proceed["gross_amount"],
                    proceed["tax_amount"],
                    proceed["net_amount"],
                    proceed["source"],
                    proceed["notes"],
                    encode_metadata(proceed["metadata"]),
                    proceed_id,
                    current_user_id,
                ),
            )
            row = fetch_investment_proceed_by_id(conn, current_user_id, proceed_id)
            item = serialize_investment_proceed(row, conn, current_user_id)
        except ValidationError as exc:
            return validation_error(str(exc))
        except sqlite3.IntegrityError:
            return jsonify({"error": "Nao foi possivel atualizar o provento."}), 400

    return jsonify(item), 200
