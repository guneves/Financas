"""Busca e filtros do extrato — secao 3.7 de docs/next-steps.md.

`GET /api/transactions` aceita filtros opcionais (periodo, tipo, conta,
categoria, texto livre, faixa de valor). Sem nenhum, devolve tudo — e o
que a pagina usa para o saldo consolidado, entao esse caminho nao pode mudar.
"""

import importlib


def create_transaction(client, headers, **overrides):
    payload = {
        "amount": 100,
        "date": "2026-03-01",
        "category": "Lazer",
        "description": "Cinema",
        "type": "EXPENSE",
    }
    payload.update(overrides)
    response = client.post("/api/transactions", json=payload, headers=headers)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def create_account(client, headers, name):
    response = client.post("/api/accounts", json={"name": name, "type": "CHECKING"}, headers=headers)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def create_category(client, headers, name, parent_id=None):
    payload = {"name": name, "kind": "EXPENSE"}
    if parent_id:
        payload["parent_id"] = parent_id
    response = client.post("/api/categories", json=payload, headers=headers)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def search(client, headers, **params):
    response = client.get("/api/transactions", headers=headers, query_string=params)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def descriptions(rows):
    return sorted(row["description"] for row in rows)


def test_no_filter_returns_everything(client, auth):
    create_transaction(client, auth, description="A")
    create_transaction(client, auth, description="B", type="INCOME", category="Receita")
    assert descriptions(search(client, auth)) == ["A", "B"]


def test_period_is_inclusive_on_both_ends(client, auth):
    create_transaction(client, auth, date="2026-02-28", description="antes")
    create_transaction(client, auth, date="2026-03-01", description="inicio")
    create_transaction(client, auth, date="2026-03-31", description="fim")
    create_transaction(client, auth, date="2026-04-01", description="depois")
    rows = search(client, auth, **{"from": "2026-03-01", "to": "2026-03-31"})
    assert descriptions(rows) == ["fim", "inicio"]


def test_open_ended_period(client, auth):
    create_transaction(client, auth, date="2026-01-10", description="velho")
    create_transaction(client, auth, date="2026-05-10", description="novo")
    assert descriptions(search(client, auth, **{"from": "2026-03-01"})) == ["novo"]
    assert descriptions(search(client, auth, to="2026-03-01")) == ["velho"]


def test_filter_by_type(client, auth):
    create_transaction(client, auth, description="gasto")
    create_transaction(client, auth, description="salario", type="INCOME", category="Receita")
    assert descriptions(search(client, auth, type="income")) == ["salario"]
    assert descriptions(search(client, auth, type="EXPENSE")) == ["gasto"]


def test_filter_by_account_includes_transfers_arriving_there(client, auth):
    origin = create_account(client, auth, "Itau")
    destination = create_account(client, auth, "Poupanca")
    create_transaction(client, auth, account_id=origin["id"], description="na origem")
    create_transaction(client, auth, account_id=destination["id"], description="no destino")
    response = client.post(
        "/api/transfers",
        json={
            "amount": 50,
            "date": "2026-03-05",
            "account_id": origin["id"],
            "transfer_account_id": destination["id"],
            "description": "transferencia",
        },
        headers=auth,
    )
    assert response.status_code == 201
    assert descriptions(search(client, auth, account_id=destination["id"])) == [
        "no destino",
        "transferencia",
    ]
    assert descriptions(search(client, auth, account_id=origin["id"])) == [
        "na origem",
        "transferencia",
    ]


def test_filter_by_category_includes_subcategories(client, auth):
    food = create_category(client, auth, "Comida")
    delivery = create_category(client, auth, "Delivery", parent_id=food["id"])
    create_transaction(client, auth, category_id=food["id"], description="mercado")
    create_transaction(client, auth, category_id=delivery["id"], description="ifood")
    create_transaction(client, auth, description="cinema")
    assert descriptions(search(client, auth, category_id=food["id"])) == ["ifood", "mercado"]
    assert descriptions(search(client, auth, category_id=delivery["id"])) == ["ifood"]


def test_filter_by_category_matches_legacy_rows_by_name(client, auth, app_module):
    food = create_category(client, auth, "Comida")
    legacy = create_transaction(client, auth, category="Comida", description="antigo")
    with importlib.import_module("db").get_db() as conn:
        conn.execute("UPDATE transactions SET category_id = NULL WHERE id = ?", (legacy["id"],))
    assert descriptions(search(client, auth, category_id=food["id"])) == ["antigo"]


def test_unknown_category_is_rejected(client, auth):
    response = client.get("/api/transactions", headers=auth, query_string={"category_id": "nope"})
    assert response.status_code == 400


def test_text_search_is_case_insensitive_on_description_and_category(client, auth):
    create_transaction(client, auth, description="Pizza IFOOD", category="Alimentação")
    create_transaction(client, auth, description="Cinema", category="Lazer")
    create_transaction(client, auth, description="Aluguel", category="Moradia")
    assert descriptions(search(client, auth, q="ifood")) == ["Pizza IFOOD"]
    assert descriptions(search(client, auth, q="laz")) == ["Cinema"]


def test_text_search_treats_like_wildcards_literally(client, auth):
    create_transaction(client, auth, description="desconto 10%")
    create_transaction(client, auth, description="desconto 100")
    create_transaction(client, auth, description="a_b")
    create_transaction(client, auth, description="axb")
    assert descriptions(search(client, auth, q="10%")) == ["desconto 10%"]
    assert descriptions(search(client, auth, q="a_b")) == ["a_b"]


def test_amount_range_is_inclusive(client, auth):
    create_transaction(client, auth, amount=49.99, description="abaixo")
    create_transaction(client, auth, amount=50, description="minimo")
    create_transaction(client, auth, amount=100, description="maximo")
    create_transaction(client, auth, amount=100.01, description="acima")
    rows = search(client, auth, min_amount="50", max_amount="100")
    assert descriptions(rows) == ["maximo", "minimo"]


def test_filters_combine(client, auth):
    create_transaction(client, auth, date="2026-03-10", amount=30, description="Uber centro")
    create_transaction(client, auth, date="2026-03-10", amount=300, description="Uber viagem")
    create_transaction(client, auth, date="2026-04-10", amount=30, description="Uber abril")
    rows = search(
        client, auth, q="uber", max_amount="100", **{"from": "2026-03-01", "to": "2026-03-31"}
    )
    assert descriptions(rows) == ["Uber centro"]


def test_invalid_filters_are_rejected(client, auth):
    bad = [
        {"from": "10/03/2026"},
        {"from": "2026-04-01", "to": "2026-03-01"},
        {"type": "BOGUS"},
        {"min_amount": "abc"},
        {"min_amount": "-1"},
        {"min_amount": "100", "max_amount": "10"},
        {"q": "x" * 101},
    ]
    for params in bad:
        response = client.get("/api/transactions", headers=auth, query_string=params)
        assert response.status_code == 400, params


def test_filters_never_leak_another_users_rows(client, auth, other_user):
    other = other_user["headers"]
    create_transaction(client, other, description="segredo")
    create_transaction(client, auth, description="meu")
    assert descriptions(search(client, auth, q="segredo")) == []
    assert descriptions(search(client, auth, q="e")) == ["meu"]


def test_filter_by_another_users_category_is_rejected(client, auth, other_user):
    theirs = create_category(client, other_user["headers"], "Deles")
    response = client.get(
        "/api/transactions", headers=auth, query_string={"category_id": theirs["id"]}
    )
    assert response.status_code == 400


def test_filter_by_another_users_account_returns_nothing(client, auth, other_user):
    theirs = create_account(client, other_user["headers"], "Conta deles")
    create_transaction(client, other_user["headers"], account_id=theirs["id"], description="x")
    assert search(client, auth, account_id=theirs["id"]) == []
