"""O extrato da corretora e o caixa da Corretora (dono, 2026-10-30).

Do real: o saldo da BTG Investimentos e o extrato inteiro menos a Conta Remunerada.
O que estes testes protegem:
- a aplicacao automatica e o bruto do pregao ficam fora; taxa, IR e renda fixa viram
  lancamento fora de despesa/receita, um por linha, nunca dois;
- o provento que o app ja tem fica com o valor e o dia do banco e nao duplica;
- o ETF de renda fixa liquida em D+1;
- a compra provisoria (posicao na frente das operacoes) sai quando a de verdade chega.
"""

import importlib

import pytest

from open_finance_world import World, bank_tx, fake_pluggy, open_finance_module  # noqa: F401
from test_open_finance_auto import auto_on, meupluggy, of_tx


@pytest.fixture()
def world(client, auth, fake_pluggy):
    return World(client, auth, fake_pluggy)


@pytest.fixture()
def broker():
    return importlib.import_module("services.broker_statement")


@pytest.fixture()
def corretora(world):
    made = meupluggy(world)
    auto_on(world)
    world.made = made
    return made["btg:0002/2-2X"]


def statement(world, of_broker, *lines):
    ids = [world.fake.add_tx(of_broker, bank_tx(amount, day, text, category_id=category)) for amount, day, text, category in lines]
    world.sync(world.made["items"]["btg"])
    return ids


class TestLines:
    @pytest.mark.parametrize("text, kind", [
        ("CONTA REMUNERADA - APLICAÇÃO AUTOMÁTICA", "sweep"),
        ("CONTA REMUNERADA - RESGATE APLICAÇÃO", "sweep"),
        ("CONTA REMUNERADA - RESGATE REMUNERAÇÃO", "sweep"),
        ("LIQ BOLSA - VISTA BRUTO - PREGÃO: 28/10/2026 - EXEC.: 85", "trade"),
        ("LIQ BOLSA - VISTA TX CCP B3 - PREGÃO: 28/10/2026", "cash"),
        ("LIQ BOLSA (IR ETF Renda Fixa IR ETF/FIDCS - RF)", "cash"),
        ("COMPRA - LCI BRB BANCO DE BRASILIA SA", "cash"),
        ("CRÉDITO REMUNERAÇÃO", "cash"),
        ("15549979 - Cashback Gestão de Carteira", "cash"),
    ])
    def test_kinds(self, broker, text, kind):
        assert broker.line_kind(text) == kind


class TestBalance:
    def test_each_line_is_one_row_and_a_repeat_writes_nothing(self, world, corretora):
        of_broker, _of, account = corretora
        statement(
            world, of_broker,
            (-0.42, "2026-10-21", "LIQ BOLSA - VISTA TX CCP B3", "03040000"),
            (-500.0, "2026-10-21", "COMPRA - CDB BANCO C6", "04000000"),
            (-300.0, "2026-10-21", "CONTA REMUNERADA - APLICAÇÃO AUTOMÁTICA", "03000000"),
            (-97.23, "2026-10-21", "LIQ BOLSA - VISTA BRUTO - PREGÃO: 19/10/2026", "03040000"),
        )
        world.sync(world.made["items"]["btg"])
        rows = world.transactions(account)
        assert sorted(row["amount"] for row in rows) == [0.42, 500.0]
        assert {row["source_type"] for row in rows} == {"BROKER_STATEMENT"}
        assert world.pending() == []

    def test_a_line_that_vanished_takes_its_row(self, world, corretora):
        of_broker, _of, account = corretora
        [fee, _kept] = statement(
            world, of_broker,
            (-0.42, "2026-10-21", "LIQ BOLSA - VISTA TX CCP B3", "03040000"),
            (-1.0, "2026-10-21", "LIQ BOLSA - VISTA TX EMOL B3", "03040000"),
        )
        world.fake.drop_tx(of_broker, fee)
        world.sync(world.made["items"]["btg"])
        assert [row["amount"] for row in world.transactions(account)] == [1.0]

    def test_it_is_not_income_nor_expense_of_the_month(self, world, corretora):
        of_broker, _of, _account = corretora
        statement(world, of_broker, (-500.0, "2026-10-21", "COMPRA - CDB BANCO C6", "04000000"))
        summary = world.call("get", "/api/home?month=2026-10").get("summary") or {}
        assert not summary.get("expense")

    def test_a_typed_operation_with_the_same_amount_is_linked(self, world, corretora, user):
        of_broker, _of, account = corretora
        typed = world.call("post", "/api/investments", json={
            "asset_class": "FIXED_INCOME", "ticker_or_name": "CDB TESTE", "quantity": 1, "average_price": 500.0,
            "metadata": {"purchase_date": "2026-10-21", "maturity_date": "2030-01-01", "fixed_income_type": "CDB",
                         "rate_type": "PRE", "annual_rate": 12},
        })
        [line] = statement(world, of_broker, (-500.0, "2026-10-21", "COMPRA - CDB BANCO C6", "04000000"))
        [row] = world.transactions(account)
        assert row["source_type"] == "INVESTMENT_TRANSACTION"
        assert typed and of_tx(user["id"], line)["target_id"] == row["id"]


class TestProceeds:
    def proceed(self, world, ticker, net, day, tax=0.0):
        world.call("post", "/api/investments", json={
            "asset_class": "STOCKS", "ticker_or_name": ticker, "quantity": 100, "average_price": 10.0,
            "metadata": {"purchase_date": "2026-01-05", "cash_account_id": None},
        })
        assets = world.call("get", "/api/assets")
        asset = next(row for row in assets if row["ticker"] == ticker)
        return world.call("post", "/api/investment-proceeds", json={
            "asset_id": asset["id"], "proceeds_type": "JCP", "gross_amount": net + tax, "tax_amount": tax,
            "payment_date": day, "record_date": "2026-10-10",
        })

    def test_the_bank_decides_the_amount_and_the_day(self, world, corretora):
        of_broker, _of, account = corretora
        self.proceed(world, "ITSA4", 5.52, "2026-10-20", tax=1.17)
        world.call("get", "/api/transactions")
        statement(world, of_broker, (7.36, "2026-10-21", "JUROS S/ CAPITAL - À VISTA s/ ITAUSA PN N1 - ITSA4", "03060000"))
        # Pago antes de a conta virar a da carteira: o dinheiro entra como linha.
        assert [(row["amount"], row["date"]) for row in world.transactions(account)] == [(7.36, "2026-10-21")]
        [proceed] = world.call("get", "/api/investment-proceeds")
        assert (proceed["gross_amount"], proceed["tax_amount"], proceed["net_amount"]) == (8.92, 1.56, 7.36)

    def test_another_ticker_is_not_this_proceed(self, world, corretora):
        of_broker, _of, account = corretora
        self.proceed(world, "ITSA4", 5.52, "2026-10-20")
        statement(world, of_broker, (5.52, "2026-10-21", "DIVIDENDOS - PETR4", "03060000"))
        assert [row["amount"] for row in world.transactions(account)] == [5.52]
        [proceed] = world.call("get", "/api/investment-proceeds")
        assert (proceed["payment_date"], proceed["sync_locked"]) == ("2026-10-20", 0)


class TestSettlement:
    def test_a_fixed_income_etf_settles_the_next_business_day(self):
        settlement = importlib.import_module("services.settlement")
        assert settlement.settlement_date("2026-10-29", "STOCKS", ticker="AUPO11") == "2026-10-30"
        assert settlement.settlement_date("2026-10-29", "STOCKS", ticker="BBDC3") == "2026-11-03"
        assert settlement.settlement_date("2026-10-20", "STOCKS", ticker="ABTC11") == "2026-10-22"


class TestProvisional:
    def setup(self, world, corretora, user, db_module):
        investments = importlib.import_module("services.open_finance_investments")
        pluggy_item = next(key for key, rows in world.fake.accounts.items() if any(row["id"] == corretora[0] for row in rows))
        position = world.fake.add_position(pluggy_item, "ITSA4", 30, value=12.61, day="2026-10-29")
        world.fake.add_operation(position, "BUY", 10, 13.0, "2026-10-20")
        world.sync(world.made["items"]["btg"])
        with db_module.get_db() as conn:
            filled = investments.fill_position_gaps(conn, user["id"], importlib.import_module("datetime").date(2026, 10, 30))
        assert filled == [{"ticker": "ITSA4", "quantity": 20.0, "unit_price": 12.61}]
        return position

    def rows(self, world):
        return [row for row in world.call("get", "/api/investments") if row["ticker_or_name"] == "ITSA4"]

    def test_the_position_is_matched_and_no_money_moves(self, world, corretora, user, db_module):
        self.setup(world, corretora, user, db_module)
        assert sum(row["quantity"] for row in self.rows(world)) == 30
        assert not [row for row in world.transactions(corretora[2]) if row["amount"] == round(20 * 12.61, 2)]
        assert world.overview()["investments"]["mismatched_count"] == 0

    def test_the_real_operation_replaces_it(self, world, corretora, user, db_module):
        position = self.setup(world, corretora, user, db_module)
        world.fake.add_operation(position, "BUY", 20, 12.5, "2026-10-30")
        world.sync(world.made["items"]["btg"])
        rows = self.rows(world)
        assert sorted((row["quantity"], row["average_price"]) for row in rows) == [(10, 13.0), (20, 12.5)]
