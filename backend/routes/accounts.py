"""Contas bancarias, transferencias e categorias.

Contas e categorias sao arquivadas, nunca apagadas (`DELETE` preenche
`archived_at`): as FKs sao `ON DELETE SET NULL` e um delete de verdade
deixaria lancamentos orfaos. Uma transferencia e uma linha so, que sai de
`account_id` e entra em `transfer_account_id`.
"""

import sqlite3

from flask import Blueprint, jsonify, request

from auth import token_required
from db import get_db, new_id, row_to_dict, serialize_transaction, utc_timestamp
from money import parse_money, rounded_money
from services.accounts import (
    CLIENT_ID_OTHER_KIND_MESSAGE,
    TRANSFER_CURRENCY_MESSAGE,
    account_balance_rows,
    category_id_for_name,
    ensure_default_account,
    fetch_account,
    fetch_category,
    fetch_transaction_by_client_id,
    rename_category_rows,
    require_account,
    resolve_category,
    seed_default_categories,
    serialize_account,
)
from services.fx import BASE_CURRENCY, FxUnavailable, normalize_currency, rate_on
from services.inbox_decisions import absorb_created
from services.invoices import apply_due_autopay
from services.investments import PORTFOLIO_ACCOUNT_TYPE
from services.proceeds_cash import apply_paid_proceeds, mark_portfolio_since
from validators import (
    ValidationError,
    optional_client_id,
    optional_string,
    parse_json_body,
    parse_optional_number,
    require_choice,
    require_date,
    require_string,
    safe_float,
    validation_error,
)

bp = Blueprint("accounts", __name__)


ALLOWED_ACCOUNT_TYPES = {"CHECKING", "SAVINGS", "BROKERAGE", "CASH", "OTHER"}
ALLOWED_CATEGORY_KINDS = {"INCOME", "EXPENSE", "BOTH"}
TRANSFER_CATEGORY = "Transferencia"


def with_balance_in_brl(conn, current_user_id, item):
    """Conta em moeda estrangeira: saldo tambem em reais, pela PTAX de hoje.

    O consolidado soma balance_brl; sem cambio disponivel, ele fica de fora
    (None) e a tela avisa, em vez de somar dolar como real.
    """
    currency = normalize_currency(item.get("currency"))
    if currency == BASE_CURRENCY:
        item["balance_brl"] = item.get("balance")
        return item
    try:
        rate = rate_on(conn, current_user_id, currency)
        item["fx_rate"] = rate
        item["balance_brl"] = rounded_money(safe_float(item.get("balance")) * rate)
    except FxUnavailable:
        item["fx_rate"] = None
        item["balance_brl"] = None
    return item


@bp.route("/api/accounts", methods=["GET", "POST"])
@token_required
def accounts(current_user_id):
    if request.method == "GET":
        include_archived = str(request.args.get("include_archived", "")).lower() in ("1", "true", "yes")
        with get_db() as conn:
            ensure_default_account(conn, current_user_id)
            apply_due_autopay(conn, current_user_id)
            apply_paid_proceeds(conn, current_user_id)
            rows = account_balance_rows(conn, current_user_id)
            items = [with_balance_in_brl(conn, current_user_id, serialize_account(row)) for row in rows]
        if not include_archived:
            items = [item for item in items if not item.get("archived_at")]
        return jsonify(items), 200

    payload = parse_json_body()
    try:
        name = require_string(payload, "name", "Nome da conta")
        account_type = require_choice(payload, "type", "Tipo de conta", ALLOWED_ACCOUNT_TYPES)
        institution = optional_string(payload, "institution", max_length=255)
        initial_balance = rounded_money(
            parse_optional_number(payload, "initial_balance", "Saldo inicial") or 0
        )
        currency = (optional_string(payload, "currency", max_length=3) or "BRL").upper()
    except ValidationError as exc:
        return validation_error(str(exc))

    account_id = new_id()
    try:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO accounts
                (id, user_id, name, type, institution, initial_balance, currency)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    current_user_id,
                    name,
                    account_type,
                    institution or None,
                    initial_balance,
                    currency,
                ),
            )
            row = fetch_account(conn, current_user_id, account_id)
    except sqlite3.IntegrityError:
        return validation_error("Ja existe uma conta com este nome.", 409)

    item = serialize_account(row)
    item["balance"] = initial_balance
    return jsonify(item), 201


@bp.route("/api/accounts/<account_id>", methods=["PATCH", "DELETE"])
@token_required
def account_detail(current_user_id, account_id):
    with get_db() as conn:
        account = fetch_account(conn, current_user_id, account_id)
        if not account:
            return jsonify({"error": "Conta nao encontrada."}), 404

        if request.method == "DELETE":
            # Arquivar, nao apagar: transactions.account_id usa ON DELETE SET
            # NULL e uma exclusao deixaria lancamentos sem conta, silenciosamente.
            used = conn.execute(
                """
                SELECT COUNT(*) AS total FROM transactions
                WHERE user_id = ? AND (account_id = ? OR transfer_account_id = ?)
                """,
                (current_user_id, account_id, account_id),
            ).fetchone()["total"]
            remaining = conn.execute(
                """
                SELECT COUNT(*) AS total FROM accounts
                WHERE user_id = ? AND archived_at IS NULL AND id <> ?
                """,
                (current_user_id, account_id),
            ).fetchone()["total"]
            if remaining == 0:
                return validation_error(
                    "Esta e a unica conta ativa. Crie outra antes de arquivar esta.", 409
                )
            conn.execute(
                """
                UPDATE accounts
                SET archived_at = ?, is_default = 0, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (utc_timestamp(), utc_timestamp(), account_id, current_user_id),
            )
            # Arquivar a padrao passa a marca para outra (fora da Corretora).
            ensure_default_account(conn, current_user_id)
            return jsonify({"archived": True, "transactions": used}), 200

        payload = parse_json_body()
        updates = {}
        try:
            if "name" in payload:
                updates["name"] = require_string(payload, "name", "Nome da conta")
            if "type" in payload:
                updates["type"] = require_choice(
                    payload, "type", "Tipo de conta", ALLOWED_ACCOUNT_TYPES
                )
            if "institution" in payload:
                updates["institution"] = optional_string(payload, "institution", max_length=255) or None
            if "initial_balance" in payload:
                updates["initial_balance"] = parse_money(
                    payload, "initial_balance", "Saldo inicial", allow_zero=True, allow_negative=True
                )
            if "archived_at" in payload and payload.get("archived_at") in (None, ""):
                updates["archived_at"] = None
        except ValidationError as exc:
            return validation_error(str(exc))

        final_type = updates.get("type", account["type"])
        archived_after = updates.get("archived_at", account["archived_at"])
        make_default = payload.get("is_default") is True
        if make_default:
            if archived_after:
                return validation_error("Uma conta arquivada nao pode ser a padrao.")
            if final_type == PORTFOLIO_ACCOUNT_TYPE:
                # O saldo da Corretora so aparece em Investimentos; a padrao e
                # onde cai o lancamento sem conta, e ele sumiria do Inicio.
                return validation_error("A conta da carteira (Corretora) nao pode ser a padrao.")
            updates["is_default"] = 1
        elif final_type == PORTFOLIO_ACCOUNT_TYPE and account["is_default"]:
            # A padrao virou a conta da carteira: a marca passa para outra.
            updates["is_default"] = 0

        if not updates:
            return validation_error("Informe ao menos um campo para atualizar.")

        # Virou a conta da carteira hoje: os proventos pagos daqui em diante
        # entram nela, os de antes ja estao no saldo (services/proceeds_cash.py).
        if updates.get("type") == PORTFOLIO_ACCOUNT_TYPE and account["type"] != PORTFOLIO_ACCOUNT_TYPE:
            updates["metadata"] = mark_portfolio_since(account["metadata"])

        updates["updated_at"] = utc_timestamp()
        assignments = ", ".join(f"{column} = ?" for column in updates)
        try:
            conn.execute(
                f"UPDATE accounts SET {assignments} WHERE id = ? AND user_id = ?",
                (*updates.values(), account_id, current_user_id),
            )
        except sqlite3.IntegrityError:
            conn.rollback()
            return validation_error("Ja existe uma conta com este nome.", 409)
        # Desmarcar as outras so depois que a conta foi gravada: um nome
        # repetido (409) nao deixa o usuario sem padrao.
        if make_default:
            conn.execute(
                "UPDATE accounts SET is_default = 0 WHERE user_id = ? AND id <> ?",
                (current_user_id, account_id),
            )
        ensure_default_account(conn, current_user_id)
        row = fetch_account(conn, current_user_id, account_id)
    return jsonify(serialize_account(row)), 200


@bp.route("/api/transfers", methods=["POST"])
@token_required
def create_transfer(current_user_id):
    """Transferencia entre contas proprias.

    Uma unica linha type='TRANSFER': sai de account_id, entra em
    transfer_account_id. Nao e receita nem despesa, entao nao distorce os
    totais do mes — que era exatamente o problema de registrar como
    despesa + receita.
    """
    payload = parse_json_body()
    with get_db() as conn:
        try:
            client_id = optional_client_id(payload)
            # Segunda entrega do mesmo envio (024): devolve a transferencia que
            # a primeira criou, sem gravar outra.
            existing = fetch_transaction_by_client_id(conn, current_user_id, client_id)
            if existing:
                if existing["type"] != "TRANSFER":
                    return validation_error(CLIENT_ID_OTHER_KIND_MESSAGE, 409)
                return jsonify(serialize_transaction(existing)), 200
            amount = parse_money(payload, "amount", "Valor")
            date_value = require_date(payload, "date", "Data")
            description = optional_string(payload, "description")
            origin = require_account(
                conn, current_user_id, str(payload.get("account_id") or ""), "Conta de origem"
            )
            destination = require_account(
                conn,
                current_user_id,
                str(payload.get("transfer_account_id") or ""),
                "Conta de destino",
            )
            if origin["id"] == destination["id"]:
                raise ValidationError("Origem e destino devem ser contas diferentes.")
            if normalize_currency(origin["currency"]) != normalize_currency(destination["currency"]):
                raise ValidationError(TRANSFER_CURRENCY_MESSAGE)
            category, category_id = resolve_category(conn, current_user_id, payload, required=False)
        except ValidationError as exc:
            return validation_error(str(exc))

        item_id = new_id()
        default_description = "{} -> {}".format(origin["name"], destination["name"])
        try:
            conn.execute(
                """
                INSERT INTO transactions
                (id, user_id, account_id, transfer_account_id, amount, date,
                 category, category_id, description, type, client_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'TRANSFER', ?)
                """,
                (
                    item_id,
                    current_user_id,
                    origin["id"],
                    destination["id"],
                    amount,
                    date_value,
                    category or TRANSFER_CATEGORY,
                    category_id,
                    description or default_description,
                    client_id,
                ),
            )
        except sqlite3.IntegrityError:
            # Entregas simultaneas do mesmo envio: a outra ja gravou.
            conn.rollback()
            existing = fetch_transaction_by_client_id(conn, current_user_id, client_id)
            if not existing:
                raise
            return jsonify(serialize_transaction(existing)), 200
        item = conn.execute(
            "SELECT * FROM transactions WHERE id = ? AND user_id = ?",
            (item_id, current_user_id),
        ).fetchone()
        # As pontas desta transferencia que esperavam em Aprovar viram ela.
        absorbed = absorb_created(conn, current_user_id, "transactions", item)
    body = serialize_transaction(item)
    if absorbed:
        body["matched_inbox"] = True
    return jsonify(body), 201


def require_parent_category(conn, current_user_id, parent_id):
    """A categoria pai: do usuario, ativa e da raiz (um nivel de subcategoria)."""
    parent = fetch_category(conn, current_user_id, str(parent_id))
    if not parent:
        raise ValidationError("Categoria pai nao encontrada.")
    if parent["archived_at"]:
        raise ValidationError("A categoria pai esta arquivada.")
    if parent["parent_id"]:
        raise ValidationError("So existe um nivel de subcategoria.")
    return parent


@bp.route("/api/categories", methods=["GET", "POST"])
@token_required
def categories(current_user_id):
    if request.method == "GET":
        include_archived = str(request.args.get("include_archived", "")).lower() in ("1", "true", "yes")
        kind = str(request.args.get("kind", "") or "").strip().upper()
        with get_db() as conn:
            seed_default_categories(conn, current_user_id)
            rows = conn.execute(
                """
                SELECT c.*, parent.name AS parent_name
                FROM categories c
                LEFT JOIN categories parent ON parent.id = c.parent_id
                WHERE c.user_id = ?
                ORDER BY COALESCE(parent.name, c.name) COLLATE NOCASE,
                         c.parent_id IS NOT NULL,
                         c.name COLLATE NOCASE
                """,
                (current_user_id,),
            ).fetchall()
        items = [row_to_dict(row) for row in rows]
        if not include_archived:
            items = [item for item in items if not item.get("archived_at")]
        if kind in ALLOWED_CATEGORY_KINDS:
            items = [item for item in items if item["kind"] in (kind, "BOTH")]
        return jsonify(items), 200

    payload = parse_json_body()
    with get_db() as conn:
        try:
            name = require_string(payload, "name", "Nome da categoria")
            kind = require_choice(payload, "kind", "Tipo da categoria", ALLOWED_CATEGORY_KINDS)
            color = optional_string(payload, "color", max_length=32) or None
            icon = optional_string(payload, "icon", max_length=64) or None
            parent_id = payload.get("parent_id")
            if parent_id in (None, ""):
                parent_id = None
            else:
                parent = require_parent_category(conn, current_user_id, parent_id)
                parent_id = parent["id"]
        except ValidationError as exc:
            return validation_error(str(exc))

        category_id = new_id()
        try:
            conn.execute(
                """
                INSERT INTO categories (id, user_id, name, kind, parent_id, color, icon)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (category_id, current_user_id, name, kind, parent_id, color, icon),
            )
        except sqlite3.IntegrityError:
            return validation_error("Ja existe uma categoria com este nome.", 409)
        row = fetch_category(conn, current_user_id, category_id)
    return jsonify(row_to_dict(row)), 201


@bp.route("/api/categories/<category_id>", methods=["PATCH", "DELETE"])
@token_required
def category_detail(current_user_id, category_id):
    with get_db() as conn:
        category = fetch_category(conn, current_user_id, category_id)
        if not category:
            return jsonify({"error": "Categoria nao encontrada."}), 404

        if request.method == "DELETE":
            # Arquivar. Apagar zeraria transactions.category_id via ON DELETE
            # SET NULL e os lancamentos perderiam a ligacao sem aviso.
            children = conn.execute(
                """
                SELECT COUNT(*) AS total FROM categories
                WHERE user_id = ? AND parent_id = ? AND archived_at IS NULL
                """,
                (current_user_id, category_id),
            ).fetchone()["total"]
            if children:
                return validation_error(
                    "Arquive as subcategorias antes de arquivar esta categoria.", 409
                )
            conn.execute(
                "UPDATE categories SET archived_at = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (utc_timestamp(), utc_timestamp(), category_id, current_user_id),
            )
            return jsonify({"archived": True}), 200

        payload = parse_json_body()
        updates = {}
        try:
            if "name" in payload:
                updates["name"] = require_string(payload, "name", "Nome da categoria")
            if "kind" in payload:
                updates["kind"] = require_choice(
                    payload, "kind", "Tipo da categoria", ALLOWED_CATEGORY_KINDS
                )
            if "color" in payload:
                updates["color"] = optional_string(payload, "color", max_length=32) or None
            if "icon" in payload:
                updates["icon"] = optional_string(payload, "icon", max_length=64) or None
            if "parent_id" in payload:
                parent_id = payload.get("parent_id")
                if parent_id in (None, ""):
                    updates["parent_id"] = None
                elif str(parent_id) == category["parent_id"]:
                    # O pai que ela ja tem fica, mesmo arquivado depois.
                    updates["parent_id"] = category["parent_id"]
                else:
                    if str(parent_id) == category_id:
                        raise ValidationError("Uma categoria nao pode ser pai dela mesma.")
                    parent = require_parent_category(conn, current_user_id, parent_id)
                    # Com filhas, virar subcategoria criaria um terceiro nivel,
                    # que o orcamento nao soma.
                    children = conn.execute(
                        "SELECT COUNT(*) FROM categories WHERE user_id = ? AND parent_id = ?",
                        (current_user_id, category_id),
                    ).fetchone()[0]
                    if children:
                        raise ValidationError(
                            "Esta categoria tem subcategorias e nao pode virar subcategoria. "
                            "Mova as subcategorias antes."
                        )
                    updates["parent_id"] = parent["id"]
            if "archived_at" in payload and payload.get("archived_at") in (None, ""):
                updates["archived_at"] = None
        except ValidationError as exc:
            return validation_error(str(exc))

        if not updates:
            return validation_error("Informe ao menos um campo para atualizar.")

        # Renomear a categoria renomeia junto o nome gravado em tudo o que e
        # dela (lancamentos, compras no cartao, recorrencias, regras, Aprovar).
        new_name = updates.get("name")
        renamed = bool(new_name) and new_name != category["name"]
        owned_old_name = renamed and category_id_for_name(conn, current_user_id, category["name"]) == category_id
        updates["updated_at"] = utc_timestamp()
        assignments = ", ".join(f"{column} = ?" for column in updates)
        try:
            conn.execute(
                f"UPDATE categories SET {assignments} WHERE id = ? AND user_id = ?",
                (*updates.values(), category_id, current_user_id),
            )
        except sqlite3.IntegrityError:
            return validation_error("Ja existe uma categoria com este nome.", 409)
        if renamed:
            rename_category_rows(
                conn, current_user_id, category_id, category["name"], new_name, owned_old_name=owned_old_name,
            )
        row = fetch_category(conn, current_user_id, category_id)
    return jsonify(row_to_dict(row)), 200
