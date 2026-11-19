"""Tudo automatico, fase 2: nenhuma linha da carteira espera o dono sem motivo
(docs/automation-prompt.md; services/open_finance_investments.py e
services/open_finance_fixed_income.py).

O que estes testes protegem, cada regra com a forma real que a Pluggy mandou
(2026-11-18):
- a TRANSFER de renda variavel (quantidade 0, valor de mercado) que so registra
  a custodia: com o app tendo no dia o que a Pluggy mostra, sai sozinha
  (DISMISSED `auto:custody`, decisao desfazivel); faltando, espera com a falta;
- o INTEREST de uma acao e ligado ao provento que o app ja calculou (nunca um
  segundo); sem um que case, espera;
- o titulo sem indexador com `rate` 0 e `fixedAnnualRate` > 0 e pre a essa
  taxa (uma deducao, nunca um chute: `rate` ausente continua esperando);
- a TRANSFER de renda fixa (titulo vindo de outra corretora) vira a compra ao
  custo de origem, sem caixa, e os resgates que esperavam por ela se resolvem
  no mesmo pull; o que o dono ja lancou com o mesmo custo e ligado;
- a AMORTIZATION e um provento AMORTIZATION, sem IR;
- o Renda+ cujo nome nao traz o ano e achado pelo vencimento;
- a operacao de um fundo do banco ja zerado sai sozinha (o dinheiro ja e o
  aporte/resgate da conta); com saldo, espera `fund:open`;
- cada decisao fica em auto_decisions; o "Desfazer" devolve a linha a esperar,
  e a regra nao decide de novo.
"""

import importlib

import pytest

from open_finance_world import World, fake_pluggy, open_finance_module  # noqa: F401
from test_open_finance_investments import broker, movements, operations
from test_treasury import prices_csv

AUTO = "/api/review/auto"
PRE_SHAPE = {"rateType": None, "rate": 0, "fixedAnnualRate": 13.5, "ratePeriodicity": "DAILY",
             "dueDate": "2028-04-03T00:00:00.000Z"}
LCA_SHAPE = {"rateType": "CDI", "rate": 95, "fixedAnnualRate": None, "dueDate": "2027-04-01T00:00:00.000Z"}


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


def typed_stock(world, ticker, quantity, day):
    return world.call("post", "/api/investments", json={
        "asset_class": "STOCKS", "ticker_or_name": ticker, "quantity": quantity, "average_price": 10,
        "metadata": {"purchase_date": day, "cash_account_id": None},
    })[0]


def decisions(world):
    return world.call("get", AUTO)["items"]


def op_of(user_id, op_type):
    [row] = [row for row in operations(user_id) if row["op_type"] == op_type]
    return row


def fixed_rows(world):
    return [row for row in movements(world) if row["asset_class"] == "FIXED_INCOME"]


class TestEquityCustody:
    def setup(self, world, typed=100, pluggy=100):
        item_id, pluggy_item, _corretora = broker(world)
        typed_stock(world, "BBAS3", typed, "2024-03-01")
        position = world.fake.add_position(pluggy_item, "BBAS3", pluggy, value=22.0)
        # Real: quantidade 0, o valor de mercado no amount.
        world.fake.add_operation(position, "TRANSFER", 0, 0, "2026-09-29", amount=2200.0)
        return item_id, position

    def test_the_app_already_holds_it_so_it_leaves_by_itself(self, world, user):
        item_id, _position = self.setup(world)
        world.sync(item_id)
        row = op_of(user["id"], "TRANSFER")
        assert (row["state"], row["held_reason"]) == ("DISMISSED", "auto:custody")
        assert len(movements(world)) == 1  # nada gravado
        [decision] = decisions(world)
        assert (decision["kind"], decision["target_id"], decision["undoable"]) == ("investment_custody", row["id"], True)
        assert world.overview()["investments"]["held"] == []

    def test_short_in_the_app_it_waits_with_the_gap(self, world, user):
        item_id, _position = self.setup(world, typed=60)
        world.sync(item_id)
        row = op_of(user["id"], "TRANSFER")
        assert (row["state"], row["held_reason"]) == ("HELD", "custody:short 40.0")
        assert decisions(world) == []

    def test_later_buys_of_the_same_pull_count_before_deciding(self, world, user):
        # Posicao de hoje 150 = 100 de antes + 50 comprados depois da transferencia.
        item_id, pluggy_item, _corretora = broker(world)
        typed_stock(world, "BBAS3", 100, "2024-03-01")
        position = world.fake.add_position(pluggy_item, "BBAS3", 150, value=22.0)
        world.fake.add_operation(position, "TRANSFER", 0, 0, "2026-09-29", amount=2200.0)
        world.fake.add_operation(position, "BUY", 50, 22.0, "2026-10-05")
        world.sync(item_id)
        assert op_of(user["id"], "TRANSFER")["state"] == "DISMISSED"

    def test_undo_puts_it_back_and_the_rule_never_retakes_it(self, world, user):
        item_id, _position = self.setup(world)
        world.sync(item_id)
        [decision] = decisions(world)
        undone = world.call("post", f"{AUTO}/{decision['id']}/undo")
        assert undone["undone_at"]
        row = op_of(user["id"], "TRANSFER")
        assert (row["state"], row["held_reason"]) == ("HELD", "undone")
        world.sync(item_id)
        assert op_of(user["id"], "TRANSFER")["state"] == "HELD"
        assert len(decisions(world)) == 1
        assert [held["reason"] for held in world.overview()["investments"]["held"]] == ["undone"]

    def test_a_repeat_pull_records_one_decision(self, world):
        item_id, _position = self.setup(world)
        world.sync(item_id)
        world.sync(item_id)
        assert len(decisions(world)) == 1


class TestEquityInterest:
    def setup(self, world, proceed_net=8.92, payment_date="2026-10-15"):
        item_id, pluggy_item, _corretora = broker(world)
        asset_id = typed_stock(world, "ITSA4", 100, "2024-03-01")["asset_id"]
        proceed = world.call("post", "/api/investment-proceeds", json={
            "asset_id": asset_id, "proceeds_type": "JCP", "record_date": "2026-09-01",
            "payment_date": payment_date, "gross_amount": round(proceed_net / 0.825, 2),
            "tax_amount": round(proceed_net / 0.825 - proceed_net, 2),
        })
        position = world.fake.add_position(pluggy_item, "ITSA4", 100, value=10.0)
        return item_id, position, proceed

    def test_it_links_to_the_computed_proceed(self, world, user):
        item_id, position, proceed = self.setup(world)
        world.fake.add_operation(position, "INTEREST", 0, 0, "2026-10-16", amount=8.92)
        world.sync(item_id)
        row = op_of(user["id"], "INTEREST")
        assert (row["state"], row["proceed_id"]) == ("LINKED", proceed["id"])
        assert len(world.call("get", "/api/investment-proceeds")) == 1
        [decision] = decisions(world)
        assert decision["kind"] == "investment_proceed_link"

    def test_five_cents_apart_still_links(self, world, user):
        item_id, position, proceed = self.setup(world, proceed_net=17.05)
        world.fake.add_operation(position, "INTEREST", 0, 0, "2026-10-15", amount=17.09)
        world.sync(item_id)
        assert op_of(user["id"], "INTEREST")["proceed_id"] == proceed["id"]

    @pytest.mark.parametrize("amount, day", [(9.50, "2026-10-15"), (8.92, "2026-10-25")])
    def test_another_amount_or_day_waits(self, world, user, amount, day):
        item_id, position, _proceed = self.setup(world)
        world.fake.add_operation(position, "INTEREST", 0, 0, day, amount=amount)
        world.sync(item_id)
        row = op_of(user["id"], "INTEREST")
        assert (row["state"], row["held_reason"]) == ("HELD", "proceed:unmatched")
        assert decisions(world) == []

    def test_one_proceed_links_once(self, world, user):
        item_id, position, proceed = self.setup(world)
        world.fake.add_operation(position, "INTEREST", 0, 0, "2026-10-15", amount=8.92)
        world.fake.add_operation(position, "INTEREST", 0, 0, "2026-10-16", amount=8.92)
        world.sync(item_id)
        states = sorted(row["state"] for row in operations(user["id"]) if row["op_type"] == "INTEREST")
        assert states == ["HELD", "LINKED"]

    def test_undo_unlinks_and_waits(self, world, user):
        item_id, position, proceed = self.setup(world)
        world.fake.add_operation(position, "INTEREST", 0, 0, "2026-10-15", amount=8.92)
        world.sync(item_id)
        [decision] = decisions(world)
        world.call("post", f"{AUTO}/{decision['id']}/undo")
        world.sync(item_id)
        row = op_of(user["id"], "INTEREST")
        assert (row["state"], row["proceed_id"]) == ("HELD", None)
        # O provento calculado fica.
        assert [item["id"] for item in world.call("get", "/api/investment-proceeds")] == [proceed["id"]]


class TestPreByDeduction:
    def base(self, **fields):
        return {"type": "FIXED_INCOME", "subtype": "CDB", "name": "CDB C6", **PRE_SHAPE, **fields}

    def test_rate_zero_and_a_fixed_rate_is_pre(self, module):
        terms = module.title_terms(self.base())
        assert terms["metadata"]["rate_type"] == "PRE" and terms["metadata"]["annual_rate"] == 0.135
        assert terms["deduced"] == {"rateType": "PRE", "fixedAnnualRate": 13.5}

    @pytest.mark.parametrize("fields, reason", [
        ({"rate": None}, "missing:rateType"),       # ausente nao e zero
        ({"rate": 100}, "missing:rateType"),        # uma parte do CDI: indexador desconhecido
        ({"fixedAnnualRate": 0}, "missing:rateType"),
        ({"fixedAnnualRate": None}, "missing:rateType"),
        ({"fixedAnnualRate": 0.135}, "unmapped:fixedAnnualRate"),  # a unidade seria um chute
    ])
    def test_anything_else_still_waits(self, module, fields, reason):
        with pytest.raises(module.Held) as held:
            module.title_terms(self.base(**fields))
        assert held.value.reason == reason

    def test_a_present_rate_type_is_never_overridden(self, module):
        terms = module.title_terms(self.base(rateType="CDI", rate=110, fixedAnnualRate=None))
        assert terms["metadata"]["indexer"] == "CDI" and "deduced" not in terms

    def test_the_buy_is_recorded_and_the_decision_shown(self, world, user):
        item_id, pluggy_item, _corretora = broker(world)
        position = world.fake.add_position(pluggy_item, None, 1, kind="FIXED_INCOME", subtype="CRA", value=1000.0,
                                           name="CRA BTG", **PRE_SHAPE)
        world.fake.add_operation(position, "BUY", 1, 1000, "2026-10-01")
        world.sync(item_id)
        [row] = fixed_rows(world)
        assert (row["metadata"]["rate_type"], row["metadata"]["annual_rate"]) == ("PRE", 0.135)
        assert row["metadata"]["is_tax_free"] is True
        [decision] = decisions(world)
        assert (decision["kind"], decision["undoable"]) == ("investment_rate_deduced", False)
        response = world.client.post(f"{AUTO}/{decision['id']}/undo", headers=world.auth)
        assert response.status_code == 409


class TestCustodyIn:
    """Real: LCA Original e LCIs BRB transferidas em 2026-04-01, com o custo de
    origem no netAmount; os resgates depois esperavam `missing:buy`."""

    def setup(self, world, cost=1000.0, market=1080.0, units=1000):
        item_id, pluggy_item, corretora = broker(world)
        position = world.fake.add_position(pluggy_item, None, units, kind="FIXED_INCOME", subtype="LCA",
                                           value=1.08, name="LCA ORIGINAL", **LCA_SHAPE)
        world.fake.add_operation(position, "TRANSFER", units, market / units, "2026-04-01", amount=market)
        world.fake.investment_transactions[position][-1]["netAmount"] = cost
        return item_id, position, corretora

    def test_the_transfer_becomes_a_buy_at_cost_without_cash(self, world, user):
        item_id, _position, corretora = self.setup(world)
        world.sync(item_id)
        [row] = fixed_rows(world)
        assert (row["ticker_or_name"], row["average_price"]) == ("LCA ORIGINAL", 1000)
        metadata = row["metadata"]
        assert metadata["purchase_date"] == "2026-04-01" and metadata["custody_transfer"] is True
        assert metadata["open_finance_units"] == 1000 and "cash_account_id" not in metadata
        assert world.transactions(corretora) == []
        transfer = op_of(user["id"], "TRANSFER")
        assert (transfer["state"], transfer["investment_id"]) == ("RECORDED", row["id"])
        [decision] = decisions(world)
        assert (decision["kind"], decision["undoable"]) == ("investment_custody_in", False)

    def test_the_waiting_redemption_resolves_in_the_same_pull(self, world, user):
        item_id, position, _corretora = self.setup(world)
        world.fake.add_operation(position, "SELL", 400, 1.1, "2026-04-01")
        world.fake.add_operation(position, "SELL", 600, 1.12, "2026-09-10")
        world.sync(item_id)
        assert [row["state"] for row in operations(user["id"])] == ["RECORDED", "RECORDED", "RECORDED"]
        redemptions = [row for row in fixed_rows(world) if row["metadata"].get("is_redemption")]
        assert sorted(row["metadata"]["open_finance_units"] for row in redemptions) == [400, 600]

    def test_a_held_redemption_fills_itself_once_the_transfer_records(self, world, user):
        # Antes: a transferencia esperava; o resgate, `missing:buy`. Agora, o pull seguinte resolve os dois.
        item_id, position, _corretora = self.setup(world)
        world.fake.investment_transactions[position][-1]["netAmount"] = None
        world.fake.add_operation(position, "SELL", 1000, 1.1, "2026-09-10")
        world.sync(item_id)
        assert sorted(row["held_reason"] for row in operations(user["id"])) == ["missing:buy", "missing:netAmount"]
        world.fake.investment_transactions[position][0]["netAmount"] = 1000.0
        world.sync(item_id)
        assert {row["state"] for row in operations(user["id"])} == {"RECORDED"}

    def test_a_title_the_owner_typed_at_the_old_broker_is_linked(self, world, user):
        typed = world.call("post", "/api/investments", json={
            "asset_class": "FIXED_INCOME", "ticker_or_name": "LCA Banco Original", "quantity": 1, "average_price": 1000,
            "metadata": {"purchase_date": "2025-03-10", "fixed_income_type": "LCA", "rate_type": "POS",
                         "indexer": "CDI", "cdi_percentage": 0.95, "is_tax_free": True, "cash_account_id": None},
        })[0]
        item_id, position, _corretora = self.setup(world)
        world.fake.add_operation(position, "SELL", 1000, 1.1, "2026-09-10")
        world.sync(item_id)
        transfer = op_of(user["id"], "TRANSFER")
        assert (transfer["state"], transfer["investment_id"]) == ("LINKED", typed["id"])
        # O resgate baixa o lote digitado, no ativo dele.
        [redemption] = [row for row in fixed_rows(world) if row["metadata"].get("is_redemption")]
        assert redemption["metadata"]["related_id"] == typed["id"]
        assert redemption["asset_id"] == typed["asset_id"]

    def test_without_the_title_terms_it_waits_for_them(self, world, user):
        item_id, pluggy_item, _corretora = broker(world)
        position = world.fake.add_position(pluggy_item, None, 1000, kind="FIXED_INCOME", subtype="LCI",
                                           value=1.0, name="LCI BRB")
        world.fake.add_operation(position, "TRANSFER", 1000, 1.0, "2026-04-01")
        world.sync(item_id)
        assert op_of(user["id"], "TRANSFER")["held_reason"] == "missing:rateType"


class TestAmortization:
    def test_it_is_an_amortization_proceed_without_tax(self, world, user):
        item_id, pluggy_item, _corretora = broker(world)
        position = world.fake.add_position(pluggy_item, None, 1, kind="FIXED_INCOME", subtype="CDB", value=1000.0,
                                           name="CDB X", rateType="CDI", rate=110)
        world.fake.add_operation(position, "BUY", 1, 1000, "2026-04-01")
        world.fake.add_operation(position, "AMORTIZATION", 0, 0, "2026-10-20", amount=117.64)
        world.sync(item_id)
        [proceed] = world.call("get", "/api/investment-proceeds")
        assert (proceed["proceeds_type"], proceed["gross_amount"], proceed["tax_amount"]) == ("AMORTIZATION", 117.64, 0)
        assert op_of(user["id"], "AMORTIZATION")["state"] == "RECORDED"


class TestRendaMais:
    def raw(self, **fields):
        return {"type": "FIXED_INCOME", "subtype": "TREASURY", "rateType": "IPCA", "fixedAnnualRate": 7.07,
                "name": "Tesouro Renda+ Aposentadoria Extra (NTNB1)", "isin": "BRSTNCNAP088",
                "dueDate": "2084-12-15T00:00:00.000Z", **fields}

    def test_a_name_without_the_year_is_found_by_the_due_date(self, module, tesouro):
        terms = module.title_terms(self.raw(), tesouro.get_prices())
        assert terms["ticker"] == "Tesouro Renda+ Aposentadoria Extra (NTNB1) 2084"
        # O nome do ativo acha o mesmo titulo na tela (services/treasury.py).
        assert tesouro.get_prices().find_title(terms["ticker"]).maturity.isoformat() == "2084-12-15"

    @pytest.mark.parametrize("fields", [{"dueDate": "2085-12-15"}, {"dueDate": None}])
    def test_another_or_no_due_date_still_waits(self, module, tesouro, fields):
        with pytest.raises(module.Held) as held:
            module.title_terms(self.raw(**fields), tesouro.get_prices())
        assert held.value.reason == "unmapped:name"


class TestBankFund:
    def setup(self, world, quantity, balance):
        item_id, pluggy_item, corretora = broker(world)
        position = world.fake.add_position(pluggy_item, None, quantity, kind="MUTUAL_FUND", subtype="FIXED_INCOME_FUND",
                                           value=2.5, name="BB RF LP HIGH")
        world.fake.investments[pluggy_item][-1]["balance"] = balance
        world.fake.add_operation(position, "BUY", 400, 2.5, "2026-08-03")
        world.fake.add_operation(position, "TAX", 4, 2.5, "2026-08-31")
        world.fake.add_operation(position, "SELL", 396, 2.6, "2026-09-15")
        return item_id, corretora

    def test_a_closed_fund_leaves_by_itself_and_records_nothing(self, world, user):
        item_id, corretora = self.setup(world, 0, 0)
        world.sync(item_id)
        assert {(row["state"], row["held_reason"]) for row in operations(user["id"])} == {("DISMISSED", "auto:closed_fund")}
        assert movements(world) == [] and world.transactions(corretora) == []
        kinds = [decision["kind"] for decision in decisions(world)]
        assert kinds == ["investment_closed_fund"] * 3

    def test_a_fund_with_a_balance_waits(self, world, user):
        item_id, _corretora = self.setup(world, 120, 300.0)
        world.sync(item_id)
        assert {row["held_reason"] for row in operations(user["id"])} == {"fund:open"}
        assert decisions(world) == []

    def test_undo_brings_one_line_back(self, world, user):
        item_id, _corretora = self.setup(world, 0, 0)
        world.sync(item_id)
        first = decisions(world)[0]
        world.call("post", f"{AUTO}/{first['id']}/undo")
        world.sync(item_id)
        assert sorted(row["state"] for row in operations(user["id"])) == ["DISMISSED", "DISMISSED", "HELD"]
