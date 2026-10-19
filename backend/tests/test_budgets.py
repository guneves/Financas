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

Desde a 038 cada categoria e um % do Gastar do plano do mes. Para ler os
testes em reais, `create_budget()` grava antes um plano de renda 10.000 com
Gastar 100% em 2026-01: 1% de categoria = R$ 100. Um mes sem categorias
proprias herda as do mes anterior; mexer nelas num mes herdado faz do mes um
plano proprio (`?month=`).
"""

import importlib

import pytest


def get_month(client, headers, month):
    response = client.get("/api/budgets", headers=headers, query_string={"month": month})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def categories_of(client, headers):
    response = client.get("/api/categories", headers=headers)
    assert response.status_code == 200
    return {item["name"]: item for item in response.get_json()}


BASE_MONTH = "2026-01"
# Gastar do plano base: 1% de categoria = R$ 100.
SPEND_AMOUNT = 10000


def ensure_plan(client, headers):
    """O plano base (renda 10.000, Gastar 100%) desde 2026-01, uma vez por usuario."""
    body = client.get("/api/monthly-plan", headers=headers, query_string={"month": BASE_MONTH}).get_json()
    if body["plan"] is None:
        response = client.put("/api/monthly-plan", headers=headers, json={
            "month": BASE_MONTH, "income_amount": SPEND_AMOUNT, "invest_percent": 0, "spend_percent": 100,
        })
        assert response.status_code == 200, response.get_data(as_text=True)


def create_budget(client, headers, category_id, month, planned_amount, **extra):
    """Categoria de `planned_amount` reais: o % equivalente do Gastar de 10.000."""
    ensure_plan(client, headers)
    payload = {"category_id": category_id, "month": month, "planned_percent": planned_amount * 100 / SPEND_AMOUNT}
    payload.update(extra)
    return client.post("/api/budgets", json=payload, headers=headers)


def patch_in(client, headers, budget_id, month, payload):
    """PATCH na categoria como a tela do mes `month` mostra (herdada ou nao)."""
    return client.patch(
        f"/api/budgets/{budget_id}", json=payload, headers=headers, query_string={"month": month}
    )


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
    assert body["planned_percent"] == 12
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


def test_later_months_inherit_the_categories(client, auth):
    lazer = categories_of(client, auth)["Lazer"]
    created = create_budget(client, auth, lazer["id"], "2026-09", 300).get_json()

    october = get_month(client, auth, "2026-10")
    item = item_for(october, "Lazer")
    assert item["id"] == created["id"]
    assert item["inherited"] is True
    assert item["source_month"] == "2026-09"
    assert item["planned_amount"] == 300
    assert october["inherited"] is True
    # Ja esta no mes (herdada): criar de novo e duplicar.
    assert create_budget(client, auth, lazer["id"], "2026-10", 400).status_code == 409
    # Antes do mes em que foi criada, nada.
    assert get_month(client, auth, "2026-08")["items"] == []


def test_categories_cannot_pass_100_percent_of_spend(client, auth):
    categories = categories_of(client, auth)
    assert create_budget(client, auth, categories["Moradia"]["id"], "2026-09", 6000).status_code == 201
    assert create_budget(client, auth, categories["Lazer"]["id"], "2026-09", 4000).status_code == 201
    over = create_budget(client, auth, categories["Outros"]["id"], "2026-09", 0.01)
    assert over.status_code == 400
    assert "100%" in over.get_json()["error"]
    # Zero cabe: a categoria existe sem levar nada do Gastar.
    assert create_budget(client, auth, categories["Outros"]["id"], "2026-09", 0).status_code == 201

    lazer = item_for(get_month(client, auth, "2026-09"), "Lazer")
    assert patch_in(client, auth, lazer["id"], "2026-09", {"planned_percent": 40.01}).status_code == 400
    assert patch_in(client, auth, lazer["id"], "2026-09", {"planned_percent": 30}).status_code == 200

    totals = get_month(client, auth, "2026-09")["totals"]
    assert totals["assigned_percent"] == 90
    assert totals["unassigned_percent"] == 10
    assert totals["unassigned_amount"] == 1000


def test_a_third_of_spend_three_times_does_not_drift(client, auth):
    categories = categories_of(client, auth)
    ensure_plan(client, auth)
    for name in ("Moradia", "Lazer", "Transporte"):
        response = client.post("/api/budgets", headers=auth, json={
            "category_id": categories[name]["id"], "month": "2026-09", "planned_percent": "33,33",
        })
        assert response.status_code == 201, response.get_data(as_text=True)
    # 33,33 x 3 = 99,99 exatos: ainda cabe 0,01%, e nada alem disso.
    fits = client.post("/api/budgets", headers=auth, json={
        "category_id": categories["Outros"]["id"], "month": "2026-09", "planned_percent": 0.01,
    })
    assert fits.status_code == 201, fits.get_data(as_text=True)
    body = get_month(client, auth, "2026-09")
    assert body["totals"]["assigned_percent"] == 100
    assert body["totals"]["unassigned_percent"] == 0
    assert body["totals"]["planned"] == 10000
    assert item_for(body, "Moradia")["planned_amount"] == 3333


def test_without_a_plan_a_category_needs_income(client, auth):
    lazer = categories_of(client, auth)["Lazer"]
    response = client.post("/api/budgets", headers=auth, json={
        "category_id": lazer["id"], "month": "2026-09", "planned_percent": 10,
    })
    assert response.status_code == 201, response.get_data(as_text=True)
    add_expense(client, auth, 70, "2026-09-05", "Lazer", lazer["id"])

    body = get_month(client, auth, "2026-09")
    item = item_for(body, "Lazer")
    assert item["needs_income"] is True
    assert item["status"] == "NEEDS_INCOME"
    assert item["planned_percent"] == 10
    assert item["planned_amount"] is None
    assert item["available"] is None
    assert item["spent"] == 70
    assert body["needs_income"] is True
    assert body["totals"]["spend_amount"] is None
    assert body["totals"]["plan_balance"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {"month": "2026-09", "planned_percent": 10},
        {"category_id": "nao-existe", "month": "2026-09", "planned_percent": 10},
        {"category_id": "x", "month": "setembro", "planned_percent": 10},
        {"category_id": "x", "month": "2026-09"},
        # Reais fixos nao existem mais: so o % do Gastar.
        {"category_id": "x", "month": "2026-09", "planned_amount": 100},
        {"category_id": "x", "month": "2026-09", "planned_percent": -10},
        {"category_id": "x", "month": "2026-09", "planned_percent": 100.01},
        {"category_id": "x", "month": "2026-09", "planned_percent": "muito"},
        {"category_id": "x", "month": "2026-09", "planned_percent": True},
    ],
)
def test_invalid_payloads_are_refused(client, auth, payload):
    if payload.get("category_id") == "x":
        payload["category_id"] = categories_of(client, auth)["Outros"]["id"]
    response = client.post("/api/budgets", json=payload, headers=auth)
    assert response.status_code == 400


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
    created = create_budget(client, auth, lazer["id"], "2026-08", 400).get_json()
    add_expense(client, auth, 150, "2026-08-10", "Lazer", lazer["id"])
    assert patch_in(client, auth, created["id"], "2026-09", {"rollover": True}).status_code == 200

    item = item_for(get_month(client, auth, "2026-09"), "Lazer")
    assert item["inherited"] is False
    assert item["carryover"] == 250
    assert item["available"] == 650
    assert item["remaining"] == 650


def test_rollover_off_ignores_the_leftover(client, auth):
    lazer = categories_of(client, auth)["Lazer"]
    create_budget(client, auth, lazer["id"], "2026-08", 400)

    item = item_for(get_month(client, auth, "2026-09"), "Lazer")
    assert item["inherited"] is True
    assert item["carryover"] == 0
    assert item["available"] == 400


def test_an_overrun_does_not_become_next_month_debt(client, auth):
    lazer = categories_of(client, auth)["Lazer"]
    created = create_budget(client, auth, lazer["id"], "2026-08", 400).get_json()
    add_expense(client, auth, 900, "2026-08-10", "Lazer", lazer["id"])
    patch_in(client, auth, created["id"], "2026-09", {"rollover": True})

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

    created = create_budget(client, auth, alimentacao["id"], "2026-08", 900).get_json()
    add_expense(client, auth, 300, "2026-08-04", "Alimentação", alimentacao["id"])
    add_expense(client, auth, 200, "2026-08-11", "Delivery", delivery["id"])
    assert item_for(get_month(client, auth, "2026-08"), "Alimentação")["remaining"] == 400

    patch_in(client, auth, created["id"], "2026-09", {"rollover": True})
    assert item_for(get_month(client, auth, "2026-09"), "Alimentação")["carryover"] == 400


def test_rollover_crosses_the_year(client, auth):
    lazer = categories_of(client, auth)["Lazer"]
    created = create_budget(client, auth, lazer["id"], "2026-12", 500).get_json()
    add_expense(client, auth, 200, "2026-12-15", "Lazer", lazer["id"])
    patch_in(client, auth, created["id"], "2027-01", {"rollover": True})

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
        f"/api/budgets/{created['id']}", json={"planned_percent": 2.5}, headers=auth
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["planned_percent"] == 2.5
    assert body["planned_amount"] == 250
    assert body["note"] == "inicial"
    assert body["month"] == "2026-09"


def test_patch_in_an_inherited_month_leaves_the_earlier_month_alone(client, auth):
    categories = categories_of(client, auth)
    created = create_budget(client, auth, categories["Lazer"]["id"], "2026-08", 400).get_json()
    create_budget(client, auth, categories["Transporte"]["id"], "2026-08", 300)

    response = patch_in(client, auth, created["id"], "2026-09", {"rollover": True, "planned_percent": 5})
    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert body["id"] != created["id"]
    assert body["month"] == "2026-09"
    assert body["inherited"] is False
    assert body["carryover"] == 400
    assert body["planned_amount"] == 500

    august = get_month(client, auth, "2026-08")
    assert item_for(august, "Lazer")["rollover"] is False
    assert item_for(august, "Lazer")["planned_amount"] == 400
    # O mes virou um plano proprio, com as outras categorias herdadas junto.
    september = get_month(client, auth, "2026-09")
    assert september["inherited"] is False
    assert item_for(september, "Transporte")["planned_amount"] == 300
    # E outubro herda o de setembro.
    assert item_for(get_month(client, auth, "2026-10"), "Lazer")["planned_amount"] == 500


def test_patch_with_a_month_that_does_not_show_the_row_is_404(client, auth):
    lazer = categories_of(client, auth)["Lazer"]
    created = create_budget(client, auth, lazer["id"], "2026-08", 400).get_json()
    # Julho e antes da linha; ela nao vale la.
    assert patch_in(client, auth, created["id"], "2026-07", {"rollover": True}).status_code == 404


def test_deleting_in_an_inherited_month_keeps_the_earlier_month(client, auth):
    categories = categories_of(client, auth)
    lazer = create_budget(client, auth, categories["Lazer"]["id"], "2026-08", 400).get_json()

    response = client.delete(f"/api/budgets/{lazer['id']}", headers=auth, query_string={"month": "2026-09"})
    assert response.status_code == 200
    assert get_month(client, auth, "2026-09")["items"] == []
    assert get_month(client, auth, "2026-10")["items"] == []
    assert item_for(get_month(client, auth, "2026-08"), "Lazer")["planned_amount"] == 400


def test_empty_patch_is_refused(client, auth):
    outros = categories_of(client, auth)["Outros"]
    created = create_budget(client, auth, outros["id"], "2026-09", 100).get_json()
    assert client.patch(f"/api/budgets/{created['id']}", json={}, headers=auth).status_code == 400


def test_patch_into_an_existing_month_is_refused(client, auth):
    outros = categories_of(client, auth)["Outros"]
    create_budget(client, auth, outros["id"], "2026-09", 100)
    # Julho vem antes de setembro: nao herda dele.
    other = create_budget(client, auth, outros["id"], "2026-07", 100).get_json()

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
    assert client.patch("/api/budgets/nope", json={"planned_percent": 1}, headers=auth).status_code == 404
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
    # Outubro ja herdava as duas: agora sao dele.
    assert body["created"] + body["skipped"] == 2
    assert body["inherited"] is False
    assert body["totals"]["planned"] == 1200


def test_copy_copies_the_percentages(client, auth):
    categories = categories_of(client, auth)
    create_budget(client, auth, categories["Alimentação"]["id"], "2026-09", 900)
    create_budget(client, auth, categories["Transporte"]["id"], "2026-09", 300)
    # Julho e antes: nada herdado, a copia cria as duas.
    body = client.post(
        "/api/budgets/copy", json={"from_month": "2026-09", "to_month": "2026-07"}, headers=auth
    ).get_json()
    assert body["created"] == 2
    assert sorted(item["planned_percent"] for item in body["items"]) == [3, 9]

    # O mesmo % sobre outro Gastar: julho com renda 5.000, Gastar 100%.
    client.put("/api/monthly-plan", headers=auth, json={
        "month": "2026-07", "income_amount": 5000, "invest_percent": 0, "spend_percent": 100,
    })
    july = get_month(client, auth, "2026-07")
    assert item_for(july, "Alimentação")["planned_amount"] == 450
    assert item_for(july, "Transporte")["planned_amount"] == 150


def test_copy_skips_what_already_exists_unless_overwrite(client, auth):
    categories = categories_of(client, auth)
    create_budget(client, auth, categories["Alimentação"]["id"], "2026-09", 900)
    create_budget(client, auth, categories["Alimentação"]["id"], "2026-07", 100)

    skipped = client.post(
        "/api/budgets/copy", json={"from_month": "2026-09", "to_month": "2026-07"}, headers=auth
    ).get_json()
    assert skipped["skipped"] == 1
    assert skipped["totals"]["planned"] == 100

    overwritten = client.post(
        "/api/budgets/copy",
        json={"from_month": "2026-09", "to_month": "2026-07", "overwrite": True},
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
            f"/api/budgets/{created['id']}", json={"planned_percent": 1}, headers=other_user["headers"]
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


# --- cartao no orcamento (decisao 1) ------------------------------------------

def create_card_purchase(client, headers, *, total, date, category, installments=1, card_name="Cartao Orcamento"):
    card = client.post(
        "/api/credit-cards", headers=headers, json={"name": card_name, "due_day": 10, "closing_day": 3},
    ).get_json()
    card = card[0] if isinstance(card, list) else card
    response = client.post(
        "/api/cc-expenses/purchases",
        headers=headers,
        json={
            "card_id": card["id"],
            "category": category,
            "description": "Compra no cartao",
            "total_amount": total,
            "purchase_date": date,
            "installments": installments,
        },
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return card


def test_a_card_purchase_counts_in_full_in_its_purchase_month(client, auth):
    alimentacao = categories_of(client, auth)["Alimentação"]
    create_budget(client, auth, alimentacao["id"], "2026-09", 1000)
    create_card_purchase(client, auth, total=600, date="2026-09-28", category="Alimentação", installments=3)

    assert item_for(get_month(client, auth, "2026-09"), "Alimentação")["spent"] == 600
    # As parcelas seguintes nao contam de novo no mes da fatura delas.
    assert item_for(get_month(client, auth, "2026-10"), "Alimentação")["spent"] == 0


def test_the_invoice_payment_is_not_spending(client, auth, app_module):
    moradia = categories_of(client, auth)["Moradia"]
    create_budget(client, auth, moradia["id"], "2026-09", 1000)
    add_expense(client, auth, 300, "2026-09-10", "Moradia", moradia["id"])
    payment = add_expense(client, auth, 900, "2026-09-10", "Moradia", moradia["id"])
    legacy = add_expense(client, auth, 400, "2026-09-10", "Pagamento Fatura Nubank")
    with importlib.import_module("db").get_db() as conn:
        conn.execute(
            "UPDATE transactions SET source_type = 'CC_INVOICE_PAYMENT', source_id = 'x:2026-09' WHERE id = ?",
            (payment["id"],),
        )

    assert item_for(get_month(client, auth, "2026-09"), "Moradia")["spent"] == 300
    assert legacy["category"].startswith("Pagamento Fatura")


def test_another_users_card_purchases_do_not_count(client, user, other_user):
    alimentacao = categories_of(client, user["headers"])["Alimentação"]
    create_budget(client, user["headers"], alimentacao["id"], "2026-09", 1000)
    create_card_purchase(client, other_user["headers"], total=500, date="2026-09-05", category="Alimentação")
    assert item_for(get_month(client, user["headers"], "2026-09"), "Alimentação")["spent"] == 0


def test_a_month_without_the_leading_zero_is_stored_padded(client, auth):
    """"2026-9" e o mesmo mes que "2026-09"; gravado curto, ficava fora das buscas."""
    category_id = categories_of(client, auth)["Outros"]["id"]
    response = client.post(
        "/api/budgets", json={"category_id": category_id, "month": "2026-9", "planned_percent": 1}, headers=auth
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    assert response.get_json()["month"] == "2026-09"
