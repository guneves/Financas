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
# O build do frontend que o Flask serve em `/` (routes/frontend.py).
FRONTEND_DIST_DIR = resolve_app_path(
    os.getenv("FRONTEND_DIST_DIR", os.path.join("frontend", "dist")),
    PROJECT_DIR,
)
# Chaves que ja apareceram em codigo ou exemplo (o padrao antigo deste arquivo,
# .env.example, README): sao publicas, entao valem como chave nenhuma.
PUBLIC_JWT_SECRETS = frozenset({
    "",
    "dev-secret-change-me",
    "troque-esta-chave-em-producao",
    "change-this-key-in-production",
})
# Sem JWT_SECRET de verdade no ambiente, a chave e gerada uma vez e guardada
# ao lado do banco (no servidor, dentro do volume de dados), com permissao 600.
# Antes os tokens eram assinados com o padrao publico e qualquer um forjava um.
JWT_SECRET_FILE = resolve_app_path(
    os.getenv("JWT_SECRET_FILE", os.path.join(os.path.dirname(DATABASE_PATH), ".jwt_secret")),
    BASE_DIR,
)


def load_jwt_secret():
    configured = str(os.getenv("JWT_SECRET", "") or "").strip()
    if configured not in PUBLIC_JWT_SECRETS:
        return configured
    try:
        with open(JWT_SECRET_FILE, encoding="utf-8") as handle:
            stored = handle.read().strip()
        if stored and stored not in PUBLIC_JWT_SECRETS:
            return stored
    except FileNotFoundError:
        pass
    import secrets

    generated = secrets.token_urlsafe(48)
    directory = os.path.dirname(JWT_SECRET_FILE)
    if directory:
        os.makedirs(directory, exist_ok=True)
    descriptor = os.open(JWT_SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(generated)
    return generated


JWT_SECRET = load_jwt_secret()
# Cadastro aberto (/api/auth/signup): so enquanto o banco nao tem usuario —
# o primeiro cadastro e o do dono — ou com ALLOW_SIGNUP=1. O app e de um
# usuario so, e o servidor nao deve aceitar contas de qualquer um.
ALLOW_SIGNUP = str(os.getenv("ALLOW_SIGNUP", "0")).strip().lower() in {"1", "true", "yes"}
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
# Quanto o botao "Atualizar cotacoes" e a rodada de hora em hora esperam o provedor. O
# yfinance faz ate duas consultas (1d/1m e, fora do pregao, 5d/1d) de ate
# PRICE_DOWNLOAD_TIMEOUT_SECONDS cada: os 6 s da leitura da carteira nao bastam.
PRICE_REFRESH_TIMEOUT_SECONDS = read_float_env(
    "PRICE_REFRESH_TIMEOUT_SECONDS",
    25.0,
    minimum=1.0,
    maximum=120.0,
)
PRICE_FETCH_WORKERS = read_int_env("PRICE_FETCH_WORKERS", 2, minimum=1, maximum=4)
# De quanto em quanto tempo o servidor atualiza sozinho as cotacoes da renda
# variavel (acoes, FIIs, ETFs, BDRs, cripto) de cada usuario
# (services/quote_refresh.py). 0 desliga (os testes).
QUOTE_AUTO_REFRESH_SECONDS = read_int_env("QUOTE_AUTO_REFRESH_SECONDS", 3600, minimum=0)
HISTORY_CACHE_TTL_SECONDS = read_int_env("HISTORY_CACHE_TTL_SECONDS", 900, minimum=60)
# Um historico vencido (TTL acima) e servido na hora e atualizado em segundo
# plano, ate esta idade; mais velho que isso, o pedido espera o download.
HISTORY_CACHE_STALE_MAX_SECONDS = read_int_env(
    "HISTORY_CACHE_STALE_MAX_SECONDS", 7 * 24 * 3600, minimum=60,
)
# Copia em disco desses caches (history_store.py), ao lado do banco: um deploy
# ou reinicio nao faz o primeiro grafico esperar o Yahoo e o BCB. Vazio desliga.
_RAW_HISTORY_CACHE_FILE = os.getenv("HISTORY_CACHE_FILE")
HISTORY_CACHE_FILE = (
    resolve_app_path(os.path.join(os.path.dirname(DATABASE_PATH), "history_cache.json"), BASE_DIR)
    if _RAW_HISTORY_CACHE_FILE is None
    else (resolve_app_path(_RAW_HISTORY_CACHE_FILE, BASE_DIR) if _RAW_HISTORY_CACHE_FILE.strip() else "")
)
# Precos e taxas do Tesouro Direto (tesouro_client.py): o CSV do Tesouro
# Transparente e uma copia dele ao lado do banco. URL vazia desliga a busca
# (os testes); arquivo vazio, a copia.
TESOURO_PRICES_URL = os.getenv(
    "TESOURO_PRICES_URL",
    "https://www.tesourotransparente.gov.br/ckan/dataset/df56aa42-484a-4a59-8184-7676580c81e3"
    "/resource/796d2059-14e9-44e3-80c9-2d9e30b405c1/download/precotaxatesourodireto.csv",
).strip()
_RAW_TESOURO_PRICES_FILE = os.getenv("TESOURO_PRICES_FILE")
TESOURO_PRICES_FILE = (
    resolve_app_path(os.path.join(os.path.dirname(DATABASE_PATH), "tesouro_precos.csv"), BASE_DIR)
    if _RAW_TESOURO_PRICES_FILE is None
    else (resolve_app_path(_RAW_TESOURO_PRICES_FILE, BASE_DIR) if _RAW_TESOURO_PRICES_FILE.strip() else "")
)
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

# Log estruturado (applog.py): uma linha JSON por evento, no stderr e, com
# LOG_TO_FILE ligado, em LOG_DIR/app.log com rotacao (5 arquivos de 1 MB).
LOG_LEVEL = str(os.getenv("LOG_LEVEL", "INFO") or "INFO").strip().upper()
LOG_DIR = resolve_app_path(os.getenv("LOG_DIR", "logs"), BASE_DIR)
LOG_TO_FILE = str(os.getenv("LOG_TO_FILE", "1")).strip().lower() not in {"0", "false", "no"}

# Aprovar (services/inbox.py): folga de datas ao procurar o lancamento que ja
# existe para um movimento que o celular notificou.
INBOX_MATCH_DAYS = read_int_env("INBOX_MATCH_DAYS", 3, minimum=0, maximum=10)

# Open Finance pela Pluggy (pluggy_client.py, services/open_finance.py). As
# credenciais ficam so aqui, no ambiente: nunca no frontend, em log ou em
# resposta. Sem as duas, a integracao fica desligada (Ajustes diz isso).
PLUGGY_CLIENT_ID = str(os.getenv("PLUGGY_CLIENT_ID", "") or "").strip()
PLUGGY_CLIENT_SECRET = str(os.getenv("PLUGGY_CLIENT_SECRET", "") or "").strip()
PLUGGY_BASE_URL = str(os.getenv("PLUGGY_BASE_URL", "https://api.pluggy.ai") or "").strip().rstrip("/")
PLUGGY_TIMEOUT_SECONDS = read_float_env("PLUGGY_TIMEOUT_SECONDS", 20.0, minimum=1.0, maximum=120.0)
# De quanto em quanto tempo a thread le (so GET) o que a Pluggy ja trouxe do
# banco (services/open_finance_refresh.py), para quem nao escolheu em Ajustes.
# Nunca abaixo de 6 h (dono, 2026-10-27). 0 desliga a thread (testes).
OPEN_FINANCE_SYNC_SECONDS = read_int_env("OPEN_FINANCE_SYNC_SECONDS", 6 * 3600, minimum=0)
