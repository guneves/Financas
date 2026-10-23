"""Inicio, avisos e faturas: as leituras que o cliente montava do historico.

GET /api/home (saldo, contas, fluxo do mes, proxima fatura), GET /api/attention
("Precisa de atencao") e GET /api/cc-invoices (a tela Cartoes). As regras
moram em services/home.py, services/attention.py e services/card_invoices.py;
aqui so se le e serializa.
"""

from flask import Blueprint, jsonify, request

from auth import token_required
from db import get_db
from services.attention import build_attention
from services.card_invoices import build_cc_invoices
from services.home import build_home, parse_months, prepare_reads
from services.invoices import local_today
from validators import ValidationError, validation_error

bp = Blueprint("home", __name__)


@bp.route("/api/home", methods=["GET"])
@token_required
def home(current_user_id):
    try:
        months = parse_months(request.args.get("months"))
    except ValidationError as exc:
        return validation_error(str(exc))
    with get_db() as conn:
        return jsonify(build_home(conn, current_user_id, months)), 200


@bp.route("/api/attention", methods=["GET"])
@token_required
def attention(current_user_id):
    with get_db() as conn:
        return jsonify(build_attention(conn, current_user_id)), 200


@bp.route("/api/cc-invoices", methods=["GET"])
@token_required
def cc_invoices(current_user_id):
    with get_db() as conn:
        today = local_today()
        prepare_reads(conn, current_user_id, today)
        return jsonify(build_cc_invoices(conn, current_user_id, today)), 200
