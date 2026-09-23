import json
import os
import sqlite3
import urllib.error
import urllib.request
import calendar
import math
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
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
    row_to_dict,
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
from services.accounts import (
    ensure_default_account,
)
from dates import (
    month_end,
    month_key,
    month_label,
    parse_iso_date,
    subtract_months,
)
from source_types import (
    INVESTMENT_CASH_SOURCE_TYPE,
)
from services.attachments import (
    prune_orphan_attachment_files,
)
from routes.transactions import (
    csv_response,
)
from asset_classes import (
    ALLOWED_ASSET_CLASSES,
    ASSET_CLASS_LABELS,
    QUOTED_ASSET_CLASSES,
    parse_asset_class_filter,
)
from services.prices import (
    _price_fetch_executor,
    get_market_prices_with_status,
    get_monthly_history,
    market_price_provider,
    quote_info_from_investment,
    quote_timestamp,
    record_price_quote,
    ticker_key,
    yf,
)

ALLOWED_PROCEEDS_TYPES = {"DIVIDEND", "JCP", "AMORTIZATION"}
INVESTMENT_CASH_CATEGORY = "Investimento"
DEFAULT_JCP_TAX_RATE = 0.15
DEFAULT_REALIZED_TAX_RATES = {
    "STOCKS": 0.15,
    "REIT": 0.20,
    "CATTLE": 0.15,
    "OTHER": 0.15,
    "FIXED_INCOME": 0.15,
}


# Separado do yfinance: um download travado la nao pode enfileirar o BCB.
_index_fetch_executor = ThreadPoolExecutor(max_workers=2)

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


def ensure_asset_owner(conn, current_user_id, asset_id):
    asset = conn.execute(
        """
        SELECT id, user_id, asset_class, ticker, name
        FROM assets
        WHERE id = ? AND user_id = ?
        """,
        (asset_id, current_user_id),
    ).fetchone()
    if not asset:
        raise ValidationError("Ativo nao encontrado.")
    return asset


def serialize_investment(row):
    item = row_to_dict(row)
    if item:
        item["metadata"] = parse_metadata_value(item.get("metadata"))
        if "current_quote_metadata" in item:
            item["current_quote_metadata"] = parse_metadata_value(item.get("current_quote_metadata"))
        if "realized_metadata" in item:
            item["realized_metadata"] = parse_metadata_value(item.get("realized_metadata"))
    return item


def investment_metadata_dict(value):
    return parse_metadata_value(value)


def investment_transaction_date(metadata, created_at=None):
    metadata = metadata or {}
    for key in ("redemption_date", "sale_date", "purchase_date"):
        parsed = parse_iso_date(metadata.get(key))
        if parsed:
            return parsed.strftime("%Y-%m-%d")

    parsed_created_at = parse_iso_date(created_at)
    if parsed_created_at:
        return parsed_created_at.strftime("%Y-%m-%d")
    return datetime.now().strftime("%Y-%m-%d")


def investment_movement_type(quantity, metadata):
    metadata = metadata or {}
    if metadata.get("is_redemption"):
        return "REDEMPTION"
    if safe_float(quantity) < 0:
        return "SELL"
    return "BUY"


def investment_fee_amount(metadata):
    return max(safe_float((metadata or {}).get("other_costs")), 0)


def investment_gross_amount(quantity, unit_price):
    return abs(safe_float(quantity) * safe_float(unit_price))


def investment_sale_price(investment, metadata):
    sale_price = safe_float((metadata or {}).get("sale_price"), None)
    if sale_price is not None and math.isfinite(sale_price) and sale_price > 0:
        return sale_price

    current_price = safe_float(investment.get("current_price"), None)
    if current_price is not None and math.isfinite(current_price) and current_price > 0:
        return current_price

    return safe_float(investment.get("average_price"))


def investment_cash_amount(investment):
    metadata = investment.get("metadata") or {}
    movement_type = investment.get("movement_type") or investment_movement_type(
        investment.get("quantity"),
        metadata,
    )
    quantity = safe_float(investment.get("quantity"))
    unit_price = safe_float(investment.get("average_price"))
    fees = investment_fee_amount(metadata)

    if movement_type == "BUY":
        amount = abs(quantity * unit_price)
    elif movement_type == "SELL":
        amount = (abs(quantity) * investment_sale_price(investment, metadata)) - fees
    elif movement_type == "REDEMPTION":
        amount = safe_float(investment.get("current_price"), abs(quantity * unit_price)) - fees
    else:
        return None

    if not math.isfinite(amount) or amount <= 0:
        return None
    return rounded_money(amount)


def investment_cash_type(investment):
    movement_type = investment.get("movement_type") or investment_movement_type(
        investment.get("quantity"),
        investment.get("metadata") or {},
    )
    if movement_type == "BUY":
        return "EXPENSE"
    if movement_type in {"SELL", "REDEMPTION"}:
        return "INCOME"
    return None


def investment_cash_description(investment):
    movement_type = investment.get("movement_type") or investment_movement_type(
        investment.get("quantity"),
        investment.get("metadata") or {},
    )
    ticker = ticker_key(investment.get("ticker_or_name"))
    labels = {
        "BUY": "Compra de investimento",
        "SELL": "Venda de investimento",
        "REDEMPTION": "Resgate de investimento",
    }
    return f"{labels.get(movement_type, 'Movimento de investimento')}: {ticker}"


def investment_cash_metadata(investment):
    return {
        "asset_id": investment.get("asset_id"),
        "asset_class": investment.get("asset_class"),
        "ticker": ticker_key(investment.get("ticker_or_name")),
        "movement_type": investment.get("movement_type"),
    }


def sync_investment_cash_transaction(conn, current_user_id, investment):
    amount = investment_cash_amount(investment)
    cash_type = investment_cash_type(investment)
    investment_id = investment.get("id")
    if not investment_id:
        return

    if amount is None or cash_type is None:
        conn.execute(
            """
            DELETE FROM transactions
            WHERE user_id = ? AND source_type = ? AND source_id = ?
            """,
            (current_user_id, INVESTMENT_CASH_SOURCE_TYPE, investment_id),
        )
        return

    transaction_date = investment.get("transaction_date") or investment_transaction_date(
        investment.get("metadata") or {},
        investment.get("created_at"),
    )
    description = investment_cash_description(investment)
    metadata = investment_cash_metadata(investment)

    existing = conn.execute(
        """
        SELECT id FROM transactions
        WHERE user_id = ? AND source_type = ? AND source_id = ?
        """,
        (current_user_id, INVESTMENT_CASH_SOURCE_TYPE, investment_id),
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE transactions
            SET amount = ?,
                date = ?,
                category = ?,
                description = ?,
                type = ?,
                metadata = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                amount,
                transaction_date,
                INVESTMENT_CASH_CATEGORY,
                description,
                cash_type,
                encode_metadata(metadata),
                existing["id"],
                current_user_id,
            ),
        )
        return

    conn.execute(
        """
        INSERT INTO transactions
        (id, user_id, account_id, amount, date, category, description, type, source_type, source_id, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"cash:{investment_id}",
            current_user_id,
            ensure_default_account(conn, current_user_id),
            amount,
            transaction_date,
            INVESTMENT_CASH_CATEGORY,
            description,
            cash_type,
            INVESTMENT_CASH_SOURCE_TYPE,
            investment_id,
            encode_metadata(metadata),
        ),
    )


def delete_investment_cash_transaction(conn, current_user_id, investment_id):
    conn.execute(
        """
        DELETE FROM transactions
        WHERE user_id = ? AND source_type = ? AND source_id = ?
        """,
        (current_user_id, INVESTMENT_CASH_SOURCE_TYPE, investment_id),
    )


def normalized_tax_rate(value):
    rate = safe_float(value, None)
    if rate is None or not math.isfinite(rate) or rate < 0:
        return None
    if rate > 1:
        return rate / 100
    return rate


def fixed_income_tax_rate_for_days(days_invested):
    days = max(int(days_invested or 0), 0)
    if days <= 180:
        return 0.225
    if days <= 360:
        return 0.200
    if days <= 720:
        return 0.175
    return 0.150


def realized_tax_rate(asset_class, metadata=None, holding_days=None):
    metadata = metadata or {}
    explicit_rate = normalized_tax_rate(
        metadata.get("tax_rate", metadata.get("tax_rate_percent"))
    )
    if explicit_rate is not None:
        return explicit_rate

    if asset_class == "FIXED_INCOME":
        if metadata.get("is_tax_free", False):
            return 0
        if holding_days is not None:
            return fixed_income_tax_rate_for_days(holding_days)

    return DEFAULT_REALIZED_TAX_RATES.get(asset_class, 0)


def investment_gross_proceeds(investment, metadata):
    movement_type = investment.get("movement_type") or investment_movement_type(
        investment.get("quantity"),
        metadata,
    )
    quantity = abs(safe_float(investment.get("quantity")))
    if movement_type == "SELL":
        return quantity * investment_sale_price(investment, metadata)
    if movement_type == "REDEMPTION":
        return safe_float(
            investment.get("current_price"),
            abs(quantity * safe_float(investment.get("average_price"))),
        )
    return 0


def investment_operation_date(investment):
    return investment_transaction_date(
        investment.get("metadata") or {},
        investment.get("transaction_date") or investment.get("created_at"),
    )


def get_or_create_asset(conn, current_user_id, asset_class, ticker_or_name):
    ticker = ticker_key(ticker_or_name)
    row = conn.execute(
        """
        SELECT id FROM assets
        WHERE user_id = ? AND asset_class = ? AND ticker = ?
        """,
        (current_user_id, asset_class, ticker),
    ).fetchone()
    if row:
        return row["id"]

    asset_id = new_id()
    conn.execute(
        """
        INSERT INTO assets
        (id, user_id, asset_class, ticker, name)
        VALUES (?, ?, ?, ?, ?)
        """,
        (asset_id, current_user_id, asset_class, ticker, ticker or ticker_or_name),
    )
    return asset_id


def fetch_investment_rows(conn, current_user_id, *, investment_id=None, order_by="it.created_at", direction="ASC"):
    query = f"""
        SELECT
            it.id,
            it.user_id,
            it.asset_id,
            a.asset_class,
            a.ticker AS ticker_or_name,
            it.quantity,
            it.unit_price AS average_price,
            COALESCE(
                (
                    SELECT pq.price
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id = it.id
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                ),
                (
                    SELECT pq.price
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id IS NULL
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                ),
                it.unit_price
            ) AS current_price,
            COALESCE(
                (
                    SELECT pq.id
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id = it.id
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                ),
                (
                    SELECT pq.id
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id IS NULL
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                )
            ) AS current_quote_id,
            COALESCE(
                (
                    SELECT pq.quoted_at
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id = it.id
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                ),
                (
                    SELECT pq.quoted_at
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id IS NULL
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                )
            ) AS current_quote_quoted_at,
            COALESCE(
                (
                    SELECT pq.source
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id = it.id
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                ),
                (
                    SELECT pq.source
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id IS NULL
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                )
            ) AS current_quote_source,
            COALESCE(
                (
                    SELECT pq.metadata
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id = it.id
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                ),
                (
                    SELECT pq.metadata
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id IS NULL
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                )
            ) AS current_quote_metadata,
            it.metadata,
            it.movement_type,
            it.gross_amount,
            it.fee_amount,
            it.transaction_date,
            it.created_at,
            it.updated_at,
            rr.quantity AS realized_quantity,
            rr.average_cost AS realized_average_cost,
            rr.gross_proceeds AS realized_gross_proceeds,
            rr.fee_amount AS realized_fee_amount,
            rr.net_proceeds AS realized_net_proceeds,
            rr.net_unit_price AS realized_net_unit_price,
            rr.cost_basis AS realized_cost_basis,
            rr.realized_profit,
            rr.profitability_percent AS realized_profitability_percent,
            rr.tax_rate AS realized_tax_rate,
            rr.tax_amount AS realized_tax_amount,
            rr.net_profit_after_tax AS realized_net_profit_after_tax,
            rr.operation_date AS realized_operation_date,
            rr.metadata AS realized_metadata
        FROM investment_transactions it
        JOIN assets a ON a.id = it.asset_id
        LEFT JOIN investment_realized_results rr
          ON rr.user_id = it.user_id
         AND rr.source_transaction_id = it.id
        WHERE it.user_id = ?
    """
    params = [current_user_id]
    if investment_id:
        query += " AND it.id = ?"
        params.append(investment_id)
    query += f" ORDER BY {order_by} {direction}"
    return conn.execute(query, params).fetchall()


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


def investment_movement_date(investment):
    metadata = investment.get("metadata") or {}
    for key in ("redemption_date", "sale_date", "purchase_date"):
        parsed = parse_iso_date(metadata.get(key))
        if parsed:
            return parsed
    return parse_iso_date(investment.get("created_at")) or datetime.now()


def historical_price_for_month(historical_prices, ticker, target_month_key):
    ticker_prices = historical_prices.get(ticker_key(ticker), {})
    if not isinstance(ticker_prices, dict):
        return None

    price = safe_float(ticker_prices.get(target_month_key), None)
    if price is not None and math.isfinite(price) and price > 0:
        return price

    previous_keys = sorted(
        key for key in ticker_prices
        if isinstance(key, str) and key <= target_month_key
    )
    if not previous_keys:
        return None

    price = safe_float(ticker_prices.get(previous_keys[-1]), None)
    if price is not None and math.isfinite(price) and price > 0:
        return price
    return None


def fixed_income_net_value(asset_class, metadata, invested_value, market_value, reference_date):
    if asset_class != "FIXED_INCOME":
        return market_value

    profit = market_value - invested_value
    if profit <= 0 or metadata.get("is_tax_free", False):
        return market_value

    purchase_date = parse_iso_date(metadata.get("purchase_date"))
    if not purchase_date:
        return market_value

    days_invested = max((reference_date - purchase_date).days, 0)
    if days_invested <= 180:
        tax_rate = 0.225
    elif days_invested <= 360:
        tax_rate = 0.200
    elif days_invested <= 720:
        tax_rate = 0.175
    else:
        tax_rate = 0.150

    return market_value - (profit * tax_rate)


def movement_affects_fixed_income_position(investment):
    metadata = investment.get("metadata") or {}
    return (
        investment.get("asset_class") == "FIXED_INCOME"
        and safe_float(investment.get("quantity")) < 0
        and metadata.get("is_redemption")
        and metadata.get("affects_position")
        and metadata.get("related_id")
    )


def current_price_from_position(data, default=0):
    price = safe_float(data.get("current_price"), default)
    if data.get("class") == "FIXED_INCOME" and data.get("original_invested", 0) > 0:
        factor = price / data["original_invested"]
        price = data["total_invested"] * factor
    return max(price, 0)


def portfolio_evolution_months(months_back):
    current_month = datetime(datetime.now().year, datetime.now().month, 1)
    return [
        subtract_months(current_month, months_back - 1 - index)
        for index in range(months_back)
    ]


def build_portfolio_evolution(investments_data, historical_prices, months_back):
    months = portfolio_evolution_months(months_back)
    current_month_key = month_key(datetime.now())
    evolution = []

    for month_start in months:
        target_key = month_key(month_start)
        target_end = month_end(month_start)
        positions = {}

        for investment in investments_data:
            metadata = investment.get("metadata") or {}
            if investment_movement_date(investment) > target_end:
                continue

            asset_class = investment.get("asset_class")
            ticker = ticker_key(investment.get("ticker_or_name"))
            if not asset_class or not ticker:
                continue

            quantity = safe_float(investment.get("quantity"))
            average_price = safe_float(investment.get("average_price"))
            if quantity == 0:
                continue

            if movement_affects_fixed_income_position(investment):
                group_key = str(metadata.get("related_id"))
            elif asset_class == "FIXED_INCOME" and metadata.get("is_redemption"):
                continue
            else:
                group_key = str(investment.get("id")) if asset_class == "FIXED_INCOME" else f"{asset_class}:{ticker}"

            if group_key not in positions:
                positions[group_key] = {
                    "ticker": ticker,
                    "class": asset_class,
                    "quantity": 0,
                    "applied": 0,
                    "original_applied": 0,
                    "current_price": safe_float(investment.get("current_price"), average_price),
                    "metadata": metadata,
                }

            position = positions[group_key]
            position["applied"] += quantity * average_price
            if not movement_affects_fixed_income_position(investment):
                position["quantity"] += quantity
                if asset_class == "FIXED_INCOME" and quantity > 0:
                    position["original_applied"] += quantity * average_price
                    position["metadata"] = metadata
                    position["ticker"] = ticker
            if investment.get("current_price") is not None and not movement_affects_fixed_income_position(investment):
                position["current_price"] = safe_float(investment.get("current_price"), average_price)

        applied_total = 0
        net_total = 0

        for position in positions.values():
            quantity = position["quantity"]
            applied_value = position["applied"]
            if quantity <= 0 or applied_value <= 0:
                continue

            adjusted_quantity = quantity
            if position["class"] == "CATTLE":
                mortality_rate = safe_float(position["metadata"].get("mortality_rate"))
                adjusted_quantity = quantity * (1 - mortality_rate)

            if position["class"] in QUOTED_ASSET_CLASSES:
                price = historical_price_for_month(
                    historical_prices,
                    position["ticker"],
                    target_key,
                )
                if price is None:
                    price = safe_float(position.get("current_price"), applied_value / quantity)
                market_value = adjusted_quantity * price
            elif position["class"] == "FIXED_INCOME" and target_key == current_month_key:
                original_applied = position.get("original_applied", applied_value)
                if original_applied > 0:
                    factor = safe_float(position.get("current_price"), original_applied) / original_applied
                    market_value = applied_value * factor
                else:
                    market_value = applied_value
            elif target_key == current_month_key:
                market_value = adjusted_quantity * safe_float(
                    position.get("current_price"),
                    applied_value / quantity,
                )
            else:
                market_value = applied_value

            net_value = fixed_income_net_value(
                position["class"],
                position["metadata"],
                applied_value,
                market_value,
                target_end,
            )

            applied_total += applied_value
            net_total += net_value

        gain = net_total - applied_total
        evolution.append({
            "month": month_label(month_start),
            "month_key": target_key,
            "patrimonio": rounded_money(max(net_total, 0)),
            "valorAplicado": rounded_money(max(applied_total, 0)),
            "ganhoCapital": rounded_money(max(gain, 0)),
            "ganhoCapitalReal": rounded_money(gain),
        })

    return evolution


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


def fetch_investments(current_user_id, investment_id=None):
    with get_db() as conn:
        rows = fetch_investment_rows(
            conn,
            current_user_id,
            investment_id=investment_id,
            order_by="it.created_at",
            direction="ASC",
        )
    return [serialize_investment(row) for row in rows]


def fetch_position_quantity(conn, current_user_id, asset_class, ticker, exclude_id=None):
    query = """
        SELECT COALESCE(SUM(quantity), 0) AS quantity
        FROM investment_transactions it
        JOIN assets a ON a.id = it.asset_id
        WHERE it.user_id = ?
          AND a.asset_class = ?
          AND a.ticker = ?
    """
    params = [current_user_id, asset_class, ticker_key(ticker)]
    if exclude_id:
        query += " AND it.id <> ?"
        params.append(exclude_id)
    row = conn.execute(query, params).fetchone()
    return safe_float(row["quantity"] if row else 0)


def resolve_catalog_ticker(conn, current_user_id, asset_class, ticker_or_name, quantity):
    """Garante que uma compra de renda variavel use um papel conhecido.

    Devolve sempre o ticker canonico das classes com cotacao (maiusculas, sem o
    sufixo .SA), inclusive nas vendas -- e a normalizacao das duas pontas que
    faz a venda encontrar a posicao criada pela compra. Vendas e resgates nao
    consultam o catalogo (eles se apoiam numa posicao que ja existe) e classes
    sem cotacao (renda fixa, gado, outros) continuam com texto livre, porque ali
    o "ticker" e so o nome que o dono deu ao ativo.

    Posicoes antigas, anteriores ao catalogo, continuam aceitas: se o ativo ja
    existe na carteira do usuario, o lancamento passa mesmo fora da lista.
    """
    ticker = market_catalog.normalize_ticker(ticker_or_name)
    if asset_class not in QUOTED_ASSET_CLASSES:
        # Renda fixa, gado e outros: o "ticker" e so o nome do ativo, texto livre.
        return ticker_key(ticker_or_name)
    if quantity <= 0:
        # Venda/resgate nao consulta o catalogo, mas usa a mesma normalizacao da
        # compra -- senao "PETR4.SA" nao acha a posicao gravada como "PETR4".
        return ticker

    if not ticker:
        raise ValidationError("Informe o ativo do lancamento.")

    entry = market_catalog.lookup(ticker)
    if entry is None:
        # O ticker gravado pode ser o normalizado ou, num ativo antigo, o texto
        # original com sufixo.
        existing = conn.execute(
            """
            SELECT ticker FROM assets
            WHERE user_id = ? AND asset_class = ? AND ticker IN (?, ?)
            """,
            (current_user_id, asset_class, ticker, ticker_key(ticker_or_name)),
        ).fetchone()
        if existing:
            return existing["ticker"]
        raise ValidationError(
            f"Ativo {ticker} nao encontrado na lista da B3. Selecione um papel pela busca."
        )

    if entry["asset_class"] != asset_class:
        expected = ASSET_CLASS_LABELS.get(entry["asset_class"], entry["asset_class"])
        raise ValidationError(
            f"{ticker} e um ativo do tipo {entry['kind_label']}. Selecione o tipo {expected}."
        )

    return entry["ticker"]


def validate_investment_movement(conn, current_user_id, asset_class, ticker_or_name, quantity):
    if quantity >= 0 or asset_class == "FIXED_INCOME":
        return

    available_quantity = fetch_position_quantity(
        conn,
        current_user_id,
        asset_class,
        ticker_or_name,
    )
    if abs(quantity) - available_quantity > 0.000001:
        raise ValidationError("Venda maior que a quantidade disponivel na carteira.")


def movement_sort_key(investment):
    return (
        investment_operation_date(investment),
        str(investment.get("created_at") or ""),
        str(investment.get("id") or ""),
    )


def fetch_asset_transactions_for_backing(conn, current_user_id, asset_id):
    rows = conn.execute(
        """
        SELECT
            it.id,
            it.user_id,
            it.asset_id,
            asset.asset_class,
            asset.ticker AS ticker_or_name,
            it.quantity,
            it.unit_price AS average_price,
            it.gross_amount,
            it.fee_amount,
            it.movement_type,
            it.transaction_date,
            it.metadata,
            it.created_at,
            it.updated_at
        FROM investment_transactions it
        JOIN assets asset ON asset.id = it.asset_id
        WHERE it.user_id = ?
          AND it.asset_id = ?
        """,
        (current_user_id, asset_id),
    ).fetchall()
    return [serialize_investment(row) for row in rows]


def validate_asset_transaction_backing(
    conn,
    current_user_id,
    asset_id,
    *,
    exclude_ids=None,
    replacements=None,
):
    excluded = {str(item_id) for item_id in (exclude_ids or set())}
    transactions = [
        item
        for item in fetch_asset_transactions_for_backing(conn, current_user_id, asset_id)
        if str(item.get("id")) not in excluded
    ]
    transactions.extend(replacements or [])
    transactions = sorted(transactions, key=movement_sort_key)
    remaining_ids = {str(item.get("id")) for item in transactions if item.get("id")}

    for item in transactions:
        metadata = item.get("metadata") or {}
        related_id = metadata.get("related_id")
        if metadata.get("is_redemption") and related_id and str(related_id) not in remaining_ids:
            raise ValidationError(
                "Nao e possivel alterar ou excluir essa compra: ela possui resgate vinculado."
            )

    balance_by_asset = {}
    for item in transactions:
        asset_class = item.get("asset_class")
        if asset_class == "FIXED_INCOME":
            continue

        quantity = safe_float(item.get("quantity"))
        if quantity == 0:
            continue

        key = item.get("asset_id") or asset_id
        next_balance = balance_by_asset.get(key, 0) + quantity
        if next_balance < -0.000001:
            ticker = ticker_key(item.get("ticker_or_name"))
            raise ValidationError(
                f"Nao e possivel alterar ou excluir essa movimentacao: {ticker} ficaria com venda sem lastro de compra anterior."
            )
        balance_by_asset[key] = next_balance


def days_between_dates(start_date, end_date):
    start = parse_iso_date(start_date)
    end = parse_iso_date(end_date)
    if not start or not end:
        return None
    return max((end - start).days, 0)


def realized_result_record(investment, *, quantity, gross_proceeds, fees, cost_basis, tax_amount, tax_rate, metadata):
    quantity = abs(safe_float(quantity))
    gross_proceeds = max(safe_float(gross_proceeds), 0)
    fees = max(safe_float(fees), 0)
    net_proceeds = max(gross_proceeds - fees, 0)
    cost_basis = max(safe_float(cost_basis), 0)
    realized_profit = net_proceeds - cost_basis
    average_cost = cost_basis / quantity if quantity > 0 else 0
    net_unit_price = net_proceeds / quantity if quantity > 0 else 0
    profitability = (realized_profit / cost_basis * 100) if cost_basis > 0 else 0
    tax_amount = max(safe_float(tax_amount), 0)

    return {
        "id": f"realized:{investment['id']}",
        "user_id": investment["user_id"],
        "asset_id": investment["asset_id"],
        "source_transaction_id": investment["id"],
        "movement_type": investment.get("movement_type") or investment_movement_type(
            investment.get("quantity"),
            investment.get("metadata") or {},
        ),
        "quantity": round(quantity, 6),
        "average_cost": rounded_money(average_cost),
        "gross_proceeds": rounded_money(gross_proceeds),
        "fee_amount": rounded_money(fees),
        "net_proceeds": rounded_money(net_proceeds),
        "net_unit_price": rounded_money(net_unit_price),
        "cost_basis": rounded_money(cost_basis),
        "realized_profit": rounded_money(realized_profit),
        "profitability_percent": round(profitability, 2),
        "tax_rate": round(safe_float(tax_rate), 6),
        "tax_amount": rounded_money(tax_amount),
        "net_profit_after_tax": rounded_money(realized_profit - tax_amount),
        "operation_date": investment_operation_date(investment),
        "metadata": metadata,
    }


def allocation_tax_amount(asset_class, movement_metadata, allocation, profit):
    rate = realized_tax_rate(
        asset_class,
        movement_metadata,
        allocation.get("holding_days"),
    )
    return max(profit, 0) * rate, rate


def build_variable_realized_result(investment, lots):
    metadata = investment.get("metadata") or {}
    asset_class = investment.get("asset_class")
    operation_date = investment_operation_date(investment)
    sold_quantity = abs(safe_float(investment.get("quantity")))
    fees = max(safe_float(investment.get("fee_amount"), investment_fee_amount(metadata)), 0)
    gross_proceeds = investment_gross_proceeds(investment, metadata)
    gross_unit_price = gross_proceeds / sold_quantity if sold_quantity > 0 else 0

    remaining = sold_quantity
    allocations = []
    cost_basis = 0
    index = 0

    while remaining > 0.000001 and index < len(lots):
        lot = lots[index]
        lot_quantity = safe_float(lot.get("remaining_quantity"))
        if lot_quantity <= 0.000001:
            lots.pop(index)
            continue

        consumed_quantity = min(remaining, lot_quantity)
        allocation_cost = consumed_quantity * safe_float(lot.get("unit_cost"))
        holding_days = days_between_dates(lot.get("purchase_date"), operation_date)
        allocations.append({
            "buy_transaction_id": lot.get("transaction_id"),
            "purchase_date": lot.get("purchase_date"),
            "quantity": round(consumed_quantity, 6),
            "unit_cost": rounded_money(lot.get("unit_cost")),
            "cost_basis": rounded_money(allocation_cost),
            "holding_days": holding_days,
        })
        cost_basis += allocation_cost
        lot["remaining_quantity"] = lot_quantity - consumed_quantity
        remaining -= consumed_quantity

        if lot["remaining_quantity"] <= 0.000001:
            lots.pop(index)
        else:
            index += 1

    if remaining > 0.000001:
        fallback_unit_cost = safe_float(investment.get("average_price"))
        fallback_cost = remaining * fallback_unit_cost
        allocations.append({
            "buy_transaction_id": None,
            "purchase_date": None,
            "quantity": round(remaining, 6),
            "unit_cost": rounded_money(fallback_unit_cost),
            "cost_basis": rounded_money(fallback_cost),
            "holding_days": None,
            "unmatched": True,
        })
        cost_basis += fallback_cost

    tax_amount = 0
    taxable_profit = 0
    for allocation in allocations:
        allocation_quantity = safe_float(allocation.get("quantity"))
        fee_share = fees * (allocation_quantity / sold_quantity) if sold_quantity > 0 else 0
        allocation_gross = allocation_quantity * gross_unit_price
        allocation_net = max(allocation_gross - fee_share, 0)
        allocation_profit = allocation_net - safe_float(allocation.get("cost_basis"))
        allocation_tax, allocation_rate = allocation_tax_amount(
            asset_class,
            metadata,
            allocation,
            allocation_profit,
        )
        tax_amount += allocation_tax
        taxable_profit += max(allocation_profit, 0)
        allocation["gross_proceeds"] = rounded_money(allocation_gross)
        allocation["fee_amount"] = rounded_money(fee_share)
        allocation["net_proceeds"] = rounded_money(allocation_net)
        allocation["realized_profit"] = rounded_money(allocation_profit)
        allocation["tax_rate"] = round(allocation_rate, 6)
        allocation["tax_amount"] = rounded_money(allocation_tax)

    effective_tax_rate = tax_amount / taxable_profit if taxable_profit > 0 else realized_tax_rate(asset_class, metadata)
    return realized_result_record(
        investment,
        quantity=sold_quantity,
        gross_proceeds=gross_proceeds,
        fees=fees,
        cost_basis=cost_basis,
        tax_amount=tax_amount,
        tax_rate=effective_tax_rate,
        metadata={
            "cost_method": "FIFO",
            "tax_method": "estimativa_simples",
            "tax_note": "Estimativa operacional. Valide regras fiscais e isencoes antes da declaracao oficial.",
            "gross_unit_price": rounded_money(gross_unit_price),
            "unmatched_quantity": round(max(remaining, 0), 6),
            "allocations": allocations,
        },
    )


def build_fixed_income_realized_result(investment, investments_by_id):
    metadata = investment.get("metadata") or {}
    operation_date = investment_operation_date(investment)
    quantity = abs(safe_float(investment.get("quantity"), 1)) or 1
    fees = max(safe_float(investment.get("fee_amount"), investment_fee_amount(metadata)), 0)
    gross_proceeds = investment_gross_proceeds(investment, metadata)
    cost_basis = abs(safe_float(investment.get("quantity")) * safe_float(investment.get("average_price")))
    related_id = metadata.get("related_id")
    related_purchase = investments_by_id.get(str(related_id)) if related_id else None
    purchase_metadata = (related_purchase or {}).get("metadata") or {}
    purchase_date = investment_operation_date(related_purchase) if related_purchase else None
    holding_days = days_between_dates(purchase_date, operation_date)
    tax_metadata = {**purchase_metadata, **metadata}
    profit = max(gross_proceeds - fees, 0) - cost_basis
    tax_rate = realized_tax_rate("FIXED_INCOME", tax_metadata, holding_days)
    tax_amount = max(profit, 0) * tax_rate

    allocation = {
        "buy_transaction_id": related_id,
        "purchase_date": purchase_date,
        "quantity": round(quantity, 6),
        "unit_cost": rounded_money(cost_basis / quantity if quantity > 0 else cost_basis),
        "cost_basis": rounded_money(cost_basis),
        "holding_days": holding_days,
        "gross_proceeds": rounded_money(gross_proceeds),
        "fee_amount": rounded_money(fees),
        "net_proceeds": rounded_money(max(gross_proceeds - fees, 0)),
        "realized_profit": rounded_money(profit),
        "tax_rate": round(tax_rate, 6),
        "tax_amount": rounded_money(tax_amount),
    }

    return realized_result_record(
        investment,
        quantity=quantity,
        gross_proceeds=gross_proceeds,
        fees=fees,
        cost_basis=cost_basis,
        tax_amount=tax_amount,
        tax_rate=tax_rate,
        metadata={
            "cost_method": "LOT_REDEMPTION",
            "tax_method": "estimativa_simples",
            "tax_note": "Estimativa operacional. Valide regras fiscais e isencoes antes da declaracao oficial.",
            "gross_unit_price": rounded_money(gross_proceeds / quantity if quantity > 0 else gross_proceeds),
            "allocations": [allocation],
        },
    )


def build_realized_results(current_user_id):
    investments = sorted(fetch_investments(current_user_id), key=movement_sort_key)
    investments_by_id = {str(item.get("id")): item for item in investments}
    lots_by_asset = {}
    results = []

    for investment in investments:
        asset_id = investment.get("asset_id")
        if not asset_id:
            continue

        metadata = investment.get("metadata") or {}
        movement_type = investment.get("movement_type") or investment_movement_type(
            investment.get("quantity"),
            metadata,
        )
        quantity = safe_float(investment.get("quantity"))
        asset_lots = lots_by_asset.setdefault(asset_id, [])

        if movement_type == "BUY" and quantity > 0:
            asset_lots.append({
                "transaction_id": investment.get("id"),
                "purchase_date": investment_operation_date(investment),
                "remaining_quantity": quantity,
                "unit_cost": safe_float(investment.get("average_price")),
                "metadata": metadata,
            })
            continue

        if movement_type == "SELL" and quantity < 0:
            results.append(build_variable_realized_result(investment, asset_lots))
            continue

        if movement_type == "REDEMPTION":
            results.append(build_fixed_income_realized_result(investment, investments_by_id))

    return results


def replace_realized_results(current_user_id, results):
    with get_db() as conn:
        conn.execute("DELETE FROM investment_realized_results WHERE user_id = ?", (current_user_id,))
        for item in results:
            conn.execute(
                """
                INSERT INTO investment_realized_results
                (
                    id, user_id, asset_id, source_transaction_id, movement_type,
                    quantity, average_cost, gross_proceeds, fee_amount,
                    net_proceeds, net_unit_price, cost_basis, realized_profit,
                    profitability_percent, tax_rate, tax_amount, net_profit_after_tax,
                    operation_date, metadata, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                """,
                (
                    item["id"],
                    item["user_id"],
                    item["asset_id"],
                    item["source_transaction_id"],
                    item["movement_type"],
                    item["quantity"],
                    item["average_cost"],
                    item["gross_proceeds"],
                    item["fee_amount"],
                    item["net_proceeds"],
                    item["net_unit_price"],
                    item["cost_basis"],
                    item["realized_profit"],
                    item["profitability_percent"],
                    item["tax_rate"],
                    item["tax_amount"],
                    item["net_profit_after_tax"],
                    item["operation_date"],
                    encode_metadata(item.get("metadata")),
                ),
            )


def refresh_realized_results(current_user_id):
    results = build_realized_results(current_user_id)
    replace_realized_results(current_user_id, results)
    return results


def realized_results_summary(current_user_id):
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS operation_count,
                COALESCE(SUM(gross_proceeds), 0) AS gross_proceeds,
                COALESCE(SUM(fee_amount), 0) AS fee_amount,
                COALESCE(SUM(net_proceeds), 0) AS net_proceeds,
                COALESCE(SUM(cost_basis), 0) AS cost_basis,
                COALESCE(SUM(realized_profit), 0) AS realized_profit,
                COALESCE(SUM(tax_amount), 0) AS tax_amount,
                COALESCE(SUM(net_profit_after_tax), 0) AS net_profit_after_tax
            FROM investment_realized_results
            WHERE user_id = ?
            """,
            (current_user_id,),
        ).fetchone()

    summary = row_to_dict(row) or {}
    return {
        "operation_count": int(summary.get("operation_count") or 0),
        "gross_proceeds": rounded_money(summary.get("gross_proceeds")),
        "fee_amount": rounded_money(summary.get("fee_amount")),
        "net_proceeds": rounded_money(summary.get("net_proceeds")),
        "cost_basis": rounded_money(summary.get("cost_basis")),
        "realized_profit": rounded_money(summary.get("realized_profit")),
        "tax_amount": rounded_money(summary.get("tax_amount")),
        "net_profit_after_tax": rounded_money(summary.get("net_profit_after_tax")),
    }


def should_refresh_market_prices():
    value = str(request.args.get("refresh_prices", "false")).strip().lower()
    return value not in {"0", "false", "no", "off"}


def open_asset_ids(investments):
    # Vendas entram com quantidade negativa; um ativo zerado nao precisa de cotacao.
    quantities = {}
    for inv in investments:
        asset_id = inv.get("asset_id")
        if asset_id:
            key = str(asset_id)
            quantities[key] = quantities.get(key, 0) + safe_float(inv.get("quantity"))
    return {asset_id for asset_id, quantity in quantities.items() if quantity > 0.000001}


def unique_market_asset_targets(investments, open_ids=None):
    if open_ids is None:
        open_ids = open_asset_ids(investments)
    targets = {}
    for inv in investments:
        asset_id = inv.get("asset_id")
        asset_class = inv.get("asset_class")
        ticker = ticker_key(inv.get("ticker_or_name"))
        if not asset_id or asset_class not in QUOTED_ASSET_CLASSES or not ticker:
            continue
        if str(asset_id) not in open_ids:
            continue
        targets[asset_id] = {
            "asset_id": asset_id,
            "asset_class": asset_class,
            "ticker": ticker,
            "name": inv.get("ticker_or_name") or ticker,
        }
    return list(targets.values())


def update_current_prices_for_assets(current_user_id, target_assets, market_result):
    updated_assets = []
    if not target_assets:
        return updated_assets

    prices = market_result.get("prices", {})
    sources = market_result.get("source_by_ticker", {})

    with get_db() as conn:
        for asset in target_assets:
            ticker = asset["ticker"]
            source = sources.get(ticker)
            if source != "market":
                continue
            price = safe_float(prices.get(ticker), None)
            if price is None or not math.isfinite(price) or price < 0:
                continue

            record_price_quote(
                conn,
                current_user_id,
                asset["asset_id"],
                round(price, 2),
                asset_class=asset["asset_class"],
                source="market",
                metadata={"ticker": ticker, "provider": market_price_provider(ticker)},
            )
            updated_assets.append({
                **asset,
                "price": round(price, 2),
                "source": "market",
                "status": "updated",
            })

    return updated_assets


def refresh_market_prices(current_user_id, investment_id=None, *, force=False, asset_id=None, asset_class=None):
    all_investments = fetch_investments(current_user_id)
    investments_to_update = (
        fetch_investments(current_user_id, investment_id) if investment_id else all_investments
    )
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

    # A posicao aberta vem de todos os movimentos, nao so dos filtrados.
    target_assets = unique_market_asset_targets(
        investments_to_update, open_asset_ids(all_investments)
    )
    tickers = sorted({asset["ticker"] for asset in target_assets})

    market_result = get_market_prices_with_status(tickers, force=force)
    updated_assets = update_current_prices_for_assets(current_user_id, target_assets, market_result)
    failed_tickers = set(market_result.get("failed_tickers", []))
    source_by_ticker = market_result.get("source_by_ticker", {})
    cached_assets = [
        {
            **asset,
            "price": safe_float(market_result.get("prices", {}).get(asset["ticker"]), None),
            "source": source_by_ticker.get(asset["ticker"]),
            "status": "cache",
        }
        for asset in target_assets
        if source_by_ticker.get(asset["ticker"]) in {"cache", "cache_stale"}
    ]
    failed_assets = [
        {
            **asset,
            "status": "failed",
            "error": market_result.get("errors", {}).get(asset["ticker"], "Cotacao nao encontrada"),
        }
        for asset in target_assets
        if asset["ticker"] in failed_tickers
    ]
    return {
        "updated_count": len(updated_assets),
        "updated_assets": updated_assets,
        "cached_assets": cached_assets,
        "failed_assets": failed_assets,
        "target_assets": target_assets,
        "requested_tickers": len(tickers),
        "priced_tickers": len(market_result.get("prices", {})),
        "failed_tickers": sorted(failed_tickers),
    }


FIXED_INCOME_INDEXERS = {"CDI", "CDI_PLUS", "IPCA"}
BUSINESS_DAYS_PER_YEAR = 252
BCB_SERIES_CDI = 12
BCB_SERIES_IPCA = 433


def fixed_income_rate_terms(metadata):
    """Le a forma de remuneracao do titulo a partir do metadata.

    Devolve (indexador, taxa) onde indexador e "PRE", "CDI", "CDI_PLUS" ou
    "IPCA". Para CDI a taxa e o percentual do CDI (1.10 = 110%); para os
    demais e a taxa anual (0.065 = 6,5% a.a.). Lancamentos anteriores a
    escolha do indexador so tem `cdi_percentage` e seguem como % do CDI.
    Devolve (None, None) se faltar a taxa.
    """
    metadata = metadata or {}
    if metadata.get("rate_type") == "PRE":
        indexer = "PRE"
    else:
        indexer = metadata.get("indexer") or "CDI"
        if indexer not in FIXED_INCOME_INDEXERS:
            return None, None

    if indexer == "CDI":
        rate = safe_float(metadata.get("cdi_percentage"), None)
    else:
        rate = safe_float(metadata.get("annual_rate"), None)

    if rate is None or not math.isfinite(rate) or rate < 0 or (indexer == "CDI" and rate == 0):
        return None, None
    return indexer, rate


FIXED_INCOME_TYPES = {"CDB", "LCI", "LCA", "LC", "LF", "RDB", "DEBENTURE", "CRI", "CRA", "CCB"}
FIXED_INCOME_RATE_KEYS = ("fixed_income_type", "rate_type", "indexer", "cdi_percentage", "annual_rate")


def validate_fixed_income_metadata(asset_class, quantity, metadata):
    """Recusa na gravacao a remuneracao que a atualizacao nao saberia ler.

    So vale para compras de renda fixa que tragam alguma das chaves de
    remuneracao: titulo sem taxa (preco manual) e resgates seguem livres.
    Sem isso, um indexador errado so aparecia como falha em "Atualizar cotacoes".
    """
    metadata = metadata or {}
    if asset_class != "FIXED_INCOME" or quantity <= 0 or metadata.get("is_redemption"):
        return
    if not any(metadata.get(key) not in (None, "") for key in FIXED_INCOME_RATE_KEYS):
        return

    fixed_income_type = metadata.get("fixed_income_type")
    if fixed_income_type not in (None, "") and fixed_income_type not in FIXED_INCOME_TYPES:
        raise ValidationError("Tipo de titulo de renda fixa invalido.")
    rate_type = metadata.get("rate_type")
    if rate_type not in (None, "", "POS", "PRE"):
        raise ValidationError("Remuneracao deve ser pos-fixada ou pre-fixada.")
    if rate_type != "PRE":
        indexer = metadata.get("indexer") or "CDI"
        if indexer not in FIXED_INCOME_INDEXERS:
            raise ValidationError("Indexador deve ser CDI, CDI+ ou IPCA+.")
    indexer, _ = fixed_income_rate_terms(metadata)
    if indexer is None:
        if rate_type == "PRE" or (metadata.get("indexer") or "CDI") != "CDI":
            raise ValidationError("Informe a taxa anual do titulo.")
        raise ValidationError("Informe o percentual do CDI do titulo.")


def ipca_accrual_factor(ipca_monthly, purchase_date):
    """Fator do IPCA desde a compra, com o primeiro mes pro rata por dias corridos.

    `ipca_monthly` e uma lista de (data do mes, variacao decimal) como a serie
    433 do BCB. Meses ainda nao divulgados nao entram: o valor e uma estimativa
    que se completa quando o IPCA sai.
    """
    factor = 1.0
    for month_date, variation in ipca_monthly:
        if (month_date.year, month_date.month) < (purchase_date.year, purchase_date.month):
            continue
        weight = 1.0
        if (month_date.year, month_date.month) == (purchase_date.year, purchase_date.month):
            days_in_month = calendar.monthrange(purchase_date.year, purchase_date.month)[1]
            weight = (days_in_month - purchase_date.day + 1) / days_in_month
        factor *= (1 + variation) ** weight
    return factor


def fixed_income_accrual_factor(indexer, rate, cdi_daily, ipca_monthly=None, purchase_date=None):
    """Fator de correcao acumulado do titulo.

    `cdi_daily` e a serie diaria do CDI (decimal ao dia) desde a compra; alem
    de corrigir os pos-fixados em CDI, seu tamanho e a contagem de dias uteis
    usada para a parte prefixada (base 252).
    """
    business_days = len(cdi_daily)
    if indexer == "CDI":
        factor = 1.0
        for daily_rate in cdi_daily:
            factor *= 1 + (daily_rate * rate)
        return factor

    fixed_part = (1 + rate) ** (business_days / BUSINESS_DAYS_PER_YEAR)
    if indexer == "PRE":
        return fixed_part
    if indexer == "CDI_PLUS":
        factor = 1.0
        for daily_rate in cdi_daily:
            factor *= 1 + daily_rate
        return factor * fixed_part
    if indexer == "IPCA":
        return ipca_accrual_factor(ipca_monthly or [], purchase_date) * fixed_part
    raise ValueError(f"Indexador desconhecido: {indexer}")


# O SGS recusa (HTTP 406) consultas de serie diaria com janela acima de 10 anos.
BCB_MAX_WINDOW_DAYS = 3650


def fetch_bcb_window(series_code, start_date, end_date):
    """Uma consulta ao SGS; devolve a lista crua de {"data", "valor"}.

    Sem valores no periodo (compra de hoje, CDI do dia ainda nao publicado) o
    BCB responde 404 com {"erro": ...}: isso e uma serie vazia, nao uma falha.
    Qualquer outra resposta que nao seja uma lista vira erro legivel -- iterar
    o objeto de erro era o "'str' object has no attribute 'get'".
    """
    url = (
        f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series_code}/dados"
        f"?formato=json&dataInicial={start_date.strftime('%d/%m/%Y')}"
        f"&dataFinal={end_date.strftime('%d/%m/%Y')}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as response_bcb:
            body = response_bcb.read().decode()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace") if exc.fp else ""
        if exc.code == 404 and "not found" in detail.lower():
            return []
        raise RuntimeError(f"BCB respondeu {exc.code}") from exc

    rows = json.loads(body) if body.strip() else []
    if not isinstance(rows, list):
        message = rows.get("error") or rows.get("erro") if isinstance(rows, dict) else None
        if isinstance(message, dict):
            message = message.get("detail")
        raise RuntimeError(f"Resposta inesperada do BCB: {message or 'formato desconhecido'}")
    return rows


def fetch_bcb_series(series_code, start_date, end_date=None):
    """Busca uma serie do SGS do BCB; devolve [(data, valor decimal)].

    Periodos acima de 10 anos sao buscados em janelas consecutivas.
    """
    end_date = end_date or datetime.now()
    series = []
    window_start = start_date
    while window_start <= end_date:
        window_end = min(window_start + timedelta(days=BCB_MAX_WINDOW_DAYS - 1), end_date)
        for row in fetch_bcb_window(series_code, window_start, window_end):
            series.append((datetime.strptime(row["data"], "%d/%m/%Y"), safe_float(row.get("valor")) / 100))
        window_start = window_end + timedelta(days=1)
    return series


def fixed_income_asset_result(inv, **fields):
    return {
        "asset_id": inv.get("asset_id"),
        "investment_id": inv.get("id"),
        "asset_class": inv.get("asset_class"),
        "ticker": ticker_key(inv.get("ticker_or_name")),
        "name": inv.get("ticker_or_name"),
        **fields,
    }


def start_fixed_income_refresh(investments_to_update):
    """Separa os titulos a corrigir e dispara a busca no BCB em segundo plano.

    Cada serie (CDI e, se algum titulo for IPCA+, o IPCA) e buscada uma unica
    vez, a partir da compra mais antiga; cada titulo usa o trecho desde a sua
    compra. Resgates tem quantidade negativa e nao sao titulos: corrigi-los
    so gerava uma falha "Taxa do titulo nao informada".
    """
    titles = []
    failed_assets = []
    for inv in investments_to_update:
        if inv.get("asset_class") != "FIXED_INCOME" or safe_float(inv.get("quantity")) <= 0:
            continue
        meta = inv.get("metadata") or {}
        if meta.get("is_redemption"):
            continue

        indexer, rate = fixed_income_rate_terms(meta)
        if indexer is None:
            failed_assets.append(fixed_income_asset_result(
                inv, status="failed", error="Taxa do titulo nao informada"
            ))
            continue

        try:
            date_str = meta.get("purchase_date") or (inv.get("created_at") or "")[:10]
            purchase_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            print(f"Data invalida para {inv['ticker_or_name']}; pulando correcao.")
            failed_assets.append(fixed_income_asset_result(
                inv, status="failed", error="Data invalida para calculo da rentabilidade"
            ))
            continue

        titles.append((inv, indexer, rate, purchase_date))

    plan = {"titles": titles, "failed_assets": failed_assets, "cdi": None, "ipca": None}
    if titles:
        start_date = min(purchase_date for _, _, _, purchase_date in titles)
        plan["cdi"] = _index_fetch_executor.submit(fetch_bcb_series, BCB_SERIES_CDI, start_date)
        if any(indexer == "IPCA" for _, indexer, _, _ in titles):
            plan["ipca"] = _index_fetch_executor.submit(
                fetch_bcb_series, BCB_SERIES_IPCA, start_date.replace(day=1)
            )
    return plan


def finish_fixed_income_refresh(current_user_id, plan):
    updated_assets = []
    failed_assets = list(plan["failed_assets"])

    def series_result(future):
        # fetch_bcb_series tem timeout proprio; o result() nao fica preso.
        if future is None:
            return None, None
        try:
            return future.result(), None
        except Exception as exc:
            print(f"Erro ao buscar indices no BCB: {exc}")
            return None, str(exc) or "Erro ao buscar indices no BCB"

    cdi_series, cdi_error = series_result(plan["cdi"])
    ipca_series, ipca_error = series_result(plan["ipca"])

    with get_db() as conn:
        for inv, indexer, rate, purchase_date in plan["titles"]:
            error = cdi_error or (ipca_error if indexer == "IPCA" else None)
            if error:
                failed_assets.append(fixed_income_asset_result(inv, status="failed", error=error))
                continue

            try:
                cdi_daily = [value for day, value in cdi_series if day >= purchase_date]
                accumulated = fixed_income_accrual_factor(
                    indexer, rate, cdi_daily, ipca_series, purchase_date
                )
                new_price = rounded_money(safe_float(inv.get("average_price")) * accumulated)
                quote_metadata = {"provider": "bcb", "indexer": indexer}
                if indexer == "CDI":
                    quote_metadata["cdi_percentage"] = rate
                else:
                    quote_metadata["annual_rate"] = rate
                record_price_quote(
                    conn,
                    current_user_id,
                    inv["asset_id"],
                    new_price,
                    asset_class=inv["asset_class"],
                    transaction_id=inv["id"],
                    source="cdi",
                    metadata=quote_metadata,
                )
            except Exception as exc:
                print(f"Erro ao corrigir {inv['ticker_or_name']} pelo BCB: {exc}")
                failed_assets.append(fixed_income_asset_result(
                    inv, status="failed", error=str(exc) or "Erro ao corrigir o titulo"
                ))
                continue

            updated_assets.append(fixed_income_asset_result(
                inv, price=new_price, source="cdi", status="updated"
            ))

    return {
        "updated_count": len(updated_assets),
        "updated_assets": updated_assets,
        "failed_assets": failed_assets,
    }


def refresh_fixed_income_prices(current_user_id, investments_to_update):
    return finish_fixed_income_refresh(
        current_user_id, start_fixed_income_refresh(investments_to_update)
    )


def build_portfolio_snapshot(current_user_id):
    all_investments = fetch_investments(current_user_id)

    grouped_assets = {}
    for asset in all_investments:
        metadata = asset.get("metadata") or {}
        asset_id = asset.get("asset_id")
        ticker = asset["ticker_or_name"]
        normalized_ticker = ticker_key(ticker)
        asset_class = asset["asset_class"]
        qty = safe_float(asset.get("quantity"))
        avg_price_buy = safe_float(asset.get("average_price"))
        curr_price = safe_float(asset.get("current_price"), avg_price_buy)
        quote_info = quote_info_from_investment(asset)
        invested_value = qty * avg_price_buy

        if movement_affects_fixed_income_position(asset):
            group_key = str(metadata.get("related_id"))
            source_transaction_id = str(metadata.get("related_id"))
        elif asset_class == "FIXED_INCOME" and metadata.get("is_redemption"):
            continue
        else:
            group_key = str(asset["id"]) if asset_class == "FIXED_INCOME" else str(asset_id or f"{asset_class}:{normalized_ticker}")
            source_transaction_id = str(asset["id"]) if asset_class == "FIXED_INCOME" else None

        if group_key not in grouped_assets:
            grouped_assets[group_key] = {
                "id": group_key,
                "asset_id": asset_id,
                "source_transaction_id": source_transaction_id,
                "original_ticker": normalized_ticker or ticker,
                "class": asset_class,
                "total_quantity": 0,
                "total_invested": 0,
                "original_invested": 0,
                "current_price": curr_price,
                "quote": quote_info,
                "metadata": metadata,
            }

        grouped_assets[group_key]["total_invested"] += invested_value

        if not movement_affects_fixed_income_position(asset):
            grouped_assets[group_key]["total_quantity"] += qty
            if asset_class == "FIXED_INCOME" and qty > 0:
                grouped_assets[group_key]["original_invested"] += invested_value
                grouped_assets[group_key]["metadata"] = metadata
                grouped_assets[group_key]["original_ticker"] = normalized_ticker or ticker
                grouped_assets[group_key]["asset_id"] = asset_id
                grouped_assets[group_key]["source_transaction_id"] = str(asset["id"])
                grouped_assets[group_key]["quote"] = quote_info
            if asset.get("current_price") is not None:
                grouped_assets[group_key]["current_price"] = curr_price
                grouped_assets[group_key]["quote"] = quote_info

    processed_assets = []
    total_invested_all = 0
    current_total_value = 0
    current_net_value_all = 0
    distribution = {}

    for data in grouped_assets.values():
        if data["total_quantity"] <= 0:
            continue

        avg_price_calculated = (
            data["total_invested"] / data["total_quantity"]
            if data["total_quantity"] > 0 else 0
        )

        adjusted_quantity = data["total_quantity"]
        if data["class"] == "CATTLE" and data.get("metadata"):
            mortality_rate = safe_float(data["metadata"].get("mortality_rate"))
            adjusted_quantity = data["total_quantity"] * (1 - mortality_rate)

        if data["class"] == "FIXED_INCOME":
            current_value = current_price_from_position(data, data["total_invested"])
        else:
            current_value = adjusted_quantity * data["current_price"]

        net_value = fixed_income_net_value(
            data["class"],
            data.get("metadata") or {},
            data["total_invested"],
            current_value,
            datetime.now(),
        )
        taxes = max(current_value - net_value, 0)
        is_tax_free = bool((data.get("metadata") or {}).get("is_tax_free", False))
        profitability = (
            ((net_value - data["total_invested"]) / data["total_invested"]) * 100
            if data["total_invested"] > 0 else 0
        )

        total_invested_all += data["total_invested"]
        current_total_value += current_value
        current_net_value_all += net_value
        distribution[data["class"]] = distribution.get(data["class"], 0) + net_value

        display_price = current_value if data["class"] == "FIXED_INCOME" else data["current_price"]

        processed_assets.append({
            "id": data["id"],
            "asset_id": data.get("asset_id"),
            "source_transaction_id": data.get("source_transaction_id"),
            "ticker": data["original_ticker"],
            "name": data["original_ticker"],
            "class": data["class"],
            "quantity": round(data["total_quantity"], 4),
            "average_price": rounded_money(avg_price_calculated),
            "current_price": rounded_money(display_price),
            "current_value": rounded_money(current_value),
            "net_value": rounded_money(net_value),
            "taxes": rounded_money(taxes),
            "is_tax_free": is_tax_free,
            "profitability_percent": round(profitability, 2),
            "quote": data.get("quote") or {},
            "metadata": data.get("metadata") or {},
        })

    for key, value in distribution.items():
        distribution[key] = round((value / current_net_value_all) * 100, 2) if current_net_value_all > 0 else 0

    return {
        "total_invested": round(total_invested_all, 2),
        "current_balance": round(current_total_value, 2),
        "current_net_balance": round(current_net_value_all, 2),
        "portfolio_profitability": round(
            ((current_net_value_all - total_invested_all) / total_invested_all * 100),
            2,
        ) if total_invested_all > 0 else 0,
        "gross_portfolio_profitability": round(
            ((current_total_value - total_invested_all) / total_invested_all * 100),
            2,
        ) if total_invested_all > 0 else 0,
        "distribution": distribution,
        "assets": processed_assets,
    }


def replace_materialized_positions(current_user_id, assets):
    with get_db() as conn:
        conn.execute("DELETE FROM investment_positions WHERE user_id = ?", (current_user_id,))
        for asset in assets:
            asset_id = asset.get("asset_id")
            if not asset_id:
                continue

            source_transaction_id = asset.get("source_transaction_id") or None
            position_id = f"position:{source_transaction_id or asset_id}"
            conn.execute(
                """
                INSERT INTO investment_positions
                (
                    id, user_id, asset_id, source_transaction_id, quantity,
                    invested_amount, average_price, current_price, current_value,
                    net_value, taxes, profitability_percent, metadata, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                """,
                (
                    position_id,
                    current_user_id,
                    asset_id,
                    source_transaction_id,
                    safe_float(asset.get("quantity")),
                    safe_float(asset.get("average_price")) * safe_float(asset.get("quantity")),
                    safe_float(asset.get("average_price")),
                    safe_float(asset.get("current_price")),
                    safe_float(asset.get("current_value")),
                    safe_float(asset.get("net_value")),
                    safe_float(asset.get("taxes")),
                    safe_float(asset.get("profitability_percent")),
                    encode_metadata(asset.get("metadata") or {}),
                ),
            )


def refresh_materialized_positions(current_user_id):
    try:
        portfolio = build_portfolio_snapshot(current_user_id)
        replace_materialized_positions(current_user_id, portfolio["assets"])
    except Exception as exc:
        print(f"Nao foi possivel atualizar posicoes materializadas: {exc}")


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
