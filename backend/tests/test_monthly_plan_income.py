"""Plano do mes a partir da renda (038).

O que estes testes fixam:

- a renda e o unico valor em reais, obrigatoria; Investir e Gastar sao % dela e
  as categorias sao % do Gastar — os reais saem na leitura, nos dois niveis, e
  nunca sao gravados;
- trocar a renda ou o Gastar % recalcula tudo, categorias incluidas;
- mais de 100% e recusado nos dois niveis; 33,33% x 3 nao escorrega;
- um mes sem plano herda o anterior com as categorias; o DELETE devolve o mes
  ao plano anterior, inteiro;
- rollover com %: a sobra do mes anterior e sobre o Gastar *daquele* mes;
- Saldo do plano = Gastar - gasto do mes, o mesmo numero no plano, no
  progresso e no orcamento; Disponivel por dia = ele / dias que faltam;
- a renda recebida so compara;
- a migration 038 converte o que pode; o resto e `needs_income`, nada e
  calculado dele, e o PUT com a renda converte com as mesmas formulas;
- nada de outro usuario.
"""

import importlib
import os
import sqlite3
from datetime import date

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(os.path.dirname(BACKEND_DIR), "database", "migrations")

TODAY = date(2025, 12, 15)


@pytest.fixture(autouse=True)
def frozen_today(app_module, monkeypatch):
    for name in ("services.monthly_plan", "services.goals"):
        monkeypatch.setattr(importlib.import_module(name), "local_today", lambda: TODAY)


def put_plan(client, headers, month, income, spend, invest=0, status=200):
    response = client.put("/api/monthly-plan", headers=headers, json={
        "month": month, "income_amount": income, "spend_percent": spend, "invest_percent": invest,
    })
    assert response.status_code == status, response.get_data(as_text=True)
    return response.get_json()


def get_plan(client, headers, month):
    response = client.get("/api/monthly-plan", headers=headers, query_string={"month": month})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def get_budgets(client, headers, month):
    response = client.get("/api/budgets", headers=headers, query_string={"month": month})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def categories_of(client, headers):
    return {item["name"]: item for item in client.get("/api/categories", headers=headers).get_json()}


def add_category(client, headers, month, category_id, percent, status=201, **extra):
    response = client.post("/api/budgets", headers=headers, json={
        "category_id": category_id, "month": month, "planned_percent": percent, **extra,
    })
    assert response.status_code == status, response.get_data(as_text=True)
    return response.get_json()


def add_entry(client, headers, amount, day, *, kind="EXPENSE", category="Lazer", category_id=None):
    payload = {"amount": amount, "date": day, "category": category, "type": kind, "description": "teste"}
    if category_id:
        payload["category_id"] = category_id
    response = client.post("/api/transactions", headers=headers, json=payload)
    assert response.status_code in (200, 201), response.get_data(as_text=True)


def item(body, name):
    items = body["categories"]["items"] if "categories" in body else body["items"]
    return next(entry for entry in items if entry["category_name"] == name)


# --- reais a partir dos percentuais ----------------------------------------


def test_every_amount_comes_from_the_income(client, auth):
    cats = categories_of(client, auth)
    put_plan(client, auth, "2025-12", 8000, spend=60, invest=25)
    add_category(client, auth, "2025-12", cats["Moradia"]["id"], 50)
    add_category(client, auth, "2025-12", cats["Lazer"]["id"], 12.5)

    body = get_plan(client, auth, "2025-12")
    assert body["needs_income"] is False
    assert body["income"]["planned"] == 8000
    assert body["invest"]["percent"] == 25
    assert body["invest"]["amount"] == 2000
    assert body["spend"]["percent"] == 60
    assert body["spend"]["amount"] == 4800
    # Sem destino: 100 - 25 - 60.
    assert body["unallocated"] == {"percent": 15, "amount": 1200}
    # Categorias: % do Gastar (4.800), nao da renda.
    assert item(body, "Moradia")["planned_amount"] == 2400
    assert item(body, "Lazer")["planned_amount"] == 600
    assert body["categories"]["assigned_percent"] == 62.5
    assert body["categories"]["assigned_amount"] == 3000
    # Sem categoria: o resto do Gastar.
    assert body["categories"]["unassigned"] == {"percent": 37.5, "amount": 1800}


def test_no_computed_amount_is_stored(client, auth, user, db_module):
    cats = categories_of(client, auth)
    put_plan(client, auth, "2025-12", 8000, spend=60, invest=25)
    add_category(client, auth, "2025-12", cats["Lazer"]["id"], 12.5)
    with db_module.get_db() as conn:
        plan = conn.execute("SELECT * FROM monthly_plans WHERE user_id = ?", (user["id"],)).fetchone()
        budget = conn.execute("SELECT * FROM budgets WHERE user_id = ?", (user["id"],)).fetchone()
    assert plan["income_amount"] == 8000
    assert (plan["spend_percent"], plan["invest_percent"]) == ("60.000000", "25.000000")
    assert (plan["spend_amount"], plan["invest_amount"]) == (0, 0)
    assert budget["planned_percent"] == "12.500000"
    assert budget["planned_amount"] == 0


def test_changing_the_income_or_spend_recalculates_both_levels(client, auth):
    cats = categories_of(client, auth)
    put_plan(client, auth, "2025-12", 10000, spend=50, invest=20)
    add_category(client, auth, "2025-12", cats["Lazer"]["id"], 10)
    body = get_plan(client, auth, "2025-12")
    assert (body["spend"]["amount"], item(body, "Lazer")["planned_amount"]) == (5000, 500)

    body = put_plan(client, auth, "2025-12", 12000, spend=50, invest=20)
    assert body["invest"]["amount"] == 2400
    assert (body["spend"]["amount"], item(body, "Lazer")["planned_amount"]) == (6000, 600)

    body = put_plan(client, auth, "2025-12", 12000, spend=40, invest=20)
    assert (body["spend"]["amount"], item(body, "Lazer")["planned_amount"]) == (4800, 480)
    assert item(body, "Lazer")["planned_percent"] == 10


def test_a_third_three_times_does_not_drift(client, auth):
    body = put_plan(client, auth, "2025-12", 3000, spend=66.67, invest=33.33)
    assert body["unallocated"]["percent"] == 0
    # 33,333333% guardado com seis casas devolve os R$ 1.000 de um terco.
    body = put_plan(client, auth, "2025-12", 3000, spend=33.333333, invest=33.333333)
    assert body["invest"]["amount"] == 1000
    assert body["spend"]["amount"] == 1000
    assert body["unallocated"]["amount"] == 1000


def test_over_100_percent_is_refused_and_exactly_100_fits(client, auth):
    response = client.put("/api/monthly-plan", headers=auth, json={
        "month": "2025-12", "income_amount": 5000, "spend_percent": 70, "invest_percent": 30.000001,
    })
    assert response.status_code == 400
    assert "100%" in response.get_json()["error"]
    body = put_plan(client, auth, "2025-12", 5000, spend=70, invest=30)
    assert body["unallocated"] == {"percent": 0, "amount": 0}


@pytest.mark.parametrize("income", [None, "", 0, -100])
def test_a_plan_without_income_is_refused(client, auth, income):
    payload = {"month": "2025-12", "spend_percent": 50, "invest_percent": 10}
    if income is not None:
        payload["income_amount"] = income
    response = client.put("/api/monthly-plan", headers=auth, json=payload)
    assert response.status_code == 400
    assert "renda" in response.get_json()["error"].lower()
    assert get_plan(client, auth, "2025-12")["plan"] is None


def test_received_income_only_compares(client, auth):
    put_plan(client, auth, "2025-12", 10000, spend=50, invest=20)
    add_entry(client, auth, 4000, "2025-12-05", kind="INCOME", category="Salário")
    body = get_plan(client, auth, "2025-12")
    assert body["income"] == {"planned": 10000, "received": 4000}
    assert body["spend"]["amount"] == 5000
    assert body["invest"]["amount"] == 2000


# --- heranca ----------------------------------------------------------------


def test_a_month_inherits_the_plan_and_its_categories(client, auth):
    cats = categories_of(client, auth)
    put_plan(client, auth, "2025-10", 10000, spend=50, invest=20)
    add_category(client, auth, "2025-10", cats["Lazer"]["id"], 10)

    december = get_plan(client, auth, "2025-12")
    assert december["plan"]["inherited"] is True
    assert december["plan"]["source_month"] == "2025-10"
    assert december["categories"]["inherited"] is True
    assert december["categories"]["source_month"] == "2025-10"
    assert item(december, "Lazer")["planned_amount"] == 500

    # Um plano novo em dezembro leva as categorias herdadas junto.
    december = put_plan(client, auth, "2025-12", 20000, spend=50, invest=20)
    assert december["categories"]["inherited"] is False
    assert item(december, "Lazer")["planned_amount"] == 1000
    assert item(get_plan(client, auth, "2025-10"), "Lazer")["planned_amount"] == 500

    # Apagar o plano de dezembro devolve o mes ao de outubro, inteiro.
    add_category(client, auth, "2025-12", cats["Moradia"]["id"], 30)
    response = client.delete("/api/monthly-plan", headers=auth, query_string={"month": "2025-12"})
    assert response.status_code == 200
    back = response.get_json()
    assert back["plan"]["source_month"] == "2025-10"
    assert [entry["category_name"] for entry in back["categories"]["items"]] == ["Lazer"]
    assert item(back, "Lazer")["planned_amount"] == 500


def test_rollover_carries_the_previous_months_own_amount(client, auth):
    cats = categories_of(client, auth)
    put_plan(client, auth, "2025-10", 10000, spend=50)          # Gastar 5.000
    add_category(client, auth, "2025-10", cats["Lazer"]["id"], 10)   # 500
    add_entry(client, auth, 200, "2025-10-10", category_id=cats["Lazer"]["id"])
    # O plano novo de novembro traz a categoria junto, como linha de novembro.
    november = put_plan(client, auth, "2025-11", 20000, spend=50)    # Gastar 10.000
    assert item(november, "Lazer")["inherited"] is False

    response = client.patch(
        f"/api/budgets/{item(november, 'Lazer')['id']}", headers=auth,
        query_string={"month": "2025-11"}, json={"rollover": True},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    november = item(get_plan(client, auth, "2025-11"), "Lazer")
    # Sobra de outubro sobre o Gastar de outubro (500 - 200), nao o de novembro.
    assert november["carryover"] == 300
    assert november["planned_amount"] == 1000
    assert november["available"] == 1300


# --- Saldo do plano e Disponivel por dia -----------------------------------


def test_plan_balance_and_daily_available(client, auth):
    cats = categories_of(client, auth)
    put_plan(client, auth, "2025-12", 10000, spend=34)          # Gastar 3.400
    add_category(client, auth, "2025-12", cats["Lazer"]["id"], 10)
    add_entry(client, auth, 1500, "2025-12-03", category="Moradia")
    add_entry(client, auth, 200, "2025-12-04", category_id=cats["Lazer"]["id"])

    body = get_plan(client, auth, "2025-12")
    # 3.400 - 1.700 gastos no mes (todas as categorias, nao so as orcadas).
    assert body["plan_balance"] == 1700
    assert body["spend"]["remaining"] == 1700
    assert body["progress"]["spend_remaining"] == 1700
    # 15 de dezembro: faltam 17 dias com hoje.
    assert body["days_remaining"] == 17
    assert body["daily_available"] == 100
    # O orcamento mostra o mesmo Saldo do plano; o das categorias e outro.
    totals = get_budgets(client, auth, "2025-12")["totals"]
    assert totals["plan_balance"] == 1700
    assert totals["plan_spent"] == 1700
    assert totals["remaining"] == 140


def test_daily_available_in_past_and_future_months(client, auth):
    put_plan(client, auth, "2025-11", 3000, spend=100)
    past = get_plan(client, auth, "2025-11")
    assert past["days_remaining"] == 0
    assert past["daily_available"] is None
    future = get_plan(client, auth, "2026-02")
    assert future["days_remaining"] == 28
    assert future["daily_available"] == 107.14


# --- a migration 038 -----------------------------------------------------------


def migrated_up_to(path, last_version):
    """Um banco como o de quem parou na migration `last_version` (db.init_db)."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, name TEXT NOT NULL)")
    for filename in sorted(os.listdir(MIGRATIONS_DIR)):
        version = filename.split("_", 1)[0]
        if filename.endswith(".sql") and version <= last_version:
            with open(os.path.join(MIGRATIONS_DIR, filename), encoding="utf-8") as file:
                conn.executescript(file.read())
            conn.execute("INSERT OR IGNORE INTO schema_migrations VALUES (?, ?)", (version, filename))
    conn.commit()
    return conn


def apply_038(conn):
    [filename] = [name for name in os.listdir(MIGRATIONS_DIR) if name.startswith("038_")]
    with open(os.path.join(MIGRATIONS_DIR, filename), encoding="utf-8") as file:
        conn.executescript(file.read())


def test_038_converts_what_has_income_and_leaves_the_rest(tmp_path):
    conn = migrated_up_to(str(tmp_path / "old.db"), "037")
    conn.executescript("""
        INSERT INTO users (id, email, password_hash) VALUES ('u1', 'a@b.c', 'x'), ('u2', 'd@e.f', 'x');
        INSERT INTO categories (id, user_id, name, kind) VALUES
            ('lazer', 'u1', 'Lazer', 'EXPENSE'), ('lazer2', 'u2', 'Lazer', 'EXPENSE');
        INSERT INTO monthly_plans (id, user_id, month, spend_amount, invest_amount, income_amount) VALUES
            ('p10', 'u1', '2025-10', 2000, 1000, 3000),
            ('p12', 'u1', '2025-12', 1500, 500, NULL),
            ('p01', 'u1', '2026-01', 1500, 500, 0),
            ('p02', 'u1', '2026-02', 0, 500, 1000),
            ('p03', 'u1', '2026-03', 900, 200, 1000),
            ('q10', 'u2', '2025-10', 100, 0, NULL);
        INSERT INTO budgets (id, user_id, category_id, month, planned_amount) VALUES
            ('b09', 'u1', 'lazer', '2025-09', 100),
            ('b10', 'u1', 'lazer', '2025-10', 500),
            ('b11', 'u1', 'lazer', '2025-11', 333.33),
            ('b12', 'u1', 'lazer', '2025-12', 300),
            ('b02', 'u1', 'lazer', '2026-02', 50),
            ('c11', 'u2', 'lazer2', '2025-11', 50);
    """)
    conn.commit()

    apply_038(conn)

    plans = {row["id"]: row for row in conn.execute("SELECT * FROM monthly_plans")}
    # 2.000 e 1.000 de 3.000.
    assert (plans["p10"]["spend_percent"], plans["p10"]["invest_percent"]) == ("66.666667", "33.333333")
    # Sem renda (ou renda 0): fica esperando a renda.
    for key in ("p12", "p01", "q10"):
        assert plans[key]["spend_percent"] is None and plans[key]["invest_percent"] is None
    # Os reais antigos ficam onde estavam.
    assert plans["p10"]["spend_amount"] == 2000
    # Passava da renda: converte assim mesmo (a API e que recusa os novos).
    assert (plans["p03"]["spend_percent"], plans["p03"]["invest_percent"]) == ("90.000000", "20.000000")

    budgets = {row["id"]: row["planned_percent"] for row in conn.execute("SELECT * FROM budgets")}
    assert budgets["b10"] == "25.000000"          # 500 de 2.000
    assert budgets["b11"] == "16.666500"          # herda o plano de outubro
    assert budgets["b09"] is None                 # sem plano
    assert budgets["b12"] is None                 # plano sem renda
    assert budgets["b02"] is None                 # Gastar 0: nao ha base
    assert budgets["c11"] is None                 # o plano do outro usuario nao tem renda
    conn.close()


def test_the_running_database_has_038(db_module):
    with db_module.get_db() as conn:
        plan_columns = {row[1] for row in conn.execute("PRAGMA table_info(monthly_plans)").fetchall()}
        budget_columns = {row[1] for row in conn.execute("PRAGMA table_info(budgets)").fetchall()}
    assert {"invest_percent", "spend_percent", "spend_amount", "invest_amount"} <= plan_columns
    assert {"planned_percent", "planned_amount"} <= budget_columns


# --- o que a 038 nao converteu: needs_income ------------------------------------


def legacy_rows(db_module, user_id, category_id):
    """O que a 038 deixa de um plano sem renda: os reais, nenhum percentual."""
    with db_module.get_db() as conn:
        conn.execute(
            """
            INSERT INTO monthly_plans (id, user_id, month, spend_amount, invest_amount, income_amount)
            VALUES (?, ?, '2025-11', 2000, 500, NULL)
            """,
            (f"plano-{user_id}", user_id),
        )
        for month, amount in (("2025-11", 500), ("2025-12", 400)):
            conn.execute(
                """
                INSERT INTO budgets (id, user_id, category_id, month, planned_amount)
                VALUES (?, ?, ?, ?, ?)
                """,
                (f"orc-{user_id}-{month}", user_id, category_id, month, amount),
            )


def test_needs_income_computes_nothing(client, auth, user, db_module):
    cats = categories_of(client, auth)
    legacy_rows(db_module, user["id"], cats["Lazer"]["id"])
    add_entry(client, auth, 120, "2025-11-05", category_id=cats["Lazer"]["id"])

    body = get_plan(client, auth, "2025-11")
    assert body["needs_income"] is True
    assert body["plan"]["needs_income"] is True
    assert body["plan"]["legacy"] == {"spend_amount": 2000, "invest_amount": 500}
    assert body["spend"]["amount"] is None
    assert body["invest"]["amount"] is None
    assert body["unallocated"] == {"percent": None, "amount": None}
    assert body["plan_balance"] is None
    assert body["daily_available"] is None
    assert body["progress"] is None
    assert body["flags"] == []
    # O realizado continua.
    assert body["spend"]["realized"] == 120
    lazer = item(body, "Lazer")
    assert lazer["needs_income"] is True
    assert lazer["status"] == "NEEDS_INCOME"
    assert lazer["legacy_amount"] == 500
    assert lazer["planned_amount"] is None
    assert lazer["spent"] == 120


def test_the_put_with_income_converts_the_plan_and_its_months(client, auth, user, db_module):
    cats = categories_of(client, auth)
    legacy_rows(db_module, user["id"], cats["Lazer"]["id"])

    # So a renda: os % saem dos reais antigos (2.000 e 500 de 5.000).
    response = client.put("/api/monthly-plan", headers=auth, json={"month": "2025-11", "income_amount": 5000})
    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert body["needs_income"] is False
    assert (body["spend"]["percent"], body["invest"]["percent"]) == (40, 10)
    assert (body["spend"]["amount"], body["invest"]["amount"]) == (2000, 500)
    # A categoria do mes: 500 de 2.000.
    assert item(body, "Lazer")["planned_percent"] == 25
    assert item(body, "Lazer")["planned_amount"] == 500
    # Dezembro, regido pelo mesmo plano, tambem converte: 400 de 2.000.
    december = get_plan(client, auth, "2025-12")
    assert december["needs_income"] is False
    assert item(december, "Lazer")["planned_percent"] == 20
    assert item(december, "Lazer")["planned_amount"] == 400


def test_the_put_can_bring_new_percentages_to_an_old_plan(client, auth, user, db_module):
    cats = categories_of(client, auth)
    legacy_rows(db_module, user["id"], cats["Lazer"]["id"])

    body = put_plan(client, auth, "2025-11", 5000, spend=50, invest=20)
    assert body["spend"]["amount"] == 2500
    # A categoria antiga vira % do Gastar novo: 500 de 2.500.
    assert item(body, "Lazer")["planned_percent"] == 20
    assert item(body, "Lazer")["planned_amount"] == 500


def test_a_converted_plan_over_the_income_is_flagged(client, auth, user, db_module):
    cats = categories_of(client, auth)
    with db_module.get_db() as conn:
        conn.execute(
            """
            INSERT INTO monthly_plans (id, user_id, month, spend_amount, invest_amount, income_amount,
                                       spend_percent, invest_percent)
            VALUES (?, ?, '2025-12', 900, 200, 1000, '90.000000', '20.000000')
            """,
            (f"plano-{user['id']}", user["id"]),
        )
        for name, percent in (("Moradia", "70.000000"), ("Lazer", "50.000000")):
            conn.execute(
                """
                INSERT INTO budgets (id, user_id, category_id, month, planned_amount, planned_percent)
                VALUES (?, ?, ?, '2025-12', 0, ?)
                """,
                (f"orc-{user['id']}-{name}", user["id"], cats[name]["id"], percent),
            )

    body = get_plan(client, auth, "2025-12")
    flags = {entry["code"]: entry for entry in body["flags"]}
    assert flags["PLAN_OVER_INCOME"]["amount"] == 100
    assert body["unallocated"] == {"percent": -10, "amount": -100}
    # Categorias em 120% do Gastar (900): 180 alem.
    assert flags["CATEGORIES_OVER_SPEND"]["amount"] == 180
    assert body["categories"]["unassigned"]["percent"] == -20

    # Reduzir uma categoria vale mesmo ainda acima de 100%; aumentar, nao.
    lazer = item(body, "Lazer")
    up = client.patch(f"/api/budgets/{lazer['id']}", headers=auth, json={"planned_percent": 51})
    assert up.status_code == 400
    down = client.patch(f"/api/budgets/{lazer['id']}", headers=auth, json={"planned_percent": 40})
    assert down.status_code == 200, down.get_data(as_text=True)


# --- isolamento -----------------------------------------------------------------


def test_another_users_plan_and_categories_stay_apart(client, auth, user, other_user, db_module):
    mine = categories_of(client, auth)
    theirs = categories_of(client, other_user["headers"])
    legacy_rows(db_module, other_user["id"], theirs["Lazer"]["id"])
    legacy_rows(db_module, user["id"], mine["Lazer"]["id"])

    # Converter o meu plano nao toca nas linhas antigas do outro.
    client.put("/api/monthly-plan", headers=auth, json={"month": "2025-11", "income_amount": 5000})
    other = get_plan(client, other_user["headers"], "2025-11")
    assert other["needs_income"] is True
    assert item(other, "Lazer")["planned_percent"] is None
    with db_module.get_db() as conn:
        untouched = conn.execute(
            "SELECT COUNT(*) FROM budgets WHERE user_id = ? AND planned_percent IS NOT NULL",
            (other_user["id"],),
        ).fetchone()[0]
    assert untouched == 0

    # Nem o plano nem as categorias de um aparecem para o outro.
    put_plan(client, auth, "2025-12", 9000, spend=50)
    stranger = client.post("/api/budgets", headers=other_user["headers"], json={
        "category_id": mine["Moradia"]["id"], "month": "2025-12", "planned_percent": 10,
    })
    assert stranger.status_code == 400
    mine_item = item(get_plan(client, auth, "2025-12"), "Lazer")
    assert client.patch(
        f"/api/budgets/{mine_item['id']}", headers=other_user["headers"], json={"planned_percent": 1},
    ).status_code == 404
    assert client.get(
        f"/api/budgets/{mine_item['id']}/lines", headers=other_user["headers"],
    ).status_code == 404
    assert get_plan(client, other_user["headers"], "2025-12")["plan"]["source_month"] == "2025-11"
