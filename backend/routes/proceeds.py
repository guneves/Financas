"""Proventos: dividendos, JCP e amortizacoes recebidos (ou a receber).

O imposto padrao do JCP e o da fonte (`default_tax_for_proceed()` em
services/proceeds.py: 15%, ou 17,5% com data com desde 2026); dividendo e
amortizacao nao tem. `investment_position_at_date()` da a quantidade elegivel
na data com, que vezes o valor por cota da o bruto. A leitura (lista, status,
YOC e os resumos) mora em `services/proceeds.py`; aqui fica a escrita.
"""

from datetime import datetime, timedelta
import sqlite3

from flask import Blueprint, jsonify, request

from auth import token_required
from dates import clamped_date, local_now, parse_iso_date
from db import encode_metadata, get_db, new_id, parse_metadata_value, serialize_metadata_row
from export_csv import ColumnError
from money import rounded_money
from responses import export_response, read_export_options
from services.investments import ensure_asset_owner, investment_metadata_dict
from services.manual_entries import require_manual_investment_cash
from services.open_finance_investments import OP_KEY_METADATA, UNKNOWN_HELD_MESSAGE, complete_held, held_operation
from services.proceeds_cash import proceed_cash_account_id
from services.proceeds_sync import sync_proceeds
from services.proceeds import (
    ALLOWED_PROCEEDS_TYPES,
    FIXED_INCOME_EVENT_TYPES,
    INTEREST_TYPE,
    build_investment_proceeds_summary,
    default_tax_for_proceed,
    fetch_investment_proceed_by_id,
    interest_tax_rate,
    investment_position_at_date,
    serialize_investment_proceed,
    serialized_proceeds,
    trailing_net_by_asset,
)
from validators import (
    MAX_YEAR,
    MIN_YEAR,
    ValidationError,
    optional_client_id,
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
from services.proceeds_payload import (  # noqa: F401  (as regras desta rota; os nomes continuam valendo aqui)
    PROCEEDS_TYPE_CLASS_MESSAGES,
    REPEAT_EVERY_MONTHS,
    REPEAT_MAX_COUNT,
    ensure_proceeds_type_fits_asset,
    insert_proceed,
    normalize_proceed_payload,
    parse_investment_proceeds_filters,
    parse_repeat,
    proceeds_by_client_id,
    repeated_payloads,
    shifted_date,
)

bp = Blueprint("proceeds", __name__)

def created_proceeds_response(payload, items, status):
    """Com `repeat`, a lista; sem ele, o provento sozinho, como sempre."""
    if payload.get("repeat") not in (None, "", False):
        return jsonify(items), status
    return jsonify(items[0]), status


@bp.route("/api/investment-proceeds", methods=["GET", "POST"])
@token_required
def investment_proceeds(current_user_id):
    if request.method == "GET":
        try:
            filters = parse_investment_proceeds_filters(request.args)
        except ValidationError as exc:
            return validation_error(str(exc))

        with get_db() as conn:
            items = serialized_proceeds(conn, current_user_id, filters)
        return jsonify(items), 200

    payload = parse_json_body()
    if not isinstance(payload, dict):
        return validation_error("Provento deve ser um objeto valido.")

    # Segunda entrega do mesmo envio (042): devolve o que a primeira gravou.
    try:
        client_id = optional_client_id(payload)
    except ValidationError as exc:
        return validation_error(str(exc))
    if client_id:
        with get_db() as conn:
            existing = proceeds_by_client_id(conn, current_user_id, client_id)
        if existing:
            return created_proceeds_response(payload, existing, 200)

    # Com `repeat`, todos os pagamentos sao gravados juntos ou nenhum, e a
    # resposta e a lista; sem ele, o provento sozinho, como sempre.
    try:
        repeat = parse_repeat(payload)
        with get_db() as conn:
            items = []
            op_key = None
            for part, item_payload in enumerate(repeated_payloads(payload, repeat)):
                proceed = normalize_proceed_payload(conn, current_user_id, item_payload)
                # O "Lancar" de um cupom que espera (Fase 3): passa pela Corretora da Pluggy.
                if OP_KEY_METADATA in proceed["metadata"]:
                    op_key = proceed["metadata"].pop(OP_KEY_METADATA)
                    if not held_operation(conn, current_user_id, op_key):
                        raise ValidationError(UNKNOWN_HELD_MESSAGE)
                    proceed["metadata"]["open_finance_operation"] = op_key
                require_manual_investment_cash(
                    conn, current_user_id, proceed_cash_account_id(conn, current_user_id, proceed["payment_date"]),
                    completes_held=bool(op_key),
                )
                proceed_id = insert_proceed(conn, current_user_id, proceed, client_id, part)
                if op_key and part == 0:
                    complete_held(conn, current_user_id, op_key, proceed_id=proceed_id)
                row = fetch_investment_proceed_by_id(conn, current_user_id, proceed_id)
                items.append(serialize_investment_proceed(row, conn, current_user_id))
    except ValidationError as exc:
        return validation_error(str(exc))
    except sqlite3.IntegrityError:
        # Entregas simultaneas do mesmo envio: a outra ja gravou.
        if client_id:
            with get_db() as conn:
                existing = proceeds_by_client_id(conn, current_user_id, client_id)
            if existing:
                return created_proceeds_response(payload, existing, 200)
        return jsonify({"error": "Nao foi possivel registrar o provento."}), 400

    return created_proceeds_response(payload, items, 201)


@bp.route("/api/investment-proceeds/sync", methods=["POST"])
@token_required
def investment_proceeds_sync(current_user_id):
    """Proventos automaticos: posicao na data com x valor da StatusInvest.

    `{"force": true}` ignora o cache do historico. Falha na fonte nao e erro
    HTTP: a resposta diz o status e os tickers que ficaram de fora.
    """
    payload = parse_json_body()
    force = bool(isinstance(payload, dict) and payload.get("force"))
    return jsonify(sync_proceeds(current_user_id, force=force)), 200


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
        items = serialized_proceeds(conn, current_user_id, filters)
    return export_response(fmt, columns, items, basename="proventos", sheet_name="Proventos")


@bp.route("/api/investment-proceeds/summary", methods=["GET"])
@token_required
def investment_proceeds_summary(current_user_id):
    try:
        filters = parse_investment_proceeds_filters(request.args)
    except ValidationError as exc:
        return validation_error(str(exc))

    with get_db() as conn:
        items = serialized_proceeds(conn, current_user_id, filters)
        trailing_net = trailing_net_by_asset(conn, current_user_id, filters)
    return jsonify(build_investment_proceeds_summary(items, trailing_net)), 200


@bp.route("/api/investment-proceeds/calendar", methods=["GET"])
@token_required
def investment_proceeds_calendar(current_user_id):
    try:
        filters = parse_investment_proceeds_filters(request.args)
    except ValidationError as exc:
        return validation_error(str(exc))

    today = local_now().strftime("%Y-%m-%d")
    if not filters.get("date_from"):
        filters["date_from"] = today
    if not filters.get("date_to"):
        filters["date_to"] = (local_now() + timedelta(days=180)).strftime("%Y-%m-%d")
    filters["ascending"] = True

    with get_db() as conn:
        items = serialized_proceeds(conn, current_user_id, filters)
    return jsonify(items), 200


@bp.route("/api/investment-proceeds/<proceed_id>", methods=["PATCH", "DELETE"])
@token_required
def investment_proceed_detail(current_user_id, proceed_id):
    with get_db() as conn:
        existing_row = fetch_investment_proceed_by_id(conn, current_user_id, proceed_id)
        if not existing_row:
            return jsonify({"error": "Provento nao encontrado."}), 404

        if request.method == "DELETE":
            # Automatico excluido nao volta na proxima sincronizacao.
            if existing_row["sync_key"]:
                conn.execute(
                    "INSERT OR IGNORE INTO proceeds_sync_dismissed (user_id, sync_key) VALUES (?, ?)",
                    (current_user_id, existing_row["sync_key"]),
                )
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
                    sync_locked = CASE WHEN sync_key IS NULL THEN 0 ELSE 1 END,
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
