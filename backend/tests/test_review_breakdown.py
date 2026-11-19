"""scripts/review_breakdown.py: a fila de Revisar e as correcoes do dono, so
lendo (2026-11-17, a pergunta "da para tirar a revisao?")."""

import importlib
import sqlite3
import subprocess
import sys

import pytest

from test_auto_record import category_id, confirm, notifications_on
from test_inbox import ITAU, detection, ms, send

pytestmark = pytest.mark.usefixtures("any_bank_notifications")


def _run(user, tmp_path, *extra):
    config = importlib.import_module("config")
    copy = tmp_path / "copy.db"
    source = sqlite3.connect(config.DATABASE_PATH)
    target = sqlite3.connect(copy)
    source.backup(target)
    source.close()
    target.close()
    backend = importlib.import_module("identity_invariants").__file__.rsplit("identity_invariants", 1)[0]
    return subprocess.run(
        [sys.executable, "scripts/review_breakdown.py", "--email", user["email"], "--database", str(copy),
         "--today", "2026-11-17", "--days", "3650", *extra],
        cwd=backend, capture_output=True, text=True, check=False,
    )


def _account(client, auth, name):
    response = client.post("/api/accounts", json={"name": name, "type": "CHECKING", "initial_balance": 0}, headers=auth)
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    return response.get_json()["id"]


def test_counts_the_queue_and_what_the_owner_changed(client, auth, user, tmp_path):
    notifications_on(client, auth)
    _account(client, auth, "Itaú")
    send(client, auth,
         detection("DEBIT_PURCHASE", 4590, at=ms(2026, 11, 10, 12, 0), app=ITAU, merchant="PADARIA"),
         detection("DEBIT_PURCHASE", 1200, at=ms(2026, 11, 16, 12, 0), app=ITAU, merchant="BANCA"),
         detection("PIX_OUT", 5000, at=ms(2026, 11, 16, 13, 0), app=ITAU, merchant=None, counterparty="Maria Silva"))
    rows = client.get("/api/transactions", headers=auth).get_json()
    rows = rows.get("items", rows) if isinstance(rows, dict) else rows
    padaria = next(row for row in rows if row["amount"] == 45.9)
    confirm(client, auth, {"table": "transactions", "id": padaria["id"],
                           "category_id": category_id(client, auth, "Padaria")})

    result = _run(user, tmp_path)
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "Fila de Revisar hoje: 2" in out
    assert "so o aviso (a Pluggy ainda nao confirmou)" in out
    assert "Gravados sozinhos desde" in out
    assert "    1  corrigido" in out
    assert "    2  como nasceu" in out
    assert "    1  categoria" in out


def test_unknown_email_exits_2(user, tmp_path):
    result = _run({"email": "ninguem@example.com"}, tmp_path)
    assert result.returncode == 2
