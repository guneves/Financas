"""Orcamento mensal por categoria — secao 3.3 de docs/next-steps.md.

O que estes testes fixam:

- o realizado vem de `transactions` do mes, ignorando TRANSFER (mover dinheiro
  entre contas proprias nao e gasto);
- uma categoria INCOME realiza receita, as demais realizam despesa;
- subcategoria sem orcamento proprio soma no orcamento do pai — mas para de
  somar assim que ganha o seu;
- `rollover` transporta a sobra do mes anterior, e so a sobra (estouro nao vira
  divida do mes seguinte);
- tudo passa por `rounded_money()`;
- nenhum orcamento de outro usuario aparece, nem pode ser lido ou editado.
"""

import pytest


def get_month(client, headers, month):
    response = client.get("/api/budgets", headers=headers, query_string={"month": month})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def categories_of(client, headers):
    response = client.get("/api/categories", headers=headers)
    assert response.status_code == 200
    return {item["name"]: item for item in response.get_json()}


def create_budget(client, headers, category_id, month, planned_amount, **extra):
    payload = {"category_id": category_id, "month": month, "planned_amount": planned_amount}
    payload.update(extra)
    return client.post("/api/budgets", json=payload, headers=headers)


def add_expense(client, headers, amount, date, category, category_id=None):
    payload = {
        "amount": amount,
        "date": date,
        "category": category,
        "type": "EXPENSE",
        "description": "teste",
    }
    if category_id:
        payload["category_id"] = category_id
    response = client.post("/api/transactions", json=payload, headers=headers)
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    return response.get_json()


def item_for(month_body, category_name):
    return next(item for item in month_body["items"] if item["category_name"] == category_name)


# --- criacao e validacao ----------------------------------------------------


def test_month_starts_empty(client, auth):
    body = get_month(client, auth, "2026-09")
    assert body["month"] == "2026-09"
    assert body["items"] == []
    assert body["totals"]["planned"] == 0
    assert body["totals"]["over_count"] == 0


def test_create_budget_returns_the_computed_item(client, auth):
    alimentacao = categories_of(client, auth)["Alimentação"]
    response = create_budget(client, auth, alimentacao["id"], "2026-09", 1200)
    assert response.status_code == 201, response.get_data(as_text=True)
    body = response.get_json()
    assert body["planned_amount"] == 1200
    assert body["available"] == 1200
    assert body["spent"] == 0
    assert body["remaining"] == 1200
    assert body["rollover"] is False
    assert body["status"] == "OK"


def test_same_category_twice_in_a_month_is_refused(client, auth):
    lazer = categories_of(client, auth)["Lazer"]
    assert create_budget(client, auth, lazer["id"], "2026-09", 300).status_code == 201
    duplicate = create_budget(client, auth, lazer["id"], "2026-09", 400)
    assert duplicate.status_code == 409


def test_same_category_in_another_month_is_fine(client, auth):
    lazer = categories_of(client, auth)["Lazer"]
    assert create_budget(client, auth, lazer["id"], "2026-09", 300).status_code == 201
    assert create_budget(client, auth, lazer["id"], "2026-10", 400).status_code == 201


@pytest.mark.parametrize(
    "payload",
    [
        {"month": "2026-09", "planned_amount": 100},
        {"category_id": "nao-existe", "month": "2026-09", "planned_amount": 100},
        {"category_id": "x", "month": "2026-9", "planned_amount": 100},
        {"category_id": "x", "month": "setembro", "planned_amount": 100},
        {"category_id": "x", "month": "2026-09"},
        {"category_id": "x", "month": "2026-09", "planned_amount": -10},
        {"category_id": "x", "month": "2026-09", "planned_amount": "muito"},
    ],
)
def test_invalid_payloads_are_refused(client, auth, payload):
    if payload.get("category_id") == "x":
        payload["category_id"] = categories_of(client, auth)["Outros"]["id"]
    response = client.post("/api/budgets", json=payload, headers=auth)
    assert response.status_code in (400, 404, 409)


def test_archived_category_cannot_be_budgeted(client, auth):
    created = client.post(
        "/api/categories", json={"name": "Temporaria", "kind": "EXPENSE"}, headers=auth
    ).get_json()
    assert client.delete(f"/api/categories/{created['id']}", headers=auth).status_code == 200
    response = create_budget(client, auth, created["id"], "2026-09", 100)
    assert response.status_code == 400


def test_invalid_month_on_get_is_refused(client, auth):
    response = client.get("/api/budgets", headers=auth, query_string={"month": "2026/09"})
    assert response.status_code == 400


def test_budgets_require_auth(client):
    assert client.get("/api/budgets").status_code == 401
    assert client.post("/api/budgets", json={}).status_code == 401


# --- realizado --------------------------------------------------------------


def test_spent_comes_from_the_month_transactions(client, auth):
    alimentacao = categories_of(client, auth)["Alimentação"]
    create_budget(client, auth, alimentacao["id"], "2026-09", 1000)
    add_expense(client, auth, 250.50, "2026-09-03", "Alimentação", alimentacao["id"])
    add_expense(client, auth, 99.50, "2026-09-20", "Alimentação", alimentacao["id"])

    item = item_for(get_month(client, auth, "2026-09"), "Alimentação")
    assert item["spent"] == 350
    assert item["remaining"] == 650
    assert item["percent"] == 35


def test_other_months_do_not_count(client, auth):
    alimentacao = categories_of(client, auth)["Alimentação"]
    create_budget(client, auth, alimentacao["id"], "2026-09", 1000)
    add_expense(client, auth, 400, "2026-08-31", "Alimentação", alimentacao["id"])
    add_expense(client, auth, 400, "2026-10-01", "Alimentação", alimentacao["id"])

    assert item_for(get_month(client, auth, "2026-09"), "Alimentação")["spent"] == 0


def test_free_text_category_counts_by_name(client, auth):
    """Lancamento sem category_id, so com o texto — o caso dos dados antigos."""
    alimentacao = categories_of(client, auth)["Alimentação"]
    create_budget(client, auth, alimentacao["id"], "2026-09", 500)
    add_expense(client, auth, 120, "2026-09-10", "Alimentação")

    assert item_for(get_month(client, auth, "2026-09"), "Alimentação")["spent"] == 120


def test_transfers_are_not_spending(client, auth):
    """A regra que o resto do app tambem tem que respeitar: TRANSFER nao e gasto."""
    accounts = client.get("/api/accounts", headers=auth).get_json()
    origin = accounts[0]["id"]
    destination = client.post(
        "/api/accounts", json={"name": "Reserva", "type": "SAVINGS"}, headers=auth
    ).get_json()["id"]

    outros = categories_of(client, auth)["Outros"]
    create_budget(client, auth, outros["id"], "2026-09", 1000)
    response = client.post(
        "/api/transfers",
        json={
            "account_id": origin,
            "transfer_account_id": destination,
            "amount": 700,
            "date": "2026-09-05",
            "category": "Outros",
            "description": "reserva do mes",
        },
        headers=auth,
    )
    assert response.status_code in (200, 201), response.get_data(as_text=True)

    assert item_for(get_month(client, auth, "2026-09"), "Outros")["spent"] == 0


def test_income_category_realizes_income_not_expense(client, auth):
    receita = categories_of(client, auth)["Receita"]
    create_budget(client, auth, receita["id"], "2026-09", 8000)
    response = client.post(
        "/api/transactions",
        json={
            "amount": 8000,
            "date": "2026-09-05",
            "category": "Receita",
            "category_id": receita["id"],
            "type": "INCOME",
            "description": "salario",
        },
        headers=auth,
    )
    assert response.status_code in (200, 201)

    item = item_for(get_month(client, auth, "2026-09"), "Receita")
    assert item["spent"] == 8000
    assert item["remaining"] == 0


def test_spending_is_rounded_half_up(client, auth):
    """Cada lancamento ja entra arredondado com ROUND_HALF_UP: 0.125 vira 0.13.

    Com banker's rounding cada um viraria 0.12 e o realizado do mes fecharia em
    0.24. O que o orcamento soma e o valor gravado, nao o digitado.
    """
    outros = categories_of(client, auth)["Outros"]
    create_budget(client, auth, outros["id"], "2026-09", 1)
    add_expense(client, auth, 0.125, "2026-09-02", "Outros", outros["id"])
    add_expense(client, auth, 0.125, "2026-09-03", "Outros", outros["id"])

    assert item_for(get_month(client, auth, "2026-09"), "Outros")["spent"] == 0.26


# --- subcategorias ----------------------------------------------------------


def test_subcategory_without_its_own_budget_rolls_up_to_the_parent(client, auth):
    alimentacao = categories_of(client, auth)["Alimentação"]
    delivery = client.post(
        "/api/categories",
        json={"name": "Delivery", "kind": "EXPENSE", "parent_id": alimentacao["id"]},
        headers=auth,
    ).get_json()

    create_budget(client, auth, alimentacao["id"], "2026-09", 900)
    add_expense(client, auth, 300, "2026-09-04", "Alimentação", alimentacao["id"])
    add_expense(client, auth, 200, "2026-09-11", "Delivery", delivery["id"])

    assert item_for(get_month(client, auth, "2026-09"), "Alimentação")["spent"] == 500


def test_subcategory_with_its_own_budget_stops_counting_on_the_parent(client, auth):
    alimentacao = categories_of(client, auth)["Alimentação"]
    delivery = client.post(
        "/api/categories",
        json={"name": "Delivery", "kind": "EXPENSE", "parent_id": alimentacao["id"]},
        headers=auth,
    ).get_json()

    create_budget(client, auth, alimentacao["id"], "2026-09", 900)
    create_budget(client, auth, delivery["id"], "2026-09", 250)
    add_expense(client, auth, 300, "2026-09-04", "Alimentação", alimentacao["id"])
    add_expense(client, auth, 200, "2026-09-11", "Delivery", delivery["id"])

    body = get_month(client, auth, "2026-09")
    assert item_for(body, "Alimentação")["spent"] == 300
    assert item_for(body, "Delivery")["spent"] == 200
    assert body["totals"]["spent"] == 500


# --- status e totais --------------------------------------------------------


def test_status_walks_ok_warning_over(client, auth):
    outros = categories_of(client, auth)["Outros"]
    create_budget(client, auth, outros["id"], "2026-09", 100)
    assert item_for(get_month(client, auth, "2026-09"), "Outros")["status"] == "OK"

    add_expense(client, auth, 85, "2026-09-02", "Outros", outros["id"])
    assert item_for(get_month(client, auth, "2026-09"), "Outros")["status"] == "WARNING"

    add_expense(client, auth, 30, "2026-09-03", "Outros", outros["id"])
    item = item_for(get_month(client, auth, "2026-09"), "Outros")
    assert item["status"] == "OVER"
    assert item["remaining"] == -15


def test_totals_add_up_and_count_the_overruns(client, auth):
    categories = categories_of(client, auth)
    create_budget(client, auth, categories["Alimentação"]["id"], "2026-09", 500)
    create_budget(client, auth, categories["Transporte"]["id"], "2026-09", 300)
    add_expense(client, auth, 600, "2026-09-07", "Alimentação", categories["Alimentação"]["id"])
    add_expense(client, auth, 100, "2026-09-08", "Transporte", categories["Transporte"]["id"])

    totals = get_month(client, auth, "2026-09")["totals"]
    assert totals["planned"] == 800
    assert totals["spent"] == 700
    assert totals["remaining"] == 100
    assert totals["over_count"] == 1


# --- rollover ---------------------------------------------------------------


def test_rollover_carries_the_leftover_forward(client, auth):
    lazer = categories_of(client, auth)["Lazer"]
    create_budget(client, auth, lazer["id"], "2026-08", 400)
    add_expense(client, auth, 150, "2026-08-10", "Lazer", lazer["id"])
    create_budget(client, auth, lazer["id"], "2026-09", 400, rollover=True)

    item = item_for(get_month(client, auth, "2026-09"), "Lazer")
    assert item["carryover"] == 250
    assert item["available"] == 650
    assert item["remaining"] == 650


def test_rollover_off_ignores_the_leftover(client, auth):
    lazer = categories_of(client, auth)["Lazer"]
    create_budget(client, auth, lazer["id"], "2026-08", 400)
    create_budget(client, auth, lazer["id"], "2026-09", 400)

    item = item_for(get_month(client, auth, "2026-09"), "Lazer")
    assert item["carryover"] == 0
    assert item["available"] == 400


def test_an_overrun_does_not_become_next_month_debt(client, auth):
    lazer = categories_of(client, auth)["Lazer"]
    create_budget(client, auth, lazer["id"], "2026-08", 400)
    add_expense(client, auth, 900, "2026-08-10", "Lazer", lazer["id"])
    create_budget(client, auth, lazer["id"], "2026-09", 400, rollover=True)

    item = item_for(get_month(client, auth, "2026-09"), "Lazer")
    assert item["carryover"] == 0
    assert item["available"] == 400


def test_rollover_uses_the_same_spent_the_screen_shows(client, auth):
    """A sobra transportada tem que descontar tambem o gasto da subcategoria.

    Regressao: o rollover calculava a sobra so com o gasto da propria categoria,
    enquanto a tela ja somava o da subcategoria sem orcamento. O mes seguinte
    recebia como disponivel um dinheiro que ja tinha sido gasto.
    """
    alimentacao = categories_of(client, auth)["Alimentação"]
    delivery = client.post(
        "/api/categories",
        json={"name": "Delivery", "kind": "EXPENSE", "parent_id": alimentacao["id"]},
        headers=auth,
    ).get_json()

    create_budget(client, auth, alimentacao["id"], "2026-08", 900)
    add_expense(client, auth, 300, "2026-08-04", "Alimentação", alimentacao["id"])
    add_expense(client, auth, 200, "2026-08-11", "Delivery", delivery["id"])
    assert item_for(get_month(client, auth, "2026-08"), "Alimentação")["remaining"] == 400

    create_budget(client, auth, alimentacao["id"], "2026-09", 900, rollover=True)
    assert item_for(get_month(client, auth, "2026-09"), "Alimentação")["carryover"] == 400


def test_rollover_crosses_the_year(client, auth):
    lazer = categories_of(client, auth)["Lazer"]
    create_budget(client, auth, lazer["id"], "2026-12", 500)
    add_expense(client, auth, 200, "2026-12-15", "Lazer", lazer["id"])
    create_budget(client, auth, lazer["id"], "2027-01", 500, rollover=True)

    assert item_for(get_month(client, auth, "2027-01"), "Lazer")["carryover"] == 300


def test_rollover_without_a_previous_month_carries_nothing(client, auth):
    lazer = categories_of(client, auth)["Lazer"]
    create_budget(client, auth, lazer["id"], "2026-09", 500, rollover=True)

    assert item_for(get_month(client, auth, "2026-09"), "Lazer")["carryover"] == 0


# --- edicao e remocao -------------------------------------------------------


def test_patch_updates_only_what_was_sent(client, auth):
    outros = categories_of(client, auth)["Outros"]
    created = create_budget(client, auth, outros["id"], "2026-09", 100, note="inicial").get_json()

    response = client.patch(
        f"/api/budgets/{created['id']}", json={"planned_amount": 250}, headers=auth
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["planned_amount"] == 250
    assert body["note"] == "inicial"
    assert body["month"] == "2026-09"


def test_patch_can_turn_rollover_on(client, auth):
    lazer = categories_of(client, auth)["Lazer"]
    create_budget(client, auth, lazer["id"], "2026-08", 400)
    created = create_budget(client, auth, lazer["id"], "2026-09", 400).get_json()

    response = client.patch(f"/api/budgets/{created['id']}", json={"rollover": True}, headers=auth)
    assert response.status_code == 200
    assert response.get_json()["carryover"] == 400


def test_empty_patch_is_refused(client, auth):
    outros = categories_of(client, auth)["Outros"]
    created = create_budget(client, auth, outros["id"], "2026-09", 100).get_json()
    assert client.patch(f"/api/budgets/{created['id']}", json={}, headers=auth).status_code == 400


def test_patch_into_an_existing_month_is_refused(client, auth):
    outros = categories_of(client, auth)["Outros"]
    create_budget(client, auth, outros["id"], "2026-09", 100)
    other = create_budget(client, auth, outros["id"], "2026-10", 100).get_json()

    response = client.patch(f"/api/budgets/{other['id']}", json={"month": "2026-09"}, headers=auth)
    assert response.status_code == 409


def test_delete_removes_the_budget_and_keeps_the_transactions(client, auth):
    outros = categories_of(client, auth)["Outros"]
    created = create_budget(client, auth, outros["id"], "2026-09", 100).get_json()
    add_expense(client, auth, 40, "2026-09-09", "Outros", outros["id"])

    assert client.delete(f"/api/budgets/{created['id']}", headers=auth).status_code == 200
    assert get_month(client, auth, "2026-09")["items"] == []
    remaining = client.get("/api/transactions", headers=auth).get_json()
    assert any(item["amount"] == 40 for item in remaining)


def test_unknown_budget_is_404(client, auth):
    assert client.patch("/api/budgets/nope", json={"planned_amount": 1}, headers=auth).status_code == 404
    assert client.delete("/api/budgets/nope", headers=auth).status_code == 404


# --- copiar mes -------------------------------------------------------------


def test_copy_defaults_to_the_previous_month(client, auth):
    categories = categories_of(client, auth)
    create_budget(client, auth, categories["Alimentação"]["id"], "2026-09", 900)
    create_budget(client, auth, categories["Transporte"]["id"], "2026-09", 300)

    response = client.post("/api/budgets/copy", json={"to_month": "2026-10"}, headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert body["from_month"] == "2026-09"
    assert body["created"] == 2
    assert body["totals"]["planned"] == 1200


def test_copy_skips_what_already_exists_unless_overwrite(client, auth):
    categories = categories_of(client, auth)
    create_budget(client, auth, categories["Alimentação"]["id"], "2026-09", 900)
    create_budget(client, auth, categories["Alimentação"]["id"], "2026-10", 100)

    skipped = client.post(
        "/api/budgets/copy", json={"from_month": "2026-09", "to_month": "2026-10"}, headers=auth
    ).get_json()
    assert skipped["skipped"] == 1
    assert skipped["totals"]["planned"] == 100

    overwritten = client.post(
        "/api/budgets/copy",
        json={"from_month": "2026-09", "to_month": "2026-10", "overwrite": True},
        headers=auth,
    ).get_json()
    assert overwritten["updated"] == 1
    assert overwritten["totals"]["planned"] == 900


def test_copy_refuses_the_same_month(client, auth):
    response = client.post(
        "/api/budgets/copy", json={"from_month": "2026-09", "to_month": "2026-09"}, headers=auth
    )
    assert response.status_code == 400


# --- isolamento por usuario -------------------------------------------------


def test_another_users_budget_is_invisible(client, user, other_user):
    mine = categories_of(client, user["headers"])["Lazer"]
    create_budget(client, user["headers"], mine["id"], "2026-09", 500)

    assert get_month(client, other_user["headers"], "2026-09")["items"] == []


def test_another_users_budget_cannot_be_edited_or_deleted(client, user, other_user):
    mine = categories_of(client, user["headers"])["Lazer"]
    created = create_budget(client, user["headers"], mine["id"], "2026-09", 500).get_json()

    assert (
        client.patch(
            f"/api/budgets/{created['id']}", json={"planned_amount": 1}, headers=other_user["headers"]
        ).status_code
        == 404
    )
    assert client.delete(f"/api/budgets/{created['id']}", headers=other_user["headers"]).status_code == 404
    assert client.get("/api/budgets", headers=user["headers"], query_string={"month": "2026-09"}).get_json()[
        "items"
    ]


def test_another_users_category_cannot_be_budgeted(client, user, other_user):
    theirs = categories_of(client, other_user["headers"])["Lazer"]
    response = create_budget(client, user["headers"], theirs["id"], "2026-09", 500)
    assert response.status_code in (400, 404)


def test_another_users_spending_does_not_count(client, user, other_user):
    mine = categories_of(client, user["headers"])["Alimentação"]
    theirs = categories_of(client, other_user["headers"])["Alimentação"]
    create_budget(client, user["headers"], mine["id"], "2026-09", 500)
    add_expense(client, other_user["headers"], 400, "2026-09-10", "Alimentação", theirs["id"])

    assert item_for(get_month(client, user["headers"], "2026-09"), "Alimentação")["spent"] == 0


def test_copy_only_sees_my_own_budgets(client, user, other_user):
    theirs = categories_of(client, other_user["headers"])["Lazer"]
    create_budget(client, other_user["headers"], theirs["id"], "2026-09", 500)

    body = client.post(
        "/api/budgets/copy", json={"from_month": "2026-09", "to_month": "2026-10"}, headers=user["headers"]
    ).get_json()
    assert body["created"] == 0
    assert body["items"] == []
