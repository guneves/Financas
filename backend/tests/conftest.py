"""Shared fixtures for the backend test suite.

`backend/app.py` reads its configuration and calls `init_db()` at import time,
so the environment has to be pointed at a throwaway database *before* the
module is imported. Each test session gets its own temporary SQLite file, built
by the real migrations in `database/migrations`, so the tests exercise the same
schema the app runs against.
"""

import importlib
import os
import sys
import tempfile
import uuid

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_DIR = os.path.dirname(BACKEND_DIR)

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


@pytest.fixture(scope="session")
def app_module():
    tmp_dir = tempfile.mkdtemp(prefix="financas-tests-")
    os.environ["DATABASE_PATH"] = os.path.join(tmp_dir, "test.db")
    os.environ["DATABASE_MIGRATIONS_DIR"] = os.path.join(PROJECT_DIR, "database", "migrations")
    os.environ["DATABASE_BACKUP_DIR"] = os.path.join(tmp_dir, "backups")
    os.environ["ATTACHMENTS_DIR"] = os.path.join(tmp_dir, "attachments")
    os.environ["JWT_SECRET"] = "test-secret"
    # O backup automatico de boot e exercitado em test_backups.py, com controle explicito.
    os.environ["AUTO_BACKUP_ON_BOOT"] = "0"
    os.environ["CORS_ORIGINS"] = "*"

    # config.py le o ambiente no import, e os modulos do app (db, auth...) copiam
    # os valores dele. Por isso nenhum teste importa esses modulos no topo do
    # arquivo: pegue-os por fixture (app_module, db_module), depois daqui.
    # Os modulos puros (brapi_client, statement_import...) podem ser importados
    # no topo — nao leem config e nao devem ser recarregados.
    for name in ("app", "config"):
        sys.modules.pop(name, None)
    module = importlib.import_module("app")
    module.app.config["TESTING"] = True
    return module


@pytest.fixture()
def client(app_module):
    with app_module.app.test_client() as test_client:
        yield test_client


def _signup(client, email=None, password="senha-de-teste-123", username="Usuario de teste"):
    email = email or f"user-{uuid.uuid4().hex[:10]}@example.com"
    response = client.post(
        "/api/auth/signup",
        json={"email": email, "password": password, "username": username},
    )
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    body = response.get_json()
    token = body["access_token"]
    return {
        "id": body["user"]["id"],
        "email": email,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture()
def user(client):
    """A signed-up user with ready-to-use Authorization headers."""
    return _signup(client)


@pytest.fixture()
def other_user(client):
    """A second, unrelated user — used to prove `user_id` isolation."""
    return _signup(client)


@pytest.fixture()
def auth(user):
    return user["headers"]


@pytest.fixture(scope="session")
def db_module(app_module):
    """`backend/db.py` — conexao, migrations e backups. Patch aqui o que ele usa."""
    return importlib.import_module("db")


@pytest.fixture(scope="session")
def invoices_module(app_module):
    """`backend/services/invoices.py` — regras de fatura e o relogio `local_today`."""
    return importlib.import_module("services.invoices")
