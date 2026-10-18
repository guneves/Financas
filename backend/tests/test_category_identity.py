"""A categoria e o id, nao o nome (035).

O mesmo nome existe em mais de um lugar: o "Outros" da raiz, "Alimentação ›
Outros" e "Lazer › Outros". O que estes testes fixam:

- uma compra no cartao guarda o id da categoria, e o orcamento a conta nela —
  a compra em "Lazer › Outros" nao pesa no "Outros" da raiz;
- editar so a descricao (a tela antiga mandava o nome de volta) nao muda a
  categoria do lancamento;
- so com o nome, vale a raiz (a unica com aquele nome no topo);
- a regra, Aprovar e o estorno andam pelo id;
- renomear a categoria leva o nome novo a tudo o que e dela — lancamentos,
  compras no cartao, recorrencias, regras e itens de Aprovar — e o orcamento
  continua somando o mesmo.
"""

import importlib
import uuid

MONTH = "2026-03"


def categories(client, headers):
    response = client.get("/api/categories", headers=headers)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def root(client, headers, name):
    return next(item for item in categories(client, headers) if item["name"] == name and not item["parent_id"])


def create_category(client, headers, name, parent_id=None):
    payload = {"name": name, "kind": "EXPENSE"}
    if parent_id:
        payload["parent_id"] = parent_id
    response = client.post("/api/categories", json=payload, headers=headers)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def three_outros(client, headers):
    """O "Outros" da raiz (semeado), "Alimentação › Outros" e "Lazer › Outros"."""
    return {
        "raiz": root(client, headers, "Outros")["id"],
        "alimentacao": create_category(client, headers, "Outros", root(client, headers, "Alimentação")["id"])["id"],
        "lazer": create_category(client, headers, "Outros", root(client, headers, "Lazer")["id"])["id"],
    }


def create_budget(client, headers, category_id, planned=500, month=MONTH):
    response = client.post(
        "/api/budgets", headers=headers,
        json={"category_id": category_id, "month": month, "planned_amount": planned},
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def spent(client, headers, category_id, month=MONTH):
    body = client.get("/api/budgets", headers=headers, query_string={"month": month}).get_json()
    return next(item for item in body["items"] if item["category_id"] == category_id)["spent"]


def create_card(client, headers):
    response = client.post(
        "/api/credit-cards", headers=headers, json={"name": f"Cartao {uuid.uuid4().hex[:6]}", "due_day": 10, "closing_day": 3},
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["id"]


def purchase(client, headers, card_id, total=100, **category):
    response = client.post("/api/cc-expenses/purchases", headers=headers, json={
        "card_id": card_id, "description": "Cinema", "total_amount": total,
        "purchase_date": f"{MONTH}-12", "installments": 1, **category,
    })
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def expense(client, headers, amount=50, description="Feira", **category):
    response = client.post("/api/transactions", headers=headers, json={
        "amount": amount, "date": f"{MONTH}-05", "type": "EXPENSE", "description": description, **category,
    })
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


class TestByIdNotByName:
    def test_a_card_purchase_in_a_subcategory_counts_in_its_own_budget(self, client, auth):
        outros = three_outros(client, auth)
        create_budget(client, auth, outros["raiz"])
        create_budget(client, auth, outros["lazer"])
        [row] = purchase(client, auth, create_card(client, auth), category_id=outros["lazer"])
        assert (row["category"], row["category_id"]) == ("Outros", outros["lazer"])
        assert spent(client, auth, outros["lazer"]) == 100
        assert spent(client, auth, outros["raiz"]) == 0

    def test_editing_only_the_description_keeps_the_subcategory(self, client, auth):
        outros = three_outros(client, auth)
        item = expense(client, auth, category_id=outros["alimentacao"])
        # A tela antiga mandava o nome de volta junto com a descricao.
        response = client.patch(
            f"/api/transactions/{item['id']}", headers=auth, json={"description": "Feira livre", "category": "Outros"},
        )
        assert response.status_code == 200, response.get_data(as_text=True)
        assert response.get_json()["category_id"] == outros["alimentacao"]
        moved = client.patch(f"/api/transactions/{item['id']}", headers=auth, json={"category_id": outros["raiz"]})
        assert moved.get_json()["category_id"] == outros["raiz"]

    def test_a_name_alone_is_the_root_one(self, client, auth):
        outros = three_outros(client, auth)
        assert expense(client, auth, category="Outros")["category_id"] == outros["raiz"]
        [row] = purchase(client, auth, create_card(client, auth), category="Outros")
        assert row["category_id"] == outros["raiz"]

    def test_a_rule_to_lazer_outros_moves_a_root_outros_lancamento(self, client, auth):
        outros = three_outros(client, auth)
        item = expense(client, auth, description="Cinema do shopping", category_id=outros["raiz"])
        rule = client.post("/api/import-rules", headers=auth, json={"pattern": "cinema", "category_id": outros["lazer"]})
        assert rule.status_code == 201, rule.get_data(as_text=True)
        assert rule.get_json()["category_id"] == outros["lazer"]
        # Mesmo nome, outra categoria: e candidata (pelo nome, "Outros" == "Outros").
        preview = client.post("/api/import-rules/apply/preview", headers=auth, json={}).get_json()
        assert [entry["id"] for entry in preview["items"]] == [item["id"]]
        client.post("/api/import-rules/apply", headers=auth, json={"transaction_ids": [item["id"]]})
        [row] = client.get("/api/transactions", headers=auth).get_json()
        assert row["category_id"] == outros["lazer"]

    def test_an_import_keeps_the_chosen_subcategory(self, client, auth):
        outros = three_outros(client, auth)
        response = client.post("/api/import/commit", headers=auth, json={"rows": [{
            "date": f"{MONTH}-07", "amount": 30, "type": "EXPENSE", "description": "Pipoca",
            "category": "Outros", "category_id": outros["lazer"],
        }]})
        assert response.status_code == 201, response.get_data(as_text=True)
        [row] = client.get("/api/transactions", headers=auth).get_json()
        assert row["category_id"] == outros["lazer"]

    def test_a_refund_nets_the_category_of_the_purchase(self, client, auth):
        outros = three_outros(client, auth)
        create_budget(client, auth, outros["lazer"])
        card_id = create_card(client, auth)
        [row] = purchase(client, auth, card_id, category_id=outros["lazer"])
        refund = client.post("/api/cc-expenses/refunds", headers=auth, json={
            "card_id": card_id, "amount": 40, "purchase_date": f"{MONTH}-14", "description": "Estorno · Cinema",
            "category": "Outros", "refund_of": row["id"], "client_id": str(uuid.uuid4()),
        })
        assert refund.status_code == 201, refund.get_data(as_text=True)
        assert refund.get_json()["category_id"] == outros["lazer"]
        assert spent(client, auth, outros["lazer"]) == 60

    def test_aprovar_keeps_the_subcategory_on_the_card_purchase(self, client, auth):
        outros = three_outros(client, auth)
        create_budget(client, auth, outros["lazer"])
        create_card(client, auth)
        detections = [{
            "key": uuid.uuid4().hex + uuid.uuid4().hex, "app": "com.itau", "kind": "CREDIT_PURCHASE",
            "amount_cents": 2500, "posted_ms": 1773326400000, "utc_offset_minutes": -180, "merchant": "CINEMARK",
        }]
        assert client.post("/api/inbox/detections", headers=auth, json={"detections": detections}).status_code == 200
        [item] = client.get("/api/inbox", headers=auth).get_json()["items"]
        item = client.patch(
            f"/api/inbox/{item['id']}", headers=auth, json={"version": item["version"], "category_id": outros["lazer"]},
        ).get_json()
        assert (item["category"], item["category_id"]) == ("Outros", outros["lazer"])
        # O nome de volta (tela antiga) nao troca a categoria do rascunho.
        item = client.patch(
            f"/api/inbox/{item['id']}", headers=auth, json={"version": item["version"], "category": "Outros"},
        ).get_json()
        assert item["category_id"] == outros["lazer"]
        approved = client.post(f"/api/inbox/{item['id']}/approve", headers=auth, json={"version": item["version"]})
        assert approved.status_code == 200, approved.get_data(as_text=True)
        [row] = client.get("/api/cc-expenses", headers=auth).get_json()
        assert row["category_id"] == outros["lazer"]
        assert spent(client, auth, outros["lazer"]) == 25


class TestRename:
    def test_card_purchases_follow_the_rename_and_the_budget_keeps_its_spent(self, client, auth):
        mercado = create_category(client, auth, "Mercado")["id"]
        create_budget(client, auth, mercado)
        expense(client, auth, amount=50, category_id=mercado)
        purchase(client, auth, create_card(client, auth), total=100, category_id=mercado)
        assert spent(client, auth, mercado) == 150

        response = client.patch(f"/api/categories/{mercado}", headers=auth, json={"name": "Supermercado"})
        assert response.status_code == 200, response.get_data(as_text=True)
        assert spent(client, auth, mercado) == 150
        [row] = client.get("/api/cc-expenses", headers=auth).get_json()
        assert (row["category"], row["category_id"]) == ("Supermercado", mercado)
        assert client.get("/api/transactions", headers=auth).get_json()[0]["category"] == "Supermercado"

    def test_recurrences_rules_and_aprovar_follow_the_rename(self, client, auth):
        mercado = create_category(client, auth, "Mercado")["id"]
        recurrence = client.post("/api/recurring", headers=auth, json={
            "amount": 300, "type": "EXPENSE", "category_id": mercado, "description": "Feira do mes",
            "frequency": "MONTHLY", "start_date": "2026-01-10",
        })
        assert recurrence.status_code == 201, recurrence.get_data(as_text=True)
        rule = client.post("/api/import-rules", headers=auth, json={"pattern": "hortifruti", "category_id": mercado})
        assert rule.status_code == 201, rule.get_data(as_text=True)
        create_card(client, auth)
        detections = [{
            "key": uuid.uuid4().hex + uuid.uuid4().hex, "app": "com.itau", "kind": "CREDIT_PURCHASE",
            "amount_cents": 4590, "posted_ms": 1773326400000, "utc_offset_minutes": -180, "merchant": "HORTIFRUTI",
        }]
        client.post("/api/inbox/detections", headers=auth, json={"detections": detections})
        [item] = client.get("/api/inbox", headers=auth).get_json()["items"]
        assert item["category_id"] == mercado

        client.patch(f"/api/categories/{mercado}", headers=auth, json={"name": "Supermercado"})

        recurring = client.get("/api/recurring", headers=auth).get_json()
        recurring_items = recurring["items"] if isinstance(recurring, dict) else recurring
        assert [entry["category"] for entry in recurring_items] == ["Supermercado"]
        assert [entry["category"] for entry in client.get("/api/import-rules", headers=auth).get_json()["items"]] == ["Supermercado"]
        assert client.get("/api/inbox", headers=auth).get_json()["items"][0]["category"] == "Supermercado"

    def test_a_row_with_only_the_old_name_keeps_counting_where_it_counted(self, client, auth, user):
        mercado = create_category(client, auth, "Mercado")["id"]
        create_budget(client, auth, mercado)
        db = importlib.import_module("db")
        with db.get_db() as conn:
            # Uma linha antiga so com o texto (a conta padrao nasce no cadastro):
            # o orcamento a conta pelo nome.
            conn.execute(
                "INSERT INTO transactions (id, user_id, account_id, amount, date, category, category_id, type)"
                " SELECT ?, ?, id, 70, ?, 'Mercado', NULL, 'EXPENSE' FROM accounts WHERE user_id = ? LIMIT 1",
                (str(uuid.uuid4()), user["id"], f"{MONTH}-09", user["id"]),
            )
        assert spent(client, auth, mercado) == 70
        client.patch(f"/api/categories/{mercado}", headers=auth, json={"name": "Supermercado"})
        assert spent(client, auth, mercado) == 70
        rows = [row for row in client.get("/api/transactions", headers=auth).get_json() if row["amount"] == 70]
        assert [(row["category"], row["category_id"]) for row in rows] == [("Supermercado", mercado)]

    def test_renaming_a_subcategory_leaves_rows_named_after_the_root(self, client, auth, user):
        outros = three_outros(client, auth)
        db = importlib.import_module("db")
        with db.get_db() as conn:
            conn.execute(
                "INSERT INTO transactions (id, user_id, account_id, amount, date, category, category_id, type)"
                " SELECT ?, ?, id, 20, ?, 'Outros', NULL, 'EXPENSE' FROM accounts WHERE user_id = ? LIMIT 1",
                (str(uuid.uuid4()), user["id"], f"{MONTH}-09", user["id"]),
            )
        # "Outros" sem id e o da raiz: renomear "Lazer › Outros" nao o leva.
        client.patch(f"/api/categories/{outros['lazer']}", headers=auth, json={"name": "Passeios"})
        rows = [row for row in client.get("/api/transactions", headers=auth).get_json() if row["amount"] == 20]
        assert [(row["category"], row["category_id"]) for row in rows] == [("Outros", None)]
