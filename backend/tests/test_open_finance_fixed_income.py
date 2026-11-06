"""Renda fixa, Tesouro e cupom da corretora so com dados exatos (Fase 3,
services/open_finance_fixed_income.py).

O que estes testes protegem:
- a posicao inteira da Pluggy fica guardada (`raw`, sem `transactions`), a cada pull;
- uma compra de renda fixa e gravada quando a posicao mapeia exatamente
  (CDI com `rate`, IPCA/pre com `fixedAnnualRate`, o tipo do titulo); senao ela
  espera com o campo (`missing:<campo>` / `unmapped:<campo>`), nunca com um chute;
- o Tesouro precisa do titulo no arquivo de precos, do mesmo indexador e do vencimento;
- o resgate baixa as compras do mesmo investimento, a mais antiga primeiro (PEPS);
- o cupom e um provento INTEREST com o IR desde a primeira compra, e a linha do
  extrato que ja o pagou vira o lancamento dele (nunca dois);
- sem caixa ligado (o dinheiro ja e uma linha do extrato da corretora);
- ligado ao que o dono ja lancou; idempotente; desfazer e para sempre.
"""

import importlib
import json

import pytest

from open_finance_world import World, bank_tx, fake_pluggy, open_finance_module  # noqa: F401
from test_open_finance_investments import broker, movements, operations, rows_of
from test_treasury import prices_csv

CDB_110 = {"rateType": "CDI", "rate": 110, "fixedAnnualRate": None, "dueDate": "2028-10-20T00:00:00.000Z",
           "issuer": "BANCO X", "isin": "BRBCOXCDB001"}


@pytest.fixture()
def world(client, auth, fake_pluggy):
    return World(client, auth, fake_pluggy)


@pytest.fixture()
def module(app_module):
    return importlib.import_module("services.open_finance_fixed_income")


@pytest.fixture()
def tesouro(app_module):
    module = importlib.import_module("tesouro_client")
    module.set_prices(module.parse_prices_csv(prices_csv()))
    yield module
    module.set_prices(None)


def cdb(world, pluggy_item, name="CDB BANCO X", subtype="CDB", **fields):
    return world.fake.add_position(
        pluggy_item, None, 1500, kind="FIXED_INCOME", subtype=subtype, value=1.0, name=name, **fields,
    )


def fixed_rows(world):
    return [row for row in movements(world) if row["asset_class"] == "FIXED_INCOME"]


def held_reason(user_id):
    return [row["held_reason"] for row in operations(user_id) if row["state"] == "HELD"]


class TestRawPosition:
    def test_the_whole_position_is_kept_without_transactions(self, world, user):
        item_id, pluggy_item, _corretora = broker(world)
        position = cdb(world, pluggy_item, **CDB_110, transactions=[{"id": "x"}])
        world.sync(item_id)
        [row] = rows_of("open_finance_positions", "user_id = ?", (user["id"],))
        raw = json.loads(row["raw"])
        assert raw["id"] == position and raw["rate"] == 110 and raw["issuer"] == "BANCO X"
        assert "transactions" not in raw

    def test_it_is_updated_on_every_pull(self, world, user):
        item_id, pluggy_item, _corretora = broker(world)
        cdb(world, pluggy_item)
        world.sync(item_id)
        world.fake.investments[pluggy_item][0]["rateType"] = "CDI"
        world.sync(item_id)
        [row] = rows_of("open_finance_positions", "user_id = ?", (user["id"],))
        assert json.loads(row["raw"])["rateType"] == "CDI"


class TestTitleTerms:
    """O mapeamento puro: so o que tem um significado so."""

    def base(self, **fields):
        return {"type": "FIXED_INCOME", "subtype": "CDB", "name": "CDB BANCO X", **fields}

    def test_cdi_with_a_rate_is_percent_of_cdi(self, module):
        terms = module.title_terms(self.base(rateType="CDI", rate=110))
        assert terms["metadata"] == {
            "fixed_income_type": "CDB", "rate_type": "POS", "indexer": "CDI", "cdi_percentage": 1.1,
            "is_tax_free": False,
        }

    def test_ipca_with_a_fixed_rate(self, module):
        metadata = module.title_terms(self.base(rateType="IPCA", fixedAnnualRate=6.5))["metadata"]
        assert (metadata["rate_type"], metadata["indexer"], metadata["annual_rate"]) == ("POS", "IPCA", 0.065)

    @pytest.mark.parametrize("rate_type", ["PRE", "PREFIXADO", "PRE_FIXADO", "pre-fixado"])
    def test_pre_with_a_fixed_rate(self, module, rate_type):
        metadata = module.title_terms(self.base(rateType=rate_type, fixedAnnualRate=12.5))["metadata"]
        assert (metadata["rate_type"], metadata["annual_rate"]) == ("PRE", 0.125)
        assert "indexer" not in metadata

    @pytest.mark.parametrize("subtype, kind, free", [
        ("LCI", "LCI", True), ("LCA", "LCA", True), ("CRI", "CRI", True), ("CRA", "CRA", True),
        ("LC", "LC", False), ("DEBENTURES", "DEBENTURE", False), ("CDB", "CDB", False),
    ])
    def test_the_title_type_decides_the_tax(self, module, subtype, kind, free):
        metadata = module.title_terms(self.base(subtype=subtype, rateType="CDI", rate=95))["metadata"]
        assert (metadata["fixed_income_type"], metadata["is_tax_free"]) == (kind, free)

    @pytest.mark.parametrize("fields, reason", [
        ({}, "missing:rateType"),
        ({"rateType": "CDI"}, "missing:rate"),
        ({"rateType": "IPCA", "rate": 6.5}, "missing:fixedAnnualRate"),
        ({"rateType": "PRE"}, "missing:fixedAnnualRate"),
        ({"rateType": "SELIC", "rate": 100}, "unmapped:rateType"),
        ({"rateType": "IGPM", "fixedAnnualRate": 5}, "unmapped:rateType"),
        # CDI com taxa fixa: CDI+ ou outra coisa? Espera.
        ({"rateType": "CDI", "rate": 100, "fixedAnnualRate": 1.5}, "unmapped:fixedAnnualRate"),
        # A unidade seria um chute: 1,10 e 110% ou 1,1%?
        ({"rateType": "CDI", "rate": 1.10}, "unmapped:rate"),
        ({"rateType": "IPCA", "fixedAnnualRate": 0.065}, "unmapped:fixedAnnualRate"),
        ({"rateType": "CDI", "rate": "cento e dez"}, "unmapped:rate"),
        ({"rateType": "CDI", "rate": 110, "subtype": None}, "missing:subtype"),
        ({"rateType": "CDI", "rate": 110, "subtype": "COE"}, "unmapped:subtype"),
        ({"rateType": "CDI", "rate": 110, "name": " "}, "missing:name"),
        ({"rateType": "CDI", "rate": 110, "type": "MUTUAL_FUND"}, "unmapped:type"),
    ])
    def test_hold_never_guess(self, module, fields, reason):
        with pytest.raises(module.Held) as held:
            module.title_terms(self.base(**fields))
        assert held.value.reason == reason

    def test_no_position_is_missing(self, module):
        with pytest.raises(module.Held) as held:
            module.title_terms(None)
        assert held.value.reason == "missing:position"


class TestTreasuryTerms:
    def base(self, **fields):
        return {"type": "FIXED_INCOME", "subtype": "TREASURY", "name": "Tesouro IPCA+ 2045",
                "rateType": "IPCA", "fixedAnnualRate": 6.5, **fields}

    def test_a_title_in_the_price_file(self, module, tesouro):
        terms = module.title_terms(self.base(dueDate="2045-05-15"), tesouro.get_prices())
        assert terms["ticker"] == "Tesouro IPCA+ 2045"
        assert terms["metadata"]["fixed_income_type"] == "TESOURO"
        assert terms["metadata"]["annual_rate"] == 0.065

    @pytest.mark.parametrize("fields, reason", [
        ({"name": "Tesouro IPCA+ 2099"}, "unmapped:name"),
        ({"name": "NTN-B qualquer"}, "unmapped:name"),
        ({"name": "Tesouro Prefixado 2045", "rateType": "PRE"}, "unmapped:name"),
        ({"rateType": "PRE"}, "unmapped:rateType"),
        ({"dueDate": "2045-08-15"}, "unmapped:dueDate"),
        ({"name": "Tesouro Selic 2029", "rateType": "SELIC", "fixedAnnualRate": None}, "unmapped:rateType"),
    ])
    def test_not_exact_waits(self, module, tesouro, fields, reason):
        with pytest.raises(module.Held) as held:
            module.title_terms(self.base(**fields), tesouro.get_prices())
        assert held.value.reason == reason

    def test_without_the_price_file_it_waits(self, module):
        with pytest.raises(module.Held) as held:
            module.title_terms(self.base(), None)
        assert held.value.reason == "missing:tesouro_prices"


class TestBuy:
    def test_a_complete_cdb_is_recorded_without_cash(self, world, user):
        item_id, pluggy_item, corretora = broker(world)
        position = cdb(world, pluggy_item, **CDB_110)
        world.fake.add_operation(position, "BUY", 1500, 1.0, "2026-10-20")
        body = world.sync(item_id)
        assert body["result"]["investments"]["recorded"] == 1
        [row] = fixed_rows(world)
        assert (row["ticker_or_name"], row["quantity"], row["average_price"]) == ("CDB BANCO X", 1, 1500)
        metadata = row["metadata"]
        assert (metadata["indexer"], metadata["cdi_percentage"], metadata["fixed_income_type"]) == ("CDI", 1.1, "CDB")
        assert metadata["purchase_date"] == "2026-10-20" and metadata["open_finance_units"] == 1500
        # O dinheiro ja e a linha do extrato da corretora: nada de caixa ligado.
        assert "cash_account_id" not in metadata and world.transactions(corretora) == []
        [op] = operations(user["id"])
        assert (op["state"], op["investment_id"]) == ("RECORDED", row["id"])

    def test_rate_type_missing_waits(self, world, user):
        item_id, pluggy_item, _corretora = broker(world)
        position = cdb(world, pluggy_item, rate=110)
        world.fake.add_operation(position, "BUY", 1500, 1.0, "2026-10-20")
        world.sync(item_id)
        assert fixed_rows(world) == []
        assert held_reason(user["id"]) == ["missing:rateType"]

    def test_selic_waits(self, world, user):
        item_id, pluggy_item, _corretora = broker(world)
        position = cdb(world, pluggy_item, rateType="SELIC", rate=100)
        world.fake.add_operation(position, "BUY", 1500, 1.0, "2026-10-20")
        world.sync(item_id)
        assert fixed_rows(world) == []
        assert held_reason(user["id"]) == ["unmapped:rateType"]

    def test_a_held_line_fills_itself_when_the_position_completes(self, world, user):
        item_id, pluggy_item, _corretora = broker(world)
        position = cdb(world, pluggy_item)
        world.fake.add_operation(position, "BUY", 1500, 1.0, "2026-10-20")
        world.sync(item_id)
        assert held_reason(user["id"]) == ["missing:rateType"]
        world.fake.investments[pluggy_item][0].update(rateType="CDI", rate=102)
        world.sync(item_id)
        [row] = fixed_rows(world)
        assert row["metadata"]["cdi_percentage"] == 1.02
        assert held_reason(user["id"]) == []

    def test_a_repeat_pull_is_a_no_op(self, world):
        item_id, pluggy_item, _corretora = broker(world)
        position = cdb(world, pluggy_item, **CDB_110)
        world.fake.add_operation(position, "BUY", 1500, 1.0, "2026-10-20")
        world.sync(item_id)
        world.sync(item_id)
        assert len(fixed_rows(world)) == 1

    def test_a_typed_buy_of_the_same_amount_is_linked(self, world, user):
        item_id, pluggy_item, _corretora = broker(world)
        typed = world.call("post", "/api/investments", json={
            "asset_class": "FIXED_INCOME", "ticker_or_name": "CDB X 110", "quantity": 1, "average_price": 1500,
            "metadata": {"purchase_date": "2026-10-21", "cash_account_id": None, "fixed_income_type": "CDB",
                         "rate_type": "POS", "indexer": "CDI", "cdi_percentage": 1.1},
        })[0]["id"]
        position = cdb(world, pluggy_item, **CDB_110)
        world.fake.add_operation(position, "BUY", 1500, 1.0, "2026-10-20")
        assert world.sync(item_id)["result"]["investments"]["linked"] == 1
        assert [row["id"] for row in fixed_rows(world)] == [typed]

    def test_undo_is_for_good(self, world, user):
        item_id, pluggy_item, _corretora = broker(world)
        position = cdb(world, pluggy_item, **CDB_110)
        world.fake.add_operation(position, "BUY", 1500, 1.0, "2026-10-20")
        world.sync(item_id)
        [row] = fixed_rows(world)
        world.call("delete", f"/api/investments/{row['id']}")
        world.sync(item_id)
        world.sync(item_id)
        assert fixed_rows(world) == []
        assert operations(user["id"])[0]["state"] == "DISMISSED"

    def test_an_lci_is_tax_free(self, world):
        item_id, pluggy_item, _corretora = broker(world)
        position = cdb(world, pluggy_item, name="LCI BANCO Y", subtype="LCI", rateType="CDI", rate=93)
        world.fake.add_operation(position, "BUY", 1500, 1.0, "2026-10-20")
        world.sync(item_id)
        [row] = fixed_rows(world)
        assert (row["metadata"]["fixed_income_type"], row["metadata"]["is_tax_free"]) == ("LCI", True)

    def test_tesouro_goes_through_the_price_file(self, world, user, tesouro):
        item_id, pluggy_item, _corretora = broker(world)
        position = world.fake.add_position(
            pluggy_item, None, 0.85, kind="FIXED_INCOME", subtype="TREASURY", value=1200, name="Tesouro IPCA+ 2045",
            rateType="IPCA", fixedAnnualRate=6.4, dueDate="2045-05-15T00:00:00.000Z",
        )
        world.fake.add_operation(position, "BUY", 0.85, 1000, "2026-10-20")
        world.sync(item_id)
        [row] = fixed_rows(world)
        assert row["metadata"]["fixed_income_type"] == "TESOURO" and row["metadata"]["treasury_units"] == 0.85
        assert row["metadata"]["annual_rate"] == 0.064
        [asset] = [entry for entry in world.call("get", "/api/investments") if entry["id"] == row["id"]]
        assert asset["asset_category"] == "TESOURO"

    def test_tesouro_without_the_title_in_the_file_waits(self, world, user, tesouro):
        item_id, pluggy_item, _corretora = broker(world)
        position = world.fake.add_position(
            pluggy_item, None, 1, kind="FIXED_INCOME", subtype="TREASURY", value=1000, name="Tesouro IPCA+ 2099",
            rateType="IPCA", fixedAnnualRate=6.4,
        )
        world.fake.add_operation(position, "BUY", 1, 1000, "2026-10-20")
        world.sync(item_id)
        assert fixed_rows(world) == [] and held_reason(user["id"]) == ["unmapped:name"]


class TestRedemption:
    def two_buys(self, world):
        item_id, pluggy_item, corretora = broker(world)
        position = cdb(world, pluggy_item, **CDB_110)
        world.fake.add_operation(position, "BUY", 1000, 1.0, "2026-10-01")
        world.fake.add_operation(position, "BUY", 500, 1.02, "2026-10-10")
        world.sync(item_id)
        buys = sorted(fixed_rows(world), key=lambda row: row["metadata"]["purchase_date"])
        return item_id, position, corretora, buys

    def redemptions(self, world):
        return [row for row in fixed_rows(world) if row["metadata"].get("is_redemption")]

    def test_two_buys_the_oldest_lot_goes_first(self, world):
        item_id, position, corretora, (old, new) = self.two_buys(world)
        world.fake.add_operation(position, "SELL", 600, 1.05, "2026-10-20")
        world.sync(item_id)
        [part] = self.redemptions(world)
        assert part["metadata"]["related_id"] == old["id"]
        assert part["average_price"] == pytest.approx(600)
        assert part["metadata"]["open_finance_units"] == 600
        assert part["metadata"]["redemption_date"] == "2026-10-20"
        assert world.transactions(corretora) == []

    def test_more_than_the_oldest_lot_takes_the_next(self, world):
        item_id, position, _corretora, (old, new) = self.two_buys(world)
        world.fake.add_operation(position, "SELL", 1200, 1.05, "2026-10-20")
        world.sync(item_id)
        parts = sorted(self.redemptions(world), key=lambda row: row["average_price"], reverse=True)
        assert [part["metadata"]["related_id"] for part in parts] == [old["id"], new["id"]]
        assert [round(part["average_price"], 2) for part in parts] == [1000, 204]
        assert [part["metadata"]["open_finance_units"] for part in parts] == [1000, 200]

    def test_a_second_redemption_continues_from_what_is_left(self, world):
        item_id, position, _corretora, (old, new) = self.two_buys(world)
        world.fake.add_operation(position, "SELL", 600, 1.05, "2026-10-20")
        world.fake.add_operation(position, "SELL", 600, 1.06, "2026-10-21")
        world.sync(item_id)
        parts = self.redemptions(world)
        by_lot = {}
        for part in parts:
            by_lot.setdefault(part["metadata"]["related_id"], []).append(part["metadata"]["open_finance_units"])
        assert sorted(by_lot[old["id"]]) == [400, 600] and by_lot[new["id"]] == [200]
        # O primeiro lote fecha com o custo exato que restava.
        assert sum(p["average_price"] for p in parts if p["metadata"]["related_id"] == old["id"]) == pytest.approx(1000)

    def test_without_a_buy_in_the_app_it_waits(self, world, user):
        item_id, pluggy_item, _corretora = broker(world)
        position = cdb(world, pluggy_item, **CDB_110)
        world.fake.add_operation(position, "SELL", 600, 1.05, "2026-10-20")
        world.sync(item_id)
        assert fixed_rows(world) == [] and held_reason(user["id"]) == ["missing:buy"]

    def test_more_units_than_bought_waits(self, world, user):
        item_id, position, _corretora, _buys = self.two_buys(world)
        world.fake.add_operation(position, "SELL", 2000, 1.05, "2026-10-20")
        world.sync(item_id)
        assert self.redemptions(world) == [] and held_reason(user["id"]) == ["unmapped:quantity"]

    def test_plan_is_peps(self, module):
        lots = [
            {"id": "a", "units": 10, "cost": 100, "taken_units": 4, "taken_cost": 40, "unknown": False},
            {"id": "b", "units": 10, "cost": 120, "taken_units": 0, "taken_cost": 0, "unknown": False},
        ]
        plan = module.redemption_plan(lots, 8, 100)
        assert [(part["lot_id"], part["units"]) for part in plan] == [("a", 6), ("b", 2)]
        assert [round(part["cost"], 2) for part in plan] == [60, 24]
        assert [part["amount"] for part in plan] == [75.0, 25.0]


class TestInterest:
    def setup(self, world, buys=(("2026-04-01", 1000),)):
        item_id, pluggy_item, corretora = broker(world)
        position = cdb(world, pluggy_item, **CDB_110)
        for day, amount in buys:
            world.fake.add_operation(position, "BUY", amount, 1.0, day)
        return item_id, pluggy_item, position, corretora

    def test_interest_is_a_proceed_taxed_from_the_first_buy(self, world, user):
        # Primeira compra a 202 dias do cupom: 20%; a segunda (49 dias) daria 22,5%.
        item_id, _pluggy, position, _corretora = self.setup(world, (("2026-04-01", 1000), ("2026-09-01", 500)))
        world.fake.add_operation(position, "INTEREST", 1, 50, "2026-10-20")
        world.sync(item_id)
        [proceed] = world.call("get", "/api/investment-proceeds")
        assert (proceed["proceeds_type"], proceed["payment_date"]) == ("INTEREST", "2026-10-20")
        assert (proceed["gross_amount"], proceed["tax_amount"], proceed["net_amount"]) == (50, 10, 40)
        [op] = [row for row in operations(user["id"]) if row["op_type"] == "INTEREST"]
        assert (op["state"], op["proceed_id"]) == ("RECORDED", proceed["id"])

    def test_interest_without_a_buy_waits(self, world, user):
        item_id, pluggy_item, _corretora = broker(world)
        position = cdb(world, pluggy_item, **CDB_110)
        world.fake.add_operation(position, "INTEREST", 1, 50, "2026-10-20")
        world.sync(item_id)
        assert world.call("get", "/api/investment-proceeds") == []
        assert held_reason(user["id"]) == ["missing:buy"]

    def test_a_repeat_pull_and_undo(self, world, user):
        item_id, _pluggy, position, _corretora = self.setup(world)
        world.fake.add_operation(position, "INTEREST", 1, 50, "2026-10-20")
        world.sync(item_id)
        world.sync(item_id)
        [proceed] = world.call("get", "/api/investment-proceeds")
        world.call("delete", f"/api/investment-proceeds/{proceed['id']}")
        world.sync(item_id)
        world.sync(item_id)
        assert world.call("get", "/api/investment-proceeds") == []
        [op] = [row for row in operations(user["id"]) if row["op_type"] == "INTEREST"]
        assert op["state"] == "DISMISSED"

    def test_the_statement_line_that_paid_it_becomes_its_row(self, world, user):
        item_id, pluggy_item, position, corretora = self.setup(world)
        world.sync(item_id)
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        db = importlib.import_module("db")
        with db.get_db() as conn:
            conn.execute(
                "UPDATE accounts SET metadata = ? WHERE id = ? AND user_id = ?",
                (json.dumps({"portfolio_since": "2026-01-01"}), corretora, user["id"]),
            )
        [of_broker] = [account["id"] for account in world.fake.accounts[pluggy_item]]
        world.fake.add_tx(of_broker, bank_tx(40.0, "2026-10-20", "RENDIMENTO CDB BANCO X", category_id="03000000"))
        world.fake.add_operation(position, "INTEREST", 1, 50, "2026-10-20")
        world.sync(item_id)
        # Depois da leitura que paga os proventos (apply_paid_proceeds), ainda um so.
        with db.get_db() as conn:
            importlib.import_module("services.proceeds_cash").apply_paid_proceeds(conn, user["id"])
        cash = rows_of("transactions", "user_id = ? AND account_id = ?", (user["id"], corretora))
        assert [(row["source_type"], row["amount"]) for row in cash] == [("INVESTMENT_PROCEED", 40.0)]
        [proceed] = world.call("get", "/api/investment-proceeds")
        assert proceed["net_amount"] == 40.0



class TestPositionFieldsScript:
    def test_it_prints_keys_never_values(self, world, user, tmp_path):
        """scripts/position_fields.py: so leitura (mode=ro, sem importar app), as
        chaves preenchidas de cada posicao; nenhum valor alem de tipo e subtipo."""
        import sqlite3
        import subprocess
        import sys

        item_id, pluggy_item, _corretora = broker(world)
        cdb(world, pluggy_item, **CDB_110)
        world.fake.add_position(pluggy_item, "PETR4", 100, value=38.5)
        world.sync(item_id)
        config = importlib.import_module("config")
        copy = tmp_path / "copy.db"
        source = sqlite3.connect(config.DATABASE_PATH)
        target = sqlite3.connect(copy)
        source.backup(target)
        source.close()
        target.close()
        before = copy.stat().st_mtime_ns
        backend = importlib.import_module("identity_invariants").__file__.rsplit("identity_invariants", 1)[0]
        result = subprocess.run(
            [sys.executable, "scripts/position_fields.py", "--email", user["email"], "--database", str(copy)],
            cwd=backend, capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stderr
        out = result.stdout
        assert "FIXED_INCOME / CDB: " in out and "EQUITY / STOCK: " in out
        assert "rateType=sim" in out and "fixedAnnualRate=nao" in out and "issuer=sim" in out
        assert "rate" in out.split("FIXED_INCOME / CDB: ")[1].split("\n")[0].split(", ")
        for value in ("BANCO X", "BRBCOXCDB001", "1500", "110", "38.5", "PETR4", "2028-10-20"):
            assert value not in out, value
        assert copy.stat().st_mtime_ns == before
        missing = subprocess.run(
            [sys.executable, "scripts/position_fields.py", "--email", "ninguem@example.com", "--database", str(copy)],
            cwd=backend, capture_output=True, text=True, check=False,
        )
        assert missing.returncode == 2

    def test_filled_keys_skip_empty_values(self):
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        try:
            position_fields = importlib.import_module("position_fields")
        finally:
            sys.path.pop(0)
        assert position_fields.filled_keys({"a": 1, "b": None, "c": "", "d": 0, "e": {}, "f": False}) == ["a", "d", "f"]
        assert position_fields.report_lines([("FIXED_INCOME", "CDB", None)]) == [
            "FIXED_INCOME / CDB: sem raw (ainda nao puxada depois do deploy)",
        ]
