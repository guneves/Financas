"""Open Finance: conectar, mapear, desconectar (routes/open_finance.py).

- sem credenciais, a integracao fica desligada e diz isso (nada quebra);
- o connect token vem do servidor; credenciais nunca saem;
- cada conta da Pluggy vai para uma conta (nunca a Corretora) ou um cartao
  com credito, escolhido pelo dono; a sugestao e so sugestao;
- desconectar pede o nome do banco, apaga na Pluggy e arquiva o nosso;
- user_id em tudo.
"""

import pytest

from open_finance_world import FakePluggy, World, bank_tx, connected, fake_pluggy, open_finance_module  # noqa: F401


@pytest.fixture()
def world(client, auth, fake_pluggy):
    return World(client, auth, fake_pluggy)


class TestOff:
    def test_without_credentials_it_says_so(self, client, auth, open_finance_module):
        open_finance_module.set_client(None)
        body = client.get("/api/open-finance", headers=auth).get_json()
        assert body["configured"] is False and body["items"] == []
        response = client.post("/api/open-finance/connect-token", json={}, headers=auth)
        assert response.status_code == 503
        assert "PLUGGY" not in response.get_data(as_text=True) or "credenciais" in response.get_json()["error"]

    def test_the_healthcheck_marks_it_not_configured(self, app_module, open_finance_module):
        open_finance_module.set_client(None)
        health = __import__("importlib").import_module("services.health")
        assert health.check_pluggy()["status"] == "not_configured"

    def test_the_background_thread_does_not_start(self, app_module, open_finance_module):
        refresh = __import__("importlib").import_module("services.open_finance_refresh")
        open_finance_module.set_client(None)
        assert refresh.start_auto_refresh(interval_seconds=3600) is False
        open_finance_module.set_client(FakePluggy())
        assert refresh.start_auto_refresh(interval_seconds=0) is False
        open_finance_module.set_client(None)


class TestConnect:
    def test_the_token_is_for_this_user(self, world, user):
        body = world.call("post", "/api/open-finance/connect-token", json={})
        assert body == {"access_token": "connect-token-de-teste"}
        assert world.fake.calls[-1] == ("connect_token", None, user["id"])

    def test_registering_stores_the_item_and_its_bank_and_card_accounts(self, world):
        pluggy_item = world.fake.add_item("Itaú")
        world.fake.add_account(pluggy_item, "BANK", number="0001/12345-0", balance=36166.9)
        world.fake.add_account(pluggy_item, "CREDIT", name="Mastercard Black", number="9437")
        world.fake.accounts[pluggy_item].append({"id": "inv-1", "type": "INVESTMENT", "name": "CDB"})
        body = world.connect(pluggy_item)
        [item] = body["items"]
        assert item["id"] == body["item_id"]
        assert (item["connector_name"], item["status"]) == ("Itaú", "UPDATED")
        assert sorted(account["type"] for account in item["accounts"]) == ["BANK", "CREDIT"]
        bank = next(account for account in item["accounts"] if account["type"] == "BANK")
        assert bank["pluggy_balance"] == 36166.9 and bank["account_id"] is None

    def test_an_unknown_item_is_refused(self, world):
        world.connect("0f0f0f0f-0000-0000-0000-000000000000", expected=400)
        world.connect("../../etc", expected=400)
        assert world.overview()["items"] == []

    def test_reconnecting_the_same_item_does_not_duplicate(self, world):
        pluggy_item = world.fake.add_item()
        world.fake.add_account(pluggy_item)
        world.connect(pluggy_item)
        world.connect(pluggy_item)
        [item] = world.overview()["items"]
        assert len(item["accounts"]) == 1

    def test_the_pluggy_refusal_message_reaches_ajustes(self, world):
        pluggy_item = world.fake.add_item(
            status="LOGIN_ERROR", execution_status="USER_NOT_SUPPORTED",
            error={"code": "USER_NOT_SUPPORTED", "message": "Seu plano permite conectar apenas um CPF."},
        )
        world.connect(pluggy_item)
        [item] = world.overview()["items"]
        assert item["needs_owner"] is True
        assert item["error_message"] == "Seu plano permite conectar apenas um CPF."
        # Nada pede dados de novo ao banco para um item que espera o dono.
        world.sync(item["id"])
        assert not [call for call in world.fake.calls if call[0] == "update_item"]

    def test_a_connect_token_to_fix_an_item(self, world):
        pluggy_item = world.fake.add_item()
        our = world.connect(pluggy_item)["item_id"]
        world.call("post", "/api/open-finance/connect-token", json={"item_id": our})
        assert world.fake.calls[-1][1] == pluggy_item


class TestMapping:
    def test_unmapped_accounts_are_pulled_but_produce_nothing(self, world):
        pluggy_item = world.fake.add_item()
        pluggy_account = world.fake.add_account(pluggy_item)
        world.fake.add_tx(pluggy_account, bank_tx(-45.9, "2026-10-20"))
        body = world.connect(pluggy_item)
        assert world.pending() == []
        [account] = body["items"][0]["accounts"]
        assert account["unmapped_count"] == 1

    def test_mapping_brings_what_was_pulled_to_aprovar(self, world):
        pluggy_item = world.fake.add_item()
        pluggy_account = world.fake.add_account(pluggy_item)
        world.fake.add_tx(pluggy_account, bank_tx(-45.9, "2026-10-20", "PADARIA"))
        [account] = world.connect(pluggy_item)["items"][0]["accounts"]
        mine = world.account("Itaú")
        body = world.map(account["id"], account_id=mine)
        assert body["placed"] == 1
        [item] = world.pending()
        assert (item["entry_type"], item["account_id"], item["amount"]) == ("EXPENSE", mine, 45.9)
        assert item["ready"] is True

    def test_the_corretora_archived_and_foreign_accounts_are_refused(self, world):
        pluggy_item = world.fake.add_item()
        world.fake.add_account(pluggy_item)
        [account] = world.connect(pluggy_item)["items"][0]["accounts"]
        broker = world.account("Corretora", "BROKERAGE")
        world.map(account["id"], expected=400, account_id=broker)
        archived = world.account("Velha")
        world.call("delete", f"/api/accounts/{archived}")
        world.map(account["id"], expected=400, account_id=archived)
        world.map(account["id"], expected=400, account_id="nao-existe")

    def test_a_card_needs_credit(self, world):
        pluggy_item = world.fake.add_item()
        world.fake.add_account(pluggy_item, "CREDIT", number="9437")
        [account] = world.connect(pluggy_item)["items"][0]["accounts"]
        debit_account = world.account("Flash conta")
        debit_only = world.card("Flash", credit_enabled=False, debit_account_id=debit_account)
        world.map(account["id"], expected=400, card_id=debit_only)
        # Uma conta BANK nao vira cartao e vice-versa: o campo e o do tipo.
        world.map(account["id"], expected=400, account_id=debit_account)
        good = world.card("Itaú Black 9437")
        world.map(account["id"], card_id=good)

    def test_two_pluggy_accounts_cannot_feed_the_same_account(self, world):
        pluggy_item = world.fake.add_item()
        world.fake.add_account(pluggy_item, number="1")
        world.fake.add_account(pluggy_item, number="2")
        first, second = world.connect(pluggy_item)["items"][0]["accounts"]
        mine = world.account("Itaú")
        world.map(first["id"], account_id=mine)
        world.map(second["id"], expected=400, account_id=mine)

    def test_suggestions_by_bank_and_last_digits_are_never_saved_alone(self, world):
        itau = world.account("Conta corrente", institution="Itaú")
        world.account("Conta BB", institution="Banco do Brasil")
        world.card("Visa 1111")
        black = world.card("Mastercard 9437")
        pluggy_item = world.fake.add_item("Itaú")
        world.fake.add_account(pluggy_item, "BANK", number="0001/12345-0")
        world.fake.add_account(pluggy_item, "CREDIT", number="5555 **** 9437")
        accounts = {entry["type"]: entry for entry in world.connect(pluggy_item)["items"][0]["accounts"]}
        assert accounts["BANK"]["suggested_id"] == itau
        assert accounts["CREDIT"]["suggested_id"] == black
        assert accounts["BANK"]["account_id"] is None and accounts["CREDIT"]["card_id"] is None

    def test_unmapping_stops_new_items(self, world):
        item_id, _pluggy_item, made = connected(world)
        pluggy_account, of_id, _mine = made["bank"]
        world.map(of_id, account_id=None)
        world.fake.add_tx(pluggy_account, bank_tx(-10, "2026-10-26"))
        world.sync(item_id)
        assert world.pending() == []


class TestSettings:
    def test_first_sync_window_default_and_change(self, world):
        assert world.overview()["first_sync_days"] == 30
        world.call("patch", "/api/open-finance/settings", json={"first_sync_days": 90})
        assert world.overview()["first_sync_days"] == 90
        for bad in (0, 400, "x", True):
            world.call("patch", "/api/open-finance/settings", expected=400, json={"first_sync_days": bad})


class TestDisconnect:
    def test_it_needs_the_bank_name(self, world):
        item_id, pluggy_item, _made = connected(world)
        world.call("delete", f"/api/open-finance/items/{item_id}", expected=400, json={"confirm": "outro"})
        world.call("delete", f"/api/open-finance/items/{item_id}", expected=400, json={})
        assert world.overview()["items"]
        world.call("delete", f"/api/open-finance/items/{item_id}", json={"confirm": "Itaú"})
        assert world.overview()["items"] == []
        assert ("delete_item", pluggy_item) in world.fake.calls

    def test_approved_entries_and_pending_items_stay(self, world):
        item_id, _pluggy_item, made = connected(world)
        pluggy_account, _of, mine = made["bank"]
        world.fake.add_tx(pluggy_account, bank_tx(-10, "2026-10-25"), bank_tx(-20, "2026-10-26"))
        world.sync(item_id)
        first, _second = sorted(world.pending(), key=lambda item: item["amount"])
        world.approve(first)
        world.call("delete", f"/api/open-finance/items/{item_id}", json={"confirm": "Itaú"})
        assert len(world.transactions(mine)) == 1
        assert len(world.pending()) == 1
        world.sync(item_id, expected=404)


class TestIsolation:
    def test_another_user_sees_and_touches_nothing(self, client, world, other_user):
        item_id, _pluggy_item, made = connected(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-10, "2026-10-26"))
        world.sync(item_id)
        other = World(client, other_user["headers"], world.fake)
        assert other.overview()["items"] == []
        assert other.pending() == []
        other.sync(item_id, expected=404)
        other.map(made["bank"][1], expected=404, account_id=other.account("Minha"))
        other.call("delete", f"/api/open-finance/items/{item_id}", expected=404, json={"confirm": "Itaú"})
        other.call("post", "/api/open-finance/connect-token", expected=404, json={"item_id": item_id})
        assert len(world.pending()) == 1

    def test_a_user_cannot_map_to_someone_elses_account(self, client, world, other_user):
        pluggy_item = world.fake.add_item()
        world.fake.add_account(pluggy_item)
        [account] = world.connect(pluggy_item)["items"][0]["accounts"]
        theirs = World(client, other_user["headers"], world.fake).account("Deles")
        world.map(account["id"], expected=400, account_id=theirs)

    def test_every_route_needs_a_token(self, client):
        for method, path in (
            ("get", "/api/open-finance"), ("post", "/api/open-finance/connect-token"),
            ("post", "/api/open-finance/items"), ("post", "/api/open-finance/items/x/sync"),
            ("delete", "/api/open-finance/items/x"), ("put", "/api/open-finance/accounts/x"),
            ("patch", "/api/open-finance/settings"),
        ):
            assert getattr(client, method)(path, json={}).status_code == 401
