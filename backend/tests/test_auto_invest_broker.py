"""A aplicacao automatica e o caixa da corretora (dono, 2026-10-28).

O que estes testes protegem:
- a conta remunerada da BTG ("CONTA REMUNERADA - APLICACAO AUTOMATICA",
  "- RESGATE APLICACAO") e o "Automatic investment" da Pluggy (03010000) sao
  como o Rende Facil (046): COVERED, nunca lancamento nem conferencia;
- no caixa da corretora (BTG Investimentos -> Corretora), so a transferencia de
  verdade vira aporte/resgate; a compra/venda de renda fixa, o IR e o IOF que
  a Pluggy chama de "Same person transfer" e o LIQ BOLSA ficam com a carteira;
- o resto da conta segue o caminho de sempre.
"""

import importlib

import pytest

from open_finance_world import World, bank_tx, connected, fake_pluggy, open_finance_module  # noqa: F401
from test_open_finance_auto import auto_on, meupluggy, of_tx


@pytest.fixture()
def world(client, auth, fake_pluggy):
    return World(client, auth, fake_pluggy)


def bank_check(world, name):
    accounts = [account for item in world.overview()["items"] for account in item["accounts"]]
    return next(account for account in accounts if account["name"] == name)["check"]


class TestText:
    @pytest.mark.parametrize("text", [
        "CONTA REMUNERADA - APLICAÇÃO AUTOMÁTICA", "CONTA REMUNERADA - RESGATE APLICAÇÃO",
        "CONTA REMUNERADA - RESGATE REMUNERAÇÃO", "RENDE FACIL Rende Facil",
    ])
    def test_auto_investments(self, text):
        assert importlib.import_module("services.inbox").is_auto_invest(text)

    @pytest.mark.parametrize("text", [
        "ValorRendimentoSaldoRemunerado", "LIQ BOLSA - VISTA BRUTO", "APLICACAO CDB", "Pix",
    ])
    def test_anything_else(self, text):
        assert not importlib.import_module("services.inbox").is_auto_invest(text)

    @pytest.mark.parametrize("description, transfer", [
        ("RECEBIMENTO TRANSFERÊNCIA", True), ("ENVIO TRANSFERÊNCIA", True),
        ("TRANSFERÊNCIA A CRÉDITO VIA PIX", True), ("TED RECEBIDA", True),
        ("VENDA - CDB BANCO BTG PACTUAL S.A. - Venc: 2027-01-04", False),
        ("IRRF - CDB BANCO BTG PACTUAL S.A.", False), ("Compra de Tesouro Direto: NTN-B1", False),
        ("EMISSAO - LCI BANCO BTG PACTUAL S.A.", False),
    ])
    def test_a_broker_transfer_is_a_real_transfer(self, description, transfer):
        module = importlib.import_module("services.open_finance_inbox")
        row = {"movement": "SELF_TRANSFER", "description": description}
        assert module.is_broker_transfer(row) is transfer

    def test_a_broker_row_that_is_not_a_movement_is_never_a_transfer(self):
        module = importlib.import_module("services.open_finance_inbox")
        assert not module.is_broker_transfer({"movement": None, "description": "TRANSFERÊNCIA"})


class TestBankAccount:
    def test_conta_remunerada_and_automatic_investment_are_never_recorded(self, world, user):
        item_id, _p, made = connected(world, connector_name="BTG Pactual")
        auto_on(world)
        remunerada = world.fake.add_tx(made["bank"][0], bank_tx(
            -100, "2026-10-20", "CONTA REMUNERADA - APLICAÇÃO AUTOMÁTICA", category_id="03000000"))
        reserva = world.fake.add_tx(made["bank"][0], bank_tx(
            300, "2026-10-21", "TES RESERV VEND", category_id="03010000", category="Automatic investment"))
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-22", "PADARIA"))
        world.sync(item_id)

        rows = world.transactions(made["bank"][2])
        assert [row["description"] for row in rows] == ["PADARIA"]
        assert {of_tx(user["id"], remunerada)["role"], of_tx(user["id"], reserva)["role"]} == {"COVERED"}
        [item] = world.overview()["items"]
        assert item["accounts"][0]["check"]["bank_only"] == []

    def test_the_history_preview_counts_them_as_covered(self, world):
        item_id, _p, made = connected(world, connector_name="BTG Pactual")
        world.fake.add_tx(made["bank"][0], bank_tx(
            -100, "2026-10-20", "CONTA REMUNERADA - APLICAÇÃO AUTOMÁTICA", category_id="03000000"))
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-22", "PADARIA"))
        preview = world.call("post", "/api/open-finance/history/preview", json={"days": 30})
        [account] = preview["accounts"]
        assert (account["covered"], account["to_record"]) == (1, 1)


class TestCorretora:
    def test_fixed_income_and_liq_bolsa_stay_with_the_portfolio(self, world, user):
        made = meupluggy(world)
        auto_on(world)
        broker, _of, corretora = made["btg:0002/2-2X"]
        cdb = world.fake.add_tx(broker, bank_tx(
            2105.71, "2026-10-21", "VENDA - CDB BANCO BTG PACTUAL S.A. - Venc: 2027-01-04", category_id="04000000"))
        irrf = world.fake.add_tx(broker, bank_tx(
            -12.3, "2026-10-21", "IRRF - CDB BANCO BTG PACTUAL S.A.", category_id="04000000"))
        liq = world.fake.add_tx(broker, bank_tx(
            -97.23, "2026-10-22", "LIQ BOLSA - VISTA BRUTO - PREGÃO: 13/10/2026", category_id="03040000"))
        auto = world.fake.add_tx(broker, bank_tx(
            -100, "2026-10-23", "CONTA REMUNERADA - APLICAÇÃO AUTOMÁTICA", category_id="03000000"))
        world.sync(made["items"]["btg"])

        assert world.transactions(corretora) == []
        assert world.pending() == []
        assert {of_tx(user["id"], tx)["role"] for tx in (cdb, irrf, liq, auto)} == {"COVERED"}

    def test_a_transfer_from_the_bank_is_still_an_aporte(self, world):
        made = meupluggy(world)
        auto_on(world)
        btg, _of, btg_id = made["btg:0002/2-2"]
        broker, _of2, corretora = made["btg:0002/2-2X"]
        world.fake.add_tx(btg, bank_tx(-500, "2026-10-20", "Tef", category_id="04000000"))
        world.fake.add_tx(broker, bank_tx(500, "2026-10-20", "RECEBIMENTO TRANSFERÊNCIA", category_id="04000000"))
        world.sync(made["items"]["btg"])
        [row] = [row for row in world.transactions() if row["amount"] == 500]
        assert (row["type"], row["account_id"], row["transfer_account_id"]) == ("TRANSFER", btg_id, corretora)
