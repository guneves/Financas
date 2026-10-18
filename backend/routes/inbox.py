"""Aprovar: o que o celular (notificacoes dos bancos) traz.

As regras moram em services/inbox.py (guardar e juntar) e
services/inbox_decisions.py (o que o dono decide). Tudo fica no servidor: o
celular e o computador leem a mesma lista, e uma decisao tomada num aparece no
outro na proxima leitura. Cada mudanca leva a `version` do item; com a versao
velha a resposta e 409, com o item como esta agora.
"""

from flask import Blueprint, jsonify, request

from auth import token_required
from db import get_db
from services import inbox, inbox_decisions
from validators import ValidationError, parse_json_body, require_id_list, validation_error

bp = Blueprint("inbox", __name__)


def _serialize(conn, current_user_id, row):
    item = inbox.serialize_item(conn, current_user_id, row)
    item["target"] = inbox_decisions.serialize_target(conn, current_user_id, item.get("target_table"), item.get("target_id"))
    return item


def _decide(current_user_id, item_id, action):
    payload = parse_json_body()
    if not isinstance(payload, dict):
        return validation_error("Envie um objeto JSON.")
    with get_db() as conn:
        try:
            row = action(conn, current_user_id, item_id, payload)
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404
        except inbox_decisions.Conflict as exc:
            conn.rollback()
            return jsonify({"error": str(exc), "item": _serialize(conn, current_user_id, exc.item_row)}), 409
        except ValidationError as exc:
            conn.rollback()
            return validation_error(str(exc))
        body = _serialize(conn, current_user_id, row)
        body["pending_count"] = inbox.pending_count(conn, current_user_id)
    return jsonify(body), 200


@bp.route("/api/inbox", methods=["GET"])
@token_required
def list_inbox(current_user_id):
    """`view=pending` (padrao) ou `decided` (o que ja foi decidido, mais recente primeiro)."""
    view = request.args.get("view", "pending")
    if view not in ("pending", "decided"):
        return validation_error("Visao invalida.")
    with get_db() as conn:
        items = inbox.list_items(conn, current_user_id, view)
        if view == "decided":
            for item in items:
                item["target"] = inbox_decisions.serialize_target(
                    conn, current_user_id, item.get("target_table"), item.get("target_id")
                )
        body = {"items": items, "pending_count": inbox.pending_count(conn, current_user_id)}
    return jsonify(body), 200


@bp.route("/api/inbox/count", methods=["GET"])
@token_required
def inbox_count(current_user_id):
    with get_db() as conn:
        count = inbox.pending_count(conn, current_user_id)
    return jsonify({"pending_count": count}), 200


@bp.route("/api/inbox/detections", methods=["POST"])
@token_required
def post_detections(current_user_id):
    """As notificacoes que os parsers do celular leram: so os campos lidos,
    nunca o texto. Reenviar a mesma chave nao duplica (status "known")."""
    payload = parse_json_body()
    detections = payload.get("detections") if isinstance(payload, dict) else None
    with get_db() as conn:
        try:
            results = inbox.ingest_detections(conn, current_user_id, detections)
        except ValidationError as exc:
            return validation_error(str(exc))
    return jsonify({"results": results}), 200


@bp.route("/api/inbox/approve-ready", methods=["POST"])
@token_required
def approve_ready(current_user_id):
    """"Aprovar todos": aprova os itens prontos da lista; o resto fica."""
    payload = parse_json_body()
    try:
        ids = require_id_list(payload if isinstance(payload, dict) else {}, "ids")
    except ValidationError as exc:
        return validation_error(str(exc))
    with get_db() as conn:
        body = inbox_decisions.approve_ready(conn, current_user_id, ids)
        body["pending_count"] = inbox.pending_count(conn, current_user_id)
    return jsonify(body), 200


@bp.route("/api/inbox/settings", methods=["GET", "PATCH"])
@token_required
def inbox_settings(current_user_id):
    """`always_ask`: "Sempre perguntar a conta/cartao" (desligado por padrao).
    Ligado, todo item pede confirmar a conta/cartao, inclusive o lembrado, e
    "Aprovar todos" nao leva nenhum."""
    if request.method == "PATCH":
        payload = parse_json_body()
        if not isinstance(payload, dict) or not isinstance(payload.get("always_ask"), bool):
            return validation_error("Envie always_ask como true ou false.")
        with get_db() as conn:
            inbox.set_always_ask(conn, current_user_id, payload["always_ask"])
    with get_db() as conn:
        body = {"always_ask": inbox.always_ask(conn, current_user_id)}
    return jsonify(body), 200


@bp.route("/api/inbox/hints", methods=["GET"])
@token_required
def list_hints(current_user_id):
    with get_db() as conn:
        hints = inbox.list_hints(conn, current_user_id)
    return jsonify(hints), 200


@bp.route("/api/inbox/hints/<hint_id>", methods=["DELETE"])
@token_required
def delete_hint(current_user_id, hint_id):
    """Esquece uma escolha lembrada; o proximo item dessa chave volta a perguntar.
    Nenhum lancamento muda."""
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM inbox_hints WHERE id = ? AND user_id = ?",
            (hint_id, current_user_id),
        )
    if not cursor.rowcount:
        return jsonify({"deleted": False}), 404
    return jsonify({"deleted": True}), 200


@bp.route("/api/inbox/<item_id>", methods=["GET", "PATCH"])
@token_required
def inbox_item(current_user_id, item_id):
    if request.method == "GET":
        with get_db() as conn:
            row = inbox.fetch_item(conn, current_user_id, item_id)
            if not row:
                return jsonify({"error": "Item nao encontrado."}), 404
            body = _serialize(conn, current_user_id, row)
        return jsonify(body), 200
    return _decide(current_user_id, item_id, inbox_decisions.update_item)


@bp.route("/api/inbox/<item_id>/approve", methods=["POST"])
@token_required
def approve(current_user_id, item_id):
    """Grava o lancamento do rascunho (com as correcoes enviadas junto). Com
    `candidate` {table, id}: o movimento e esse lancamento que ja existe.
    `remember` (padrao true) guarda a escolha de cartao/conta."""
    return _decide(current_user_id, item_id, inbox_decisions.approve_item)


@bp.route("/api/inbox/<item_id>/deny", methods=["POST"])
@token_required
def deny(current_user_id, item_id):
    return _decide(current_user_id, item_id, inbox_decisions.deny_item)


@bp.route("/api/inbox/<item_id>/restore", methods=["POST"])
@token_required
def restore(current_user_id, item_id):
    return _decide(current_user_id, item_id, inbox_decisions.restore_item)


@bp.route("/api/inbox/<item_id>/split", methods=["POST"])
@token_required
def split(current_user_id, item_id):
    """"Nao e a mesma": `source` (notification) e `source_id` saem
    para um item proprio."""
    payload = parse_json_body()
    if not isinstance(payload, dict):
        return validation_error("Envie um objeto JSON.")
    with get_db() as conn:
        try:
            row, new_row = inbox_decisions.split_item(conn, current_user_id, item_id, payload)
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404
        except inbox_decisions.Conflict as exc:
            conn.rollback()
            return jsonify({"error": str(exc), "item": _serialize(conn, current_user_id, exc.item_row)}), 409
        except ValidationError as exc:
            conn.rollback()
            return validation_error(str(exc))
        body = {
            "item": _serialize(conn, current_user_id, row),
            "new_item": _serialize(conn, current_user_id, new_row),
            "pending_count": inbox.pending_count(conn, current_user_id),
        }
    return jsonify(body), 200
