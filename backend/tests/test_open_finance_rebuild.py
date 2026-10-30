"""Refazer tudo da Pluggy (services/open_finance_rebuild.py, dono 2026-10-30).

O que estes testes protegem:
- o ensaio nao grava; um backup que falha para tudo; outro usuario nunca e tocado;
- a Flash fica de pe, inteira, e a ponta do banco dela liga na transferencia dela;
  as outras contas sem Pluggy perdem as linhas e guardam o saldo;
- da carteira so sai o mes pedido, menos o bitcoin (ABTC11 nao e bitcoin); o caixa
  do que fica fica; a trava recusa o que nao voltaria;
- todo saldo mapeado termina no da Pluggy (a Corretora ate o dia do saldo, a Wise
  em dolar); pagamento de fatura baixa a fatura e nunca vira despesa; debito
  automatico e recorrencia nao gravam o que o banco nao mandou;
- nenhuma transferencia fica esperando em silencio.
"""

import importlib
import importlib.util
import json
import os
import subprocess
import sys

import pytest

from open_finance_world import World, bank_tx, card_tx, fake_pluggy, open_finance_module  # noqa: F401

SETTINGS = "/api/open-finance/settings"


@pytest.fixture()
def world(client, auth, fake_pluggy):
    made = World(client, auth, fake_pluggy)
    # A Flash existe em todo cenario: sem ela o --apply recusa.
    made.flash = made.account("Flash")
    made.flash_card = made.card("Cartão Flash", debit_account_id=made.flash, credit_enabled=False)
    return made


@pytest.fixture()
def rebuild(app_module, monkeypatch):
    module = importlib.import_module("services.open_finance_rebuild")
    monkeypatch.setattr(module.proceeds_sync, "sync_proceeds", lambda *_a, **_k: {"status": "ok", "message": None})
    return module


def rows_of(table, where="1=1", params=()):
    db = importlib.import_module("db")
    with db.get_db() as conn:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table} WHERE {where}", params).fetchall()]


def everything():
    db = importlib.import_module("db")
    with db.get_db() as conn:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()]
        return {table: [tuple(row) for row in conn.execute(f'SELECT * FROM "{table}" ORDER BY 1, 2').fetchall()]
                for table in tables}


def connect(world, name, kind="BANK", balance=0.0, currency="BRL", target=None, number=None):
    """Uma conexao com uma conta, ja mapeada. (item nosso, conta da Pluggy, conta do app/cartao)"""
    fake = world.fake
    pluggy_item = fake.add_item(name)
    pluggy_account = fake.add_account(pluggy_item, kind, name=name, number=number or name, balance=balance)
    fake.accounts[pluggy_item][-1]["currencyCode"] = currency
    body = world.connect(pluggy_item)
    item = next(entry for entry in body["items"] if entry["id"] == body["item_id"])
    of_id = item["accounts"][0]["id"]
    if kind == "BANK":
        target = target or world.account(name, currency=currency) if currency != "BRL" else target or world.account(name)
        world.map(of_id, account_id=target)
    else:
        target = target or world.card(name)
        world.map(of_id, card_id=target)
    return body["item_id"], pluggy_account, target


def add_card_account(world, pluggy_item, name, balance=0.0):
    fake = world.fake
    pluggy_account = fake.add_account(pluggy_item, "CREDIT", name=name, number=name, balance=balance)
    overview = world.sync(next(entry["id"] for entry in world.overview()["items"]
                               if any(a["name"] != name for a in entry["accounts"])))
    assert overview
    return pluggy_account


def typed(world, account, amount, date="2026-05-10", description="digitado", kind="EXPENSE"):
    return world.call("post", "/api/transactions", json={
        "account_id": account, "amount": amount, "date": date, "type": kind, "category": "Outros",
        "description": description,
    })["id"]


def transfer(world, origin, destination, amount, date="2026-10-20", description="Pix", **extra):
    return world.call("post", "/api/transfers", json={
        "account_id": origin, "transfer_account_id": destination, "amount": amount, "date": date,
        "description": description, **extra,
    })["id"]


def movement(world, asset_class, ticker, quantity, price, date, **metadata):
    key = "purchase_date" if quantity > 0 else "sale_date"
    body = {
        "asset_class": asset_class, "ticker_or_name": ticker, "quantity": quantity, "average_price": price,
        "metadata": {key: date, **metadata},
    }
    if quantity < 0:
        body["metadata"]["sale_price"] = price
    made = world.call("post", "/api/investments", json=body)
    return (made[0] if isinstance(made, list) else made)["id"]


def balance_of(world, account_id):
    """Direto do saldo do servico: a tela nao lista as arquivadas."""
    db = importlib.import_module("db")
    accounts = importlib.import_module("services.accounts")
    with db.get_db() as conn:
        owner = conn.execute("SELECT user_id FROM accounts WHERE id = ?", (account_id,)).fetchone()["user_id"]
        return round(next(row for row in accounts.account_balance_rows(conn, owner) if row["id"] == account_id)["balance"], 2)


def set_archived(account_id, stamp):
    with importlib.import_module("db").get_db() as conn:
        conn.execute("UPDATE accounts SET archived_at = ? WHERE id = ?", (stamp, account_id))


def history(world):
    world.call("post", "/api/open-finance/history/apply", json={"days": 60, "confirm": True})


def auto_on(world):
    world.call("patch", SETTINGS, json={"auto_record": True})


def run(rebuild, user_id, **options):
    options.setdefault("accept_balance_shift", True)
    lines = []
    code = rebuild.apply(user_id, rebuild.Options(**options), out=lines.append)
    return code, "\n".join(lines)


def preview(rebuild, user_id, **options):
    lines = []
    code = rebuild.dry_run(user_id, rebuild.Options(**options), out=lines.append)
    return code, "\n".join(lines)


class Bank:
    """BB (com cartao em outra conexao), a Flash e o Inter arquivado."""

    def __init__(self, world):
        self.world = world
        self.item, self.pluggy, self.bb = connect(world, "BB", balance=1000.0)
        self.flash = world.flash
        typed(world, self.flash, 50.0, "2026-10-15", "almoco na flash")
        self.inter = world.account("Inter")
        typed(world, self.inter, 300.0, "2026-05-02", "salario inter", "INCOME")
        set_archived(self.inter, "2026-10-01")
        auto_on_ready(world, self.item)


def auto_on_ready(world, item):
    world.sync(item)
    auto_on(world)


@pytest.fixture()
def bank(world):
    return Bank(world)


class TestSafety:
    def test_the_dry_run_writes_nothing(self, world, bank, rebuild, user):
        typed(world, bank.bb, 10.0)
        before = everything()
        code, text = preview(rebuild, user["id"])
        assert code == rebuild.EXIT_OK
        assert before == everything()
        assert "ENSAIO" in text and "transactions" in text
        assert all(call[0] != "update_item" for call in world.fake.calls)

    def test_a_failed_backup_stops_everything(self, world, bank, rebuild, user, monkeypatch):
        typed(world, bank.bb, 10.0)
        before = everything()

        def boom():
            raise OSError("disco cheio")

        monkeypatch.setattr(rebuild, "create_database_backup", boom)
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_REFUSED and "disco cheio" in text
        assert before == everything()

    def test_a_broken_backup_stops_everything(self, world, bank, rebuild, user, monkeypatch, tmp_path):
        typed(world, bank.bb, 10.0)
        before = everything()
        path = tmp_path / "finance-ruim.db"
        path.write_bytes(b"isto nao e um banco")
        monkeypatch.setattr(rebuild, "create_database_backup", lambda: {"database_path": str(path)})
        code, _text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_REFUSED
        assert before == everything()

    def test_the_backup_is_kept_apart_and_named(self, world, bank, rebuild, user):
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_OK, text
        assert "finance-before-rebuild-" in text

    def test_only_the_exact_email(self, rebuild, user):
        assert rebuild.find_user(user["email"]) == user["id"]
        with pytest.raises(rebuild.RebuildRefused):
            rebuild.find_user(user["email"].split("@")[0])

    def test_the_other_user_is_never_touched(self, client, world, bank, rebuild, user, other_user):
        headers = {"Authorization": f"Bearer {other_user['token']}"}
        account = client.post("/api/accounts", json={"name": "Dele", "type": "CHECKING"}, headers=headers).get_json()["id"]
        client.post("/api/transactions", headers=headers, json={
            "account_id": account, "amount": 5, "date": "2026-10-01", "type": "EXPENSE", "category": "Outros",
            "description": "dele",
        })
        typed(world, bank.bb, 10.0)
        before = rows_of("transactions", "user_id = ?", (other_user["id"],))
        accounts = rows_of("accounts", "user_id = ?", (other_user["id"],))
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_OK, text
        assert before == rows_of("transactions", "user_id = ?", (other_user["id"],)) != []
        assert accounts == rows_of("accounts", "user_id = ?", (other_user["id"],))


class TestWipe:
    def test_typed_rows_go_and_the_bank_balance_is_pluggys(self, world, bank, rebuild, user):
        typed(world, bank.bb, 123.0)
        world.fake.add_tx(bank.pluggy, bank_tx(-40.0, "2026-10-20", "COMPRA PADARIA DO ZE"))
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_OK, text
        [row] = world.transactions(bank.bb)
        assert (row["amount"], row["description"], row["category"]) == (40.0, "Padaria do Ze", "Alimentação")
        assert balance_of(world, bank.bb) == 1000.0

    def test_flash_stands_with_its_rows_and_balance(self, world, bank, rebuild, user):
        before = rows_of("transactions", "account_id = ?", (bank.flash,))
        account = rows_of("accounts", "id = ?", (bank.flash,))[0]
        assert before
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_OK, text
        assert rows_of("transactions", "account_id = ?", (bank.flash,)) == before
        assert rows_of("accounts", "id = ?", (bank.flash,))[0]["initial_balance"] == account["initial_balance"]

    def test_inter_loses_its_rows_and_keeps_its_balance(self, world, bank, rebuild, user):
        balance = balance_of(world, bank.inter)
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_OK, text
        assert rows_of("transactions", "account_id = ?", (bank.inter,)) == []
        assert balance_of(world, bank.inter) == balance == 300.0

    def test_the_pluggy_side_of_a_flash_transfer_links_to_it(self, world, bank, rebuild, user):
        kept = transfer(world, bank.flash, bank.bb, 280.0, "2026-10-26", "Flash -> BB")
        flash_balance = balance_of(world, bank.flash)
        tx_id = world.fake.add_tx(bank.pluggy, bank_tx(280.0, "2026-10-26", "PIX RECEBIDO", payment_method="PIX"))
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_OK, text
        assert world.transactions(bank.bb) == [] and kept in [row["id"] for row in world.transactions(bank.flash)]
        assert rows_of("open_finance_transactions", "pluggy_transaction_id = ?", (tx_id,))[0]["target_id"] == kept
        assert balance_of(world, bank.flash) == flash_balance
        assert balance_of(world, bank.bb) == 1000.0

    def receipt(self, world, bank, user, on_disk=True):
        row_id = typed(world, bank.bb, 10.0)
        db = importlib.import_module("db")
        attachments = importlib.import_module("services.attachments")
        if on_disk:
            path = attachments.attachment_path(user["id"], "guardado.png")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(b"png")
        with db.get_db() as conn:
            conn.execute(
                """
                INSERT INTO transaction_attachments
                (id, user_id, transaction_id, original_name, stored_name, content_type, size_bytes, sha256)
                VALUES ('a1', ?, ?, 'r.png', 'guardado.png', 'image/png', 1, 'x')
                """,
                (user["id"], row_id),
            )

    def test_a_receipt_of_a_deleted_row_is_removed_after_the_commit(self, world, bank, rebuild, user, monkeypatch):
        self.receipt(world, bank, user)
        removed = []
        monkeypatch.setattr(rebuild, "remove_attachment_files", lambda user_id, names: removed.extend(names))
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_OK, text
        assert removed == ["guardado.png"]
        assert rows_of("transaction_attachments", "id = 'a1'") == []
        assert "Comprovantes copiados: 1" in text
        folder = text.split("Comprovantes copiados: 1 em ")[1].split("\n")[0]
        assert os.path.isfile(os.path.join(folder, "guardado.png"))
        assert "receipts-before-rebuild-" in folder

    def test_a_receipt_that_cannot_be_copied_stops_the_wipe(self, world, bank, rebuild, user):
        self.receipt(world, bank, user, on_disk=False)
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_REFUSED and "Comprovante" in text
        assert rows_of("transaction_attachments", "id = 'a1'")
        assert rows_of("transactions", "user_id = ? AND amount = 10", (user["id"],))

    def test_doing_it_twice_changes_nothing(self, world, bank, rebuild, user):
        world.fake.add_tx(bank.pluggy, bank_tx(-40.0, "2026-10-20", "PADARIA"))
        assert run(rebuild, user["id"])[0] == rebuild.EXIT_OK
        first = sorted((row["date"], row["amount"]) for row in world.transactions(bank.bb))
        assert run(rebuild, user["id"])[0] == rebuild.EXIT_OK
        assert first == sorted((row["date"], row["amount"]) for row in world.transactions(bank.bb))
        assert balance_of(world, bank.bb) == 1000.0

    def test_a_failed_pull_keeps_the_saved_state_and_resumes(self, world, bank, rebuild, user, monkeypatch):
        import pluggy_client

        balance = balance_of(world, bank.inter)
        original = world.fake.list_transactions

        def refused(*_a, **_k):
            raise pluggy_client.PluggyError("fora do ar", status=503)

        monkeypatch.setattr(world.fake, "list_transactions", refused)
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_FAILED and "--from-step" in text
        assert rows_of("user_settings", "setting_key = ?", (rebuild.STATE_SETTING,))
        monkeypatch.setattr(world.fake, "list_transactions", original)
        code, text = run(rebuild, user["id"], from_step="pull")
        assert code == rebuild.EXIT_OK, text
        assert balance_of(world, bank.inter) == balance
        assert rows_of("user_settings", "setting_key = ?", (rebuild.STATE_SETTING,)) == []


def broker_world(world, balance=5000.0):
    corretora = world.account("BTG Corretora", type_="BROKERAGE")
    item, pluggy_account, _ = connect(world, "BTG Investimentos", balance=balance, target=corretora)
    pluggy_item = next(key for key, accounts in world.fake.accounts.items()
                       if any(account["id"] == pluggy_account for account in accounts))
    return item, pluggy_item, corretora


class TestInvestments:
    def setup_portfolio(self, world):
        item, pluggy_item, corretora = broker_world(world)
        auto_on_ready(world, item)
        self.sept = movement(world, "STOCKS", "PETR4", 100, 30.0, "2026-09-10")
        self.btc = movement(world, "OTHER", "BTC", 0.01, 500000.0, "2026-10-20")
        self.october = movement(world, "STOCKS", "ITUB4", 10, 20.0, "2026-10-05")
        fake = world.fake
        self.petr = fake.add_position(pluggy_item, "PETR4", 100, value=30.0)
        fake.add_operation(self.petr, "BUY", 100, 30.0, "2026-09-10")
        self.abtc = fake.add_position(pluggy_item, "ITUB4", 10, value=20.0)
        fake.add_operation(self.abtc, "BUY", 10, 20.0, "2026-10-05")
        world.sync(item)
        return item, pluggy_item, corretora

    def test_bitcoin_and_september_stay_and_october_comes_back_from_pluggy(self, world, rebuild, user):
        self.setup_portfolio(world)
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_OK, text
        kept = {row["id"]: row for row in rows_of("investment_transactions", "user_id = ?", (user["id"],))}
        assert self.btc in kept and self.sept in kept
        assert self.october not in kept
        tickers = {row["ticker"] for row in rows_of(
            "assets a JOIN investment_transactions t ON t.asset_id = a.id", "a.user_id = ?", (user["id"],),
        )}
        assert {"BTC", "PETR4", "ITUB4"} <= tickers

    def test_abtc11_is_not_bitcoin(self, rebuild):
        assert rebuild.is_bitcoin({"asset_class": "OTHER", "ticker": "BTC"})
        assert not rebuild.is_bitcoin({"asset_class": "STOCKS", "ticker": "ABTC11"})
        assert not rebuild.is_bitcoin({"asset_class": "OTHER", "ticker": "ABTC11"})
        assert not rebuild.is_bitcoin({"asset_class": "REIT", "ticker": "BTCI11"})

    def test_cash_of_what_stays_stays(self, world, rebuild, user):
        _item, _pluggy, corretora = self.setup_portfolio(world)
        cash = rows_of("transactions", "source_type = 'INVESTMENT_TRANSACTION' AND source_id = ?", (self.sept,))
        assert cash
        assert run(rebuild, user["id"])[0] == rebuild.EXIT_OK
        assert rows_of("transactions", "id = ?", (cash[0]["id"],))
        assert rows_of("transactions", "source_id = ?", (self.october,)) == []

    def test_the_corretora_ends_on_pluggys_cash_with_settlement_in_transit(self, world, rebuild, user):
        _item, pluggy_item, corretora = self.setup_portfolio(world)
        # Pregao 26/10, liquida 28/10, depois de hoje (27/10): em transito.
        position = world.fake.add_position(pluggy_item, "VALE3", 10, value=50.0, day="2026-10-26")
        world.fake.add_operation(position, "BUY", 10, 50.0, "2026-10-26")
        world.fake.items[pluggy_item]["lastUpdatedAt"] = "2026-10-27T12:00:00.000Z"
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_OK, text
        with importlib.import_module("db").get_db() as conn:
            settled = rebuild.settled_balance(conn, user["id"], corretora, "2026-10-27")
        assert settled == 5000.0

    def test_dismissed_and_held_october_operations_are_reevaluated(self, world, rebuild, user):
        item, pluggy_item, _ = self.setup_portfolio(world)
        db = importlib.import_module("db")
        with db.get_db() as conn:
            conn.execute(
                "UPDATE open_finance_investment_operations SET state = 'DISMISSED', investment_id = NULL "
                "WHERE user_id = ? AND code = 'ITUB4'", (user["id"],),
            )
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_OK, text
        [row] = rows_of("open_finance_investment_operations", "user_id = ? AND code = 'ITUB4'", (user["id"],))
        assert row["state"] == "RECORDED"

    def test_the_gate_refuses_an_october_trade_that_would_not_come_back(self, world, rebuild, user):
        self.setup_portfolio(world)
        before = len(rows_of("investment_transactions", "user_id = ?", (user["id"],)))
        world.fake.investment_transactions[self.abtc].clear()
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_REFUSED
        assert "TRAVA DA CARTEIRA" in text and "ITUB4" in text
        assert len(rows_of("investment_transactions", "user_id = ?", (user["id"],))) == before

    def test_the_gate_can_be_accepted_and_then_fails_loudly(self, world, rebuild, user):
        self.setup_portfolio(world)
        world.fake.investment_transactions[self.abtc].clear()
        code, text = run(rebuild, user["id"], accept_investment_gaps=True)
        assert code == rebuild.EXIT_FAILED
        assert "FALHOU" in text and "ITUB4" in text

    def test_the_gate_refuses_an_unknown_equity(self, world, rebuild, user):
        _item, pluggy_item, _ = self.setup_portfolio(world)
        position = world.fake.add_position(pluggy_item, "ZZZZ9", 5, value=10.0)
        world.fake.add_operation(position, "BUY", 5, 10.0, "2026-10-06")
        gate = rebuild.investment_gate(user["id"], rebuild.Options())
        assert any("ZZZZ9" in line for line in gate["gaps"])

    def test_interest_does_not_block_and_is_printed(self, world, rebuild, user):
        _item, pluggy_item, _ = self.setup_portfolio(world)
        world.fake.add_operation(self.petr, "INTEREST", 0, 0, "2026-10-08")
        gate = rebuild.investment_gate(user["id"], rebuild.Options())
        assert gate["gaps"] == []
        assert any("INTEREST" in line for line in gate["other_held"])

    def test_the_dry_run_lists_each_movement_and_ticker(self, world, rebuild, user):
        self.setup_portfolio(world)
        _code, text = preview(rebuild, user["id"])
        assert "BTC BUY 0.01: FICA (bitcoin)" in text
        assert "ITUB4 BUY 10.0: APAGA" in text
        assert "PETR4: app 100.0 x Pluggy 100" in text

    def test_a_movement_before_a_corporate_action_stays(self, world, rebuild, user):
        self.setup_portfolio(world)
        asset = rows_of("assets", "user_id = ? AND ticker = 'ITUB4'", (user["id"],))[0]
        world.call("post", "/api/corporate-actions", json={
            "asset_id": asset["id"], "action_type": "SPLIT", "ex_date": "2026-10-10", "ratio_from": 1, "ratio_to": 2,
        })
        with importlib.import_module("db").get_db() as conn:
            listed = rebuild.classify_movements(conn, user["id"], "2026-10")
        [entry] = [item for item in listed if item["ticker"] == "ITUB4"]
        assert entry["action"] == "keep" and "evento corporativo" in entry["reason"]


class TestSummedTwins:
    def test_an_operation_links_to_the_typed_trades_that_sum_to_it(self, world, user):
        item, pluggy_item, _ = broker_world(world)
        auto_on_ready(world, item)
        first = movement(world, "REIT", "HGLG11", 10, 9.0, "2026-10-02")
        second = movement(world, "REIT", "HGLG11", 16, 9.0, "2026-10-02")
        position = world.fake.add_position(pluggy_item, "HGLG11", 26, value=9.0)
        world.fake.add_operation(position, "BUY", 26, 9.0, "2026-10-02")
        world.sync(item)
        operations = rows_of("open_finance_investment_operations", "user_id = ?", (user["id"],))
        assert {row["investment_id"] for row in operations} == {first, second}
        assert {row["state"] for row in operations} == {"LINKED"}
        assert sum(row["quantity"] for row in operations) == 26
        assert len(rows_of("investment_transactions", "user_id = ?", (user["id"],))) == 2
        world.sync(item)
        assert len(rows_of("investment_transactions", "user_id = ?", (user["id"],))) == 2

    def test_a_sale_of_opposite_sign_never_adds_up(self, world, user):
        item, pluggy_item, _ = broker_world(world)
        auto_on_ready(world, item)
        movement(world, "REIT", "HGLG11", 12, 9.0, "2026-10-01")
        movement(world, "REIT", "HGLG11", -3, 9.0, "2026-10-02")
        movement(world, "REIT", "HGLG11", -9, 9.0, "2026-10-02")
        position = world.fake.add_position(pluggy_item, "HGLG11", 0, value=9.0)
        world.fake.add_operation(position, "SELL", 12, 9.0, "2026-10-02")
        world.sync(item)
        [main] = [row for row in rows_of("open_finance_investment_operations", "user_id = ?", (user["id"],))
                  if row["quantity"] == 12]
        assert main["state"] == "LINKED"
        assert len(rows_of("investment_transactions", "user_id = ?", (user["id"],))) == 3


class TestInvoices:
    def card_world(self, world, due=10, closing=3):
        item, pluggy_account, bb = connect(world, "BB", balance=500.0)
        pluggy_item = next(key for key, accounts in world.fake.accounts.items()
                           if any(account["id"] == pluggy_account for account in accounts))
        card = world.card("Ourocard", due_day=due, closing_day=closing)
        card_pluggy = world.fake.add_account(pluggy_item, "CREDIT", name="Ourocard", number="77", balance=-30.0)
        world.sync(item)
        entry = next(row for row in world.overview()["items"][0]["accounts"] if row["name"] == "Ourocard")
        world.map(entry["id"], card_id=card)
        auto_on(world)
        return item, pluggy_account, bb, card, card_pluggy

    def test_a_bank_payment_pays_the_invoice_and_is_no_despesa(self, world, user):
        item, pluggy_account, bb, card, card_pluggy = self.card_world(world)
        world.fake.add_tx(card_pluggy, card_tx(100.0, "2026-09-20", "LOJA", docs_sign=True))
        tx_id = world.fake.add_tx(
            pluggy_account, bank_tx(-100.0, "2026-10-10", "PAGAMENTO FATURA", category_id="05100000"),
        )
        history(world)
        [row] = rows_of("cc_expenses", "card_id = ?", (card,))
        [payment] = world.transactions(bb)
        assert row["status"] == "PAID" and row["paid_by"] == payment["id"]
        assert (payment["source_type"], payment["amount"]) == ("CC_INVOICE_PAYMENT", 100.0)
        assert tx_id in payment["source_id"]
        world.sync(item)
        assert len(world.transactions(bb)) == 1

    def test_a_different_amount_pays_the_invoice_with_the_banks_amount(self, world, user):
        item, pluggy_account, bb, card, card_pluggy = self.card_world(world)
        world.fake.add_tx(card_pluggy, card_tx(100.0, "2026-09-20", "LOJA", docs_sign=True))
        world.fake.add_tx(pluggy_account, bank_tx(-105.0, "2026-10-10", "PAGAMENTO FATURA", category_id="05100000"))
        history(world)
        assert rows_of("cc_expenses", "card_id = ?", (card,))[0]["status"] == "PAID"
        assert world.transactions(bb)[0]["amount"] == 105.0

    def test_past_invoices_do_not_stay_open_after_the_rebuild(self, world, rebuild, user):
        item, pluggy_account, bb, card, card_pluggy = self.card_world(world)
        world.fake.add_tx(card_pluggy, card_tx(30.0, "2026-10-20", "LOJA NOVA", docs_sign=True))
        world.fake.add_tx(card_pluggy, card_tx(55.0, "2026-05-20", "LOJA VELHA", docs_sign=True))
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_OK, text
        statuses = {row["description"]: row["status"] for row in rows_of("cc_expenses", "card_id = ?", (card,))}
        assert statuses == {"Loja Velha": "PAID", "Loja Nova": "OPEN"}
        assert balance_of(world, bb) == 500.0

    def test_autopay_never_debits_a_connected_card(self, world, user, invoices_module):
        item, _p, bb, card, card_pluggy = self.card_world(world)
        world.call("patch", f"/api/credit-cards/{card}", json={"autopay_account_id": bb, "autopay_start_date": "2026-01-01"})
        world.fake.add_tx(card_pluggy, card_tx(100.0, "2026-09-20", "LOJA", docs_sign=True))
        history(world)
        with importlib.import_module("db").get_db() as conn:
            assert invoices_module.apply_due_autopay(conn, user["id"]) == []
        assert world.transactions(bb) == []

    def test_a_card_that_does_not_add_up_is_named(self, world, rebuild, user):
        item, _p, bb, card, card_pluggy = self.card_world(world)
        world.fake.add_tx(card_pluggy, card_tx(10.0, "2026-10-20", "LOJA", docs_sign=True))
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_FAILED
        assert "Ourocard" in text and "diferenca" in text

    def test_a_purchase_older_than_the_history_comes_back_with_its_installments(self, world, rebuild, user):
        item, pluggy_account, bb, card, card_pluggy = self.card_world(world)
        world.fake.accounts[next(iter(world.fake.accounts))][-1]["balance"] = -100.0
        for number in (3, 4):
            world.fake.add_tx(card_pluggy, card_tx(
                50.0, f"2026-1{number - 3}-05", "NETSHOES 0{}/04".format(number), installment=number, total_installments=4,
                purchase_date="2026-07-20", docs_sign=True,
            ))
        code, text = run(rebuild, user["id"])
        assert "compras de antes do historico 1" in text
        rows = rows_of("cc_expenses", "card_id = ?", (card,))
        assert len(rows) == 4 and sum(row["amount"] for row in rows) == 200.0
        assert {row["purchase_date"] for row in rows} == {"2026-07-20"}

    def test_a_purchase_with_its_first_installment_is_not_adopted(self, world, rebuild, user):
        item, _p, bb, card, card_pluggy = self.card_world(world)
        for number in (1, 2):
            world.fake.add_tx(card_pluggy, card_tx(
                50.0, f"2026-1{number - 1}-05", "LOJA", installment=number, total_installments=2,
                purchase_date="2026-10-01", docs_sign=True,
            ))
        run(rebuild, user["id"], allow_pending=True)
        assert len(rows_of("cc_expenses", "card_id = ?", (card,))) == 2


class TestRecurrence:
    def test_run_writes_nothing_on_a_connected_account(self, world, bank, user):
        created = world.call("post", "/api/recurring", json={
            "account_id": bank.bb, "description": "aluguel", "amount": 100, "type": "EXPENSE", "category": "Outros",
            "frequency": "MONTHLY", "start_date": "2026-09-01",
        })
        result = world.call("post", "/api/recurring/run")
        assert result["created"] == [] or result.get("created_count", 0) == 0
        assert world.transactions(bank.bb) == []
        row = rows_of("recurring_transactions", "id = ?", (created["id"],))[0]
        assert row["next_run_date"] > "2026-10-27"


class TestOneSided:
    def test_the_transfer_to_wise_keeps_its_dollars(self, world, rebuild, user):
        item, btg_pluggy, btg = connect(world, "BTG Banking", balance=1880.0)
        wise_item, wise_pluggy, wise = connect(world, "Wise", balance=110.26, currency="USD")
        world.sync(item)
        auto_on(world)
        kept = transfer(world, btg, wise, 559.43, "2026-10-20", "Pix para Wise", transfer_amount=110.24)
        assert kept
        world.fake.add_tx(btg_pluggy, bank_tx(-559.43, "2026-10-20", "PIX ENVIADO WISE BRASIL", payment_method="PIX",
                                              counterparty="WISE BRASIL CORRETORA DE CAMBIO"))
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_OK, text
        [row] = world.transactions(btg)
        assert (row["type"], row["amount"], row["transfer_amount"]) == ("TRANSFER", 559.43, 110.24)
        assert row["transfer_account_id"] == wise
        assert balance_of(world, wise) == 110.26 and balance_of(world, btg) == 1880.0

    def test_a_transfer_to_an_archived_account_comes_back_whole(self, world, bank, rebuild, user):
        set_archived(bank.inter, None)
        transfer(world, bank.bb, bank.inter, 70.0, "2026-06-01", "para o inter")
        set_archived(bank.inter, "2026-10-01")
        world.fake.add_tx(bank.pluggy, bank_tx(-70.0, "2026-06-01", "PIX ENVIADO", payment_method="PIX"))
        balance = balance_of(world, bank.inter)
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_OK, text
        [row] = world.transactions(bank.bb)
        assert row["type"] == "TRANSFER" and row["transfer_account_id"] == bank.inter
        assert rows_of("accounts", "id = ?", (bank.inter,))[0]["archived_at"] == "2026-10-01"
        assert balance_of(world, bank.inter) == balance

    def test_an_own_transfer_nothing_explains_becomes_a_despesa(self, world, bank, rebuild, user):
        world.fake.add_tx(bank.pluggy, bank_tx(-90.0, "2026-06-01", "TRANSF MESMA TITULARIDADE", category_id="04000000"))
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_OK, text
        [row] = world.transactions(bank.bb)
        assert (row["type"], row["amount"]) == ("EXPENSE", 90.0)
        assert balance_of(world, bank.bb) == 1000.0

    def test_a_recent_one_sided_transfer_fails_unless_allowed(self, world, bank, rebuild, user):
        world.fake.add_tx(bank.pluggy, bank_tx(-90.0, "2026-10-27", "TRANSF MESMA TITULARIDADE", category_id="04000000"))
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_FAILED and "pendente" in text
        code, text = run(rebuild, user["id"], allow_pending=True)
        assert code == rebuild.EXIT_OK, text
        # O saldo espera a ponta: quando ela gravar, o app bate com o banco.
        assert balance_of(world, bank.bb) == 1090.0


class TestRegister:
    def test_wise_is_registered_mapped_and_the_rest_ignored(self, world, rebuild, user):
        item, _p, _bb = connect(world, "BB", balance=0.0)
        auto_on_ready(world, item)
        wise = world.account("Wise", currency="USD")
        fake = world.fake
        pluggy_item = fake.add_item("MeuPluggy")
        usd = fake.add_account(pluggy_item, "BANK", name="USD", number="1", balance=110.26)
        fake.accounts[pluggy_item][-1]["currencyCode"] = "USD"
        fake.add_account(pluggy_item, "BANK", name="BRL", number="2", balance=0.0)
        fake.add_account(pluggy_item, "BANK", name="EUR", number="3", balance=0.0)
        fake.accounts[pluggy_item][-1]["currencyCode"] = "EUR"
        fake.add_tx(usd, {**bank_tx(50.0, "2026-07-26", "JUROS"), "currencyCode": "USD"})
        options = dict(register_item=pluggy_item, maps={"USD": wise}, ignores=("BRL", "EUR"))
        _code, text = preview(rebuild, user["id"], **options)
        assert "[ainda nao gravada no app]" in text
        code, text = run(rebuild, user["id"], **options)
        assert code == rebuild.EXIT_OK, text
        assert balance_of(world, wise) == 110.26
        assert "(USD)" in text
        ignored = rows_of("open_finance_accounts", "name IN ('BRL', 'EUR') AND ignored_at IS NOT NULL")
        assert len(ignored) == 2


class TestReview:
    def test_only_recent_rows_without_a_sure_category_wait(self, world, bank, rebuild, user):
        fake = world.fake
        fake.add_tx(bank.pluggy, bank_tx(-10.0, "2026-05-05", "COISA ANTIGA"))
        fake.add_tx(bank.pluggy, bank_tx(-11.0, "2026-10-20", "IFOOD"))
        fake.add_tx(bank.pluggy, bank_tx(-12.0, "2026-10-21", "COISA RECENTE"))
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_OK, text
        flags = {row["amount"]: row["needs_review"] for row in world.transactions(bank.bb)}
        assert flags == {10.0: 0, 11.0: 0, 12.0: 1}

    def test_the_cutoff_can_be_chosen(self, world, bank, rebuild, user):
        world.fake.add_tx(bank.pluggy, bank_tx(-12.0, "2026-10-21", "COISA RECENTE"))
        assert run(rebuild, user["id"], reviewed_before="2026-10-25")[0] == rebuild.EXIT_OK
        assert world.transactions(bank.bb)[0]["needs_review"] == 0


class TestEndCheck:
    def test_a_row_from_nowhere_fails_the_end_check(self, world, bank, rebuild, user):
        assert run(rebuild, user["id"])[0] == rebuild.EXIT_OK
        typed(world, bank.bb, 3.0)
        code, text = run(rebuild, user["id"], from_step="balances")
        assert code == rebuild.EXIT_FAILED
        assert "nao vieram da Pluggy" in text

    def test_the_report_of_categories(self, world, bank, rebuild, user):
        world.fake.add_tx(bank.pluggy, bank_tx(-12.0, "2026-10-21", "ZZZ DESCONHECIDA"))
        world.fake.add_tx(bank.pluggy, bank_tx(-13.0, "2026-10-21", "IFOOD"))
        assert run(rebuild, user["id"])[0] == rebuild.EXIT_OK
        report = rebuild.category_report(user["id"])
        assert dict(report["categories"])["Alimentação"] == 1
        assert ("Zzz Desconhecida", 1) in report["uncategorized"]


class TestReview2:
    """Achados da revisao de 2026-10-30."""

    def two_banks(self, world):
        first_item, first, first_account = connect(world, "BB", balance=-90.0)
        _second_item, second, second_account = connect(world, "Itau", balance=500.0)
        auto_on_ready(world, first_item)
        return first, first_account, second, second_account

    def test_a_failed_connection_records_nothing(self, world, rebuild, user, monkeypatch):
        import pluggy_client

        first, first_account, second, second_account = self.two_banks(world)
        transfer(world, first_account, second_account, 90.0, "2026-06-01", "para o itau")
        world.fake.add_tx(first, bank_tx(-90.0, "2026-06-01", "PIX ENVIADO", payment_method="PIX"))
        original = world.fake.list_transactions

        def half(account_id, date_from, date_to=None):
            if account_id == second:
                raise pluggy_client.PluggyError("fora do ar", status=503)
            return original(account_id, date_from, date_to)

        monkeypatch.setattr(world.fake, "list_transactions", half)
        code, text = run(rebuild, user["id"], accept_investment_gaps=True)
        assert code == rebuild.EXIT_FAILED and "nada foi gravado" in text
        assert rows_of("transactions", "account_id = ?", (first_account,)) == []  # world.transactions() grava (record_due)
        monkeypatch.setattr(world.fake, "list_transactions", original)
        code, text = run(rebuild, user["id"], from_step="pull")
        assert code == rebuild.EXIT_OK, text
        [row] = world.transactions(first_account)
        assert row["type"] == "TRANSFER"

    def test_pull_is_refused_after_recording_and_wipe_clears_it(self, world, bank, rebuild, user):
        world.fake.add_tx(bank.pluggy, bank_tx(-90.0, "2026-10-27", "TRANSF MESMA TITULARIDADE", category_id="04000000"))
        assert run(rebuild, user["id"])[0] == rebuild.EXIT_FAILED
        code, text = run(rebuild, user["id"], from_step="pull")
        assert code == rebuild.EXIT_REFUSED and "duplicaria" in text
        assert run(rebuild, user["id"], from_step="wipe", allow_pending=True)[0] == rebuild.EXIT_OK

    def test_a_flash_in_another_case_or_in_the_bank_field_is_found(self, world, rebuild, user):
        with importlib.import_module("db").get_db() as conn:
            conn.execute("UPDATE accounts SET name = 'VR', institution = 'FLASH' WHERE id = ?", (world.flash,))
            assert rebuild.kept_account_ids(conn, user["id"], ("flash",)) == {world.flash}

    def test_no_flash_account_refuses_before_any_write(self, world, bank, rebuild, user):
        with importlib.import_module("db").get_db() as conn:
            conn.execute("UPDATE accounts SET name = 'Outra' WHERE id = ?", (world.flash,))
        before = everything()
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_REFUSED and "Conta mantida" in text
        assert before == everything()
        assert "--apply RECUSARIA" in preview(rebuild, user["id"])[1]

    def test_no_flash_card_refuses(self, world, bank, rebuild, user):
        with importlib.import_module("db").get_db() as conn:
            conn.execute("UPDATE credit_cards SET name = 'Outro', debit_account_id = NULL WHERE id = ?", (world.flash_card,))
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_REFUSED and "Cartao mantido" in text

    def test_auto_record_off_refuses_before_the_wipe_and_in_the_dry_run(self, world, bank, rebuild, user):
        world.call("patch", SETTINGS, json={"auto_record": False})
        typed(world, bank.bb, 10.0)
        before = everything()
        code, text = run(rebuild, user["id"])
        assert code == rebuild.EXIT_REFUSED and "Gravar sozinho" in text
        assert before == everything()
        assert "--apply RECUSARIA: Gravar sozinho" in preview(rebuild, user["id"])[1]

    def test_each_shift_is_printed(self, world, bank, rebuild, user):
        _code, text = run(rebuild, user["id"])
        assert "BB: 0.0 -> 1000.0" in text

    def test_a_shift_on_a_fully_covered_account_needs_acceptance(self, world, rebuild, user):
        item, pluggy, account = connect(world, "BB", balance=5000.0)
        auto_on_ready(world, item)
        typed(world, account, 10.0, "2026-06-01")
        world.fake.add_tx(pluggy, bank_tx(-10.0, "2026-06-01", "PADARIA"))
        code, text = run(rebuild, user["id"], accept_balance_shift=False)
        assert code == rebuild.EXIT_FAILED
        assert "ALERTA" in text and "--accept-balance-shift" in text
        assert rows_of("accounts", "id = ?", (account,))[0]["initial_balance"] == 0
        code, text = run(rebuild, user["id"], from_step="balances", accept_balance_shift=True)
        assert code == rebuild.EXIT_OK, text
        assert balance_of(world, account) == 5000.0

    def test_history_older_than_pluggy_only_flags(self, world, rebuild, user):
        item, pluggy, account = connect(world, "BB", balance=5000.0)
        auto_on_ready(world, item)
        typed(world, account, 10.0, "2026-01-01")
        world.fake.add_tx(pluggy, bank_tx(-10.0, "2026-06-01", "PADARIA"))
        code, text = run(rebuild, user["id"], accept_balance_shift=False)
        assert code == rebuild.EXIT_OK, text
        assert "ALERTA" in text

    def test_a_lost_row_fails_though_the_balance_was_forced(self, world, bank, rebuild, user):
        world.fake.add_tx(bank.pluggy, bank_tx(-40.0, "2026-10-20", "PADARIA"))
        assert run(rebuild, user["id"])[0] == rebuild.EXIT_OK
        with importlib.import_module("db").get_db() as conn:
            conn.execute("DELETE FROM transactions WHERE account_id = ?", (bank.bb,))
        code, text = run(rebuild, user["id"], from_step="balances")
        assert code == rebuild.EXIT_FAILED and "sem lancamento" in text

    def test_balance_from_rows_counts_each_kind(self, world, bank, rebuild, user):
        typed(world, bank.bb, 10.0, "2026-05-01")
        typed(world, bank.bb, 25.0, "2026-05-02", kind="INCOME")
        transfer(world, bank.flash, bank.bb, 5.0, "2026-05-03")
        typed(world, bank.bb, 99.0, "2026-05-09")
        with importlib.import_module("db").get_db() as conn:
            assert rebuild.balance_from_rows(conn, user["id"], bank.bb, "2026-05-05") == 20.0

    def test_a_changed_payment_is_corrected_not_paid_twice(self, world, user):
        item, pluggy, bb = connect(world, "BB", balance=500.0)
        auto_on_ready(world, item)
        tx_id = world.fake.add_tx(pluggy, bank_tx(-838.5, "2026-10-22", "PAGAMENTO FATURA", category_id="05100000"))
        world.sync(item)
        world.fake.transactions[pluggy][0]["amount"] = -840.0
        world.sync(item)
        [row] = world.transactions(bb)
        assert row["amount"] == 840.0 and tx_id in row["source_id"]

    def test_a_changed_payment_linked_to_a_typed_one_only_points(self, world, user):
        item, pluggy, bb = connect(world, "BB", balance=500.0)
        auto_on_ready(world, item)
        world.fake.add_tx(pluggy, bank_tx(-838.5, "2026-10-22", "PAGAMENTO FATURA", category_id="05100000"))
        world.sync(item)
        with importlib.import_module("db").get_db() as conn:
            conn.execute("UPDATE transactions SET source_id = 'cartao:2026-10:app' WHERE account_id = ?", (bb,))
        world.fake.transactions[pluggy][0]["amount"] = -840.0
        world.sync(item)
        [row] = world.transactions(bb)
        assert row["amount"] == 838.5
        assert rows_of("open_finance_transactions", "user_id = ?", (user["id"],))[0]["conflict"] == "changed"


class TestCommandLine:
    def script(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "rebuild_from_pluggy.py")
        spec = importlib.util.spec_from_file_location("rebuild_from_pluggy", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_the_default_is_a_dry_run_that_writes_nothing(self, world, bank, rebuild, user, capsys):
        typed(world, bank.bb, 10.0)
        before = everything()
        assert self.script().main(["--email", user["email"]]) == 0
        assert "ENSAIO" in capsys.readouterr().out
        assert before == everything()

    def test_apply_and_the_report(self, world, bank, rebuild, user, capsys):
        world.fake.add_tx(bank.pluggy, bank_tx(-10.0, "2026-10-20", "IFOOD"))
        script = self.script()
        assert script.main(["--email", user["email"], "--apply"]) == 2
        assert script.main(["--email", user["email"], "--apply", "--app-stopped", "--accept-balance-shift"]) == 0
        assert script.main(["--email", user["email"], "--report-categories"]) == 0
        assert "Alimentação" in capsys.readouterr().out

    def test_a_wrong_email_is_refused(self, rebuild, user):
        assert self.script().main(["--email", "ninguem@example.com"]) == 2

    def test_map_needs_both_sides(self):
        script = self.script()
        args = script.parse_args(["--email", "x", "--map", "USD=abc", "--ignore", "BRL"])
        assert script.options_from(args).maps == {"USD": "abc"}
        with pytest.raises(SystemExit):
            script.options_from(script.parse_args(["--email", "x", "--map", "USD"]))


def test_the_script_alone_migrates_and_starts_no_thread(tmp_path):
    """O container de uma vez so: banco sem as migrations, sem app.py, sem thread."""
    backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = (
        "import sys, threading\n"
        "sys.path.insert(0, 'scripts')\n"
        "import rebuild_from_pluggy as script\n"
        "result = script.main(['--email', 'ninguem@example.com'])\n"
        "import db\n"
        "with db.get_db() as conn:\n"
        "    version = conn.execute(\"SELECT 1 FROM schema_migrations WHERE version = '050'\").fetchone()\n"
        "print('RESULT', result, version is not None, 'app' in sys.modules, threading.active_count())\n"
    )
    env = {**os.environ, "DATABASE_PATH": str(tmp_path / "novo.db"), "DATABASE_BACKUP_DIR": str(tmp_path / "b"),
           "ATTACHMENTS_DIR": str(tmp_path / "a"), "LOG_DIR": str(tmp_path / "l")}
    done = subprocess.run([sys.executable, "-c", code], cwd=backend, env=env, capture_output=True, text=True, timeout=120)
    assert "RESULT 2 True False 1" in done.stdout, done.stdout + done.stderr


def test_state_is_json(rebuild, world, bank, user):
    db = importlib.import_module("db")
    with db.get_db() as conn:
        plan = rebuild.build_plan(conn, user["id"], rebuild.Options())
        state = rebuild.capture_state(conn, user["id"], plan)
        assert json.loads(rows_of_setting(conn, user["id"], rebuild.STATE_SETTING)) == state
        conn.rollback()


def rows_of_setting(conn, user_id, key):
    return conn.execute(
        "SELECT value FROM user_settings WHERE user_id = ? AND setting_key = ?", (user_id, key),
    ).fetchone()["value"]
