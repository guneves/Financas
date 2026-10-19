"""Os lancamentos por tras do realizado (GET /api/budgets/<id>/lines).

O que estes testes fixam:

- a soma de `amount` das linhas e sempre o `spent` que a tela mostra — as
  linhas e o total saem da mesma lista (`budget_month_lines()`);
- entram as subcategorias sem orcamento proprio, e saem as que tem;
- TRANSFER, pagamento de fatura e outros meses ficam de fora;
- uma compra parcelada e uma linha so, com o valor inteiro; um estorno
  subtrai;
- numa despesa dividida, a linha traz a parte do dono e o valor cheio;
- o orcamento de outro usuario nao abre.
"""

import pytest


def categories_of(client, headers):
    return {item["name"]: item for item in client.get("/api/categories", headers=headers).get_json()}


def create_budget(client, headers, category_id, month, planned_percent=10):
    response = client.post(
        "/api/budgets",
        headers=headers,
        json={"category_id": category_id, "month": month, "planned_percent": planned_percent},
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def add_entry(client, headers, amount, date, category, category_id=None, kind="EXPENSE", description="teste"):
    payload = {"amount": amount, "date": date, "category": category, "type": kind, "description": description}
    if category_id:
        payload["category_id"] = category_id
    response = client.post("/api/transactions", json=payload, headers=headers)
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    return response.get_json()


def create_card(client, headers):
    response = client.post(
        "/api/credit-cards", headers=headers, json={"name": "Cartao", "due_day": 10, "closing_day": 3},
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def card_purchase(client, headers, card, total, date, category, installments=1):
    response = client.post(
        "/api/cc-expenses/purchases",
        headers=headers,
        json={
            "card_id": card["id"], "category": category, "description": "Mercado",
            "total_amount": total, "purchase_date": date, "installments": installments,
        },
    )
    assert response.status_code == 201, response.get_data(as_text=True)


def lines_of(client, headers, budget_id):
    response = client.get(f"/api/budgets/{budget_id}/lines", headers=headers)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def screen_spent(client, headers, month, budget_id):
    body = client.get("/api/budgets", headers=headers, query_string={"month": month}).get_json()
    return next(item for item in body["items"] if item["id"] == budget_id)["spent"]


def assert_lines_add_up(client, headers, month, budget_id):
    body = lines_of(client, headers, budget_id)
    total = round(sum(line["amount"] for line in body["lines"]), 2)
    assert total == pytest.approx(body["spent"])
    assert body["spent"] == screen_spent(client, headers, month, budget_id)
    return body


def test_lines_are_the_month_expenses_of_the_category(client, auth):
    cats = categories_of(client, auth)
    budget = create_budget(client, auth, cats["Alimentação"]["id"], "2026-09")
    add_entry(client, auth, 50, "2026-09-02", "Alimentação", cats["Alimentação"]["id"], description="Padaria")
    add_entry(client, auth, 30.10, "2026-09-15", "Alimentação", description="Feira")  # so o nome
    add_entry(client, auth, 99, "2026-08-31", "Alimentação", cats["Alimentação"]["id"])  # outro mes
    add_entry(client, auth, 77, "2026-09-03", "Moradia", cats["Moradia"]["id"])  # outra categoria

    body = assert_lines_add_up(client, auth, "2026-09", budget["id"])
    assert [line["description"] for line in body["lines"]] == ["Padaria", "Feira"]
    assert body["spent"] == 80.10
    assert all(line["source"] == "TRANSACTION" for line in body["lines"])


def test_invoice_payments_and_transfers_are_not_lines(client, auth):
    import importlib

    cats = categories_of(client, auth)
    budget = create_budget(client, auth, cats["Moradia"]["id"], "2026-09")
    add_entry(client, auth, 300, "2026-09-10", "Moradia", cats["Moradia"]["id"], description="Aluguel")
    payment = add_entry(client, auth, 900, "2026-09-10", "Moradia", cats["Moradia"]["id"])
    with importlib.import_module("db").get_db() as conn:
        conn.execute(
            "UPDATE transactions SET source_type = 'CC_INVOICE_PAYMENT', source_id = 'x:2026-09' WHERE id = ?",
            (payment["id"],),
        )

    body = assert_lines_add_up(client, auth, "2026-09", budget["id"])
    assert [line["description"] for line in body["lines"]] == ["Aluguel"]


def test_a_card_purchase_is_one_line_with_every_installment(client, auth):
    cats = categories_of(client, auth)
    budget = create_budget(client, auth, cats["Alimentação"]["id"], "2026-09")
    card = create_card(client, auth)
    card_purchase(client, auth, card, 600, "2026-09-28", "Alimentação", installments=3)
    refund = client.post("/api/cc-expenses/refunds", headers=auth, json={
        "card_id": card["id"], "amount": 100, "purchase_date": "2026-09-29",
        "description": "Estorno · Mercado", "category": "Alimentação",
    })
    assert refund.status_code == 201, refund.get_data(as_text=True)

    body = assert_lines_add_up(client, auth, "2026-09", budget["id"])
    purchase, credit = body["lines"]
    assert purchase["source"] == "CARD"
    assert purchase["amount"] == 600
    assert purchase["installments"] == 3
    assert purchase["card_name"] == "Cartao"
    assert credit["refund"] is True
    assert credit["amount"] == -100
    assert body["spent"] == 500


def test_a_subcategory_counts_until_it_has_its_own_budget(client, auth):
    cats = categories_of(client, auth)
    parent = cats["Alimentação"]
    child = client.post(
        "/api/categories", headers=auth,
        json={"name": "Delivery", "kind": "EXPENSE", "parent_id": parent["id"]},
    ).get_json()
    budget = create_budget(client, auth, parent["id"], "2026-09")
    add_entry(client, auth, 40, "2026-09-05", "Delivery", child["id"], description="iFood")

    body = assert_lines_add_up(client, auth, "2026-09", budget["id"])
    assert [line["subcategory"] for line in body["lines"]] == [True]

    create_budget(client, auth, child["id"], "2026-09", 5)
    assert lines_of(client, auth, budget["id"])["lines"] == []


def test_a_split_expense_shows_the_owners_part(client, auth):
    cats = categories_of(client, auth)
    budget = create_budget(client, auth, cats["Alimentação"]["id"], "2026-09")
    item = add_entry(client, auth, 100, "2026-09-05", "Alimentação", cats["Alimentação"]["id"])
    response = client.patch(f"/api/transactions/{item['id']}", headers=auth, json={
        "share_mode": "SPLIT", "share_others_amount": 40, "share_person": "Ana",
    })
    assert response.status_code == 200, response.get_data(as_text=True)

    (line,) = assert_lines_add_up(client, auth, "2026-09", budget["id"])["lines"]
    assert line["amount"] == 60
    assert line["total_amount"] == 100
    assert line["shared"] is True


def test_an_income_category_lists_income(client, auth):
    cats = categories_of(client, auth)
    income = next(cat for cat in cats.values() if cat["kind"] == "INCOME")
    budget = create_budget(client, auth, income["id"], "2026-09")
    add_entry(client, auth, 5000, "2026-09-05", income["name"], income["id"], kind="INCOME", description="Salario")
    add_entry(client, auth, 10, "2026-09-06", income["name"], income["id"], description="Tarifa")

    body = assert_lines_add_up(client, auth, "2026-09", budget["id"])
    assert [line["description"] for line in body["lines"]] == ["Salario"]


def test_another_users_budget_does_not_open(client, user, other_user):
    cats = categories_of(client, user["headers"])
    budget = create_budget(client, user["headers"], cats["Alimentação"]["id"], "2026-09")
    response = client.get(f"/api/budgets/{budget['id']}/lines", headers=other_user["headers"])
    assert response.status_code == 404


def test_lines_require_auth(client):
    assert client.get("/api/budgets/x/lines").status_code == 401


def test_an_inherited_month_opens_its_own_lines(client, auth):
    """Outubro herda a linha de setembro: `?month=` abre os lancamentos de outubro."""
    cats = categories_of(client, auth)
    budget = create_budget(client, auth, cats["Alimentação"]["id"], "2026-09")
    add_entry(client, auth, 30, "2026-09-05", "Alimentação", cats["Alimentação"]["id"], description="setembro")
    add_entry(client, auth, 45, "2026-10-05", "Alimentação", cats["Alimentação"]["id"], description="outubro")

    response = client.get(f"/api/budgets/{budget['id']}/lines", headers=auth, query_string={"month": "2026-10"})
    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert body["month"] == "2026-10"
    assert [line["description"] for line in body["lines"]] == ["outubro"]
    assert body["spent"] == screen_spent(client, auth, "2026-10", budget["id"]) == 45
    # Antes da linha ela nao vale.
    early = client.get(f"/api/budgets/{budget['id']}/lines", headers=auth, query_string={"month": "2026-08"})
    assert early.status_code == 404
