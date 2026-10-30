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
from services import auto_record
from services.attachments import remove_attachment_files
from services.inbox_decisions import absorb_created
from services.invoices import apply_due_autopay
from services.proceeds_cash import apply_paid_proceeds
from services.transaction_pages import fetch_page, parse_page_args
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
    - review=1: so o gravado sozinho que espera a revisao (045)
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
    else:
        # O Extrato e em reais: o que a conta global (outra moeda) movimenta
        # sozinha fica na tela dela; a transferencia de reais para ela fica.
        clauses.append(
            "NOT EXISTS (SELECT 1 FROM accounts fa WHERE fa.id = transactions.account_id"
            " AND fa.user_id = transactions.user_id AND COALESCE(fa.currency, 'BRL') <> 'BRL')"
        )

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

    if str(args.get("review") or "") in ("1", "true"):
        clauses.append("needs_review = 1")

    return " AND ".join(clauses), params


def debit_card_owns(conn, current_user_id, card_id, account_id):
    """O cartao debita desta conta (041)?"""
    return bool(conn.execute(
        "SELECT 1 FROM credit_cards WHERE id = ? AND user_id = ? AND debit_account_id = ?",
        (card_id, current_user_id, account_id),
    ).fetchone())


def debit_card_id(conn, current_user_id, payload, transaction_type, account_id):
    """`card_id` de uma compra no debito (049): uma despesa na conta do cartao.
    Ausente ou vazio, None."""
    card_id = str(payload.get("card_id") or "").strip()
    if not card_id:
        return None
    card = conn.execute(
        "SELECT * FROM credit_cards WHERE id = ? AND user_id = ?", (card_id, current_user_id),
    ).fetchone()
    if not card:
        raise ValidationError("Cartao nao encontrado.")
    if card["archived_at"]:
        raise ValidationError(f"O cartao {card['name']} foi excluido; ele nao recebe lancamentos novos.")
    if transaction_type != "EXPENSE" or not card["debit_account_id"] or card["debit_account_id"] != account_id:
        raise ValidationError("A compra no debito e uma despesa na conta do cartao.")
    return card_id


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
                    "items": [serialize_transaction(row) for row in page["rows"]],
                    "next_cursor": page["next_cursor"],
                    "count": page["count"],
                    "totals": page["totals"],
                    "day_totals": page["day_totals"],
                }), 200
            rows = conn.execute(
                f"{select_sql} WHERE {where} ORDER BY date DESC, created_at DESC",
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
            card_id = debit_card_id(conn, current_user_id, payload, transaction_type, account_id)
        except ValidationError as exc:
            return validation_error(str(exc))

        try:
            conn.execute(
                """
                INSERT INTO transactions
                (id, user_id, account_id, amount, date, category, category_id, description, type,
                 client_id, card_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    card_id,
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
                updates["amount"] = parse_money(payload, "amount", "Valor")
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
            # A conta que o lancamento ja tem fica, mesmo arquivada: o Extrato
            # manda a conta de volta em toda edicao. Vazio nao e "a padrao" —
            # mudaria a conta sem o dono ter escolhido.
            if "account_id" in payload:
                updates["account_id"] = keep_or_require_account(
                    conn, current_user_id, payload.get("account_id"), item["account_id"],
                    "Conta de origem" if item["type"] == "TRANSFER" else "Conta",
                )
            if "transfer_account_id" in payload:
                if item["type"] != "TRANSFER":
                    raise ValidationError(
                        "Conta de destino so se aplica a transferencias."
                    )
                updates["transfer_account_id"] = keep_or_require_account(
                    conn, current_user_id, payload.get("transfer_account_id"),
                    item["transfer_account_id"], "Conta de destino",
                )
            # De quem e (032): so despesa e receita comuns. Aporte e resgate
            # nao chegam aqui (o caixa de uma operacao e travado acima; o
            # digitado e transferencia). O valor final vale tanto para a
            # divisao nova quanto para a que ja estava gravada.
            final_amount = updates.get("amount", item["amount"])
            if has_share_fields(payload):
                if item["type"] == "TRANSFER":
                    raise ValidationError("Transferencia entre contas nao se divide com outra pessoa.")
                updates.update(parse_share(payload, final_amount))
            else:
                check_split_fits(item["share_mode"], item["share_others_amount"], final_amount)
        except ValidationError as exc:
            return validation_error(str(exc))

        origin = updates.get("account_id", item["account_id"])
        destination = updates.get("transfer_account_id", item["transfer_account_id"])
        if item["type"] == "TRANSFER" and origin == destination:
            return validation_error("Origem e destino devem ser contas diferentes.")
        if item["type"] == "TRANSFER" and (
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
