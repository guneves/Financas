import json
import os
import re
import sqlite3
import urllib.request
import uuid
import base64
import calendar
import hashlib
import hmac
import math
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
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
PROJECT_DIR = os.path.dirname(BASE_DIR)


def resolve_app_path(raw_path, base_dir=BASE_DIR):
    value = str(raw_path or "").strip()
    if not value:
        return base_dir
    return value if os.path.isabs(value) else os.path.join(base_dir, value)


RAW_DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "finance.db"))
DATABASE_PATH = resolve_app_path(RAW_DATABASE_PATH, BASE_DIR)
MIGRATIONS_DIR = resolve_app_path(
    os.getenv("DATABASE_MIGRATIONS_DIR", os.path.join("database", "migrations")),
    PROJECT_DIR,
)
DATABASE_BACKUP_DIR = resolve_app_path(
    os.getenv("DATABASE_BACKUP_DIR", os.path.join("backups")),
    BASE_DIR,
)
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

try:
    JWT_EXP_DAYS = max(1, int(os.getenv("JWT_EXP_DAYS", "30")))
except ValueError:
    JWT_EXP_DAYS = 30

ALLOWED_TRANSACTION_TYPES = {"INCOME", "EXPENSE", "TRANSFER"}
ALLOWED_ACCOUNT_TYPES = {"CHECKING", "SAVINGS", "BROKERAGE", "CASH", "OTHER"}
ALLOWED_CATEGORY_KINDS = {"INCOME", "EXPENSE", "BOTH"}
DEFAULT_ACCOUNT_NAME = "Conta Principal"
TRANSFER_CATEGORY = "Transferencia"
DEFAULT_CATEGORY_SEEDS = (
    ("receita", "Receita", "INCOME"),
    ("investimento", "Investimento", "BOTH"),
    ("alimentacao", "Alimentação", "EXPENSE"),
    ("moradia", "Moradia", "EXPENSE"),
    ("transporte", "Transporte", "EXPENSE"),
    ("saude", "Saúde", "EXPENSE"),
    ("educacao", "Educação", "EXPENSE"),
    ("lazer", "Lazer", "EXPENSE"),
    ("servicos", "Serviços", "EXPENSE"),
    ("outros", "Outros", "EXPENSE"),
)
ALLOWED_ASSET_CLASSES = {"STOCKS", "FIXED_INCOME", "REIT", "CATTLE", "OTHER"}
ALLOWED_CC_STATUS = {"OPEN", "PAID"}
ALLOWED_PROCEEDS_TYPES = {"DIVIDEND", "JCP", "AMORTIZATION"}
QUOTED_ASSET_CLASSES = {"STOCKS", "REIT"}
INVESTMENT_CASH_SOURCE_TYPE = "INVESTMENT_TRANSACTION"
INVESTMENT_CASH_CATEGORY = "Investimento"
DEFAULT_JCP_TAX_RATE = 0.15
DEFAULT_REALIZED_TAX_RATES = {
    "STOCKS": 0.15,
    "REIT": 0.20,
    "CATTLE": 0.15,
    "OTHER": 0.15,
    "FIXED_INCOME": 0.15,
}


def read_int_env(name, default, *, minimum=None, maximum=None):
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def read_float_env(name, default, *, minimum=None, maximum=None):
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


PRICE_CACHE_TTL_SECONDS = read_int_env("PRICE_CACHE_TTL_SECONDS", 60, minimum=5)
PRICE_FETCH_TIMEOUT_SECONDS = read_float_env(
    "PRICE_FETCH_TIMEOUT_SECONDS",
    6.0,
    minimum=1.0,
    maximum=30.0,
)
PRICE_DOWNLOAD_TIMEOUT_SECONDS = read_float_env(
    "PRICE_DOWNLOAD_TIMEOUT_SECONDS",
    8.0,
    minimum=1.0,
    maximum=30.0,
)
PRICE_FETCH_WORKERS = read_int_env("PRICE_FETCH_WORKERS", 2, minimum=1, maximum=4)
HISTORY_CACHE_TTL_SECONDS = read_int_env("HISTORY_CACHE_TTL_SECONDS", 900, minimum=60)
SQLITE_BUSY_TIMEOUT_MS = read_int_env("SQLITE_BUSY_TIMEOUT_MS", 5000, minimum=1000, maximum=60000)
PRICE_QUOTE_STALE_HOURS = read_int_env("PRICE_QUOTE_STALE_HOURS", 36, minimum=1, maximum=720)
BACKUP_RETENTION_DAYS = read_int_env("BACKUP_RETENTION_DAYS", 7, minimum=1, maximum=365)
AUTO_BACKUP_ON_BOOT = str(os.getenv("AUTO_BACKUP_ON_BOOT", "1")).strip().lower() not in {"0", "false", "no"}
AUTO_BACKUP_MIN_INTERVAL_HOURS = read_int_env(
    "AUTO_BACKUP_MIN_INTERVAL_HOURS",
    12,
    minimum=0,
    maximum=720,
)
# So os arquivos gerados automaticamente entram na rotacao. Backups com nome
# proprio (ex.: "finance-before-normalized-investments-*.db") sao marcos feitos
# a mao e nunca sao apagados pela retencao.
BACKUP_FILE_PATTERN = re.compile(r"^finance-\d{8}-\d{6}\.(db|sql|zip)$")

_price_cache = {}
_history_cache = {}
_price_cache_lock = threading.Lock()
_price_fetch_executor = ThreadPoolExecutor(max_workers=PRICE_FETCH_WORKERS)

app = Flask(__name__)
cors_origins = "*" if CORS_ORIGINS == "*" else [
    origin.strip() for origin in CORS_ORIGINS.split(",") if origin.strip()
] or "*"
CORS(app, resources={r"/api/*": {"origins": cors_origins}})


def get_db():
    database_dir = os.path.dirname(os.path.abspath(DATABASE_PATH))
    if database_dir:
        os.makedirs(database_dir, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    return conn


def configure_sqlite_database(conn):
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA synchronous = NORMAL")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.DatabaseError as exc:
        print(f"Nao foi possivel ativar WAL no SQLite: {exc}")


def migration_version(filename):
    stem = filename.rsplit(".", 1)[0]
    return stem.split("_", 1)[0]


def sql_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def migration_files():
    if not os.path.isdir(MIGRATIONS_DIR):
        raise RuntimeError(f"Diretorio de migrations nao encontrado: {MIGRATIONS_DIR}")

    files = [
        filename
        for filename in os.listdir(MIGRATIONS_DIR)
        if filename.lower().endswith(".sql")
    ]
    return sorted(files)


def ensure_migrations_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )
        """
    )


def applied_migration_versions(conn):
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {row["version"] for row in rows}


def init_db():
    with get_db() as conn:
        configure_sqlite_database(conn)
        ensure_migrations_table(conn)
        applied_versions = applied_migration_versions(conn)

        for filename in migration_files():
            version = migration_version(filename)
            if version in applied_versions:
                continue

            migration_path = os.path.join(MIGRATIONS_DIR, filename)
            with open(migration_path, "r", encoding="utf-8") as file:
                sql = file.read()

            migration_script = (
                "BEGIN IMMEDIATE;\n"
                f"{sql}\n"
                "INSERT OR IGNORE INTO schema_migrations (version, name) VALUES "
                f"({sql_literal(version)}, {sql_literal(filename)});\n"
                "COMMIT;"
            )
            try:
                conn.executescript(migration_script)
            except sqlite3.DatabaseError:
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.DatabaseError:
                    pass
                raise
            applied_versions.add(version)


def database_status():
    with get_db() as conn:
        configure_sqlite_database(conn)
        ensure_migrations_table(conn)
        migration_rows = conn.execute(
            "SELECT version, name, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        page_count = conn.execute("PRAGMA page_count").fetchone()[0]
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        wal_checkpoint = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()

    return {
        "path": DATABASE_PATH,
        "journal_mode": journal_mode,
        "foreign_keys": bool(foreign_keys),
        "busy_timeout_ms": SQLITE_BUSY_TIMEOUT_MS,
        "size_bytes": page_size * page_count,
        "wal_log_pages": wal_checkpoint[1] if wal_checkpoint else 0,
        "wal_checkpointed_pages": wal_checkpoint[2] if wal_checkpoint else 0,
        "migrations": [row_to_dict(row) for row in migration_rows],
    }


def create_database_backup():
    os.makedirs(DATABASE_BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = os.path.join(DATABASE_BACKUP_DIR, f"finance-{timestamp}.db")

    with sqlite3.connect(DATABASE_PATH, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000) as source:
        with sqlite3.connect(backup_path) as target:
            source.backup(target)

    dump_path = os.path.join(DATABASE_BACKUP_DIR, f"finance-{timestamp}.sql")
    with sqlite3.connect(DATABASE_PATH, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000) as source:
        with open(dump_path, "w", encoding="utf-8") as dump_file:
            for line in source.iterdump():
                dump_file.write(f"{line}\n")

    zip_path = os.path.join(DATABASE_BACKUP_DIR, f"finance-{timestamp}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(backup_path, arcname=os.path.basename(backup_path))
        archive.write(dump_path, arcname=os.path.basename(dump_path))

    return {
        "database_path": backup_path,
        "dump_path": dump_path,
        "zip_path": zip_path,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def backup_files():
    """Backups automaticos (finance-AAAAMMDD-HHMMSS.*), do mais novo ao mais antigo."""
    if not os.path.isdir(DATABASE_BACKUP_DIR):
        return []

    entries = []
    for filename in os.listdir(DATABASE_BACKUP_DIR):
        if not BACKUP_FILE_PATTERN.match(filename):
            continue
        path = os.path.join(DATABASE_BACKUP_DIR, filename)
        if not os.path.isfile(path):
            continue
        try:
            entries.append((path, os.path.getmtime(path)))
        except OSError:
            continue

    entries.sort(key=lambda entry: entry[1], reverse=True)
    return entries


def last_backup_age_hours():
    """Hours since the most recent backup, or None when there is none."""
    entries = backup_files()
    if not entries:
        return None
    return max(0.0, (time.time() - entries[0][1]) / 3600)


def prune_database_backups(retention_days=None):
    """Delete backup artifacts older than the retention window."""
    retention_days = BACKUP_RETENTION_DAYS if retention_days is None else retention_days
    cutoff = time.time() - retention_days * 86400

    removed = []
    for path, modified_at in backup_files():
        if modified_at >= cutoff:
            continue
        try:
            os.remove(path)
            removed.append(os.path.basename(path))
        except OSError as exc:
            print(f"Nao foi possivel remover o backup antigo {path}: {exc}")

    return removed


def run_startup_backup():
    """Back up the database on boot, then prune anything past retention.

    Skipped when AUTO_BACKUP_ON_BOOT is off, when there is no database file yet,
    or when a backup already ran inside AUTO_BACKUP_MIN_INTERVAL_HOURS - restarting
    the app repeatedly should not fill the backup directory.
    """
    if not AUTO_BACKUP_ON_BOOT:
        return None

    if not os.path.isfile(DATABASE_PATH) or os.path.getsize(DATABASE_PATH) == 0:
        return None

    age_hours = last_backup_age_hours()
    if age_hours is not None and age_hours < AUTO_BACKUP_MIN_INTERVAL_HOURS:
        prune_database_backups()
        return None

    try:
        backup = create_database_backup()
    except Exception as exc:
        print(f"Backup automatico de boot falhou: {exc}")
        return None

    removed = prune_database_backups()
    print(
        f"Backup automatico criado em {backup['zip_path']}"
        + (f" ({len(removed)} arquivo(s) antigo(s) removido(s))" if removed else "")
    )
    backup["pruned"] = removed
    return backup


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


def optional_date(payload, key, label):
    if key not in payload or payload.get(key) in (None, ""):
        return None
    return require_date(payload, key, label)


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


def ensure_asset_owner(conn, current_user_id, asset_id):
    asset = conn.execute(
        """
        SELECT id, user_id, asset_class, ticker, name
        FROM assets
        WHERE id = ? AND user_id = ?
        """,
        (asset_id, current_user_id),
    ).fetchone()
    if not asset:
        raise ValidationError("Ativo nao encontrado.")
    return asset


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
        if "current_quote_metadata" in item:
            item["current_quote_metadata"] = parse_metadata_value(item.get("current_quote_metadata"))
        if "realized_metadata" in item:
            item["realized_metadata"] = parse_metadata_value(item.get("realized_metadata"))
    return item


def serialize_metadata_row(row):
    item = row_to_dict(row)
    if item and "metadata" in item:
        item["metadata"] = parse_metadata_value(item.get("metadata"))
    return item


def serialize_transaction(row):
    return serialize_metadata_row(row)


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def quote_timestamp(date_value=None):
    parsed = parse_iso_date(date_value)
    if parsed:
        return f"{parsed.strftime('%Y-%m-%d')}T00:00:00Z"
    return utc_timestamp()


def investment_metadata_dict(value):
    return parse_metadata_value(value)


def investment_transaction_date(metadata, created_at=None):
    metadata = metadata or {}
    for key in ("redemption_date", "sale_date", "purchase_date"):
        parsed = parse_iso_date(metadata.get(key))
        if parsed:
            return parsed.strftime("%Y-%m-%d")

    parsed_created_at = parse_iso_date(created_at)
    if parsed_created_at:
        return parsed_created_at.strftime("%Y-%m-%d")
    return datetime.now().strftime("%Y-%m-%d")


def investment_movement_type(quantity, metadata):
    metadata = metadata or {}
    if metadata.get("is_redemption"):
        return "REDEMPTION"
    if safe_float(quantity) < 0:
        return "SELL"
    return "BUY"


def investment_fee_amount(metadata):
    return max(safe_float((metadata or {}).get("other_costs")), 0)


def investment_gross_amount(quantity, unit_price):
    return abs(safe_float(quantity) * safe_float(unit_price))


def investment_sale_price(investment, metadata):
    sale_price = safe_float((metadata or {}).get("sale_price"), None)
    if sale_price is not None and math.isfinite(sale_price) and sale_price > 0:
        return sale_price

    current_price = safe_float(investment.get("current_price"), None)
    if current_price is not None and math.isfinite(current_price) and current_price > 0:
        return current_price

    return safe_float(investment.get("average_price"))


def investment_cash_amount(investment):
    metadata = investment.get("metadata") or {}
    movement_type = investment.get("movement_type") or investment_movement_type(
        investment.get("quantity"),
        metadata,
    )
    quantity = safe_float(investment.get("quantity"))
    unit_price = safe_float(investment.get("average_price"))
    fees = investment_fee_amount(metadata)

    if movement_type == "BUY":
        amount = abs(quantity * unit_price)
    elif movement_type == "SELL":
        amount = (abs(quantity) * investment_sale_price(investment, metadata)) - fees
    elif movement_type == "REDEMPTION":
        amount = safe_float(investment.get("current_price"), abs(quantity * unit_price)) - fees
    else:
        return None

    if not math.isfinite(amount) or amount <= 0:
        return None
    return rounded_money(amount)


def investment_cash_type(investment):
    movement_type = investment.get("movement_type") or investment_movement_type(
        investment.get("quantity"),
        investment.get("metadata") or {},
    )
    if movement_type == "BUY":
        return "EXPENSE"
    if movement_type in {"SELL", "REDEMPTION"}:
        return "INCOME"
    return None


def investment_cash_description(investment):
    movement_type = investment.get("movement_type") or investment_movement_type(
        investment.get("quantity"),
        investment.get("metadata") or {},
    )
    ticker = ticker_key(investment.get("ticker_or_name"))
    labels = {
        "BUY": "Compra de investimento",
        "SELL": "Venda de investimento",
        "REDEMPTION": "Resgate de investimento",
    }
    return f"{labels.get(movement_type, 'Movimento de investimento')}: {ticker}"


def investment_cash_metadata(investment):
    return {
        "asset_id": investment.get("asset_id"),
        "asset_class": investment.get("asset_class"),
        "ticker": ticker_key(investment.get("ticker_or_name")),
        "movement_type": investment.get("movement_type"),
    }


def sync_investment_cash_transaction(conn, current_user_id, investment):
    amount = investment_cash_amount(investment)
    cash_type = investment_cash_type(investment)
    investment_id = investment.get("id")
    if not investment_id:
        return

    if amount is None or cash_type is None:
        conn.execute(
            """
            DELETE FROM transactions
            WHERE user_id = ? AND source_type = ? AND source_id = ?
            """,
            (current_user_id, INVESTMENT_CASH_SOURCE_TYPE, investment_id),
        )
        return

    transaction_date = investment.get("transaction_date") or investment_transaction_date(
        investment.get("metadata") or {},
        investment.get("created_at"),
    )
    description = investment_cash_description(investment)
    metadata = investment_cash_metadata(investment)

    existing = conn.execute(
        """
        SELECT id FROM transactions
        WHERE user_id = ? AND source_type = ? AND source_id = ?
        """,
        (current_user_id, INVESTMENT_CASH_SOURCE_TYPE, investment_id),
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE transactions
            SET amount = ?,
                date = ?,
                category = ?,
                description = ?,
                type = ?,
                metadata = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                amount,
                transaction_date,
                INVESTMENT_CASH_CATEGORY,
                description,
                cash_type,
                encode_metadata(metadata),
                existing["id"],
                current_user_id,
            ),
        )
        return

    conn.execute(
        """
        INSERT INTO transactions
        (id, user_id, account_id, amount, date, category, description, type, source_type, source_id, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"cash:{investment_id}",
            current_user_id,
            ensure_default_account(conn, current_user_id),
            amount,
            transaction_date,
            INVESTMENT_CASH_CATEGORY,
            description,
            cash_type,
            INVESTMENT_CASH_SOURCE_TYPE,
            investment_id,
            encode_metadata(metadata),
        ),
    )


def delete_investment_cash_transaction(conn, current_user_id, investment_id):
    conn.execute(
        """
        DELETE FROM transactions
        WHERE user_id = ? AND source_type = ? AND source_id = ?
        """,
        (current_user_id, INVESTMENT_CASH_SOURCE_TYPE, investment_id),
    )


def normalized_tax_rate(value):
    rate = safe_float(value, None)
    if rate is None or not math.isfinite(rate) or rate < 0:
        return None
    if rate > 1:
        return rate / 100
    return rate


def fixed_income_tax_rate_for_days(days_invested):
    days = max(int(days_invested or 0), 0)
    if days <= 180:
        return 0.225
    if days <= 360:
        return 0.200
    if days <= 720:
        return 0.175
    return 0.150


def realized_tax_rate(asset_class, metadata=None, holding_days=None):
    metadata = metadata or {}
    explicit_rate = normalized_tax_rate(
        metadata.get("tax_rate", metadata.get("tax_rate_percent"))
    )
    if explicit_rate is not None:
        return explicit_rate

    if asset_class == "FIXED_INCOME":
        if metadata.get("is_tax_free", False):
            return 0
        if holding_days is not None:
            return fixed_income_tax_rate_for_days(holding_days)

    return DEFAULT_REALIZED_TAX_RATES.get(asset_class, 0)


def investment_gross_proceeds(investment, metadata):
    movement_type = investment.get("movement_type") or investment_movement_type(
        investment.get("quantity"),
        metadata,
    )
    quantity = abs(safe_float(investment.get("quantity")))
    if movement_type == "SELL":
        return quantity * investment_sale_price(investment, metadata)
    if movement_type == "REDEMPTION":
        return safe_float(
            investment.get("current_price"),
            abs(quantity * safe_float(investment.get("average_price"))),
        )
    return 0


def investment_operation_date(investment):
    return investment_transaction_date(
        investment.get("metadata") or {},
        investment.get("transaction_date") or investment.get("created_at"),
    )


def rounded_money(value):
    """Arredonda valores monetarios para centavos com ROUND_HALF_UP.

    O round() do Python usa banker's rounding (metade para o par), entao
    0.125 virava 0.12 e 0.135 virava 0.14 — comportamento inconsistente para
    dinheiro. A conversao via str() recupera a intencao decimal do float
    antes de quantizar, evitando herdar o erro de representacao binaria.
    """
    numeric = safe_float(value)
    if not math.isfinite(numeric):
        return 0.0
    try:
        return float(Decimal(str(numeric)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return 0.0


def quote_transaction_id(asset_class, transaction_id):
    return None if asset_class in QUOTED_ASSET_CLASSES else transaction_id


def get_or_create_asset(conn, current_user_id, asset_class, ticker_or_name):
    ticker = ticker_key(ticker_or_name)
    row = conn.execute(
        """
        SELECT id FROM assets
        WHERE user_id = ? AND asset_class = ? AND ticker = ?
        """,
        (current_user_id, asset_class, ticker),
    ).fetchone()
    if row:
        return row["id"]

    asset_id = new_id()
    conn.execute(
        """
        INSERT INTO assets
        (id, user_id, asset_class, ticker, name)
        VALUES (?, ?, ?, ?, ?)
        """,
        (asset_id, current_user_id, asset_class, ticker, ticker or ticker_or_name),
    )
    return asset_id


def record_price_quote(
    conn,
    current_user_id,
    asset_id,
    price,
    *,
    asset_class=None,
    transaction_id=None,
    quoted_at=None,
    source="manual",
    metadata=None,
):
    if price is None:
        return None

    numeric_price = safe_float(price, None)
    if numeric_price is None or not math.isfinite(numeric_price) or numeric_price < 0:
        return None

    row = conn.execute(
        "SELECT asset_class FROM assets WHERE id = ? AND user_id = ?",
        (asset_id, current_user_id),
    ).fetchone()
    resolved_asset_class = asset_class or (row["asset_class"] if row else None)
    scoped_transaction_id = quote_transaction_id(resolved_asset_class, transaction_id)

    quote_id = new_id()
    conn.execute(
        """
        INSERT INTO price_quotes
        (id, user_id, asset_id, transaction_id, price, quoted_at, source, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            quote_id,
            current_user_id,
            asset_id,
            scoped_transaction_id,
            round(numeric_price, 6),
            quoted_at or utc_timestamp(),
            source,
            encode_metadata(metadata),
        ),
    )
    return quote_id


def fetch_investment_rows(conn, current_user_id, *, investment_id=None, order_by="it.created_at", direction="ASC"):
    query = f"""
        SELECT
            it.id,
            it.user_id,
            it.asset_id,
            a.asset_class,
            a.ticker AS ticker_or_name,
            it.quantity,
            it.unit_price AS average_price,
            COALESCE(
                (
                    SELECT pq.price
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id = it.id
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                ),
                (
                    SELECT pq.price
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id IS NULL
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                ),
                it.unit_price
            ) AS current_price,
            COALESCE(
                (
                    SELECT pq.id
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id = it.id
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                ),
                (
                    SELECT pq.id
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id IS NULL
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                )
            ) AS current_quote_id,
            COALESCE(
                (
                    SELECT pq.quoted_at
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id = it.id
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                ),
                (
                    SELECT pq.quoted_at
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id IS NULL
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                )
            ) AS current_quote_quoted_at,
            COALESCE(
                (
                    SELECT pq.source
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id = it.id
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                ),
                (
                    SELECT pq.source
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id IS NULL
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                )
            ) AS current_quote_source,
            COALESCE(
                (
                    SELECT pq.metadata
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id = it.id
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                ),
                (
                    SELECT pq.metadata
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id IS NULL
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                )
            ) AS current_quote_metadata,
            it.metadata,
            it.movement_type,
            it.gross_amount,
            it.fee_amount,
            it.transaction_date,
            it.created_at,
            it.updated_at,
            rr.quantity AS realized_quantity,
            rr.average_cost AS realized_average_cost,
            rr.gross_proceeds AS realized_gross_proceeds,
            rr.fee_amount AS realized_fee_amount,
            rr.net_proceeds AS realized_net_proceeds,
            rr.net_unit_price AS realized_net_unit_price,
            rr.cost_basis AS realized_cost_basis,
            rr.realized_profit,
            rr.profitability_percent AS realized_profitability_percent,
            rr.tax_rate AS realized_tax_rate,
            rr.tax_amount AS realized_tax_amount,
            rr.net_profit_after_tax AS realized_net_profit_after_tax,
            rr.operation_date AS realized_operation_date,
            rr.metadata AS realized_metadata
        FROM investment_transactions it
        JOIN assets a ON a.id = it.asset_id
        LEFT JOIN investment_realized_results rr
          ON rr.user_id = it.user_id
         AND rr.source_transaction_id = it.id
        WHERE it.user_id = ?
    """
    params = [current_user_id]
    if investment_id:
        query += " AND it.id = ?"
        params.append(investment_id)
    query += f" ORDER BY {order_by} {direction}"
    return conn.execute(query, params).fetchall()


def investment_position_at_date(conn, current_user_id, asset_id, date_value):
    target_date = require_date({"date": date_value}, "date", "Data de referencia")
    rows = conn.execute(
        """
        SELECT
            id,
            movement_type,
            quantity,
            unit_price,
            fee_amount,
            transaction_date,
            metadata,
            created_at
        FROM investment_transactions
        WHERE user_id = ?
          AND asset_id = ?
          AND transaction_date <= ?
        ORDER BY transaction_date ASC, created_at ASC, id ASC
        """,
        (current_user_id, asset_id, target_date),
    ).fetchall()

    quantity = 0.0
    cost_basis = 0.0
    for row in rows:
        item = serialize_metadata_row(row)
        movement_type = item.get("movement_type")
        movement_quantity = safe_float(item.get("quantity"))
        unit_price = safe_float(item.get("unit_price"))
        fee_amount = max(safe_float(item.get("fee_amount")), 0)

        if movement_type in {"BUY", "ADJUSTMENT"} and movement_quantity > 0:
            quantity += movement_quantity
            cost_basis += (movement_quantity * unit_price) + fee_amount
            continue

        if movement_type in {"SELL", "REDEMPTION"} or movement_quantity < 0:
            reduction_quantity = min(abs(movement_quantity), max(quantity, 0))
            average_cost = cost_basis / quantity if quantity > 0 else unit_price
            quantity -= reduction_quantity
            cost_basis -= reduction_quantity * average_cost
            if quantity <= 0.000001:
                quantity = 0.0
                cost_basis = 0.0

    average_cost = cost_basis / quantity if quantity > 0 else 0
    return {
        "quantity": round(quantity, 6),
        "cost_basis": rounded_money(cost_basis),
        "average_cost": rounded_money(average_cost),
    }


def default_tax_for_proceed(proceeds_type, gross_amount):
    if proceeds_type == "JCP":
        return gross_amount * DEFAULT_JCP_TAX_RATE
    return 0


def normalize_proceed_payload(conn, current_user_id, payload, existing=None):
    existing = existing or {}
    merged = {
        "asset_id": existing.get("asset_id"),
        "proceeds_type": existing.get("proceeds_type"),
        "declared_date": existing.get("declared_date"),
        "record_date": existing.get("record_date"),
        "ex_date": existing.get("ex_date"),
        "payment_date": existing.get("payment_date"),
        "amount_per_unit": existing.get("amount_per_unit"),
        "eligible_quantity": existing.get("eligible_quantity"),
        "gross_amount": existing.get("gross_amount"),
        "tax_amount": existing.get("tax_amount"),
        "source": existing.get("source") or "manual",
        "notes": existing.get("notes") or "",
        "metadata": parse_metadata_value(existing.get("metadata")),
    }
    for key in merged:
        if key in payload:
            merged[key] = payload.get(key)

    asset_id = require_string(merged, "asset_id", "Ativo")
    ensure_asset_owner(conn, current_user_id, asset_id)
    proceeds_type = require_choice(merged, "proceeds_type", "Tipo de provento", ALLOWED_PROCEEDS_TYPES)
    declared_date = optional_date(merged, "declared_date", "Data de declaracao")
    record_date = require_date(merged, "record_date", "Data com")
    ex_date = optional_date(merged, "ex_date", "Data ex")
    payment_date = require_date(merged, "payment_date", "Data de pagamento")

    amount_per_unit = parse_optional_number(
        merged,
        "amount_per_unit",
        "Valor por cota",
        minimum=0,
    )
    eligible_quantity = parse_optional_number(
        merged,
        "eligible_quantity",
        "Quantidade elegivel",
        minimum=0,
    )
    gross_amount = parse_optional_number(
        merged,
        "gross_amount",
        "Valor bruto",
        minimum=0,
    )

    position = investment_position_at_date(conn, current_user_id, asset_id, record_date)
    if eligible_quantity is None:
        eligible_quantity = position["quantity"]

    if gross_amount is None:
        if amount_per_unit is None:
            raise ValidationError("Informe valor por cota ou valor bruto.")
        if eligible_quantity <= 0:
            raise ValidationError("Informe a quantidade elegivel ou cadastre uma posicao na data com.")
        gross_amount = amount_per_unit * eligible_quantity

    if amount_per_unit is None and eligible_quantity > 0:
        amount_per_unit = gross_amount / eligible_quantity

    tax_was_provided = "tax_amount" in payload and payload.get("tax_amount") not in (None, "")
    tax_amount = parse_optional_number(
        merged,
        "tax_amount",
        "Imposto",
        minimum=0,
    )
    should_recalculate_tax = (
        not tax_was_provided
        and (
            existing.get("id") is None
            or any(key in payload for key in ("proceeds_type", "amount_per_unit", "eligible_quantity", "gross_amount"))
        )
    )
    if tax_amount is None or should_recalculate_tax:
        tax_amount = default_tax_for_proceed(proceeds_type, gross_amount)

    gross_amount = rounded_money(gross_amount)
    tax_amount = rounded_money(tax_amount)
    if tax_amount - gross_amount > 0.000001:
        raise ValidationError("Imposto nao pode ser maior que o valor bruto.")

    metadata = merged.get("metadata")
    if metadata not in (None, "") and not isinstance(metadata, (dict, str)):
        raise ValidationError("Metadata deve ser um objeto valido.")

    return {
        "asset_id": asset_id,
        "proceeds_type": proceeds_type,
        "declared_date": declared_date,
        "record_date": record_date,
        "ex_date": ex_date,
        "payment_date": payment_date,
        "amount_per_unit": round(safe_float(amount_per_unit), 8) if amount_per_unit is not None else None,
        "eligible_quantity": round(safe_float(eligible_quantity), 6),
        "gross_amount": gross_amount,
        "tax_amount": tax_amount,
        "net_amount": rounded_money(gross_amount - tax_amount),
        "source": optional_string(merged, "source", 100) or "manual",
        "notes": optional_string(merged, "notes", 1000),
        "metadata": investment_metadata_dict(metadata),
    }


def proceed_status(payment_date):
    parsed_payment = parse_iso_date(payment_date)
    today = datetime.now().date()
    if parsed_payment and parsed_payment.date() > today:
        return "SCHEDULED"
    return "PAID"


def serialize_investment_proceed(row, conn=None, current_user_id=None):
    item = serialize_metadata_row(row)
    if not item:
        return None

    item["asset"] = {
        "id": item.get("asset_id"),
        "asset_class": item.pop("asset_class", None),
        "ticker": item.pop("ticker", None),
        "name": item.pop("asset_name", None),
    }
    item["status"] = proceed_status(item.get("payment_date"))

    position = None
    if conn is not None and current_user_id is not None and item.get("asset_id") and item.get("record_date"):
        try:
            position = investment_position_at_date(
                conn,
                current_user_id,
                item["asset_id"],
                item["record_date"],
            )
        except ValidationError:
            position = None

    eligible_quantity = safe_float(item.get("eligible_quantity"))
    average_cost = safe_float((position or {}).get("average_cost"))
    cost_basis = average_cost * eligible_quantity if eligible_quantity > 0 else 0
    gross_amount = safe_float(item.get("gross_amount"))
    net_amount = safe_float(item.get("net_amount"))
    tax_amount = safe_float(item.get("tax_amount"))

    item["cost_basis_at_record_date"] = rounded_money(cost_basis)
    item["average_cost_at_record_date"] = rounded_money(average_cost)
    item["gross_yield_on_cost_percent"] = round((gross_amount / cost_basis) * 100, 4) if cost_basis > 0 else 0
    item["yield_on_cost_percent"] = round((net_amount / cost_basis) * 100, 4) if cost_basis > 0 else 0
    item["effective_tax_rate_percent"] = round((tax_amount / gross_amount) * 100, 2) if gross_amount > 0 else 0
    return item


def fetch_investment_proceeds(conn, current_user_id, filters=None):
    filters = filters or {}
    query = """
        SELECT
            proceeds.*,
            asset.asset_class,
            asset.ticker,
            asset.name AS asset_name
        FROM investment_proceeds proceeds
        JOIN assets asset ON asset.id = proceeds.asset_id
        WHERE proceeds.user_id = ?
    """
    params = [current_user_id]

    if filters.get("asset_id"):
        query += " AND proceeds.asset_id = ?"
        params.append(filters["asset_id"])
    if filters.get("proceeds_type"):
        query += " AND proceeds.proceeds_type = ?"
        params.append(filters["proceeds_type"])
    if filters.get("date_from"):
        query += " AND proceeds.payment_date >= ?"
        params.append(filters["date_from"])
    if filters.get("date_to"):
        query += " AND proceeds.payment_date <= ?"
        params.append(filters["date_to"])

    today = datetime.now().strftime("%Y-%m-%d")
    if filters.get("status") == "PAID":
        query += " AND proceeds.payment_date <= ?"
        params.append(today)
    elif filters.get("status") == "SCHEDULED":
        query += " AND proceeds.payment_date > ?"
        params.append(today)

    direction = "ASC" if filters.get("ascending") else "DESC"
    query += f" ORDER BY proceeds.payment_date {direction}, proceeds.created_at {direction}"
    return conn.execute(query, params).fetchall()


def fetch_investment_proceed_by_id(conn, current_user_id, proceed_id):
    return conn.execute(
        """
        SELECT
            proceeds.*,
            asset.asset_class,
            asset.ticker,
            asset.name AS asset_name
        FROM investment_proceeds proceeds
        JOIN assets asset ON asset.id = proceeds.asset_id
        WHERE proceeds.user_id = ?
          AND proceeds.id = ?
        """,
        (current_user_id, proceed_id),
    ).fetchone()


def build_investment_proceeds_summary(items):
    summary = {
        "event_count": len(items),
        "gross_amount": 0,
        "tax_amount": 0,
        "net_amount": 0,
        "cost_basis": 0,
        "yield_on_cost_percent": 0,
        "paid_net_amount": 0,
        "scheduled_net_amount": 0,
        "by_type": {},
        "by_month": {},
        "next_events": [],
    }

    for item in items:
        gross = safe_float(item.get("gross_amount"))
        tax = safe_float(item.get("tax_amount"))
        net = safe_float(item.get("net_amount"))
        cost_basis = safe_float(item.get("cost_basis_at_record_date"))
        proceeds_type = item.get("proceeds_type") or "OTHER"
        month_key = str(item.get("payment_date") or "")[:7]

        summary["gross_amount"] += gross
        summary["tax_amount"] += tax
        summary["net_amount"] += net
        summary["cost_basis"] += cost_basis
        if item.get("status") == "SCHEDULED":
            summary["scheduled_net_amount"] += net
            summary["next_events"].append(item)
        else:
            summary["paid_net_amount"] += net

        type_bucket = summary["by_type"].setdefault(proceeds_type, {
            "proceeds_type": proceeds_type,
            "event_count": 0,
            "gross_amount": 0,
            "tax_amount": 0,
            "net_amount": 0,
        })
        type_bucket["event_count"] += 1
        type_bucket["gross_amount"] += gross
        type_bucket["tax_amount"] += tax
        type_bucket["net_amount"] += net

        if month_key:
            month_bucket = summary["by_month"].setdefault(month_key, {
                "month": month_key,
                "event_count": 0,
                "gross_amount": 0,
                "tax_amount": 0,
                "net_amount": 0,
            })
            month_bucket["event_count"] += 1
            month_bucket["gross_amount"] += gross
            month_bucket["tax_amount"] += tax
            month_bucket["net_amount"] += net

    for key in ("gross_amount", "tax_amount", "net_amount", "cost_basis", "paid_net_amount", "scheduled_net_amount"):
        summary[key] = rounded_money(summary[key])
    summary["yield_on_cost_percent"] = round(
        (summary["net_amount"] / summary["cost_basis"]) * 100,
        4,
    ) if summary["cost_basis"] > 0 else 0

    for bucket in summary["by_type"].values():
        for key in ("gross_amount", "tax_amount", "net_amount"):
            bucket[key] = rounded_money(bucket[key])
    for bucket in summary["by_month"].values():
        for key in ("gross_amount", "tax_amount", "net_amount"):
            bucket[key] = rounded_money(bucket[key])

    summary["by_type"] = sorted(summary["by_type"].values(), key=lambda item: item["proceeds_type"])
    summary["by_month"] = sorted(summary["by_month"].values(), key=lambda item: item["month"])
    summary["next_events"] = sorted(
        summary["next_events"],
        key=lambda item: (item.get("payment_date") or "", item.get("asset", {}).get("ticker") or ""),
    )[:8]
    return summary


def parse_investment_proceeds_filters(args):
    filters = {}
    if args.get("asset_id"):
        filters["asset_id"] = str(args.get("asset_id")).strip()
    if args.get("proceeds_type"):
        filters["proceeds_type"] = require_choice(
            {"proceeds_type": args.get("proceeds_type")},
            "proceeds_type",
            "Tipo de provento",
            ALLOWED_PROCEEDS_TYPES,
        )
    if args.get("date_from"):
        filters["date_from"] = require_date({"date_from": args.get("date_from")}, "date_from", "Data inicial")
    if args.get("date_to"):
        filters["date_to"] = require_date({"date_to": args.get("date_to")}, "date_to", "Data final")
    if args.get("status"):
        status = str(args.get("status")).strip().upper()
        if status not in {"PAID", "SCHEDULED", "ALL"}:
            raise ValidationError("Status invalido.")
        if status != "ALL":
            filters["status"] = status
    filters["ascending"] = args.get("ascending") == "true"
    return filters


def default_closing_day(due_day):
    """Fechamento presumido quando o cartao nao tem dia de fechamento gravado."""
    candidate = int(due_day) - 7
    return candidate if candidate > 0 else 30 + candidate


def add_invoice_months(month, year, months):
    """Avanca (mes, ano) em `months` meses, normalizando a virada de ano."""
    zero_based = (int(month) - 1) + int(months)
    return zero_based % 12 + 1, int(year) + zero_based // 12


def compute_invoice_start(purchase_date, due_day, closing_day=None):
    """Fatura em que uma compra cai, dados o dia de fechamento e o de vencimento.

    Regra: uma compra feita antes do fechamento entra na fatura que fecha neste
    ciclo; a partir do fechamento (inclusive) ela escorrega para a proxima. Quando
    o fechamento cai depois do vencimento no mes, o ciclo ja esta deslocado e a
    compra vai um mes adiante do que essa contagem sugeriria.

    Esta regra vivia em `frontend/src/pages/Carteira.jsx` e foi trazida para ca em
    2026-09-15 para poder ser testada e reusada — o comportamento e o mesmo.
    """
    if isinstance(purchase_date, str):
        purchase_date = datetime.strptime(purchase_date, "%Y-%m-%d").date()

    due_day = int(due_day)
    closing_day = int(closing_day) if closing_day else default_closing_day(due_day)

    purchase_day = purchase_date.day
    offset = 0
    if closing_day < due_day:
        if purchase_day >= closing_day:
            offset = 1
    elif purchase_day < closing_day:
        offset = 1
    else:
        offset = 2

    month, year = add_invoice_months(purchase_date.month, purchase_date.year, offset)
    return {"invoice_month": month, "invoice_year": year}


def split_installments(total_amount, installments_count):
    """Divide um total em parcelas de centavos inteiros, sem perder centavo.

    O resto e distribuido nas primeiras parcelas, entao a soma das parcelas e
    sempre igual ao total informado.
    """
    total_cents = int(Decimal(str(rounded_money(total_amount))).scaleb(2).to_integral_value(rounding=ROUND_HALF_UP))
    base_cents, remainder = divmod(total_cents, installments_count)
    return [
        rounded_money((base_cents + (1 if index < remainder else 0)) / 100)
        for index in range(installments_count)
    ]


def build_installment_rows(purchase, card):
    """Linhas de cc_expenses para uma compra parcelada, ja com a fatura de cada uma."""
    start = compute_invoice_start(
        purchase["purchase_date"],
        card["due_day"],
        card["closing_day"],
    )
    amounts = split_installments(purchase["total_amount"], purchase["installments"])

    rows = []
    for index, amount in enumerate(amounts):
        month, year = add_invoice_months(start["invoice_month"], start["invoice_year"], index)
        rows.append({
            "card_id": purchase["card_id"],
            "category": purchase["category"],
            "description": purchase["description"],
            "amount": amount,
            "purchase_date": purchase["purchase_date"],
            "invoice_month": month,
            "invoice_year": year,
            "installment_info": f"{index + 1}/{purchase['installments']}",
            "status": "OPEN",
        })
    return rows


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


def parse_iso_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def parse_iso_datetime(value):
    if not value:
        return None
    raw_value = str(value).strip()
    if not raw_value:
        return None
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        parsed_date = parse_iso_date(raw_value)
        if not parsed_date:
            return None
        return parsed_date.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def quote_age_hours(quoted_at):
    parsed = parse_iso_datetime(quoted_at)
    if not parsed:
        return None
    return max((datetime.now(timezone.utc) - parsed).total_seconds() / 3600, 0)


def quote_status(quoted_at):
    age_hours = quote_age_hours(quoted_at)
    if age_hours is None:
        return "missing"
    if age_hours > PRICE_QUOTE_STALE_HOURS:
        return "stale"
    return "fresh"


def quote_info_from_investment(investment):
    quoted_at = investment.get("current_quote_quoted_at")
    status = quote_status(quoted_at)
    age_hours = quote_age_hours(quoted_at)
    return {
        "id": investment.get("current_quote_id"),
        "source": investment.get("current_quote_source") or "fallback",
        "quoted_at": quoted_at,
        "metadata": investment.get("current_quote_metadata") or {},
        "age_hours": round(age_hours, 2) if age_hours is not None else None,
        "stale_after_hours": PRICE_QUOTE_STALE_HOURS,
        "status": status,
        "is_stale": status != "fresh",
    }


def month_label(date_value):
    return date_value.strftime("%m/%y")


def month_key(date_value):
    return date_value.strftime("%Y-%m")


def month_end(date_value):
    last_day = calendar.monthrange(date_value.year, date_value.month)[1]
    return datetime(date_value.year, date_value.month, last_day, 23, 59, 59)


def investment_movement_date(investment):
    metadata = investment.get("metadata") or {}
    for key in ("redemption_date", "sale_date", "purchase_date"):
        parsed = parse_iso_date(metadata.get(key))
        if parsed:
            return parsed
    return parse_iso_date(investment.get("created_at")) or datetime.now()


def parse_asset_class_filter(value):
    normalized = str(value or "").strip().upper()
    if normalized in {"", "TODOS", "ALL"}:
        return None
    return normalized if normalized in ALLOWED_ASSET_CLASSES else None


def historical_price_for_month(historical_prices, ticker, target_month_key):
    ticker_prices = historical_prices.get(ticker_key(ticker), {})
    if not isinstance(ticker_prices, dict):
        return None

    price = safe_float(ticker_prices.get(target_month_key), None)
    if price is not None and math.isfinite(price) and price > 0:
        return price

    previous_keys = sorted(
        key for key in ticker_prices
        if isinstance(key, str) and key <= target_month_key
    )
    if not previous_keys:
        return None

    price = safe_float(ticker_prices.get(previous_keys[-1]), None)
    if price is not None and math.isfinite(price) and price > 0:
        return price
    return None


def fixed_income_net_value(asset_class, metadata, invested_value, market_value, reference_date):
    if asset_class != "FIXED_INCOME":
        return market_value

    profit = market_value - invested_value
    if profit <= 0 or metadata.get("is_tax_free", False):
        return market_value

    purchase_date = parse_iso_date(metadata.get("purchase_date"))
    if not purchase_date:
        return market_value

    days_invested = max((reference_date - purchase_date).days, 0)
    if days_invested <= 180:
        tax_rate = 0.225
    elif days_invested <= 360:
        tax_rate = 0.200
    elif days_invested <= 720:
        tax_rate = 0.175
    else:
        tax_rate = 0.150

    return market_value - (profit * tax_rate)


def movement_affects_fixed_income_position(investment):
    metadata = investment.get("metadata") or {}
    return (
        investment.get("asset_class") == "FIXED_INCOME"
        and safe_float(investment.get("quantity")) < 0
        and metadata.get("is_redemption")
        and metadata.get("affects_position")
        and metadata.get("related_id")
    )


def current_price_from_position(data, default=0):
    price = safe_float(data.get("current_price"), default)
    if data.get("class") == "FIXED_INCOME" and data.get("original_invested", 0) > 0:
        factor = price / data["original_invested"]
        price = data["total_invested"] * factor
    return max(price, 0)


def portfolio_evolution_months(months_back):
    current_month = datetime(datetime.now().year, datetime.now().month, 1)
    return [
        subtract_months(current_month, months_back - 1 - index)
        for index in range(months_back)
    ]


def build_portfolio_evolution(investments_data, historical_prices, months_back):
    months = portfolio_evolution_months(months_back)
    current_month_key = month_key(datetime.now())
    evolution = []

    for month_start in months:
        target_key = month_key(month_start)
        target_end = month_end(month_start)
        positions = {}

        for investment in investments_data:
            metadata = investment.get("metadata") or {}
            if investment_movement_date(investment) > target_end:
                continue

            asset_class = investment.get("asset_class")
            ticker = ticker_key(investment.get("ticker_or_name"))
            if not asset_class or not ticker:
                continue

            quantity = safe_float(investment.get("quantity"))
            average_price = safe_float(investment.get("average_price"))
            if quantity == 0:
                continue

            if movement_affects_fixed_income_position(investment):
                group_key = str(metadata.get("related_id"))
            elif asset_class == "FIXED_INCOME" and metadata.get("is_redemption"):
                continue
            else:
                group_key = str(investment.get("id")) if asset_class == "FIXED_INCOME" else f"{asset_class}:{ticker}"

            if group_key not in positions:
                positions[group_key] = {
                    "ticker": ticker,
                    "class": asset_class,
                    "quantity": 0,
                    "applied": 0,
                    "original_applied": 0,
                    "current_price": safe_float(investment.get("current_price"), average_price),
                    "metadata": metadata,
                }

            position = positions[group_key]
            position["applied"] += quantity * average_price
            if not movement_affects_fixed_income_position(investment):
                position["quantity"] += quantity
                if asset_class == "FIXED_INCOME" and quantity > 0:
                    position["original_applied"] += quantity * average_price
                    position["metadata"] = metadata
                    position["ticker"] = ticker
            if investment.get("current_price") is not None and not movement_affects_fixed_income_position(investment):
                position["current_price"] = safe_float(investment.get("current_price"), average_price)

        applied_total = 0
        net_total = 0

        for position in positions.values():
            quantity = position["quantity"]
            applied_value = position["applied"]
            if quantity <= 0 or applied_value <= 0:
                continue

            adjusted_quantity = quantity
            if position["class"] == "CATTLE":
                mortality_rate = safe_float(position["metadata"].get("mortality_rate"))
                adjusted_quantity = quantity * (1 - mortality_rate)

            if position["class"] in QUOTED_ASSET_CLASSES:
                price = historical_price_for_month(
                    historical_prices,
                    position["ticker"],
                    target_key,
                )
                if price is None:
                    price = safe_float(position.get("current_price"), applied_value / quantity)
                market_value = adjusted_quantity * price
            elif position["class"] == "FIXED_INCOME" and target_key == current_month_key:
                original_applied = position.get("original_applied", applied_value)
                if original_applied > 0:
                    factor = safe_float(position.get("current_price"), original_applied) / original_applied
                    market_value = applied_value * factor
                else:
                    market_value = applied_value
            elif target_key == current_month_key:
                market_value = adjusted_quantity * safe_float(
                    position.get("current_price"),
                    applied_value / quantity,
                )
            else:
                market_value = applied_value

            net_value = fixed_income_net_value(
                position["class"],
                position["metadata"],
                applied_value,
                market_value,
                target_end,
            )

            applied_total += applied_value
            net_total += net_value

        gain = net_total - applied_total
        evolution.append({
            "month": month_label(month_start),
            "month_key": target_key,
            "patrimonio": rounded_money(max(net_total, 0)),
            "valorAplicado": rounded_money(max(applied_total, 0)),
            "ganhoCapital": rounded_money(max(gain, 0)),
            "ganhoCapitalReal": rounded_money(gain),
        })

    return evolution


def parse_json_body():
    return request.get_json(silent=True) or {}


@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "ok",
        "database": "sqlite",
        "journal_mode": database_status()["journal_mode"],
    }), 200


@app.route("/api/database/status", methods=["GET"])
@token_required
def get_database_status(current_user_id):
    return jsonify(database_status()), 200


@app.route("/api/database/backups", methods=["POST"])
@token_required
def backup_database(current_user_id):
    try:
        backup = create_database_backup()
        backup["pruned"] = prune_database_backups()
        return jsonify(backup), 201
    except Exception as exc:
        print(f"Erro ao criar backup SQLite: {exc}")
        return jsonify({"error": "Nao foi possivel criar o backup do banco."}), 500


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
            ensure_default_account(conn, user_id)
            seed_default_categories(conn, user_id)
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


# ---------------------------------------------------------------------------
# Contas bancarias e categorias (3.1 / 3.2 de docs/next-steps.md)
# ---------------------------------------------------------------------------


def serialize_account(row):
    item = serialize_metadata_row(row)
    if item:
        item["is_default"] = bool(item.get("is_default"))
        for key in ("balance", "initial_balance"):
            if key in item and item[key] is not None:
                item[key] = rounded_money(item[key])
    return item


def default_account_id(current_user_id):
    return f"acct:{current_user_id}"


def ensure_default_account(conn, current_user_id):
    """Garante que o usuario tenha ao menos uma conta e devolve o id dela.

    Contas nasceram na migration 007, mas usuarios criados depois dela e
    lancamentos vindos de outros fluxos (caixa de investimento, por exemplo)
    ainda precisam de um destino. A conta padrao e sempre criada com o mesmo id
    deterministico usado no backfill, para que nao existam duas "Conta
    Principal" para o mesmo usuario.
    """
    existing = conn.execute(
        """
        SELECT id FROM accounts
        WHERE user_id = ? AND archived_at IS NULL
        ORDER BY is_default DESC, created_at ASC
        LIMIT 1
        """,
        (current_user_id,),
    ).fetchone()
    if existing:
        return existing["id"]

    account_id = default_account_id(current_user_id)
    conn.execute(
        """
        INSERT OR IGNORE INTO accounts (id, user_id, name, type, is_default)
        VALUES (?, ?, ?, 'CHECKING', 1)
        """,
        (account_id, current_user_id, DEFAULT_ACCOUNT_NAME),
    )
    return account_id


def seed_default_categories(conn, current_user_id):
    """Cria as 10 categorias iniciais para um usuario novo."""
    conn.executemany(
        """
        INSERT OR IGNORE INTO categories (id, user_id, name, kind)
        VALUES (?, ?, ?, ?)
        """,
        [
            (f"cat:{current_user_id}:{slug}", current_user_id, name, kind)
            for slug, name, kind in DEFAULT_CATEGORY_SEEDS
        ],
    )


def fetch_account(conn, current_user_id, account_id):
    if not account_id:
        return None
    return conn.execute(
        "SELECT * FROM accounts WHERE id = ? AND user_id = ?",
        (account_id, current_user_id),
    ).fetchone()


def require_account(conn, current_user_id, account_id, label="Conta"):
    account = fetch_account(conn, current_user_id, account_id)
    if not account:
        raise ValidationError(f"{label} nao encontrada.")
    if account["archived_at"]:
        raise ValidationError(f"{label} esta arquivada.")
    return account


def resolve_account_id(conn, current_user_id, payload, key="account_id", label="Conta"):
    """Conta informada no payload, ou a conta padrao quando omitida."""
    raw = payload.get(key)
    if raw in (None, ""):
        return ensure_default_account(conn, current_user_id)
    return require_account(conn, current_user_id, str(raw), label)["id"]


def fetch_category(conn, current_user_id, category_id):
    if not category_id:
        return None
    return conn.execute(
        "SELECT * FROM categories WHERE id = ? AND user_id = ?",
        (category_id, current_user_id),
    ).fetchone()


def resolve_category(conn, current_user_id, payload, required=True):
    """Resolve (nome, id) da categoria de um lancamento.

    Aceita `category_id` (novo) ou `category` em texto (o que o app sempre
    mandou). O nome continua sendo gravado em transactions.category: e ele que
    o Dashboard agrupa e e o fallback caso a categoria seja apagada depois.
    """
    category_id = payload.get("category_id")
    if category_id not in (None, ""):
        row = fetch_category(conn, current_user_id, str(category_id))
        if not row:
            raise ValidationError("Categoria nao encontrada.")
        if row["archived_at"]:
            raise ValidationError("Categoria esta arquivada.")
        return row["name"], row["id"]

    if required:
        name = require_string(payload, "category", "Categoria")
    else:
        name = optional_string(payload, "category", max_length=255)
        if not name:
            return None, None

    row = conn.execute(
        "SELECT id FROM categories WHERE user_id = ? AND name = ? LIMIT 1",
        (current_user_id, name),
    ).fetchone()
    return name, row["id"] if row else None


def account_balance_rows(conn, current_user_id):
    """Saldo por conta: inicial + receitas - despesas -/+ transferencias.

    TRANSFER sai de account_id e entra em transfer_account_id, por isso aparece
    duas vezes aqui com sinais opostos e some do consolidado.
    """
    return conn.execute(
        """
        SELECT
            a.*,
            a.initial_balance
              + COALESCE((
                    SELECT SUM(
                        CASE t.type
                            WHEN 'INCOME' THEN t.amount
                            WHEN 'EXPENSE' THEN -t.amount
                            WHEN 'TRANSFER' THEN -t.amount
                            ELSE 0
                        END
                    )
                    FROM transactions t
                    WHERE t.user_id = a.user_id AND t.account_id = a.id
                ), 0)
              + COALESCE((
                    SELECT SUM(t.amount)
                    FROM transactions t
                    WHERE t.user_id = a.user_id
                      AND t.type = 'TRANSFER'
                      AND t.transfer_account_id = a.id
                ), 0) AS balance
        FROM accounts a
        WHERE a.user_id = ?
        ORDER BY a.archived_at IS NOT NULL, a.is_default DESC, a.name COLLATE NOCASE
        """,
        (current_user_id,),
    ).fetchall()


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
        return jsonify([serialize_transaction(row) for row in rows]), 200

    payload = parse_json_body()
    item_id = new_id()
    with get_db() as conn:
        try:
            amount = parse_number(payload, "amount", "Valor", minimum=0, allow_zero=False)
            date_value = require_date(payload, "date", "Data")
            description = optional_string(payload, "description")
            transaction_type = require_choice(payload, "type", "Tipo", ALLOWED_TRANSACTION_TYPES)
            if transaction_type == "TRANSFER":
                raise ValidationError(
                    "Use POST /api/transfers para registrar uma transferencia entre contas."
                )
            category, category_id = resolve_category(conn, current_user_id, payload)
            account_id = resolve_account_id(conn, current_user_id, payload)
        except ValidationError as exc:
            return validation_error(str(exc))

        conn.execute(
            """
            INSERT INTO transactions
            (id, user_id, account_id, amount, date, category, category_id, description, type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                current_user_id,
                account_id,
                rounded_money(amount),
                date_value,
                category,
                category_id,
                description,
                transaction_type,
            ),
        )
        item = conn.execute("SELECT * FROM transactions WHERE id = ?", (item_id,)).fetchone()
    return jsonify(serialize_transaction(item)), 201


@app.route("/api/transactions/<item_id>", methods=["PATCH"])
@token_required
def update_transaction(current_user_id, item_id):
    """Editar um lancamento (3.7 de docs/next-steps.md).

    Ate aqui so existia DELETE: corrigir um digito significava apagar e digitar
    de novo. Lancamentos espelhados de investimento continuam bloqueados — eles
    sao derivados da movimentacao e sao reescritos por
    sync_investment_cash_transaction().
    """
    payload = parse_json_body()
    with get_db() as conn:
        item = conn.execute(
            "SELECT * FROM transactions WHERE id = ? AND user_id = ?",
            (item_id, current_user_id),
        ).fetchone()
        if not item:
            return jsonify({"error": "Lancamento nao encontrado."}), 404
        if item["source_type"] == INVESTMENT_CASH_SOURCE_TYPE:
            return jsonify({
                "error": "Este lancamento de caixa esta vinculado a uma movimentacao de investimento. Edite a movimentacao de investimento para manter o patrimonio consistente."
            }), 409

        updates = {}
        try:
            if "amount" in payload:
                updates["amount"] = rounded_money(
                    parse_number(payload, "amount", "Valor", minimum=0, allow_zero=False)
                )
            if "date" in payload:
                updates["date"] = require_date(payload, "date", "Data")
            if "description" in payload:
                updates["description"] = optional_string(payload, "description")
            if "type" in payload:
                transaction_type = require_choice(
                    payload, "type", "Tipo", ALLOWED_TRANSACTION_TYPES
                )
                if (transaction_type == "TRANSFER") != (item["type"] == "TRANSFER"):
                    raise ValidationError(
                        "Nao e possivel converter um lancamento comum em transferencia."
                    )
                updates["type"] = transaction_type
            if "category" in payload or "category_id" in payload:
                category, category_id = resolve_category(conn, current_user_id, payload)
                updates["category"] = category
                updates["category_id"] = category_id
            if "account_id" in payload:
                updates["account_id"] = resolve_account_id(conn, current_user_id, payload)
            if "transfer_account_id" in payload:
                if item["type"] != "TRANSFER":
                    raise ValidationError(
                        "Conta de destino so se aplica a transferencias."
                    )
                updates["transfer_account_id"] = require_account(
                    conn,
                    current_user_id,
                    str(payload.get("transfer_account_id") or ""),
                    "Conta de destino",
                )["id"]
        except ValidationError as exc:
            return validation_error(str(exc))

        if not updates:
            return validation_error("Informe ao menos um campo para atualizar.")

        origin = updates.get("account_id", item["account_id"])
        destination = updates.get("transfer_account_id", item["transfer_account_id"])
        if item["type"] == "TRANSFER" and origin == destination:
            return validation_error("Origem e destino devem ser contas diferentes.")

        assignments = ", ".join(f"{column} = ?" for column in updates)
        conn.execute(
            f"UPDATE transactions SET {assignments} WHERE id = ? AND user_id = ?",
            (*updates.values(), item_id, current_user_id),
        )
        updated = conn.execute(
            "SELECT * FROM transactions WHERE id = ? AND user_id = ?",
            (item_id, current_user_id),
        ).fetchone()
    return jsonify(serialize_transaction(updated)), 200


@app.route("/api/transactions/<item_id>", methods=["DELETE"])
@token_required
def delete_transaction(current_user_id, item_id):
    with get_db() as conn:
        item = conn.execute(
            "SELECT source_type FROM transactions WHERE id = ? AND user_id = ?",
            (item_id, current_user_id),
        ).fetchone()
        if not item:
            return jsonify({"deleted": False}), 404
        if item["source_type"] == INVESTMENT_CASH_SOURCE_TYPE:
            return jsonify({
                "error": "Este lancamento de caixa esta vinculado a uma movimentacao de investimento. Exclua a movimentacao de investimento para manter o patrimonio consistente."
            }), 409
        cursor = conn.execute(
            "DELETE FROM transactions WHERE id = ? AND user_id = ?",
            (item_id, current_user_id),
        )
    if cursor.rowcount == 0:
        return jsonify({"deleted": False}), 404
    return jsonify({"deleted": True}), 200


@app.route("/api/accounts", methods=["GET", "POST"])
@token_required
def accounts(current_user_id):
    if request.method == "GET":
        include_archived = str(request.args.get("include_archived", "")).lower() in ("1", "true", "yes")
        with get_db() as conn:
            ensure_default_account(conn, current_user_id)
            rows = account_balance_rows(conn, current_user_id)
        items = [serialize_account(row) for row in rows]
        if not include_archived:
            items = [item for item in items if not item.get("archived_at")]
        return jsonify(items), 200

    payload = parse_json_body()
    try:
        name = require_string(payload, "name", "Nome da conta")
        account_type = require_choice(payload, "type", "Tipo de conta", ALLOWED_ACCOUNT_TYPES)
        institution = optional_string(payload, "institution", max_length=255)
        initial_balance = rounded_money(
            parse_optional_number(payload, "initial_balance", "Saldo inicial") or 0
        )
        currency = (optional_string(payload, "currency", max_length=3) or "BRL").upper()
    except ValidationError as exc:
        return validation_error(str(exc))

    account_id = new_id()
    try:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO accounts
                (id, user_id, name, type, institution, initial_balance, currency)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    current_user_id,
                    name,
                    account_type,
                    institution or None,
                    initial_balance,
                    currency,
                ),
            )
            row = fetch_account(conn, current_user_id, account_id)
    except sqlite3.IntegrityError:
        return validation_error("Ja existe uma conta com este nome.", 409)

    item = serialize_account(row)
    item["balance"] = initial_balance
    return jsonify(item), 201


@app.route("/api/accounts/<account_id>", methods=["PATCH", "DELETE"])
@token_required
def account_detail(current_user_id, account_id):
    with get_db() as conn:
        account = fetch_account(conn, current_user_id, account_id)
        if not account:
            return jsonify({"error": "Conta nao encontrada."}), 404

        if request.method == "DELETE":
            # Arquivar, nao apagar: transactions.account_id usa ON DELETE SET
            # NULL e uma exclusao deixaria lancamentos sem conta, silenciosamente.
            used = conn.execute(
                """
                SELECT COUNT(*) AS total FROM transactions
                WHERE user_id = ? AND (account_id = ? OR transfer_account_id = ?)
                """,
                (current_user_id, account_id, account_id),
            ).fetchone()["total"]
            remaining = conn.execute(
                """
                SELECT COUNT(*) AS total FROM accounts
                WHERE user_id = ? AND archived_at IS NULL AND id <> ?
                """,
                (current_user_id, account_id),
            ).fetchone()["total"]
            if remaining == 0:
                return validation_error(
                    "Esta e a unica conta ativa. Crie outra antes de arquivar esta.", 409
                )
            conn.execute(
                """
                UPDATE accounts
                SET archived_at = ?, is_default = 0, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (utc_timestamp(), utc_timestamp(), account_id, current_user_id),
            )
            return jsonify({"archived": True, "transactions": used}), 200

        payload = parse_json_body()
        updates = {}
        try:
            if "name" in payload:
                updates["name"] = require_string(payload, "name", "Nome da conta")
            if "type" in payload:
                updates["type"] = require_choice(
                    payload, "type", "Tipo de conta", ALLOWED_ACCOUNT_TYPES
                )
            if "institution" in payload:
                updates["institution"] = optional_string(payload, "institution", max_length=255) or None
            if "initial_balance" in payload:
                updates["initial_balance"] = rounded_money(
                    parse_number(payload, "initial_balance", "Saldo inicial")
                )
            if "archived_at" in payload and payload.get("archived_at") in (None, ""):
                updates["archived_at"] = None
        except ValidationError as exc:
            return validation_error(str(exc))

        if payload.get("is_default") is True:
            conn.execute(
                "UPDATE accounts SET is_default = 0 WHERE user_id = ?",
                (current_user_id,),
            )
            updates["is_default"] = 1

        if not updates:
            return validation_error("Informe ao menos um campo para atualizar.")

        updates["updated_at"] = utc_timestamp()
        assignments = ", ".join(f"{column} = ?" for column in updates)
        try:
            conn.execute(
                f"UPDATE accounts SET {assignments} WHERE id = ? AND user_id = ?",
                (*updates.values(), account_id, current_user_id),
            )
        except sqlite3.IntegrityError:
            return validation_error("Ja existe uma conta com este nome.", 409)
        row = fetch_account(conn, current_user_id, account_id)
    return jsonify(serialize_account(row)), 200


@app.route("/api/transfers", methods=["POST"])
@token_required
def create_transfer(current_user_id):
    """Transferencia entre contas proprias.

    Uma unica linha type='TRANSFER': sai de account_id, entra em
    transfer_account_id. Nao e receita nem despesa, entao nao distorce os
    totais do mes — que era exatamente o problema de registrar como
    despesa + receita.
    """
    payload = parse_json_body()
    with get_db() as conn:
        try:
            amount = rounded_money(
                parse_number(payload, "amount", "Valor", minimum=0, allow_zero=False)
            )
            date_value = require_date(payload, "date", "Data")
            description = optional_string(payload, "description")
            origin = require_account(
                conn, current_user_id, str(payload.get("account_id") or ""), "Conta de origem"
            )
            destination = require_account(
                conn,
                current_user_id,
                str(payload.get("transfer_account_id") or ""),
                "Conta de destino",
            )
            if origin["id"] == destination["id"]:
                raise ValidationError("Origem e destino devem ser contas diferentes.")
            category, category_id = resolve_category(conn, current_user_id, payload, required=False)
        except ValidationError as exc:
            return validation_error(str(exc))

        item_id = new_id()
        default_description = "{} -> {}".format(origin["name"], destination["name"])
        conn.execute(
            """
            INSERT INTO transactions
            (id, user_id, account_id, transfer_account_id, amount, date,
             category, category_id, description, type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'TRANSFER')
            """,
            (
                item_id,
                current_user_id,
                origin["id"],
                destination["id"],
                amount,
                date_value,
                category or TRANSFER_CATEGORY,
                category_id,
                description or default_description,
            ),
        )
        item = conn.execute(
            "SELECT * FROM transactions WHERE id = ? AND user_id = ?",
            (item_id, current_user_id),
        ).fetchone()
    return jsonify(serialize_transaction(item)), 201


@app.route("/api/categories", methods=["GET", "POST"])
@token_required
def categories(current_user_id):
    if request.method == "GET":
        include_archived = str(request.args.get("include_archived", "")).lower() in ("1", "true", "yes")
        kind = str(request.args.get("kind", "") or "").strip().upper()
        with get_db() as conn:
            seed_default_categories(conn, current_user_id)
            rows = conn.execute(
                """
                SELECT c.*, parent.name AS parent_name
                FROM categories c
                LEFT JOIN categories parent ON parent.id = c.parent_id
                WHERE c.user_id = ?
                ORDER BY COALESCE(parent.name, c.name) COLLATE NOCASE,
                         c.parent_id IS NOT NULL,
                         c.name COLLATE NOCASE
                """,
                (current_user_id,),
            ).fetchall()
        items = [row_to_dict(row) for row in rows]
        if not include_archived:
            items = [item for item in items if not item.get("archived_at")]
        if kind in ALLOWED_CATEGORY_KINDS:
            items = [item for item in items if item["kind"] in (kind, "BOTH")]
        return jsonify(items), 200

    payload = parse_json_body()
    with get_db() as conn:
        try:
            name = require_string(payload, "name", "Nome da categoria")
            kind = require_choice(payload, "kind", "Tipo da categoria", ALLOWED_CATEGORY_KINDS)
            color = optional_string(payload, "color", max_length=32) or None
            icon = optional_string(payload, "icon", max_length=64) or None
            parent_id = payload.get("parent_id")
            if parent_id in (None, ""):
                parent_id = None
            else:
                parent = fetch_category(conn, current_user_id, str(parent_id))
                if not parent:
                    raise ValidationError("Categoria pai nao encontrada.")
                if parent["parent_id"]:
                    raise ValidationError("So existe um nivel de subcategoria.")
                parent_id = parent["id"]
        except ValidationError as exc:
            return validation_error(str(exc))

        category_id = new_id()
        try:
            conn.execute(
                """
                INSERT INTO categories (id, user_id, name, kind, parent_id, color, icon)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (category_id, current_user_id, name, kind, parent_id, color, icon),
            )
        except sqlite3.IntegrityError:
            return validation_error("Ja existe uma categoria com este nome.", 409)
        row = fetch_category(conn, current_user_id, category_id)
    return jsonify(row_to_dict(row)), 201


@app.route("/api/categories/<category_id>", methods=["PATCH", "DELETE"])
@token_required
def category_detail(current_user_id, category_id):
    with get_db() as conn:
        category = fetch_category(conn, current_user_id, category_id)
        if not category:
            return jsonify({"error": "Categoria nao encontrada."}), 404

        if request.method == "DELETE":
            # Arquivar. Apagar zeraria transactions.category_id via ON DELETE
            # SET NULL e os lancamentos perderiam a ligacao sem aviso.
            children = conn.execute(
                """
                SELECT COUNT(*) AS total FROM categories
                WHERE user_id = ? AND parent_id = ? AND archived_at IS NULL
                """,
                (current_user_id, category_id),
            ).fetchone()["total"]
            if children:
                return validation_error(
                    "Arquive as subcategorias antes de arquivar esta categoria.", 409
                )
            conn.execute(
                "UPDATE categories SET archived_at = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (utc_timestamp(), utc_timestamp(), category_id, current_user_id),
            )
            return jsonify({"archived": True}), 200

        payload = parse_json_body()
        updates = {}
        try:
            if "name" in payload:
                updates["name"] = require_string(payload, "name", "Nome da categoria")
            if "kind" in payload:
                updates["kind"] = require_choice(
                    payload, "kind", "Tipo da categoria", ALLOWED_CATEGORY_KINDS
                )
            if "color" in payload:
                updates["color"] = optional_string(payload, "color", max_length=32) or None
            if "icon" in payload:
                updates["icon"] = optional_string(payload, "icon", max_length=64) or None
            if "parent_id" in payload:
                parent_id = payload.get("parent_id")
                if parent_id in (None, ""):
                    updates["parent_id"] = None
                else:
                    parent = fetch_category(conn, current_user_id, str(parent_id))
                    if not parent:
                        raise ValidationError("Categoria pai nao encontrada.")
                    if parent["id"] == category_id:
                        raise ValidationError("Uma categoria nao pode ser pai dela mesma.")
                    if parent["parent_id"]:
                        raise ValidationError("So existe um nivel de subcategoria.")
                    updates["parent_id"] = parent["id"]
            if "archived_at" in payload and payload.get("archived_at") in (None, ""):
                updates["archived_at"] = None
        except ValidationError as exc:
            return validation_error(str(exc))

        if not updates:
            return validation_error("Informe ao menos um campo para atualizar.")

        # Renomear a categoria renomeia junto o texto gravado nos lancamentos,
        # que e o que o Dashboard agrupa.
        new_name = updates.get("name")
        updates["updated_at"] = utc_timestamp()
        assignments = ", ".join(f"{column} = ?" for column in updates)
        try:
            conn.execute(
                f"UPDATE categories SET {assignments} WHERE id = ? AND user_id = ?",
                (*updates.values(), category_id, current_user_id),
            )
        except sqlite3.IntegrityError:
            return validation_error("Ja existe uma categoria com este nome.", 409)
        if new_name and new_name != category["name"]:
            conn.execute(
                "UPDATE transactions SET category = ? WHERE user_id = ? AND category_id = ?",
                (new_name, current_user_id, category_id),
            )
        row = fetch_category(conn, current_user_id, category_id)
    return jsonify(row_to_dict(row)), 200


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


@app.route("/api/cc-expenses/purchases", methods=["POST"])
@token_required
def create_cc_purchase(current_user_id):
    """Registra uma compra no cartao, parcelando e escolhendo a fatura no servidor.

    O cliente manda a compra (valor total e numero de parcelas); a regra de qual
    fatura cada parcela ocupa fica aqui, junto do cartao que a define.
    """
    payload = parse_json_body()
    if not isinstance(payload, dict):
        return validation_error("Informe uma compra valida.")

    try:
        card_id = require_string(payload, "card_id", "Cartao")
        purchase = {
            "card_id": card_id,
            "category": require_string(payload, "category", "Categoria"),
            "description": require_string(payload, "description", "Descricao", max_length=500),
            "total_amount": parse_number(payload, "total_amount", "Valor total", minimum=0, allow_zero=False),
            "purchase_date": require_date(payload, "purchase_date", "Data da compra"),
            "installments": parse_int_number(payload, "installments", "Parcelas", minimum=1, maximum=72),
        }

        with get_db() as conn:
            ensure_credit_card_owner(conn, current_user_id, card_id)
            card = conn.execute(
                "SELECT due_day, closing_day FROM credit_cards WHERE id = ? AND user_id = ?",
                (card_id, current_user_id),
            ).fetchone()
            if not card:
                raise ValidationError("Cartao nao encontrado.")

            rows = build_installment_rows(purchase, card)
            inserted = []
            for row in rows:
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
                        row["card_id"],
                        row["category"],
                        row["description"],
                        row["amount"],
                        row["purchase_date"],
                        row["invoice_month"],
                        row["invoice_year"],
                        row["installment_info"],
                        row["status"],
                    ),
                )
                inserted.append(item_id)

            placeholders = ",".join("?" for _ in inserted)
            created = conn.execute(
                f"SELECT * FROM cc_expenses WHERE id IN ({placeholders})"
                " ORDER BY invoice_year ASC, invoice_month ASC",
                inserted,
            ).fetchall()
    except ValidationError as exc:
        return validation_error(str(exc))
    except sqlite3.IntegrityError:
        return jsonify({"error": "Nao foi possivel criar a compra no cartao."}), 400

    return jsonify([row_to_dict(row) for row in created]), 201


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


@app.route("/api/assets", methods=["GET"])
@token_required
def list_assets(current_user_id):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM assets
            WHERE user_id = ?
            ORDER BY asset_class ASC, ticker ASC
            """,
            (current_user_id,),
        ).fetchall()
    return jsonify([serialize_metadata_row(row) for row in rows]), 200


@app.route("/api/investment-transactions", methods=["GET"])
@token_required
def list_investment_transactions(current_user_id):
    refresh_realized_results(current_user_id)
    with get_db() as conn:
        rows = fetch_investment_rows(
            conn,
            current_user_id,
            order_by="it.transaction_date",
            direction="DESC",
        )
    return jsonify([serialize_investment(row) for row in rows]), 200


@app.route("/api/investment-realized-results", methods=["GET"])
@token_required
def list_investment_realized_results(current_user_id):
    refresh_realized_results(current_user_id)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                rr.*,
                asset.asset_class,
                asset.ticker,
                asset.name,
                it.transaction_date,
                it.metadata AS transaction_metadata
            FROM investment_realized_results rr
            JOIN assets asset ON asset.id = rr.asset_id
            JOIN investment_transactions it ON it.id = rr.source_transaction_id
            WHERE rr.user_id = ?
            ORDER BY rr.operation_date DESC, rr.created_at DESC
            """,
            (current_user_id,),
        ).fetchall()

    items = []
    for row in rows:
        item = serialize_metadata_row(row)
        item["transaction_metadata"] = parse_metadata_value(item.get("transaction_metadata"))
        items.append(item)
    return jsonify(items), 200


@app.route("/api/investment-proceeds", methods=["GET", "POST"])
@token_required
def investment_proceeds(current_user_id):
    if request.method == "GET":
        try:
            filters = parse_investment_proceeds_filters(request.args)
        except ValidationError as exc:
            return validation_error(str(exc))

        with get_db() as conn:
            rows = fetch_investment_proceeds(conn, current_user_id, filters)
            items = [
                serialize_investment_proceed(row, conn, current_user_id)
                for row in rows
            ]
        return jsonify(items), 200

    payload = parse_json_body()
    if not isinstance(payload, dict):
        return validation_error("Provento deve ser um objeto valido.")

    try:
        with get_db() as conn:
            proceed = normalize_proceed_payload(conn, current_user_id, payload)
            proceed_id = new_id()
            conn.execute(
                """
                INSERT INTO investment_proceeds
                (
                    id, user_id, asset_id, proceeds_type, declared_date,
                    record_date, ex_date, payment_date, amount_per_unit,
                    eligible_quantity, gross_amount, tax_amount, net_amount,
                    source, notes, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proceed_id,
                    current_user_id,
                    proceed["asset_id"],
                    proceed["proceeds_type"],
                    proceed["declared_date"],
                    proceed["record_date"],
                    proceed["ex_date"],
                    proceed["payment_date"],
                    proceed["amount_per_unit"],
                    proceed["eligible_quantity"],
                    proceed["gross_amount"],
                    proceed["tax_amount"],
                    proceed["net_amount"],
                    proceed["source"],
                    proceed["notes"],
                    encode_metadata(proceed["metadata"]),
                ),
            )
            row = fetch_investment_proceed_by_id(conn, current_user_id, proceed_id)
            item = serialize_investment_proceed(row, conn, current_user_id)
    except ValidationError as exc:
        return validation_error(str(exc))
    except sqlite3.IntegrityError:
        return jsonify({"error": "Nao foi possivel registrar o provento."}), 400

    return jsonify(item), 201


@app.route("/api/investment-proceeds/summary", methods=["GET"])
@token_required
def investment_proceeds_summary(current_user_id):
    try:
        filters = parse_investment_proceeds_filters(request.args)
    except ValidationError as exc:
        return validation_error(str(exc))

    with get_db() as conn:
        rows = fetch_investment_proceeds(conn, current_user_id, filters)
        items = [
            serialize_investment_proceed(row, conn, current_user_id)
            for row in rows
        ]
    return jsonify(build_investment_proceeds_summary(items)), 200


@app.route("/api/investment-proceeds/calendar", methods=["GET"])
@token_required
def investment_proceeds_calendar(current_user_id):
    try:
        filters = parse_investment_proceeds_filters(request.args)
    except ValidationError as exc:
        return validation_error(str(exc))

    today = datetime.now().strftime("%Y-%m-%d")
    if not filters.get("date_from"):
        filters["date_from"] = today
    if not filters.get("date_to"):
        filters["date_to"] = (datetime.now() + timedelta(days=180)).strftime("%Y-%m-%d")
    filters["ascending"] = True

    with get_db() as conn:
        rows = fetch_investment_proceeds(conn, current_user_id, filters)
        items = [
            serialize_investment_proceed(row, conn, current_user_id)
            for row in rows
        ]
    return jsonify(items), 200


@app.route("/api/investment-proceeds/<proceed_id>", methods=["PATCH", "DELETE"])
@token_required
def investment_proceed_detail(current_user_id, proceed_id):
    with get_db() as conn:
        existing_row = fetch_investment_proceed_by_id(conn, current_user_id, proceed_id)
        if not existing_row:
            return jsonify({"error": "Provento nao encontrado."}), 404

        if request.method == "DELETE":
            cursor = conn.execute(
                "DELETE FROM investment_proceeds WHERE id = ? AND user_id = ?",
                (proceed_id, current_user_id),
            )
            return jsonify({"deleted": cursor.rowcount}), 200

        payload = parse_json_body()
        if not isinstance(payload, dict):
            return validation_error("Provento deve ser um objeto valido.")

        try:
            existing = serialize_metadata_row(existing_row)
            proceed = normalize_proceed_payload(conn, current_user_id, payload, existing)
            conn.execute(
                """
                UPDATE investment_proceeds
                SET asset_id = ?,
                    proceeds_type = ?,
                    declared_date = ?,
                    record_date = ?,
                    ex_date = ?,
                    payment_date = ?,
                    amount_per_unit = ?,
                    eligible_quantity = ?,
                    gross_amount = ?,
                    tax_amount = ?,
                    net_amount = ?,
                    source = ?,
                    notes = ?,
                    metadata = ?,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ? AND user_id = ?
                """,
                (
                    proceed["asset_id"],
                    proceed["proceeds_type"],
                    proceed["declared_date"],
                    proceed["record_date"],
                    proceed["ex_date"],
                    proceed["payment_date"],
                    proceed["amount_per_unit"],
                    proceed["eligible_quantity"],
                    proceed["gross_amount"],
                    proceed["tax_amount"],
                    proceed["net_amount"],
                    proceed["source"],
                    proceed["notes"],
                    encode_metadata(proceed["metadata"]),
                    proceed_id,
                    current_user_id,
                ),
            )
            row = fetch_investment_proceed_by_id(conn, current_user_id, proceed_id)
            item = serialize_investment_proceed(row, conn, current_user_id)
        except ValidationError as exc:
            return validation_error(str(exc))
        except sqlite3.IntegrityError:
            return jsonify({"error": "Nao foi possivel atualizar o provento."}), 400

    return jsonify(item), 200


@app.route("/api/investment-positions", methods=["GET"])
@token_required
def list_investment_positions(current_user_id):
    refresh_materialized_positions(current_user_id)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                pos.*,
                asset.asset_class,
                asset.ticker,
                asset.name
            FROM investment_positions pos
            JOIN assets asset ON asset.id = pos.asset_id
            WHERE pos.user_id = ?
            ORDER BY asset.asset_class ASC, asset.ticker ASC
            """,
            (current_user_id,),
        ).fetchall()
    return jsonify([serialize_metadata_row(row) for row in rows]), 200


@app.route("/api/investments", methods=["GET", "POST"])
@token_required
def investments(current_user_id):
    if request.method == "GET":
        refresh_realized_results(current_user_id)
        order = request.args.get("order", "created_at")
        order_by = {
            "created_at": "it.created_at",
            "ticker_or_name": "a.ticker",
            "asset_class": "a.asset_class",
        }.get(order, "it.created_at")
        direction = "ASC" if request.args.get("ascending") == "true" else "DESC"

        with get_db() as conn:
            rows = fetch_investment_rows(
                conn,
                current_user_id,
                order_by=order_by,
                direction=direction,
            )
        return jsonify([serialize_investment(row) for row in rows]), 200

    payload = parse_json_body()
    items = payload if isinstance(payload, list) else [payload]
    if not items:
        return validation_error("Informe ao menos um investimento.")

    inserted = []
    affected_asset_ids = set()
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
                metadata_dict = investment_metadata_dict(metadata)
                validate_investment_movement(
                    conn,
                    current_user_id,
                    asset_class,
                    ticker_or_name,
                    quantity,
                )

                item_id = new_id()
                asset_id = get_or_create_asset(conn, current_user_id, asset_class, ticker_or_name)
                affected_asset_ids.add(asset_id)
                transaction_date = investment_transaction_date(metadata_dict)
                conn.execute(
                    """
                    INSERT INTO investment_transactions
                    (
                        id, user_id, asset_id, movement_type, quantity,
                        unit_price, gross_amount, fee_amount, transaction_date, metadata
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item_id,
                        current_user_id,
                        asset_id,
                        investment_movement_type(quantity, metadata_dict),
                        quantity,
                        average_price,
                        investment_gross_amount(quantity, average_price),
                        investment_fee_amount(metadata_dict),
                        transaction_date,
                        encode_metadata(metadata),
                    ),
                )
                record_price_quote(
                    conn,
                    current_user_id,
                    asset_id,
                    current_price,
                    asset_class=asset_class,
                    transaction_id=item_id,
                    quoted_at=quote_timestamp(transaction_date),
                    source="manual",
                )
                inserted.append(item_id)

            for asset_id in affected_asset_ids:
                validate_asset_transaction_backing(conn, current_user_id, asset_id)

            rows = []
            for item_id in inserted:
                row = fetch_investment_rows(conn, current_user_id, investment_id=item_id)[0]
                sync_investment_cash_transaction(
                    conn,
                    current_user_id,
                    serialize_investment(row),
                )
                rows.append(row)
    except ValidationError as exc:
        return validation_error(str(exc))
    except sqlite3.IntegrityError:
        return jsonify({"error": "Nao foi possivel criar o investimento."}), 400

    refresh_realized_results(current_user_id)
    refresh_materialized_positions(current_user_id)
    return jsonify([serialize_investment(row) for row in rows]), 201


@app.route("/api/investments/<investment_id>", methods=["PATCH", "DELETE"])
@token_required
def investment_detail(current_user_id, investment_id):
    if request.method == "DELETE":
        with get_db() as conn:
            existing = conn.execute(
                """
                SELECT id FROM investment_transactions
                WHERE id = ? AND user_id = ?
                """,
                (investment_id, current_user_id),
            ).fetchone()
            if not existing:
                return jsonify({"deleted": False}), 404
            existing_rows = fetch_investment_rows(conn, current_user_id, investment_id=investment_id)
            existing_item = serialize_investment(existing_rows[0]) if existing_rows else None
            if existing_item:
                try:
                    validate_asset_transaction_backing(
                        conn,
                        current_user_id,
                        existing_item["asset_id"],
                        exclude_ids={investment_id},
                    )
                except ValidationError as exc:
                    return validation_error(str(exc), 409)
            delete_investment_cash_transaction(conn, current_user_id, investment_id)
            conn.execute(
                "DELETE FROM investment_transactions WHERE id = ? AND user_id = ?",
                (investment_id, current_user_id),
            )
        refresh_realized_results(current_user_id)
        refresh_materialized_positions(current_user_id)
        return jsonify({"deleted": True}), 200

    payload = parse_json_body()
    allowed = {"quantity", "average_price", "current_price", "metadata"}
    if not any(key in payload for key in allowed):
        return jsonify({"updated": False}), 400

    try:
        parsed_quantity = (
            parse_number(payload, "quantity", "Quantidade")
            if "quantity" in payload else None
        )
        if parsed_quantity == 0:
            raise ValidationError("Quantidade deve ser diferente de zero.")
        parsed_average_price = (
            parse_number(payload, "average_price", "Preco medio", minimum=0)
            if "average_price" in payload else None
        )
        parsed_current_price = (
            parse_optional_number(payload, "current_price", "Preco atual", minimum=0)
            if "current_price" in payload else None
        )
        parsed_metadata = payload.get("metadata") if "metadata" in payload else None
        if "metadata" in payload and parsed_metadata not in (None, "") and not isinstance(parsed_metadata, (dict, str)):
            raise ValidationError("Metadata deve ser um objeto valido.")
    except ValidationError as exc:
        return validation_error(str(exc))

    with get_db() as conn:
        existing_rows = fetch_investment_rows(conn, current_user_id, investment_id=investment_id)
        existing_row = existing_rows[0] if existing_rows else None
        if not existing_row:
            return jsonify({"error": "Investimento nao encontrado."}), 404

        existing = serialize_investment(existing_row)
        asset_class = existing["asset_class"]
        quantity = parsed_quantity if parsed_quantity is not None else safe_float(existing["quantity"])
        unit_price = (
            parsed_average_price
            if parsed_average_price is not None
            else safe_float(existing["average_price"])
        )
        metadata = (
            investment_metadata_dict(parsed_metadata)
            if "metadata" in payload
            else existing.get("metadata") or {}
        )
        transaction_date = investment_transaction_date(metadata, existing.get("created_at"))

        if "quantity" in payload:
            if asset_class != "FIXED_INCOME" and quantity < 0:
                available_quantity = fetch_position_quantity(
                    conn,
                    current_user_id,
                    asset_class,
                    existing["ticker_or_name"],
                    exclude_id=investment_id,
                )
                if abs(quantity) - available_quantity > 0.000001:
                    return validation_error("Venda maior que a quantidade disponivel na carteira.")

        try:
            validate_asset_transaction_backing(
                conn,
                current_user_id,
                existing["asset_id"],
                exclude_ids={investment_id},
                replacements=[{
                    **existing,
                    "quantity": quantity,
                    "average_price": unit_price,
                    "movement_type": investment_movement_type(quantity, metadata),
                    "gross_amount": investment_gross_amount(quantity, unit_price),
                    "fee_amount": investment_fee_amount(metadata),
                    "transaction_date": transaction_date,
                    "metadata": metadata,
                }],
            )
        except ValidationError as exc:
            return validation_error(str(exc), 409)

        conn.execute(
            """
            UPDATE investment_transactions
            SET quantity = ?,
                unit_price = ?,
                movement_type = ?,
                gross_amount = ?,
                fee_amount = ?,
                transaction_date = ?,
                metadata = ?,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = ? AND user_id = ?
            """,
            (
                quantity,
                unit_price,
                investment_movement_type(quantity, metadata),
                investment_gross_amount(quantity, unit_price),
                investment_fee_amount(metadata),
                transaction_date,
                encode_metadata(metadata),
                investment_id,
                current_user_id,
            ),
        )

        if "current_price" in payload:
            record_price_quote(
                conn,
                current_user_id,
                existing["asset_id"],
                parsed_current_price,
                asset_class=asset_class,
                transaction_id=investment_id,
                source="manual",
            )

        row = fetch_investment_rows(conn, current_user_id, investment_id=investment_id)[0]
        sync_investment_cash_transaction(
            conn,
            current_user_id,
            serialize_investment(row),
        )
    if not row:
        return jsonify({"error": "Investimento nao encontrado."}), 404
    refresh_realized_results(current_user_id)
    refresh_materialized_positions(current_user_id)
    return jsonify(serialize_investment(row)), 200


@app.route("/api/investments/by-asset/<asset_id>", methods=["DELETE"])
@token_required
def delete_investments_by_asset(current_user_id, asset_id):
    payload = parse_json_body()
    try:
        asset_class = require_choice(
            {"asset_class": request.args.get("asset_class") or payload.get("asset_class")},
            "asset_class",
            "Classe do ativo",
            ALLOWED_ASSET_CLASSES,
        )
    except ValidationError as exc:
        return validation_error(str(exc))

    with get_db() as conn:
        asset = conn.execute(
            """
            SELECT id, asset_class, ticker
            FROM assets
            WHERE id = ? AND user_id = ?
            """,
            (asset_id, current_user_id),
        ).fetchone()
        if not asset:
            return jsonify({"deleted": 0, "error": "Ativo nao encontrado."}), 404
        if asset["asset_class"] != asset_class:
            return validation_error("Classe do ativo nao confere com o ativo informado.", 409)

        rows = conn.execute(
            """
            SELECT it.id
            FROM investment_transactions it
            WHERE it.user_id = ? AND it.asset_id = ?
            """,
            (current_user_id, asset_id),
        ).fetchall()
        for row in rows:
            delete_investment_cash_transaction(conn, current_user_id, row["id"])
        cursor = conn.execute(
            "DELETE FROM assets WHERE user_id = ? AND id = ? AND asset_class = ?",
            (current_user_id, asset_id, asset_class),
        )
    if rows:
        refresh_realized_results(current_user_id)
        refresh_materialized_positions(current_user_id)
    return jsonify({"deleted": cursor.rowcount}), 200


@app.route("/api/investments/by-ticker/<path:ticker>", methods=["DELETE"])
@token_required
def delete_investments_by_ticker(current_user_id, ticker):
    return validation_error(
        "Operacao por ticker desativada por seguranca. Use asset_id e asset_class para excluir uma posicao.",
        410,
    )


@app.route("/api/investments/price-by-asset/<asset_id>", methods=["PATCH"])
@token_required
def update_price_by_asset(current_user_id, asset_id):
    payload = parse_json_body()
    try:
        asset_class = require_choice(payload, "asset_class", "Classe do ativo", ALLOWED_ASSET_CLASSES)
        current_price = parse_number(payload, "current_price", "Preco atual", minimum=0)
    except ValidationError as exc:
        return validation_error(str(exc))

    with get_db() as conn:
        asset = conn.execute(
            """
            SELECT id, asset_class
            FROM assets
            WHERE id = ? AND user_id = ?
            """,
            (asset_id, current_user_id),
        ).fetchone()
        if not asset:
            return jsonify({"updated": 0, "error": "Ativo nao encontrado."}), 404
        if asset["asset_class"] != asset_class:
            return validation_error("Classe do ativo nao confere com o ativo informado.", 409)

        record_price_quote(
            conn,
            current_user_id,
            asset_id,
            current_price,
            asset_class=asset_class,
            source="manual",
        )
    refresh_materialized_positions(current_user_id)
    return jsonify({"updated": 1}), 200


@app.route("/api/investments/price-by-ticker", methods=["PATCH"])
@token_required
def update_price_by_ticker(current_user_id):
    return validation_error(
        "Atualizacao por ticker desativada por seguranca. Use asset_id e asset_class para atualizar cotacao.",
        410,
    )


def fetch_investments(current_user_id, investment_id=None):
    with get_db() as conn:
        rows = fetch_investment_rows(
            conn,
            current_user_id,
            investment_id=investment_id,
            order_by="it.created_at",
            direction="ASC",
        )
    return [serialize_investment(row) for row in rows]


def fetch_position_quantity(conn, current_user_id, asset_class, ticker, exclude_id=None):
    query = """
        SELECT COALESCE(SUM(quantity), 0) AS quantity
        FROM investment_transactions it
        JOIN assets a ON a.id = it.asset_id
        WHERE it.user_id = ?
          AND a.asset_class = ?
          AND a.ticker = ?
    """
    params = [current_user_id, asset_class, ticker_key(ticker)]
    if exclude_id:
        query += " AND it.id <> ?"
        params.append(exclude_id)
    row = conn.execute(query, params).fetchone()
    return safe_float(row["quantity"] if row else 0)


def validate_investment_movement(conn, current_user_id, asset_class, ticker_or_name, quantity):
    if quantity >= 0 or asset_class == "FIXED_INCOME":
        return

    available_quantity = fetch_position_quantity(
        conn,
        current_user_id,
        asset_class,
        ticker_or_name,
    )
    if abs(quantity) - available_quantity > 0.000001:
        raise ValidationError("Venda maior que a quantidade disponivel na carteira.")


def movement_sort_key(investment):
    return (
        investment_operation_date(investment),
        str(investment.get("created_at") or ""),
        str(investment.get("id") or ""),
    )


def fetch_asset_transactions_for_backing(conn, current_user_id, asset_id):
    rows = conn.execute(
        """
        SELECT
            it.id,
            it.user_id,
            it.asset_id,
            asset.asset_class,
            asset.ticker AS ticker_or_name,
            it.quantity,
            it.unit_price AS average_price,
            it.gross_amount,
            it.fee_amount,
            it.movement_type,
            it.transaction_date,
            it.metadata,
            it.created_at,
            it.updated_at
        FROM investment_transactions it
        JOIN assets asset ON asset.id = it.asset_id
        WHERE it.user_id = ?
          AND it.asset_id = ?
        """,
        (current_user_id, asset_id),
    ).fetchall()
    return [serialize_investment(row) for row in rows]


def validate_asset_transaction_backing(
    conn,
    current_user_id,
    asset_id,
    *,
    exclude_ids=None,
    replacements=None,
):
    excluded = {str(item_id) for item_id in (exclude_ids or set())}
    transactions = [
        item
        for item in fetch_asset_transactions_for_backing(conn, current_user_id, asset_id)
        if str(item.get("id")) not in excluded
    ]
    transactions.extend(replacements or [])
    transactions = sorted(transactions, key=movement_sort_key)
    remaining_ids = {str(item.get("id")) for item in transactions if item.get("id")}

    for item in transactions:
        metadata = item.get("metadata") or {}
        related_id = metadata.get("related_id")
        if metadata.get("is_redemption") and related_id and str(related_id) not in remaining_ids:
            raise ValidationError(
                "Nao e possivel alterar ou excluir essa compra: ela possui resgate vinculado."
            )

    balance_by_asset = {}
    for item in transactions:
        asset_class = item.get("asset_class")
        if asset_class == "FIXED_INCOME":
            continue

        quantity = safe_float(item.get("quantity"))
        if quantity == 0:
            continue

        key = item.get("asset_id") or asset_id
        next_balance = balance_by_asset.get(key, 0) + quantity
        if next_balance < -0.000001:
            ticker = ticker_key(item.get("ticker_or_name"))
            raise ValidationError(
                f"Nao e possivel alterar ou excluir essa movimentacao: {ticker} ficaria com venda sem lastro de compra anterior."
            )
        balance_by_asset[key] = next_balance


def days_between_dates(start_date, end_date):
    start = parse_iso_date(start_date)
    end = parse_iso_date(end_date)
    if not start or not end:
        return None
    return max((end - start).days, 0)


def realized_result_record(investment, *, quantity, gross_proceeds, fees, cost_basis, tax_amount, tax_rate, metadata):
    quantity = abs(safe_float(quantity))
    gross_proceeds = max(safe_float(gross_proceeds), 0)
    fees = max(safe_float(fees), 0)
    net_proceeds = max(gross_proceeds - fees, 0)
    cost_basis = max(safe_float(cost_basis), 0)
    realized_profit = net_proceeds - cost_basis
    average_cost = cost_basis / quantity if quantity > 0 else 0
    net_unit_price = net_proceeds / quantity if quantity > 0 else 0
    profitability = (realized_profit / cost_basis * 100) if cost_basis > 0 else 0
    tax_amount = max(safe_float(tax_amount), 0)

    return {
        "id": f"realized:{investment['id']}",
        "user_id": investment["user_id"],
        "asset_id": investment["asset_id"],
        "source_transaction_id": investment["id"],
        "movement_type": investment.get("movement_type") or investment_movement_type(
            investment.get("quantity"),
            investment.get("metadata") or {},
        ),
        "quantity": round(quantity, 6),
        "average_cost": rounded_money(average_cost),
        "gross_proceeds": rounded_money(gross_proceeds),
        "fee_amount": rounded_money(fees),
        "net_proceeds": rounded_money(net_proceeds),
        "net_unit_price": rounded_money(net_unit_price),
        "cost_basis": rounded_money(cost_basis),
        "realized_profit": rounded_money(realized_profit),
        "profitability_percent": round(profitability, 2),
        "tax_rate": round(safe_float(tax_rate), 6),
        "tax_amount": rounded_money(tax_amount),
        "net_profit_after_tax": rounded_money(realized_profit - tax_amount),
        "operation_date": investment_operation_date(investment),
        "metadata": metadata,
    }


def allocation_tax_amount(asset_class, movement_metadata, allocation, profit):
    rate = realized_tax_rate(
        asset_class,
        movement_metadata,
        allocation.get("holding_days"),
    )
    return max(profit, 0) * rate, rate


def build_variable_realized_result(investment, lots):
    metadata = investment.get("metadata") or {}
    asset_class = investment.get("asset_class")
    operation_date = investment_operation_date(investment)
    sold_quantity = abs(safe_float(investment.get("quantity")))
    fees = max(safe_float(investment.get("fee_amount"), investment_fee_amount(metadata)), 0)
    gross_proceeds = investment_gross_proceeds(investment, metadata)
    gross_unit_price = gross_proceeds / sold_quantity if sold_quantity > 0 else 0

    remaining = sold_quantity
    allocations = []
    cost_basis = 0
    index = 0

    while remaining > 0.000001 and index < len(lots):
        lot = lots[index]
        lot_quantity = safe_float(lot.get("remaining_quantity"))
        if lot_quantity <= 0.000001:
            lots.pop(index)
            continue

        consumed_quantity = min(remaining, lot_quantity)
        allocation_cost = consumed_quantity * safe_float(lot.get("unit_cost"))
        holding_days = days_between_dates(lot.get("purchase_date"), operation_date)
        allocations.append({
            "buy_transaction_id": lot.get("transaction_id"),
            "purchase_date": lot.get("purchase_date"),
            "quantity": round(consumed_quantity, 6),
            "unit_cost": rounded_money(lot.get("unit_cost")),
            "cost_basis": rounded_money(allocation_cost),
            "holding_days": holding_days,
        })
        cost_basis += allocation_cost
        lot["remaining_quantity"] = lot_quantity - consumed_quantity
        remaining -= consumed_quantity

        if lot["remaining_quantity"] <= 0.000001:
            lots.pop(index)
        else:
            index += 1

    if remaining > 0.000001:
        fallback_unit_cost = safe_float(investment.get("average_price"))
        fallback_cost = remaining * fallback_unit_cost
        allocations.append({
            "buy_transaction_id": None,
            "purchase_date": None,
            "quantity": round(remaining, 6),
            "unit_cost": rounded_money(fallback_unit_cost),
            "cost_basis": rounded_money(fallback_cost),
            "holding_days": None,
            "unmatched": True,
        })
        cost_basis += fallback_cost

    tax_amount = 0
    taxable_profit = 0
    for allocation in allocations:
        allocation_quantity = safe_float(allocation.get("quantity"))
        fee_share = fees * (allocation_quantity / sold_quantity) if sold_quantity > 0 else 0
        allocation_gross = allocation_quantity * gross_unit_price
        allocation_net = max(allocation_gross - fee_share, 0)
        allocation_profit = allocation_net - safe_float(allocation.get("cost_basis"))
        allocation_tax, allocation_rate = allocation_tax_amount(
            asset_class,
            metadata,
            allocation,
            allocation_profit,
        )
        tax_amount += allocation_tax
        taxable_profit += max(allocation_profit, 0)
        allocation["gross_proceeds"] = rounded_money(allocation_gross)
        allocation["fee_amount"] = rounded_money(fee_share)
        allocation["net_proceeds"] = rounded_money(allocation_net)
        allocation["realized_profit"] = rounded_money(allocation_profit)
        allocation["tax_rate"] = round(allocation_rate, 6)
        allocation["tax_amount"] = rounded_money(allocation_tax)

    effective_tax_rate = tax_amount / taxable_profit if taxable_profit > 0 else realized_tax_rate(asset_class, metadata)
    return realized_result_record(
        investment,
        quantity=sold_quantity,
        gross_proceeds=gross_proceeds,
        fees=fees,
        cost_basis=cost_basis,
        tax_amount=tax_amount,
        tax_rate=effective_tax_rate,
        metadata={
            "cost_method": "FIFO",
            "tax_method": "estimativa_simples",
            "tax_note": "Estimativa operacional. Valide regras fiscais e isencoes antes da declaracao oficial.",
            "gross_unit_price": rounded_money(gross_unit_price),
            "unmatched_quantity": round(max(remaining, 0), 6),
            "allocations": allocations,
        },
    )


def build_fixed_income_realized_result(investment, investments_by_id):
    metadata = investment.get("metadata") or {}
    operation_date = investment_operation_date(investment)
    quantity = abs(safe_float(investment.get("quantity"), 1)) or 1
    fees = max(safe_float(investment.get("fee_amount"), investment_fee_amount(metadata)), 0)
    gross_proceeds = investment_gross_proceeds(investment, metadata)
    cost_basis = abs(safe_float(investment.get("quantity")) * safe_float(investment.get("average_price")))
    related_id = metadata.get("related_id")
    related_purchase = investments_by_id.get(str(related_id)) if related_id else None
    purchase_metadata = (related_purchase or {}).get("metadata") or {}
    purchase_date = investment_operation_date(related_purchase) if related_purchase else None
    holding_days = days_between_dates(purchase_date, operation_date)
    tax_metadata = {**purchase_metadata, **metadata}
    profit = max(gross_proceeds - fees, 0) - cost_basis
    tax_rate = realized_tax_rate("FIXED_INCOME", tax_metadata, holding_days)
    tax_amount = max(profit, 0) * tax_rate

    allocation = {
        "buy_transaction_id": related_id,
        "purchase_date": purchase_date,
        "quantity": round(quantity, 6),
        "unit_cost": rounded_money(cost_basis / quantity if quantity > 0 else cost_basis),
        "cost_basis": rounded_money(cost_basis),
        "holding_days": holding_days,
        "gross_proceeds": rounded_money(gross_proceeds),
        "fee_amount": rounded_money(fees),
        "net_proceeds": rounded_money(max(gross_proceeds - fees, 0)),
        "realized_profit": rounded_money(profit),
        "tax_rate": round(tax_rate, 6),
        "tax_amount": rounded_money(tax_amount),
    }

    return realized_result_record(
        investment,
        quantity=quantity,
        gross_proceeds=gross_proceeds,
        fees=fees,
        cost_basis=cost_basis,
        tax_amount=tax_amount,
        tax_rate=tax_rate,
        metadata={
            "cost_method": "LOT_REDEMPTION",
            "tax_method": "estimativa_simples",
            "tax_note": "Estimativa operacional. Valide regras fiscais e isencoes antes da declaracao oficial.",
            "gross_unit_price": rounded_money(gross_proceeds / quantity if quantity > 0 else gross_proceeds),
            "allocations": [allocation],
        },
    )


def build_realized_results(current_user_id):
    investments = sorted(fetch_investments(current_user_id), key=movement_sort_key)
    investments_by_id = {str(item.get("id")): item for item in investments}
    lots_by_asset = {}
    results = []

    for investment in investments:
        asset_id = investment.get("asset_id")
        if not asset_id:
            continue

        metadata = investment.get("metadata") or {}
        movement_type = investment.get("movement_type") or investment_movement_type(
            investment.get("quantity"),
            metadata,
        )
        quantity = safe_float(investment.get("quantity"))
        asset_lots = lots_by_asset.setdefault(asset_id, [])

        if movement_type == "BUY" and quantity > 0:
            asset_lots.append({
                "transaction_id": investment.get("id"),
                "purchase_date": investment_operation_date(investment),
                "remaining_quantity": quantity,
                "unit_cost": safe_float(investment.get("average_price")),
                "metadata": metadata,
            })
            continue

        if movement_type == "SELL" and quantity < 0:
            results.append(build_variable_realized_result(investment, asset_lots))
            continue

        if movement_type == "REDEMPTION":
            results.append(build_fixed_income_realized_result(investment, investments_by_id))

    return results


def replace_realized_results(current_user_id, results):
    with get_db() as conn:
        conn.execute("DELETE FROM investment_realized_results WHERE user_id = ?", (current_user_id,))
        for item in results:
            conn.execute(
                """
                INSERT INTO investment_realized_results
                (
                    id, user_id, asset_id, source_transaction_id, movement_type,
                    quantity, average_cost, gross_proceeds, fee_amount,
                    net_proceeds, net_unit_price, cost_basis, realized_profit,
                    profitability_percent, tax_rate, tax_amount, net_profit_after_tax,
                    operation_date, metadata, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                """,
                (
                    item["id"],
                    item["user_id"],
                    item["asset_id"],
                    item["source_transaction_id"],
                    item["movement_type"],
                    item["quantity"],
                    item["average_cost"],
                    item["gross_proceeds"],
                    item["fee_amount"],
                    item["net_proceeds"],
                    item["net_unit_price"],
                    item["cost_basis"],
                    item["realized_profit"],
                    item["profitability_percent"],
                    item["tax_rate"],
                    item["tax_amount"],
                    item["net_profit_after_tax"],
                    item["operation_date"],
                    encode_metadata(item.get("metadata")),
                ),
            )


def refresh_realized_results(current_user_id):
    results = build_realized_results(current_user_id)
    replace_realized_results(current_user_id, results)
    return results


def realized_results_summary(current_user_id):
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS operation_count,
                COALESCE(SUM(gross_proceeds), 0) AS gross_proceeds,
                COALESCE(SUM(fee_amount), 0) AS fee_amount,
                COALESCE(SUM(net_proceeds), 0) AS net_proceeds,
                COALESCE(SUM(cost_basis), 0) AS cost_basis,
                COALESCE(SUM(realized_profit), 0) AS realized_profit,
                COALESCE(SUM(tax_amount), 0) AS tax_amount,
                COALESCE(SUM(net_profit_after_tax), 0) AS net_profit_after_tax
            FROM investment_realized_results
            WHERE user_id = ?
            """,
            (current_user_id,),
        ).fetchone()

    summary = row_to_dict(row) or {}
    return {
        "operation_count": int(summary.get("operation_count") or 0),
        "gross_proceeds": rounded_money(summary.get("gross_proceeds")),
        "fee_amount": rounded_money(summary.get("fee_amount")),
        "net_proceeds": rounded_money(summary.get("net_proceeds")),
        "cost_basis": rounded_money(summary.get("cost_basis")),
        "realized_profit": rounded_money(summary.get("realized_profit")),
        "tax_amount": rounded_money(summary.get("tax_amount")),
        "net_profit_after_tax": rounded_money(summary.get("net_profit_after_tax")),
    }


def ticker_key(ticker_symbol):
    return str(ticker_symbol or "").strip().upper()


def should_refresh_market_prices():
    value = str(request.args.get("refresh_prices", "false")).strip().lower()
    return value not in {"0", "false", "no", "off"}


def read_price_cache(tickers):
    now = time.time()
    fresh_prices = {}
    fallback_prices = {}
    stale_tickers = []

    with _price_cache_lock:
        for ticker in tickers:
            entry = _price_cache.get(ticker)
            if not entry:
                stale_tickers.append(ticker)
                continue

            price = entry.get("price")
            updated_at = entry.get("updated_at", 0)
            if price is None:
                stale_tickers.append(ticker)
                continue

            fallback_prices[ticker] = price
            if now - updated_at <= PRICE_CACHE_TTL_SECONDS:
                fresh_prices[ticker] = price
            else:
                stale_tickers.append(ticker)

    return fresh_prices, fallback_prices, stale_tickers


def update_price_cache(price_by_ticker):
    if not price_by_ticker:
        return

    now = time.time()
    with _price_cache_lock:
        for ticker, price in price_by_ticker.items():
            try:
                numeric_price = round(float(price), 2)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(numeric_price) or numeric_price < 0:
                continue

            _price_cache[ticker] = {
                "price": numeric_price,
                "updated_at": now,
            }


def cache_market_prices_from_future(future):
    try:
        update_price_cache(future.result())
    except Exception as exc:
        print(f"Erro ao finalizar cache de cotacoes: {exc}")


def extract_close_values(data, yf_symbol):
    if data is None or getattr(data, "empty", True):
        return None

    columns = getattr(data, "columns", None)
    if columns is None:
        return None

    close_values = None
    try:
        if getattr(columns, "nlevels", 1) > 1:
            if (yf_symbol, "Close") in columns:
                close_values = data[(yf_symbol, "Close")]
            elif ("Close", yf_symbol) in columns:
                close_values = data[("Close", yf_symbol)]
            elif yf_symbol in columns.get_level_values(0):
                symbol_frame = data[yf_symbol]
                if "Close" in symbol_frame:
                    close_values = symbol_frame["Close"]
            elif "Close" in columns.get_level_values(0):
                close_frame = data["Close"]
                if yf_symbol in getattr(close_frame, "columns", []):
                    close_values = close_frame[yf_symbol]
        elif "Close" in columns:
            close_values = data["Close"]
    except Exception:
        return None

    if close_values is None:
        return None
    if hasattr(close_values, "columns"):
        if getattr(close_values, "empty", True):
            return None
        close_values = close_values.iloc[:, 0]

    if not hasattr(close_values, "dropna"):
        return None

    close_values = close_values.dropna()
    if close_values.empty:
        return None
    return close_values


def extract_latest_close(data, yf_symbol):
    close_values = extract_close_values(data, yf_symbol)
    if close_values is None:
        return None

    try:
        price = float(close_values.iloc[-1])
    except (TypeError, ValueError):
        return None

    if not math.isfinite(price) or price < 0:
        return None
    return price


def download_close_prices(yf_symbols, *, period, interval):
    if yf is None or not yf_symbols:
        return {}

    try:
        data = yf.download(
            tickers=" ".join(yf_symbols),
            period=period,
            interval=interval,
            group_by="ticker",
            threads=True,
            progress=False,
            auto_adjust=False,
            timeout=PRICE_DOWNLOAD_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        print(f"Erro ao consultar yfinance ({period}/{interval}): {exc}")
        return {}

    prices = {}
    for yf_symbol in yf_symbols:
        price = extract_latest_close(data, yf_symbol)
        if price is not None:
            prices[yf_symbol] = price
    return prices


def download_market_prices(tickers):
    if yf is None:
        return {}

    symbols_by_ticker = {ticker: yahoo_symbol(ticker) for ticker in tickers}
    yf_symbols = sorted(set(symbols_by_ticker.values()))

    symbol_prices = download_close_prices(yf_symbols, period="1d", interval="1m")
    missing_symbols = [symbol for symbol in yf_symbols if symbol not in symbol_prices]
    if missing_symbols:
        symbol_prices.update(download_close_prices(missing_symbols, period="5d", interval="1d"))

    prices = {}
    for ticker, yf_symbol in symbols_by_ticker.items():
        price = symbol_prices.get(yf_symbol)
        if price is not None:
            prices[ticker] = round(price, 2)
    return prices


def download_monthly_history(tickers, start_date):
    historical_prices = {ticker: {} for ticker in tickers}
    if yf is None or not tickers:
        return historical_prices

    symbols_by_ticker = {ticker: yahoo_symbol(ticker) for ticker in tickers}
    yf_symbols = sorted(set(symbols_by_ticker.values()))

    try:
        data = yf.download(
            tickers=" ".join(yf_symbols),
            start=start_date,
            interval="1mo",
            group_by="ticker",
            threads=True,
            progress=False,
            auto_adjust=False,
            timeout=PRICE_DOWNLOAD_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        print(f"Erro ao consultar historico no yfinance: {exc}")
        return historical_prices

    for ticker, yf_symbol in symbols_by_ticker.items():
        close_values = extract_close_values(data, yf_symbol)
        if close_values is None:
            continue

        for date, price in close_values.items():
            try:
                numeric_price = round(float(price), 2)
            except (TypeError, ValueError):
                continue
            if math.isfinite(numeric_price):
                historical_prices[ticker][date.strftime("%Y-%m")] = numeric_price

    return historical_prices


def get_monthly_history(tickers, start_date):
    normalized_tickers = tuple(sorted({ticker_key(ticker) for ticker in tickers if ticker_key(ticker)}))
    if not normalized_tickers:
        return {}

    cache_key = (normalized_tickers, start_date)
    now = time.time()
    with _price_cache_lock:
        cached = _history_cache.get(cache_key)
        if cached and now - cached.get("updated_at", 0) <= HISTORY_CACHE_TTL_SECONDS:
            return {
                ticker: dict(prices)
                for ticker, prices in cached.get("prices", {}).items()
            }

    prices = download_monthly_history(list(normalized_tickers), start_date)
    with _price_cache_lock:
        _history_cache[cache_key] = {
            "prices": {
                ticker: dict(monthly_prices)
                for ticker, monthly_prices in prices.items()
            },
            "updated_at": now,
        }
    return prices


def get_market_prices(tickers, *, force=False):
    normalized_tickers = sorted({ticker_key(ticker) for ticker in tickers if ticker_key(ticker)})
    if not normalized_tickers:
        return {}
    if yf is None:
        print("yfinance nao esta instalado; pulando atualizacao de cotacoes.")
        return {}

    fresh_prices, fallback_prices, stale_tickers = read_price_cache(normalized_tickers)
    prices = {} if force else dict(fresh_prices)
    tickers_to_fetch = normalized_tickers if force else stale_tickers
    if not tickers_to_fetch:
        return prices

    future = _price_fetch_executor.submit(download_market_prices, tickers_to_fetch)
    try:
        fetched_prices = future.result(timeout=PRICE_FETCH_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        future.add_done_callback(cache_market_prices_from_future)
        print(
            "Tempo limite ao consultar yfinance; usando cotacoes em cache "
            "ou valores ja gravados."
        )
        for ticker in tickers_to_fetch:
            if ticker in fallback_prices:
                prices[ticker] = fallback_prices[ticker]
        return prices
    except Exception as exc:
        print(f"Erro ao consultar cotacoes no yfinance: {exc}")
        for ticker in tickers_to_fetch:
            if ticker in fallback_prices:
                prices[ticker] = fallback_prices[ticker]
        return prices

    update_price_cache(fetched_prices)
    prices.update(fetched_prices)
    for ticker in tickers_to_fetch:
        if ticker not in prices and ticker in fallback_prices:
            prices[ticker] = fallback_prices[ticker]
    return prices


def get_market_prices_with_status(tickers, *, force=False):
    normalized_tickers = sorted({ticker_key(ticker) for ticker in tickers if ticker_key(ticker)})
    result = {
        "prices": {},
        "source_by_ticker": {},
        "failed_tickers": [],
        "errors": {},
    }
    if not normalized_tickers:
        return result
    if yf is None:
        print("yfinance nao esta instalado; pulando atualizacao de cotacoes.")
        result["failed_tickers"] = normalized_tickers
        result["errors"] = {ticker: "yfinance indisponivel" for ticker in normalized_tickers}
        return result

    fresh_prices, fallback_prices, stale_tickers = read_price_cache(normalized_tickers)
    if not force:
        for ticker, price in fresh_prices.items():
            result["prices"][ticker] = price
            result["source_by_ticker"][ticker] = "cache"

    tickers_to_fetch = normalized_tickers if force else stale_tickers
    if not tickers_to_fetch:
        return result

    fetch_error = None
    future = _price_fetch_executor.submit(download_market_prices, tickers_to_fetch)
    try:
        fetched_prices = future.result(timeout=PRICE_FETCH_TIMEOUT_SECONDS)
    except FutureTimeoutError:
        future.add_done_callback(cache_market_prices_from_future)
        fetch_error = "Tempo limite ao consultar yfinance"
        print("Tempo limite ao consultar yfinance; usando cache quando disponivel.")
        fetched_prices = {}
    except Exception as exc:
        fetch_error = f"Erro ao consultar yfinance: {exc}"
        print(fetch_error)
        fetched_prices = {}

    update_price_cache(fetched_prices)
    for ticker, price in fetched_prices.items():
        result["prices"][ticker] = price
        result["source_by_ticker"][ticker] = "market"

    for ticker in tickers_to_fetch:
        if ticker in result["prices"]:
            continue
        if ticker in fallback_prices:
            result["prices"][ticker] = fallback_prices[ticker]
            result["source_by_ticker"][ticker] = "cache_stale"
        else:
            result["failed_tickers"].append(ticker)
            result["errors"][ticker] = fetch_error or "Cotacao nao encontrada"

    return result


def unique_market_asset_targets(investments):
    targets = {}
    for inv in investments:
        asset_id = inv.get("asset_id")
        asset_class = inv.get("asset_class")
        ticker = ticker_key(inv.get("ticker_or_name"))
        if not asset_id or asset_class not in QUOTED_ASSET_CLASSES or not ticker:
            continue
        targets[asset_id] = {
            "asset_id": asset_id,
            "asset_class": asset_class,
            "ticker": ticker,
            "name": inv.get("ticker_or_name") or ticker,
        }
    return list(targets.values())


def update_current_prices_for_assets(current_user_id, target_assets, market_result):
    updated_assets = []
    if not target_assets:
        return updated_assets

    prices = market_result.get("prices", {})
    sources = market_result.get("source_by_ticker", {})

    with get_db() as conn:
        for asset in target_assets:
            ticker = asset["ticker"]
            source = sources.get(ticker)
            if source != "market":
                continue
            price = safe_float(prices.get(ticker), None)
            if price is None or not math.isfinite(price) or price < 0:
                continue

            record_price_quote(
                conn,
                current_user_id,
                asset["asset_id"],
                round(price, 2),
                asset_class=asset["asset_class"],
                source="market",
                metadata={"ticker": ticker, "provider": "yfinance"},
            )
            updated_assets.append({
                **asset,
                "price": round(price, 2),
                "source": "market",
                "status": "updated",
            })

    return updated_assets


def refresh_market_prices(current_user_id, investment_id=None, *, force=False, asset_id=None, asset_class=None):
    investments_to_update = fetch_investments(current_user_id, investment_id)
    if asset_id:
        investments_to_update = [
            inv for inv in investments_to_update
            if str(inv.get("asset_id")) == str(asset_id)
        ]
    if asset_class:
        investments_to_update = [
            inv for inv in investments_to_update
            if inv.get("asset_class") == asset_class
        ]

    target_assets = unique_market_asset_targets(investments_to_update)
    tickers = sorted({asset["ticker"] for asset in target_assets})

    market_result = get_market_prices_with_status(tickers, force=force)
    updated_assets = update_current_prices_for_assets(current_user_id, target_assets, market_result)
    failed_tickers = set(market_result.get("failed_tickers", []))
    source_by_ticker = market_result.get("source_by_ticker", {})
    cached_assets = [
        {
            **asset,
            "price": safe_float(market_result.get("prices", {}).get(asset["ticker"]), None),
            "source": source_by_ticker.get(asset["ticker"]),
            "status": "cache",
        }
        for asset in target_assets
        if source_by_ticker.get(asset["ticker"]) in {"cache", "cache_stale"}
    ]
    failed_assets = [
        {
            **asset,
            "status": "failed",
            "error": market_result.get("errors", {}).get(asset["ticker"], "Cotacao nao encontrada"),
        }
        for asset in target_assets
        if asset["ticker"] in failed_tickers
    ]
    return {
        "updated_count": len(updated_assets),
        "updated_assets": updated_assets,
        "cached_assets": cached_assets,
        "failed_assets": failed_assets,
        "target_assets": target_assets,
        "requested_tickers": len(tickers),
        "priced_tickers": len(market_result.get("prices", {})),
        "failed_tickers": sorted(failed_tickers),
    }


def refresh_fixed_income_prices(current_user_id, investments_to_update):
    updated_assets = []
    failed_assets = []

    for inv in investments_to_update:
        if inv["asset_class"] != "FIXED_INCOME":
            continue

        meta = inv.get("metadata") or {}
        if not meta or "cdi_percentage" not in meta:
            failed_assets.append({
                "asset_id": inv.get("asset_id"),
                "investment_id": inv.get("id"),
                "asset_class": inv.get("asset_class"),
                "ticker": ticker_key(inv.get("ticker_or_name")),
                "name": inv.get("ticker_or_name"),
                "status": "failed",
                "error": "Percentual do CDI nao informado",
            })
            continue

        cdi_pct = safe_float(meta["cdi_percentage"])
        date_str = meta.get("purchase_date")
        try:
            if date_str:
                dt_obj = datetime.strptime(date_str, "%Y-%m-%d")
            else:
                dt_obj = datetime.strptime(inv["created_at"][:10], "%Y-%m-%d")
        except ValueError:
            print(f"Data invalida para {inv['ticker_or_name']}; pulando CDI.")
            failed_assets.append({
                "asset_id": inv.get("asset_id"),
                "investment_id": inv.get("id"),
                "asset_class": inv.get("asset_class"),
                "ticker": ticker_key(inv.get("ticker_or_name")),
                "name": inv.get("ticker_or_name"),
                "status": "failed",
                "error": "Data invalida para calculo de CDI",
            })
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
                        record_price_quote(
                            conn,
                            current_user_id,
                            inv["asset_id"],
                            round(new_price, 2),
                            asset_class=inv["asset_class"],
                            transaction_id=inv["id"],
                            source="cdi",
                            metadata={"provider": "bcb", "cdi_percentage": cdi_pct},
                        )
                    updated_assets.append({
                        "asset_id": inv.get("asset_id"),
                        "investment_id": inv.get("id"),
                        "asset_class": inv.get("asset_class"),
                        "ticker": ticker_key(inv.get("ticker_or_name")),
                        "name": inv.get("ticker_or_name"),
                        "price": round(new_price, 2),
                        "source": "cdi",
                        "status": "updated",
                    })
        except Exception as exc:
            print(f"Erro ao buscar CDI para {inv['ticker_or_name']}: {exc}")
            failed_assets.append({
                "asset_id": inv.get("asset_id"),
                "investment_id": inv.get("id"),
                "asset_class": inv.get("asset_class"),
                "ticker": ticker_key(inv.get("ticker_or_name")),
                "name": inv.get("ticker_or_name"),
                "status": "failed",
                "error": str(exc) or "Erro ao buscar CDI",
            })

    return {
        "updated_count": len(updated_assets),
        "updated_assets": updated_assets,
        "failed_assets": failed_assets,
    }


def build_portfolio_snapshot(current_user_id):
    all_investments = fetch_investments(current_user_id)

    grouped_assets = {}
    for asset in all_investments:
        metadata = asset.get("metadata") or {}
        asset_id = asset.get("asset_id")
        ticker = asset["ticker_or_name"]
        normalized_ticker = ticker_key(ticker)
        asset_class = asset["asset_class"]
        qty = safe_float(asset.get("quantity"))
        avg_price_buy = safe_float(asset.get("average_price"))
        curr_price = safe_float(asset.get("current_price"), avg_price_buy)
        quote_info = quote_info_from_investment(asset)
        invested_value = qty * avg_price_buy

        if movement_affects_fixed_income_position(asset):
            group_key = str(metadata.get("related_id"))
            source_transaction_id = str(metadata.get("related_id"))
        elif asset_class == "FIXED_INCOME" and metadata.get("is_redemption"):
            continue
        else:
            group_key = str(asset["id"]) if asset_class == "FIXED_INCOME" else str(asset_id or f"{asset_class}:{normalized_ticker}")
            source_transaction_id = str(asset["id"]) if asset_class == "FIXED_INCOME" else None

        if group_key not in grouped_assets:
            grouped_assets[group_key] = {
                "id": group_key,
                "asset_id": asset_id,
                "source_transaction_id": source_transaction_id,
                "original_ticker": normalized_ticker or ticker,
                "class": asset_class,
                "total_quantity": 0,
                "total_invested": 0,
                "original_invested": 0,
                "current_price": curr_price,
                "quote": quote_info,
                "metadata": metadata,
            }

        grouped_assets[group_key]["total_invested"] += invested_value

        if not movement_affects_fixed_income_position(asset):
            grouped_assets[group_key]["total_quantity"] += qty
            if asset_class == "FIXED_INCOME" and qty > 0:
                grouped_assets[group_key]["original_invested"] += invested_value
                grouped_assets[group_key]["metadata"] = metadata
                grouped_assets[group_key]["original_ticker"] = normalized_ticker or ticker
                grouped_assets[group_key]["asset_id"] = asset_id
                grouped_assets[group_key]["source_transaction_id"] = str(asset["id"])
                grouped_assets[group_key]["quote"] = quote_info
            if asset.get("current_price") is not None:
                grouped_assets[group_key]["current_price"] = curr_price
                grouped_assets[group_key]["quote"] = quote_info

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

        if data["class"] == "FIXED_INCOME":
            current_value = current_price_from_position(data, data["total_invested"])
        else:
            current_value = adjusted_quantity * data["current_price"]

        net_value = fixed_income_net_value(
            data["class"],
            data.get("metadata") or {},
            data["total_invested"],
            current_value,
            datetime.now(),
        )
        taxes = max(current_value - net_value, 0)
        is_tax_free = bool((data.get("metadata") or {}).get("is_tax_free", False))
        profitability = (
            ((net_value - data["total_invested"]) / data["total_invested"]) * 100
            if data["total_invested"] > 0 else 0
        )

        total_invested_all += data["total_invested"]
        current_total_value += current_value
        current_net_value_all += net_value
        distribution[data["class"]] = distribution.get(data["class"], 0) + net_value

        display_price = current_value if data["class"] == "FIXED_INCOME" else data["current_price"]

        processed_assets.append({
            "id": data["id"],
            "asset_id": data.get("asset_id"),
            "source_transaction_id": data.get("source_transaction_id"),
            "ticker": data["original_ticker"],
            "name": data["original_ticker"],
            "class": data["class"],
            "quantity": round(data["total_quantity"], 4),
            "average_price": rounded_money(avg_price_calculated),
            "current_price": rounded_money(display_price),
            "current_value": rounded_money(current_value),
            "net_value": rounded_money(net_value),
            "taxes": rounded_money(taxes),
            "is_tax_free": is_tax_free,
            "profitability_percent": round(profitability, 2),
            "quote": data.get("quote") or {},
            "metadata": data.get("metadata") or {},
        })

    for key, value in distribution.items():
        distribution[key] = round((value / current_net_value_all) * 100, 2) if current_net_value_all > 0 else 0

    return {
        "total_invested": round(total_invested_all, 2),
        "current_balance": round(current_total_value, 2),
        "current_net_balance": round(current_net_value_all, 2),
        "portfolio_profitability": round(
            ((current_net_value_all - total_invested_all) / total_invested_all * 100),
            2,
        ) if total_invested_all > 0 else 0,
        "gross_portfolio_profitability": round(
            ((current_total_value - total_invested_all) / total_invested_all * 100),
            2,
        ) if total_invested_all > 0 else 0,
        "distribution": distribution,
        "assets": processed_assets,
    }


def replace_materialized_positions(current_user_id, assets):
    with get_db() as conn:
        conn.execute("DELETE FROM investment_positions WHERE user_id = ?", (current_user_id,))
        for asset in assets:
            asset_id = asset.get("asset_id")
            if not asset_id:
                continue

            source_transaction_id = asset.get("source_transaction_id") or None
            position_id = f"position:{source_transaction_id or asset_id}"
            conn.execute(
                """
                INSERT INTO investment_positions
                (
                    id, user_id, asset_id, source_transaction_id, quantity,
                    invested_amount, average_price, current_price, current_value,
                    net_value, taxes, profitability_percent, metadata, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                """,
                (
                    position_id,
                    current_user_id,
                    asset_id,
                    source_transaction_id,
                    safe_float(asset.get("quantity")),
                    safe_float(asset.get("average_price")) * safe_float(asset.get("quantity")),
                    safe_float(asset.get("average_price")),
                    safe_float(asset.get("current_price")),
                    safe_float(asset.get("current_value")),
                    safe_float(asset.get("net_value")),
                    safe_float(asset.get("taxes")),
                    safe_float(asset.get("profitability_percent")),
                    encode_metadata(asset.get("metadata") or {}),
                ),
            )


def refresh_materialized_positions(current_user_id):
    try:
        portfolio = build_portfolio_snapshot(current_user_id)
        replace_materialized_positions(current_user_id, portfolio["assets"])
    except Exception as exc:
        print(f"Nao foi possivel atualizar posicoes materializadas: {exc}")


@app.route("/api/investments/portfolio", methods=["GET"])
@token_required
def get_portfolio(current_user_id):
    try:
        if should_refresh_market_prices():
            try:
                refresh_market_prices(current_user_id, force=False)
            except Exception as exc:
                print(f"Erro ao atualizar cotacoes antes da carteira: {exc}")

        refresh_realized_results(current_user_id)
        portfolio = build_portfolio_snapshot(current_user_id)
        portfolio["realized_result"] = realized_results_summary(current_user_id)
        replace_materialized_positions(current_user_id, portfolio["assets"])
        return jsonify(portfolio), 200
    except Exception as exc:
        print(f"Erro no calculo: {exc}")
        return jsonify({"error": "Nao foi possivel calcular a carteira."}), 500


@app.route("/api/investments/update-prices", methods=["POST"])
@token_required
def update_stock_prices(current_user_id):
    try:
        payload = parse_json_body()
        investment_id = payload.get("investment_id")
        asset_id = payload.get("asset_id")
        asset_class = None
        if payload.get("asset_class") not in (None, ""):
            asset_class = require_choice(payload, "asset_class", "Classe do ativo", ALLOWED_ASSET_CLASSES)

        investments_to_update = fetch_investments(current_user_id, investment_id)
        if asset_id:
            investments_to_update = [
                inv for inv in investments_to_update
                if str(inv.get("asset_id")) == str(asset_id)
            ]
        if asset_class:
            investments_to_update = [
                inv for inv in investments_to_update
                if inv.get("asset_class") == asset_class
            ]
        if asset_id and not investments_to_update:
            return jsonify({"error": "Ativo nao encontrado para atualizacao de cotacao."}), 404

        market_result = refresh_market_prices(
            current_user_id,
            investment_id,
            force=True,
            asset_id=asset_id,
            asset_class=asset_class,
        )
        fixed_income_result = refresh_fixed_income_prices(current_user_id, investments_to_update)
        updated_assets = market_result.get("updated_assets", []) + fixed_income_result.get("updated_assets", [])
        failed_assets = market_result.get("failed_assets", []) + fixed_income_result.get("failed_assets", [])
        cached_assets = market_result.get("cached_assets", [])
        updated_count = len(updated_assets)
        refresh_materialized_positions(current_user_id)
        portfolio = build_portfolio_snapshot(current_user_id)
        scoped_asset_ids = {str(inv.get("asset_id")) for inv in investments_to_update if inv.get("asset_id")}
        stale_assets = [
            {
                "asset_id": asset.get("asset_id"),
                "id": asset.get("id"),
                "ticker": asset.get("ticker"),
                "name": asset.get("name"),
                "asset_class": asset.get("class"),
                "quote": asset.get("quote") or {},
            }
            for asset in portfolio.get("assets", [])
            if (not scoped_asset_ids or str(asset.get("asset_id")) in scoped_asset_ids)
            and (asset.get("quote") or {}).get("status") != "fresh"
        ]

        return jsonify({
            "message": "Cotacoes e CDI atualizados com sucesso",
            "updated_count": updated_count,
            "updated_assets": updated_assets,
            "failed_assets": failed_assets,
            "cached_assets": cached_assets,
            "stale_assets": stale_assets,
            "requested_tickers": market_result["requested_tickers"],
            "priced_tickers": market_result["priced_tickers"],
        }), 200
    except ValidationError as exc:
        return validation_error(str(exc))
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
        asset_class_filter = parse_asset_class_filter(request.args.get("asset_class"))
        filtered_investments = [
            inv for inv in investments_data
            if asset_class_filter is None or inv.get("asset_class") == asset_class_filter
        ]
        start_date = subtract_months(datetime.now(), months_back + 1).strftime("%Y-%m-%d")

        historical_prices = {}
        quoted_assets = [
            inv for inv in filtered_investments
            if inv.get("asset_class") in QUOTED_ASSET_CLASSES
        ]
        unique_tickers = sorted({
            ticker_key(asset.get("ticker_or_name"))
            for asset in quoted_assets
            if ticker_key(asset.get("ticker_or_name"))
        })

        if yf is None:
            historical_prices = {ticker: {} for ticker in unique_tickers}
        elif unique_tickers:
            future = _price_fetch_executor.submit(get_monthly_history, unique_tickers, start_date)
            try:
                historical_prices = future.result(timeout=PRICE_FETCH_TIMEOUT_SECONDS)
            except FutureTimeoutError:
                print("Tempo limite ao buscar historico no yfinance.")
                historical_prices = {ticker: {} for ticker in unique_tickers}
            except Exception as exc:
                print(f"Erro ao buscar historico no yfinance: {exc}")
                historical_prices = {ticker: {} for ticker in unique_tickers}

        evolution = build_portfolio_evolution(
            filtered_investments,
            historical_prices,
            months_back,
        )

        return jsonify({
            "historical_prices": historical_prices,
            "evolution": evolution,
        }), 200
    except Exception as exc:
        print(f"Erro no historico de investimentos: {exc}")
        return jsonify({"error": "Nao foi possivel carregar o historico de investimentos."}), 500


init_db()
run_startup_backup()

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", port=5000)
