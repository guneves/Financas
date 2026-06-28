import json
import os
import sqlite3
import urllib.request
import uuid
import base64
import calendar
import hashlib
import hmac
import math
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return False

try:
    import yfinance as yf
except ImportError:
    yf = None

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "finance.db"))
DATABASE_PATH = (
    RAW_DATABASE_PATH
    if os.path.isabs(RAW_DATABASE_PATH)
    else os.path.join(BASE_DIR, RAW_DATABASE_PATH)
)
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

try:
    JWT_EXP_DAYS = max(1, int(os.getenv("JWT_EXP_DAYS", "30")))
except ValueError:
    JWT_EXP_DAYS = 30

ALLOWED_TRANSACTION_TYPES = {"INCOME", "EXPENSE"}
ALLOWED_ASSET_CLASSES = {"STOCKS", "FIXED_INCOME", "REIT", "CATTLE", "OTHER"}
ALLOWED_CC_STATUS = {"OPEN", "PAID"}

app = Flask(__name__)
cors_origins = "*" if CORS_ORIGINS == "*" else [
    origin.strip() for origin in CORS_ORIGINS.split(",") if origin.strip()
] or "*"
CORS(app, resources={r"/api/*": {"origins": cors_origins}})


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount REAL NOT NULL CHECK (amount >= 0),
    date TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    type TEXT NOT NULL CHECK (type IN ('INCOME', 'EXPENSE')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_transactions_user_date
ON transactions(user_id, date DESC);

CREATE TABLE IF NOT EXISTS investments (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    asset_class TEXT NOT NULL CHECK (asset_class IN ('STOCKS', 'FIXED_INCOME', 'REIT', 'CATTLE', 'OTHER')),
    ticker_or_name TEXT NOT NULL,
    quantity REAL NOT NULL,
    average_price REAL NOT NULL CHECK (average_price >= 0),
    current_price REAL,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_investments_user_asset_class
ON investments(user_id, asset_class);

CREATE INDEX IF NOT EXISTS idx_investments_user_ticker
ON investments(user_id, ticker_or_name);

CREATE TABLE IF NOT EXISTS credit_cards (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    due_day INTEGER NOT NULL CHECK (due_day BETWEEN 1 AND 31),
    closing_day INTEGER NOT NULL CHECK (closing_day BETWEEN 1 AND 31),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(user_id, name)
);

CREATE INDEX IF NOT EXISTS idx_credit_cards_user_name
ON credit_cards(user_id, name);

CREATE TABLE IF NOT EXISTS cc_expenses (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    card_id TEXT NOT NULL REFERENCES credit_cards(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount >= 0),
    purchase_date TEXT NOT NULL,
    invoice_month INTEGER NOT NULL CHECK (invoice_month BETWEEN 1 AND 12),
    invoice_year INTEGER NOT NULL CHECK (invoice_year >= 2000),
    installment_info TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'PAID')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_cc_expenses_invoice
ON cc_expenses(user_id, invoice_year, invoice_month);

CREATE INDEX IF NOT EXISTS idx_cc_expenses_status
ON cc_expenses(user_id, status);
"""


def get_db():
    database_dir = os.path.dirname(os.path.abspath(DATABASE_PATH))
    if database_dir:
        os.makedirs(database_dir, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript(SCHEMA_SQL)


def new_id():
    return str(uuid.uuid4())


def row_to_dict(row):
    return dict(row) if row else None


def safe_float(value, default=0):
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


class ValidationError(ValueError):
    pass


def validation_error(message, status=400):
    return jsonify({"error": message}), status


def require_string(payload, key, label, max_length=255):
    value = str(payload.get(key, "") or "").strip()
    if not value:
        raise ValidationError(f"{label} e obrigatorio.")
    if len(value) > max_length:
        raise ValidationError(f"{label} deve ter no maximo {max_length} caracteres.")
    return value


def optional_string(payload, key, max_length=500):
    value = payload.get(key)
    if value is None:
        return ""
    value = str(value).strip()
    if len(value) > max_length:
        raise ValidationError(f"{key} deve ter no maximo {max_length} caracteres.")
    return value


def require_choice(payload, key, label, choices):
    value = str(payload.get(key, "") or "").strip().upper()
    if value not in choices:
        raise ValidationError(f"{label} invalido.")
    return value


def parse_number(payload, key, label, *, minimum=None, maximum=None, allow_zero=True):
    try:
        value = float(payload.get(key))
    except (TypeError, ValueError):
        raise ValidationError(f"{label} deve ser um numero valido.")

    if not math.isfinite(value):
        raise ValidationError(f"{label} deve ser um numero valido.")
    if minimum is not None and value < minimum:
        raise ValidationError(f"{label} deve ser maior ou igual a {minimum}.")
    if not allow_zero and value == 0:
        raise ValidationError(f"{label} deve ser maior que zero.")
    if maximum is not None and value > maximum:
        raise ValidationError(f"{label} deve ser menor ou igual a {maximum}.")
    return value


def parse_optional_number(payload, key, label, *, minimum=None, maximum=None):
    if key not in payload or payload.get(key) in (None, ""):
        return None
    return parse_number(payload, key, label, minimum=minimum, maximum=maximum)


def parse_int_number(payload, key, label, *, minimum=None, maximum=None):
    value = parse_number(payload, key, label, minimum=minimum, maximum=maximum)
    if not float(value).is_integer():
        raise ValidationError(f"{label} deve ser um numero inteiro.")
    return int(value)


def require_date(payload, key, label):
    value = require_string(payload, key, label, max_length=10)
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValidationError(f"{label} deve estar no formato AAAA-MM-DD.")
    return value


def require_id_list(payload, key="ids"):
    raw_ids = payload.get(key)
    if not isinstance(raw_ids, list):
        raise ValidationError("Informe uma lista de ids.")

    ids = [str(item).strip() for item in raw_ids if str(item).strip()]
    if not ids:
        raise ValidationError("Informe ao menos um id.")
    return ids


def ensure_credit_card_owner(conn, current_user_id, card_id):
    card = conn.execute(
        "SELECT id FROM credit_cards WHERE id = ? AND user_id = ?",
        (card_id, current_user_id),
    ).fetchone()
    if not card:
        raise ValidationError("Cartao nao encontrado.")


def parse_metadata_value(value):
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def encode_metadata(value):
    if value in (None, ""):
        return None
    return json.dumps(value) if isinstance(value, dict) else value


def serialize_investment(row):
    item = row_to_dict(row)
    if item:
        item["metadata"] = parse_metadata_value(item.get("metadata"))
    return item


def serialize_cc_expense(row):
    item = row_to_dict(row)
    if not item:
        return None

    card_name = item.pop("card_name", None)
    due_day = item.pop("card_due_day", None)
    closing_day = item.pop("card_closing_day", None)
    if card_name is not None:
        item["credit_cards"] = {
            "name": card_name,
            "due_day": due_day,
            "closing_day": closing_day,
        }
    return item


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


def fetch_user_by_id(user_id):
    with get_db() as conn:
        return conn.execute(
            "SELECT id, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()


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


def yahoo_symbol(ticker_symbol):
    yf_symbol = str(ticker_symbol or "").strip().upper()
    if not yf_symbol.endswith(".SA") and any(char.isdigit() for char in yf_symbol):
        return f"{yf_symbol}.SA"
    return yf_symbol


def subtract_months(date_value, months):
    month = date_value.month - months
    year = date_value.year
    while month <= 0:
        month += 12
        year -= 1
    day = min(date_value.day, calendar.monthrange(year, month)[1])
    return date_value.replace(year=year, month=month, day=day)


def parse_json_body():
    return request.get_json(silent=True) or {}


@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "database": "sqlite"}), 200


@app.route("/api/auth/signup", methods=["POST"])
def signup():
    payload = parse_json_body()
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))

    if not email or "@" not in email or len(password) < 6:
        return jsonify({"error": "Informe email valido e senha com pelo menos 6 caracteres."}), 400

    user_id = new_id()
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO users (id, email, password_hash) VALUES (?, ?, ?)",
                (user_id, email, generate_password_hash(password)),
            )
            user = conn.execute(
                "SELECT id, email, created_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Ja existe uma conta com este email."}), 409

    return jsonify({"user": row_to_dict(user), "access_token": create_token(user_id)}), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    payload = parse_json_body()
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))

    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Email ou senha invalidos."}), 401

    public_user = {key: user[key] for key in ("id", "email", "created_at")}
    return jsonify({"user": public_user, "access_token": create_token(user["id"])}), 200


@app.route("/api/auth/me", methods=["GET"])
@token_required
def me(current_user_id):
    return jsonify({"user": row_to_dict(fetch_user_by_id(current_user_id))}), 200


@app.route("/api/transactions", methods=["GET", "POST"])
@token_required
def transactions(current_user_id):
    if request.method == "GET":
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT * FROM transactions
                WHERE user_id = ?
                ORDER BY date DESC, created_at DESC
                """,
                (current_user_id,),
            ).fetchall()
        return jsonify([row_to_dict(row) for row in rows]), 200

    payload = parse_json_body()
    try:
        amount = parse_number(payload, "amount", "Valor", minimum=0, allow_zero=False)
        date_value = require_date(payload, "date", "Data")
        category = require_string(payload, "category", "Categoria")
        description = optional_string(payload, "description")
        transaction_type = require_choice(payload, "type", "Tipo", ALLOWED_TRANSACTION_TYPES)
    except ValidationError as exc:
        return validation_error(str(exc))

    item_id = new_id()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO transactions
            (id, user_id, amount, date, category, description, type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                current_user_id,
                amount,
                date_value,
                category,
                description,
                transaction_type,
            ),
        )
        item = conn.execute("SELECT * FROM transactions WHERE id = ?", (item_id,)).fetchone()
    return jsonify(row_to_dict(item)), 201


@app.route("/api/transactions/<item_id>", methods=["DELETE"])
@token_required
def delete_transaction(current_user_id, item_id):
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM transactions WHERE id = ? AND user_id = ?",
            (item_id, current_user_id),
        )
    if cursor.rowcount == 0:
        return jsonify({"deleted": False}), 404
    return jsonify({"deleted": True}), 200


@app.route("/api/credit-cards", methods=["GET", "POST"])
@token_required
def credit_cards(current_user_id):
    if request.method == "GET":
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM credit_cards WHERE user_id = ? ORDER BY name ASC",
                (current_user_id,),
            ).fetchall()
        return jsonify([row_to_dict(row) for row in rows]), 200

    payload = parse_json_body()
    try:
        name = require_string(payload, "name", "Nome do cartao")
        due_day = parse_int_number(payload, "due_day", "Dia de vencimento", minimum=1, maximum=31)
        closing_day = parse_int_number(payload, "closing_day", "Dia de fechamento", minimum=1, maximum=31)
    except ValidationError as exc:
        return validation_error(str(exc))

    item_id = new_id()
    try:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO credit_cards (id, user_id, name, due_day, closing_day)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    current_user_id,
                    name,
                    due_day,
                    closing_day,
                ),
            )
            item = conn.execute("SELECT * FROM credit_cards WHERE id = ?", (item_id,)).fetchone()
    except sqlite3.IntegrityError as exc:
        if "UNIQUE" in str(exc).upper():
            return jsonify({"error": "Ja existe um cartao com este nome."}), 409
        return jsonify({"error": "Nao foi possivel criar o cartao."}), 400
    return jsonify(row_to_dict(item)), 201


@app.route("/api/credit-cards/<card_id>", methods=["DELETE"])
@token_required
def delete_credit_card(current_user_id, card_id):
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM credit_cards WHERE id = ? AND user_id = ?",
            (card_id, current_user_id),
        )
    if cursor.rowcount == 0:
        return jsonify({"deleted": False}), 404
    return jsonify({"deleted": True}), 200


@app.route("/api/cc-expenses", methods=["GET", "POST", "DELETE"])
@token_required
def cc_expenses(current_user_id):
    if request.method == "GET":
        status = request.args.get("status")
        params = [current_user_id]
        status_filter = ""
        if status:
            status = str(status).strip().upper()
            if status not in ALLOWED_CC_STATUS:
                return validation_error("Status invalido.")
            status_filter = "AND cce.status = ?"
            params.append(status)

        with get_db() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    cce.*,
                    cc.name AS card_name,
                    cc.due_day AS card_due_day,
                    cc.closing_day AS card_closing_day
                FROM cc_expenses cce
                LEFT JOIN credit_cards cc ON cc.id = cce.card_id
                WHERE cce.user_id = ?
                {status_filter}
                ORDER BY cce.invoice_year ASC, cce.invoice_month ASC, cce.created_at ASC
                """,
                params,
            ).fetchall()
        return jsonify([serialize_cc_expense(row) for row in rows]), 200

    if request.method == "DELETE":
        payload = parse_json_body()
        try:
            ids = require_id_list(payload)
        except ValidationError as exc:
            return validation_error(str(exc))

        placeholders = ",".join("?" for _ in ids)
        with get_db() as conn:
            cursor = conn.execute(
                f"DELETE FROM cc_expenses WHERE user_id = ? AND id IN ({placeholders})",
                [current_user_id, *ids],
            )
        return jsonify({"deleted": cursor.rowcount}), 200

    payload = parse_json_body()
    items = payload if isinstance(payload, list) else [payload]
    if not items:
        return validation_error("Informe ao menos uma fatura.")

    inserted = []
    try:
        with get_db() as conn:
            for item in items:
                if not isinstance(item, dict):
                    raise ValidationError("Cada fatura deve ser um objeto valido.")

                card_id = require_string(item, "card_id", "Cartao")
                ensure_credit_card_owner(conn, current_user_id, card_id)
                category = require_string(item, "category", "Categoria")
                description = require_string(item, "description", "Descricao", max_length=500)
                amount = parse_number(item, "amount", "Valor", minimum=0, allow_zero=False)
                purchase_date = require_date(item, "purchase_date", "Data da compra")
                invoice_month = parse_int_number(item, "invoice_month", "Mes da fatura", minimum=1, maximum=12)
                invoice_year = parse_int_number(item, "invoice_year", "Ano da fatura", minimum=2000)
                installment_info = require_string(item, "installment_info", "Parcela", max_length=20)
                status_value = str(item.get("status", "OPEN") or "OPEN").strip().upper()
                if status_value not in ALLOWED_CC_STATUS:
                    raise ValidationError("Status invalido.")

                item_id = new_id()
                conn.execute(
                    """
                    INSERT INTO cc_expenses
                    (id, user_id, card_id, category, description, amount, purchase_date,
                     invoice_month, invoice_year, installment_info, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item_id,
                        current_user_id,
                        card_id,
                        category,
                        description,
                        amount,
                        purchase_date,
                        invoice_month,
                        invoice_year,
                        installment_info,
                        status_value,
                    ),
                )
                inserted.append(item_id)

            placeholders = ",".join("?" for _ in inserted)
            rows = conn.execute(
                f"SELECT * FROM cc_expenses WHERE id IN ({placeholders})",
                inserted,
            ).fetchall()
    except ValidationError as exc:
        return validation_error(str(exc))
    except sqlite3.IntegrityError:
        return jsonify({"error": "Nao foi possivel criar a fatura."}), 400

    return jsonify([row_to_dict(row) for row in rows]), 201


@app.route("/api/cc-expenses/candidates", methods=["GET"])
@token_required
def cc_expense_candidates(current_user_id):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, amount, installment_info
            FROM cc_expenses
            WHERE user_id = ?
              AND card_id = ?
              AND description = ?
              AND purchase_date = ?
              AND category = ?
            """,
            (
                current_user_id,
                request.args.get("card_id"),
                request.args.get("description"),
                request.args.get("purchase_date"),
                request.args.get("category"),
            ),
        ).fetchall()
    return jsonify([row_to_dict(row) for row in rows]), 200


@app.route("/api/cc-expenses/status", methods=["PATCH"])
@token_required
def update_cc_expense_status(current_user_id):
    payload = parse_json_body()
    try:
        ids = require_id_list(payload)
        status = str(payload.get("status", "PAID") or "PAID").strip().upper()
        if status not in ALLOWED_CC_STATUS:
            raise ValidationError("Status invalido.")
    except ValidationError as exc:
        return validation_error(str(exc))

    placeholders = ",".join("?" for _ in ids)
    with get_db() as conn:
        cursor = conn.execute(
            f"""
            UPDATE cc_expenses
            SET status = ?
            WHERE user_id = ? AND id IN ({placeholders})
            """,
            [status, current_user_id, *ids],
        )
    return jsonify({"updated": cursor.rowcount}), 200


@app.route("/api/cc-expenses/invoice-status", methods=["PATCH"])
@token_required
def update_invoice_status(current_user_id):
    payload = parse_json_body()
    try:
        card_id = require_string(payload, "card_id", "Cartao")
        invoice_month = parse_int_number(payload, "invoice_month", "Mes da fatura", minimum=1, maximum=12)
        invoice_year = parse_int_number(payload, "invoice_year", "Ano da fatura", minimum=2000)
        status = str(payload.get("status", "PAID") or "PAID").strip().upper()
        current_status = str(payload.get("current_status", "OPEN") or "OPEN").strip().upper()
        if status not in ALLOWED_CC_STATUS or current_status not in ALLOWED_CC_STATUS:
            raise ValidationError("Status invalido.")
    except ValidationError as exc:
        return validation_error(str(exc))

    with get_db() as conn:
        try:
            ensure_credit_card_owner(conn, current_user_id, card_id)
        except ValidationError as exc:
            return validation_error(str(exc), 404)

        cursor = conn.execute(
            """
            UPDATE cc_expenses
            SET status = ?
            WHERE user_id = ?
              AND card_id = ?
              AND invoice_month = ?
              AND invoice_year = ?
              AND status = ?
            """,
            (
                status,
                current_user_id,
                card_id,
                invoice_month,
                invoice_year,
                current_status,
            ),
        )
    return jsonify({"updated": cursor.rowcount}), 200


@app.route("/api/investments", methods=["GET", "POST"])
@token_required
def investments(current_user_id):
    if request.method == "GET":
        order = request.args.get("order", "created_at")
        if order not in {"created_at", "ticker_or_name", "asset_class"}:
            order = "created_at"
        direction = "ASC" if request.args.get("ascending") == "true" else "DESC"

        with get_db() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM investments
                WHERE user_id = ?
                ORDER BY {order} {direction}
                """,
                (current_user_id,),
            ).fetchall()
        return jsonify([serialize_investment(row) for row in rows]), 200

    payload = parse_json_body()
    items = payload if isinstance(payload, list) else [payload]
    if not items:
        return validation_error("Informe ao menos um investimento.")

    inserted = []
    try:
        with get_db() as conn:
            for item in items:
                if not isinstance(item, dict):
                    raise ValidationError("Cada investimento deve ser um objeto valido.")

                asset_class = require_choice(item, "asset_class", "Tipo de ativo", ALLOWED_ASSET_CLASSES)
                ticker_or_name = require_string(item, "ticker_or_name", "Ativo")
                quantity = parse_number(item, "quantity", "Quantidade")
                if quantity == 0:
                    raise ValidationError("Quantidade deve ser diferente de zero.")
                average_price = parse_number(item, "average_price", "Preco medio", minimum=0)
                current_price = parse_optional_number(item, "current_price", "Preco atual", minimum=0)
                metadata = item.get("metadata")
                if metadata not in (None, "") and not isinstance(metadata, (dict, str)):
                    raise ValidationError("Metadata deve ser um objeto valido.")

                item_id = new_id()
                conn.execute(
                    """
                    INSERT INTO investments
                    (id, user_id, asset_class, ticker_or_name, quantity,
                     average_price, current_price, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item_id,
                        current_user_id,
                        asset_class,
                        ticker_or_name,
                        quantity,
                        average_price,
                        current_price,
                        encode_metadata(metadata),
                    ),
                )
                inserted.append(item_id)

            placeholders = ",".join("?" for _ in inserted)
            rows = conn.execute(
                f"SELECT * FROM investments WHERE id IN ({placeholders})",
                inserted,
            ).fetchall()
    except ValidationError as exc:
        return validation_error(str(exc))
    except sqlite3.IntegrityError:
        return jsonify({"error": "Nao foi possivel criar o investimento."}), 400

    return jsonify([serialize_investment(row) for row in rows]), 201


@app.route("/api/investments/<investment_id>", methods=["PATCH", "DELETE"])
@token_required
def investment_detail(current_user_id, investment_id):
    if request.method == "DELETE":
        with get_db() as conn:
            cursor = conn.execute(
                "DELETE FROM investments WHERE id = ? AND user_id = ?",
                (investment_id, current_user_id),
            )
        if cursor.rowcount == 0:
            return jsonify({"deleted": False}), 404
        return jsonify({"deleted": True}), 200

    payload = parse_json_body()
    allowed = {"quantity", "average_price", "current_price", "metadata"}
    assignments = []
    values = []
    try:
        for key in allowed:
            if key not in payload:
                continue

            if key == "quantity":
                value = parse_number(payload, key, "Quantidade")
                if value == 0:
                    raise ValidationError("Quantidade deve ser diferente de zero.")
            elif key == "average_price":
                value = parse_number(payload, key, "Preco medio", minimum=0)
            elif key == "current_price":
                value = parse_optional_number(payload, key, "Preco atual", minimum=0)
            else:
                value = payload[key]
                if value not in (None, "") and not isinstance(value, (dict, str)):
                    raise ValidationError("Metadata deve ser um objeto valido.")
                value = encode_metadata(value)

            assignments.append(f"{key} = ?")
            values.append(value)
    except ValidationError as exc:
        return validation_error(str(exc))

    if not assignments:
        return jsonify({"updated": False}), 400

    with get_db() as conn:
        conn.execute(
            f"""
            UPDATE investments
            SET {', '.join(assignments)}
            WHERE id = ? AND user_id = ?
            """,
            [*values, investment_id, current_user_id],
        )
        row = conn.execute(
            "SELECT * FROM investments WHERE id = ? AND user_id = ?",
            (investment_id, current_user_id),
        ).fetchone()
    if not row:
        return jsonify({"error": "Investimento nao encontrado."}), 404
    return jsonify(serialize_investment(row)), 200


@app.route("/api/investments/by-ticker/<path:ticker>", methods=["DELETE"])
@token_required
def delete_investments_by_ticker(current_user_id, ticker):
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM investments WHERE ticker_or_name = ? AND user_id = ?",
            (ticker, current_user_id),
        )
    return jsonify({"deleted": cursor.rowcount}), 200


@app.route("/api/investments/price-by-ticker", methods=["PATCH"])
@token_required
def update_price_by_ticker(current_user_id):
    payload = parse_json_body()
    try:
        ticker = require_string(payload, "ticker", "Ativo")
        current_price = parse_number(payload, "current_price", "Preco atual", minimum=0)
    except ValidationError as exc:
        return validation_error(str(exc))

    with get_db() as conn:
        cursor = conn.execute(
            """
            UPDATE investments
            SET current_price = ?
            WHERE user_id = ? AND ticker_or_name = ?
            """,
            (
                current_price,
                current_user_id,
                ticker,
            ),
        )
    if cursor.rowcount == 0:
        return jsonify({"updated": 0, "error": "Ativo nao encontrado."}), 404
    return jsonify({"updated": cursor.rowcount}), 200


def fetch_investments(current_user_id, investment_id=None):
    query = "SELECT * FROM investments WHERE user_id = ?"
    params = [current_user_id]
    if investment_id:
        query += " AND id = ?"
        params.append(investment_id)
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [serialize_investment(row) for row in rows]


@app.route("/api/investments/portfolio", methods=["GET"])
@token_required
def get_portfolio(current_user_id):
    try:
        all_investments = fetch_investments(current_user_id)

        grouped_assets = {}
        for asset in all_investments:
            metadata = asset.get("metadata") or {}
            if asset["asset_class"] == "FIXED_INCOME" and metadata.get("is_redemption"):
                continue

            ticker = asset["ticker_or_name"]
            asset_class = asset["asset_class"]
            qty = safe_float(asset.get("quantity"))
            avg_price_buy = safe_float(asset.get("average_price"))
            curr_price = safe_float(asset.get("current_price"), avg_price_buy)
            invested_value = qty * avg_price_buy

            group_key = str(asset["id"]) if asset_class == "FIXED_INCOME" else ticker
            if group_key not in grouped_assets:
                grouped_assets[group_key] = {
                    "id": group_key,
                    "original_ticker": ticker,
                    "class": asset_class,
                    "total_quantity": qty,
                    "total_invested": invested_value,
                    "current_price": curr_price,
                    "metadata": metadata,
                }
            else:
                grouped_assets[group_key]["total_quantity"] += qty
                grouped_assets[group_key]["total_invested"] += invested_value
                if asset.get("current_price") is not None:
                    grouped_assets[group_key]["current_price"] = curr_price

        processed_assets = []
        total_invested_all = 0
        current_total_value = 0
        current_net_value_all = 0
        distribution = {}

        for data in grouped_assets.values():
            if data["total_quantity"] <= 0:
                continue

            avg_price_calculated = (
                data["total_invested"] / data["total_quantity"]
                if data["total_quantity"] > 0 else 0
            )

            adjusted_quantity = data["total_quantity"]
            if data["class"] == "CATTLE" and data.get("metadata"):
                mortality_rate = safe_float(data["metadata"].get("mortality_rate"))
                adjusted_quantity = data["total_quantity"] * (1 - mortality_rate)

            current_value = adjusted_quantity * data["current_price"]
            profitability = (
                ((current_value - data["total_invested"]) / data["total_invested"]) * 100
                if data["total_invested"] > 0 else 0
            )

            net_value = current_value
            taxes = 0
            is_tax_free = False

            if data["class"] == "FIXED_INCOME" and data.get("metadata"):
                meta = data["metadata"]
                is_tax_free = meta.get("is_tax_free", False)
                purchase_date_str = meta.get("purchase_date")
                profit = current_value - data["total_invested"]

                if profit > 0 and not is_tax_free and purchase_date_str:
                    try:
                        purchase_date = datetime.strptime(purchase_date_str, "%Y-%m-%d")
                    except ValueError:
                        purchase_date = None

                    if purchase_date:
                        days_invested = (datetime.now() - purchase_date).days
                        if days_invested <= 180:
                            tax_rate = 0.225
                        elif days_invested <= 360:
                            tax_rate = 0.200
                        elif days_invested <= 720:
                            tax_rate = 0.175
                        else:
                            tax_rate = 0.150

                        taxes = profit * tax_rate
                        net_value = current_value - taxes

            total_invested_all += data["total_invested"]
            current_total_value += current_value
            current_net_value_all += net_value
            distribution[data["class"]] = distribution.get(data["class"], 0) + current_value

            processed_assets.append({
                "id": data["id"],
                "ticker": data["original_ticker"],
                "name": data["original_ticker"],
                "class": data["class"],
                "quantity": round(data["total_quantity"], 4),
                "average_price": round(avg_price_calculated, 2),
                "current_price": round(data["current_price"], 2),
                "current_value": round(current_value, 2),
                "net_value": round(net_value, 2),
                "taxes": round(taxes, 2),
                "is_tax_free": is_tax_free,
                "profitability_percent": round(profitability, 2),
            })

        for key, value in distribution.items():
            distribution[key] = round((value / current_total_value) * 100, 2) if current_total_value > 0 else 0

        return jsonify({
            "total_invested": round(total_invested_all, 2),
            "current_balance": round(current_total_value, 2),
            "current_net_balance": round(current_net_value_all, 2),
            "portfolio_profitability": round(
                ((current_total_value - total_invested_all) / total_invested_all * 100),
                2,
            ) if total_invested_all > 0 else 0,
            "distribution": distribution,
            "assets": processed_assets,
        }), 200
    except Exception as exc:
        print(f"Erro no calculo: {exc}")
        return jsonify({"error": "Nao foi possivel calcular a carteira."}), 500


@app.route("/api/investments/update-prices", methods=["POST"])
@token_required
def update_stock_prices(current_user_id):
    try:
        payload = parse_json_body()
        investments_to_update = fetch_investments(current_user_id, payload.get("investment_id"))
        updated_count = 0

        for inv in investments_to_update:
            if inv["asset_class"] == "STOCKS":
                if yf is None:
                    print("yfinance nao esta instalado; pulando atualizacao de acoes.")
                    continue

                yf_symbol = yahoo_symbol(inv["ticker_or_name"])
                try:
                    ticker = yf.Ticker(yf_symbol)
                    current_price = ticker.fast_info["last_price"]
                    with get_db() as conn:
                        conn.execute(
                            """
                            UPDATE investments
                            SET current_price = ?
                            WHERE id = ? AND user_id = ?
                            """,
                            (round(current_price, 2), inv["id"], current_user_id),
                        )
                    updated_count += 1
                except Exception as exc:
                    print(f"Erro ao buscar cotacao para {yf_symbol}: {exc}")

            elif inv["asset_class"] == "FIXED_INCOME":
                meta = inv.get("metadata") or {}
                if meta and "cdi_percentage" in meta:
                    cdi_pct = safe_float(meta["cdi_percentage"])
                    date_str = meta.get("purchase_date")
                    try:
                        if date_str:
                            dt_obj = datetime.strptime(date_str, "%Y-%m-%d")
                        else:
                            dt_obj = datetime.strptime(inv["created_at"][:10], "%Y-%m-%d")
                    except ValueError:
                        print(f"Data invalida para {inv['ticker_or_name']}; pulando CDI.")
                        continue

                    url = (
                        "https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados"
                        f"?formato=json&dataInicial={dt_obj.strftime('%d/%m/%Y')}"
                        f"&dataFinal={datetime.now().strftime('%d/%m/%Y')}"
                    )

                    try:
                        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                        with urllib.request.urlopen(req, timeout=15) as response_bcb:
                            if response_bcb.status == 200:
                                cdi_data = json.loads(response_bcb.read().decode())
                                accumulated = 1.0
                                for day in cdi_data:
                                    daily_rate = safe_float(day.get("valor")) / 100
                                    accumulated *= (1 + (daily_rate * cdi_pct))

                                new_price = safe_float(inv.get("average_price")) * accumulated
                                with get_db() as conn:
                                    conn.execute(
                                        """
                                        UPDATE investments
                                        SET current_price = ?
                                        WHERE id = ? AND user_id = ?
                                        """,
                                        (round(new_price, 2), inv["id"], current_user_id),
                                    )
                                updated_count += 1
                    except Exception as exc:
                        print(f"Erro ao buscar CDI para {inv['ticker_or_name']}: {exc}")

        return jsonify({
            "message": "Cotacoes e CDI atualizados com sucesso",
            "updated_count": updated_count,
        }), 200
    except Exception as exc:
        print(f"ERRO FATAL NA ROTA UPDATE-PRICES: {exc}")
        return jsonify({"error": "Nao foi possivel atualizar os precos."}), 500


@app.route("/api/investments/history", methods=["GET"])
@token_required
def get_historical_portfolio(current_user_id):
    try:
        investments_data = fetch_investments(current_user_id)
        try:
            months_back = int(request.args.get("months", 12))
        except ValueError:
            months_back = 12
        months_back = max(1, min(months_back, 60))
        start_date = subtract_months(datetime.now(), months_back).strftime("%Y-%m-%d")

        historical_prices = {}
        stocks = [inv for inv in investments_data if inv["asset_class"] == "STOCKS"]
        unique_tickers = sorted(set(s["ticker_or_name"].strip().upper() for s in stocks))

        for ticker in unique_tickers:
            if yf is None:
                historical_prices[ticker] = {}
                continue

            yf_symbol = yahoo_symbol(ticker)
            try:
                stock_data = yf.Ticker(yf_symbol)
                hist = stock_data.history(start=start_date, interval="1mo")
                prices_by_month = {}
                for date, row in hist.iterrows():
                    prices_by_month[date.strftime("%Y-%m")] = round(row["Close"], 2)
                historical_prices[ticker] = prices_by_month
            except Exception as exc:
                print(f"Erro ao buscar historico de {yf_symbol}: {exc}")

        return jsonify({"historical_prices": historical_prices}), 200
    except Exception as exc:
        print(f"Erro no historico de investimentos: {exc}")
        return jsonify({"error": "Nao foi possivel carregar o historico de investimentos."}), 500


init_db()

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", port=5000)
