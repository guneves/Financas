"""Uma rodada da thread atualiza TUDO, sem o dono apertar nada (dono, 2026-10-30,
services/open_finance_refresh.py).

O que estes testes protegem:

- uma rodada (`refresh_all_users`), so com GET, leva de uma vez: lancamentos e
  saldo das contas, compras do cartao, os saldos da Pluggy da Conferencia, a
  conta em dolar (a Wise) e o BTG (operacoes, conferencia de posicoes, caixa);
- uma conexao que falha, ate com um erro inesperado, nao para as outras, e o
  erro fica nela;
- depois de um boot, o pull vencido volta logo; o que nao venceu nao repete: o
  piso de 6 h vale tambem no boot;
- `PATCH /items` continua recusado no cliente.
"""

import importlib
from datetime import datetime, timezone

import pytest

import pluggy_client
from open_finance_world import World, bank_tx, card_tx, connected, fake_pluggy, open_finance_module  # noqa: F401

SETTINGS = "/api/open-finance/settings"
# 27/10/2026, o dia do fake_pluggy; o primeiro pull grava o relogio de verdade,
# entao cada teste poe a ultima busca bem antes.
NOW = datetime(2026, 10, 27, 18, 0, tzinfo=timezone.utc).timestamp()
LONG_AGO = "2026-10-27T02:00:00Z"
RECENT = "2026-10-27T15:00:00Z"
PLUGGY_READS = {
    "get_item", "list_accounts", "list_transactions", "list_investments", "list_investment_transactions",
}


@pytest.fixture()
def world(client, auth, fake_pluggy):
    return World(client, auth, fake_pluggy)


@pytest.fixture()
def refresh():
    module = importlib.import_module("services.open_finance_refresh")
    module.reset_attempts()
    yield module
    module.reset_attempts()


def set_last_sync(stamp):
    db = importlib.import_module("db")
    with db.get_db() as conn:
        conn.execute("UPDATE open_finance_items SET last_sync_at = ?", (stamp,))


def wise_connection(world):
    fake = world.fake
    pluggy_item = fake.add_item("MeuPluggy")
    pluggy_account = fake.add_account(pluggy_item, "BANK", name="Wise USD", number="USD-1", balance=100.0)
    fake.accounts[pluggy_item][0]["currencyCode"] = "USD"
    body = world.connect(pluggy_item)
    wise = world.account("Wise", institution="Wise", currency="USD")
    of_account = next(entry for entry in body["items"] if entry["id"] == body["item_id"])["accounts"][0]
    world.map(of_account["id"], account_id=wise)
    return pluggy_account, pluggy_item, wise


def broker_connection(world):
    fake = world.fake
    corretora = world.account("BTG Corretora", type_="BROKERAGE")
    pluggy_item = fake.add_item("MeuPluggy")
    pluggy_account = fake.add_account(pluggy_item, "BANK", name="BTG Investimentos", number="9", balance=5000.0)
    body = world.connect(pluggy_item)
    of_account = next(entry for entry in body["items"] if entry["id"] == body["item_id"])["accounts"][0]
    world.map(of_account["id"], account_id=corretora)
    return pluggy_account, pluggy_item, corretora


def everything(world):
    """Itau (conta e cartao), Wise e BTG, com tudo ligado e nada novo ainda."""
    _item, itau_item, made = connected(world, connector_name="Itaú", card=True)
    wise = wise_connection(world)
    broker = broker_connection(world)
    world.call("patch", SETTINGS, json={"auto_record": True})
    set_last_sync(LONG_AGO)
    return itau_item, made, wise, broker


def account_row(world, account_id):
    return next(row for row in world.call("get", "/api/accounts") if row["id"] == account_id)


class TestOneTick:
    def test_it_updates_everything_with_no_button(self, world, refresh, user):
        itau_item, made, (wise_pluggy, wise_item, wise), (_broker_pluggy, broker_item, corretora) = everything(world)
        fake = world.fake
        bank_pluggy, _of, mine = made["bank"]
        card_pluggy, _of_card, card = made["card"]
        fake.add_tx(bank_pluggy, bank_tx(-45.9, "2026-10-26", "COMPRA PADARIA"))
        fake.add_tx(card_pluggy, card_tx(89.9, "2026-10-26", "SMART FIT", docs_sign=True))
        usd = bank_tx(-12.34, "2026-10-26", "Spotify")
        usd["currencyCode"] = "USD"
        fake.add_tx(wise_pluggy, usd)
        position = fake.add_position(broker_item, "PETR4", 100, value=38.5, day="2026-10-26")
        fake.add_operation(position, "BUY", 100, 38.5, "2026-10-20")
        for raw in fake.accounts[itau_item]:
            raw["balance"] = 954.1 if raw["type"] == "BANK" else -928.4
        fake.accounts[wise_item][0]["balance"] = 87.66
        fake.accounts[broker_item][0]["balance"] = 1150.0
        fake.calls.clear()

        results = refresh.refresh_all_users(NOW)

        assert all("error" not in entry for entry in results[user["id"]].values())
        assert len(results[user["id"]]) == 3
        # So leitura.
        assert {call[0] for call in fake.calls} <= PLUGGY_READS
        # A conta: o lancamento e o saldo, pela linha.
        assert [(row["amount"], row["needs_review"]) for row in world.transactions(mine)] == [(45.9, 1)]
        assert account_row(world, mine)["balance"] == -45.9
        # O cartao.
        assert [(row["amount"], row["description"]) for row in world.card_rows(card)] == [(89.9, "Smart Fit")]
        # A Wise, em dolar.
        [row] = world.call("get", f"/api/transactions?account_id={wise}")
        assert (row["amount"], row["account_id"]) == (12.34, wise)
        assert account_row(world, wise)["balance"] == -12.34
        # O BTG: a operacao, a conferencia de posicoes e o caixa.
        operations = [row for row in world.call("get", "/api/investments") if row.get("ticker_or_name")]
        assert [(row["ticker_or_name"], row["quantity"]) for row in operations] == [("PETR4", 100)]
        check = world.overview()["investments"]
        [position_check] = check["positions"]
        assert (position_check["pluggy_quantity"], position_check["matches"]) == (100, True)
        assert check["cash"]["pluggy_balance"] == 1150.0
        assert world.transactions(corretora), "o caixa da operacao passa pela Corretora"

    def test_the_conferencia_shows_the_new_pluggy_balance_of_every_account(self, world, refresh):
        itau_item, _made, (_wise_pluggy, wise_item, _wise), (_b, broker_item, _c) = everything(world)
        fake = world.fake
        for raw in fake.accounts[itau_item]:
            raw["balance"] = 11.0
        fake.accounts[wise_item][0]["balance"] = 22.0
        fake.accounts[broker_item][0]["balance"] = 33.0
        refresh.refresh_all_users(NOW)
        accounts = {
            account["number"]: account["pluggy_balance"]
            for item in world.overview()["items"] for account in item["accounts"]
        }
        assert accounts == {"0001/12345-0": 11.0, "9437": 11.0, "USD-1": 22.0, "9": 33.0}

    def test_a_second_tick_adds_nothing(self, world, refresh):
        _itau, made, _wise, _broker = everything(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-26"))
        refresh.refresh_all_users(NOW)
        refresh.reset_attempts()
        set_last_sync(LONG_AGO)
        refresh.refresh_all_users(NOW)
        assert len(world.transactions(made["bank"][2])) == 1


class TestAFailureStaysInItsItem:
    @pytest.mark.parametrize("error", [
        pluggy_client.PluggyError("fora do ar", status=500),
        RuntimeError("dado inesperado"),
    ], ids=["pluggy", "unexpected"])
    def test_the_others_still_update(self, world, refresh, user, monkeypatch, error):
        itau_item, made, (wise_pluggy, _wise_item, wise), _broker = everything(world)
        fake = world.fake
        usd = bank_tx(-12.34, "2026-10-26", "Spotify")
        usd["currencyCode"] = "USD"
        fake.add_tx(wise_pluggy, usd)
        fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-26"))
        real_get_item = fake.get_item

        def get_item(item_id):
            if item_id == itau_item:
                raise error
            return real_get_item(item_id)

        monkeypatch.setattr(fake, "get_item", get_item)
        results = refresh.refresh_all_users(NOW)[user["id"]]
        assert sum(1 for entry in results.values() if "error" in entry) == 1
        assert len(results) == 3
        assert world.transactions(made["bank"][2]) == []
        assert len(world.call("get", f"/api/transactions?account_id={wise}")) == 1
        [failed] = [item for item in world.overview()["items"] if item.get("last_sync_error")]
        assert str(error) in failed["last_sync_error"]


class TestAfterBoot:
    def test_an_overdue_pull_is_caught_up_on_the_first_tick(self, world, refresh, user):
        _itau, made, _wise, _broker = everything(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-26"))
        # O boot: a memoria de tentativas vem vazia; quem decide e last_sync_at.
        refresh.reset_attempts()
        assert user["id"] in refresh.due_user_ids(NOW)
        refresh.refresh_all_users(NOW)
        assert len(world.transactions(made["bank"][2])) == 1

    def test_the_first_tick_comes_soon(self, refresh):
        assert refresh.FIRST_DELAY_SECONDS <= 60

    def test_a_recent_pull_is_not_repeated(self, world, refresh, user):
        everything(world)
        set_last_sync(RECENT)
        refresh.reset_attempts()
        assert user["id"] not in refresh.due_user_ids(NOW)


def test_the_client_still_refuses_patch():
    client = pluggy_client.PluggyClient("id", "segredo", "https://exemplo.invalid", 1)
    with pytest.raises(pluggy_client.PluggyError):
        client.call("PATCH", "/items/1")
