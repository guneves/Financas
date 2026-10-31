"""Dono, 2026-10-30: a Pluggy faz o trabalho e o app espera por ela. O movimento
de uma ponta so fica quieto ate a Pluggy atualizar; salario nao e transferencia;
uma despesa pode virar transferencia; so o pull grava movimento de banco."""

import importlib
from datetime import date, datetime, timezone

import pytest

from tests.open_finance_world import World, bank_tx, connected, fake_pluggy, open_finance_module  # noqa: F401

NOW = "2026-10-27"


@pytest.fixture()
def world(client, auth, fake_pluggy, db_module, user):
    made = World(client, auth, fake_pluggy)
    with db_module.get_db() as conn:
        for key in ("open_finance_auto_record", "auto_record_notifications"):
            conn.execute(
                "INSERT OR REPLACE INTO user_settings (user_id, setting_key, value) VALUES (?, ?, '1')",
                (user["id"], key),
            )
    return made


def own_transfer(amount=500.0, description="PIX RECEBIDO", day=NOW):
    return bank_tx(amount, day, description=description, category_id="04000000", payment_method="PIX")


def bank_updates(fake, pluggy_item, stamp=None):
    """A Pluggy falou com o banco: agora (o item, nestes testes, ja nasceu antes)."""
    fake.items[pluggy_item]["lastUpdatedAt"] = stamp or datetime.now(timezone.utc).isoformat()


class TestSalaryIsIncome:
    def test_a_ted_salary_is_never_a_transfer(self, world):
        item_id, _pluggy, made = connected(world)
        pluggy_id, _of, account_id = made["bank"]
        world.fake.add_tx(pluggy_id, bank_tx(5000.0, NOW, description="TED SALARIO ACME", payment_method="TED"))
        world.sync(item_id)
        rows = world.transactions(account_id)
        assert [(row["type"], row["amount"]) for row in rows] == [("INCOME", 5000.0)]

    def test_pluggys_income_category_wins_over_the_method(self, world):
        item_id, _pluggy, made = connected(world)
        pluggy_id, _of, account_id = made["bank"]
        world.fake.add_tx(
            pluggy_id, bank_tx(5000.0, NOW, description="TED ACME LTDA", category_id="01010000", payment_method="TED"),
        )
        world.sync(item_id)
        assert [row["type"] for row in world.transactions(account_id)] == ["INCOME"]

    def test_an_outgoing_row_is_not_income(self, app_module):
        rows = importlib.import_module("services.open_finance_inbox")
        raw = {"description": "TED FOLHA", "categoryId": "04000000"}
        assert rows.movement_of(raw, "BANK", "OUT") == "SELF_TRANSFER"


class TestNotBetweenMyAccounts:
    def test_an_incoming_one_sided_transfer_becomes_income_in_its_account(self, world):
        item_id, _pluggy, made = connected(world)
        pluggy_id, _of, account_id = made["bank"]
        world.fake.add_tx(pluggy_id, own_transfer(5000.0, "TED RECEBIDO ACME"))
        world.sync(item_id)
        item = world.pending()[0]
        assert (item["account_id"], item["transfer_account_id"]) == (None, account_id)
        # O APK instalado manda EXPENSE: a direcao guardada de uma transferencia e OUT.
        world.approve(item, entry_type="EXPENSE", remember=False)
        rows = world.transactions(account_id)
        assert [(row["type"], row["amount"]) for row in rows] == [("INCOME", 5000.0)]

    def test_an_outgoing_one_sided_transfer_becomes_expense(self, world):
        item_id, _pluggy, made = connected(world)
        pluggy_id, _of, account_id = made["bank"]
        world.fake.add_tx(pluggy_id, own_transfer(-80.0, "PIX ENVIADO"))
        world.sync(item_id)
        world.approve(world.pending()[0], entry_type="EXPENSE", remember=False)
        assert [row["type"] for row in world.transactions(account_id)] == ["EXPENSE"]


class TestWaitsForTheBank:
    def test_quiet_until_a_refresh_passes_without_the_other_side(self, world):
        item_id, pluggy_item, made = connected(world)
        world.fake.add_tx(made["bank"][0], own_transfer())
        world.sync(item_id)
        assert world.call("get", "/api/review")["waiting"] == 0
        assert world.pending()[0]["awaiting_bank"] is True
        bank_updates(world.fake, pluggy_item)
        world.sync(item_id)
        assert world.call("get", "/api/review")["waiting"] == 1
        assert world.pending()[0]["awaiting_bank"] is False

    def test_every_connection_must_refresh(self, world):
        first, pluggy_first, made = connected(world)
        second, pluggy_second, _ = connected(world, connector_name="BTG")
        world.fake.add_tx(made["bank"][0], own_transfer())
        world.sync(first)
        bank_updates(world.fake, pluggy_first)
        world.sync(first)
        assert world.call("get", "/api/review")["waiting"] == 0
        bank_updates(world.fake, pluggy_second)
        world.sync(second)
        assert world.call("get", "/api/review")["waiting"] == 1

    def test_a_dead_connection_does_not_hide_it_forever(self, world, db_module):
        item_id, _pluggy, made = connected(world)
        world.fake.add_tx(made["bank"][0], own_transfer())
        world.sync(item_id)
        with db_module.get_db() as conn:
            conn.execute("UPDATE inbox_items SET created_at = '2020-01-01T00:00:00.000Z'")
        assert world.call("get", "/api/review")["waiting"] == 1

    def test_the_conference_waits_too(self, world):
        item_id, pluggy_item, made = connected(world)
        pluggy_id, _of, account_id = made["bank"]
        world.fake.add_tx(pluggy_id, bank_tx(-10.0, "2026-10-21", description="PADARIA"))
        bank_updates(world.fake, pluggy_item, "2026-10-23T12:00:00.000Z")
        world.sync(item_id)
        world.call("post", "/api/transactions", json={
            "amount": 33.0, "date": "2026-10-26", "type": "EXPENSE", "category": "Outros", "account_id": account_id,
        })
        check = world.overview()["items"][0]["accounts"][0]["check"]
        assert (check["app_only_count"], check["awaiting_bank_count"]) == (0, 1)
        assert check["explanation"]["app_only"] == 3300

    def test_an_old_app_row_the_bank_never_brought_is_flagged(self, world, db_module):
        item_id, pluggy_item, made = connected(world)
        pluggy_id, _of, account_id = made["bank"]
        world.fake.add_tx(pluggy_id, bank_tx(-10.0, "2026-10-21", description="PADARIA"))
        world.sync(item_id)
        world.call("post", "/api/transactions", json={
            "amount": 33.0, "date": "2026-10-22", "type": "EXPENSE", "category": "Outros", "account_id": account_id,
        })
        with db_module.get_db() as conn:
            conn.execute("UPDATE open_finance_items SET pluggy_updated_at = '2026-10-27T12:00:00.000Z'")
            conn.execute("UPDATE transactions SET created_at = '2026-10-22T12:00:00.000Z'")
        check = world.overview()["items"][0]["accounts"][0]["check"]
        assert (check["app_only_count"], check["awaiting_bank_count"]) == (1, 0)


class TestOnlyThePullRecords:
    def test_a_read_never_records_a_bank_movement(self, world, invoices_module, monkeypatch):
        item_id, _pluggy, made = connected(world)
        pluggy_id, _of, account_id = made["bank"]
        world.fake.add_tx(pluggy_id, bank_tx(-80.0, NOW, description="PIX JOAO", payment_method="PIX"))
        world.sync(item_id)
        assert world.transactions(account_id) == []
        monkeypatch.setattr(invoices_module, "local_today", lambda: date(2026, 11, 5))
        assert world.transactions(account_id) == []
        world.call("get", "/api/home")
        assert world.transactions(account_id) == []
        world.sync(item_id)
        assert [row["type"] for row in world.transactions(account_id)] == ["EXPENSE"]


class TestExpenseToTransfer:
    def patch(self, world, row_id, expected=200, **body):
        return world.call("patch", f"/api/transactions/{row_id}", expected=expected, json=body)

    def expense(self, world, account_id, amount=120.0):
        return world.call("post", "/api/transactions", json={
            "amount": amount, "date": NOW, "type": "EXPENSE", "category": "Outros", "account_id": account_id,
        })["id"]

    def balances(self, world):
        return {row["id"]: row["balance"] for row in world.call("get", "/api/accounts")}

    def test_an_expense_becomes_a_transfer(self, world):
        origin, destination = world.account("A"), world.account("B")
        row_id = self.expense(world, origin)
        body = self.patch(world, row_id, type="TRANSFER", account_id=origin, transfer_account_id=destination)
        assert body["type"] == "TRANSFER" and body["transfer_account_id"] == destination
        assert body["category_id"] is None
        balances = self.balances(world)
        assert (balances[origin], balances[destination]) == (-120.0, 120.0)

    def test_an_income_becomes_a_transfer_into_its_account(self, world):
        origin, destination = world.account("A"), world.account("B")
        row_id = world.call("post", "/api/transactions", json={
            "amount": 50.0, "date": NOW, "type": "INCOME", "category": "Outros", "account_id": destination,
        })["id"]
        body = self.patch(world, row_id, type="TRANSFER", account_id=origin, transfer_account_id=destination)
        assert (body["account_id"], body["transfer_account_id"]) == (origin, destination)

    def test_it_needs_both_accounts_and_keeps_the_rows_own_side(self, world):
        origin, destination, third = world.account("A"), world.account("B"), world.account("C")
        row_id = self.expense(world, origin)
        self.patch(world, row_id, expected=400, type="TRANSFER", account_id=origin)
        self.patch(world, row_id, expected=400, type="TRANSFER", account_id=origin, transfer_account_id=origin)
        self.patch(world, row_id, expected=400, type="TRANSFER", account_id=third, transfer_account_id=destination)

    def test_a_shared_expense_stops_being_shared(self, world):
        origin, destination = world.account("A"), world.account("B")
        row_id = self.expense(world, origin)
        self.patch(world, row_id, share_mode="OTHERS", share_person="Ana")
        body = self.patch(world, row_id, type="TRANSFER", account_id=origin, transfer_account_id=destination)
        assert body["share_mode"] is None

    def test_the_review_mark_goes(self, world, db_module):
        origin, destination = world.account("A"), world.account("B")
        row_id = self.expense(world, origin)
        with db_module.get_db() as conn:
            conn.execute("UPDATE transactions SET needs_review = 1 WHERE id = ?", (row_id,))
        self.patch(world, row_id, type="TRANSFER", account_id=origin, transfer_account_id=destination)
        assert world.call("get", "/api/review")["count"] == 0

    def test_invoice_rows_stay_locked(self, world, db_module):
        origin, destination = world.account("A"), world.account("B")
        row_id = self.expense(world, origin)
        with db_module.get_db() as conn:
            conn.execute("UPDATE transactions SET source_type = 'CC_AUTOPAY', source_id = 'x' WHERE id = ?", (row_id,))
        self.patch(world, row_id, expected=409, type="TRANSFER", account_id=origin, transfer_account_id=destination)

    def test_the_other_side_pluggy_recorded_is_absorbed(self, world):
        first, _p1, one = connected(world)
        second, _p2, two = connected(world, connector_name="BTG")
        world.fake.add_tx(one["bank"][0], bank_tx(-300.0, NOW, description="COMPRA ENVIADO"))
        world.fake.add_tx(two["bank"][0], bank_tx(300.0, NOW, description="DEPOSITO"))
        world.sync(first)
        world.sync(second)
        origin, destination = one["bank"][2], two["bank"][2]
        expense = world.transactions(origin)[0]
        body = self.patch(world, expense["id"], type="TRANSFER", account_id=origin, transfer_account_id=destination)
        assert body["absorbed_other_side"] is True
        assert [row["type"] for row in world.transactions()] == ["TRANSFER"]
        assert self.balances(world)[destination] == 300.0
        world.sync(second)
        assert len(world.transactions()) == 1

    def test_the_other_side_arriving_later_links_to_it(self, world):
        first, _p1, one = connected(world)
        second, _p2, two = connected(world, connector_name="BTG")
        world.fake.add_tx(one["bank"][0], bank_tx(-300.0, NOW, description="COMPRA ENVIADO"))
        world.sync(first)
        origin, destination = one["bank"][2], two["bank"][2]
        expense = world.transactions(origin)[0]
        self.patch(world, expense["id"], type="TRANSFER", account_id=origin, transfer_account_id=destination)
        world.fake.add_tx(two["bank"][0], bank_tx(300.0, NOW, description="DEPOSITO"))
        world.sync(second)
        assert [row["type"] for row in world.transactions()] == ["TRANSFER"]
