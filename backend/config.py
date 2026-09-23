"""Configuracao do backend, lida do ambiente (e do `backend/.env`) uma vez, no import.

Os valores sao constantes de modulo. Quem usa um deles importa pelo nome
(`from config import DATABASE_PATH`), entao um teste que precisa trocar um valor
faz `monkeypatch.setattr` no modulo que *usa* o valor, nao aqui.
"""

import os

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        return False

load_dotenv()

try:
    JWT_EXP_DAYS = max(1, int(os.getenv("JWT_EXP_DAYS", "30")))
except ValueError:
    JWT_EXP_DAYS = 30


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
# Comprovantes por lancamento (014). Fora do banco e fora do zip de backup:
# fotos de recibo multiplicariam o tamanho de cada backup diario da retencao.
# O backup guarda um espelho, uma copia de cada arquivo (db.mirror_attachments).
ATTACHMENTS_DIR = resolve_app_path(
    os.getenv("ATTACHMENTS_DIR", os.path.join("attachments")),
    BASE_DIR,
)
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")


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
ATTACHMENT_MAX_BYTES = read_int_env(
    "ATTACHMENT_MAX_BYTES",
    10 * 1024 * 1024,
    minimum=64 * 1024,
    maximum=50 * 1024 * 1024,
)
