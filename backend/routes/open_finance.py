"""Open Finance pela Pluggy (Ajustes › Open Finance; regras em services/open_finance.py).

Conectar e so na web (o widget Pluggy Connect); o APK le a lista e pode pedir
"Atualizar". Nada aqui grava lancamento: o que a Pluggy traz vai para o
Aprovar. As credenciais da Pluggy nunca saem do servidor — so o connect token,
de 30 minutos, que so serve para abrir o widget.
"""

from flask import Blueprint, jsonify

from auth import token_required
from db import get_db
from services import open_finance
from validators import ValidationError, parse_json_body, validation_error

bp = Blueprint("open_finance", __name__)


def _not_configured():
    return jsonify({"error": "Open Finance desligado: o servidor nao tem as credenciais da Pluggy."}), 503


def _pluggy_failure(exc):
    # A mensagem da Pluggy (ex.: o limite de CPF do plano) vai para a tela.
    status = 502 if exc.network or (exc.status or 0) >= 500 else 400
    return jsonify({"error": str(exc), "code": exc.code}), status


def _run(action):
    try:
        return action()
    except open_finance.NotConfigured:
        return _not_configured()
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValidationError as exc:
        return validation_error(str(exc))
    except open_finance.PluggyError as exc:
        return _pluggy_failure(exc)


@bp.route("/api/open-finance", methods=["GET"])
@token_required
def open_finance_overview(current_user_id):
    """`configured`, a janela da primeira busca e as conexoes com as contas
    (mapeamento, sugestao, saldo da Pluggy ao lado do do app)."""
    return jsonify(open_finance.list_view(current_user_id)), 200


@bp.route("/api/open-finance/settings", methods=["PATCH"])
@token_required
def open_finance_settings(current_user_id):
    payload = parse_json_body()
    if not isinstance(payload, dict) or "first_sync_days" not in payload:
        return validation_error("Envie first_sync_days.")

    def action():
        with get_db() as conn:
            days = open_finance.set_first_sync_days(conn, current_user_id, payload["first_sync_days"])
        return jsonify({"first_sync_days": days}), 200

    return _run(action)


@bp.route("/api/open-finance/connect-token", methods=["POST"])
@token_required
def open_finance_connect_token(current_user_id):
    """O token do widget. `item_id` (uma conexao nossa): o widget atualiza a
    conexao (senha nova, MFA) em vez de criar outra."""
    payload = parse_json_body()
    item_id = payload.get("item_id") if isinstance(payload, dict) else None

    def action():
        token = open_finance.connect_token(current_user_id, item_id or None)
        return jsonify({"access_token": token}), 200

    return _run(action)


@bp.route("/api/open-finance/items", methods=["POST"])
@token_required
def open_finance_register(current_user_id):
    """O widget conectou: `pluggy_item_id` e o itemId que ele devolveu."""
    payload = parse_json_body()
    if not isinstance(payload, dict):
        return validation_error("Envie um objeto JSON.")

    def action():
        of_item_id = open_finance.register_item(current_user_id, payload.get("pluggy_item_id"))
        body = open_finance.list_view(current_user_id)
        body["item_id"] = of_item_id
        return jsonify(body), 201

    return _run(action)


@bp.route("/api/open-finance/items/<item_id>/sync", methods=["POST"])
@token_required
def open_finance_sync(current_user_id, item_id):
    """"Atualizar": pede dados novos ao banco (se nao pediu ha pouco e o item
    nao espera o dono) e puxa para o Aprovar."""

    def action():
        result = open_finance.sync_item(current_user_id, item_id, request_update=True)
        body = open_finance.list_view(current_user_id)
        body["result"] = result
        return jsonify(body), 200

    return _run(action)


@bp.route("/api/open-finance/items/<item_id>", methods=["DELETE"])
@token_required
def open_finance_disconnect(current_user_id, item_id):
    """Desconectar: `confirm` com o nome do banco. Apaga o item na Pluggy e
    arquiva o nosso; o que ja foi lancado fica."""
    payload = parse_json_body()
    confirm = payload.get("confirm") if isinstance(payload, dict) else None

    def action():
        open_finance.disconnect(current_user_id, item_id, confirm)
        return jsonify(open_finance.list_view(current_user_id)), 200

    return _run(action)


@bp.route("/api/open-finance/accounts/<account_id>", methods=["PUT"])
@token_required
def open_finance_map(current_user_id, account_id):
    """Mapeia uma conta da Pluggy: `account_id` (BANK) ou `card_id` (CREDIT); null desliga."""
    payload = parse_json_body()

    def action():
        result = open_finance.map_account(current_user_id, account_id, payload)
        body = open_finance.list_view(current_user_id)
        body["placed"] = result["placed"]
        return jsonify(body), 200

    return _run(action)
