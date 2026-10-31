"""O saldo em reais e o Ritmo de gastos (dono, 2026-10-31).

- a transferencia para a conta global sai do saldo em reais da Evolucao do saldo;
- o gasto de um mes numa linha so (Inter) conta no saldo, nunca no Ritmo.
"""

import importlib


def account(client, auth, name, **extra):
    response = client.post("/api/accounts", json={"name": name, "type": "CHECKING", "initial_balance": 1000, **extra}, headers=auth)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["id"]


def flow(user, keys):
    home = importlib.import_module("services.home")
    accounts = importlib.import_module("services.accounts")
    db = importlib.import_module("db")
    with db.get_db() as conn:
        rows = [dict(row) for row in accounts.account_balance_rows(conn, user["id"])]
        return home.monthly_flow(conn, user["id"], rows, keys)


def test_a_transfer_to_the_global_account_leaves_the_reais_balance(client, auth, user):
    bank = account(client, auth, "Banco")
    wise = account(client, auth, "Wise", currency="USD", initial_balance=0)
    response = client.post("/api/transfers", headers=auth, json={
        "account_id": bank, "transfer_account_id": wise, "amount": 559.43, "transfer_amount": 110, "date": "2026-10-06",
    })
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    [october] = flow(user, ["2026-10"])
    assert october["balance"] == 440.57


def test_a_month_line_counts_in_the_balance_and_never_in_the_pace(client, auth, user):
    bank = account(client, auth, "Inter")
    db = importlib.import_module("db")
    panels = importlib.import_module("services.home_panels")
    with db.get_db() as conn:
        conn.execute(
            """INSERT INTO transactions (id, user_id, account_id, amount, date, category, description, type, source_type, source_id)
               VALUES ('line', ?, ?, 300, '2026-08-31', 'Outros', 'Gastos no Inter', 'EXPENSE', 'MONTH_SUMMARY', 'inter:2026-08')""",
            (user["id"], bank),
        )
    [august] = flow(user, ["2026-08"])
    assert august["balance"] == 700.0
    with db.get_db() as conn:
        spending = panels.monthly_spending(conn, user["id"], ["2026-08"])
    assert spending["2026-08"]["total"] == 0
