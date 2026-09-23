"""Saude do app e manutencao do banco (status, backup manual)."""

from flask import Blueprint, jsonify, request

import export_csv
from auth import token_required
from db import create_database_backup, database_status, prune_database_backups
from services.health import check_integrations
from applog import get_logger

logger = get_logger(__name__)

bp = Blueprint("system", __name__)


@bp.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "ok",
        "database": "sqlite",
        "journal_mode": database_status()["journal_mode"],
    }), 200


@bp.route("/api/database/status", methods=["GET"])
@token_required
def get_database_status(current_user_id):
    return jsonify(database_status()), 200


@bp.route("/api/database/backups", methods=["POST"])
@token_required
def backup_database(current_user_id):
    try:
        backup = create_database_backup()
        backup["pruned"] = prune_database_backups()
        return jsonify(backup), 201
    except Exception as exc:
        logger.exception(f"Erro ao criar backup SQLite: {exc}")
        return jsonify({"error": "Nao foi possivel criar o backup do banco."}), 500


@bp.route("/api/exports/columns", methods=["GET"])
@token_required
def export_columns(current_user_id):
    """Colunas de cada exportacao, na ordem padrao, para o seletor do cliente."""
    return jsonify(export_csv.column_catalog()), 200


@bp.route("/api/health/integrations", methods=["GET"])
@token_required
def integrations_health(current_user_id):
    """Teste ativo de yfinance, brapi e BCB (cache de 10 min; ?refresh=1 refaz)."""
    force = str(request.args.get("refresh", "")).lower() in ("1", "true", "yes")
    return jsonify(check_integrations(force=force)), 200
