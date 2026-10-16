"""Plano do mes (`/api/monthly-plan`), regras em services/monthly_plan.py.

O plano e um plano, nao um registro: o DELETE e real e sem guarda — apagar nao
desfaz nenhum lancamento (mesma natureza de /api/budgets e /api/goals).
"""

from flask import Blueprint, jsonify, request

from auth import token_required
from services.monthly_plan import (
    build_monthly_plan,
    delete_monthly_plan,
    parse_month_arg,
    save_monthly_plan,
)
from validators import ValidationError, parse_json_body, validation_error

bp = Blueprint("monthly_plan", __name__)


@bp.route("/api/monthly-plan", methods=["GET", "PUT", "DELETE"])
@token_required
def monthly_plan(current_user_id):
    if request.method == "PUT":
        try:
            return jsonify(save_monthly_plan(current_user_id, parse_json_body())), 200
        except ValidationError as exc:
            return validation_error(str(exc))

    try:
        month = parse_month_arg(request.args.get("month"))
    except ValidationError as exc:
        return validation_error(str(exc))
    if request.method == "DELETE":
        result = delete_monthly_plan(current_user_id, month)
        if result is None:
            return jsonify({"error": "Nenhum plano gravado neste mes."}), 404
        return jsonify(result), 200
    return jsonify(build_monthly_plan(current_user_id, month)), 200
