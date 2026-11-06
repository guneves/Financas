"""Fase 4: so o palpite vai para o Revisar (decisao 6).

O que estes testes protegem:

- "intocado" e o snapshot: o "e meu" sem mudar nada nao e toque; mudar a
  categoria e. Por isso a revisao que sai sozinha nao cala o banco: o valor,
  o sumico, a outra ponta da transferencia, a data e o valor perto (near match)
  continuam valendo depois;
- sai sozinha a linha que a Pluggy confirmou com categoria certa (regra do dono,
  tabela de comerciantes, CNAE) e a transferencia com as duas pontas no app;
- ficam a revisar: a categoria da arvore da Pluggy ou a padrao, o Flash (sem
  Pluggy) e a conta global (revisa na tela dela);
- na mesma passada que grava: o contador do Revisar nunca mostra e logo tira.
"""

import importlib
import time

import pytest

from identity_check import assert_identity
from open_finance_world import World, bank_tx, card_tx, connected, fake_pluggy, open_finance_module  # noqa: F401
from test_auto_record import confirm, notifications_on, rows_of
from test_global_account import global_world, offline, pull, usd_tx  # noqa: F401
from test_inbox import BB, ITAU, detection, ms, send
from test_open_finance_auto import auto_on, meupluggy
from test_notification_policy import FLASH, flash  # noqa: F401

pytestmark = pytest.mark.usefixtures("any_bank_notifications")

PIX = "05000000"
SHOPPING = "08000000"  # "Compras" na arvore da Pluggy: palpite largo


@pytest.fixture()
def world(client, auth, fake_pluggy):
    notifications_on(client, auth)
    client.patch("/api/open-finance/settings", json={"auto_record": True}, headers=auth)
    return World(client, auth, fake_pluggy)


def _setup(world, **kwargs):
    item_id, _p, made = connected(world, connector_name="Itaú", **kwargs)
    world.call("patch", "/api/open-finance/settings", json={"auto_record": True, "include_pending": True})
    return item_id, made


def of_row(user_id, pluggy_id):
    [row] = rows_of("open_finance_transactions", "user_id = ? AND pluggy_transaction_id = ?", (user_id, pluggy_id))
    return row


def stored(user_id, transaction_id):
    [row] = rows_of("transactions", "user_id = ? AND id = ?", (user_id, transaction_id))
    return row


def bank_amount(world, account, pluggy_id, amount):
    """O banco muda o valor da mesma transacao (mesma id)."""
    for tx in world.fake.transactions[account]:
        if tx["id"] == pluggy_id:
            tx["amount"] = amount


def review_count(world):
    return world.call("get", "/api/home")["review_count"]


def _notified_padaria(world, made, item_id, day=20, cents=4590):
    """Notificacao + Pluggy da mesma compra na padaria (comerciante conhecido):
    a revisao sai sozinha. Devolve (lancamento, id da Pluggy)."""
    account, _of, mine = made["bank"]
    send(world.client, world.auth, detection("DEBIT_PURCHASE", cents, at=ms(2026, 10, day, 14, 0), app=ITAU))
    pluggy_id = world.fake.add_tx(account, bank_tx(-cents / 100, f"2026-10-{day}", "COMPRA CARTAO DEB PADARIA"))
    world.sync(item_id)
    [row] = world.transactions(mine)
    return row, pluggy_id


# ---------------------------------------------------------------------------
# O que sai sozinho e o que fica
# ---------------------------------------------------------------------------

class TestWhatLeavesReview:
    def test_notification_and_pluggy_agree_with_a_merchant_category(self, world, user):
        item_id, made = _setup(world)
        row, _pluggy_id = _notified_padaria(world, made, item_id)
        assert (row["needs_review"], row["category_id"]) == (0, world.category_id("Alimentação"))
        assert review_count(world) == 0
        assert_identity(user["id"])

    def test_the_banks_merchant_replaces_the_notifications_guess(self, world, user):
        # A notificacao nao diz o comerciante; a Pluggy diz (padaria): a
        # categoria certa entra na linha ainda intocada.
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 1990, at=ms(2026, 10, 20, 9, 0), app=ITAU,
                                                 merchant="LOJA 123"))
        [before] = world.transactions(mine)
        assert before["needs_review"] == 1
        world.fake.add_tx(account, bank_tx(-19.9, "2026-10-20", "PADARIA DO ZE"))
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert (after["id"], after["needs_review"], after["category_id"]) == (
            before["id"], 0, world.category_id("Alimentação"),
        )

    def test_a_pluggy_tree_category_stays_in_review(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 1990, at=ms(2026, 10, 20, 9, 0), app=ITAU,
                                                 merchant="LOJA 123"))
        world.fake.add_tx(account, bank_tx(-19.9, "2026-10-20", "LOJA 123", category_id=SHOPPING))
        world.sync(item_id)
        [row] = world.transactions(mine)
        assert (row["source_type"], row["needs_review"]) == ("OPEN_FINANCE", 1)
        assert review_count(world) == 1

    def test_the_default_category_stays_in_review(self, world):
        item_id, made = _setup(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-19.9, "2026-10-20", "LOJA 123"))
        world.sync(item_id)
        [row] = world.transactions(made["bank"][2])
        assert row["needs_review"] == 1

    def test_pluggy_alone_with_a_merchant_category_never_waits_for_review(self, world):
        item_id, made = _setup(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-12, "2026-10-25", "PADARIA"))
        world.sync(item_id)
        [row] = world.transactions(made["bank"][2])
        assert row["needs_review"] == 0
        assert review_count(world) == 0

    def test_the_owners_rule_is_confident(self, world, client, auth):
        item_id, made = _setup(world)
        response = client.post("/api/import-rules", headers=auth,
                               json={"pattern": "loja 123", "category_id": world.category_id("Lazer")})
        assert response.status_code == 201, response.get_data(as_text=True)
        world.fake.add_tx(made["bank"][0], bank_tx(-19.9, "2026-10-20", "LOJA 123", category_id=SHOPPING))
        world.sync(item_id)
        [row] = world.transactions(made["bank"][2])
        assert (row["needs_review"], row["category_id"]) == (0, world.category_id("Lazer"))

    def test_a_card_purchase_with_a_merchant_category(self, world):
        item_id, made = _setup(world, bank=False, card=True)
        world.fake.add_tx(made["card"][0], card_tx(89.9, "2026-10-22", "SMART FIT", docs_sign=True))
        world.sync(item_id)
        [row] = world.call("get", "/api/cc-expenses")
        assert row["needs_review"] == 0

    def test_a_card_refund_stays_in_review(self, world):
        item_id, made = _setup(world, bank=False, card=True)
        world.fake.add_tx(made["card"][0], card_tx(-89.9, "2026-10-22", "SMART FIT", docs_sign=True))
        world.sync(item_id)
        rows = world.call("get", "/api/cc-expenses")
        assert [(row["kind"], row["needs_review"]) for row in rows] == [("REFUND", 1)]

    def test_the_flash_stays_in_review(self, client, auth, flash):
        # Sem Pluggy, nada confirma: mesmo a padaria fica a revisar.
        send(client, auth, detection("PURCHASE", 3200, at=int(time.time() * 1000), app=FLASH,
                                     merchant="PADARIA BOM PAO"))
        rows = [row for row in client.get("/api/transactions", headers=auth).get_json() if row["amount"] == 32.0]
        assert [(row["account_id"], row["needs_review"]) for row in rows] == [(flash, 1)]

    def test_both_sides_of_an_own_transfer_leave_review(self, world, user):
        made = meupluggy(world)
        auto_on(world)
        itau, bb = made["itau:0001/1-1"], made["bb:0003/3-3"]
        send(world.client, world.auth, detection("PIX_OUT", 70000, at=ms(2026, 10, 22, 9, 0), app=ITAU, merchant=None,
                                                 counterparty="Fulano Dono"))
        [first] = [row for row in world.transactions() if row["amount"] == 700.0]
        assert (first["type"], first["needs_review"]) == ("EXPENSE", 1)
        world.fake.add_tx(bb[0], bank_tx(700, "2026-10-22", "PIX RECEBIDO", category_id=PIX, counterparty="Fulano Dono"))
        world.sync(made["items"]["bb"])
        [row] = [row for row in world.transactions() if row["amount"] == 700.0]
        assert (row["id"], row["type"], row["account_id"], row["transfer_account_id"]) == (
            first["id"], "TRANSFER", itau[2], bb[2],
        )
        assert stored(user["id"], row["id"])["needs_review"] == 0
        assert_identity(user["id"])

    def test_two_notified_sides_without_pluggy_stay_in_review(self, world, user):
        made = meupluggy(world)
        auto_on(world)
        send(world.client, world.auth, detection("PIX_OUT", 70000, at=ms(2026, 10, 22, 9, 0), app=ITAU, merchant=None,
                                                 counterparty="Fulano Dono"))
        send(world.client, world.auth, detection("PIX_IN", 70000, at=ms(2026, 10, 22, 9, 1), app=BB, merchant=None,
                                                 counterparty="Fulano Dono"))
        [row] = [row for row in world.transactions() if row["amount"] == 700.0]
        assert row["type"] == "TRANSFER"
        assert stored(user["id"], row["id"])["needs_review"] == 1
        assert made

    def test_the_global_account_keeps_its_review(self, world):
        ids = global_world(world)
        world.fake.add_tx(ids["wise_pluggy"], usd_tx(-9.99, "2026-10-20", description="Padaria Bakery"))
        pull(world, ids["item"])
        [row] = world.call("get", f"/api/transactions?account_id={ids['wise']}")
        assert row["needs_review"] == 1


# ---------------------------------------------------------------------------
# A armadilha: depois de sair sozinha, o banco continua mandando
# ---------------------------------------------------------------------------

class TestTheBankStillApplies:
    def test_auto_cleared_then_the_bank_changes_the_amount(self, world, user):
        item_id, made = _setup(world)
        account = made["bank"][0]
        row, pluggy_id = _notified_padaria(world, made, item_id)
        assert row["needs_review"] == 0
        bank_amount(world, account, pluggy_id, -47.9)
        world.sync(item_id)
        [after] = world.transactions(made["bank"][2])
        assert (after["id"], after["amount"]) == (row["id"], 47.9)
        # E de novo: o snapshot do item tambem andou.
        bank_amount(world, account, pluggy_id, -48.9)
        world.sync(item_id)
        [again] = world.transactions(made["bank"][2])
        assert (again["id"], again["amount"]) == (row["id"], 48.9)
        assert_identity(user["id"])

    def test_auto_cleared_pluggy_only_then_the_bank_changes_the_amount(self, world):
        item_id, made = _setup(world)
        account = made["bank"][0]
        pluggy_id = world.fake.add_tx(account, bank_tx(-12, "2026-10-25", "PADARIA"))
        world.sync(item_id)
        [row] = world.transactions(made["bank"][2])
        assert (row["needs_review"], row["category_id"]) == (0, world.category_id("Alimentação"))
        bank_amount(world, account, pluggy_id, -13)
        world.sync(item_id)
        [after] = world.transactions(made["bank"][2])
        assert (after["id"], after["amount"]) == (row["id"], 13.0)

    def test_auto_cleared_then_the_bank_drops_it(self, world, user):
        item_id, made = _setup(world)
        account = made["bank"][0]
        row, pluggy_id = _notified_padaria(world, made, item_id)
        assert row["needs_review"] == 0
        world.fake.drop_tx(account, pluggy_id)
        world.fake.add_tx(account, bank_tx(-30, "2026-10-24", "MERCADO"))
        world.sync(item_id)
        assert [entry["amount"] for entry in world.transactions(made["bank"][2])] == [30.0]
        assert of_row(user["id"], pluggy_id)["role"] == "REMOVED"
        assert_identity(user["id"])

    def test_auto_cleared_then_the_other_side_of_an_own_transfer_arrives(self, world, user, client, auth):
        made = meupluggy(world)
        auto_on(world)
        itau, bb = made["itau:0001/1-1"], made["bb:0003/3-3"]
        # A regra do dono da categoria ao Pix: a despesa sai da revisao sozinha.
        client.post("/api/import-rules", headers=auth,
                    json={"pattern": "pix enviado", "category_id": world.category_id("Lazer")})
        world.fake.add_tx(itau[0], bank_tx(-700, "2026-10-22", "PIX ENVIADO", category_id=PIX,
                                           counterparty="Fulano Dono"))
        world.sync(made["items"]["itau"])
        [first] = [row for row in world.transactions() if row["amount"] == 700.0]
        assert (first["type"], first["needs_review"]) == ("EXPENSE", 0)
        world.fake.add_tx(bb[0], bank_tx(700, "2026-10-22", "PIX RECEBIDO", category_id=PIX, counterparty="Fulano Dono"))
        world.sync(made["items"]["bb"])
        [row] = [row for row in world.transactions() if row["amount"] == 700.0]
        assert (row["id"], row["type"], row["account_id"], row["transfer_account_id"]) == (
            first["id"], "TRANSFER", itau[2], bb[2],
        )
        assert_identity(user["id"])

    def test_auto_cleared_notification_then_the_other_side_is_notified(self, world, user, client, auth):
        made = meupluggy(world)
        auto_on(world)
        itau, bb = made["itau:0001/1-1"], made["bb:0003/3-3"]
        client.post("/api/import-rules", headers=auth,
                    json={"pattern": "pix enviado", "category_id": world.category_id("Lazer")})
        send(world.client, world.auth, detection("PIX_OUT", 70000, at=ms(2026, 10, 22, 9, 0), app=ITAU, merchant=None,
                                                 counterparty="Fulano Dono"))
        world.fake.add_tx(itau[0], bank_tx(-700, "2026-10-22", "PIX ENVIADO", category_id=PIX,
                                           counterparty="Fulano Dono"))
        world.sync(made["items"]["itau"])
        [first] = [row for row in world.transactions() if row["amount"] == 700.0]
        assert (first["type"], first["needs_review"]) == ("EXPENSE", 0)
        send(world.client, world.auth, detection("PIX_IN", 70000, at=ms(2026, 10, 22, 9, 1), app=BB, merchant=None,
                                                 counterparty="Fulano Dono"))
        [row] = [row for row in world.transactions() if row["amount"] == 700.0]
        assert (row["id"], row["type"], row["account_id"], row["transfer_account_id"]) == (
            first["id"], "TRANSFER", itau[2], bb[2],
        )
        assert_identity(user["id"])

    def test_auto_cleared_pending_then_posted_with_another_amount(self, world, user):
        # A gorjeta: pendente R$ 100 (confirma e sai da revisao), liquidada R$ 112
        # com outra id: a mesma linha, no valor do banco.
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 10000, at=ms(2026, 10, 22, 12, 0), app=ITAU,
                                                 merchant="RESTAURANTE SABOR"))
        pending_id = world.fake.add_tx(account, bank_tx(-100, "2026-10-22", "RESTAURANTE SABOR", status="PENDING"))
        world.sync(item_id)
        [row] = world.transactions(mine)
        assert (row["needs_review"], row["source_id"]) == (0, pending_id)
        world.fake.drop_tx(account, pending_id)
        world.fake.add_tx(account, bank_tx(-112, "2026-10-22", "RESTAURANTE SABOR LTDA"))
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert (after["id"], after["amount"]) == (row["id"], 112.0)
        assert_identity(user["id"])

    def test_auto_cleared_then_a_near_amount_notification_joins(self, world, user):
        # A Pluggy primeiro (sai da revisao), a notificacao com outro valor depois:
        # uma linha so, no valor do banco.
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        world.fake.add_tx(account, bank_tx(-112, "2026-10-22", "RESTAURANTE SABOR LTDA"))
        world.sync(item_id)
        [row] = world.transactions(mine)
        assert row["needs_review"] == 0
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 10000, at=ms(2026, 10, 22, 12, 0), app=ITAU,
                                                 merchant="RESTAURANTE SABOR"))
        assert [(entry["id"], entry["amount"]) for entry in world.transactions(mine)] == [(row["id"], 112.0)]
        assert_identity(user["id"])

    def test_reviewed_without_a_change_follows_the_bank_date(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 1990, at=ms(2026, 10, 20, 23, 50), app=ITAU,
                                                 merchant="LOJA 123"))
        [row] = world.transactions(mine)
        confirm(world.client, world.auth, {"table": "transactions", "id": row["id"], "category_id": row["category_id"]})
        world.fake.add_tx(account, bank_tx(-19.9, "2026-10-21", "LOJA 123"))
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert after["date"] == "2026-10-21"
        assert_identity(user["id"])

    def test_a_changed_category_keeps_the_date_and_only_links(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 1990, at=ms(2026, 10, 20, 23, 50), app=ITAU,
                                                 merchant="LOJA 123"))
        [row] = world.transactions(mine)
        confirm(world.client, world.auth, {"table": "transactions", "id": row["id"], "category_id": world.category_id("Lazer")})
        pluggy_id = world.fake.add_tx(account, bank_tx(-19.9, "2026-10-21", "LOJA 123"))
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert (after["id"], after["date"], after["category_id"]) == (row["id"], "2026-10-20", world.category_id("Lazer"))
        assert of_row(user["id"], pluggy_id)["role"] == "MATCHED"
        assert_identity(user["id"])

    def test_a_changed_category_is_never_overwritten_by_the_bank(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 4590, at=ms(2026, 10, 20, 14, 0), app=ITAU))
        [row] = world.transactions(mine)
        confirm(world.client, world.auth, {"table": "transactions", "id": row["id"], "category_id": world.category_id("Lazer")})
        world.fake.add_tx(account, bank_tx(-45.9, "2026-10-20", "COMPRA CARTAO DEB PADARIA"))
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert (after["id"], after["category_id"]) == (row["id"], world.category_id("Lazer"))


def test_untouched_is_the_snapshot_not_the_review(world, user):
    """notification_untouched(): o "e meu" nao toca, a categoria toca."""
    item_id, made = _setup(world)
    send(world.client, world.auth, detection("DEBIT_PURCHASE", 1990, at=ms(2026, 10, 20, 9, 0), app=ITAU,
                                             merchant="LOJA 123"))
    [row] = world.transactions(made["bank"][2])
    ofi = importlib.import_module("services.open_finance_inbox")
    inbox = importlib.import_module("services.inbox")
    db = importlib.import_module("db")

    def untouched():
        with db.get_db() as conn:
            [item] = conn.execute(
                "SELECT * FROM inbox_items WHERE user_id = ? AND target_id = ?", (user["id"], row["id"]),
            ).fetchall()
            return ofi.notification_untouched(conn, user["id"], inbox.item_dict(item))

    assert untouched()
    confirm(world.client, world.auth, {"table": "transactions", "id": row["id"]})
    assert untouched()
    confirm(world.client, world.auth, {"table": "transactions", "id": row["id"], "category_id": world.category_id("Lazer")})
    assert not untouched()
    assert item_id
