"""Alocacao alvo da carteira (`/api/allocation`), regras em services/allocation.py.

As metas sao um plano: o PUT troca o conjunto inteiro (as somas so fecham com
todas as linhas juntas) e nao ha confirmacao — nenhum lancamento muda.

Aqui tambem mora `/api/investments/contributions` (aportes x resgates por mes,
services/contributions.py): leitura analitica da carteira, como a alocacao.
"""

from flask import Blueprint, jsonify, request

from asset_classes import parse_asset_class_filter
from auth import token_required
from services.allocation import build_allocation, replace_targets
from services.contributions import DEFAULT_MONTHS, build_contributions
from validators import ValidationError, parse_json_body, safe_float, validation_error

bp = Blueprint("allocation", __name__)


@bp.route("/api/allocation", methods=["GET"])
@token_required
def allocation(current_user_id):
    """Atual x meta por classe e por ativo; `?contribution=` sugere o aporte."""
    contribution = safe_float(request.args.get("contribution"), 0.0)
    if contribution < 0:
        return validation_error("O aporte nao pode ser negativo.")
    return jsonify(build_allocation(current_user_id, contribution)), 200


@bp.route("/api/allocation/targets", methods=["PUT"])
@token_required
def allocation_targets(current_user_id):
    payload = parse_json_body()
    try:
        replace_targets(current_user_id, payload)
    except ValidationError as exc:
        return validation_error(str(exc))
    return jsonify(build_allocation(current_user_id)), 200


@bp.route("/api/investments/contributions", methods=["GET"])
@token_required
def investment_contributions(current_user_id):
    """Aportes x resgates por mes: `?months=` (12, ate 60) e `?asset_class=`."""
    return jsonify(build_contributions(
        current_user_id,
        request.args.get("months", DEFAULT_MONTHS),
        parse_asset_class_filter(request.args.get("asset_class")),
    )), 200
