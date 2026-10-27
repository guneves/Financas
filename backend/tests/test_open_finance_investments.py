"""BTG Investimentos na carteira (044, services/open_finance_investments.py).

O que estes testes protegem:
- a compra e a venda de renda variavel da corretora viram operacoes, com o
  caixa pela Corretora, na data do pregao; puxar de novo nao duplica;
- a operacao que o dono ja digitou e ligada, nunca duplicada;
- antes do ultimo evento corporativo, ou uma venda sem posicao, a operacao
  espera (HELD) e nada e gravado;
- renda fixa, TRANSFER e INTEREST esperam o dono;
- desfazer (apagar a operacao) e para sempre;
- a conferencia: quantidade da Pluggy (D-1) mais as operacoes depois dela, e o
  caixa a liquidar (D+2);
- o pull so le (GET) e outro usuario nao e tocado.
"""

import importlib

import pytest

from open_finance_world import World, fake_pluggy, open_finance_module  # noqa: F401

SETTINGS = "/api/open-finance/settings"


@pytest.fixture()
def world(client, auth, fake_pluggy):
    return World(client, auth, fake_pluggy)


def rows_of(table, where="1=1", params=()):
    db = importlib.import_module("db")
    with db.get_db() as conn:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table} WHERE {where}", params).fetchall()]


def broker(world, balance=5000.0):
    """O BTG pelo MeuPluggy com a conta de investimentos mapeada na Corretora."""
    fake = world.fake
    corretora = world.account("BTG Corretora", type_="BROKERAGE")
    pluggy_item = fake.add_item("MeuPluggy")
    fake.add_account(pluggy_item, "BANK", name="BTG Investimentos", number="9", balance=balance)
    body = world.connect(pluggy_item)
    of_id = body["items"][0]["accounts"][0]["id"]
    world.map(of_id, account_id=corretora)
    return body["item_id"], pluggy_item, corretora


def movements(world):
    return [row for row in world.call("get", "/api/investments") if row.get("ticker_or_name")]


def operations(user_id):
    return rows_of("open_finance_investment_operations", "user_id = ? ORDER BY trade_date, op_key", (user_id,))


class TestOperations:
    def test_a_buy_is_recorded_with_cash_from_the_corretora(self, world, user):
        item_id, pluggy_item, corretora = broker(world)
        position = world.fake.add_position(pluggy_item, "PETR4", 100, value=38.5)
        world.fake.add_operation(position, "BUY", 100, 38.5, "2026-10-20", expenses={"brokerageFee": 2.5})
        body = world.sync(item_id)
        assert body["result"]["investments"] == {"recorded": 1, "linked": 0, "held": 0, "dismissed": 0}
        [movement] = movements(world)
        assert (movement["ticker_or_name"], movement["quantity"], movement["average_price"]) == ("PETR4", 100, 38.5)
        assert movement["metadata"]["purchase_date"] == "2026-10-20"
        assert movement["metadata"]["other_costs"] == 2.5
        cash = world.transactions(corretora)
        assert [(row["type"], row["amount"], row["date"]) for row in cash] == [("EXPENSE", 3850.0, "2026-10-20")]

    def test_a_repeat_pull_is_a_no_op(self, world):
        item_id, pluggy_item, _corretora = broker(world)
        position = world.fake.add_position(pluggy_item, "PETR4", 100)
        world.fake.add_operation(position, "BUY", 100, 38.5, "2026-10-20")
        world.sync(item_id)
        world.sync(item_id)
        assert len(movements(world)) == 1

    def test_without_an_id_the_key_is_the_operation(self, world, user):
        item_id, pluggy_item, _corretora = broker(world)
        position = world.fake.add_position(pluggy_item, "PETR4", 100)
        world.fake.add_operation(position, "BUY", 100, 38.5, "2026-10-20", op_id=False)
        world.sync(item_id)
        world.sync(item_id)
        assert len(movements(world)) == 1
        assert operations(user["id"])[0]["op_key"].startswith("pluggy-inv:")

    def test_a_sell_after_the_buy(self, world):
        item_id, pluggy_item, corretora = broker(world)
        position = world.fake.add_position(pluggy_item, "BOVA11", 5, value=130)
        world.fake.add_operation(position, "SELL", 5, 130, "2026-10-22")
        world.fake.add_operation(position, "BUY", 10, 120, "2026-10-20")
        world.sync(item_id)
        rows = sorted(movements(world), key=lambda row: row["quantity"])
        assert [row["quantity"] for row in rows] == [-5, 10]
        assert rows[0]["metadata"]["sale_price"] == 130
        assert sorted(row["type"] for row in world.transactions(corretora)) == ["EXPENSE", "INCOME"]

    def test_a_typed_operation_is_linked(self, world, user):
        item_id, pluggy_item, _corretora = broker(world)
        typed = world.call("post", "/api/investments", json={
            "asset_class": "STOCKS", "ticker_or_name": "PETR4", "quantity": 100, "average_price": 38.4,
            "metadata": {"purchase_date": "2026-10-21", "cash_account_id": None},
        })[0]["id"]
        position = world.fake.add_position(pluggy_item, "PETR4", 100)
        world.fake.add_operation(position, "BUY", 100, 38.5, "2026-10-20")
        assert world.sync(item_id)["result"]["investments"]["linked"] == 1
        assert [row["id"] for row in movements(world)] == [typed]
        assert operations(user["id"])[0]["investment_id"] == typed

    def test_the_owners_class_wins(self, world):
        item_id, pluggy_item, _corretora = broker(world)
        world.call("post", "/api/investments", json={
            "asset_class": "REIT", "ticker_or_name": "MXRF11", "quantity": 10, "average_price": 10,
            "metadata": {"purchase_date": "2026-01-05", "cash_account_id": None},
        })
        position = world.fake.add_position(pluggy_item, "MXRF11", 30)
        world.fake.add_operation(position, "BUY", 20, 9.8, "2026-10-20")
        world.sync(item_id)
        assert {row["asset_class"] for row in movements(world)} == {"REIT"}

    def test_an_unknown_ticker_waits(self, world, user):
        item_id, pluggy_item, _corretora = broker(world)
        position = world.fake.add_position(pluggy_item, "ZZZZ3", 10)
        world.fake.add_operation(position, "BUY", 10, 5, "2026-10-20")
        world.sync(item_id)
        assert movements(world) == []
        assert operations(user["id"])[0]["held_reason"] == "unknown_asset"

    def test_a_sale_without_position_waits_and_writes_nothing(self, world, user):
        item_id, pluggy_item, corretora = broker(world)
        position = world.fake.add_position(pluggy_item, "PETR4", 0)
        world.fake.add_operation(position, "SELL", 10, 40, "2026-10-20")
        world.sync(item_id)
        assert movements(world) == [] and world.transactions(corretora) == []
        [op] = operations(user["id"])
        assert op["state"] == "HELD" and op["held_reason"].startswith("refused")

    def test_before_a_corporate_action_it_waits(self, world, user):
        item_id, pluggy_item, _corretora = broker(world)
        created = world.call("post", "/api/investments", json={
            "asset_class": "STOCKS", "ticker_or_name": "PETR4", "quantity": 10, "average_price": 30,
            "metadata": {"purchase_date": "2026-01-05", "cash_account_id": None},
        })[0]
        world.call("post", "/api/corporate-actions", json={
            "asset_id": created["asset_id"], "action_type": "SPLIT", "ex_date": "2026-10-15", "ratio_from": 1,
            "ratio_to": 2,
        })
        position = world.fake.add_position(pluggy_item, "PETR4", 30)
        world.fake.add_operation(position, "BUY", 10, 30, "2026-10-10")
        world.sync(item_id)
        assert len(movements(world)) == 1
        assert operations(user["id"])[0]["held_reason"].startswith("corporate_action")

    @pytest.mark.parametrize("kind, op", [("FIXED_INCOME", "BUY"), ("EQUITY", "TRANSFER"), ("EQUITY", "INTEREST")])
    def test_other_types_wait_for_the_owner(self, world, user, kind, op):
        item_id, pluggy_item, _corretora = broker(world)
        position = world.fake.add_position(pluggy_item, "PETR4", 10, kind=kind)
        world.fake.add_operation(position, op, 10, 30, "2026-10-20")
        world.sync(item_id)
        assert movements(world) == []
        assert operations(user["id"])[0]["held_reason"] == "type"

    def test_undo_is_for_good(self, world, user):
        item_id, pluggy_item, corretora = broker(world)
        position = world.fake.add_position(pluggy_item, "PETR4", 100)
        world.fake.add_operation(position, "BUY", 100, 38.5, "2026-10-20")
        world.sync(item_id)
        [movement] = movements(world)
        world.call("delete", f"/api/investments/{movement['id']}")
        assert world.sync(item_id)["result"]["investments"]["dismissed"] == 1
        world.sync(item_id)
        assert movements(world) == [] and world.transactions(corretora) == []
        assert operations(user["id"])[0]["state"] == "DISMISSED"

    def test_only_reads(self, world):
        item_id, pluggy_item, _corretora = broker(world)
        world.fake.add_position(pluggy_item, "PETR4", 100)
        world.sync(item_id)
        assert {call[0] for call in world.fake.calls} <= {
            "get_item", "list_accounts", "list_transactions", "list_investments", "list_investment_transactions",
        }

    def test_another_user_is_untouched(self, world, client, other_user, fake_pluggy):
        item_id, pluggy_item, _corretora = broker(world)
        position = world.fake.add_position(pluggy_item, "PETR4", 100)
        world.fake.add_operation(position, "BUY", 100, 38.5, "2026-10-20")
        world.sync(item_id)
        other = World(client, other_user["headers"], fake_pluggy)
        assert movements(other) == []


class TestPortfolioCheck:
    def test_positions_d_minus_one_plus_later_operations(self, world):
        item_id, pluggy_item, _corretora = broker(world)
        # Posicao de 26/10 (D-1) sem a compra de 27/10: a compra a explica.
        position = world.fake.add_position(pluggy_item, "PETR4", 100, day="2026-10-26")
        world.fake.add_operation(position, "BUY", 100, 38.5, "2026-10-20")
        world.fake.add_operation(position, "BUY", 50, 38.5, "2026-10-27")
        world.sync(item_id)
        check = world.overview()["investments"]
        [entry] = check["positions"]
        assert (entry["pluggy_quantity"], entry["app_quantity"], entry["matches"]) == (100, 150, True)
        assert check["mismatched_count"] == 0

    def test_a_missing_operation_is_a_mismatch(self, world):
        item_id, pluggy_item, _corretora = broker(world)
        world.fake.add_position(pluggy_item, "PETR4", 100)
        world.sync(item_id)
        check = world.overview()["investments"]
        assert check["positions"][0]["matches"] is False and check["mismatched_count"] == 1

    def test_cash_waiting_settlement_is_not_a_difference(self, world):
        item_id, pluggy_item, corretora = broker(world, balance=5000.0)
        world.call("post", "/api/transactions", json={
            "account_id": corretora, "amount": 5000, "date": "2026-10-01", "type": "INCOME", "category": "Receita",
        })
        position = world.fake.add_position(pluggy_item, "PETR4", 100)
        # Comprou ontem: o app ja tirou 3.850, a corretora so tira no D+2.
        world.fake.add_operation(position, "BUY", 100, 38.5, "2026-10-26")
        world.sync(item_id)
        cash = world.overview()["investments"]["cash"]
        assert (cash["difference"], cash["unsettled"], cash["unexplained"]) == (3850.0, 3850.0, 0.0)

    def test_held_operations_are_listed(self, world):
        item_id, pluggy_item, _corretora = broker(world)
        position = world.fake.add_position(pluggy_item, "CDB BANCO X", 1, kind="FIXED_INCOME", subtype="CDB")
        world.fake.add_operation(position, "BUY", 1, 1000, "2026-10-20")
        world.sync(item_id)
        [held] = world.overview()["investments"]["held"]
        assert (held["type"], held["reason"]) == ("BUY", "type")

    def test_no_positions_no_check(self, world):
        broker(world)
        assert world.overview()["investments"] is None


def test_business_days_back():
    module = importlib.import_module("services.open_finance_investments")
    from datetime import date

    assert module.business_days_back(date(2026, 10, 27), 2) == date(2026, 10, 23)  # terca -> sexta
    assert module.business_days_back(date(2026, 10, 29), 2) == date(2026, 10, 27)


@pytest.mark.parametrize("value, total", [(None, 0), (2.5, 2.5), ({"brokerageFee": 2.5, "b3": 0.37}, 2.87), (-1, 0)])
def test_expenses_total(value, total):
    module = importlib.import_module("services.open_finance_investments")
    assert module.expenses_total(value) == total
