"""Pluggy (027, 028): o extrato do banco espera o dono em Aprovar, e cada compra continua um lancamento so.

A Pluggy e falsa aqui (FakePluggy, posta no lugar das funcoes de pluggy_client
que o app chama); a regra e real. O que estes testes protegem:

- nada entra no extrato sem o dono aprovar (Aprovar, /api/inbox);
- sincronizar de novo nao grava nada (o livro pluggy_transactions);
- so entra o que tem data a partir de `since`;
- uma transacao que confirma um lancamento do dono (digitado, do celular,
  importado) marca esse lancamento em vez de criar outro; com dois parecidos,
  ou com uma transferencia/fatura parecida, nada e gravado ate o dono decidir;
- no cartao, a compra aprovada entra pela regra da fatura, com as parcelas da Pluggy;
- o que a Pluggy muda ou apaga depois e seguido no que nasceu dela;
- o caminho inverso: o celular confirma algo que a Pluggy ja trouxe, e o
  servidor confirma a linha do banco em vez de criar outra;
- user_id em tudo, e nada vai a rede sem credenciais.
"""

import importlib
import uuid
from datetime import date

import pytest

import pluggy_client

ITEM = "11111111-2222-3333-4444-555555555555"
BANK = "aaaaaaaa-0000-0000-0000-000000000001"
OTHER_BANK = "aaaaaaaa-0000-0000-0000-000000000002"
CARD = "cccccccc-0000-0000-0000-000000000001"
TODAY = date(2026, 10, 17)


def raw(tx_id, when, amount, direction="DEBIT", description="COMPRA", status="POSTED", **card):
    item = {
        "id": tx_id,
        "description": description,
        "currencyCode": "BRL",
        "amount": -amount if direction == "DEBIT" else amount,
        "date": f"{when}T03:00:00.000Z",
        "type": direction,
        "status": status,
        "updatedAt": "2026-10-17T10:00:00.000Z",
    }
    if card:
        item["creditCardMetadata"] = card
    return item


class FakePluggy:
    def __init__(self):
        self.transactions = {}
        self.calls = []
        self.failing = set()

    def put(self, account, *items):
        self.transactions.setdefault(account, []).extend(items)

    def drop(self, account, tx_id):
        self.transactions[account] = [item for item in self.transactions[account] if item["id"] != tx_id]

    def edit(self, account, tx_id, **changes):
        for item in self.transactions[account]:
            if item["id"] == tx_id:
                item.update(changes)

    def list_transactions(self, account_id, date_from, date_to=None, account_type="BANK"):
        self.calls.append((account_id, date_from))
        if account_id in self.failing:
            raise pluggy_client.PluggyUnavailableError("fora do ar")
        found = []
        for item in self.transactions.get(account_id, []):
            if item["date"][:10] < date_from:
                continue
            parsed = pluggy_client.parse_transaction(dict(item, accountId=account_id), account_type)
            if parsed:
                found.append(parsed)
        return found

    def get_item(self, item_id):
        return pluggy_client.PluggyItem(
            id=item_id, status="UPDATED", execution_status="SUCCESS",
            connector_name="Itaú", last_updated_at="2026-10-17T09:00:00.000Z",
        )

    def list_accounts(self, item_id):
        return [
            pluggy_client.PluggyAccount(BANK, item_id, "BANK", "CHECKING_ACCOUNT", "0001/12345-6", "Conta Corrente", "BRL"),
            pluggy_client.PluggyAccount(CARD, item_id, "CREDIT", "CREDIT_CARD", "1234", "Itau Visa", "BRL"),
        ]


@pytest.fixture()
def sync_module(app_module):
    return importlib.import_module("services.pluggy_sync")


@pytest.fixture()
def pluggy(app_module, sync_module, monkeypatch):
    monkeypatch.setenv("PLUGGY_CLIENT_ID", "client-id-de-teste")
    monkeypatch.setenv("PLUGGY_CLIENT_SECRET", "segredo")
    fake = FakePluggy()
    monkeypatch.setattr(pluggy_client, "get_item", fake.get_item)
    monkeypatch.setattr(pluggy_client, "list_accounts", fake.list_accounts)
    monkeypatch.setattr(pluggy_client, "list_transactions", fake.list_transactions)
    monkeypatch.setattr(pluggy_client, "get_api_key", lambda force=False: "chave")
    sync_module.reset_sync_throttle()
    monkeypatch.setattr(sync_module, "local_today", lambda: TODAY)
    monkeypatch.setattr(importlib.import_module("routes.pluggy"), "local_today", lambda: TODAY)
    return fake


def create_account(client, auth, name="Itaú"):
    response = client.post("/api/accounts", json={"name": name, "type": "CHECKING"}, headers=auth)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["id"]


def create_card(client, auth, name="Itaú Visa"):
    response = client.post(
        "/api/credit-cards", json={"name": name, "due_day": 10, "closing_day": 3}, headers=auth,
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["id"]


def add_item(client, auth):
    response = client.post("/api/pluggy/items", json={"item_id": ITEM}, headers=auth)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["id"]


def link(client, auth, item_row, pluggy_account, *, account_id=None, card_id=None, since="2026-10-01"):
    payload = {"item": item_row, "since": since, "name": "conta da Pluggy"}
    if account_id:
        payload.update(type="BANK", account_id=account_id)
    else:
        payload.update(type="CREDIT", card_id=card_id)
    response = client.put(f"/api/pluggy/links/{pluggy_account}", json=payload, headers=auth)
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    return response.get_json()


def run_sync(client, auth):
    response = client.post("/api/pluggy/sync", json={"force": True}, headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def inbox_items(client, auth, view="pending"):
    response = client.get(f"/api/inbox?view={view}", headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["items"]


def approve(client, auth, item, **payload):
    response = client.post(
        f"/api/inbox/{item['id']}/approve", json={"version": item["version"], **payload}, headers=auth,
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def approve_all(client, auth):
    items = inbox_items(client, auth)
    for item in items:
        approve(client, auth, item)
    return len(items)


def sync_and_approve(client, auth):
    """Sincroniza e aprova tudo como veio: o que antes entrava sozinho."""
    body = run_sync(client, auth)
    body["approved"] = approve_all(client, auth)
    return body


def rows(client, auth, account_id=None):
    items = client.get("/api/transactions", headers=auth).get_json()
    if account_id:
        items = [item for item in items if item["account_id"] == account_id]
    return items


def card_rows(client, auth, card_id):
    return [item for item in client.get("/api/cc-expenses", headers=auth).get_json() if item["card_id"] == card_id]


def ledger(db_module, user, pluggy_id):
    with db_module.get_db() as conn:
        return conn.execute(
            "SELECT * FROM pluggy_transactions WHERE user_id = ? AND pluggy_id = ?",
            (user["id"], pluggy_id),
        ).fetchone()


@pytest.fixture()
def bank(client, auth, pluggy):
    """Uma conta do app ligada a conta corrente da Pluggy, desde 01/10."""
    account_id = create_account(client, auth)
    item_row = add_item(client, auth)
    link(client, auth, item_row, BANK, account_id=account_id)
    return {"account_id": account_id, "item": item_row}


@pytest.fixture()
def card(client, auth, pluggy):
    card_id = create_card(client, auth)
    item_row = add_item(client, auth)
    link(client, auth, item_row, CARD, card_id=card_id)
    return {"card_id": card_id, "item": item_row}


class TestWithoutCredentials:
    def test_sync_says_so_and_never_reaches_the_network(self, client, auth, monkeypatch, sync_module):
        sync_module.reset_sync_throttle()
        monkeypatch.setattr(pluggy_client, "list_transactions", lambda *a, **k: pytest.fail("foi a rede"))
        monkeypatch.setattr(pluggy_client, "get_item", lambda *a, **k: pytest.fail("foi a rede"))
        body = client.post("/api/pluggy/sync", json={"force": True}, headers=auth).get_json()
        assert body["status"] == "not_configured"
        assert "PLUGGY_CLIENT_ID" in body["message"]
        status = client.get("/api/pluggy", headers=auth).get_json()
        assert status["configured"] is False
        # conftest deixa as duas vazias: estao no ambiente, sem valor.
        assert status["setup"] == {
            "missing": [],
            "empty": ["PLUGGY_CLIENT_ID", "PLUGGY_CLIENT_SECRET"],
            "unknown_names": [],
        }

    def test_a_connection_needs_the_credentials(self, client, auth):
        response = client.post("/api/pluggy/items", json={"item_id": ITEM}, headers=auth)
        assert response.status_code == 400
        assert "PLUGGY_CLIENT_ID" in response.get_json()["error"]


class TestConnections:
    def test_an_item_is_checked_on_pluggy(self, client, auth, pluggy, monkeypatch):
        def missing(_item_id):
            raise pluggy_client.PluggyHTTPError(404, "Item not found")

        monkeypatch.setattr(pluggy_client, "get_item", missing)
        response = client.post("/api/pluggy/items", json={"item_id": ITEM}, headers=auth)
        assert response.status_code == 400

    def test_the_same_item_twice_is_refused(self, client, auth, pluggy):
        add_item(client, auth)
        response = client.post("/api/pluggy/items", json={"item_id": ITEM}, headers=auth)
        assert response.status_code == 409

    def test_accounts_come_with_their_link(self, client, auth, bank):
        accounts = client.get(f"/api/pluggy/items/{bank['item']}/accounts", headers=auth).get_json()
        by_id = {item["id"]: item for item in accounts}
        assert by_id[BANK]["link"]["account_id"] == bank["account_id"]
        assert by_id[CARD]["link"] is None
        assert by_id[CARD]["type"] == "CREDIT"

    def test_removing_the_item_keeps_every_entry(self, client, auth, bank, pluggy):
        pluggy.put(BANK, raw("t1", "2026-10-10", 50))
        sync_and_approve(client, auth)
        response = client.delete(f"/api/pluggy/items/{bank['item']}", headers=auth)
        assert response.status_code == 200
        assert client.get("/api/pluggy", headers=auth).get_json()["links"] == []
        assert len(rows(client, auth, bank["account_id"])) == 1

    def test_a_link_needs_an_account_of_the_user(self, client, auth, other_user, pluggy):
        item_row = add_item(client, auth)
        foreign = create_account(client, other_user["headers"], "Do outro")
        response = client.put(
            f"/api/pluggy/links/{BANK}",
            json={"item": item_row, "type": "BANK", "account_id": foreign},
            headers=auth,
        )
        assert response.status_code == 400

    def test_since_defaults_to_today(self, client, auth, pluggy):
        account_id = create_account(client, auth)
        item_row = add_item(client, auth)
        response = client.put(
            f"/api/pluggy/links/{BANK}",
            json={"item": item_row, "type": "BANK", "account_id": account_id},
            headers=auth,
        )
        assert response.status_code == 201
        assert response.get_json()["since"] == "2026-10-17"


class TestBankSync:
    def test_nothing_enters_the_extrato_before_the_owner_approves(self, client, auth, bank, pluggy, db_module, user):
        pluggy.put(BANK, raw("t1", "2026-10-10", 45.9, description="PADARIA"))
        body = run_sync(client, auth)
        assert (body["created"], body["review"]) == (0, 1)
        assert rows(client, auth, bank["account_id"]) == []
        [item] = inbox_items(client, auth)
        assert (item["entry_type"], item["amount"], item["account_id"]) == ("EXPENSE", 45.9, bank["account_id"])
        assert item["occurred_at"] == "2026-10-10"
        assert item["ready"] is True
        assert item["sources"][0]["source"] == "pluggy"
        # A data como a Pluggy mandou fica guardada inteira.
        assert item["sources"][0]["date_raw"] == "2026-10-10T03:00:00.000Z"
        assert ledger(db_module, user, "t1")["state"] == "REVIEW"
        assert client.get("/api/inbox/count", headers=auth).get_json()["pending_count"] == 1

    def test_debits_and_credits_become_entries_once(self, client, auth, bank, pluggy):
        pluggy.put(
            BANK,
            raw("t1", "2026-10-10", 45.9, description="PADARIA"),
            raw("t2", "2026-10-11", 1200, direction="CREDIT", description="SALARIO"),
        )
        first = sync_and_approve(client, auth)
        assert first["status"] == "ok"
        assert (first["review"], first["approved"]) == (2, 2)

        items = {item["description"]: item for item in rows(client, auth, bank["account_id"])}
        assert items["PADARIA"]["type"] == "EXPENSE"
        assert items["PADARIA"]["amount"] == 45.9
        assert items["PADARIA"]["source_type"] == "PLUGGY"
        assert items["PADARIA"]["external_id"] == "pluggy:t1"
        assert items["PADARIA"]["category"] == "Outros"
        assert items["SALARIO"]["type"] == "INCOME"
        assert items["SALARIO"]["category"] == "Receita"
        assert items["SALARIO"]["occurred_at"] == "2026-10-11"

        second = run_sync(client, auth)
        assert (second["created"], second["review"]) == (0, 0)
        assert inbox_items(client, auth) == []
        assert len(rows(client, auth, bank["account_id"])) == 2

    def test_only_what_is_on_or_after_since(self, client, auth, bank, pluggy):
        pluggy.put(BANK, raw("old", "2026-09-30", 10), raw("new", "2026-10-01", 20))
        sync_and_approve(client, auth)
        assert [item["amount"] for item in rows(client, auth, bank["account_id"])] == [20]
        # A primeira leitura vai ate a vespera de `since` (o `from` da Pluggy pode ser "maior que").
        assert pluggy.calls[0] == (BANK, "2026-09-30")

    def test_after_the_first_sync_it_reads_the_recent_window(self, client, auth, pluggy):
        account_id = create_account(client, auth)
        item_row = add_item(client, auth)
        link(client, auth, item_row, BANK, account_id=account_id, since="2026-01-01")
        run_sync(client, auth)
        run_sync(client, auth)
        assert pluggy.calls[0] == (BANK, "2025-12-31")
        # 45 dias antes de 17/10, menos a vespera.
        assert pluggy.calls[1] == (BANK, "2026-09-01")

    def test_changing_since_reads_everything_again(self, client, auth, bank, pluggy):
        pluggy.put(BANK, raw("t1", "2026-09-20", 10))
        sync_and_approve(client, auth)
        assert rows(client, auth, bank["account_id"]) == []
        link(client, auth, bank["item"], BANK, account_id=bank["account_id"], since="2026-09-15")
        sync_and_approve(client, auth)
        assert [item["amount"] for item in rows(client, auth, bank["account_id"])] == [10]

    def test_an_import_rule_categorizes(self, client, auth, bank, pluggy):
        response = client.post(
            "/api/import-rules", json={"pattern": "uber", "category": "Transporte"}, headers=auth,
        )
        assert response.status_code == 201, response.get_data(as_text=True)
        pluggy.put(BANK, raw("t1", "2026-10-10", 23.4, description="UBER *TRIP"))
        run_sync(client, auth)
        assert inbox_items(client, auth)[0]["category"] == "Transporte"
        approve_all(client, auth)
        assert rows(client, auth, bank["account_id"])[0]["category"] == "Transporte"
        rule = client.get("/api/import-rules", headers=auth).get_json()["items"][0]
        assert rule["hits"] == 1

    def test_pending_waits_for_posted(self, client, auth, bank, pluggy, db_module, user):
        pluggy.put(BANK, raw("t1", "2026-10-15", 30, status="PENDING"))
        body = run_sync(client, auth)
        assert body["waiting"] == 1
        assert rows(client, auth, bank["account_id"]) == []
        assert ledger(db_module, user, "t1")["state"] == "WAITING"

        pluggy.edit(BANK, "t1", status="POSTED")
        sync_and_approve(client, auth)
        assert len(rows(client, auth, bank["account_id"])) == 1

    def test_pending_can_be_imported_when_asked(self, client, auth, bank, pluggy, sync_module, monkeypatch):
        monkeypatch.setattr(sync_module, "PLUGGY_IMPORT_PENDING", True)
        pluggy.put(BANK, raw("t1", "2026-10-15", 30, status="PENDING"))
        sync_and_approve(client, auth)
        assert len(rows(client, auth, bank["account_id"])) == 1

    def test_without_force_it_runs_once_in_a_while(self, client, auth, bank, pluggy):
        first = client.post("/api/pluggy/sync", json={}, headers=auth).get_json()
        second = client.post("/api/pluggy/sync", json={}, headers=auth).get_json()
        assert first["status"] == "ok"
        assert second["status"] == "skipped"
        assert run_sync(client, auth)["status"] == "ok"

    def test_a_failed_account_is_not_read_as_deleted(self, client, auth, bank, pluggy, db_module, user):
        pluggy.put(BANK, raw("t1", "2026-10-10", 50))
        sync_and_approve(client, auth)
        pluggy.failing.add(BANK)
        body = run_sync(client, auth)
        assert body["status"] == "error"
        assert body["failed"]
        assert len(rows(client, auth, bank["account_id"])) == 1
        assert ledger(db_module, user, "t1")["state"] == "IMPORTED"
        status = client.get("/api/pluggy", headers=auth).get_json()
        assert status["provider"]["consecutive_failures"] >= 1


class TestFollowingPluggy:
    def test_a_changed_amount_follows_on_what_came_from_pluggy(self, client, auth, bank, pluggy):
        pluggy.put(BANK, raw("t1", "2026-10-10", 50))
        sync_and_approve(client, auth)
        pluggy.edit(BANK, "t1", amount=-55.5, date="2026-10-11T03:00:00.000Z")
        body = run_sync(client, auth)
        assert body["updated"] == 1
        item = rows(client, auth, bank["account_id"])[0]
        assert (item["amount"], item["date"]) == (55.5, "2026-10-11")

    def test_what_the_owner_corrected_does_not_follow(self, client, auth, bank, pluggy):
        pluggy.put(BANK, raw("t1", "2026-10-10", 50))
        run_sync(client, auth)
        approve(client, auth, inbox_items(client, auth)[0], amount=48)
        pluggy.edit(BANK, "t1", amount=-55.5)
        assert run_sync(client, auth)["updated"] == 0
        assert rows(client, auth, bank["account_id"])[0]["amount"] == 48

    def test_a_waiting_item_follows_until_the_owner_touches_it(self, client, auth, bank, pluggy):
        pluggy.put(BANK, raw("t1", "2026-10-10", 50))
        run_sync(client, auth)
        pluggy.edit(BANK, "t1", amount=-52, date="2026-10-11T03:00:00.000Z")
        assert run_sync(client, auth)["updated"] == 1
        [item] = inbox_items(client, auth)
        assert (item["amount"], item["occurred_at"]) == (52, "2026-10-11")
        response = client.patch(f"/api/inbox/{item['id']}", json={"version": item["version"], "amount": 50}, headers=auth)
        assert response.status_code == 200
        pluggy.edit(BANK, "t1", amount=-53)
        run_sync(client, auth)
        assert inbox_items(client, auth)[0]["amount"] == 50

    def test_a_vanished_waiting_transaction_leaves_aprovar(self, client, auth, bank, pluggy):
        pluggy.put(BANK, raw("t1", "2026-10-10", 50))
        run_sync(client, auth)
        pluggy.drop(BANK, "t1")
        assert run_sync(client, auth)["removed"] == 1
        assert inbox_items(client, auth) == []
        assert inbox_items(client, auth, "decided")[0]["state"] == "REMOVED"

    def test_a_deleted_transaction_takes_its_entry_away(self, client, auth, bank, pluggy, db_module, user):
        pluggy.put(BANK, raw("t1", "2026-10-10", 50))
        sync_and_approve(client, auth)
        pluggy.drop(BANK, "t1")
        body = run_sync(client, auth)
        assert body["removed"] == 1
        assert rows(client, auth, bank["account_id"]) == []
        assert ledger(db_module, user, "t1")["state"] == "REMOVED"
        # Nao volta: o livro sabe que sumiu.
        run_sync(client, auth)
        assert rows(client, auth, bank["account_id"]) == []

    def test_a_deleted_transaction_with_a_receipt_keeps_its_entry(self, client, auth, bank, pluggy, db_module, user):
        pluggy.put(BANK, raw("t1", "2026-10-10", 50))
        sync_and_approve(client, auth)
        entry = rows(client, auth, bank["account_id"])[0]
        with db_module.get_db() as conn:
            conn.execute(
                """
                INSERT INTO transaction_attachments
                (id, user_id, transaction_id, stored_name, original_name, content_type, size_bytes, sha256)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), user["id"], entry["id"], f"{uuid.uuid4()}.pdf", "nota.pdf",
                 "application/pdf", 10, "0" * 64),
            )
        pluggy.drop(BANK, "t1")
        run_sync(client, auth)
        kept = rows(client, auth, bank["account_id"])
        assert len(kept) == 1
        assert kept[0]["external_id"] is None
        assert ledger(db_module, user, "t1")["reason"] == "kept_receipt"

    def test_the_owner_deleting_an_entry_from_pluggy_is_final(self, client, auth, bank, pluggy):
        pluggy.put(BANK, raw("t1", "2026-10-10", 50))
        sync_and_approve(client, auth)
        entry = rows(client, auth, bank["account_id"])[0]
        assert client.delete(f"/api/transactions/{entry['id']}", headers=auth).status_code == 200
        run_sync(client, auth)
        assert rows(client, auth, bank["account_id"]) == []
        assert inbox_items(client, auth) == []


class TestAttachingToTheOwnersEntries:
    def post_entry(self, client, auth, account_id, amount=45.9, when="2026-10-10", client_id=None, **extra):
        payload = {
            "amount": amount, "date": when, "category": "Mercado", "description": "Do celular",
            "type": "EXPENSE", "account_id": account_id, **extra,
        }
        if client_id:
            payload["client_id"] = client_id
        response = client.post("/api/transactions", json=payload, headers=auth)
        assert response.status_code == 201, response.get_data(as_text=True)
        return response.get_json()

    def test_one_candidate_is_confirmed_not_duplicated(self, client, auth, bank, pluggy, db_module, user):
        mine = self.post_entry(client, auth, bank["account_id"], client_id=str(uuid.uuid4()))
        pluggy.put(BANK, raw("t1", "2026-10-11", 45.9, description="SUPERMERCADO X"))
        body = run_sync(client, auth)
        assert (body["created"], body["attached"]) == (0, 1)

        items = rows(client, auth, bank["account_id"])
        assert len(items) == 1
        assert items[0]["id"] == mine["id"]
        assert items[0]["external_id"] == "pluggy:t1"
        # Continua do dono: descricao, data e origem como estavam.
        assert items[0]["source_type"] is None
        assert (items[0]["description"], items[0]["date"]) == ("Do celular", "2026-10-10")
        assert '"date": "2026-10-11"' in ledger(db_module, user, "t1")["difference"]

    def test_a_typed_entry_without_client_id_is_a_candidate_too(self, client, auth, bank, pluggy):
        self.post_entry(client, auth, bank["account_id"])
        pluggy.put(BANK, raw("t1", "2026-10-10", 45.9))
        assert run_sync(client, auth)["attached"] == 1

    def test_outside_the_date_window_it_is_a_new_entry(self, client, auth, bank, pluggy):
        self.post_entry(client, auth, bank["account_id"], when="2026-10-01")
        pluggy.put(BANK, raw("t1", "2026-10-05", 45.9))
        assert run_sync(client, auth)["review"] == 1
        assert inbox_items(client, auth)[0]["candidates"] == []
        approve_all(client, auth)
        assert len(rows(client, auth, bank["account_id"])) == 2

    def test_no_match_across_accounts(self, client, auth, bank, pluggy):
        other = create_account(client, auth, "Outra")
        self.post_entry(client, auth, other)
        pluggy.put(BANK, raw("t1", "2026-10-10", 45.9))
        assert run_sync(client, auth)["review"] == 1
        assert inbox_items(client, auth)[0]["candidates"] == []

    def test_no_match_across_types(self, client, auth, bank, pluggy):
        self.post_entry(client, auth, bank["account_id"], type="INCOME")
        pluggy.put(BANK, raw("t1", "2026-10-10", 45.9))
        assert run_sync(client, auth)["review"] == 1
        assert inbox_items(client, auth)[0]["candidates"] == []

    def test_two_candidates_wait_for_the_owner(self, client, auth, bank, pluggy):
        first = self.post_entry(client, auth, bank["account_id"], when="2026-10-09")
        second = self.post_entry(client, auth, bank["account_id"], when="2026-10-11")
        pluggy.put(BANK, raw("t1", "2026-10-10", 45.9))
        body = run_sync(client, auth)
        assert body["review"] == 1
        assert len(rows(client, auth, bank["account_id"])) == 2

        review = inbox_items(client, auth)
        assert len(review) == 1
        assert review[0]["reason"] == "several_candidates"
        assert {item["id"] for item in review[0]["candidates"]} == {first["id"], second["id"]}

        decided = approve(client, auth, review[0], candidate={"table": "transactions", "id": second["id"]})
        assert decided["state"] == "MATCHED"
        assert decided["target_id"] == second["id"]
        by_id = {item["id"]: item for item in rows(client, auth, bank["account_id"])}
        assert by_id[second["id"]]["external_id"] == "pluggy:t1"
        assert by_id[first["id"]]["external_id"] is None
        assert inbox_items(client, auth) == []

    def test_the_owner_can_keep_both_or_ignore(self, client, auth, bank, pluggy, db_module, user):
        self.post_entry(client, auth, bank["account_id"], when="2026-10-09")
        self.post_entry(client, auth, bank["account_id"], when="2026-10-11")
        pluggy.put(BANK, raw("t1", "2026-10-10", 45.9), raw("t2", "2026-10-10", 45.9))
        run_sync(client, auth)
        review = inbox_items(client, auth)
        assert len(review) == 2
        by_pluggy = {item["sources"][0]["id"]: item for item in review}
        t1 = ledger(db_module, user, "t1")["id"]
        t2 = ledger(db_module, user, "t2")["id"]

        inserted = approve(client, auth, by_pluggy[t1])
        assert inserted["state"] == "APPROVED"
        assert ledger(db_module, user, "t1")["state"] == "IMPORTED"
        item = by_pluggy[t2]
        dismissed = client.post(f"/api/inbox/{item['id']}/deny", json={"version": item["version"]}, headers=auth)
        assert dismissed.get_json()["state"] == "DENIED"
        assert ledger(db_module, user, "t2")["state"] == "DISMISSED"
        assert len(rows(client, auth, bank["account_id"])) == 3
        # Decidido fica decidido.
        run_sync(client, auth)
        assert len(rows(client, auth, bank["account_id"])) == 3
        assert inbox_items(client, auth) == []
        again = client.post(f"/api/inbox/{item['id']}/approve", json={}, headers=auth)
        assert again.status_code == 409

    def test_attach_only_to_a_listed_candidate(self, client, auth, bank, pluggy):
        self.post_entry(client, auth, bank["account_id"], when="2026-10-09")
        self.post_entry(client, auth, bank["account_id"], when="2026-10-11")
        unrelated = self.post_entry(client, auth, bank["account_id"], amount=1)
        pluggy.put(BANK, raw("t1", "2026-10-10", 45.9))
        run_sync(client, auth)
        review = inbox_items(client, auth)[0]
        response = client.post(
            f"/api/inbox/{review['id']}/approve",
            json={"version": review["version"], "candidate": {"table": "transactions", "id": unrelated["id"]}},
            headers=auth,
        )
        assert response.status_code == 400

    def test_a_transfer_is_never_touched_and_never_doubled(self, client, auth, bank, pluggy):
        savings = create_account(client, auth, "Poupança")
        response = client.post(
            "/api/transfers",
            json={"amount": 300, "date": "2026-10-10", "account_id": bank["account_id"], "transfer_account_id": savings},
            headers=auth,
        )
        assert response.status_code == 201
        transfer = response.get_json()
        pluggy.put(BANK, raw("t1", "2026-10-10", 300, description="PIX ENVIADO"))
        body = run_sync(client, auth)
        assert (body["created"], body["attached"], body["review"]) == (0, 0, 1)

        review = inbox_items(client, auth)[0]
        assert review["reason"] == "out_of_reach"
        assert review["candidates"][0]["kind"] == "transfer"
        approve(client, auth, review, candidate={"table": "transactions", "id": transfer["id"]})
        after = next(item for item in rows(client, auth) if item["id"] == transfer["id"])
        # A transferencia fica intocada: so o livro sabe que e ela.
        assert after["external_id"] is None
        assert after["type"] == "TRANSFER"

        # O lado de chegada, numa conta ligada tambem, confirma a mesma
        # transferencia que o dono ja apontou: nada a decidir de novo.
        item_row = bank["item"]
        link(client, auth, item_row, OTHER_BANK, account_id=savings)
        pluggy.put(OTHER_BANK, raw("t2", "2026-10-10", 300, direction="CREDIT", description="PIX RECEBIDO"))
        body = run_sync(client, auth)
        assert (body["review"], body["attached"]) == (0, 1)
        assert inbox_items(client, auth) == []
        assert len([item for item in rows(client, auth) if item["type"] == "TRANSFER"]) == 1

    def test_an_invoice_payment_is_out_of_reach(self, client, auth, bank, pluggy, db_module, user):
        with db_module.get_db() as conn:
            conn.execute(
                """
                INSERT INTO transactions
                (id, user_id, account_id, amount, date, category, description, type, source_type, source_id)
                VALUES (?, ?, ?, 812.4, '2026-10-10', 'Pagamento Fatura', 'Fatura 10/2026', 'EXPENSE',
                        'CC_AUTOPAY', 'card:2026-10')
                """,
                (str(uuid.uuid4()), user["id"], bank["account_id"]),
            )
        pluggy.put(BANK, raw("t1", "2026-10-10", 812.4, description="PAGTO FATURA CARTAO"))
        body = run_sync(client, auth)
        assert body["review"] == 1
        review = inbox_items(client, auth)[0]
        assert review["candidates"][0]["kind"] == "invoice_payment"
        assert len(rows(client, auth, bank["account_id"])) == 1


class TestCards:
    def test_a_purchase_goes_to_its_invoice(self, client, auth, card, pluggy):
        pluggy.put(CARD, raw("c1", "2026-10-08", 99.9, description="LOJA X"))
        body = run_sync(client, auth)
        assert body["review"] == 1
        assert card_rows(client, auth, card["card_id"]) == []
        [waiting] = inbox_items(client, auth)
        assert (waiting["entry_type"], waiting["card_id"], waiting["amount"]) == ("CARD", card["card_id"], 99.9)
        approve(client, auth, waiting)
        items = card_rows(client, auth, card["card_id"])
        assert len(items) == 1
        item = items[0]
        assert item["installment_info"] == "1/1"
        assert item["amount"] == 99.9
        # Fecha dia 3, vence dia 10: compra de 08/10 cai na fatura de 11/2026.
        assert (item["invoice_month"], item["invoice_year"]) == (11, 2026)
        assert item["source_type"] == "PLUGGY"
        assert item["external_id"] == "pluggy:c1"
        run_sync(client, auth)
        assert len(card_rows(client, auth, card["card_id"])) == 1

    def test_a_card_credit_stays_out(self, client, auth, card, pluggy, db_module, user):
        pluggy.put(CARD, raw("c1", "2026-10-10", 500, direction="CREDIT", description="PAGAMENTO RECEBIDO"))
        body = run_sync(client, auth)
        assert body["skipped"] == 1
        assert card_rows(client, auth, card["card_id"]) == []
        assert ledger(db_module, user, "c1")["reason"] == "card_credit"

    def test_installments_build_the_whole_purchase_once(self, client, auth, card, pluggy):
        pluggy.put(CARD, raw(
            "c1", "2026-10-08", 100, description="TV PARC 01/03",
            installmentNumber=1, totalInstallments=3, purchaseDate="2026-10-08T00:00:00.000Z",
        ))
        run_sync(client, auth)
        [waiting] = inbox_items(client, auth)
        assert (waiting["amount"], waiting["installments"]) == (300, 3)
        approve(client, auth, waiting)
        items = card_rows(client, auth, card["card_id"])
        assert [item["installment_info"] for item in items] == ["1/3", "2/3", "3/3"]
        assert [item["amount"] for item in items] == [100, 100, 100]
        assert [(item["invoice_month"], item["invoice_year"]) for item in items] == [(11, 2026), (12, 2026), (1, 2027)]
        assert len({item["source_id"] for item in items}) == 1

        # A segunda parcela chega no mes seguinte, com outro id: marca a dela,
        # sem passar por Aprovar (a compra ja foi aprovada).
        pluggy.put(CARD, raw(
            "c2", "2026-11-08", 100, description="TV PARC 02/03",
            installmentNumber=2, totalInstallments=3, purchaseDate="2026-10-08T00:00:00.000Z",
        ))
        body = run_sync(client, auth)
        assert (body["attached"], body["review"]) == (1, 0)
        assert inbox_items(client, auth) == []
        items = card_rows(client, auth, card["card_id"])
        assert len(items) == 3
        assert {item["installment_info"]: item["external_id"] for item in items} == {
            "1/3": "pluggy:c1", "2/3": "pluggy:c2", "3/3": None,
        }

    def test_an_installment_of_a_purchase_before_since_stays_out(self, client, auth, card, pluggy, db_module, user):
        pluggy.put(CARD, raw(
            "c5", "2026-10-08", 100, installmentNumber=5, totalInstallments=10,
            purchaseDate="2026-06-08T00:00:00.000Z",
        ))
        run_sync(client, auth)
        assert card_rows(client, auth, card["card_id"]) == []
        assert ledger(db_module, user, "c5")["reason"] == "before_since"

    def test_the_owners_purchase_is_confirmed(self, client, auth, card, pluggy):
        response = client.post(
            "/api/cc-expenses/purchases",
            json={
                "card_id": card["card_id"], "category": "Casa", "description": "TV",
                "total_amount": 300, "purchase_date": "2026-10-08", "installments": 3,
                "client_id": str(uuid.uuid4()),
            },
            headers=auth,
        )
        assert response.status_code == 201
        pluggy.put(CARD, raw(
            "c1", "2026-10-09", 100, installmentNumber=1, totalInstallments=3,
            purchaseDate="2026-10-08T00:00:00.000Z",
        ))
        assert run_sync(client, auth)["attached"] == 1
        pluggy.put(CARD, raw(
            "c2", "2026-11-09", 100, installmentNumber=2, totalInstallments=3,
            purchaseDate="2026-10-08T00:00:00.000Z",
        ))
        assert run_sync(client, auth)["attached"] == 1
        items = card_rows(client, auth, card["card_id"])
        assert len(items) == 3
        assert {item["installment_info"]: item["external_id"] for item in items} == {
            "1/3": "pluggy:c1", "2/3": "pluggy:c2", "3/3": None,
        }
        assert all(item["source_type"] is None for item in items)

    def test_a_different_installment_count_waits_for_the_owner(self, client, auth, card, pluggy):
        client.post(
            "/api/cc-expenses/purchases",
            json={
                "card_id": card["card_id"], "category": "Casa", "description": "TV",
                "total_amount": 300, "purchase_date": "2026-10-08", "installments": 1,
            },
            headers=auth,
        )
        pluggy.put(CARD, raw(
            "c1", "2026-10-08", 100, installmentNumber=1, totalInstallments=3,
            purchaseDate="2026-10-08T00:00:00.000Z",
        ))
        body = run_sync(client, auth)
        assert body["review"] == 1
        assert len(card_rows(client, auth, card["card_id"])) == 1
        review = inbox_items(client, auth)[0]
        assert review["reason"] == "installments_differ"

    def test_a_deleted_purchase_goes_unless_an_installment_was_paid(self, client, auth, card, pluggy, db_module, user):
        pluggy.put(CARD, raw("c1", "2026-10-08", 40), raw("c2", "2026-10-09", 60))
        sync_and_approve(client, auth)
        paid = next(item for item in card_rows(client, auth, card["card_id"]) if item["external_id"] == "pluggy:c2")
        with db_module.get_db() as conn:
            conn.execute("UPDATE cc_expenses SET status = 'PAID' WHERE id = ?", (paid["id"],))
        pluggy.drop(CARD, "c1")
        pluggy.drop(CARD, "c2")
        run_sync(client, auth)
        remaining = card_rows(client, auth, card["card_id"])
        assert [item["id"] for item in remaining] == [paid["id"]]
        assert ledger(db_module, user, "c2")["reason"] == "kept_paid"


class TestTheOtherWayAround:
    """A Pluggy trouxe primeiro; o dono confirma depois (no celular ou no "+ Novo")."""

    def test_typing_what_waits_in_aprovar_takes_its_place(self, client, auth, bank, pluggy, db_module, user):
        pluggy.put(BANK, raw("t1", "2026-10-10", 45.9, description="SUPERMERCADO X"))
        run_sync(client, auth)
        assert len(inbox_items(client, auth)) == 1

        client_id = str(uuid.uuid4())
        payload = {
            "amount": 45.9, "date": "2026-10-11", "category": "Mercado", "description": "Mercado",
            "type": "EXPENSE", "account_id": bank["account_id"], "client_id": client_id,
        }
        response = client.post("/api/transactions", json=payload, headers=auth)
        assert response.status_code == 201, response.get_data(as_text=True)
        body = response.get_json()
        assert body["matched_inbox"] is True
        assert inbox_items(client, auth) == []
        assert inbox_items(client, auth, "decided")[0]["state"] == "MATCHED"
        assert ledger(db_module, user, "t1")["state"] == "ATTACHED"
        [entry] = rows(client, auth, bank["account_id"])
        assert (entry["id"], entry["external_id"], entry["source_type"]) == (body["id"], "pluggy:t1", None)

        # Reenvio do mesmo envio (fila do celular): a mesma linha, nada novo.
        again = client.post("/api/transactions", json=payload, headers=auth)
        assert again.status_code == 200
        assert again.get_json()["id"] == body["id"]
        assert len(rows(client, auth, bank["account_id"])) == 1

    def test_a_confirmed_entry_claims_an_approved_bank_row(self, client, auth, bank, pluggy):
        pluggy.put(BANK, raw("t1", "2026-10-10", 45.9, description="SUPERMERCADO X"))
        sync_and_approve(client, auth)
        bank_row = rows(client, auth, bank["account_id"])[0]

        payload = {
            "amount": 45.9, "date": "2026-10-11", "category": "Mercado", "description": "Mercado",
            "type": "EXPENSE", "account_id": bank["account_id"], "client_id": str(uuid.uuid4()),
        }
        response = client.post("/api/transactions", json=payload, headers=auth)
        assert response.status_code == 200, response.get_data(as_text=True)
        body = response.get_json()
        assert body["matched_bank"] is True
        assert body["id"] == bank_row["id"]
        assert (body["category"], body["description"]) == ("Mercado", "Mercado")
        # Valor e data seguem os do banco.
        assert body["date"] == "2026-10-10"
        assert len(rows(client, auth, bank["account_id"])) == 1

    def test_a_second_purchase_of_the_same_amount_is_a_new_entry(self, client, auth, bank, pluggy):
        pluggy.put(BANK, raw("t1", "2026-10-10", 12))
        run_sync(client, auth)
        for _ in range(2):
            response = client.post(
                "/api/transactions",
                json={
                    "amount": 12, "date": "2026-10-10", "category": "Padaria", "type": "EXPENSE",
                    "account_id": bank["account_id"], "client_id": str(uuid.uuid4()),
                },
                headers=auth,
            )
            assert response.status_code in (200, 201)
        assert len(rows(client, auth, bank["account_id"])) == 2
        assert inbox_items(client, auth) == []

        # Quando a Pluggy traz a segunda compra, ela confirma a do dono.
        pluggy.put(BANK, raw("t2", "2026-10-10", 12))
        body = run_sync(client, auth)
        assert (body["created"], body["attached"]) == (0, 1)
        assert len(rows(client, auth, bank["account_id"])) == 2

    def test_without_client_id_an_approved_row_is_not_claimed(self, client, auth, bank, pluggy):
        pluggy.put(BANK, raw("t1", "2026-10-10", 45.9))
        sync_and_approve(client, auth)
        response = client.post(
            "/api/transactions",
            json={"amount": 45.9, "date": "2026-10-10", "category": "Mercado", "type": "EXPENSE",
                  "account_id": bank["account_id"]},
            headers=auth,
        )
        assert response.status_code == 201
        assert "matched_inbox" not in response.get_json()
        assert len(rows(client, auth, bank["account_id"])) == 2

    def test_typing_a_card_purchase_that_waits_takes_its_place(self, client, auth, card, pluggy):
        pluggy.put(CARD, raw(
            "c1", "2026-10-08", 100, installmentNumber=1, totalInstallments=3,
            purchaseDate="2026-10-08T00:00:00.000Z",
        ))
        run_sync(client, auth)
        response = client.post(
            "/api/cc-expenses/purchases",
            json={
                "card_id": card["card_id"], "category": "Casa", "description": "TV",
                "total_amount": 300, "purchase_date": "2026-10-09", "installments": 3,
                "client_id": str(uuid.uuid4()),
            },
            headers=auth,
        )
        assert response.status_code == 201, response.get_data(as_text=True)
        body = response.get_json()
        assert len(body) == 3
        assert all(item["matched_inbox"] for item in body)
        assert inbox_items(client, auth) == []
        items = card_rows(client, auth, card["card_id"])
        assert {item["installment_info"]: item["external_id"] for item in items} == {
            "1/3": "pluggy:c1", "2/3": None, "3/3": None,
        }

    def test_a_confirmed_card_purchase_claims_the_approved_bank_purchase(self, client, auth, card, pluggy):
        pluggy.put(CARD, raw(
            "c1", "2026-10-08", 100, installmentNumber=1, totalInstallments=3,
            purchaseDate="2026-10-08T00:00:00.000Z",
        ))
        sync_and_approve(client, auth)
        response = client.post(
            "/api/cc-expenses/purchases",
            json={
                "card_id": card["card_id"], "category": "Casa", "description": "TV",
                "total_amount": 300, "purchase_date": "2026-10-09", "installments": 3,
                "client_id": str(uuid.uuid4()),
            },
            headers=auth,
        )
        assert response.status_code == 200, response.get_data(as_text=True)
        body = response.get_json()
        assert len(body) == 3
        assert all(item["matched_bank"] for item in body)
        assert all(item["category"] == "Casa" for item in body)
        assert len(card_rows(client, auth, card["card_id"])) == 3

    def test_a_pending_replaced_by_posted_keeps_the_confirmed_entry(
        self, client, auth, bank, pluggy, sync_module, monkeypatch,
    ):
        monkeypatch.setattr(sync_module, "PLUGGY_IMPORT_PENDING", True)
        pluggy.put(BANK, raw("p1", "2026-10-10", 70, status="PENDING"))
        run_sync(client, auth)
        response = client.post(
            "/api/transactions",
            json={"amount": 70, "date": "2026-10-10", "category": "Farmacia", "type": "EXPENSE",
                  "account_id": bank["account_id"], "client_id": str(uuid.uuid4())},
            headers=auth,
        )
        assert response.status_code == 201
        confirmed = response.get_json()
        assert confirmed["matched_inbox"] is True

        # O banco liquida com outro id: o PENDING some, o POSTED chega.
        pluggy.drop(BANK, "p1")
        pluggy.put(BANK, raw("p2", "2026-10-10", 70))
        run_sync(client, auth)
        items = rows(client, auth, bank["account_id"])
        assert len(items) == 1
        assert items[0]["id"] == confirmed["id"]
        assert items[0]["category"] == "Farmacia"
        assert items[0]["external_id"] == "pluggy:p2"
        assert items[0]["source_type"] is None
        assert inbox_items(client, auth) == []


class TestIsolation:
    def test_another_user_sees_and_decides_nothing(self, client, auth, other_user, bank, pluggy):
        first = client.post(
            "/api/transactions",
            json={"amount": 45.9, "date": "2026-10-09", "category": "X", "type": "EXPENSE", "account_id": bank["account_id"]},
            headers=auth,
        ).get_json()
        client.post(
            "/api/transactions",
            json={"amount": 45.9, "date": "2026-10-11", "category": "X", "type": "EXPENSE", "account_id": bank["account_id"]},
            headers=auth,
        )
        pluggy.put(BANK, raw("t1", "2026-10-10", 45.9))
        run_sync(client, auth)
        review_id = inbox_items(client, auth)[0]["id"]

        other = other_user["headers"]
        status = client.get("/api/pluggy", headers=other).get_json()
        assert (status["items"], status["links"], status["counts"]) == ([], [], {})
        assert client.get("/api/pluggy/review", headers=other).get_json()["differences"] == []
        assert inbox_items(client, other) == []
        response = client.post(
            f"/api/inbox/{review_id}/approve",
            json={"candidate": {"table": "transactions", "id": first["id"]}}, headers=other,
        )
        assert response.status_code == 404
        assert client.delete(f"/api/pluggy/items/{bank['item']}", headers=other).status_code == 404
        assert client.delete(f"/api/pluggy/links/{BANK}", headers=other).status_code == 404
        assert run_sync(client, other)["status"] == "skipped"

    def test_the_same_pluggy_ids_for_two_users_stay_apart(self, client, auth, other_user, bank, pluggy):
        pluggy.put(BANK, raw("t1", "2026-10-10", 10))
        sync_and_approve(client, auth)
        other = other_user["headers"]
        account_id = create_account(client, other, "Dele")
        item_row = add_item(client, other)
        link(client, other, item_row, BANK, account_id=account_id)
        assert sync_and_approve(client, other)["approved"] == 1
        assert len(rows(client, auth, bank["account_id"])) == 1
        assert len(rows(client, other, account_id)) == 1


class TestHealth:
    def test_pluggy_on_the_integrations_card(self, client, auth, monkeypatch, app_module):
        health = importlib.import_module("services.health")
        prices = importlib.import_module("services.prices")
        fixed_income = importlib.import_module("services.fixed_income")
        monkeypatch.setattr(prices, "yf", object())
        monkeypatch.setattr(prices, "download_close_prices", lambda symbols, **kw: {symbols[0]: 38.5})
        monkeypatch.setattr(fixed_income, "fetch_bcb_series", lambda *a, **k: [])
        monkeypatch.setattr(importlib.import_module("brapi_client"), "is_configured", lambda: False)

        health._cache.update({"at": 0.0, "result": None})
        items = {item["key"]: item for item in health.check_integrations(force=True)["items"]}
        assert items["pluggy"]["status"] == "not_configured"

        monkeypatch.setenv("PLUGGY_CLIENT_ID", "id")
        monkeypatch.setenv("PLUGGY_CLIENT_SECRET", "segredo")
        monkeypatch.setattr(pluggy_client, "get_api_key", lambda force=False: "chave")
        items = {item["key"]: item for item in health.check_integrations(force=True)["items"]}
        assert items["pluggy"]["status"] == "ok"

        def refused(force=False):
            raise pluggy_client.PluggyHTTPError(401, "credenciais invalidas")

        monkeypatch.setattr(pluggy_client, "get_api_key", refused)
        result = health.check_integrations(force=True)
        assert {item["key"]: item for item in result["items"]}["pluggy"]["status"] == "error"
        health._cache.update({"at": 0.0, "result": None})
