"""Revisar (045): o que gravou sozinho espera o dono dizer "e meu" e a categoria.

As regras moram em services/review.py; o Extrato le a lista e confirma um a um
(ou todos de uma vez, com as categorias que ja tem).
"""

from flask import Blueprint, jsonify

from auth import token_required
from db import get_db
from services import auto_record, inbox, review
from validators import ValidationError, parse_json_body, validation_error

bp = Blueprint("review", __name__)


@bp.route("/api/review", methods=["GET"])
@token_required
def review_queue(current_user_id):
    """{items, count, waiting}: do mais novo para o mais antigo. Antes, o que
    esperava o prazo (o aviso do Samsung sem o do banco, o Pix sem par) grava.
    `waiting`: o que nao grava sozinho e fica no Aprovar (a transferencia entre
    contas do dono com uma ponta so, outra moeda; tudo, com o interruptor
    desligado)."""
    with get_db() as conn:
        auto_record.record_due(conn, current_user_id)
        items = review.queue(conn, current_user_id)
        waiting = inbox.pending_count(conn, current_user_id)
    return jsonify({"items": items, "count": len(items), "waiting": waiting}), 200


@bp.route("/api/review", methods=["POST"])
@token_required
def confirm_review(current_user_id):
    """`items`: [{table: transactions|cc_expenses, id, category_id?}]. Tudo ou
    nada: um id que nao existe recusa o lote (404)."""
    payload = parse_json_body()
    raw_items = payload.get("items") if isinstance(payload, dict) else None
    with get_db() as conn:
        try:
            reviewed = review.review_items(conn, current_user_id, raw_items)
        except LookupError as exc:
            conn.rollback()
            return jsonify({"error": str(exc)}), 404
        except ValidationError as exc:
            conn.rollback()
            return validation_error(str(exc))
        remaining = review.count(conn, current_user_id)
    return jsonify({"reviewed": reviewed, "count": remaining}), 200
