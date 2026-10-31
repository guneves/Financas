"""Open Finance pela Pluggy (Ajustes › Open Finance; regras em services/open_finance.py).

Conectar e so na web (o widget Pluggy Connect); o APK le a lista e pode pedir
"Atualizar" (so le o que a Pluggy ja tem: nunca PATCH /items). O que a Pluggy
traz vai para o Aprovar, ou, com "Gravar sozinho" ligado (044), vira
lancamento sem esperar. O historico e previa -> confirmacao. As credenciais da
Pluggy nunca saem do servidor — so o connect token, de 30 minutos, que so
serve para abrir o widget.
"""

from flask import Blueprint, jsonify, request

from auth import token_required
from db import get_db
from services import open_finance, open_finance_resolve
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


@bp.route("/api/open-finance/settings", methods=["GET", "PATCH"])
@token_required
def open_finance_settings(current_user_id):
    """As preferencias do Open Finance, no servidor (o celular e o computador
    concordam): `first_sync_days` (1-365), `sync_hours` (0 ou 6-24),
    `include_pending`, `auto_record` (gravar sozinho; ligar e recusado com
    conta sem destino ou conexao sem pull nas ultimas 48 h). PATCH parcial;
    `auto_sync_available` e `auto_record_blockers` so se leem, e
    `ignore_notifications` (sempre true) e so para um APK antigo."""
    if request.method == "GET":
        with get_db() as conn:
            return jsonify(open_finance.settings(conn, current_user_id)), 200
    payload = parse_json_body()

    def action():
        with get_db() as conn:
            body = open_finance.update_settings(conn, current_user_id, payload)
        return jsonify(body), 200

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
    """"Atualizar": le (GET) o que a Pluggy ja trouxe do banco e puxa para o
    Aprovar (ou grava, com "Gravar sozinho")."""

    def action():
        result = open_finance.sync_item(current_user_id, item_id)
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
    """Mapeia uma conta da Pluggy: `account_id` (BANK) ou `card_id` (CREDIT); null
    desliga; `{"ignore": true}` e "nao usar"."""
    payload = parse_json_body()

    def action():
        result = open_finance.map_account(current_user_id, account_id, payload)
        body = open_finance.list_view(current_user_id)
        body["placed"] = result["placed"]
        return jsonify(body), 200

    return _run(action)


@bp.route("/api/open-finance/check/record", methods=["POST"])
@token_required
def open_finance_check_record(current_user_id):
    """Conferencia, "Lancar": `row_id` (um movimento so no banco) vira lancamento."""
    payload = parse_json_body()
    if not isinstance(payload, dict):
        return validation_error("Envie um objeto JSON.")

    def action():
        with get_db() as conn:
            result = open_finance_resolve.record_bank_row(conn, current_user_id, payload.get("row_id"))
        body = open_finance.list_view(current_user_id)
        body["recorded"] = result
        return jsonify(body), 200

    return _run(action)


@bp.route("/api/open-finance/check/confirm", methods=["POST"])
@token_required
def open_finance_check_confirm(current_user_id):
    """Conferencia, "Aconteceu": `table` e `id` de um lancamento so no app;
    `undo: true` desfaz."""
    payload = parse_json_body()
    if not isinstance(payload, dict):
        return validation_error("Envie um objeto JSON.")

    def action():
        with get_db() as conn:
            open_finance_resolve.confirm_app_row(
                conn, current_user_id, payload.get("table"), payload.get("id"), payload.get("undo") is True,
            )
        return jsonify(open_finance.list_view(current_user_id)), 200

    return _run(action)


@bp.route("/api/open-finance/history/preview", methods=["POST"])
@token_required
def open_finance_history_preview(current_user_id):
    """O historico dos ultimos `days` dias (padrao 365), contado por conta,
    sem gravar nada: linked, to_link, to_record, waiting, covered, app_only."""
    payload = parse_json_body()
    days = payload.get("days") if isinstance(payload, dict) else None

    def action():
        return jsonify(open_finance.history_preview(current_user_id, days)), 200

    return _run(action)


@bp.route("/api/open-finance/history/apply", methods=["POST"])
@token_required
def open_finance_history_apply(current_user_id):
    """Aplica o historico (`confirm: true`, com "Gravar sozinho" ligado): liga
    o que ja existe, grava o resto; nada digitado e apagado."""
    payload = parse_json_body()
    if not isinstance(payload, dict):
        return validation_error("Envie um objeto JSON.")

    def action():
        result = open_finance.history_apply(current_user_id, payload.get("days"), payload.get("confirm"))
        body = open_finance.list_view(current_user_id)
        body["history"] = result
        return jsonify(body), 200

    return _run(action)
