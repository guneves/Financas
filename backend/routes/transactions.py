"""Extrato: lancamentos (`/api/transactions`) e a exportacao em CSV.

Soma de `transactions` sempre ignora `type = 'TRANSFER'` — mover dinheiro
entre contas proprias nao e receita nem despesa. O pagamento de fatura e o
caixa de investimento nascem de outros fluxos e nao sao editados por aqui.
"""

import sqlite3
from datetime import datetime

from flask import Blueprint, jsonify, request

from auth import token_required
from db import get_db, new_id, serialize_transaction
from money import rounded_money
from export_csv import ColumnError
from responses import export_response, read_export_options
from services.accounts import (
    CLIENT_ID_OTHER_KIND_MESSAGE,
    fetch_transaction_by_client_id,
    require_account,
    resolve_account_id,
    resolve_category,
)
from services.attachments import remove_attachment_files
from services.inbox_decisions import absorb_created
from services.invoices import apply_due_autopay
from services.proceeds_cash import apply_paid_proceeds
from services.sharing import (
    INVESTMENT_CATEGORY,
    check_split_fits,
    has_share_fields,
    parse_share,
)
from source_types import (
    INVESTMENT_CASH_SOURCE_TYPE,
    INVESTMENT_PROCEED_SOURCE_TYPE,
    INVOICE_PAYMENT_LOCKED_MESSAGE,
    INVOICE_PAYMENT_SOURCE_TYPES,
)
from validators import (
    ValidationError,
    optional_client_id,
    optional_date,
    optional_string,
    parse_json_body,
    parse_number,
    parse_optional_number,
    require_choice,
    require_date,
    validation_error,
)

bp = Blueprint("transactions", __name__)

# O provento pago na conta da carteira acompanha o provento (services/proceeds_cash.py).
PROCEED_LOCKED_MESSAGE = (
    "Este lancamento e um provento pago na conta da carteira. Edite ou exclua o provento "
    "em Proventos."
)


ALLOWED_TRANSACTION_TYPES = {"INCOME", "EXPENSE", "TRANSFER"}


def escape_like(value):
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def transaction_filter_clause(conn, current_user_id, args):
    """Monta o WHERE dos filtros do extrato. Todo filtro e opcional.

    - from / to: periodo inclusivo (AAAA-MM-DD)
    - type: INCOME | EXPENSE | TRANSFER
    - account_id: a conta de origem ou, numa transferencia, a de destino
    - category_id: a categoria e as subcategorias dela; lancamentos que so
      carregam o nome (texto livre ou anteriores a 008) casam pelo nome
    - q: texto livre em descricao e categoria
    - min_amount / max_amount: faixa de valor, inclusiva
    """
    clauses = ["user_id = ?"]
    params = [current_user_id]

    date_from = optional_date(args, "from", "Data inicial")
    date_to = optional_date(args, "to", "Data final")
    if date_from and date_to and date_from > date_to:
        raise ValidationError("Data inicial deve ser anterior ou igual a data final.")
    if date_from:
        clauses.append("date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("date <= ?")
        params.append(date_to)

    if args.get("type"):
        transaction_type = require_choice(args, "type", "Tipo", ALLOWED_TRANSACTION_TYPES)
        clauses.append("type = ?")
        params.append(transaction_type)

    account_id = str(args.get("account_id") or "").strip()
    if account_id:
        clauses.append("(account_id = ? OR transfer_account_id = ?)")
        params.extend([account_id, account_id])

    category_id = str(args.get("category_id") or "").strip()
    if category_id:
        category_rows = conn.execute(
            """
            SELECT id, name FROM categories
            WHERE user_id = ? AND (id = ? OR parent_id = ?)
            """,
            (current_user_id, category_id, category_id),
        ).fetchall()
        if not category_rows:
            raise ValidationError("Categoria nao encontrada.")
        ids = [row["id"] for row in category_rows]
        names = [row["name"] for row in category_rows]
        id_marks = ", ".join("?" for _ in ids)
        name_marks = ", ".join("?" for _ in names)
        clauses.append(
            f"(category_id IN ({id_marks}) OR (category_id IS NULL AND category IN ({name_marks})))"
        )
        params.extend(ids + names)

    text = str(args.get("q") or "").strip()
    if len(text) > 100:
        raise ValidationError("Busca deve ter no maximo 100 caracteres.")
    if text:
        pattern = f"%{escape_like(text)}%"
        clauses.append(
            "(description LIKE ? ESCAPE '\\' OR category LIKE ? ESCAPE '\\')"
        )
        params.extend([pattern, pattern])

    min_amount = parse_optional_number(args, "min_amount", "Valor minimo", minimum=0)
    max_amount = parse_optional_number(args, "max_amount", "Valor maximo", minimum=0)
    if min_amount is not None and max_amount is not None and min_amount > max_amount:
        raise ValidationError("Valor minimo deve ser menor ou igual ao valor maximo.")
    if min_amount is not None:
        clauses.append("amount >= ?")
        params.append(rounded_money(min_amount))
    if max_amount is not None:
        clauses.append("amount <= ?")
        params.append(rounded_money(max_amount))

    return " AND ".join(clauses), params


@bp.route("/api/transactions", methods=["GET", "POST"])
@token_required
def transactions(current_user_id):
    if request.method == "GET":
        with get_db() as conn:
            apply_due_autopay(conn, current_user_id)
            apply_paid_proceeds(conn, current_user_id)
            try:
                where, params = transaction_filter_clause(conn, current_user_id, request.args)
            except ValidationError as exc:
                return validation_error(str(exc))
            rows = conn.execute(
                f"""
                SELECT transactions.*,
                    (
                        SELECT COUNT(*) FROM transaction_attachments ta
                        WHERE ta.user_id = transactions.user_id
                            AND ta.transaction_id = transactions.id
                    ) AS attachment_count
                FROM transactions
                WHERE {where}
                ORDER BY date DESC, created_at DESC
                """,
                params,
            ).fetchall()
        return jsonify([serialize_transaction(row) for row in rows]), 200

    payload = parse_json_body()
    item_id = new_id()
    with get_db() as conn:
        try:
            client_id = optional_client_id(payload)
            # Segunda entrega do mesmo envio: devolve o que a primeira criou,
            # antes de validar — a conta pode ter sido arquivada nesse meio.
            existing = fetch_transaction_by_client_id(conn, current_user_id, client_id)
            if existing:
                if existing["type"] == "TRANSFER":
                    return validation_error(CLIENT_ID_OTHER_KIND_MESSAGE, 409)
                return jsonify(serialize_transaction(existing)), 200
            amount = parse_number(payload, "amount", "Valor", minimum=0, allow_zero=False)
            date_value = require_date(payload, "date", "Data")
            description = optional_string(payload, "description")
            transaction_type = require_choice(payload, "type", "Tipo", ALLOWED_TRANSACTION_TYPES)
            if transaction_type == "TRANSFER":
                raise ValidationError(
                    "Use POST /api/transfers para registrar uma transferencia entre contas."
                )
            category, category_id = resolve_category(conn, current_user_id, payload)
            account_id = resolve_account_id(conn, current_user_id, payload)
        except ValidationError as exc:
            return validation_error(str(exc))

        try:
            conn.execute(
                """
                INSERT INTO transactions
                (id, user_id, account_id, amount, date, category, category_id, description, type,
                 client_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    current_user_id,
                    account_id,
                    rounded_money(amount),
                    date_value,
                    category,
                    category_id,
                    description,
                    transaction_type,
                    client_id,
                ),
            )
        except sqlite3.IntegrityError:
            # Duas entregas do mesmo envio ao mesmo tempo: o indice unico
            # recusou esta, a outra ja gravou.
            conn.rollback()
            existing = fetch_transaction_by_client_id(conn, current_user_id, client_id)
            if not existing:
                raise
            return jsonify(serialize_transaction(existing)), 200
        item = conn.execute(
            "SELECT * FROM transactions WHERE id = ? AND user_id = ?",
            (item_id, current_user_id),
        ).fetchone()
        # O mesmo movimento esperava em Aprovar (notificacao): vira este.
        absorbed = absorb_created(conn, current_user_id, "transactions", item)
    body = serialize_transaction(item)
    if absorbed:
        body["matched_inbox"] = True
    return jsonify(body), 201


def account_names_map(conn, current_user_id):
    rows = conn.execute(
        "SELECT id, name FROM accounts WHERE user_id = ?",
        (current_user_id,),
    ).fetchall()
    return {row["id"]: row["name"] for row in rows}


@bp.route("/api/transactions/export", methods=["GET"])
@token_required
def export_transactions(current_user_id):
    """Extrato filtrado em CSV ou .xlsx — os mesmos filtros de GET /api/transactions,
    mais `format` e `columns` (responses.read_export_options)."""
    try:
        fmt, columns = read_export_options(request.args, "transactions")
    except ColumnError as exc:
        return validation_error(str(exc))
    with get_db() as conn:
        apply_due_autopay(conn, current_user_id)
        apply_paid_proceeds(conn, current_user_id)
        try:
            where, params = transaction_filter_clause(conn, current_user_id, request.args)
        except ValidationError as exc:
            return validation_error(str(exc))
        rows = conn.execute(
            f"""
            SELECT * FROM transactions
            WHERE {where}
            ORDER BY date DESC, created_at DESC
            """,
            params,
        ).fetchall()
        names = account_names_map(conn, current_user_id)

    items = [serialize_transaction(row) for row in rows]
    return export_response(
        fmt, columns, items,
        basename="extrato", sheet_name="Extrato", context={"account_names": names},
    )


@bp.route("/api/transactions/<item_id>", methods=["PATCH"])
@token_required
def update_transaction(current_user_id, item_id):
    """Editar um lancamento (3.7 de docs/next-steps.md).

    Ate aqui so existia DELETE: corrigir um digito significava apagar e digitar
    de novo. Lancamentos espelhados de investimento continuam bloqueados — eles
    sao derivados da movimentacao e sao reescritos por
    sync_investment_cash_transaction().
    """
    payload = parse_json_body()
    with get_db() as conn:
        item = conn.execute(
            "SELECT * FROM transactions WHERE id = ? AND user_id = ?",
            (item_id, current_user_id),
        ).fetchone()
        if not item:
            return jsonify({"error": "Lancamento nao encontrado."}), 404
        if item["source_type"] == INVESTMENT_CASH_SOURCE_TYPE:
            return jsonify({
                "error": "Este lancamento de caixa esta vinculado a uma movimentacao de investimento. Edite a movimentacao de investimento para manter o patrimonio consistente."
            }), 409
        if item["source_type"] == INVESTMENT_PROCEED_SOURCE_TYPE:
            return jsonify({"error": PROCEED_LOCKED_MESSAGE}), 409
        if item["source_type"] in INVOICE_PAYMENT_SOURCE_TYPES:
            return jsonify({"error": INVOICE_PAYMENT_LOCKED_MESSAGE}), 409

        updates = {}
        try:
            if "amount" in payload:
                updates["amount"] = rounded_money(
                    parse_number(payload, "amount", "Valor", minimum=0, allow_zero=False)
                )
            if "date" in payload:
                updates["date"] = require_date(payload, "date", "Data")
            if "description" in payload:
                updates["description"] = optional_string(payload, "description")
            if "type" in payload:
                transaction_type = require_choice(
                    payload, "type", "Tipo", ALLOWED_TRANSACTION_TYPES
                )
                if (transaction_type == "TRANSFER") != (item["type"] == "TRANSFER"):
                    raise ValidationError(
                        "Nao e possivel converter um lancamento comum em transferencia."
                    )
                updates["type"] = transaction_type
            if "category" in payload or "category_id" in payload:
                category, category_id = resolve_category(conn, current_user_id, payload, current=item)
                updates["category"] = category
                updates["category_id"] = category_id
            if "account_id" in payload:
                updates["account_id"] = resolve_account_id(conn, current_user_id, payload)
            if "transfer_account_id" in payload:
                if item["type"] != "TRANSFER":
                    raise ValidationError(
                        "Conta de destino so se aplica a transferencias."
                    )
                updates["transfer_account_id"] = require_account(
                    conn,
                    current_user_id,
                    str(payload.get("transfer_account_id") or ""),
                    "Conta de destino",
                )["id"]
            # De quem e (032): so despesa e receita comuns; aporte e resgate
            # nao se dividem. O valor final vale tanto para a divisao nova
            # quanto para a que ja estava gravada.
            final_amount = updates.get("amount", item["amount"])
            final_category = updates.get("category", item["category"])
            if has_share_fields(payload):
                if item["type"] == "TRANSFER":
                    raise ValidationError("Transferencia entre contas nao se divide com outra pessoa.")
                share = parse_share(payload, final_amount)
                if share["share_mode"] and final_category == INVESTMENT_CATEGORY:
                    raise ValidationError("Investimento nao se divide com outra pessoa.")
                updates.update(share)
            else:
                check_split_fits(item["share_mode"], item["share_others_amount"], final_amount)
                if item["share_mode"] and final_category == INVESTMENT_CATEGORY:
                    raise ValidationError("Investimento nao se divide com outra pessoa. Volte para \"Só minha\" antes.")
        except ValidationError as exc:
            return validation_error(str(exc))

        if not updates:
            return validation_error("Informe ao menos um campo para atualizar.")

        origin = updates.get("account_id", item["account_id"])
        destination = updates.get("transfer_account_id", item["transfer_account_id"])
        if item["type"] == "TRANSFER" and origin == destination:
            return validation_error("Origem e destino devem ser contas diferentes.")

        assignments = ", ".join(f"{column} = ?" for column in updates)
        conn.execute(
            f"UPDATE transactions SET {assignments} WHERE id = ? AND user_id = ?",
            (*updates.values(), item_id, current_user_id),
        )
        updated = conn.execute(
            "SELECT * FROM transactions WHERE id = ? AND user_id = ?",
            (item_id, current_user_id),
        ).fetchone()
    return jsonify(serialize_transaction(updated)), 200


@bp.route("/api/transactions/<item_id>", methods=["DELETE"])
@token_required
def delete_transaction(current_user_id, item_id):
    with get_db() as conn:
        item = conn.execute(
            "SELECT source_type FROM transactions WHERE id = ? AND user_id = ?",
            (item_id, current_user_id),
        ).fetchone()
        if not item:
            return jsonify({"deleted": False}), 404
        if item["source_type"] == INVESTMENT_CASH_SOURCE_TYPE:
            return jsonify({
                "error": "Este lancamento de caixa esta vinculado a uma movimentacao de investimento. Exclua a movimentacao de investimento para manter o patrimonio consistente."
            }), 409
        if item["source_type"] == INVESTMENT_PROCEED_SOURCE_TYPE:
            return jsonify({"error": PROCEED_LOCKED_MESSAGE}), 409
        if item["source_type"] in INVOICE_PAYMENT_SOURCE_TYPES:
            return jsonify({"error": INVOICE_PAYMENT_LOCKED_MESSAGE}), 409
        # As linhas de comprovante saem pelo ON DELETE CASCADE; os arquivos,
        # depois do commit, para um DELETE que falhe nao levar o recibo.
        stored_names = [
            row["stored_name"]
            for row in conn.execute(
                """
                SELECT stored_name FROM transaction_attachments
                WHERE user_id = ? AND transaction_id = ?
                """,
                (current_user_id, item_id),
            ).fetchall()
        ]
        cursor = conn.execute(
            "DELETE FROM transactions WHERE id = ? AND user_id = ?",
            (item_id, current_user_id),
        )
    if cursor.rowcount == 0:
        return jsonify({"deleted": False}), 404
    remove_attachment_files(current_user_id, stored_names)
    return jsonify({"deleted": True}), 200
