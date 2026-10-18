"""Pluggy (Open Finance): conexoes, contas ligadas, sincronizacao e possiveis duplicatas.

As regras moram em `services/pluggy_sync.py`; a rede, em `pluggy_client.py`.
Ligar uma conta, desligar ou remover uma conexao e configuracao: apaga so a
ligacao, nunca um lancamento (o livro `pluggy_transactions` fica, entao ligar
de novo nao reimporta o que ja entrou).
"""

import re
import sqlite3

from flask import Blueprint, jsonify, request

import pluggy_client
from auth import token_required
from db import get_db, new_id, row_to_dict
from integrations import provider_snapshot
from services.accounts import require_account
from services.invoices import ensure_credit_card_owner, local_today
from services.pluggy_sync import (
    resolve_review,
    review_items,
    serialize_ledger,
    state_counts,
    sync_pluggy,
)
from validators import (
    ValidationError,
    optional_date,
    optional_string,
    parse_json_body,
    require_choice,
    require_string,
    validation_error,
)

bp = Blueprint("pluggy", __name__)

# Os ids da Pluggy sao UUIDs; um formato fechado basta para nao gravar lixo.
PLUGGY_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{7,63}$")


def require_pluggy_id(payload, key, label):
    value = require_string(payload, key, label, max_length=64)
    if not PLUGGY_ID_PATTERN.match(value):
        raise ValidationError(f"{label} invalido.")
    return value


def fetch_item(conn, current_user_id, item_row_id):
    return conn.execute(
        "SELECT * FROM pluggy_items WHERE id = ? AND user_id = ?",
        (item_row_id, current_user_id),
    ).fetchone()


def serialize_links(conn, current_user_id):
    rows = conn.execute(
        """
        SELECT l.*, a.name AS account_name, c.name AS card_name
        FROM pluggy_account_links l
        LEFT JOIN accounts a ON a.id = l.account_id AND a.user_id = l.user_id
        LEFT JOIN credit_cards c ON c.id = l.card_id AND c.user_id = l.user_id
        WHERE l.user_id = ?
        ORDER BY l.created_at
        """,
        (current_user_id,),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


@bp.route("/api/pluggy", methods=["GET"])
@token_required
def pluggy_status(current_user_id):
    with get_db() as conn:
        items = conn.execute(
            "SELECT * FROM pluggy_items WHERE user_id = ? ORDER BY created_at",
            (current_user_id,),
        ).fetchall()
        configured = pluggy_client.is_configured()
        body = {
            "configured": configured,
            # So nomes de variaveis, nunca valores: o que a tela diz que falta.
            "setup": None if configured else pluggy_client.setup_report(),
            "items": [row_to_dict(row) for row in items],
            "links": serialize_links(conn, current_user_id),
            "counts": state_counts(conn, current_user_id),
            "provider": provider_snapshot("pluggy"),
        }
    return jsonify(body), 200


@bp.route("/api/pluggy/items", methods=["POST"])
@token_required
def add_pluggy_item(current_user_id):
    """Cadastra uma conexao pelo id do item na Pluggy, conferido na propria Pluggy."""
    payload = parse_json_body()
    try:
        item_id = require_pluggy_id(payload, "item_id", "Id da conexao")
    except ValidationError as exc:
        return validation_error(str(exc))
    if not pluggy_client.is_configured():
        return validation_error(pluggy_client.not_configured_message())
    try:
        item = pluggy_client.get_item(item_id)
    except pluggy_client.PluggyHTTPError as exc:
        if exc.status in (400, 404):
            return validation_error("A Pluggy nao conhece esta conexao. Confira o id do item.")
        return jsonify({"error": f"A Pluggy nao respondeu: {exc}"}), 502
    except pluggy_client.PluggyError as exc:
        return jsonify({"error": f"A Pluggy nao respondeu: {exc}"}), 502

    row_id = new_id()
    try:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO pluggy_items
                (id, user_id, item_id, connector_name, status, execution_status, last_updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_id, current_user_id, item_id, item.connector_name or None,
                    item.status or None, item.execution_status or None, item.last_updated_at or None,
                ),
            )
            row = fetch_item(conn, current_user_id, row_id)
    except sqlite3.IntegrityError:
        return jsonify({"error": "Esta conexao ja esta cadastrada."}), 409
    return jsonify(row_to_dict(row)), 201


@bp.route("/api/pluggy/items/<item_row_id>", methods=["DELETE"])
@token_required
def delete_pluggy_item(current_user_id, item_row_id):
    """Remove a conexao e as ligacoes das contas dela. Nenhum lancamento sai."""
    with get_db() as conn:
        item = fetch_item(conn, current_user_id, item_row_id)
        if not item:
            return jsonify({"deleted": False}), 404
        conn.execute(
            "DELETE FROM pluggy_account_links WHERE user_id = ? AND item_id = ?",
            (current_user_id, item["item_id"]),
        )
        conn.execute(
            "DELETE FROM pluggy_items WHERE id = ? AND user_id = ?",
            (item_row_id, current_user_id),
        )
    return jsonify({"deleted": True}), 200


@bp.route("/api/pluggy/items/<item_row_id>/accounts", methods=["GET"])
@token_required
def pluggy_item_accounts(current_user_id, item_row_id):
    """As contas da conexao, lidas agora na Pluggy, com a ligacao de cada uma."""
    with get_db() as conn:
        item = fetch_item(conn, current_user_id, item_row_id)
        if not item:
            return jsonify({"error": "Conexao nao encontrada."}), 404
        links = {link["pluggy_account_id"]: link for link in serialize_links(conn, current_user_id)}
    if not pluggy_client.is_configured():
        return validation_error(pluggy_client.not_configured_message())
    try:
        accounts = pluggy_client.list_accounts(item["item_id"])
    except pluggy_client.PluggyError as exc:
        return jsonify({"error": f"A Pluggy nao respondeu: {exc}"}), 502
    return jsonify([
        {
            "id": account.id,
            "type": account.type,
            "subtype": account.subtype,
            "number": account.number,
            "name": account.name,
            "currency": account.currency,
            "link": links.get(account.id),
        }
        for account in accounts
    ]), 200


@bp.route("/api/pluggy/links/<pluggy_account_id>", methods=["PUT", "DELETE"])
@token_required
def pluggy_link(current_user_id, pluggy_account_id):
    """Liga (ou religa) uma conta da Pluggy a uma conta ou cartao do app.

    `since` (AAAA-MM-DD, padrao hoje) e o primeiro dia que entra: o que veio
    antes ja esta no saldo inicial da conta ou foi lancado a mao. Trocar o
    `since` faz a proxima sincronizacao ler tudo de novo desde ele.
    """
    if not PLUGGY_ID_PATTERN.match(pluggy_account_id or ""):
        return validation_error("Conta da Pluggy invalida.")
    if request.method == "DELETE":
        with get_db() as conn:
            cursor = conn.execute(
                "DELETE FROM pluggy_account_links WHERE user_id = ? AND pluggy_account_id = ?",
                (current_user_id, pluggy_account_id),
            )
        if not cursor.rowcount:
            return jsonify({"deleted": False}), 404
        return jsonify({"deleted": True}), 200

    payload = parse_json_body()
    with get_db() as conn:
        try:
            item = fetch_item(conn, current_user_id, require_string(payload, "item", "Conexao"))
            if not item:
                raise ValidationError("Conexao nao encontrada.")
            account_type = require_choice(payload, "type", "Tipo da conta", {"BANK", "CREDIT"})
            since = optional_date(payload, "since", "Desde") or local_today().strftime("%Y-%m-%d")
            name = optional_string(payload, "name", max_length=120)
            account_id = card_id = None
            if account_type == "BANK":
                account_id = require_account(
                    conn, current_user_id, require_string(payload, "account_id", "Conta"), "Conta"
                )["id"]
            else:
                card_id = require_string(payload, "card_id", "Cartao")
                ensure_credit_card_owner(conn, current_user_id, card_id)
        except ValidationError as exc:
            return validation_error(str(exc))

        existing = conn.execute(
            "SELECT * FROM pluggy_account_links WHERE user_id = ? AND pluggy_account_id = ?",
            (current_user_id, pluggy_account_id),
        ).fetchone()
        if existing:
            full_sync_done = existing["full_sync_done"] if existing["since"] == since else 0
            conn.execute(
                """
                UPDATE pluggy_account_links
                SET item_id = ?, pluggy_account_type = ?, name = ?, account_id = ?, card_id = ?,
                    since = ?, full_sync_done = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    item["item_id"], account_type, name, account_id, card_id, since,
                    full_sync_done, existing["id"], current_user_id,
                ),
            )
            status = 200
        else:
            conn.execute(
                """
                INSERT INTO pluggy_account_links
                (id, user_id, item_id, pluggy_account_id, pluggy_account_type, name,
                 account_id, card_id, since)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id(), current_user_id, item["item_id"], pluggy_account_id, account_type,
                    name, account_id, card_id, since,
                ),
            )
            status = 201
        link = next(
            row for row in serialize_links(conn, current_user_id)
            if row["pluggy_account_id"] == pluggy_account_id
        )
    return jsonify(link), status


@bp.route("/api/pluggy/sync", methods=["POST"])
@token_required
def pluggy_sync(current_user_id):
    """Sincroniza agora. Sem `force`, no maximo uma vez a cada poucos minutos."""
    payload = request.get_json(silent=True) or {}
    force = bool(payload.get("force")) if isinstance(payload, dict) else False
    return jsonify(sync_pluggy(current_user_id, force=force)), 200


@bp.route("/api/pluggy/review", methods=["GET"])
@token_required
def pluggy_review(current_user_id):
    with get_db() as conn:
        body = review_items(conn, current_user_id)
    return jsonify(body), 200


@bp.route("/api/pluggy/review/<ledger_id>", methods=["POST"])
@token_required
def pluggy_review_decide(current_user_id, ledger_id):
    """Possivel duplicata: `attach` (e este lancamento, `target_id`), `insert`
    (lancar separado) ou `dismiss` (ignorar a transacao do banco)."""
    payload = parse_json_body()
    action = str(payload.get("action") or "").strip().lower() if isinstance(payload, dict) else ""
    target_id = str(payload.get("target_id") or "").strip() if isinstance(payload, dict) else ""
    with get_db() as conn:
        try:
            row = resolve_review(conn, current_user_id, ledger_id, action, target_id or None)
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404
        except ValidationError as exc:
            return validation_error(str(exc))
        body = serialize_ledger(conn, current_user_id, row)
    return jsonify(body), 200
