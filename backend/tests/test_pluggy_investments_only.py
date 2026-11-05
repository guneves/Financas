"""Investimentos so pela Pluggy (Fase 3, docs/notifications-pluggy-design.md §5, decisao 3).

O que estes testes protegem:
- com MANUAL_ONLY_OFF_PLUGGY ligado, uma operacao, um resgate ou um provento
  digitado cujo caixa e a Corretora da Pluggy e recusado (400, "A Pluggy traz as
  operacoes da corretora."); `cash_account_id: null` ou outra conta passam;
- o "Lancar" de uma linha HELD deste usuario (pelo `op_key`) passa e a linha fica
  RECORDED com o que foi gravado, na mesma transacao; o op_key de outro usuario,
  desconhecido ou que nao espera e 400 (e nada e gravado);
- um PATCH que leva a operacao para a Corretora da Pluggy e recusado;
- os gravadores do servidor nunca sao barrados: proceeds_sync,
  apply_paid_proceeds() e as operacoes da Pluggy;
- a linha que espera vem com o que da para preencher (`prefill`) e o op_key.

conftest.py desliga MANUAL_ONLY_OFF_PLUGGY; aqui ele e ligado por teste.
"""

import importlib
import json

import pytest

import statusinvest_client
from open_finance_world import World, fake_pluggy, open_finance_module  # noqa: F401
from statusinvest_client import ProceedEvent
from test_open_finance_fixed_income import CDB_110, cdb
from test_open_finance_investments import broker, movements, operations, rows_of

MESSAGE = "A Pluggy traz as operações da corretora."


@pytest.fixture()
def world(client, auth, fake_pluggy):
    return World(client, auth, fake_pluggy)


@pytest.fixture()
def switch_on(app_module, monkeypatch):
    monkeypatch.setattr(importlib.import_module("services.manual_entries"), "MANUAL_ONLY_OFF_PLUGGY", True)


def buy(world, expected, **metadata):
    response = world.client.post("/api/investments", headers=world.auth, json={
        "asset_class": "STOCKS", "ticker_or_name": "PETR4", "quantity": 10, "average_price": 30,
        "metadata": {"purchase_date": "2026-10-20", **metadata},
    })
    assert response.status_code == expected, response.get_data(as_text=True)
    return response.get_json()


def held_line(world, pluggy_item, item_id, kind="BUY", ticker="PETR4"):
    """Uma operacao que espera (a Pluggy mandou sem preco: `incomplete`)."""
    position = world.fake.add_position(pluggy_item, ticker, 10)
    world.fake.add_operation(position, kind, 10, 0, "2026-10-20")
    world.sync(item_id)
    [held] = world.overview()["investments"]["held"]
    return held


class TestTypedOperations:
    def test_a_typed_buy_on_the_fed_corretora_is_refused(self, world, switch_on):
        broker(world)
        body = buy(world, 400)
        assert body["error"] == MESSAGE
        assert movements(world) == []

    def test_naming_the_fed_corretora_is_refused_too(self, world, switch_on):
        _item, _pluggy, corretora = broker(world)
        assert buy(world, 400, cash_account_id=corretora)["error"] == MESSAGE

    def test_without_cash_it_passes(self, world, switch_on):
        broker(world)
        [created] = buy(world, 201, cash_account_id=None)
        assert "cash_account_id" not in created["metadata"]

    def test_another_account_passes(self, world, switch_on):
        broker(world)
        flash = world.account("Flash", type_="CHECKING")
        [created] = buy(world, 201, cash_account_id=flash)
        assert created["metadata"]["cash_account_id"] == flash

    def test_with_the_switch_off_typing_stays(self, world):
        _item, _pluggy, corretora = broker(world)
        [created] = buy(world, 201)
        assert created["metadata"]["cash_account_id"] == corretora

    def test_a_corretora_without_pluggy_takes_typing(self, world, switch_on):
        corretora = world.account("Corretora", type_="BROKERAGE")
        [created] = buy(world, 201)
        assert created["metadata"]["cash_account_id"] == corretora

    def test_a_patch_onto_the_fed_corretora_is_refused(self, world, switch_on):
        _item, _pluggy, corretora = broker(world)
        [created] = buy(world, 201, cash_account_id=None)
        response = world.client.patch(f"/api/investments/{created['id']}", headers=world.auth, json={
            "metadata": {**created["metadata"], "cash_account_id": corretora},
        })
        assert response.status_code == 400 and response.get_json()["error"] == MESSAGE

    def test_a_patch_that_keeps_its_cash_passes(self, world, monkeypatch, app_module):
        _item, _pluggy, corretora = broker(world)
        [created] = buy(world, 201)
        monkeypatch.setattr(importlib.import_module("services.manual_entries"), "MANUAL_ONLY_OFF_PLUGGY", True)
        response = world.client.patch(f"/api/investments/{created['id']}", headers=world.auth, json={
            "average_price": 31,
        })
        assert response.status_code == 200, response.get_data(as_text=True)
        assert response.get_json()["metadata"]["cash_account_id"] == corretora


class TestLancar:
    def test_a_held_op_key_passes_and_the_line_is_recorded(self, world, user, switch_on):
        item_id, pluggy_item, corretora = broker(world)
        held = held_line(world, pluggy_item, item_id)
        assert held["op_key"].startswith("pluggy-inv:")
        prefill = held["prefill"]
        assert (prefill["kind"], prefill["ticker_or_name"], prefill["quantity"], prefill["cash_account_id"]) == (
            "operation", "PETR4", 10, corretora,
        )
        assert prefill["metadata"]["open_finance_op_key"] == held["op_key"]
        response = world.client.post("/api/investments", headers=world.auth, json={
            "asset_class": prefill["asset_class"], "ticker_or_name": "PETR4", "quantity": 10, "average_price": 30,
            "metadata": prefill["metadata"],
        })
        assert response.status_code == 201, response.get_data(as_text=True)
        [created] = response.get_json()
        assert created["metadata"]["cash_account_id"] == corretora
        assert created["metadata"]["open_finance_operation"] == held["op_key"]
        assert "open_finance_op_key" not in created["metadata"]
        [op] = operations(user["id"])
        assert (op["state"], op["investment_id"], op["held_reason"]) == ("RECORDED", created["id"], None)
        assert world.overview()["investments"]["held"] == []
        # O proximo pull nao grava de novo.
        world.sync(item_id)
        assert len(movements(world)) == 1

    def test_another_users_op_key_is_refused(self, world, client, other_user, fake_pluggy, switch_on):
        item_id, pluggy_item, _corretora = broker(world)
        held = held_line(world, pluggy_item, item_id)
        other = World(client, other_user["headers"], fake_pluggy)
        response = other.client.post("/api/investments", headers=other.auth, json={
            "asset_class": "STOCKS", "ticker_or_name": "PETR4", "quantity": 10, "average_price": 30,
            "metadata": {"purchase_date": "2026-10-20", "cash_account_id": None, "open_finance_op_key": held["op_key"]},
        })
        assert response.status_code == 400
        assert movements(other) == []
        assert world.overview()["investments"]["held"][0]["op_key"] == held["op_key"]

    @pytest.mark.parametrize("key", ["pluggy-inv:nao-existe", "qualquer", 42])
    def test_an_unknown_op_key_is_refused(self, world, key, switch_on):
        broker(world)
        assert buy(world, 400, cash_account_id=None, open_finance_op_key=key)["error"]
        assert movements(world) == []

    def test_a_key_that_is_not_held_is_refused(self, world, user, switch_on):
        item_id, pluggy_item, _corretora = broker(world)
        held = held_line(world, pluggy_item, item_id)
        buy(world, 201, cash_account_id=None, open_finance_op_key=held["op_key"])
        assert buy(world, 400, cash_account_id=None, open_finance_op_key=held["op_key"])["error"]

    def test_a_held_fixed_income_buy_prefills_what_it_knows(self, world, switch_on):
        item_id, pluggy_item, _corretora = broker(world)
        position = cdb(world, pluggy_item, rate=110)  # sem rateType
        world.fake.add_operation(position, "BUY", 1500, 1.0, "2026-10-20")
        world.sync(item_id)
        [held] = world.overview()["investments"]["held"]
        prefill = held["prefill"]
        assert held["reason"] == "missing:rateType"
        assert (prefill["kind"], prefill["asset_class"], prefill["average_price"], prefill["cash_account_id"]) == (
            "operation", "FIXED_INCOME", 1500, None,
        )
        assert prefill["metadata"]["fixed_income_type"] == "CDB"
        assert "cdi_percentage" not in prefill["metadata"]
        response = world.client.post("/api/investments", headers=world.auth, json={
            "asset_class": "FIXED_INCOME", "ticker_or_name": prefill["ticker_or_name"], "quantity": 1,
            "average_price": 1500,
            "metadata": {**prefill["metadata"], "rate_type": "POS", "indexer": "CDI", "cdi_percentage": 1.1,
                         "cash_account_id": None},
        })
        assert response.status_code == 201, response.get_data(as_text=True)
        assert world.overview()["investments"]["held"] == []


def fixed_income_position(world):
    world.call("post", "/api/investments", json={
        "asset_class": "FIXED_INCOME", "ticker_or_name": "CDB TESTE", "quantity": 1, "average_price": 1000,
        "metadata": {"purchase_date": "2026-01-05", "cash_account_id": None, "fixed_income_type": "CDB",
                     "rate_type": "POS", "indexer": "CDI", "cdi_percentage": 1.0},
    })
    snapshot = world.call("get", "/api/investments/portfolio")
    return next(asset for asset in snapshot["assets"] if asset["class"] == "FIXED_INCOME")


class TestRedemptions:
    def test_a_redemption_onto_the_fed_corretora_is_refused(self, world, switch_on):
        broker(world)
        position = fixed_income_position(world)
        response = world.client.post("/api/investments/redemptions", headers=world.auth, json={
            "position_id": position["id"], "amount": 100, "date": "2026-10-20",
        })
        assert response.status_code == 400 and response.get_json()["error"] == MESSAGE

    def test_a_redemption_without_cash_passes(self, world, switch_on):
        broker(world)
        position = fixed_income_position(world)
        response = world.client.post("/api/investments/redemptions", headers=world.auth, json={
            "position_id": position["id"], "amount": 100, "date": "2026-10-20", "cash_account_id": None,
        })
        assert response.status_code == 201, response.get_data(as_text=True)

    def test_a_held_redemption_is_completed_by_its_op_key(self, world, user, switch_on):
        item_id, pluggy_item, _corretora = broker(world)
        position = fixed_income_position(world)
        pluggy_position = cdb(world, pluggy_item, **CDB_110)
        world.fake.add_operation(pluggy_position, "SELL", 100, 1.0, "2026-10-20")
        world.sync(item_id)
        [held] = world.overview()["investments"]["held"]
        assert (held["reason"], held["prefill"]["kind"]) == ("missing:buy", "redemption")
        response = world.client.post("/api/investments/redemptions", headers=world.auth, json={
            "position_id": position["id"], "amount": 100, "date": "2026-10-20",
            "metadata": {"open_finance_op_key": held["op_key"]},
        })
        assert response.status_code == 201, response.get_data(as_text=True)
        [part] = response.get_json()
        [op] = operations(user["id"])
        assert (op["state"], op["investment_id"]) == ("RECORDED", part["id"])


def set_portfolio_since(user_id, corretora, day):
    db = importlib.import_module("db")
    with db.get_db() as conn:
        conn.execute(
            "UPDATE accounts SET metadata = ? WHERE id = ? AND user_id = ?",
            (json.dumps({"portfolio_since": day}), corretora, user_id),
        )


class TestProceeds:
    def stock(self, world):
        [created] = buy(world, 201, cash_account_id=None, purchase_date="2026-01-05")
        return created["asset_id"]

    def post(self, world, asset_id, payment_date, **extra):
        return world.client.post("/api/investment-proceeds", headers=world.auth, json={
            "asset_id": asset_id, "proceeds_type": "DIVIDEND", "record_date": "2026-09-01",
            "payment_date": payment_date, "gross_amount": 25, **extra,
        })

    def test_a_typed_proceed_landing_in_the_fed_corretora_is_refused(self, world, user, switch_on):
        _item, _pluggy, corretora = broker(world)
        set_portfolio_since(user["id"], corretora, "2026-01-01")
        response = self.post(world, self.stock(world), "2026-10-20")
        assert response.status_code == 400 and response.get_json()["error"] == MESSAGE
        assert world.call("get", "/api/investment-proceeds") == []

    def test_a_proceed_paid_before_the_corretora_was_the_portfolio_passes(self, world, user, switch_on):
        _item, _pluggy, corretora = broker(world)
        set_portfolio_since(user["id"], corretora, "2026-10-25")
        assert self.post(world, self.stock(world), "2026-10-20").status_code == 201

    def test_with_the_switch_off_it_passes(self, world, user):
        _item, _pluggy, corretora = broker(world)
        set_portfolio_since(user["id"], corretora, "2026-01-01")
        assert self.post(world, self.stock(world), "2026-10-20").status_code == 201

    def test_a_held_coupon_is_completed_by_its_op_key(self, world, user, switch_on):
        item_id, pluggy_item, corretora = broker(world)
        set_portfolio_since(user["id"], corretora, "2026-01-01")
        position = cdb(world, pluggy_item)  # sem taxa: a compra espera, entao o cupom tambem
        world.fake.add_operation(position, "INTEREST", 1, 50, "2026-10-20")
        world.sync(item_id)
        [held] = world.overview()["investments"]["held"]
        assert (held["type"], held["prefill"]["kind"]) == ("INTEREST", "proceed")
        asset_id = fixed_income_position(world)["asset_id"]
        response = world.client.post("/api/investment-proceeds", headers=world.auth, json={
            "asset_id": asset_id, "proceeds_type": "INTEREST", "payment_date": "2026-10-20", "gross_amount": 50,
            "metadata": {"open_finance_op_key": held["op_key"]},
        })
        assert response.status_code == 201, response.get_data(as_text=True)
        proceed = response.get_json()
        [op] = [row for row in operations(user["id"]) if row["op_type"] == "INTEREST"]
        assert (op["state"], op["proceed_id"]) == ("RECORDED", proceed["id"])

    def test_another_users_coupon_key_is_refused(self, world, client, other_user, fake_pluggy, user, switch_on):
        item_id, pluggy_item, _corretora = broker(world)
        position = cdb(world, pluggy_item)
        world.fake.add_operation(position, "INTEREST", 1, 50, "2026-10-20")
        world.sync(item_id)
        [held] = world.overview()["investments"]["held"]
        other = World(client, other_user["headers"], fake_pluggy)
        [created] = other.call("post", "/api/investments", json={
            "asset_class": "STOCKS", "ticker_or_name": "PETR4", "quantity": 10, "average_price": 30,
            "metadata": {"purchase_date": "2026-01-05"},
        })
        response = other.client.post("/api/investment-proceeds", headers=other.auth, json={
            "asset_id": created["asset_id"], "proceeds_type": "DIVIDEND", "record_date": "2026-09-01",
            "payment_date": "2026-10-20", "gross_amount": 25, "metadata": {"open_finance_op_key": held["op_key"]},
        })
        assert response.status_code == 400


class TestServerWritersAreNeverGuarded:
    def test_proceeds_sync_still_writes(self, world, user, monkeypatch, switch_on):
        _item, _pluggy, corretora = broker(world)
        set_portfolio_since(user["id"], corretora, "2026-01-01")
        self_asset = buy(world, 201, cash_account_id=None, purchase_date="2026-01-05")[0]
        assert self_asset["ticker_or_name"] == "PETR4"
        event = ProceedEvent("PETR4", "DIVIDEND", "DIVIDEND", "2026-09-01", "2026-10-20", 1.5, "Dividendo")
        statusinvest_client.clear_cache()
        monkeypatch.setattr(statusinvest_client, "get_proceed_events", lambda *args, **kwargs: [event])
        prices = importlib.import_module("services.prices")
        monkeypatch.setattr(prices, "download_close_prices", lambda symbols, **kwargs: {})
        world.call("post", "/api/investment-proceeds/sync", json={})
        [proceed] = world.call("get", "/api/investment-proceeds")
        assert proceed["gross_amount"] == 15
        # E o dinheiro dele cai na Corretora da Pluggy (apply_paid_proceeds, sem guarda).
        db = importlib.import_module("db")
        with db.get_db() as conn:
            importlib.import_module("services.proceeds_cash").apply_paid_proceeds(conn, user["id"])
        cash = rows_of("transactions", "user_id = ? AND account_id = ? AND source_type = 'INVESTMENT_PROCEED'",
                       (user["id"], corretora))
        assert [row["amount"] for row in cash] == [15]

    def test_pluggy_operations_still_record_on_the_corretora(self, world, user, switch_on):
        item_id, pluggy_item, corretora = broker(world)
        position = world.fake.add_position(pluggy_item, "PETR4", 100, value=38.5)
        world.fake.add_operation(position, "BUY", 100, 38.5, "2026-10-20")
        world.sync(item_id)
        [movement] = movements(world)
        assert movement["metadata"]["cash_account_id"] == corretora
        assert [row["type"] for row in world.transactions(corretora)] == ["EXPENSE"]
