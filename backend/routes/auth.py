"""Cadastro, login e perfil (`/api/auth/*`)."""

import sqlite3

from flask import Blueprint, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from auth import (
    PUBLIC_USER_COLUMNS,
    create_token,
    fetch_user_by_id,
    normalize_username,
    token_required,
)
from config import ALLOW_SIGNUP
from db import get_db, new_id, row_to_dict
from services.accounts import ensure_default_account, seed_default_categories
from validators import parse_json_body

bp = Blueprint("auth", __name__)


@bp.route("/api/auth/signup", methods=["POST"])
def signup():
    payload = parse_json_body()
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))

    if not email or "@" not in email or len(password) < 6:
        return jsonify({"error": "Informe email valido e senha com pelo menos 6 caracteres."}), 400

    username, username_error = normalize_username(payload.get("username"))
    if username_error:
        return jsonify({"error": username_error}), 400

    user_id = new_id()
    try:
        with get_db() as conn:
            if not ALLOW_SIGNUP and conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                return jsonify({
                    "error": "O cadastro esta fechado neste servidor. Entre com a conta existente."
                }), 403
            conn.execute(
                "INSERT INTO users (id, email, username, password_hash) VALUES (?, ?, ?, ?)",
                (user_id, email, username, generate_password_hash(password)),
            )
            ensure_default_account(conn, user_id)
            seed_default_categories(conn, user_id)
            user = conn.execute(
                f"SELECT {', '.join(PUBLIC_USER_COLUMNS)} FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Ja existe uma conta com este email."}), 409

    return jsonify({"user": row_to_dict(user), "access_token": create_token(user_id)}), 201


@bp.route("/api/auth/login", methods=["POST"])
def login():
    payload = parse_json_body()
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))

    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Email ou senha invalidos."}), 401

    public_user = {key: user[key] for key in PUBLIC_USER_COLUMNS}
    return jsonify({"user": public_user, "access_token": create_token(user["id"])}), 200


@bp.route("/api/auth/me", methods=["GET", "PATCH"])
@token_required
def me(current_user_id):
    if request.method == "PATCH":
        payload = parse_json_body()
        username, username_error = normalize_username(payload.get("username"))
        if username_error:
            return jsonify({"error": username_error}), 400
        with get_db() as conn:
            conn.execute(
                "UPDATE users SET username = ? WHERE id = ?",
                (username, current_user_id),
            )

    return jsonify({"user": row_to_dict(fetch_user_by_id(current_user_id))}), 200
