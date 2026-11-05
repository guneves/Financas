"""Desempenho das consultas novas de Notificacoes + Pluggy (06-verify-and-fix.md §5).

- Cada consulta que um cenario gerado executa e passada por `EXPLAIN QUERY
  PLAN`: nenhuma varre `open_finance_transactions`, `notify_detections`,
  `transactions`, `inbox_items` ou `cc_expenses` inteira (SCAN sem indice).
- O par aproximado do pull (`near_notification_items()`, uma vez por linha nova
  sem par) custa o numero de notificacoes da janela, nunca o de itens da
  Pluggy: contado em instrucoes da VM do SQLite (`set_progress_handler`), que
  nao dependem do relogio da maquina.
"""

import importlib
import re
import sqlite3

import pytest

from open_finance_world import World, bank_tx, connected, fake_pluggy, open_finance_module  # noqa: F401
from test_auto_record import notifications_on
from test_notify_pluggy_fuzz import Run, Scenario

HOT_TABLES = ("open_finance_transactions", "notify_detections", "transactions", "inbox_items", "cc_expenses")


@pytest.fixture()
def world(client, auth, fake_pluggy):
    notifications_on(client, auth)
    return World(client, auth, fake_pluggy)


def test_no_query_of_a_generated_world_scans_a_hot_table(world, user, monkeypatch, invoices_module):
    db = importlib.import_module("db")
    statements = set()
    real_connect = sqlite3.connect

    def tracing(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        conn.set_trace_callback(statements.add)
        return conn

    monkeypatch.setattr(db.sqlite3, "connect", tracing)
    Run(world, Scenario(3).generate(), monkeypatch, invoices_module, user).play()
    monkeypatch.setattr(db.sqlite3, "connect", real_connect)
    scans = {}
    with db.get_db() as conn:
        for sql in statements:
            if not re.match(r"\s*(SELECT|UPDATE|DELETE|WITH)\b", sql, re.I):
                continue
            for step in conn.execute("EXPLAIN QUERY PLAN " + sql).fetchall():
                found = re.match(r"SCAN (\w+)", step[3])
                if found and found.group(1) in HOT_TABLES:
                    scans[" ".join(sql.split())[:300]] = step[3]
    assert len(statements) > 500  # o cenario rodou de verdade
    assert scans == {}


def _vm_steps(conn, call):
    steps = [0]

    def count():
        steps[0] += 1
        return 0

    conn.set_progress_handler(count, 100)
    try:
        call()
    finally:
        conn.set_progress_handler(None, 0)
    return steps[0]


def test_the_near_pass_costs_the_notifications_not_the_pluggy_items(world, user):
    item_id, _p, made = connected(world)
    world.call("patch", "/api/open-finance/settings", json={"auto_record": True, "include_pending": True})
    account = made["bank"][0]
    db = importlib.import_module("db")
    inbox = importlib.import_module("services.inbox")

    def steps_for_a_new_row():
        with db.get_db() as conn:
            conn.execute("UPDATE open_finance_accounts SET synced_until = NULL WHERE user_id = ?", (user["id"],))
        world.sync(item_id)
        with db.get_db() as conn:
            row = dict(conn.execute(
                "SELECT * FROM open_finance_transactions WHERE user_id = ? AND role = 'SOURCE' LIMIT 1",
                (user["id"],),
            ).fetchone())
            return _vm_steps(conn, lambda: inbox.near_notification_items(conn, user["id"], row))

    world.fake.add_tx(account, *(bank_tx(-(100 + index) / 100, f"2026-10-{1 + index % 25:02d}", f"LOJA {index}")
                                 for index in range(200)))
    few = steps_for_a_new_row()
    world.fake.add_tx(account, *(bank_tx(-(900 + index) / 100, f"2026-10-{1 + index % 25:02d}", f"LOJA X{index}")
                                 for index in range(800)))
    many = steps_for_a_new_row()
    # 5x mais itens da Pluggy na janela, nenhuma notificacao a mais.
    assert many <= few * 1.5 + 5, (few, many)
