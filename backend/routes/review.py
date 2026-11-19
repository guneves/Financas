"""Revisar (045): o que gravou sozinho espera o dono dizer "e meu" e a categoria.

As regras moram em services/review.py; o Extrato le a lista e confirma um a um
(ou todos de uma vez, com as categorias que ja tem).
"""

import time
from datetime import timedelta

from flask import Blueprint, jsonify, request

from auth import token_required
from dates import local_today
from db import get_db
from services import auto_decisions, auto_record, auto_undo, open_finance_auto, review
from validators import ValidationError, parse_json_body, validation_error

bp = Blueprint("review", __name__)


@bp.route("/api/review", methods=["GET"])
@token_required
def review_queue(current_user_id):
    """{items, count, waiting}: do mais novo para o mais antigo. Antes, o que
    esperava o prazo (o aviso do Samsung sem o do banco, o Pix sem par) grava.
    `waiting`: o que nao gravou sozinho e a Pluggy, ja atualizada, nao
    identificou (a transferencia com uma ponta so, outra moeda; tudo, com o
    interruptor desligado). O que ainda espera a Pluggy atualizar nao conta."""
    with get_db() as conn:
        auto_record.record_due(conn, current_user_id)
        items = review.queue(conn, current_user_id)
        waiting = open_finance_auto.flagged_count(conn, current_user_id, time.time())
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


@bp.route("/api/review/auto", methods=["GET"])
@token_required
def automatic_decisions(current_user_id):
    """{items, counts}: as decisoes que o app tomou sozinho (058), da mais nova
    para a mais antiga, com o que cada "Desfazer" devolve. `counts`: as nao
    desfeitas, por regra. Filtros: `kinds` (separadas por virgula; `conference`
    = as da Conferencia, CONFERENCE_KINDS) e `days` (1-365: as decididas nos
    ultimos N dias)."""
    kinds = None
    raw_kinds = (request.args.get("kinds") or "").strip()
    if raw_kinds:
        kinds = []
        for kind in (part.strip() for part in raw_kinds.split(",") if part.strip()):
            if kind == "conference":
                kinds.extend(auto_decisions.CONFERENCE_KINDS)
            elif kind in auto_decisions.KINDS:
                kinds.append(kind)
            else:
                return validation_error(f"Regra desconhecida: {kind}.")
    since = None
    raw_days = (request.args.get("days") or "").strip()
    if raw_days:
        try:
            days = int(raw_days)
        except ValueError:
            days = 0
        if not 1 <= days <= 365:
            return validation_error("Informe 'days' entre 1 e 365.")
        since = (local_today() - timedelta(days=days)).isoformat()
    with get_db() as conn:
        items = auto_decisions.recent(conn, current_user_id, since=since, kinds=kinds)
        counts = auto_decisions.counts(conn, current_user_id, since=since)
    if kinds:
        counts = {kind: total for kind, total in counts.items() if kind in kinds}
    return jsonify({"items": items, "counts": counts}), 200


@bp.route("/api/review/auto/<decision_id>/undo", methods=["POST"])
@token_required
def undo_automatic_decision(current_user_id, decision_id):
    """Desfaz uma decisao automatica; a regra nao decide de novo o mesmo
    lancamento. 404 se nao existe, 409 se ja foi desfeita."""
    with get_db() as conn:
        try:
            decision = auto_undo.undo(conn, current_user_id, decision_id)
        except LookupError as exc:
            return jsonify({"error": str(exc)}), 404
        except (auto_undo.AlreadyUndone, auto_undo.NotUndoable) as exc:
            return jsonify({"error": str(exc)}), 409
    return jsonify(decision), 200
