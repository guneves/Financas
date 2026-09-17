"""Contas bancarias e transferencias — secao 3.1 de docs/next-steps.md.

O ponto central que estes testes protegem: uma TRANSFER nao e receita nem
despesa. Ela muda o saldo de duas contas e deixa o consolidado exatamente onde
estava. Antes da migration 007 o unico jeito de registrar isso era despesa +
receita, o que inflava os dois totais do mes.
"""

import pytest


def create_account(client, headers, name, account_type="CHECKING", initial_balance=0):
    response = client.post(
        "/api/accounts",
        json={"name": name, "type": account_type, "initial_balance": initial_balance},
        headers=headers,
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def list_accounts(client, headers, **params):
    response = client.get("/api/accounts", headers=headers, query_string=params)
    assert response.status_code == 200
    return response.get_json()


def balance_of(accounts, name):
    return next(item["balance"] for item in accounts if item["name"] == name)


# --------------------------------------------------------------------------
# A conta padrao
# --------------------------------------------------------------------------


def test_signup_creates_a_default_account(client, auth):
    accounts = list_accounts(client, auth)
    assert len(accounts) == 1
    assert accounts[0]["name"] == "Conta Principal"
    assert accounts[0]["is_default"] is True
    assert accounts[0]["type"] == "CHECKING"
    assert accounts[0]["balance"] == 0


def test_transaction_without_account_id_lands_in_the_default_account(client, auth):
    client.post(
        "/api/transactions",
        json={"amount": 100, "date": "2026-03-01", "category": "Lazer", "type": "EXPENSE"},
        headers=auth,
    )
    accounts = list_accounts(client, auth)
    assert balance_of(accounts, "Conta Principal") == -100

    listed = client.get("/api/transactions", headers=auth).get_json()
    assert listed[0]["account_id"] == accounts[0]["id"]


def test_investment_cash_transaction_also_lands_in_an_account(client, auth):
    client.post(
        "/api/investments",
        json={
            "asset_class": "STOCKS",
            "ticker_or_name": "PETR4",
            "quantity": 10,
            "average_price": 30,
            "metadata": {"purchase_date": "2026-03-01"},
        },
        headers=auth,
    )
    cash = [
        item
        for item in client.get("/api/transactions", headers=auth).get_json()
        if item["source_type"] == "INVESTMENT_TRANSACTION"
    ]
    assert cash, "a compra deveria ter gerado o lancamento de caixa espelhado"
    assert cash[0]["account_id"] is not None


# --------------------------------------------------------------------------
# CRUD de contas
# --------------------------------------------------------------------------


def test_create_account_with_initial_balance(client, auth):
    account = create_account(client, auth, "Poupanca", "SAVINGS", initial_balance=1500.5)
    assert account["type"] == "SAVINGS"
    assert account["initial_balance"] == 1500.5
    assert balance_of(list_accounts(client, auth), "Poupanca") == 1500.5


def test_initial_balance_is_rounded_half_up(client, auth):
    account = create_account(client, auth, "Meia Ponta", initial_balance=10.125)
    assert account["initial_balance"] == 10.13


def test_duplicate_account_name_is_refused(client, auth):
    create_account(client, auth, "Nubank")
    response = client.post(
        "/api/accounts", json={"name": "Nubank", "type": "CHECKING"}, headers=auth
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "CHECKING"},
        {"name": "", "type": "CHECKING"},
        {"name": "X", "type": "CRYPTO"},
        {"name": "X"},
    ],
)
def test_invalid_account_payloads_are_refused(client, auth, payload):
    response = client.post("/api/accounts", json=payload, headers=auth)
    assert response.status_code == 400


def test_rename_account(client, auth):
    account = create_account(client, auth, "Banco Velho")
    response = client.patch(
        f"/api/accounts/{account['id']}", json={"name": "Banco Novo"}, headers=auth
    )
    assert response.status_code == 200
    assert response.get_json()["name"] == "Banco Novo"


def test_setting_a_new_default_clears_the_previous_one(client, auth):
    account = create_account(client, auth, "Corretora", "BROKERAGE")
    client.patch(f"/api/accounts/{account['id']}", json={"is_default": True}, headers=auth)
    accounts = list_accounts(client, auth)
    defaults = [item["name"] for item in accounts if item["is_default"]]
    assert defaults == ["Corretora"]


def test_archiving_hides_the_account_but_keeps_its_transactions(client, auth):
    account = create_account(client, auth, "Conta Antiga")
    client.post(
        "/api/transactions",
        json={
            "amount": 40,
            "date": "2026-03-02",
            "category": "Lazer",
            "type": "EXPENSE",
            "account_id": account["id"],
        },
        headers=auth,
    )

    response = client.delete(f"/api/accounts/{account['id']}", headers=auth)
    assert response.status_code == 200
    assert response.get_json() == {"archived": True, "transactions": 1}

    names = [item["name"] for item in list_accounts(client, auth)]
    assert "Conta Antiga" not in names
    assert "Conta Antiga" in [
        item["name"] for item in list_accounts(client, auth, include_archived="1")
    ]
    assert len(client.get("/api/transactions", headers=auth).get_json()) == 1


def test_the_last_active_account_cannot_be_archived(client, auth):
    only_account = list_accounts(client, auth)[0]
    response = client.delete(f"/api/accounts/{only_account['id']}", headers=auth)
    assert response.status_code == 409


def test_archived_account_cannot_receive_new_transactions(client, auth):
    account = create_account(client, auth, "Encerrada")
    client.delete(f"/api/accounts/{account['id']}", headers=auth)
    response = client.post(
        "/api/transactions",
        json={
            "amount": 10,
            "date": "2026-03-02",
            "category": "Lazer",
            "type": "EXPENSE",
            "account_id": account["id"],
        },
        headers=auth,
    )
    assert response.status_code == 400


# --------------------------------------------------------------------------
# Transferencias
# --------------------------------------------------------------------------


def test_transfer_moves_money_without_changing_the_consolidated_total(client, auth):
    origin = list_accounts(client, auth)[0]
    destination = create_account(client, auth, "Poupanca", "SAVINGS")

    client.post(
        "/api/transactions",
        json={
            "amount": 1000,
            "date": "2026-03-01",
            "category": "Receita",
            "type": "INCOME",
            "account_id": origin["id"],
        },
        headers=auth,
    )
    response = client.post(
        "/api/transfers",
        json={
            "amount": 300,
            "date": "2026-03-05",
            "account_id": origin["id"],
            "transfer_account_id": destination["id"],
        },
        headers=auth,
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    transfer = response.get_json()
    assert transfer["type"] == "TRANSFER"
    assert transfer["description"] == "Conta Principal -> Poupanca"

    accounts = list_accounts(client, auth)
    assert balance_of(accounts, "Conta Principal") == 700
    assert balance_of(accounts, "Poupanca") == 300
    assert sum(item["balance"] for item in accounts) == 1000


def test_transfer_is_neither_income_nor_expense(client, auth):
    origin = list_accounts(client, auth)[0]
    destination = create_account(client, auth, "Poupanca", "SAVINGS")
    client.post(
        "/api/transfers",
        json={
            "amount": 250,
            "date": "2026-03-05",
            "account_id": origin["id"],
            "transfer_account_id": destination["id"],
        },
        headers=auth,
    )
    types = {item["type"] for item in client.get("/api/transactions", headers=auth).get_json()}
    assert types == {"TRANSFER"}


def test_transfer_to_the_same_account_is_refused(client, auth):
    account = list_accounts(client, auth)[0]
    response = client.post(
        "/api/transfers",
        json={
            "amount": 50,
            "date": "2026-03-05",
            "account_id": account["id"],
            "transfer_account_id": account["id"],
        },
        headers=auth,
    )
    assert response.status_code == 400


def test_transfer_to_another_users_account_is_refused(client, auth, other_user):
    origin = list_accounts(client, auth)[0]
    foreign = list_accounts(client, other_user["headers"])[0]
    response = client.post(
        "/api/transfers",
        json={
            "amount": 50,
            "date": "2026-03-05",
            "account_id": origin["id"],
            "transfer_account_id": foreign["id"],
        },
        headers=auth,
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": 0},
        {"amount": -10},
        {"date": "05/03/2026"},
        {"account_id": "nao-existe"},
        {"transfer_account_id": ""},
    ],
)
def test_invalid_transfer_payloads_are_refused(client, auth, overrides):
    origin = list_accounts(client, auth)[0]
    destination = create_account(client, auth, "Poupanca", "SAVINGS")
    payload = {
        "amount": 100,
        "date": "2026-03-05",
        "account_id": origin["id"],
        "transfer_account_id": destination["id"],
    }
    payload.update(overrides)
    response = client.post("/api/transfers", json=payload, headers=auth)
    assert response.status_code == 400


def test_transfer_cannot_be_created_through_the_plain_transactions_endpoint(client, auth):
    response = client.post(
        "/api/transactions",
        json={"amount": 10, "date": "2026-03-05", "category": "Lazer", "type": "TRANSFER"},
        headers=auth,
    )
    assert response.status_code == 400
    assert "/api/transfers" in response.get_json()["error"]


# --------------------------------------------------------------------------
# Isolamento por user_id
# --------------------------------------------------------------------------


def test_accounts_are_isolated_per_user(client, auth, other_user):
    create_account(client, auth, "Minha Conta")
    names = [item["name"] for item in list_accounts(client, other_user["headers"])]
    assert "Minha Conta" not in names


def test_cannot_patch_another_users_account(client, auth, other_user):
    account = create_account(client, auth, "Minha Conta")
    response = client.patch(
        f"/api/accounts/{account['id']}",
        json={"name": "Sequestrada"},
        headers=other_user["headers"],
    )
    assert response.status_code == 404


def test_cannot_archive_another_users_account(client, auth, other_user):
    account = create_account(client, auth, "Minha Conta")
    response = client.delete(f"/api/accounts/{account['id']}", headers=other_user["headers"])
    assert response.status_code == 404


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/accounts"),
        ("post", "/api/accounts"),
        ("post", "/api/transfers"),
    ],
)
def test_account_endpoints_require_authentication(client, method, path):
    response = getattr(client, method)(path, json={})
    assert response.status_code == 401
