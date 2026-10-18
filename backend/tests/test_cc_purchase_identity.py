"""Cada compra no cartao e uma compra: o client_id (035).

A compra era a chave cartao + descricao + data + categoria, e duas corridas de
Uber iguais no mesmo dia viravam uma. O que estes testes fixam:

- toda compra tem um client_id, o mesmo em todas as parcelas — o do envio, ou
  um gerado quando o cliente nao manda;
- dividir uma corrida nao divide a outra, e A receber mostra duas;
- as parcelas de uma compra (/candidates?id=) nao trazem a outra: excluir uma
  deixa a outra;
- o comprovante de uma nao aparece na outra;
- o orcamento mostra duas linhas;
- a migration 035 da um client_id as compras antigas, separando as identicas
  pela ordem em que foram gravadas, e o id da categoria a cada linha.
"""

import io
import os
import sqlite3
import uuid

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(os.path.dirname(BACKEND_DIR), "database", "migrations")
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def create_card(client, headers):
    response = client.post(
        "/api/credit-cards", headers=headers, json={"name": f"Cartao {uuid.uuid4().hex[:6]}", "due_day": 10, "closing_day": 3},
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["id"]


def ride(client, headers, card_id, **extra):
    payload = {
        "card_id": card_id, "category": "Transporte", "description": "Uber", "total_amount": 10,
        "purchase_date": "2026-03-10", "installments": 1, **extra,
    }
    response = client.post("/api/cc-expenses/purchases", headers=headers, json=payload)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def card_rows(client, headers):
    return client.get("/api/cc-expenses", headers=headers).get_json()


def candidates(client, headers, expense_id):
    response = client.get("/api/cc-expenses/candidates", headers=headers, query_string={"id": expense_id})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


@pytest.fixture()
def two_rides(client, auth):
    card_id = create_card(client, auth)
    # Uma pelo "+ Novo" (com client_id), outra sem: as duas viram compras.
    [first] = ride(client, auth, card_id, client_id=str(uuid.uuid4()))
    [second] = ride(client, auth, card_id)
    return first, second


class TestTwoIdenticalRides:
    def test_each_ride_has_its_own_purchase_id(self, client, auth, two_rides):
        first, second = two_rides
        assert first["client_id"] and second["client_id"]
        assert first["client_id"] != second["client_id"]
        assert [row["id"] for row in candidates(client, auth, first["id"])] == [first["id"]]

    def test_sharing_one_ride_leaves_the_other(self, client, auth, two_rides):
        first, second = two_rides
        response = client.patch(f"/api/cc-expenses/{first['id']}/share", headers=auth, json={
            "share_mode": "SPLIT", "share_others_amount": 5, "share_person": "Ana",
        })
        assert response.status_code == 200, response.get_data(as_text=True)
        rows = {row["id"]: row for row in card_rows(client, auth)}
        assert (rows[first["id"]]["share_mode"], rows[first["id"]]["share_others_amount"]) == ("SPLIT", 5)
        assert rows[second["id"]]["share_mode"] is None

    def test_a_receber_lists_both_rides(self, client, auth, two_rides):
        for row, person in zip(two_rides, ("Ana", "Bruno")):
            client.patch(f"/api/cc-expenses/{row['id']}/share", headers=auth, json={"share_mode": "OTHERS", "share_person": person})
        items = client.get("/api/receivables", headers=auth).get_json()
        assert sorted((item["person"], item["others_amount"]) for item in items) == [("Ana", 10), ("Bruno", 10)]

    def test_deleting_one_ride_keeps_the_other(self, client, auth, two_rides):
        first, second = two_rides
        ids = [row["id"] for row in candidates(client, auth, first["id"])]
        assert client.delete("/api/cc-expenses", headers=auth, json={"ids": ids}).status_code == 200
        assert [row["id"] for row in card_rows(client, auth)] == [second["id"]]

    def test_a_receipt_belongs_to_one_ride(self, client, auth, two_rides):
        first, second = two_rides
        uploaded = client.post(
            f"/api/cc-expenses/{first['id']}/attachments", headers=auth,
            data={"file": (io.BytesIO(PDF), "recibo.pdf")}, content_type="multipart/form-data",
        )
        assert uploaded.status_code == 201, uploaded.get_data(as_text=True)
        assert client.get(f"/api/cc-expenses/{second['id']}/attachments", headers=auth).get_json() == []
        counts = {row["id"]: row["attachment_count"] for row in card_rows(client, auth)}
        assert counts == {first["id"]: 1, second["id"]: 0}

    def test_the_budget_shows_two_lines(self, client, auth, two_rides):
        transporte = next(item for item in client.get("/api/categories", headers=auth).get_json() if item["name"] == "Transporte")
        budget = client.post("/api/budgets", headers=auth, json={
            "category_id": transporte["id"], "month": "2026-03", "planned_amount": 100,
        }).get_json()
        lines = client.get(f"/api/budgets/{budget['id']}/lines", headers=auth).get_json()["lines"]
        assert [line["amount"] for line in lines] == [10, 10]


def test_all_installments_of_a_purchase_come_together(client, auth):
    card_id = create_card(client, auth)
    created = ride(client, auth, card_id, total_amount=100, installments=3, description="Geladeira")
    assert len({row["client_id"] for row in created}) == 1
    assert sorted(row["id"] for row in candidates(client, auth, created[-1]["id"])) == sorted(row["id"] for row in created)


def test_another_users_purchase_has_no_installments_here(client, auth, other_user):
    [row] = ride(client, auth, create_card(client, auth))
    assert candidates(client, other_user["headers"], row["id"]) == []


# --------------------------------------------------------------------------
# A migration 035 sobre compras anteriores a ela
# --------------------------------------------------------------------------

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


def apply_035(conn):
    [filename] = [name for name in os.listdir(MIGRATIONS_DIR) if name.startswith("035_")]
    with open(os.path.join(MIGRATIONS_DIR, filename), encoding="utf-8") as file:
        conn.executescript(file.read())


def test_035_gives_old_purchases_an_id_and_separates_identical_ones(tmp_path):
    conn = migrated_up_to(str(tmp_path / "old.db"), "034")
    conn.execute("INSERT INTO users (id, email, password_hash) VALUES ('u1', 'a@b.c', 'x')")
    conn.execute("INSERT INTO credit_cards (id, user_id, name, due_day, closing_day) VALUES ('c1', 'u1', 'Nubank', 10, 3)")
    conn.executescript("""
        INSERT INTO categories (id, user_id, name, kind, parent_id, created_at) VALUES
            ('outros', 'u1', 'Outros', 'EXPENSE', NULL, '2026-01-01T00:00:00Z'),
            ('lazer', 'u1', 'Lazer', 'EXPENSE', NULL, '2026-01-01T00:00:00Z'),
            ('lazer-outros', 'u1', 'Outros', 'EXPENSE', 'lazer', '2026-02-01T00:00:00Z'),
            ('transporte', 'u1', 'Transporte', 'EXPENSE', NULL, '2026-01-01T00:00:00Z');
    """)
    rows = [
        # Duas corridas identicas.
        ("r1", "Uber", "Transporte", "1/1", "2026-03-10T10:00:00Z", None),
        ("r2", "Uber", "Transporte", "1/1", "2026-03-10T18:00:00Z", None),
        # Duas compras identicas em 2x, gravadas uma depois da outra.
        ("a1", "Tenis", "Outros", "1/2", "2026-03-11T10:00:00.001Z", None),
        ("a2", "Tenis", "Outros", "2/2", "2026-03-11T10:00:00.002Z", None),
        ("b1", "Tenis", "Outros", "1/2", "2026-03-11T12:00:00.001Z", None),
        ("b2", "Tenis", "Outros", "2/2", "2026-03-11T12:00:00.002Z", None),
        # Ja tinha client_id (024): fica como esta.
        ("n1", "Mercado", "Sem categoria cadastrada", "1/1", "2026-03-12T10:00:00Z", "envio-do-celular"),
    ]
    for row_id, description, category, installment, created_at, client_id in rows:
        conn.execute(
            """
            INSERT INTO cc_expenses (id, user_id, card_id, category, description, amount, purchase_date,
                                     invoice_month, invoice_year, installment_info, created_at, client_id)
            VALUES (?, 'u1', 'c1', ?, ?, 10, '2026-03-10', 4, 2026, ?, ?, ?)
            """,
            (row_id, category, description, installment, created_at, client_id),
        )
    conn.commit()

    apply_035(conn)

    found = {row["id"]: row for row in conn.execute("SELECT id, client_id, category_id FROM cc_expenses")}
    assert found["r1"]["client_id"] != found["r2"]["client_id"]
    assert found["a1"]["client_id"] == found["a2"]["client_id"]
    assert found["b1"]["client_id"] == found["b2"]["client_id"]
    assert found["a1"]["client_id"] != found["b1"]["client_id"]
    assert all(found[key]["client_id"].startswith("legacy:") for key in ("r1", "r2", "a1", "b1"))
    assert found["n1"]["client_id"] == "envio-do-celular"
    # A categoria pelo nome, como o orcamento ja lia: a raiz antes.
    assert found["r1"]["category_id"] == "transporte"
    assert found["a1"]["category_id"] == "outros"
    assert found["n1"]["category_id"] is None
    conn.close()


def test_the_running_database_has_035(db_module):
    with db_module.get_db() as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(cc_expenses)").fetchall()}
        applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()}
    assert "category_id" in columns
    assert "035" in applied


def test_a_purchase_from_the_old_endpoint_still_finds_its_installments(client, auth):
    """O POST antigo de /api/cc-expenses nao da client_id: a chave antiga vale."""
    card_id = create_card(client, auth)
    base = {"card_id": card_id, "category": "Casa", "description": "Sofa", "amount": 50, "purchase_date": "2026-03-10"}
    response = client.post("/api/cc-expenses", headers=auth, json=[
        {**base, "invoice_month": 4, "invoice_year": 2026, "installment_info": "1/2"},
        {**base, "invoice_month": 5, "invoice_year": 2026, "installment_info": "2/2"},
    ])
    assert response.status_code == 201, response.get_data(as_text=True)
    created = response.get_json()
    assert all(row["client_id"] is None for row in created)
    assert sorted(row["id"] for row in candidates(client, auth, created[0]["id"])) == sorted(row["id"] for row in created)
