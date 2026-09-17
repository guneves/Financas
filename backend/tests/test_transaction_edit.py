"""Editar um lancamento — secao 3.7 de docs/next-steps.md.

Ate aqui `/api/transactions/<id>` so aceitava DELETE: um digito errado
significava apagar e redigitar. PATCH e parcial (so mexe no que veio no
payload) e recusa as duas coisas que quebrariam a consistencia: editar um
lancamento espelhado de investimento, e converter um lancamento comum em
transferencia (ou vice-versa).
"""

import pytest


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


def patch(client, headers, item_id, payload):
    return client.patch(f"/api/transactions/{item_id}", json=payload, headers=headers)


# --------------------------------------------------------------------------
# Edicao feliz
# --------------------------------------------------------------------------


def test_patch_amount(client, auth):
    item = create_transaction(client, auth)
    response = patch(client, auth, item["id"], {"amount": 250.5})
    assert response.status_code == 200
    assert response.get_json()["amount"] == 250.5


def test_patch_rounds_the_amount_half_up(client, auth):
    item = create_transaction(client, auth)
    assert patch(client, auth, item["id"], {"amount": 10.125}).get_json()["amount"] == 10.13


def test_patch_is_partial(client, auth):
    item = create_transaction(client, auth)
    updated = patch(client, auth, item["id"], {"description": "Teatro"}).get_json()
    assert updated["description"] == "Teatro"
    assert updated["amount"] == item["amount"]
    assert updated["date"] == item["date"]
    assert updated["category"] == item["category"]


def test_patch_date_and_type(client, auth):
    item = create_transaction(client, auth)
    updated = patch(client, auth, item["id"], {"date": "2026-04-15", "type": "INCOME"}).get_json()
    assert updated["date"] == "2026-04-15"
    assert updated["type"] == "INCOME"


def test_patch_category_by_id_updates_the_stored_name(client, auth):
    item = create_transaction(client, auth)
    categories = client.get("/api/categories", headers=auth).get_json()
    moradia = next(c for c in categories if c["name"] == "Moradia")

    updated = patch(client, auth, item["id"], {"category_id": moradia["id"]}).get_json()
    assert updated["category"] == "Moradia"
    assert updated["category_id"] == moradia["id"]


def test_patch_moves_the_transaction_between_accounts(client, auth):
    item = create_transaction(client, auth, amount=200, type="EXPENSE")
    savings = client.post(
        "/api/accounts", json={"name": "Poupanca", "type": "SAVINGS"}, headers=auth
    ).get_json()

    patch(client, auth, item["id"], {"account_id": savings["id"]})

    accounts = client.get("/api/accounts", headers=auth).get_json()
    balances = {account["name"]: account["balance"] for account in accounts}
    assert balances["Conta Principal"] == 0
    assert balances["Poupanca"] == -200


def test_changing_the_type_flips_the_account_balance(client, auth):
    item = create_transaction(client, auth, amount=100, type="EXPENSE")
    patch(client, auth, item["id"], {"type": "INCOME"})
    account = client.get("/api/accounts", headers=auth).get_json()[0]
    assert account["balance"] == 100


# --------------------------------------------------------------------------
# Recusas
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"amount": 0},
        {"amount": -5},
        {"amount": "muito"},
        {"date": "01/03/2026"},
        {"type": "PIX"},
        {"category_id": "nao-existe"},
        {"account_id": "nao-existe"},
    ],
)
def test_invalid_patch_payloads_are_refused(client, auth, payload):
    item = create_transaction(client, auth)
    assert patch(client, auth, item["id"], payload).status_code == 400


def test_empty_patch_is_refused(client, auth):
    item = create_transaction(client, auth)
    assert patch(client, auth, item["id"], {}).status_code == 400


def test_patching_an_unknown_transaction_is_404(client, auth):
    assert patch(client, auth, "nao-existe", {"amount": 10}).status_code == 404


def test_cannot_convert_a_plain_transaction_into_a_transfer(client, auth):
    item = create_transaction(client, auth)
    assert patch(client, auth, item["id"], {"type": "TRANSFER"}).status_code == 400


def test_cannot_convert_a_transfer_into_a_plain_transaction(client, auth):
    origin = client.get("/api/accounts", headers=auth).get_json()[0]
    destination = client.post(
        "/api/accounts", json={"name": "Poupanca", "type": "SAVINGS"}, headers=auth
    ).get_json()
    transfer = client.post(
        "/api/transfers",
        json={
            "amount": 100,
            "date": "2026-03-05",
            "account_id": origin["id"],
            "transfer_account_id": destination["id"],
        },
        headers=auth,
    ).get_json()
    assert patch(client, auth, transfer["id"], {"type": "EXPENSE"}).status_code == 400


def test_transfer_destination_can_be_corrected(client, auth):
    origin = client.get("/api/accounts", headers=auth).get_json()[0]
    savings = client.post(
        "/api/accounts", json={"name": "Poupanca", "type": "SAVINGS"}, headers=auth
    ).get_json()
    brokerage = client.post(
        "/api/accounts", json={"name": "Corretora", "type": "BROKERAGE"}, headers=auth
    ).get_json()
    transfer = client.post(
        "/api/transfers",
        json={
            "amount": 100,
            "date": "2026-03-05",
            "account_id": origin["id"],
            "transfer_account_id": savings["id"],
        },
        headers=auth,
    ).get_json()

    patch(client, auth, transfer["id"], {"transfer_account_id": brokerage["id"]})

    balances = {
        account["name"]: account["balance"]
        for account in client.get("/api/accounts", headers=auth).get_json()
    }
    assert balances["Poupanca"] == 0
    assert balances["Corretora"] == 100


def test_transfer_origin_and_destination_cannot_be_made_equal(client, auth):
    origin = client.get("/api/accounts", headers=auth).get_json()[0]
    savings = client.post(
        "/api/accounts", json={"name": "Poupanca", "type": "SAVINGS"}, headers=auth
    ).get_json()
    transfer = client.post(
        "/api/transfers",
        json={
            "amount": 100,
            "date": "2026-03-05",
            "account_id": origin["id"],
            "transfer_account_id": savings["id"],
        },
        headers=auth,
    ).get_json()
    assert patch(client, auth, transfer["id"], {"account_id": savings["id"]}).status_code == 400


def test_transfer_destination_is_rejected_on_a_plain_transaction(client, auth):
    item = create_transaction(client, auth)
    savings = client.post(
        "/api/accounts", json={"name": "Poupanca", "type": "SAVINGS"}, headers=auth
    ).get_json()
    assert patch(client, auth, item["id"], {"transfer_account_id": savings["id"]}).status_code == 400


def test_investment_cash_transaction_cannot_be_edited(client, auth):
    """Mesma regra que ja vale para DELETE: a movimentacao de investimento manda."""
    client.post(
        "/api/investments",
        json={
            "asset_class": "STOCKS",
            "ticker_or_name": "VALE3",
            "quantity": 5,
            "average_price": 60,
            "metadata": {"purchase_date": "2026-03-01"},
        },
        headers=auth,
    )
    cash = next(
        item
        for item in client.get("/api/transactions", headers=auth).get_json()
        if item["source_type"] == "INVESTMENT_TRANSACTION"
    )
    assert patch(client, auth, cash["id"], {"amount": 1}).status_code == 409


# --------------------------------------------------------------------------
# Isolamento por user_id
# --------------------------------------------------------------------------


def test_cannot_patch_another_users_transaction(client, auth, other_user):
    item = create_transaction(client, auth)
    response = patch(client, other_user["headers"], item["id"], {"amount": 1})
    assert response.status_code == 404


def test_patch_requires_authentication(client, auth):
    item = create_transaction(client, auth)
    assert client.patch(f"/api/transactions/{item['id']}", json={"amount": 1}).status_code == 401
