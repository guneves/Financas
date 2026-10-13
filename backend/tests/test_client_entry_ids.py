"""Criacao idempotente do "+ Novo" (migration 024, mobile-docs/steps-to-production.md, fase 3).

O celular grava sem rede e reenvia depois, sem saber se a primeira tentativa
chegou. Cada envio leva um `client_id`; o que estes testes protegem e que a
segunda entrega nao vira um segundo lancamento — nem uma segunda despesa no
mes, nem um saldo movido duas vezes, nem uma fatura com a compra em dobro.
"""

import importlib
import sqlite3
import uuid

import pytest


def new_client_id():
    return str(uuid.uuid4())


def create_account(client, headers, name, initial_balance=0):
    response = client.post(
        "/api/accounts",
        json={"name": name, "type": "CHECKING", "initial_balance": initial_balance},
        headers=headers,
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def create_card(client, headers, name="Cartao do celular"):
    response = client.post(
        "/api/credit-cards",
        headers=headers,
        json={"name": name, "due_day": 10, "closing_day": 3},
    )
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    body = response.get_json()
    return body[0] if isinstance(body, list) else body


def balances(client, headers):
    accounts = client.get("/api/accounts", headers=headers).get_json()
    return {item["name"]: item["balance"] for item in accounts}


def entry_payload(entry_type, client_id, **overrides):
    payload = {
        "amount": 42.5,
        "date": "2026-03-05",
        "category": "Mercado" if entry_type == "EXPENSE" else "Salario",
        "description": "Lancado no celular",
        "type": entry_type,
        "client_id": client_id,
    }
    payload.update(overrides)
    return payload


# --- despesa e receita -------------------------------------------------------

@pytest.mark.parametrize("entry_type", ["EXPENSE", "INCOME"])
def test_second_delivery_of_an_entry_creates_nothing(client, auth, entry_type):
    payload = entry_payload(entry_type, new_client_id())

    first = client.post("/api/transactions", json=payload, headers=auth)
    second = client.post("/api/transactions", json=payload, headers=auth)

    assert first.status_code == 201, first.get_data(as_text=True)
    assert second.status_code == 200, second.get_data(as_text=True)
    assert second.get_json() == first.get_json()

    listed = client.get("/api/transactions", headers=auth).get_json()
    assert len(listed) == 1
    sign = -1 if entry_type == "EXPENSE" else 1
    assert balances(client, auth)["Conta Principal"] == sign * 42.5


def test_entry_with_client_id_is_still_a_typed_entry(client, auth):
    created = client.post(
        "/api/transactions", json=entry_payload("EXPENSE", new_client_id()), headers=auth
    ).get_json()
    # Sem source_type: nada que le "quem gravou" passa a tratar a linha como automatica.
    assert created["source_type"] is None
    assert created["source_id"] is None

    edited = client.patch(
        f"/api/transactions/{created['id']}", json={"amount": 50}, headers=auth
    )
    assert edited.status_code == 200, edited.get_data(as_text=True)
    assert edited.get_json()["amount"] == 50

    removed = client.delete(f"/api/transactions/{created['id']}", headers=auth)
    assert removed.status_code in (200, 204), removed.get_data(as_text=True)
    assert client.get("/api/transactions", headers=auth).get_json() == []


def test_replay_returns_the_entry_as_it_is_now_and_ignores_the_new_payload(client, auth):
    client_id = new_client_id()
    created = client.post(
        "/api/transactions", json=entry_payload("EXPENSE", client_id), headers=auth
    ).get_json()
    client.patch(f"/api/transactions/{created['id']}", json={"amount": 60}, headers=auth)

    replay = client.post(
        "/api/transactions", json=entry_payload("EXPENSE", client_id, amount=999), headers=auth
    )
    assert replay.status_code == 200
    assert replay.get_json()["id"] == created["id"]
    assert replay.get_json()["amount"] == 60
    assert balances(client, auth)["Conta Principal"] == -60


def test_replay_succeeds_after_the_account_was_archived(client, auth):
    # A validacao vem depois da consulta: o envio ja foi aceito uma vez.
    account = create_account(client, auth, "Conta que sera arquivada")
    payload = entry_payload("EXPENSE", new_client_id(), account_id=account["id"])
    first = client.post("/api/transactions", json=payload, headers=auth)
    assert first.status_code == 201, first.get_data(as_text=True)
    archived = client.delete(f"/api/accounts/{account['id']}", headers=auth)
    assert archived.status_code == 200, archived.get_data(as_text=True)

    replay = client.post("/api/transactions", json=payload, headers=auth)
    assert replay.status_code == 200, replay.get_data(as_text=True)
    assert replay.get_json()["id"] == first.get_json()["id"]


def test_entries_without_client_id_are_never_merged(client, auth):
    payload = entry_payload("EXPENSE", None)
    del payload["client_id"]
    first = client.post("/api/transactions", json=payload, headers=auth)
    second = client.post("/api/transactions", json=payload, headers=auth)
    assert first.status_code == 201 and second.status_code == 201
    assert first.get_json()["client_id"] is None
    assert len(client.get("/api/transactions", headers=auth).get_json()) == 2
    assert balances(client, auth)["Conta Principal"] == -85


@pytest.mark.parametrize(
    "bad_client_id",
    ["curto", "x" * 65, "com espaco dentro", "-comeca-com-hifen", 12345678, ["a" * 12]],
)
def test_malformed_client_id_is_refused(client, auth, bad_client_id):
    response = client.post(
        "/api/transactions", json=entry_payload("EXPENSE", bad_client_id), headers=auth
    )
    assert response.status_code == 400
    assert "client_id" in response.get_json()["error"]
    assert client.get("/api/transactions", headers=auth).get_json() == []


def test_same_client_id_from_another_user_does_not_collide(client, user, other_user):
    client_id = new_client_id()
    mine = client.post(
        "/api/transactions", json=entry_payload("EXPENSE", client_id), headers=user["headers"]
    )
    theirs = client.post(
        "/api/transactions",
        json=entry_payload("EXPENSE", client_id, amount=7),
        headers=other_user["headers"],
    )
    assert mine.status_code == 201
    # 201, nao 200: o id do outro usuario nao e visto, nem devolvido.
    assert theirs.status_code == 201, theirs.get_data(as_text=True)
    assert theirs.get_json()["id"] != mine.get_json()["id"]
    assert theirs.get_json()["amount"] == 7

    assert len(client.get("/api/transactions", headers=user["headers"]).get_json()) == 1
    assert len(client.get("/api/transactions", headers=other_user["headers"]).get_json()) == 1


# --- transferencia -----------------------------------------------------------

def test_second_delivery_of_a_transfer_moves_the_money_once(client, auth):
    savings = create_account(client, auth, "Reserva")
    main_id = next(
        item["id"]
        for item in client.get("/api/accounts", headers=auth).get_json()
        if item["name"] == "Conta Principal"
    )
    payload = {
        "amount": 300,
        "date": "2026-03-05",
        "account_id": main_id,
        "transfer_account_id": savings["id"],
        "client_id": new_client_id(),
    }

    first = client.post("/api/transfers", json=payload, headers=auth)
    second = client.post("/api/transfers", json=payload, headers=auth)

    assert first.status_code == 201, first.get_data(as_text=True)
    assert second.status_code == 200, second.get_data(as_text=True)
    assert second.get_json() == first.get_json()
    assert first.get_json()["type"] == "TRANSFER"

    listed = client.get("/api/transactions", headers=auth).get_json()
    assert len(listed) == 1
    after = balances(client, auth)
    assert after["Conta Principal"] == -300
    assert after["Reserva"] == 300


def test_transfer_client_id_is_scoped_to_the_user(client, user, other_user):
    client_id = new_client_id()

    def transfer(person):
        target = create_account(client, person["headers"], "Destino")
        main_id = next(
            item["id"]
            for item in client.get("/api/accounts", headers=person["headers"]).get_json()
            if item["name"] == "Conta Principal"
        )
        return client.post(
            "/api/transfers",
            headers=person["headers"],
            json={
                "amount": 10,
                "date": "2026-03-05",
                "account_id": main_id,
                "transfer_account_id": target["id"],
                "client_id": client_id,
            },
        )

    assert transfer(user).status_code == 201
    assert transfer(other_user).status_code == 201


def test_malformed_client_id_is_refused_on_a_transfer(client, auth):
    savings = create_account(client, auth, "Reserva")
    main_id = next(
        item["id"]
        for item in client.get("/api/accounts", headers=auth).get_json()
        if item["name"] == "Conta Principal"
    )
    response = client.post(
        "/api/transfers",
        headers=auth,
        json={
            "amount": 10,
            "date": "2026-03-05",
            "account_id": main_id,
            "transfer_account_id": savings["id"],
            "client_id": "curto",
        },
    )
    assert response.status_code == 400
    assert client.get("/api/transactions", headers=auth).get_json() == []


# --- compra no cartao --------------------------------------------------------

def purchase_payload(card, client_id, **overrides):
    payload = {
        "card_id": card["id"],
        "category": "Compras",
        "description": "Compra pelo celular",
        "total_amount": 100.0,
        "purchase_date": "2026-03-01",
        "installments": 3,
        "client_id": client_id,
    }
    payload.update(overrides)
    return payload


def test_second_delivery_of_an_installment_purchase_creates_no_extra_installment(client, auth):
    card = create_card(client, auth)
    payload = purchase_payload(card, new_client_id())

    first = client.post("/api/cc-expenses/purchases", json=payload, headers=auth)
    second = client.post("/api/cc-expenses/purchases", json=payload, headers=auth)

    assert first.status_code == 201, first.get_data(as_text=True)
    assert second.status_code == 200, second.get_data(as_text=True)
    assert second.get_json() == first.get_json()

    rows = first.get_json()
    assert [row["installment_info"] for row in rows] == ["1/3", "2/3", "3/3"]
    assert len({row["client_id"] for row in rows}) == 1

    listed = client.get("/api/cc-expenses", headers=auth).get_json()
    assert len(listed) == 3
    # 100 / 3 nao fecha em centavos: o total continua sendo o da compra, uma vez.
    assert sum(row["amount"] for row in listed) == pytest.approx(100.0)


def test_single_installment_purchase_is_idempotent_too(client, auth):
    card = create_card(client, auth)
    payload = purchase_payload(card, new_client_id(), installments=1)
    first = client.post("/api/cc-expenses/purchases", json=payload, headers=auth)
    second = client.post("/api/cc-expenses/purchases", json=payload, headers=auth)
    assert (first.status_code, second.status_code) == (201, 200)
    assert len(client.get("/api/cc-expenses", headers=auth).get_json()) == 1


def test_purchases_without_client_id_are_never_merged(client, auth):
    card = create_card(client, auth)
    payload = purchase_payload(card, None, installments=1)
    del payload["client_id"]
    assert client.post("/api/cc-expenses/purchases", json=payload, headers=auth).status_code == 201
    assert client.post("/api/cc-expenses/purchases", json=payload, headers=auth).status_code == 201
    assert len(client.get("/api/cc-expenses", headers=auth).get_json()) == 2


def test_purchase_client_id_from_another_user_does_not_collide(client, user, other_user):
    client_id = new_client_id()
    mine = client.post(
        "/api/cc-expenses/purchases",
        json=purchase_payload(create_card(client, user["headers"]), client_id),
        headers=user["headers"],
    )
    theirs = client.post(
        "/api/cc-expenses/purchases",
        json=purchase_payload(create_card(client, other_user["headers"]), client_id, installments=2),
        headers=other_user["headers"],
    )
    assert mine.status_code == 201
    assert theirs.status_code == 201, theirs.get_data(as_text=True)
    assert len(theirs.get_json()) == 2
    assert {row["user_id"] for row in theirs.get_json()} == {other_user["id"]}
    assert len(client.get("/api/cc-expenses", headers=user["headers"]).get_json()) == 3


def test_malformed_client_id_is_refused_on_a_purchase(client, auth):
    card = create_card(client, auth)
    response = client.post(
        "/api/cc-expenses/purchases", json=purchase_payload(card, "curto"), headers=auth
    )
    assert response.status_code == 400
    assert client.get("/api/cc-expenses", headers=auth).get_json() == []


# --- o mesmo id na rota errada -------------------------------------------------

def test_client_id_of_an_expense_is_refused_as_a_transfer_and_the_other_way(client, auth):
    savings = create_account(client, auth, "Reserva")
    main_id = next(
        item["id"]
        for item in client.get("/api/accounts", headers=auth).get_json()
        if item["name"] == "Conta Principal"
    )
    expense_id = new_client_id()
    transfer_id = new_client_id()
    transfer_payload = {
        "amount": 10,
        "date": "2026-03-05",
        "account_id": main_id,
        "transfer_account_id": savings["id"],
    }
    assert client.post(
        "/api/transactions", json=entry_payload("EXPENSE", expense_id), headers=auth
    ).status_code == 201
    assert client.post(
        "/api/transfers", json={**transfer_payload, "client_id": transfer_id}, headers=auth
    ).status_code == 201

    # Devolver 200 aqui diria "transferencia gravada" mostrando uma despesa.
    as_transfer = client.post(
        "/api/transfers", json={**transfer_payload, "client_id": expense_id}, headers=auth
    )
    as_expense = client.post(
        "/api/transactions", json=entry_payload("EXPENSE", transfer_id), headers=auth
    )
    assert as_transfer.status_code == 409
    assert as_expense.status_code == 409
    assert len(client.get("/api/transactions", headers=auth).get_json()) == 2


# --- duas entregas ao mesmo tempo -----------------------------------------------

def blind_first_lookup(monkeypatch, module_name, function_name):
    """A primeira consulta nao ve nada, como a entrega que chegou junto com a outra."""
    module = importlib.import_module(module_name)
    real = getattr(module, function_name)
    calls = {"count": 0}

    def lookup(conn, user_id, client_id):
        calls["count"] += 1
        if calls["count"] == 1:
            return [] if function_name == "fetch_purchase_by_client_id" else None
        return real(conn, user_id, client_id)

    # Patch onde o nome e lido: cada rota importou a funcao pelo nome.
    monkeypatch.setattr(module, function_name, lookup)


def test_concurrent_delivery_of_an_entry_ends_in_one_row(client, auth, monkeypatch):
    payload = entry_payload("EXPENSE", new_client_id())
    first = client.post("/api/transactions", json=payload, headers=auth)
    blind_first_lookup(monkeypatch, "routes.transactions", "fetch_transaction_by_client_id")

    second = client.post("/api/transactions", json=payload, headers=auth)

    assert second.status_code == 200, second.get_data(as_text=True)
    assert second.get_json() == first.get_json()
    assert len(client.get("/api/transactions", headers=auth).get_json()) == 1
    assert balances(client, auth)["Conta Principal"] == -42.5


def test_concurrent_delivery_of_a_transfer_ends_in_one_row(client, auth, monkeypatch):
    savings = create_account(client, auth, "Reserva")
    main_id = next(
        item["id"]
        for item in client.get("/api/accounts", headers=auth).get_json()
        if item["name"] == "Conta Principal"
    )
    payload = {
        "amount": 300,
        "date": "2026-03-05",
        "account_id": main_id,
        "transfer_account_id": savings["id"],
        "client_id": new_client_id(),
    }
    first = client.post("/api/transfers", json=payload, headers=auth)
    blind_first_lookup(monkeypatch, "routes.accounts", "fetch_transaction_by_client_id")

    second = client.post("/api/transfers", json=payload, headers=auth)

    assert second.status_code == 200, second.get_data(as_text=True)
    assert second.get_json() == first.get_json()
    assert balances(client, auth) == {"Conta Principal": -300, "Reserva": 300}


def test_concurrent_delivery_of_a_purchase_leaves_no_half_written_installments(client, auth, monkeypatch):
    card = create_card(client, auth)
    payload = purchase_payload(card, new_client_id())
    first = client.post("/api/cc-expenses/purchases", json=payload, headers=auth)
    blind_first_lookup(monkeypatch, "routes.cards", "fetch_purchase_by_client_id")

    second = client.post("/api/cc-expenses/purchases", json=payload, headers=auth)

    assert second.status_code == 200, second.get_data(as_text=True)
    assert second.get_json() == first.get_json()
    listed = client.get("/api/cc-expenses", headers=auth).get_json()
    assert len(listed) == 3
    assert sum(row["amount"] for row in listed) == pytest.approx(100.0)


# --- o indice e a ultima linha de defesa --------------------------------------

def test_unique_indexes_refuse_a_second_row_for_the_same_delivery(client, auth, user, app_module):
    """Duas entregas simultaneas passam as duas pela consulta; quem segura e o indice."""
    db = importlib.import_module("db")
    client_id = new_client_id()
    created = client.post(
        "/api/transactions", json=entry_payload("EXPENSE", client_id), headers=auth
    ).get_json()
    card = create_card(client, auth)
    purchase = client.post(
        "/api/cc-expenses/purchases", json=purchase_payload(card, client_id), headers=auth
    ).get_json()

    conn = db.get_db()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO transactions (id, user_id, account_id, amount, date, category, type, client_id)
                VALUES (?, ?, ?, 1, '2026-03-05', 'Mercado', 'EXPENSE', ?)
                """,
                (db.new_id(), user["id"], created["account_id"], client_id),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO cc_expenses
                (id, user_id, card_id, category, description, amount, purchase_date,
                 invoice_month, invoice_year, installment_info, status, client_id)
                VALUES (?, ?, ?, 'Compras', 'x', 1, '2026-03-01', 3, 2026, ?, 'OPEN', ?)
                """,
                (db.new_id(), user["id"], card["id"], purchase[0]["installment_info"], client_id),
            )
    finally:
        conn.rollback()
        conn.close()
