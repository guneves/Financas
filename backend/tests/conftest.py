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
    # Nenhuma tela do APK por padrao: test_app_bundle.py aponta para a sua.
    os.environ["APP_BUNDLE_DIR"] = os.path.join(tmp_dir, "app-bundle")
    os.environ["JWT_SECRET"] = "test-secret"
    # Os testes cadastram varios usuarios (user, other_user).
    os.environ["ALLOW_SIGNUP"] = "1"
    # O backup automatico de boot e exercitado em test_backups.py, com controle explicito.
    os.environ["AUTO_BACKUP_ON_BOOT"] = "0"
    # Sem copia em disco do historico: cada teste comeca do cache que ele monta.
    # test_history_fetch.py liga a copia num arquivo proprio.
    os.environ["HISTORY_CACHE_FILE"] = ""
    # Nenhum teste baixa os precos do Tesouro; quem precisa usa tesouro_client.set_prices().
    os.environ["TESOURO_PRICES_URL"] = ""
    os.environ["TESOURO_PRICES_FILE"] = ""
    # Nem a thread que atualiza as cotacoes de hora em hora (services/quote_refresh.py).
    os.environ["QUOTE_AUTO_REFRESH_SECONDS"] = "0"
    os.environ["CORS_ORIGINS"] = "*"
    # Log so no stderr: os testes nao criam backend/logs.
    os.environ["LOG_TO_FILE"] = "0"
    # O token real do backend/.env nao vale nos testes: nenhum teste vai a brapi
    # sem pedir (monkeypatch.setenv + urlopen substituido).
    os.environ["BRAPI_TOKEN"] = ""

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


@pytest.fixture(scope="session")
def prices_module(app_module):
    """`backend/services/prices.py` — cotacoes. Patch aqui `yf` e `download_close_prices`."""
    return importlib.import_module("services.prices")


@pytest.fixture(scope="session")
def fixed_income_module(app_module):
    """`backend/services/fixed_income.py` — patch aqui `fetch_bcb_series` e o `urllib`."""
    return importlib.import_module("services.fixed_income")


@pytest.fixture(scope="session")
def realized_results_module(app_module):
    """`backend/services/realized_results.py` — custo medio, aliquotas e resultado realizado."""
    return importlib.import_module("services.realized_results")


@pytest.fixture(scope="session")
def portfolio_module(app_module):
    """`backend/services/portfolio.py` — posicoes, alvos de cotacao e evolucao."""
    return importlib.import_module("services.portfolio")


def _daily_history_from_months(monthly_by_ticker, splits=None):
    """O que `get_daily_history()` devolve, montado de {ticker: {AAAA-MM: preco}}:
    todo dia do mes (ate hoje) fecha no preco daquele mes."""
    import calendar
    from datetime import date

    today = date.today()
    prices = {}
    for ticker, months in monthly_by_ticker.items():
        by_day = {}
        for month, price in months.items():
            year, number = int(month[:4]), int(month[5:7])
            for day in range(1, calendar.monthrange(year, number)[1] + 1):
                current = date(year, number, day)
                if current <= today:
                    by_day[current.isoformat()] = price
        prices[ticker] = by_day
    return {"prices": prices, "splits": dict(splits or {})}


@pytest.fixture(scope="session")
def daily_history_from_months():
    """Troca de `routes.investments.get_daily_history` a partir de fechamentos mensais."""
    return _daily_history_from_months
