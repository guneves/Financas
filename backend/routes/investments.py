"""Investimentos: movimentacoes, carteira, cotacoes, historico e exportacao.

As regras moram em services/ (investments, realized_results, portfolio, prices,
fixed_income); aqui ficam as rotas. Toda escrita em movimentacao recalcula o
resultado realizado e as posicoes materializadas antes de responder.

`load_history_inputs()` (historico e rentabilidade) le `yf` para decidir se
busca historico — os testes trocam `yf` aqui e em services/prices.py, e
`get_monthly_history` aqui.
"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime
import sqlite3

from flask import Blueprint, jsonify, request

from asset_classes import ALLOWED_ASSET_CLASSES, QUOTED_ASSET_CLASSES, parse_asset_class_filter
from auth import token_required
from config import PRICE_FETCH_TIMEOUT_SECONDS
from dates import parse_iso_date, subtract_months
from db import encode_metadata, get_db, new_id, parse_metadata_value, serialize_metadata_row
from export_csv import ColumnError
from money import rounded_money
import export_csv
import export_xlsx
from responses import XLSX_MIMETYPE, download_response
from responses import export_response, read_export_options
from services.corporate_actions import (
    create_corporate_action,
    delete_corporate_action,
    ensure_outside_corporate_actions,
    is_bonus_movement,
    list_corporate_actions,
)
from services.fx import (
    BASE_CURRENCY,
    SUPPORTED_CURRENCIES,
    FxUnavailable,
    monthly_rates,
    normalize_currency,
    rate_on,
)
from services.tax_report import build_tax_report, exemption_meter
from services.fixed_income import (
    index_history,
    finish_fixed_income_refresh,
    start_fixed_income_refresh,
    validate_fixed_income_metadata,
)
from services.investments import (
    CASH_ACCOUNT_KEY,
    delete_investment_cash_transaction,
    fetch_investment_rows,
    fetch_investments,
    fetch_position_quantity,
    get_or_create_asset,
    investment_cash_account_id,
    investment_cash_receipt_count,
    investment_fee_amount,
    investment_gross_amount,
    investment_metadata_dict,
    investment_movement_type,
    investment_transaction_date,
    resolve_catalog_ticker,
    resolve_investment_cash_account,
    serialize_investment,
    sync_investment_cash_transaction,
    validate_asset_transaction_backing,
    validate_investment_movement,
    with_investment_cash_account,
)
from services.portfolio import (
    build_portfolio_evolution,
    build_portfolio_snapshot,
    refresh_market_prices,
    refresh_materialized_positions,
    replace_materialized_positions,
)
from services.prices import (
    _price_fetch_executor,
    get_monthly_history,
    quote_timestamp,
    record_price_quote,
    ticker_key,
    yf,
)
from services.benchmarks import load_benchmarks
from services.realized_results import realized_results_summary, refresh_realized_results
from services.returns import build_investment_returns, returns_evaluated_months
from validators import (
    ValidationError,
    normalize_month,
    parse_json_body,
    parse_number,
    parse_optional_number,
    require_choice,
    require_string,
    safe_float,
    validation_error,
)
from applog import get_logger

logger = get_logger(__name__)

bp = Blueprint("investments", __name__)

# CDI/IPCA da evolucao: fora do executor do yfinance, que o historico ja ocupa.
_index_history_executor = ThreadPoolExecutor(max_workers=1)

# Moeda estrangeira: acoes/ETFs de fora e "outros" (cripto, conta no
# exterior). Renda fixa e FII sao em reais.
FOREIGN_CURRENCY_CLASSES = {"STOCKS", "OTHER"}


def read_movement_currency(item, asset_class):
    currency = normalize_currency(item.get("currency"))
    if currency not in SUPPORTED_CURRENCIES:
        raise ValidationError(f"Moeda nao suportada: {currency}. Use BRL, USD, EUR ou GBP.")
    if currency != BASE_CURRENCY and asset_class not in FOREIGN_CURRENCY_CLASSES:
        raise ValidationError("So acoes do exterior e 'outros' podem ser em moeda estrangeira.")
    return currency


def with_fx_rate(conn, current_user_id, currency, metadata):
    """Guarda o cambio da operacao: o informado (o da corretora) ou a PTAX da data."""
    informed = metadata.get("fx_rate")
    if informed not in (None, ""):
        rate = parse_number(metadata, "fx_rate", "Cambio", minimum=0, allow_zero=False)
        return {**metadata, "fx_rate": rate, "fx_source": "informado"}
    try:
        rate = rate_on(conn, current_user_id, currency, investment_transaction_date(metadata))
    except FxUnavailable as exc:
        raise ValidationError(f"{exc} Informe o cambio da operacao.")
    return {**metadata, "fx_rate": rate, "fx_source": "ptax"}


BONUS_LOCKED_MESSAGE = (
    "Esta operacao e a bonificacao de um evento corporativo; "
    "para mudar ou tirar, exclua o evento em Operacoes."
)

CASH_RECEIPT_LOCKED_MESSAGE = (
    "O lancamento desta operacao no extrato tem comprovante. "
    "Remova o comprovante no Extrato antes de tirar a operacao de la."
)

CASH_WITHOUT_AMOUNT_MESSAGE = (
    "Esta operacao nao tem valor para lancar no extrato. "
    "Corrija o valor ou desmarque 'Lancar no extrato'."
)


@bp.route("/api/investments/portfolio/export", methods=["GET"])
@token_required
def export_portfolio(current_user_id):
    """Carteira atual em CSV ou .xlsx, sem forcar atualizacao de cotacao."""
    try:
        fmt, columns = read_export_options(request.args, "portfolio")
    except ColumnError as exc:
        return validation_error(str(exc))
    try:
        portfolio = build_portfolio_snapshot(current_user_id)
    except Exception as exc:
        logger.exception(f"Erro ao exportar a carteira: {exc}")
        return jsonify({"error": "Nao foi possivel exportar a carteira."}), 500

    return export_response(
        fmt, columns, portfolio.get("assets") or [], basename="carteira", sheet_name="Carteira",
    )


def movement_export_item(investment):
    """Uma operacao como a tela Operacoes mostra: preco de venda/resgate na
    venda, bruto = quantidade x preco, custos, e o resultado realizado (FIFO)."""
    metadata = investment.get("metadata") or {}
    movement_type = investment_movement_type(investment.get("quantity"), metadata)
    quantity = abs(float(investment.get("quantity") or 0))
    if metadata.get("is_redemption"):
        unit_price = float(investment.get("current_price") or 0)
    elif movement_type == "SELL" and metadata.get("sale_price"):
        unit_price = float(metadata.get("sale_price") or 0)
    else:
        unit_price = float(investment.get("average_price") or 0)
    realized_fee = investment.get("realized_fee_amount")
    return {
        "date": investment_transaction_date(metadata, investment.get("created_at")),
        "movement_type": movement_type,
        "ticker": investment.get("ticker_or_name"),
        "asset_class": investment.get("asset_class"),
        "quantity": quantity,
        "unit_price": unit_price,
        "gross_amount": rounded_money(investment_gross_amount(quantity, unit_price)),
        "fees": realized_fee if realized_fee is not None else investment_fee_amount(metadata),
        "realized_cost_basis": investment.get("realized_cost_basis"),
        "realized_profit": investment.get("realized_profit"),
        "realized_tax_amount": investment.get("realized_tax_amount"),
        "realized_net_profit_after_tax": investment.get("realized_net_profit_after_tax"),
    }


@bp.route("/api/investments/export", methods=["GET"])
@token_required
def export_movements(current_user_id):
    """Operacoes (compras, vendas, aportes, resgates) em CSV ou .xlsx, mais
    recentes primeiro, com o resultado realizado de cada venda."""
    try:
        fmt, columns = read_export_options(request.args, "movements")
    except ColumnError as exc:
        return validation_error(str(exc))
    refresh_realized_results(current_user_id)
    with get_db() as conn:
        rows = fetch_investment_rows(conn, current_user_id, order_by="it.created_at", direction="DESC")
    items = [movement_export_item(serialize_investment(row)) for row in rows]
    items.sort(key=lambda item: item["date"] or "", reverse=True)
    return export_response(fmt, columns, items, basename="operacoes", sheet_name="Operações")


@bp.route("/api/assets", methods=["GET"])
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


@bp.route("/api/investment-transactions", methods=["GET"])
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


@bp.route("/api/investment-realized-results", methods=["GET"])
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


@bp.route("/api/investment-positions", methods=["GET"])
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


@bp.route("/api/investments", methods=["GET", "POST"])
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
                currency = read_movement_currency(item, asset_class)
                if currency == BASE_CURRENCY:
                    ticker_or_name = resolve_catalog_ticker(
                        conn,
                        current_user_id,
                        asset_class,
                        ticker_or_name,
                        quantity,
                    )
                else:
                    # Fora do catalogo da B3; o cambio da data fica na operacao.
                    ticker_or_name = ticker_key(ticker_or_name)
                    metadata_dict = with_fx_rate(conn, current_user_id, currency, metadata_dict)
                    metadata = metadata_dict
                # So vai ao extrato a operacao que pede (metadata.cash_account_id):
                # a conta e validada aqui, antes de qualquer escrita.
                if CASH_ACCOUNT_KEY in metadata_dict:
                    metadata_dict = with_investment_cash_account(
                        metadata_dict,
                        resolve_investment_cash_account(conn, current_user_id, metadata_dict),
                    )
                    metadata = metadata_dict
                validate_investment_movement(
                    conn,
                    current_user_id,
                    asset_class,
                    ticker_or_name,
                    quantity,
                )

                item_id = new_id()
                asset_id = get_or_create_asset(conn, current_user_id, asset_class, ticker_or_name, currency)
                affected_asset_ids.add(asset_id)
                transaction_date = investment_transaction_date(metadata_dict)
                ensure_outside_corporate_actions(conn, current_user_id, asset_id, transaction_date)
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
                movement = serialize_investment(row)
                in_statement = sync_investment_cash_transaction(conn, current_user_id, movement)
                if investment_cash_account_id(movement.get("metadata")) and not in_statement:
                    raise ValidationError(CASH_WITHOUT_AMOUNT_MESSAGE)
                rows.append(row)
    except ValidationError as exc:
        return validation_error(str(exc))
    except sqlite3.IntegrityError:
        return jsonify({"error": "Nao foi possivel criar o investimento."}), 400

    refresh_realized_results(current_user_id)
    refresh_materialized_positions(current_user_id)
    return jsonify([serialize_investment(row) for row in rows]), 201


@bp.route("/api/investments/<investment_id>", methods=["PATCH", "DELETE"])
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
            if existing_item and is_bonus_movement(existing_item.get("metadata")):
                return validation_error(BONUS_LOCKED_MESSAGE, 409)
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
        if is_bonus_movement(existing.get("metadata")):
            return validation_error(BONUS_LOCKED_MESSAGE, 409)
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
        # O ajuste de um desdobramento mora no metadata; um formulario que
        # manda o metadata inteiro de volta nao pode apaga-lo.
        # O mesmo vale para o cambio travado de uma operacao em moeda
        # estrangeira: sem ele, o caixa recalcularia pela PTAX da data.
        existing_metadata = existing.get("metadata") or {}
        for kept_key in ("corporate_adjustments", "fx_rate", "fx_source"):
            if existing_metadata.get(kept_key) not in (None, "") and kept_key not in metadata:
                metadata = {**metadata, kept_key: existing_metadata[kept_key]}
        # A conta do extrato tambem fica quando o metadata vem sem a chave — um
        # formulario que nao a conhece nao pode apagar um lancamento. Tirar a
        # operacao do extrato e mandar a chave vazia (null), de proposito.
        previous_cash_account_id = investment_cash_account_id(existing_metadata)
        requested_cash = (
            metadata
            if "metadata" in payload and CASH_ACCOUNT_KEY in metadata
            else {CASH_ACCOUNT_KEY: previous_cash_account_id}
        )
        try:
            cash_account_id = resolve_investment_cash_account(
                conn,
                current_user_id,
                requested_cash,
                previous_account_id=previous_cash_account_id,
            )
        except ValidationError as exc:
            return validation_error(str(exc))
        if not cash_account_id and investment_cash_receipt_count(conn, current_user_id, investment_id):
            # Sair do extrato apaga o lancamento, e o comprovante iria junto.
            return validation_error(CASH_RECEIPT_LOCKED_MESSAGE, 409)
        metadata = with_investment_cash_account(metadata, cash_account_id)
        try:
            validate_fixed_income_metadata(asset_class, quantity, metadata)
        except ValidationError as exc:
            return validation_error(str(exc))
        transaction_date = investment_transaction_date(metadata, existing.get("created_at"))
        try:
            ensure_outside_corporate_actions(
                conn, current_user_id, existing["asset_id"], transaction_date,
                previous_date=existing.get("transaction_date"),
            )
        except ValidationError as exc:
            return validation_error(str(exc), 409)

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
        in_statement = sync_investment_cash_transaction(
            conn,
            current_user_id,
            serialize_investment(row),
        )
        if cash_account_id and not in_statement:
            # Pede o extrato mas ficou sem valor a lancar (preco zerado, custos
            # maiores que a venda): a edicao inteira e desfeita, senao o
            # lancamento sumiria — com os comprovantes — sem ninguem pedir.
            conn.rollback()
            return validation_error(CASH_WITHOUT_AMOUNT_MESSAGE)
    if not row:
        return jsonify({"error": "Investimento nao encontrado."}), 404
    refresh_realized_results(current_user_id)
    refresh_materialized_positions(current_user_id)
    return jsonify(serialize_investment(row)), 200


@bp.route("/api/investments/by-asset/<asset_id>", methods=["DELETE"])
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


@bp.route("/api/investments/by-ticker/<path:ticker>", methods=["DELETE"])
@token_required
def delete_investments_by_ticker(current_user_id, ticker):
    return validation_error(
        "Operacao por ticker desativada por seguranca. Use asset_id e asset_class para excluir uma posicao.",
        410,
    )


@bp.route("/api/investments/price-by-asset/<asset_id>", methods=["PATCH"])
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


@bp.route("/api/investments/price-by-ticker", methods=["PATCH"])
@token_required
def update_price_by_ticker(current_user_id):
    return validation_error(
        "Atualizacao por ticker desativada por seguranca. Use asset_id e asset_class para atualizar cotacao.",
        410,
    )


def should_refresh_market_prices():
    value = str(request.args.get("refresh_prices", "false")).strip().lower()
    return value not in {"0", "false", "no", "off"}


@bp.route("/api/investments/portfolio", methods=["GET"])
@token_required
def get_portfolio(current_user_id):
    try:
        if should_refresh_market_prices():
            try:
                refresh_market_prices(current_user_id, force=False)
            except Exception as exc:
                logger.exception(f"Erro ao atualizar cotacoes antes da carteira: {exc}")

        refresh_realized_results(current_user_id)
        portfolio = build_portfolio_snapshot(current_user_id)
        portfolio["realized_result"] = realized_results_summary(current_user_id)
        replace_materialized_positions(current_user_id, portfolio["assets"])
        return jsonify(portfolio), 200
    except Exception as exc:
        logger.exception(f"Erro no calculo: {exc}")
        return jsonify({"error": "Nao foi possivel calcular a carteira."}), 500


@bp.route("/api/investments/update-prices", methods=["POST"])
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
            logger.warning(f"Nao foi possivel atualizar posicoes materializadas: {exc}")
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
        logger.exception(f"ERRO FATAL NA ROTA UPDATE-PRICES: {exc}")
        return jsonify({"error": "Nao foi possivel atualizar os precos."}), 500


def read_months_arg(args, default=12):
    """`?months=` do historico e da rentabilidade: de 1 a 60."""
    try:
        months_back = int(args.get("months", default))
    except (TypeError, ValueError):
        months_back = default
    return max(1, min(months_back, 60))


def load_history_inputs(current_user_id, months_back, asset_class_filter):
    """O que a evolucao e a rentabilidade avaliam: as movimentacoes (em reais,
    filtradas pela classe), o fechamento mensal dos cotados em reais e as series
    CDI/IPCA da renda fixa. Cobre os ultimos `months_back` meses."""
    investments_data = fetch_investments(current_user_id)
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
            logger.warning("Tempo limite ao buscar historico no yfinance.")
            historical_prices = {ticker: {} for ticker in unique_tickers}
        except Exception as exc:
            logger.exception(f"Erro ao buscar historico no yfinance: {exc}")
            historical_prices = {ticker: {} for ticker in unique_tickers}

    # Historico de ativo em moeda estrangeira vem na moeda dele: cada mes
    # vira reais pelo cambio do fim daquele mes.
    foreign_currency = {
        ticker_key(asset.get("ticker_or_name")): asset.get("native_currency")
        for asset in quoted_assets
        if asset.get("native_currency") and asset.get("native_currency") != BASE_CURRENCY
    }
    if foreign_currency:
        with get_db() as conn:
            for ticker, currency in foreign_currency.items():
                months = historical_prices.get(ticker) or {}
                rates = monthly_rates(conn, current_user_id, currency, sorted(months))
                historical_prices[ticker] = {
                    key: price * rates[key] for key, price in months.items() if rates.get(key)
                }

    # Renda fixa nos meses passados: CDI/IPCA desde a compra mais antiga.
    index_series = None
    fixed_titles = [
        inv for inv in filtered_investments
        if inv.get("asset_class") == "FIXED_INCOME" and safe_float(inv.get("quantity")) > 0
        and not (inv.get("metadata") or {}).get("is_redemption")
    ]
    if fixed_titles:
        first_purchase = min(parse_iso_date(investment_transaction_date(inv.get("metadata") or {}, inv.get("created_at"))) for inv in fixed_titles)
        need_ipca = any((inv.get("metadata") or {}).get("indexer") == "IPCA" for inv in fixed_titles)
        index_series = fetch_index_history(first_purchase, need_ipca)

    return filtered_investments, historical_prices, index_series


def fetch_index_history(start_date, need_ipca):
    """CDI (e IPCA) do BCB com tempo limite; None se nao vier."""
    future = _index_history_executor.submit(index_history, start_date, need_ipca)
    try:
        return future.result(timeout=PRICE_FETCH_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        logger.warning("Tempo limite ao buscar CDI/IPCA para a evolucao.")
    except Exception as exc:
        logger.warning(f"CDI/IPCA indisponivel para a evolucao: {exc}")
    return None


@bp.route("/api/investments/history", methods=["GET"])
@token_required
def get_historical_portfolio(current_user_id):
    try:
        months_back = read_months_arg(request.args)
        asset_class_filter = parse_asset_class_filter(request.args.get("asset_class"))
        filtered_investments, historical_prices, index_series = load_history_inputs(
            current_user_id, months_back, asset_class_filter,
        )

        evolution = build_portfolio_evolution(
            filtered_investments,
            historical_prices,
            months_back,
            index_series,
        )

        return jsonify({
            "historical_prices": historical_prices,
            "evolution": evolution,
        }), 200
    except Exception as exc:
        logger.exception(f"Erro no historico de investimentos: {exc}")
        return jsonify({"error": "Nao foi possivel carregar o historico de investimentos."}), 500


@bp.route("/api/investments/returns", methods=["GET"])
@token_required
def get_investment_returns(current_user_id):
    """Rentabilidade ponderada no tempo (TWR mensal, Dietz modificado)."""
    try:
        months_back = read_months_arg(request.args)
        asset_class_filter = parse_asset_class_filter(request.args.get("asset_class"))
        # Um mes a mais (o valor inicial do primeiro) e, no minimo, o ano
        # corrente inteiro, para o acumulado no ano.
        evaluated_months = returns_evaluated_months(months_back)
        filtered_investments, historical_prices, index_series = load_history_inputs(
            current_user_id, evaluated_months, asset_class_filter,
        )
        first_month = subtract_months(datetime.now().replace(day=1), evaluated_months - 1)
        cdi_series = fetch_index_history(
            datetime(first_month.year, first_month.month, 1), False,
        )
        # IPCA, Ibovespa, IFIX e IDIV: cada um falha sozinho, sem derrubar a resposta.
        try:
            benchmarks = load_benchmarks(current_user_id, first_month)
        except Exception as exc:
            logger.exception(f"Indices de comparacao indisponiveis: {exc}")
            benchmarks = None
        result = build_investment_returns(
            current_user_id,
            filtered_investments,
            historical_prices,
            months_back,
            index_series=index_series,
            cdi_series=(cdi_series or {}).get("cdi"),
            benchmarks=benchmarks,
            asset_class=asset_class_filter,
        )
        return jsonify(result), 200
    except Exception as exc:
        logger.exception(f"Erro na rentabilidade dos investimentos: {exc}")
        return jsonify({"error": "Nao foi possivel calcular a rentabilidade."}), 500


@bp.route("/api/corporate-actions", methods=["GET", "POST"])
@token_required
def corporate_actions(current_user_id):
    """Desdobramentos, grupamentos e bonificacoes (services/corporate_actions.py)."""
    if request.method == "GET":
        with get_db() as conn:
            items = list_corporate_actions(conn, current_user_id, request.args.get("asset_id"))
        return jsonify(items), 200

    payload = parse_json_body()
    try:
        with get_db() as conn:
            item = create_corporate_action(conn, current_user_id, payload)
    except ValidationError as exc:
        return validation_error(str(exc))
    # A cotacao do proprio dia ex pode ser de antes ou de depois do evento;
    # busca uma nova no mercado. Sem rede, o cliente avisa para atualizar.
    try:
        refreshed = refresh_market_prices(current_user_id, force=True, asset_id=item["asset_id"])
        item["price_refreshed"] = bool(refreshed.get("updated_count"))
    except Exception as exc:  # cotacao e melhor esforco aqui
        logger.warning(f"Cotacao nao atualizada depois do evento corporativo: {exc}")
        item["price_refreshed"] = False
    refresh_realized_results(current_user_id)
    refresh_materialized_positions(current_user_id)
    return jsonify(item), 201


@bp.route("/api/corporate-actions/<action_id>", methods=["DELETE"])
@token_required
def delete_corporate_action_route(current_user_id, action_id):
    """Desfaz o evento: so o ultimo do ativo e sem operacao depois da data ex."""
    try:
        with get_db() as conn:
            delete_corporate_action(conn, current_user_id, action_id)
    except LookupError as exc:
        return jsonify({"deleted": False, "error": str(exc)}), 404
    except ValidationError as exc:
        return validation_error(str(exc), 409)
    refresh_realized_results(current_user_id)
    refresh_materialized_positions(current_user_id)
    return jsonify({"deleted": True}), 200


def read_report_year(args):
    try:
        year = int(args.get("year") or datetime.now().year - 1)
    except (TypeError, ValueError):
        raise ValidationError("Ano invalido.")
    if year < 2000 or year > datetime.now().year:
        raise ValidationError("Ano fora do intervalo.")
    return year


@bp.route("/api/tax-report", methods=["GET"])
@token_required
def tax_report(current_user_id):
    """Relatorio anual de IR (services/tax_report.py); padrao: o ano passado."""
    try:
        year = read_report_year(request.args)
    except ValidationError as exc:
        return validation_error(str(exc))
    return jsonify(build_tax_report(current_user_id, year)), 200


@bp.route("/api/tax-report/exemption", methods=["GET"])
@token_required
def tax_exemption(current_user_id):
    """Isentometro do mes (padrao: o mes corrente); `planned_sale` simula uma venda."""
    try:
        month = normalize_month(request.args.get("month") or datetime.now().strftime("%Y-%m"))
    except ValidationError as exc:
        return validation_error(str(exc))
    planned_sale = safe_float(request.args.get("planned_sale"), 0.0)
    return jsonify(exemption_meter(current_user_id, month, planned_sale)), 200


@bp.route("/api/tax-report/export", methods=["GET"])
@token_required
def tax_report_export(current_user_id):
    """O mesmo relatorio em .xlsx, uma aba por secao."""
    try:
        year = read_report_year(request.args)
    except ValidationError as exc:
        return validation_error(str(exc))
    report = build_tax_report(current_user_id, year)
    income = (
        [{"section": "Rendimentos isentos", **item} for item in report["rendimentos_isentos"]]
        + [
            {"section": "Tributação exclusiva", "line": item["line"], "amount": item["gross"], "withheld": item["withheld"]}
            for item in report["tributacao_exclusiva"]
        ]
    )
    # O app e so em reais nas telas, entao esta linha so existe se houver venda
    # de ativo em moeda estrangeira (so a API cria um): o imposto estimado nao
    # pode sumir do relatorio. Os valores sao em reais.
    exterior = report["exterior"]
    if any(exterior.get(key) for key in ("result", "tax", "loss_used", "loss_balance")):
        income.append({
            "section": "Exterior (Lei 14.754/2023)",
            "line": "Resultado do ano / imposto estimado (15%)",
            "amount": exterior["result"],
            "withheld": exterior["tax"],
        })
    body = export_xlsx.workbook_xlsx([
        ("Bens e Direitos", export_csv.TAX_BENS_COLUMNS, report["bens_e_direitos"], None),
        ("Renda variável", export_csv.TAX_MONTH_COLUMNS, report["renda_variavel"]["months"], None),
        ("Rendimentos", export_csv.TAX_INCOME_COLUMNS, income, None),
    ])
    return download_response(body, XLSX_MIMETYPE, f"ir-{year}.xlsx")
