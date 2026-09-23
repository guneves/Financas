"""Saude do app e manutencao do banco (status, backup manual)."""

from flask import Blueprint, jsonify

from auth import token_required
from db import create_database_backup, database_status, prune_database_backups

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
        print(f"Erro ao criar backup SQLite: {exc}")
        return jsonify({"error": "Nao foi possivel criar o backup do banco."}), 500
