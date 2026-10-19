"""Categorias como tabela — secao 3.2 de docs/next-steps.md.

Antes da migration 008 as categorias eram uma constante de 10 strings em
`frontend/src/pages/Transactions.jsx`. O contrato que estes testes fixam:
`transactions.category` continua guardando o *nome* (e o que o Dashboard
agrupa) e `category_id` e a ligacao nova — renomear a categoria tem que
arrastar o texto junto, ou o agrupamento se parte em dois.
"""

import pytest

DEFAULT_NAMES = {
    "Receita",
    "Alimentação",
    "Moradia",
    "Transporte",
    "Saúde",
    "Educação",
    "Lazer",
    "Serviços",
    "Outros",
}


def list_categories(client, headers, **params):
    response = client.get("/api/categories", headers=headers, query_string=params)
    assert response.status_code == 200
    return response.get_json()


def create_category(client, headers, name, kind="EXPENSE", parent_id=None):
    payload = {"name": name, "kind": kind}
    if parent_id:
        payload["parent_id"] = parent_id
    return client.post("/api/categories", json=payload, headers=headers)


def by_name(categories, name):
    return next(item for item in categories if item["name"] == name)


# --------------------------------------------------------------------------
# Seed inicial
# --------------------------------------------------------------------------


def test_signup_seeds_the_nine_original_categories(client, auth):
    names = {item["name"] for item in list_categories(client, auth)}
    assert names == DEFAULT_NAMES


def test_receita_is_seeded_as_income_and_the_rest_as_expense(client, auth):
    categories = list_categories(client, auth)
    assert by_name(categories, "Receita")["kind"] == "INCOME"
    # Investimento deixou de ser categoria (039): aporte e transferencia para a Corretora.
    assert "Investimento" not in {item["name"] for item in categories}
    assert by_name(categories, "Moradia")["kind"] == "EXPENSE"


def test_kind_filter_includes_both(client, auth):
    response = client.post("/api/categories", headers=auth, json={"name": "Reembolsos", "kind": "BOTH"})
    assert response.status_code == 201, response.get_data(as_text=True)
    names = {item["name"] for item in list_categories(client, auth, kind="INCOME")}
    assert names == {"Receita", "Reembolsos"}


# --------------------------------------------------------------------------
# CRUD
# --------------------------------------------------------------------------


def test_create_category(client, auth):
    response = create_category(client, auth, "Pets")
    assert response.status_code == 201
    assert response.get_json()["name"] == "Pets"
    assert "Pets" in {item["name"] for item in list_categories(client, auth)}


def test_duplicate_root_category_name_is_refused(client, auth):
    create_category(client, auth, "Pets")
    assert create_category(client, auth, "Pets").status_code == 409


def test_subcategory_carries_its_parent(client, auth):
    food = by_name(list_categories(client, auth), "Alimentação")
    response = create_category(client, auth, "Mercado", parent_id=food["id"])
    assert response.status_code == 201
    assert response.get_json()["parent_id"] == food["id"]
    assert by_name(list_categories(client, auth), "Mercado")["parent_name"] == "Alimentação"


def test_only_one_level_of_subcategory(client, auth):
    food = by_name(list_categories(client, auth), "Alimentação")
    market = create_category(client, auth, "Mercado", parent_id=food["id"]).get_json()
    response = create_category(client, auth, "Hortifruti", parent_id=market["id"])
    assert response.status_code == 400


def test_a_category_cannot_be_its_own_parent(client, auth):
    pets = create_category(client, auth, "Pets").get_json()
    response = client.patch(
        f"/api/categories/{pets['id']}", json={"parent_id": pets["id"]}, headers=auth
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "EXPENSE"},
        {"name": "", "kind": "EXPENSE"},
        {"name": "X", "kind": "MISTERIO"},
        {"name": "X", "kind": "EXPENSE", "parent_id": "nao-existe"},
    ],
)
def test_invalid_category_payloads_are_refused(client, auth, payload):
    assert client.post("/api/categories", json=payload, headers=auth).status_code == 400


# --------------------------------------------------------------------------
# Renomear arrasta o texto gravado nos lancamentos
# --------------------------------------------------------------------------


def test_renaming_a_category_renames_it_on_linked_transactions(client, auth):
    lazer = by_name(list_categories(client, auth), "Lazer")
    client.post(
        "/api/transactions",
        json={
            "amount": 50,
            "date": "2026-03-01",
            "category_id": lazer["id"],
            "type": "EXPENSE",
        },
        headers=auth,
    )
    client.patch(f"/api/categories/{lazer['id']}", json={"name": "Diversao"}, headers=auth)

    transaction = client.get("/api/transactions", headers=auth).get_json()[0]
    assert transaction["category"] == "Diversao"
    assert transaction["category_id"] == lazer["id"]


def test_creating_a_transaction_by_category_name_links_the_existing_category(client, auth):
    lazer = by_name(list_categories(client, auth), "Lazer")
    client.post(
        "/api/transactions",
        json={"amount": 50, "date": "2026-03-01", "category": "Lazer", "type": "EXPENSE"},
        headers=auth,
    )
    transaction = client.get("/api/transactions", headers=auth).get_json()[0]
    assert transaction["category_id"] == lazer["id"]


def test_an_unknown_category_name_is_still_accepted_without_a_link(client, auth):
    """O app sempre mandou texto livre; quebrar isso quebraria os scripts de seed."""
    response = client.post(
        "/api/transactions",
        json={"amount": 50, "date": "2026-03-01", "category": "Categoria Nova", "type": "EXPENSE"},
        headers=auth,
    )
    assert response.status_code == 201
    assert response.get_json()["category"] == "Categoria Nova"
    assert response.get_json()["category_id"] is None


# --------------------------------------------------------------------------
# Arquivamento
# --------------------------------------------------------------------------


def test_archiving_a_category_hides_it_but_keeps_the_transaction(client, auth):
    pets = create_category(client, auth, "Pets").get_json()
    client.post(
        "/api/transactions",
        json={"amount": 50, "date": "2026-03-01", "category_id": pets["id"], "type": "EXPENSE"},
        headers=auth,
    )
    assert client.delete(f"/api/categories/{pets['id']}", headers=auth).status_code == 200

    assert "Pets" not in {item["name"] for item in list_categories(client, auth)}
    assert "Pets" in {
        item["name"] for item in list_categories(client, auth, include_archived="1")
    }
    transaction = client.get("/api/transactions", headers=auth).get_json()[0]
    assert transaction["category"] == "Pets"
    assert transaction["category_id"] == pets["id"]


def test_archived_category_cannot_be_used_on_a_new_transaction(client, auth):
    pets = create_category(client, auth, "Pets").get_json()
    client.delete(f"/api/categories/{pets['id']}", headers=auth)
    response = client.post(
        "/api/transactions",
        json={"amount": 50, "date": "2026-03-01", "category_id": pets["id"], "type": "EXPENSE"},
        headers=auth,
    )
    assert response.status_code == 400


def test_a_parent_with_live_children_cannot_be_archived(client, auth):
    food = by_name(list_categories(client, auth), "Alimentação")
    create_category(client, auth, "Mercado", parent_id=food["id"])
    assert client.delete(f"/api/categories/{food['id']}", headers=auth).status_code == 409


# --------------------------------------------------------------------------
# Isolamento por user_id
# --------------------------------------------------------------------------


def test_categories_are_isolated_per_user(client, auth, other_user):
    create_category(client, auth, "Pets")
    names = {item["name"] for item in list_categories(client, other_user["headers"])}
    assert "Pets" not in names


def test_cannot_use_another_users_category(client, auth, other_user):
    pets = create_category(client, auth, "Pets").get_json()
    response = client.post(
        "/api/transactions",
        json={"amount": 10, "date": "2026-03-01", "category_id": pets["id"], "type": "EXPENSE"},
        headers=other_user["headers"],
    )
    assert response.status_code == 400


def test_cannot_patch_another_users_category(client, auth, other_user):
    pets = create_category(client, auth, "Pets").get_json()
    response = client.patch(
        f"/api/categories/{pets['id']}", json={"name": "Roubada"}, headers=other_user["headers"]
    )
    assert response.status_code == 404


@pytest.mark.parametrize("method", ["get", "post"])
def test_category_endpoints_require_authentication(client, method):
    assert getattr(client, method)("/api/categories", json={}).status_code == 401
