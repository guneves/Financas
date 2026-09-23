import os
import sqlite3
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta

from flask import Flask, jsonify, request
from flask_cors import CORS

import export_csv
import market_catalog
from config import (
    CORS_ORIGINS,
    PRICE_FETCH_TIMEOUT_SECONDS,
)
from db import (
    encode_metadata,
    get_db,
    init_db,
    new_id,
    parse_metadata_value,
    run_startup_backup,
    serialize_metadata_row,
)
from validators import (
    ValidationError,
    optional_date,
    optional_string,
    parse_json_body,
    parse_number,
    parse_optional_number,
    require_choice,
    require_date,
    require_string,
    safe_float,
    validation_error,
)
from auth import (
    token_required,
)
from money import (
    rounded_money,
)
from dates import (
    parse_iso_date,
    subtract_months,
)
from services.attachments import (
    prune_orphan_attachment_files,
)
from routes.transactions import (
    csv_response,
)
from asset_classes import (
    ALLOWED_ASSET_CLASSES,
    QUOTED_ASSET_CLASSES,
    parse_asset_class_filter,
)
from services.prices import (
    _price_fetch_executor,
    get_monthly_history,
    quote_timestamp,
    record_price_quote,
    ticker_key,
    yf,
)
from services.fixed_income import (
    finish_fixed_income_refresh,
    start_fixed_income_refresh,
    validate_fixed_income_metadata,
)
from services.investments import (
    delete_investment_cash_transaction,
    ensure_asset_owner,
    fetch_investment_rows,
    fetch_investments,
    fetch_position_quantity,
    get_or_create_asset,
    investment_fee_amount,
    investment_gross_amount,
    investment_metadata_dict,
    investment_movement_type,
    investment_transaction_date,
    resolve_catalog_ticker,
    serialize_investment,
    sync_investment_cash_transaction,
    validate_asset_transaction_backing,
    validate_investment_movement,
)
from services.realized_results import (
    realized_results_summary,
    refresh_realized_results,
)
from services.portfolio import (
    build_portfolio_evolution,
    build_portfolio_snapshot,
    refresh_market_prices,
    refresh_materialized_positions,
    replace_materialized_positions,
)

ALLOWED_PROCEEDS_TYPES = {"DIVIDEND", "JCP", "AMORTIZATION"}
DEFAULT_JCP_TAX_RATE = 0.15


app = Flask(__name__)
cors_origins = "*" if CORS_ORIGINS == "*" else [
    origin.strip() for origin in CORS_ORIGINS.split(",") if origin.strip()
] or "*"
CORS(app, resources={r"/api/*": {"origins": cors_origins}})

# Blueprints ja extraidos do app.py (Fase 5). As rotas que ainda moram aqui
# usam @app.route; cada area que sai vira um modulo em routes/.
from routes import (  # noqa: E402
    accounts as account_routes,
    auth as auth_routes,
    budgets as budget_routes,
    cards as card_routes,
    imports as import_routes,
    recurring as recurring_routes,
    system as system_routes,
    transactions as transaction_routes,
    attachments as attachment_routes,
)

for blueprint_module in (
    system_routes,
    auth_routes,
    budget_routes,
    recurring_routes,
    import_routes,
    card_routes,
    account_routes,
    transaction_routes,
    attachment_routes,
):
    app.register_blueprint(blueprint_module.bp)


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


@app.route("/api/investments/portfolio/export", methods=["GET"])
@token_required
def export_portfolio(current_user_id):
    """Carteira atual em CSV, sem forcar atualizacao de cotacao."""
    try:
        portfolio = build_portfolio_snapshot(current_user_id)
    except Exception as exc:
        print(f"Erro ao exportar a carteira: {exc}")
        return jsonify({"error": "Nao foi possivel exportar a carteira."}), 500

    text = export_csv.portfolio_csv(portfolio.get("assets"))
    filename = f"carteira-{datetime.now().strftime('%Y-%m-%d')}.csv"
    return csv_response(text, filename)


@app.route("/api/assets", methods=["GET"])
@token_required
def list_assets(current_user_id):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM assets
            WHERE user_id = ?
            ORDER BY asset_class ASC, ticker ASC
            """,
            (current_user_id,),
        ).fetchall()
    return jsonify([serialize_metadata_row(row) for row in rows]), 200


@app.route("/api/investment-transactions", methods=["GET"])
@token_required
def list_investment_transactions(current_user_id):
    refresh_realized_results(current_user_id)
    with get_db() as conn:
        rows = fetch_investment_rows(
            conn,
            current_user_id,
            order_by="it.transaction_date",
            direction="DESC",
        )
    return jsonify([serialize_investment(row) for row in rows]), 200


@app.route("/api/investment-realized-results", methods=["GET"])
@token_required
def list_investment_realized_results(current_user_id):
    refresh_realized_results(current_user_id)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                rr.*,
                asset.asset_class,
                asset.ticker,
                asset.name,
                it.transaction_date,
                it.metadata AS transaction_metadata
            FROM investment_realized_results rr
            JOIN assets asset ON asset.id = rr.asset_id
            JOIN investment_transactions it ON it.id = rr.source_transaction_id
            WHERE rr.user_id = ?
            ORDER BY rr.operation_date DESC, rr.created_at DESC
            """,
            (current_user_id,),
        ).fetchall()

    items = []
    for row in rows:
        item = serialize_metadata_row(row)
        item["transaction_metadata"] = parse_metadata_value(item.get("transaction_metadata"))
        items.append(item)
    return jsonify(items), 200


@app.route("/api/investment-proceeds", methods=["GET", "POST"])
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


@app.route("/api/investment-proceeds/summary", methods=["GET"])
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


@app.route("/api/investment-proceeds/calendar", methods=["GET"])
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


@app.route("/api/investment-proceeds/<proceed_id>", methods=["PATCH", "DELETE"])
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


@app.route("/api/investment-positions", methods=["GET"])
@token_required
def list_investment_positions(current_user_id):
    refresh_materialized_positions(current_user_id)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                pos.*,
                asset.asset_class,
                asset.ticker,
                asset.name
            FROM investment_positions pos
            JOIN assets asset ON asset.id = pos.asset_id
            WHERE pos.user_id = ?
            ORDER BY asset.asset_class ASC, asset.ticker ASC
            """,
            (current_user_id,),
        ).fetchall()
    return jsonify([serialize_metadata_row(row) for row in rows]), 200


@app.route("/api/market/tickers", methods=["GET"])
@token_required
def market_tickers(current_user_id):
    """Busca no catalogo da B3 (acoes, ETFs, FIIs e BDRs).

    Alimenta o autocomplete da tela de lancamento. E dado de referencia, igual
    para todo mundo, entao nao ha filtro por user_id aqui -- nenhuma linha vem
    do banco.
    """
    results = market_catalog.search(
        query=request.args.get("q", ""),
        asset_class=parse_asset_class_filter(request.args.get("asset_class")),
        kind=request.args.get("kind"),
        limit=request.args.get("limit", 20),
    )
    return jsonify(results), 200


@app.route("/api/market/tickers/<ticker>", methods=["GET"])
@token_required
def market_ticker_detail(current_user_id, ticker):
    entry = market_catalog.lookup(ticker)
    if not entry:
        return jsonify({"error": "Ativo nao encontrado na lista da B3."}), 404
    return jsonify(entry), 200


@app.route("/api/investments", methods=["GET", "POST"])
@token_required
def investments(current_user_id):
    if request.method == "GET":
        refresh_realized_results(current_user_id)
        order = request.args.get("order", "created_at")
        order_by = {
            "created_at": "it.created_at",
            "ticker_or_name": "a.ticker",
            "asset_class": "a.asset_class",
        }.get(order, "it.created_at")
        direction = "ASC" if request.args.get("ascending") == "true" else "DESC"

        with get_db() as conn:
            rows = fetch_investment_rows(
                conn,
                current_user_id,
                order_by=order_by,
                direction=direction,
            )
        return jsonify([serialize_investment(row) for row in rows]), 200

    payload = parse_json_body()
    items = payload if isinstance(payload, list) else [payload]
    if not items:
        return validation_error("Informe ao menos um investimento.")

    inserted = []
    affected_asset_ids = set()
    try:
        with get_db() as conn:
            for item in items:
                if not isinstance(item, dict):
                    raise ValidationError("Cada investimento deve ser um objeto valido.")

                asset_class = require_choice(item, "asset_class", "Tipo de ativo", ALLOWED_ASSET_CLASSES)
                ticker_or_name = require_string(item, "ticker_or_name", "Ativo")
                quantity = parse_number(item, "quantity", "Quantidade")
                if quantity == 0:
                    raise ValidationError("Quantidade deve ser diferente de zero.")
                average_price = parse_number(item, "average_price", "Preco medio", minimum=0)
                current_price = parse_optional_number(item, "current_price", "Preco atual", minimum=0)
                metadata = item.get("metadata")
                if metadata not in (None, "") and not isinstance(metadata, (dict, str)):
                    raise ValidationError("Metadata deve ser um objeto valido.")
                metadata_dict = investment_metadata_dict(metadata)
                validate_fixed_income_metadata(asset_class, quantity, metadata_dict)
                ticker_or_name = resolve_catalog_ticker(
                    conn,
                    current_user_id,
                    asset_class,
                    ticker_or_name,
                    quantity,
                )
                validate_investment_movement(
                    conn,
                    current_user_id,
                    asset_class,
                    ticker_or_name,
                    quantity,
                )

                item_id = new_id()
                asset_id = get_or_create_asset(conn, current_user_id, asset_class, ticker_or_name)
                affected_asset_ids.add(asset_id)
                transaction_date = investment_transaction_date(metadata_dict)
                conn.execute(
                    """
                    INSERT INTO investment_transactions
                    (
                        id, user_id, asset_id, movement_type, quantity,
                        unit_price, gross_amount, fee_amount, transaction_date, metadata
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item_id,
                        current_user_id,
                        asset_id,
                        investment_movement_type(quantity, metadata_dict),
                        quantity,
                        average_price,
                        investment_gross_amount(quantity, average_price),
                        investment_fee_amount(metadata_dict),
                        transaction_date,
                        encode_metadata(metadata),
                    ),
                )
                record_price_quote(
                    conn,
                    current_user_id,
                    asset_id,
                    current_price,
                    asset_class=asset_class,
                    transaction_id=item_id,
                    quoted_at=quote_timestamp(transaction_date),
                    source="manual",
                )
                inserted.append(item_id)

            for asset_id in affected_asset_ids:
                validate_asset_transaction_backing(conn, current_user_id, asset_id)

            rows = []
            for item_id in inserted:
                row = fetch_investment_rows(conn, current_user_id, investment_id=item_id)[0]
                sync_investment_cash_transaction(
                    conn,
                    current_user_id,
                    serialize_investment(row),
                )
                rows.append(row)
    except ValidationError as exc:
        return validation_error(str(exc))
    except sqlite3.IntegrityError:
        return jsonify({"error": "Nao foi possivel criar o investimento."}), 400

    refresh_realized_results(current_user_id)
    refresh_materialized_positions(current_user_id)
    return jsonify([serialize_investment(row) for row in rows]), 201


@app.route("/api/investments/<investment_id>", methods=["PATCH", "DELETE"])
@token_required
def investment_detail(current_user_id, investment_id):
    if request.method == "DELETE":
        with get_db() as conn:
            existing = conn.execute(
                """
                SELECT id FROM investment_transactions
                WHERE id = ? AND user_id = ?
                """,
                (investment_id, current_user_id),
            ).fetchone()
            if not existing:
                return jsonify({"deleted": False}), 404
            existing_rows = fetch_investment_rows(conn, current_user_id, investment_id=investment_id)
            existing_item = serialize_investment(existing_rows[0]) if existing_rows else None
            if existing_item:
                try:
                    validate_asset_transaction_backing(
                        conn,
                        current_user_id,
                        existing_item["asset_id"],
                        exclude_ids={investment_id},
                    )
                except ValidationError as exc:
                    return validation_error(str(exc), 409)
            delete_investment_cash_transaction(conn, current_user_id, investment_id)
            conn.execute(
                "DELETE FROM investment_transactions WHERE id = ? AND user_id = ?",
                (investment_id, current_user_id),
            )
        refresh_realized_results(current_user_id)
        refresh_materialized_positions(current_user_id)
        return jsonify({"deleted": True}), 200

    payload = parse_json_body()
    allowed = {"quantity", "average_price", "current_price", "metadata"}
    if not any(key in payload for key in allowed):
        return jsonify({"updated": False}), 400

    try:
        parsed_quantity = (
            parse_number(payload, "quantity", "Quantidade")
            if "quantity" in payload else None
        )
        if parsed_quantity == 0:
            raise ValidationError("Quantidade deve ser diferente de zero.")
        parsed_average_price = (
            parse_number(payload, "average_price", "Preco medio", minimum=0)
            if "average_price" in payload else None
        )
        parsed_current_price = (
            parse_optional_number(payload, "current_price", "Preco atual", minimum=0)
            if "current_price" in payload else None
        )
        parsed_metadata = payload.get("metadata") if "metadata" in payload else None
        if "metadata" in payload and parsed_metadata not in (None, "") and not isinstance(parsed_metadata, (dict, str)):
            raise ValidationError("Metadata deve ser um objeto valido.")
    except ValidationError as exc:
        return validation_error(str(exc))

    with get_db() as conn:
        existing_rows = fetch_investment_rows(conn, current_user_id, investment_id=investment_id)
        existing_row = existing_rows[0] if existing_rows else None
        if not existing_row:
            return jsonify({"error": "Investimento nao encontrado."}), 404

        existing = serialize_investment(existing_row)
        asset_class = existing["asset_class"]
        quantity = parsed_quantity if parsed_quantity is not None else safe_float(existing["quantity"])
        unit_price = (
            parsed_average_price
            if parsed_average_price is not None
            else safe_float(existing["average_price"])
        )
        metadata = (
            investment_metadata_dict(parsed_metadata)
            if "metadata" in payload
            else existing.get("metadata") or {}
        )
        try:
            validate_fixed_income_metadata(asset_class, quantity, metadata)
        except ValidationError as exc:
            return validation_error(str(exc))
        transaction_date = investment_transaction_date(metadata, existing.get("created_at"))

        if "quantity" in payload:
            if asset_class != "FIXED_INCOME" and quantity < 0:
                available_quantity = fetch_position_quantity(
                    conn,
                    current_user_id,
                    asset_class,
                    existing["ticker_or_name"],
                    exclude_id=investment_id,
                )
                if abs(quantity) - available_quantity > 0.000001:
                    return validation_error("Venda maior que a quantidade disponivel na carteira.")

        try:
            validate_asset_transaction_backing(
                conn,
                current_user_id,
                existing["asset_id"],
                exclude_ids={investment_id},
                replacements=[{
                    **existing,
                    "quantity": quantity,
                    "average_price": unit_price,
                    "movement_type": investment_movement_type(quantity, metadata),
                    "gross_amount": investment_gross_amount(quantity, unit_price),
                    "fee_amount": investment_fee_amount(metadata),
                    "transaction_date": transaction_date,
                    "metadata": metadata,
                }],
            )
        except ValidationError as exc:
            return validation_error(str(exc), 409)

        conn.execute(
            """
            UPDATE investment_transactions
            SET quantity = ?,
                unit_price = ?,
                movement_type = ?,
                gross_amount = ?,
                fee_amount = ?,
                transaction_date = ?,
                metadata = ?,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = ? AND user_id = ?
            """,
            (
                quantity,
                unit_price,
                investment_movement_type(quantity, metadata),
                investment_gross_amount(quantity, unit_price),
                investment_fee_amount(metadata),
                transaction_date,
                encode_metadata(metadata),
                investment_id,
                current_user_id,
            ),
        )

        if "current_price" in payload:
            record_price_quote(
                conn,
                current_user_id,
                existing["asset_id"],
                parsed_current_price,
                asset_class=asset_class,
                transaction_id=investment_id,
                source="manual",
            )

        row = fetch_investment_rows(conn, current_user_id, investment_id=investment_id)[0]
        sync_investment_cash_transaction(
            conn,
            current_user_id,
            serialize_investment(row),
        )
    if not row:
        return jsonify({"error": "Investimento nao encontrado."}), 404
    refresh_realized_results(current_user_id)
    refresh_materialized_positions(current_user_id)
    return jsonify(serialize_investment(row)), 200


@app.route("/api/investments/by-asset/<asset_id>", methods=["DELETE"])
@token_required
def delete_investments_by_asset(current_user_id, asset_id):
    payload = parse_json_body()
    try:
        asset_class = require_choice(
            {"asset_class": request.args.get("asset_class") or payload.get("asset_class")},
            "asset_class",
            "Classe do ativo",
            ALLOWED_ASSET_CLASSES,
        )
    except ValidationError as exc:
        return validation_error(str(exc))

    with get_db() as conn:
        asset = conn.execute(
            """
            SELECT id, asset_class, ticker
            FROM assets
            WHERE id = ? AND user_id = ?
            """,
            (asset_id, current_user_id),
        ).fetchone()
        if not asset:
            return jsonify({"deleted": 0, "error": "Ativo nao encontrado."}), 404
        if asset["asset_class"] != asset_class:
            return validation_error("Classe do ativo nao confere com o ativo informado.", 409)

        rows = conn.execute(
            """
            SELECT it.id
            FROM investment_transactions it
            WHERE it.user_id = ? AND it.asset_id = ?
            """,
            (current_user_id, asset_id),
        ).fetchall()
        for row in rows:
            delete_investment_cash_transaction(conn, current_user_id, row["id"])
        cursor = conn.execute(
            "DELETE FROM assets WHERE user_id = ? AND id = ? AND asset_class = ?",
            (current_user_id, asset_id, asset_class),
        )
    if rows:
        refresh_realized_results(current_user_id)
        refresh_materialized_positions(current_user_id)
    return jsonify({"deleted": cursor.rowcount}), 200


@app.route("/api/investments/by-ticker/<path:ticker>", methods=["DELETE"])
@token_required
def delete_investments_by_ticker(current_user_id, ticker):
    return validation_error(
        "Operacao por ticker desativada por seguranca. Use asset_id e asset_class para excluir uma posicao.",
        410,
    )


@app.route("/api/investments/price-by-asset/<asset_id>", methods=["PATCH"])
@token_required
def update_price_by_asset(current_user_id, asset_id):
    payload = parse_json_body()
    try:
        asset_class = require_choice(payload, "asset_class", "Classe do ativo", ALLOWED_ASSET_CLASSES)
        current_price = parse_number(payload, "current_price", "Preco atual", minimum=0)
    except ValidationError as exc:
        return validation_error(str(exc))

    with get_db() as conn:
        asset = conn.execute(
            """
            SELECT id, asset_class
            FROM assets
            WHERE id = ? AND user_id = ?
            """,
            (asset_id, current_user_id),
        ).fetchone()
        if not asset:
            return jsonify({"updated": 0, "error": "Ativo nao encontrado."}), 404
        if asset["asset_class"] != asset_class:
            return validation_error("Classe do ativo nao confere com o ativo informado.", 409)

        record_price_quote(
            conn,
            current_user_id,
            asset_id,
            current_price,
            asset_class=asset_class,
            source="manual",
        )
    refresh_materialized_positions(current_user_id)
    return jsonify({"updated": 1}), 200


@app.route("/api/investments/price-by-ticker", methods=["PATCH"])
@token_required
def update_price_by_ticker(current_user_id):
    return validation_error(
        "Atualizacao por ticker desativada por seguranca. Use asset_id e asset_class para atualizar cotacao.",
        410,
    )


def should_refresh_market_prices():
    value = str(request.args.get("refresh_prices", "false")).strip().lower()
    return value not in {"0", "false", "no", "off"}


@app.route("/api/investments/portfolio", methods=["GET"])
@token_required
def get_portfolio(current_user_id):
    try:
        if should_refresh_market_prices():
            try:
                refresh_market_prices(current_user_id, force=False)
            except Exception as exc:
                print(f"Erro ao atualizar cotacoes antes da carteira: {exc}")

        refresh_realized_results(current_user_id)
        portfolio = build_portfolio_snapshot(current_user_id)
        portfolio["realized_result"] = realized_results_summary(current_user_id)
        replace_materialized_positions(current_user_id, portfolio["assets"])
        return jsonify(portfolio), 200
    except Exception as exc:
        print(f"Erro no calculo: {exc}")
        return jsonify({"error": "Nao foi possivel calcular a carteira."}), 500


@app.route("/api/investments/update-prices", methods=["POST"])
@token_required
def update_stock_prices(current_user_id):
    try:
        payload = parse_json_body()
        investment_id = payload.get("investment_id")
        asset_id = payload.get("asset_id")
        asset_class = None
        if payload.get("asset_class") not in (None, ""):
            asset_class = require_choice(payload, "asset_class", "Classe do ativo", ALLOWED_ASSET_CLASSES)

        investments_to_update = fetch_investments(current_user_id, investment_id)
        if asset_id:
            investments_to_update = [
                inv for inv in investments_to_update
                if str(inv.get("asset_id")) == str(asset_id)
            ]
        if asset_class:
            investments_to_update = [
                inv for inv in investments_to_update
                if inv.get("asset_class") == asset_class
            ]
        if asset_id and not investments_to_update:
            return jsonify({"error": "Ativo nao encontrado para atualizacao de cotacao."}), 404

        # BCB e yfinance sao buscados ao mesmo tempo; as gravacoes ficam nesta thread.
        fixed_income_plan = start_fixed_income_refresh(investments_to_update)
        market_result = refresh_market_prices(
            current_user_id,
            investment_id,
            force=True,
            asset_id=asset_id,
            asset_class=asset_class,
        )
        fixed_income_result = finish_fixed_income_refresh(current_user_id, fixed_income_plan)
        updated_assets = market_result.get("updated_assets", []) + fixed_income_result.get("updated_assets", [])
        failed_assets = market_result.get("failed_assets", []) + fixed_income_result.get("failed_assets", [])
        cached_assets = market_result.get("cached_assets", [])
        updated_count = len(updated_assets)
        portfolio = build_portfolio_snapshot(current_user_id)
        try:
            replace_materialized_positions(current_user_id, portfolio["assets"])
        except Exception as exc:
            print(f"Nao foi possivel atualizar posicoes materializadas: {exc}")
        scoped_asset_ids = {str(inv.get("asset_id")) for inv in investments_to_update if inv.get("asset_id")}
        stale_assets = [
            {
                "asset_id": asset.get("asset_id"),
                "id": asset.get("id"),
                "ticker": asset.get("ticker"),
                "name": asset.get("name"),
                "asset_class": asset.get("class"),
                "quote": asset.get("quote") or {},
            }
            for asset in portfolio.get("assets", [])
            if (not scoped_asset_ids or str(asset.get("asset_id")) in scoped_asset_ids)
            and (asset.get("quote") or {}).get("status") != "fresh"
        ]

        return jsonify({
            "message": "Cotacoes e CDI atualizados com sucesso",
            "updated_count": updated_count,
            "updated_assets": updated_assets,
            "failed_assets": failed_assets,
            "cached_assets": cached_assets,
            "stale_assets": stale_assets,
            "requested_tickers": market_result["requested_tickers"],
            "priced_tickers": market_result["priced_tickers"],
        }), 200
    except ValidationError as exc:
        return validation_error(str(exc))
    except Exception as exc:
        print(f"ERRO FATAL NA ROTA UPDATE-PRICES: {exc}")
        return jsonify({"error": "Nao foi possivel atualizar os precos."}), 500


@app.route("/api/investments/history", methods=["GET"])
@token_required
def get_historical_portfolio(current_user_id):
    try:
        investments_data = fetch_investments(current_user_id)
        try:
            months_back = int(request.args.get("months", 12))
        except ValueError:
            months_back = 12
        months_back = max(1, min(months_back, 60))
        asset_class_filter = parse_asset_class_filter(request.args.get("asset_class"))
        filtered_investments = [
            inv for inv in investments_data
            if asset_class_filter is None or inv.get("asset_class") == asset_class_filter
        ]
        start_date = subtract_months(datetime.now(), months_back + 1).strftime("%Y-%m-%d")

        historical_prices = {}
        quoted_assets = [
            inv for inv in filtered_investments
            if inv.get("asset_class") in QUOTED_ASSET_CLASSES
        ]
        unique_tickers = sorted({
            ticker_key(asset.get("ticker_or_name"))
            for asset in quoted_assets
            if ticker_key(asset.get("ticker_or_name"))
        })

        if yf is None:
            historical_prices = {ticker: {} for ticker in unique_tickers}
        elif unique_tickers:
            future = _price_fetch_executor.submit(get_monthly_history, unique_tickers, start_date)
            try:
                historical_prices = future.result(timeout=PRICE_FETCH_TIMEOUT_SECONDS)
            except FutureTimeoutError:
                print("Tempo limite ao buscar historico no yfinance.")
                historical_prices = {ticker: {} for ticker in unique_tickers}
            except Exception as exc:
                print(f"Erro ao buscar historico no yfinance: {exc}")
                historical_prices = {ticker: {} for ticker in unique_tickers}

        evolution = build_portfolio_evolution(
            filtered_investments,
            historical_prices,
            months_back,
        )

        return jsonify({
            "historical_prices": historical_prices,
            "evolution": evolution,
        }), 200
    except Exception as exc:
        print(f"Erro no historico de investimentos: {exc}")
        return jsonify({"error": "Nao foi possivel carregar o historico de investimentos."}), 500


init_db()
run_startup_backup()
prune_orphan_attachment_files()

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", port=5000)
