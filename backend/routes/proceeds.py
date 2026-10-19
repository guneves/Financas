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
from dates import clamped_date, parse_iso_date
from db import encode_metadata, get_db, new_id, parse_metadata_value, serialize_metadata_row
from export_csv import ColumnError
from money import rounded_money
from responses import export_response, read_export_options
from services.fixed_income import fixed_income_is_tax_free
from services.investments import ensure_asset_owner, investment_metadata_dict
from services.proceeds_sync import sync_proceeds
from services.realized_results import days_between_dates, fixed_income_tax_rate_for_days
from services.proceeds import (
    ALLOWED_PROCEEDS_TYPES,
    FIXED_INCOME_EVENT_TYPES,
    INTEREST_TYPE,
    asset_movement_rows,
    build_investment_proceeds_summary,
    default_tax_for_proceed,
    fetch_investment_proceed_by_id,
    fetch_investment_proceeds,
    investment_position_at_date,
    serialize_investment_proceed,
    serialized_proceeds,
    trailing_net_by_asset,
)
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

# "Repetir" de um provento novo: um pagamento a cada N meses, `count` ao todo
# (o primeiro incluido) — os cupons de um titulo ate o vencimento.
REPEAT_EVERY_MONTHS = {1, 2, 3, 6, 12}
REPEAT_MAX_COUNT = 120


def interest_tax_rate(conn, current_user_id, asset_id, payment_date):
    """Aliquota do IR retido no cupom de juros de renda fixa.

    Tabela regressiva pelos dias entre a aplicacao e o pagamento (Lei
    11.033/2004, art. 1o), a mesma do resgate; zero no titulo isento (LCI, LCA,
    CRI, CRA, debenture incentivada). A aplicacao e a primeira compra do ativo
    ate o pagamento. Ativo que nao e renda fixa, ou sem compra, nao presume
    imposto: o dono informa.
    """
    asset = conn.execute(
        "SELECT asset_class FROM assets WHERE id = ? AND user_id = ?",
        (asset_id, current_user_id),
    ).fetchone()
    if not asset or asset["asset_class"] != "FIXED_INCOME":
        return 0.0
    for row in asset_movement_rows(conn, current_user_id, asset_id, payment_date):
        movement = serialize_metadata_row(row)
        if movement.get("movement_type") != "BUY" or safe_float(movement.get("quantity")) <= 0:
            continue
        if fixed_income_is_tax_free(movement.get("metadata")):
            return 0.0
        days = days_between_dates(movement.get("transaction_date"), payment_date)
        return fixed_income_tax_rate_for_days(days)
    return 0.0


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
    payment_date = require_date(merged, "payment_date", "Data de pagamento")
    if proceeds_type in FIXED_INCOME_EVENT_TYPES and merged.get("record_date") in (None, ""):
        merged["record_date"] = payment_date
    record_date = require_date(merged, "record_date", "Data com")
    ex_date = optional_date(merged, "ex_date", "Data ex")

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
    # O IR do cupom muda com a data de pagamento (tabela regressiva).
    tax_inputs = ("proceeds_type", "amount_per_unit", "eligible_quantity", "gross_amount")
    if proceeds_type == INTEREST_TYPE:
        tax_inputs += ("payment_date", "asset_id")
    should_recalculate_tax = (
        not tax_was_provided
        and (
            existing.get("id") is None
            or any(key in payload for key in tax_inputs)
        )
    )
    if tax_amount is None or should_recalculate_tax:
        if proceeds_type == INTEREST_TYPE:
            tax_amount = gross_amount * interest_tax_rate(conn, current_user_id, asset_id, payment_date)
        else:
            tax_amount = default_tax_for_proceed(
                proceeds_type,
                gross_amount,
                record_date,
                (parse_metadata_value(merged.get("metadata")) or {}).get("kind"),
            )

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


def shifted_date(value, months):
    """A data `months` meses depois, no mesmo dia (ou no ultimo do mes curto)."""
    parsed = parse_iso_date(value) if value not in (None, "") else None
    if not parsed or not months:
        return value
    index = parsed.year * 12 + parsed.month - 1 + months
    return clamped_date(index // 12, index % 12 + 1, parsed.day).isoformat()


def parse_repeat(payload):
    """`repeat: {every_months, count}` de um POST, ou None (um pagamento so)."""
    repeat = payload.get("repeat")
    if repeat in (None, "", False):
        return None
    if not isinstance(repeat, dict):
        raise ValidationError("Repeticao invalida.")
    try:
        every_months = int(repeat.get("every_months"))
        count = int(repeat.get("count"))
    except (TypeError, ValueError):
        raise ValidationError("Informe a frequencia e o numero de pagamentos.")
    if every_months not in REPEAT_EVERY_MONTHS:
        raise ValidationError("Frequencia invalida: a cada 1, 2, 3, 6 ou 12 meses.")
    if count < 1 or count > REPEAT_MAX_COUNT:
        raise ValidationError(f"Numero de pagamentos deve ficar entre 1 e {REPEAT_MAX_COUNT}.")
    return every_months, count


def repeated_payloads(payload, repeat):
    """Um payload por pagamento; as datas andam juntas, o resto e igual."""
    if not repeat:
        return [payload]
    every_months, count = repeat
    payloads = []
    for index in range(count):
        item = dict(payload)
        for key in ("declared_date", "record_date", "ex_date", "payment_date"):
            if key in item:
                item[key] = shifted_date(item[key], every_months * index)
        payloads.append(item)
    return payloads


def insert_proceed(conn, current_user_id, proceed):
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
    return proceed_id


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

    # Com `repeat`, todos os pagamentos sao gravados juntos ou nenhum, e a
    # resposta e a lista; sem ele, o provento sozinho, como sempre.
    try:
        repeat = parse_repeat(payload)
        with get_db() as conn:
            items = []
            for item_payload in repeated_payloads(payload, repeat):
                proceed = normalize_proceed_payload(conn, current_user_id, item_payload)
                proceed_id = insert_proceed(conn, current_user_id, proceed)
                row = fetch_investment_proceed_by_id(conn, current_user_id, proceed_id)
                items.append(serialize_investment_proceed(row, conn, current_user_id))
    except ValidationError as exc:
        return validation_error(str(exc))
    except sqlite3.IntegrityError:
        return jsonify({"error": "Nao foi possivel registrar o provento."}), 400

    if repeat:
        return jsonify(items), 201
    item = items[0]
    return jsonify(item), 201


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
