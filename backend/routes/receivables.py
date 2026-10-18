"""A receber (`/api/receivables`, 032): a parte dos outros nas despesas, regras em services/sharing.py.

O dono marca a despesa (ou a compra no cartao) como de outra pessoa, com o
nome dela, ao editar; ela fica aqui pendente ate o dono dizer que a pessoa
pagou. Marcar como pago nao grava dinheiro: o Pix que chega e um lancamento
proprio.
"""

from flask import Blueprint, jsonify, request

from auth import token_required
from db import get_db
from services.sharing import list_receivables, settle_receivables
from validators import ValidationError, parse_json_body, validation_error

bp = Blueprint("receivables", __name__)


@bp.route("/api/receivables", methods=["GET"])
@token_required
def receivables(current_user_id):
    include_settled = str(request.args.get("include_settled", "")).lower() in ("1", "true", "sim")
    with get_db() as conn:
        items = list_receivables(conn, current_user_id, include_settled=include_settled)
    return jsonify(items), 200


def id_list(payload, key):
    raw = payload.get(key, [])
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValidationError("Informe uma lista de ids.")
    return [str(item).strip() for item in raw if str(item).strip()]


@bp.route("/api/receivables/settle", methods=["POST"])
@token_required
def settle(current_user_id):
    payload = parse_json_body()
    try:
        transaction_ids = id_list(payload, "transaction_ids")
        cc_expense_ids = id_list(payload, "cc_expense_ids")
        if not transaction_ids and not cc_expense_ids:
            raise ValidationError("Informe ao menos um item.")
        settled = payload.get("settled", True)
        if not isinstance(settled, bool):
            raise ValidationError("settled deve ser verdadeiro ou falso.")
    except ValidationError as exc:
        return validation_error(str(exc))
    with get_db() as conn:
        changed = settle_receivables(conn, current_user_id, transaction_ids, cc_expense_ids, settled)
    return jsonify({"updated": changed}), 200
