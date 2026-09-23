"""Autenticacao: JWT HS256 feito a mao e o decorator `token_required`.

`token_required` passa o id do usuario como primeiro argumento da rota
(`current_user_id`) — toda consulta da rota filtra por ele.
"""

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import jsonify, request

from config import JWT_EXP_DAYS, JWT_SECRET
from db import get_db


def create_token(user_id):
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "exp": int((datetime.now(timezone.utc) + timedelta(days=JWT_EXP_DAYS)).timestamp()),
    }
    header_part = base64url_encode(json.dumps(header, separators=(",", ":")).encode())
    payload_part = base64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_part}.{payload_part}".encode()
    signature = hmac.new(JWT_SECRET.encode(), signing_input, hashlib.sha256).digest()
    return f"{header_part}.{payload_part}.{base64url_encode(signature)}"


def base64url_encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def base64url_decode(value):
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def decode_token(token):
    try:
        header_part, payload_part, signature_part = token.split(".")
    except ValueError as exc:
        raise ValueError("Token invalido.") from exc

    signing_input = f"{header_part}.{payload_part}".encode()
    expected_signature = hmac.new(JWT_SECRET.encode(), signing_input, hashlib.sha256).digest()
    provided_signature = base64url_decode(signature_part)

    if not hmac.compare_digest(expected_signature, provided_signature):
        raise ValueError("Token invalido.")

    payload = json.loads(base64url_decode(payload_part).decode())
    if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
        raise TimeoutError("Sessao expirada.")

    return payload


PUBLIC_USER_COLUMNS = ("id", "email", "username", "created_at")
USERNAME_MAX_LENGTH = 40


def fetch_user_by_id(user_id):
    with get_db() as conn:
        return conn.execute(
            f"SELECT {', '.join(PUBLIC_USER_COLUMNS)} FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()


def normalize_username(value):
    """Devolve (username, erro). Espacos repetidos viram um so."""
    username = " ".join(str(value or "").split())
    if len(username) < 2:
        return None, "Informe um nome de usuario com pelo menos 2 caracteres."
    if len(username) > USERNAME_MAX_LENGTH:
        return None, f"O nome de usuario pode ter no maximo {USERNAME_MAX_LENGTH} caracteres."
    if "@" in username:
        return None, "O nome de usuario nao pode ser um e-mail."
    return username, None


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"message": "Token ausente ou invalido."}), 401

        token = header.split(" ", 1)[1]
        try:
            payload = decode_token(token)
            user_id = payload.get("sub")
            if not user_id or not fetch_user_by_id(user_id):
                return jsonify({"message": "Usuario nao encontrado."}), 401
        except TimeoutError as exc:
            return jsonify({"message": str(exc)}), 401
        except Exception:
            return jsonify({"message": "Token invalido."}), 401

        return f(user_id, *args, **kwargs)
    return decorated
