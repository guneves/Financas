"""Cartoes de credito, compras parceladas e pagamento de fatura.

`/api/credit-cards` e `/api/cc-expenses/*`. As regras (mes da fatura,
fechamento, debito automatico) estao em `services/invoices.py`; o pagamento
real e `POST /api/cc-expenses/pay-invoice`.
"""

import sqlite3

from flask import Blueprint, jsonify, request

from auth import token_required
from db import get_db, new_id, row_to_dict, serialize_transaction
from services.accounts import fetch_account, require_account, resolve_account_id
from services.invoices import (
    InvoiceStillOpenError,
    apply_due_autopay,
    autopay_source_id,
    build_installment_rows,
    ensure_credit_card_owner,
    ensure_invoice_closed,
    local_today,
    serialize_cc_expense,
    settle_invoice,
)
from source_types import CC_INVOICE_PAYMENT_SOURCE_TYPE
from validators import (
    ValidationError,
    optional_date,
    parse_int_number,
    parse_json_body,
    parse_number,
    require_date,
    require_id_list,
    require_string,
    validation_error,
)

bp = Blueprint("cards", __name__)


ALLOWED_CC_STATUS = {"OPEN", "PAID"}


@bp.route("/api/credit-cards", methods=["GET", "POST"])
@token_required
def credit_cards(current_user_id):
    if request.method == "GET":
        with get_db() as conn:
            apply_due_autopay(conn, current_user_id)
            rows = conn.execute(
                "SELECT * FROM credit_cards WHERE user_id = ? ORDER BY name ASC",
                (current_user_id,),
            ).fetchall()
        return jsonify([row_to_dict(row) for row in rows]), 200

    payload = parse_json_body()
    try:
        name = require_string(payload, "name", "Nome do cartao")
        due_day = parse_int_number(payload, "due_day", "Dia de vencimento", minimum=1, maximum=31)
        closing_day = parse_int_number(payload, "closing_day", "Dia de fechamento", minimum=1, maximum=31)
    except ValidationError as exc:
        return validation_error(str(exc))

    item_id = new_id()
    try:
        with get_db() as conn:
            try:
                autopay_account_id = resolve_autopay_account(conn, current_user_id, payload)
            except ValidationError as exc:
                return validation_error(str(exc))
            conn.execute(
                """
                INSERT INTO credit_cards
                (id, user_id, name, due_day, closing_day, autopay_account_id, autopay_start_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    current_user_id,
                    name,
                    due_day,
                    closing_day,
                    autopay_account_id,
                    local_today().strftime("%Y-%m-%d") if autopay_account_id else None,
                ),
            )
            item = conn.execute("SELECT * FROM credit_cards WHERE id = ?", (item_id,)).fetchone()
    except sqlite3.IntegrityError as exc:
        if "UNIQUE" in str(exc).upper():
            return jsonify({"error": "Ja existe um cartao com este nome."}), 409
        return jsonify({"error": "Nao foi possivel criar o cartao."}), 400
    return jsonify(row_to_dict(item)), 201


def resolve_autopay_account(conn, current_user_id, payload):
    """Conta do debito automatico no payload; vazio/None desliga o debito."""
    raw = payload.get("autopay_account_id")
    if raw in (None, ""):
        return None
    return require_account(conn, current_user_id, str(raw), "Conta do debito automatico")["id"]


@bp.route("/api/credit-cards/<card_id>", methods=["PATCH"])
@token_required
def update_credit_card(current_user_id, card_id):
    """Liga, troca ou desliga o debito automatico do cartao.

    Ligar (ou trocar de conta) grava hoje em autopay_start_date: faturas que
    venceram antes disso continuam para pagamento manual.
    """
    payload = parse_json_body()
    if not isinstance(payload, dict) or "autopay_account_id" not in payload:
        return validation_error("Informe autopay_account_id (ou null para desligar).")

    with get_db() as conn:
        card = conn.execute(
            "SELECT * FROM credit_cards WHERE id = ? AND user_id = ?",
            (card_id, current_user_id),
        ).fetchone()
        if not card:
            return jsonify({"error": "Cartao nao encontrado."}), 404
        try:
            autopay_account_id = resolve_autopay_account(conn, current_user_id, payload)
        except ValidationError as exc:
            return validation_error(str(exc))

        if autopay_account_id is None:
            start_date = None
        elif autopay_account_id == card["autopay_account_id"]:
            start_date = card["autopay_start_date"]
        else:
            start_date = local_today().strftime("%Y-%m-%d")

        conn.execute(
            """
            UPDATE credit_cards
            SET autopay_account_id = ?, autopay_start_date = ?
            WHERE id = ? AND user_id = ?
            """,
            (autopay_account_id, start_date, card_id, current_user_id),
        )
        # Uma fatura que vence hoje ja e paga agora, sem esperar a proxima leitura.
        apply_due_autopay(conn, current_user_id)
        item = conn.execute(
            "SELECT * FROM credit_cards WHERE id = ? AND user_id = ?",
            (card_id, current_user_id),
        ).fetchone()
    return jsonify(row_to_dict(item)), 200


@bp.route("/api/credit-cards/<card_id>", methods=["DELETE"])
@token_required
def delete_credit_card(current_user_id, card_id):
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM credit_cards WHERE id = ? AND user_id = ?",
            (card_id, current_user_id),
        )
    if cursor.rowcount == 0:
        return jsonify({"deleted": False}), 404
    return jsonify({"deleted": True}), 200


@bp.route("/api/cc-expenses", methods=["GET", "POST", "DELETE"])
@token_required
def cc_expenses(current_user_id):
    if request.method == "GET":
        status = request.args.get("status")
        params = [current_user_id]
        status_filter = ""
        if status:
            status = str(status).strip().upper()
            if status not in ALLOWED_CC_STATUS:
                return validation_error("Status invalido.")
            status_filter = "AND cce.status = ?"
            params.append(status)

        with get_db() as conn:
            apply_due_autopay(conn, current_user_id)
            rows = conn.execute(
                f"""
                SELECT
                    cce.*,
                    cc.name AS card_name,
                    cc.due_day AS card_due_day,
                    cc.closing_day AS card_closing_day
                FROM cc_expenses cce
                LEFT JOIN credit_cards cc ON cc.id = cce.card_id
                WHERE cce.user_id = ?
                {status_filter}
                ORDER BY cce.invoice_year ASC, cce.invoice_month ASC, cce.created_at ASC
                """,
                params,
            ).fetchall()
        return jsonify([serialize_cc_expense(row) for row in rows]), 200

    if request.method == "DELETE":
        payload = parse_json_body()
        try:
            ids = require_id_list(payload)
        except ValidationError as exc:
            return validation_error(str(exc))

        placeholders = ",".join("?" for _ in ids)
        with get_db() as conn:
            cursor = conn.execute(
                f"DELETE FROM cc_expenses WHERE user_id = ? AND id IN ({placeholders})",
                [current_user_id, *ids],
            )
        return jsonify({"deleted": cursor.rowcount}), 200

    payload = parse_json_body()
    items = payload if isinstance(payload, list) else [payload]
    if not items:
        return validation_error("Informe ao menos uma fatura.")

    inserted = []
    try:
        with get_db() as conn:
            for item in items:
                if not isinstance(item, dict):
                    raise ValidationError("Cada fatura deve ser um objeto valido.")

                card_id = require_string(item, "card_id", "Cartao")
                ensure_credit_card_owner(conn, current_user_id, card_id)
                category = require_string(item, "category", "Categoria")
                description = require_string(item, "description", "Descricao", max_length=500)
                amount = parse_number(item, "amount", "Valor", minimum=0, allow_zero=False)
                purchase_date = require_date(item, "purchase_date", "Data da compra")
                invoice_month = parse_int_number(item, "invoice_month", "Mes da fatura", minimum=1, maximum=12)
                invoice_year = parse_int_number(item, "invoice_year", "Ano da fatura", minimum=2000)
                installment_info = require_string(item, "installment_info", "Parcela", max_length=20)
                status_value = str(item.get("status", "OPEN") or "OPEN").strip().upper()
                if status_value not in ALLOWED_CC_STATUS:
                    raise ValidationError("Status invalido.")

                item_id = new_id()
                conn.execute(
                    """
                    INSERT INTO cc_expenses
                    (id, user_id, card_id, category, description, amount, purchase_date,
                     invoice_month, invoice_year, installment_info, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item_id,
                        current_user_id,
                        card_id,
                        category,
                        description,
                        amount,
                        purchase_date,
                        invoice_month,
                        invoice_year,
                        installment_info,
                        status_value,
                    ),
                )
                inserted.append(item_id)

            placeholders = ",".join("?" for _ in inserted)
            rows = conn.execute(
                f"SELECT * FROM cc_expenses WHERE id IN ({placeholders})",
                inserted,
            ).fetchall()
    except ValidationError as exc:
        return validation_error(str(exc))
    except sqlite3.IntegrityError:
        return jsonify({"error": "Nao foi possivel criar a fatura."}), 400

    return jsonify([row_to_dict(row) for row in rows]), 201


@bp.route("/api/cc-expenses/purchases", methods=["POST"])
@token_required
def create_cc_purchase(current_user_id):
    """Registra uma compra no cartao, parcelando e escolhendo a fatura no servidor.

    O cliente manda a compra (valor total e numero de parcelas); a regra de qual
    fatura cada parcela ocupa fica aqui, junto do cartao que a define.
    """
    payload = parse_json_body()
    if not isinstance(payload, dict):
        return validation_error("Informe uma compra valida.")

    try:
        card_id = require_string(payload, "card_id", "Cartao")
        purchase = {
            "card_id": card_id,
            "category": require_string(payload, "category", "Categoria"),
            "description": require_string(payload, "description", "Descricao", max_length=500),
            "total_amount": parse_number(payload, "total_amount", "Valor total", minimum=0, allow_zero=False),
            "purchase_date": require_date(payload, "purchase_date", "Data da compra"),
            "installments": parse_int_number(payload, "installments", "Parcelas", minimum=1, maximum=72),
        }

        with get_db() as conn:
            ensure_credit_card_owner(conn, current_user_id, card_id)
            card = conn.execute(
                "SELECT due_day, closing_day FROM credit_cards WHERE id = ? AND user_id = ?",
                (card_id, current_user_id),
            ).fetchone()
            if not card:
                raise ValidationError("Cartao nao encontrado.")

            rows = build_installment_rows(purchase, card)
            inserted = []
            for row in rows:
                item_id = new_id()
                conn.execute(
                    """
                    INSERT INTO cc_expenses
                    (id, user_id, card_id, category, description, amount, purchase_date,
                     invoice_month, invoice_year, installment_info, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item_id,
                        current_user_id,
                        row["card_id"],
                        row["category"],
                        row["description"],
                        row["amount"],
                        row["purchase_date"],
                        row["invoice_month"],
                        row["invoice_year"],
                        row["installment_info"],
                        row["status"],
                    ),
                )
                inserted.append(item_id)

            placeholders = ",".join("?" for _ in inserted)
            created = conn.execute(
                f"SELECT * FROM cc_expenses WHERE id IN ({placeholders})"
                " ORDER BY invoice_year ASC, invoice_month ASC",
                inserted,
            ).fetchall()
    except ValidationError as exc:
        return validation_error(str(exc))
    except sqlite3.IntegrityError:
        return jsonify({"error": "Nao foi possivel criar a compra no cartao."}), 400

    return jsonify([row_to_dict(row) for row in created]), 201


@bp.route("/api/cc-expenses/candidates", methods=["GET"])
@token_required
def cc_expense_candidates(current_user_id):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, amount, installment_info
            FROM cc_expenses
            WHERE user_id = ?
              AND card_id = ?
              AND description = ?
              AND purchase_date = ?
              AND category = ?
            """,
            (
                current_user_id,
                request.args.get("card_id"),
                request.args.get("description"),
                request.args.get("purchase_date"),
                request.args.get("category"),
            ),
        ).fetchall()
    return jsonify([row_to_dict(row) for row in rows]), 200


@bp.route("/api/cc-expenses/status", methods=["PATCH"])
@token_required
def update_cc_expense_status(current_user_id):
    payload = parse_json_body()
    try:
        ids = require_id_list(payload)
        status = str(payload.get("status", "PAID") or "PAID").strip().upper()
        if status not in ALLOWED_CC_STATUS:
            raise ValidationError("Status invalido.")
    except ValidationError as exc:
        return validation_error(str(exc))

    placeholders = ",".join("?" for _ in ids)
    with get_db() as conn:
        if status == "PAID":
            lines = conn.execute(
                f"""
                SELECT DISTINCT cce.invoice_month, cce.invoice_year, cc.due_day, cc.closing_day
                FROM cc_expenses cce
                JOIN credit_cards cc ON cc.id = cce.card_id AND cc.user_id = cce.user_id
                WHERE cce.user_id = ? AND cce.id IN ({placeholders})
                """,
                [current_user_id, *ids],
            ).fetchall()
            try:
                for line in lines:
                    ensure_invoice_closed(line, line["invoice_month"], line["invoice_year"])
            except ValidationError as exc:
                return validation_error(str(exc), 409)

        cursor = conn.execute(
            f"""
            UPDATE cc_expenses
            SET status = ?
            WHERE user_id = ? AND id IN ({placeholders})
            """,
            [status, current_user_id, *ids],
        )
    return jsonify({"updated": cursor.rowcount}), 200


@bp.route("/api/cc-expenses/invoice-status", methods=["PATCH"])
@token_required
def update_invoice_status(current_user_id):
    payload = parse_json_body()
    try:
        card_id = require_string(payload, "card_id", "Cartao")
        invoice_month = parse_int_number(payload, "invoice_month", "Mes da fatura", minimum=1, maximum=12)
        invoice_year = parse_int_number(payload, "invoice_year", "Ano da fatura", minimum=2000)
        status = str(payload.get("status", "PAID") or "PAID").strip().upper()
        current_status = str(payload.get("current_status", "OPEN") or "OPEN").strip().upper()
        if status not in ALLOWED_CC_STATUS or current_status not in ALLOWED_CC_STATUS:
            raise ValidationError("Status invalido.")
    except ValidationError as exc:
        return validation_error(str(exc))

    with get_db() as conn:
        try:
            ensure_credit_card_owner(conn, current_user_id, card_id)
        except ValidationError as exc:
            return validation_error(str(exc), 404)

        if status == "PAID":
            card = conn.execute(
                "SELECT due_day, closing_day FROM credit_cards WHERE id = ? AND user_id = ?",
                (card_id, current_user_id),
            ).fetchone()
            try:
                ensure_invoice_closed(card, invoice_month, invoice_year)
            except ValidationError as exc:
                return validation_error(str(exc), 409)

        cursor = conn.execute(
            """
            UPDATE cc_expenses
            SET status = ?
            WHERE user_id = ?
              AND card_id = ?
              AND invoice_month = ?
              AND invoice_year = ?
              AND status = ?
            """,
            (
                status,
                current_user_id,
                card_id,
                invoice_month,
                invoice_year,
                current_status,
            ),
        )
    return jsonify({"updated": cursor.rowcount}), 200


def invoice_payment_account_id(conn, current_user_id, card, payload):
    """Conta do pagamento manual: a informada, a do debito automatico ou a padrao."""
    if payload.get("account_id") in (None, "") and card["autopay_account_id"]:
        autopay_account = fetch_account(conn, current_user_id, card["autopay_account_id"])
        if autopay_account and not autopay_account["archived_at"]:
            return autopay_account["id"]
    return resolve_account_id(conn, current_user_id, payload)


@bp.route("/api/cc-expenses/pay-invoice", methods=["POST"])
@token_required
def pay_invoice(current_user_id):
    """Paga uma fatura fechada: debita a conta e baixa os itens, de uma vez.

    Fatura ainda aberta (antes do dia do fechamento) e recusada com 409 — o
    valor dela ainda pode mudar. `account_id` omitido usa a conta do debito
    automatico do cartao, se houver e nao estiver arquivada, senao a conta
    padrao; `date` omitido e hoje.
    """
    payload = parse_json_body()
    if not isinstance(payload, dict):
        return validation_error("Informe uma fatura valida.")

    try:
        card_id = require_string(payload, "card_id", "Cartao")
        invoice_month = parse_int_number(payload, "invoice_month", "Mes da fatura", minimum=1, maximum=12)
        invoice_year = parse_int_number(payload, "invoice_year", "Ano da fatura", minimum=2000)
        payment_date = optional_date(payload, "date", "Data do pagamento") or local_today().strftime("%Y-%m-%d")
    except ValidationError as exc:
        return validation_error(str(exc))

    with get_db() as conn:
        card = conn.execute(
            "SELECT * FROM credit_cards WHERE id = ? AND user_id = ?",
            (card_id, current_user_id),
        ).fetchone()
        if not card:
            return jsonify({"error": "Cartao nao encontrado."}), 404
        try:
            ensure_invoice_closed(card, invoice_month, invoice_year)
            account_id = invoice_payment_account_id(conn, current_user_id, card, payload)
        except InvoiceStillOpenError as exc:
            return validation_error(str(exc), 409)
        except ValidationError as exc:
            return validation_error(str(exc))

        row = settle_invoice(
            conn,
            current_user_id,
            card,
            invoice_month,
            invoice_year,
            account_id=account_id,
            payment_date=payment_date,
            source_type=CC_INVOICE_PAYMENT_SOURCE_TYPE,
            source_id=f"{autopay_source_id(card_id, invoice_month, invoice_year)}:{new_id()}",
        )
        if not row:
            return jsonify({"error": "Nao ha itens em aberto nesta fatura."}), 409
    return jsonify({"transaction": serialize_transaction(row)}), 201
