"""Metas financeiras (`/api/goals`), regras em services/goals.py.

Uma meta e um plano, nao um registro: o DELETE e real e sem guarda — apagar
nao desfaz nenhum lancamento (mesma natureza de /api/budgets).
"""

from flask import Blueprint, jsonify, request

from auth import token_required
from services.goals import create_goal, delete_goal, get_goal, list_goals, update_goal
from validators import ValidationError, parse_json_body, validation_error

bp = Blueprint("goals", __name__)


@bp.route("/api/goals", methods=["GET", "POST"])
@token_required
def goals(current_user_id):
    if request.method == "GET":
        return jsonify(list_goals(current_user_id)), 200
    try:
        item = create_goal(current_user_id, parse_json_body())
    except ValidationError as exc:
        return validation_error(str(exc))
    return jsonify(item), 201


@bp.route("/api/goals/<goal_id>", methods=["GET", "PATCH", "DELETE"])
@token_required
def goal_detail(current_user_id, goal_id):
    if request.method == "GET":
        item = get_goal(current_user_id, goal_id)
    elif request.method == "DELETE":
        if not delete_goal(current_user_id, goal_id):
            return jsonify({"error": "Meta nao encontrada."}), 404
        return jsonify({"deleted": True}), 200
    else:
        try:
            item = update_goal(current_user_id, goal_id, parse_json_body())
        except ValidationError as exc:
            return validation_error(str(exc))
    if item is None:
        return jsonify({"error": "Meta nao encontrada."}), 404
    return jsonify(item), 200
