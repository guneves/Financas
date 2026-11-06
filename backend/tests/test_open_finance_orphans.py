"""Fase 5: a notificacao que a Pluggy nunca listou, o saldo do banco decide
(decisao 1; services/open_finance_orphans.py).

O que estes testes protegem:

- a diferenca e a da Conferencia (banco - app, `open_finance_check.balance_difference()`),
  a mesma da tela: a orfa sai so quando tira-la zera exatamente essa diferenca
  (+X de uma despesa, -X de uma receita), a mais antiga ou todas juntas; sem
  tolerancia, sem subconjunto;
- diferenca 0 (o saldo ja a conta, a compra internacional em processamento, o
  caso do Claude): fica, "confirmado pelo saldo" na Conferencia;
- so depois de o banco atualizar depois de data + 5 dias e o app ler; nunca o
  que tem comprovante, divisao, "Aconteceu", valor digitado, a transferencia, o
  cartao (so lista);
- a que a Pluggy lista tarde (exata ou perto) e a mesma linha, nunca orfa.
"""

import importlib
import io
from datetime import date

import pytest

from identity_check import assert_identity
from open_finance_world import World, bank_tx, card_tx, connected, fake_pluggy, open_finance_module  # noqa: F401
from test_auto_record import confirm, notifications_on, rows_of
from test_inbox import ITAU, detection, ms, send
from test_open_finance_auto import pin_today

pytestmark = pytest.mark.usefixtures("any_bank_notifications")

TODAY = date(2026, 10, 31)
REFRESHED = "2026-10-30T12:00:00.000Z"


@pytest.fixture()
def world(client, auth, fake_pluggy, monkeypatch, invoices_module):
    notifications_on(client, auth)
    pin_today(monkeypatch, invoices_module, TODAY)
    return World(client, auth, fake_pluggy)


class Bank:
    """Uma conta do Itau na Pluggy, mapeada, com Gravar sozinho."""

    def __init__(self, world, refreshed=REFRESHED):
        self.world = world
        self.item_id, self.pluggy_item, made = connected(world, connector_name="Itaú")
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        self.pluggy_account, self.of_account, self.account = made["bank"]
        world.fake.items[self.pluggy_item]["lastUpdatedAt"] = refreshed

    def balance(self, value):
        for raw in self.world.fake.accounts[self.pluggy_item]:
            if raw["id"] == self.pluggy_account:
                raw["balance"] = value

    def notify(self, kind, cents, day, merchant="LOJA 123", **extra):
        send(self.world.client, self.world.auth, detection(kind, cents, at=ms(2026, 10, day, 12, 0), app=ITAU,
                                                           merchant=merchant, **extra))

    def sync(self):
        """Puxa do comeco (a conta ainda sem linha da Pluggy teria so os
        dias de sobreposicao), como test_global_account.pull()."""
        db = importlib.import_module("db")
        with db.get_db() as conn:
            conn.execute("UPDATE open_finance_accounts SET synced_until = NULL WHERE id = ?", (self.of_account,))
        return self.world.sync(self.item_id)["result"]

    def rows(self):
        return self.world.transactions(self.account)

    def overview(self):
        body = self.world.call("get", "/api/open-finance")
        return next(
            account for item in body["items"] for account in item["accounts"] if account["id"] == self.of_account
        )


def stored_difference(user_id, bank):
    """A diferenca pela funcao da Conferencia, direto (a mesma da tela)."""
    db = importlib.import_module("db")
    orphans = importlib.import_module("services.open_finance_orphans")
    with db.get_db() as conn:
        [account] = conn.execute(
            "SELECT * FROM open_finance_accounts WHERE id = ? AND user_id = ?", (bank.of_account, user_id),
        ).fetchall()
        return orphans.account_difference(conn, user_id, dict(account))


def item_of(user_id, transaction_id):
    [item] = rows_of("inbox_items", "user_id = ? AND target_id = ?", (user_id, transaction_id))
    return item


class TestTheBalanceDecides:
    def test_the_bank_balance_excludes_it_so_it_is_removed(self, world, user):
        bank = Bank(world)
        bank.notify("DEBIT_PURCHASE", 5000, 10)
        [row] = bank.rows()
        item_id = item_of(user["id"], row["id"])["id"]
        bank.balance(0.0)  # o banco nunca tirou os R$ 50
        body = bank.sync()
        assert bank.rows() == []
        assert body["removed_orphans"] == 1
        removed = rows_of("inbox_items", "user_id = ? AND id = ?", (user["id"], item_id))
        assert [(entry["state"], entry["reason"], entry["target_id"]) for entry in removed] == [("REMOVED", "orphan", None)]
        assert rows_of("notify_detections", "user_id = ? AND target_id = ?", (user["id"], row["id"])) == []
        assert bank.overview()["difference"] == 0
        assert_identity(user["id"])

    def test_the_balance_already_counts_it_so_it_stays_confirmed(self, world, user):
        bank = Bank(world)
        bank.notify("DEBIT_PURCHASE", 5000, 10)
        [row] = bank.rows()
        bank.balance(-50.0)
        body = bank.sync()
        assert [entry["id"] for entry in bank.rows()] == [row["id"]]
        assert body["removed_orphans"] == 0
        account = bank.overview()
        assert account["difference"] == 0
        assert [entry["id"] for entry in account["check"]["balance_confirmed"]] == [row["id"]]
        assert account["check"]["balance_confirmed_count"] == 1
        assert row["id"] not in {entry["id"] for entry in account["check"]["app_only"]}

    def test_a_future_typed_row_is_not_a_difference(self, world, user):
        """O banco nao tem o boleto agendado: a diferenca e a de hoje, e a orfa
        real de mesmo valor fica (antes saia: +50 do futuro = o conserto dela)."""
        bank = Bank(world)
        bank.notify("DEBIT_PURCHASE", 5000, 10)
        [row] = bank.rows()
        world.call("post", "/api/transactions", json={
            "account_id": bank.account, "amount": 50.0, "date": "2026-11-05", "type": "EXPENSE",
            "category": "Outros", "description": "Boleto agendado",
        })
        bank.balance(-50.0)  # o banco ja tirou a compra, e nao o boleto
        body = bank.sync()
        assert body["removed_orphans"] == 0
        assert row["id"] in {entry["id"] for entry in bank.rows()}
        assert stored_difference(user["id"], bank) == 0
        assert bank.overview()["difference"] == 0

    def test_another_difference_keeps_it(self, world, user):
        bank = Bank(world)
        bank.notify("DEBIT_PURCHASE", 5000, 10)
        bank.balance(30.0)  # +80: algo mais difere
        bank.sync()
        assert len(bank.rows()) == 1
        assert stored_difference(user["id"], bank) == 8000
        assert bank.overview()["check"]["balance_confirmed"] == []

    def test_two_orphans_that_together_explain_it_both_leave(self, world, user):
        bank = Bank(world)
        bank.notify("DEBIT_PURCHASE", 2000, 10)
        bank.notify("DEBIT_PURCHASE", 3000, 11, merchant="OUTRA LOJA")
        bank.balance(0.0)  # +50
        body = bank.sync()
        assert bank.rows() == []
        assert body["removed_orphans"] == 2

    def test_only_the_oldest_that_explains_it_leaves(self, world, user):
        bank = Bank(world)
        bank.notify("DEBIT_PURCHASE", 2000, 10)
        bank.notify("DEBIT_PURCHASE", 3000, 11, merchant="OUTRA LOJA")
        bank.balance(-30.0)  # +20
        bank.sync()
        assert [entry["amount"] for entry in bank.rows()] == [30.0]

    def test_no_subset_search(self, world, user):
        # 20 + 30 + 40, diferenca +70: so 30 + 40 explicaria; nada sai.
        bank = Bank(world)
        bank.notify("DEBIT_PURCHASE", 2000, 10)
        bank.notify("DEBIT_PURCHASE", 3000, 11, merchant="OUTRA LOJA")
        bank.notify("DEBIT_PURCHASE", 4000, 12, merchant="MAIS UMA")
        bank.balance(-20.0)
        bank.sync()
        assert len(bank.rows()) == 3

    def test_no_tolerance(self, world, user):
        bank = Bank(world)
        bank.notify("DEBIT_PURCHASE", 5000, 10)
        bank.balance(-0.01)  # +49,99
        bank.sync()
        assert len(bank.rows()) == 1

    def test_an_income_orphan_leaves_on_minus_x(self, world, user):
        bank = Bank(world)
        bank.notify("PIX_IN", 12000, 10, merchant=None, counterparty="Maria Silva")
        [row] = bank.rows()
        assert row["type"] == "INCOME"
        bank.balance(0.0)  # -120
        assert bank.sync()["removed_orphans"] == 1
        assert bank.rows() == []

    def test_an_income_orphan_never_leaves_on_plus_x(self, world, user):
        bank = Bank(world)
        bank.notify("PIX_IN", 12000, 10, merchant=None, counterparty="Maria Silva")
        bank.balance(240.0)  # +120: o sinal errado
        bank.sync()
        assert len(bank.rows()) == 1


class TestTheClaudeCase:
    def test_international_in_processing_is_kept_every_sweep(self, world, user):
        # R$ 110 notificado no dia 0; o saldo do banco ja -110; a Pluggy nada por 20 dias.
        bank = Bank(world)
        bank.notify("DEBIT_PURCHASE", 11000, 5, merchant="CLAUDE.AI", international=True)
        [row] = bank.rows()
        bank.balance(-110.0)
        for _ in range(3):
            assert bank.sync()["removed_orphans"] == 0
            assert [entry["id"] for entry in bank.rows()] == [row["id"]]
        assert [entry["id"] for entry in bank.overview()["check"]["balance_confirmed"]] == [row["id"]]

    def test_it_posts_on_day_25_and_joins_the_notified_row(self, world, user):
        bank = Bank(world)
        bank.notify("DEBIT_PURCHASE", 11000, 5, merchant="CLAUDE.AI", international=True)
        [row] = bank.rows()
        bank.balance(-112.4)
        bank.sync()
        world.fake.add_tx(bank.pluggy_account, bank_tx(-112.4, "2026-10-05", "CLAUDE.AI SUBSCRIPTION"))
        bank.sync()
        assert [(entry["id"], entry["amount"]) for entry in bank.rows()] == [(row["id"], 112.4)]
        assert_identity(user["id"])


class TestProtected:
    def setup_orphan(self, world):
        bank = Bank(world)
        bank.notify("DEBIT_PURCHASE", 5000, 10)
        [row] = bank.rows()
        bank.balance(0.0)
        return bank, row

    def test_a_receipt(self, world, client, auth):
        bank, row = self.setup_orphan(world)
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
        response = client.post(
            f"/api/transactions/{row['id']}/attachments", headers=auth,
            data={"file": (io.BytesIO(png), "nota.png")}, content_type="multipart/form-data",
        )
        assert response.status_code == 201, response.get_data(as_text=True)
        bank.sync()
        assert len(bank.rows()) == 1

    def test_a_share(self, world, client, auth):
        bank, row = self.setup_orphan(world)
        response = client.patch(f"/api/transactions/{row['id']}", headers=auth,
                                json={"share_mode": "OTHERS", "share_person": "Ana"})
        assert response.status_code == 200, response.get_data(as_text=True)
        bank.sync()
        assert len(bank.rows()) == 1

    def test_aconteceu(self, world, user):
        bank, row = self.setup_orphan(world)
        db = importlib.import_module("db")
        with db.get_db() as conn:
            conn.execute(
                "INSERT INTO open_finance_confirmed (user_id, target_table, target_id) VALUES (?, 'transactions', ?)",
                (user["id"], row["id"]),
            )
        bank.sync()
        assert len(bank.rows()) == 1

    def test_an_amount_the_owner_typed(self, world, client, auth):
        bank, row = self.setup_orphan(world)
        response = client.patch(f"/api/transactions/{row['id']}", headers=auth, json={"amount": 55})
        assert response.status_code == 200, response.get_data(as_text=True)
        bank.balance(5.0)  # +55: o conserto bateria, mas o valor e do dono
        bank.sync()
        assert [entry["amount"] for entry in bank.rows()] == [55.0]

    def test_review_does_not_protect(self, world, user):
        bank, row = self.setup_orphan(world)
        confirm(world.client, world.auth, {"table": "transactions", "id": row["id"], "category_id": world.category_id("Lazer")})
        bank.sync()
        assert bank.rows() == []


class TestWhenItWaits:
    def test_a_stale_connection_keeps_it(self, world):
        bank = Bank(world, refreshed="2026-10-14T12:00:00.000Z")  # antes de 10 + 5
        bank.notify("DEBIT_PURCHASE", 5000, 10)
        bank.balance(0.0)
        bank.sync()
        assert len(bank.rows()) == 1

    def test_too_recent_keeps_it(self, world):
        bank = Bank(world)
        bank.notify("DEBIT_PURCHASE", 5000, 28)  # 31 - 5 = 26
        bank.balance(0.0)
        bank.sync()
        assert len(bank.rows()) == 1

    def test_a_connection_not_read_yet_keeps_it(self, world, user):
        bank = Bank(world, refreshed="2099-01-01T12:00:00.000Z")  # nunca lida
        bank.notify("DEBIT_PURCHASE", 5000, 10)
        bank.balance(0.0)
        bank.sync()
        assert len(bank.rows()) == 1

    def test_listed_late_before_the_sweep_is_one_row(self, world, user):
        bank = Bank(world)
        bank.notify("DEBIT_PURCHASE", 5000, 10)
        [row] = bank.rows()
        world.fake.add_tx(bank.pluggy_account, bank_tx(-50, "2026-10-14", "LOJA 123"))
        bank.balance(0.0)  # se o app ainda tivesse a notificada sozinha, +50
        body = bank.sync()
        # Intocada e com outra data: refeita do jeito do banco (reconcile_recorded), uma linha.
        assert [(entry["amount"], entry["date"], entry["source_type"]) for entry in bank.rows()] == [
            (50.0, "2026-10-14", "OPEN_FINANCE"),
        ]
        assert body["removed_orphans"] == 0
        assert row["id"]
        assert_identity(user["id"])


class TestOutOfScope:
    def test_a_converted_own_transfer(self, world, client, auth):
        bank = Bank(world)
        other = world.account("Poupança")
        bank.notify("PIX_OUT", 5000, 10, merchant=None, counterparty="Maria Silva")
        [row] = bank.rows()
        response = client.patch(f"/api/transactions/{row['id']}", headers=auth, json={
            "type": "TRANSFER", "account_id": bank.account, "transfer_account_id": other,
        })
        assert response.status_code == 200, response.get_data(as_text=True)
        bank.balance(0.0)
        bank.sync()
        assert [entry["type"] for entry in bank.rows()] == ["TRANSFER"]

    def test_a_card_purchase_is_list_only(self, world):
        item_id, pluggy_item, made = connected(world, connector_name="Itaú", bank=False, card=True)
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        world.fake.items[pluggy_item]["lastUpdatedAt"] = REFRESHED
        send(world.client, world.auth, detection("CREDIT_PURCHASE", 5000, at=ms(2026, 10, 10, 12, 0), app=ITAU,
                                                 merchant="LOJA 123"))
        world.fake.accounts[pluggy_item][0]["balance"] = 0.0
        body = world.sync(item_id)["result"]
        assert len(world.call("get", "/api/cc-expenses")) == 1
        assert body["removed_orphans"] == 0


class TestPure:
    def orphans(self):
        return importlib.import_module("services.open_finance_orphans")

    def test_choose(self):
        choose = self.orphans().choose
        a = {"type": "EXPENSE", "amount": 20}
        b = {"type": "EXPENSE", "amount": 30}
        c = {"type": "INCOME", "amount": 30}
        assert choose([a, b], 5000) == [a, b]
        assert choose([a, b], 2000) == [a]
        assert choose([a, b], 3000) == [b]
        assert choose([a, b], 1000) == []
        assert choose([a, b], 0) == []
        assert choose([a, b], None) == []
        assert choose([c], -3000) == [c]
        assert choose([c], 3000) == []
        assert choose([a, c], -1000) == [a, c]

    def test_the_conference_helper(self):
        check = importlib.import_module("services.open_finance_check")
        assert check.balance_difference({"balance": 100.0}, {"balance": 50.0}) == (50.0, 5000)
        assert check.balance_difference({"balance": None}, {"balance": 50.0}) == (50.0, None)
        assert check.balance_difference({"balance": 100.0}, None) == (None, None)
        assert check.balance_difference({"balance": 100.0}, {"balance": 50.0}, settled_balance=70.0) == (70.0, 3000)

