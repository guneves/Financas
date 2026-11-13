"""Extrato: lancamentos (`/api/transactions`) e a exportacao em CSV.

Soma de `transactions` sempre ignora `type = 'TRANSFER'` — mover dinheiro
entre contas proprias nao e receita nem despesa. O pagamento de fatura e o
caixa de investimento nascem de outros fluxos e nao sao editados por aqui.
"""

import sqlite3

from flask import Blueprint, jsonify, request

from auth import token_required
from db import get_db, serialize_transaction
from money import parse_money, rounded_money
from export_csv import ColumnError
from responses import export_response, read_export_options
from services.accounts import (
    CLIENT_ID_OTHER_KIND_MESSAGE,
    fetch_account,
    fetch_transaction_by_client_id,
    keep_or_require_account,
    resolve_account_id,
    resolve_category,
    transfer_amount_for,
)
from services import auto_record, entries, manual_entries
from services.attachments import remove_attachment_files
from services.inbox import TRANSFER_CATEGORY
from services.inbox_decisions import absorb_created, absorb_other_side
from services.invoices import apply_due_autopay
from services.proceeds_cash import apply_paid_proceeds
from services.transaction_pages import fetch_page, parse_page_args
from services.twins import transaction_twin_ids
from services.sharing import (
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
    parse_optional_number,
    require_choice,
    require_date,
    validation_error,
)
from services.transaction_filters import (  # noqa: F401  (as regras desta rota; os nomes continuam valendo aqui)
    ALLOWED_TRANSACTION_TYPES,
    account_names_map,
    debit_card_id,
    debit_card_owns,
    escape_like,
    transaction_filter_clause,
    with_twins,
)

bp = Blueprint("transactions", __name__)

# O provento pago na conta da carteira acompanha o provento (services/proceeds_cash.py).
PROCEED_LOCKED_MESSAGE = (
    "Este lancamento e um provento pago na conta da carteira. Edite ou exclua o provento "
    "em Proventos."
)


@bp.route("/api/transactions", methods=["GET", "POST"])
@token_required
def transactions(current_user_id):
    if request.method == "GET":
        with get_db() as conn:
            apply_due_autopay(conn, current_user_id)
            apply_paid_proceeds(conn, current_user_id)
            auto_record.record_due(conn, current_user_id)
            try:
                where, params = transaction_filter_clause(conn, current_user_id, request.args)
                page_args = parse_page_args(request.args)
            except ValidationError as exc:
                return validation_error(str(exc))
            select_sql = """
                SELECT transactions.*,
                    (
                        SELECT COUNT(*) FROM transaction_attachments ta
                        WHERE ta.user_id = transactions.user_id
                            AND ta.transaction_id = transactions.id
                    ) AS attachment_count
                FROM transactions
            """
            if page_args:
                # Com limit: uma pagina e os totais do filtro todo (services/transaction_pages.py).
                limit, cursor = page_args
                page = fetch_page(conn, where, params, limit, cursor, select_sql)
                return jsonify({
                    "items": with_twins(conn, current_user_id, page["rows"]),
                    "next_cursor": page["next_cursor"],
                    "count": page["count"],
                    "totals": page["totals"],
                    "day_totals": page["day_totals"],
                }), 200
            rows = conn.execute(
                f"{select_sql} WHERE {where} ORDER BY date DESC, created_at DESC",
                params,
            ).fetchall()
            items = with_twins(conn, current_user_id, rows)
        return jsonify(items), 200

    payload = parse_json_body()
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
            amount = parse_money(payload, "amount", "Valor")
            date_value = require_date(payload, "date", "Data")
            description = optional_string(payload, "description")
            transaction_type = require_choice(payload, "type", "Tipo", ALLOWED_TRANSACTION_TYPES)
            if transaction_type == "TRANSFER":
                raise ValidationError(
                    "Use POST /api/transfers para registrar uma transferencia entre contas."
                )
            category, category_id = resolve_category(conn, current_user_id, payload)
            account_id = resolve_account_id(conn, current_user_id, payload)
            manual_entries.require_manual_account(conn, current_user_id, account_id)
            card_id = debit_card_id(conn, current_user_id, payload, transaction_type, account_id)
        except ValidationError as exc:
            return validation_error(str(exc))

        try:
            item_id = entries.insert_transaction(
                conn, current_user_id, entry_type=transaction_type, account_id=account_id,
                amount=rounded_money(amount), date=date_value, category=category, category_id=category_id,
                description=description, client_id=client_id, card_id=card_id,
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
                updates["amount"] = parse_money(payload, "amount", "Valor")
            if "date" in payload:
                updates["date"] = require_date(payload, "date", "Data")
            if "description" in payload:
                updates["description"] = optional_string(payload, "description")
            if "type" in payload:
                transaction_type = require_choice(
                    payload, "type", "Tipo", ALLOWED_TRANSACTION_TYPES
                )
                if item["type"] == "TRANSFER" and transaction_type != "TRANSFER":
                    raise ValidationError(
                        "Nao e possivel converter uma transferencia em lancamento comum."
                    )
                updates["type"] = transaction_type
            # A despesa ou receita que na verdade foi entre as contas do dono:
            # sem categoria nem divisao, sai da revisao (o dono acabou de dizer
            # o que ela e). O lado que ela ja tem fica como esta.
            converting = updates.get("type") == "TRANSFER" and item["type"] != "TRANSFER"
            final_type = updates.get("type", item["type"])
            if converting:
                if not payload.get("account_id") or not payload.get("transfer_account_id"):
                    raise ValidationError("Escolha a outra conta da transferencia.")
                updates.update({
                    "category": TRANSFER_CATEGORY, "category_id": None, "share_mode": None,
                    "share_person": None, "share_others_amount": None, "share_settled_at": None,
                    "needs_review": 0,
                })
            if ("category" in payload or "category_id" in payload) and not converting:
                category, category_id = resolve_category(conn, current_user_id, payload, current=item)
                updates["category"] = category
                updates["category_id"] = category_id
            # A conta que o lancamento ja tem fica, mesmo arquivada: o Extrato
            # manda a conta de volta em toda edicao. Vazio nao e "a padrao" —
            # mudaria a conta sem o dono ter escolhido.
            if "account_id" in payload:
                updates["account_id"] = keep_or_require_account(
                    conn, current_user_id, payload.get("account_id"), item["account_id"],
                    "Conta de origem" if final_type == "TRANSFER" else "Conta",
                )
            if "transfer_account_id" in payload:
                if final_type != "TRANSFER":
                    raise ValidationError(
                        "Conta de destino so se aplica a transferencias."
                    )
                updates["transfer_account_id"] = keep_or_require_account(
                    conn, current_user_id, payload.get("transfer_account_id"),
                    item["account_id"] if converting else item["transfer_account_id"], "Conta de destino",
                )
            # De quem e (032): so despesa e receita comuns. Aporte e resgate
            # nao chegam aqui (o caixa de uma operacao e travado acima; o
            # digitado e transferencia). O valor final vale tanto para a
            # divisao nova quanto para a que ja estava gravada.
            final_amount = updates.get("amount", item["amount"])
            if has_share_fields(payload):
                if final_type == "TRANSFER":
                    raise ValidationError("Transferencia entre contas nao se divide com outra pessoa.")
                updates.update(parse_share(payload, final_amount))
            elif not converting:
                check_split_fits(item["share_mode"], item["share_others_amount"], final_amount)
        except ValidationError as exc:
            return validation_error(str(exc))

        origin = updates.get("account_id", item["account_id"])
        destination = updates.get("transfer_account_id", item["transfer_account_id"])
        if final_type == "TRANSFER" and origin == destination:
            return validation_error("Origem e destino devem ser contas diferentes.")
        if converting and item["account_id"] not in (origin, destination):
            return validation_error("A transferencia sai ou entra na conta do lancamento.")
        if final_type == "TRANSFER" and (
            "account_id" in updates or "transfer_account_id" in updates or "transfer_amount" in payload
        ):
            # A mesma regra da criacao (POST /api/transfers): entre moedas, o
            # valor que entrou no destino (047); na mesma moeda, nenhum.
            try:
                origin_row = fetch_account(conn, current_user_id, origin)
                destination_row = fetch_account(conn, current_user_id, destination)
                if origin_row and destination_row:
                    transfer_amount = transfer_amount_for(origin_row, destination_row, payload, current=item)
                    if transfer_amount != item["transfer_amount"]:
                        updates["transfer_amount"] = transfer_amount
            except ValidationError as exc:
                return validation_error(str(exc))
        elif "transfer_amount" in payload:
            return validation_error("Valor no destino so se aplica a transferencias.")

        if not updates:
            return validation_error("Informe ao menos um campo para atualizar.")
        # A compra no debito (049) que deixa de ser despesa da conta do cartao
        # sai do cartao.
        if item["card_id"] and (
            updates.get("type", item["type"]) != "EXPENSE"
            or not debit_card_owns(conn, current_user_id, item["card_id"], updates.get("account_id", item["account_id"]))
        ):
            updates["card_id"] = None

        assignments = ", ".join(f"{column} = ?" for column in updates)
        conn.execute(
            f"UPDATE transactions SET {assignments} WHERE id = ? AND user_id = ?",
            (*updates.values(), item_id, current_user_id),
        )
        updated = conn.execute(
            "SELECT * FROM transactions WHERE id = ? AND user_id = ?",
            (item_id, current_user_id),
        ).fetchone()
        absorbed = 0
        if converting:
            other = destination if origin == item["account_id"] else origin
            twin_type = "INCOME" if origin == item["account_id"] else "EXPENSE"
            absorbed = absorb_other_side(conn, current_user_id, updated, other, twin_type)
    body = serialize_transaction(updated)
    if absorbed:
        body["absorbed_other_side"] = True
    return jsonify(body), 200


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
