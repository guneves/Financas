"""Tudo automatico, Fase 1 (automation-prompt, dono 2026-11-18): o
Revisar decide sozinho.

1.1 A categoria da Pluggy preenche uma linha ainda na padrao: o aviso nasce em
    "Outros"; quando a Pluggy confirma com a arvore dela (Groceries ->
    Alimentacao), a categoria entra, a linha continua a revisar, a decisao fica
    no registro (auto_decisions) com "Desfazer". O que o dono trocou, ou o que a
    regra dele deu, fica.
1.2 Auto-confirmar: N dias depois da data (review_auto_days, padrao 3 em
    producao; 0 aqui pelo conftest) a linha sai da revisao com a categoria que
    tem. Numa conta da Pluggy ela antes espera o banco (ou BANK_WAIT_MAX_DAYS a
    mais). "Desfazer" a devolve para sempre.
"""

import importlib
from datetime import date, datetime

import pytest

from finance_world import freeze
from identity_check import assert_identity
from open_finance_world import World, bank_tx, card_tx, connected, fake_pluggy, open_finance_module  # noqa: F401
from test_auto_record import confirm, notifications_on, rows_of
from test_inbox import ITAU, detection, ms, send
from test_notification_policy import FLASH, flash  # noqa: F401

pytestmark = pytest.mark.usefixtures("any_bank_notifications")

GROCERIES = "10000000"
SETTINGS = "/api/inbox/settings"


@pytest.fixture()
def world(client, auth, fake_pluggy):
    notifications_on(client, auth)
    client.patch("/api/open-finance/settings", json={"auto_record": True}, headers=auth)
    return World(client, auth, fake_pluggy)


@pytest.fixture()
def clock(monkeypatch):
    dates = importlib.import_module("dates")

    def set_day(year, month, day):
        # O relogio de todos: dates.now_source, e o local_today que
        # open_finance_world congelou modulo a modulo (2026-10-27).
        monkeypatch.setattr(dates, "now_source", lambda: datetime(year, month, day, 12))
        freeze(monkeypatch, date(year, month, day))
    return set_day


def _setup(world, **kwargs):
    item_id, _p, made = connected(world, connector_name="Itaú", **kwargs)
    world.call("patch", "/api/open-finance/settings", json={"auto_record": True, "include_pending": True})
    return item_id, made


def decisions(world, kind=None):
    items = world.call("get", "/api/review/auto")["items"]
    return [entry for entry in items if kind is None or entry["kind"] == kind]


def stored(user_id, transaction_id):
    [row] = rows_of("transactions", "user_id = ? AND id = ?", (user_id, transaction_id))
    return row


def _notice(world, cents=1990, day=20, merchant="LOJA 123"):
    send(world.client, world.auth, detection("DEBIT_PURCHASE", cents, at=ms(2026, 10, day, 9, 0), app=ITAU,
                                             merchant=merchant))


# ---------------------------------------------------------------------------
# 1.1 A categoria da Pluggy preenche a padrao
# ---------------------------------------------------------------------------

class TestPluggyFillsTheDefault:
    def test_groceries_fill_an_untouched_notice_row(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        _notice(world)
        [before] = world.transactions(mine)
        assert before["category_id"] == world.category_id("Outros")
        world.fake.add_tx(account, bank_tx(-19.9, "2026-10-20", "LOJA 123", category_id=GROCERIES))
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert (after["id"], after["category_id"], after["needs_review"]) == (
            before["id"], world.category_id("Alimentação"), 1,
        )
        [decision] = decisions(world, "pluggy_category")
        assert decision["target_id"] == before["id"]
        assert decision["detail"]["after"][1] == world.category_id("Alimentação")
        assert_identity(user["id"])

    def test_the_fill_is_not_the_owners_touch(self, world, user):
        # Depois de preencher, o banco ainda muda o valor da linha (o snapshot andou).
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        _notice(world)
        pluggy_id = world.fake.add_tx(account, bank_tx(-19.9, "2026-10-20", "LOJA 123", category_id=GROCERIES))
        world.sync(item_id)
        for tx in world.fake.transactions[account]:
            if tx["id"] == pluggy_id:
                tx["amount"] = -21.9
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert (after["amount"], after["category_id"]) == (21.9, world.category_id("Alimentação"))
        assert_identity(user["id"])

    def test_a_card_notice_row(self, world, user):
        item_id, made = _setup(world, bank=False, card=True)
        account, _of, card = made["card"]
        send(world.client, world.auth, detection("CREDIT_PURCHASE", 1990, at=ms(2026, 10, 20, 9, 0), app=ITAU,
                                                 merchant="LOJA 123"))
        [before] = world.card_rows(card)
        assert before["category_id"] == world.category_id("Outros")
        world.fake.add_tx(account, card_tx(19.9, "2026-10-20", "LOJA 123", category_id=GROCERIES, docs_sign=True))
        world.sync(item_id)
        [after] = world.card_rows(card)
        assert (after["category_id"], after["needs_review"]) == (world.category_id("Alimentação"), 1)
        assert_identity(user["id"])

    def test_recategorised_by_the_owner_keeps_theirs(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        _notice(world)
        [row] = world.transactions(mine)
        confirm(world.client, world.auth, {"table": "transactions", "id": row["id"], "category_id": world.category_id("Lazer")})
        world.fake.add_tx(account, bank_tx(-19.9, "2026-10-20", "LOJA 123", category_id=GROCERIES))
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert after["category_id"] == world.category_id("Lazer")
        assert decisions(world) == []

    def test_reviewed_as_is_keeps_the_default(self, world):
        # "E meu" com a padrao foi a escolha do dono: a Pluggy nao troca.
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        _notice(world)
        [row] = world.transactions(mine)
        confirm(world.client, world.auth, {"table": "transactions", "id": row["id"]})
        world.fake.add_tx(account, bank_tx(-19.9, "2026-10-20", "LOJA 123", category_id=GROCERIES))
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert after["category_id"] == world.category_id("Outros")

    def test_an_owner_rule_keeps_the_rule(self, world, client, auth):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        response = client.post("/api/import-rules", headers=auth,
                               json={"pattern": "loja 123", "category_id": world.category_id("Lazer")})
        assert response.status_code == 201, response.get_data(as_text=True)
        _notice(world)
        [before] = world.transactions(mine)
        assert before["category_id"] == world.category_id("Lazer")
        # O banco descreve de outro jeito: a regra nao casa com o texto dele.
        world.fake.add_tx(account, bank_tx(-19.9, "2026-10-20", "PAG*ZZQ 4471", category_id=GROCERIES))
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert after["category_id"] == world.category_id("Lazer")
        assert decisions(world) == []

    def test_pluggy_alone_is_born_with_the_tree_and_decides_nothing(self, world):
        item_id, made = _setup(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-19.9, "2026-10-20", "LOJA 123", category_id=GROCERIES))
        world.sync(item_id)
        [row] = world.transactions(made["bank"][2])
        assert row["category_id"] == world.category_id("Alimentação")
        assert decisions(world) == []

    def test_undo_restores_the_default_and_never_refills(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        _notice(world)
        pluggy_id = world.fake.add_tx(account, bank_tx(-19.9, "2026-10-20", "LOJA 123", category_id=GROCERIES))
        world.sync(item_id)
        [decision] = decisions(world, "pluggy_category")
        undone = world.call("post", f"/api/review/auto/{decision['id']}/undo")
        assert undone["undone_at"]
        [row] = world.transactions(mine)
        assert row["category_id"] == world.category_id("Outros")
        world.call("post", f"/api/review/auto/{decision['id']}/undo", expected=409)
        world.sync(item_id)
        [again] = world.transactions(mine)
        assert again["category_id"] == world.category_id("Outros")
        # O desfazer e do app: o banco continua corrigindo o valor.
        for tx in world.fake.transactions[account]:
            if tx["id"] == pluggy_id:
                tx["amount"] = -21.9
        world.sync(item_id)
        [last] = world.transactions(mine)
        assert last["amount"] == 21.9
        assert_identity(user["id"])

    def test_undo_of_an_unknown_decision_is_404(self, world):
        world.call("post", "/api/review/auto/nao-existe/undo", expected=404)


# ---------------------------------------------------------------------------
# 1.2 Auto-confirmar
# ---------------------------------------------------------------------------

def review_days(world, days):
    body = world.call("patch", SETTINGS, json={"review_auto_days": days})
    assert body["review_auto_days"] == days


class TestTheSetting:
    def test_get_and_patch(self, world):
        assert world.call("get", SETTINGS)["review_auto_days"] == 0  # conftest: REVIEW_AUTO_DAYS_DEFAULT=0
        review_days(world, 3)
        assert world.call("get", SETTINGS)["review_auto_days"] == 3
        review_days(world, 0)

    @pytest.mark.parametrize("value", [31, -1, True, "3", 2.5, None])
    def test_refuses_out_of_range(self, world, value):
        world.call("patch", SETTINGS, json={"review_auto_days": value}, expected=400)

    def test_other_users_setting_is_their_own(self, world, client, other_user):
        review_days(world, 5)
        db = importlib.import_module("db")
        review_auto = importlib.import_module("services.review_auto")
        with db.get_db() as conn:
            assert review_auto.days(conn, other_user["id"]) == 0


class TestAutoConfirm:
    def test_a_flash_row_leaves_after_n_days(self, client, auth, flash, user, clock):
        world = World(client, auth, None)
        review_days(world, 3)
        clock(2026, 10, 21)
        send(client, auth, detection("PURCHASE", 3200, at=ms(2026, 10, 20, 12, 0), app=FLASH, merchant="RESTAURANTE"))
        [row] = [entry for entry in world.transactions(flash) if entry["amount"] == 32.0]
        assert row["needs_review"] == 1
        clock(2026, 10, 22)
        assert world.call("get", "/api/review")["count"] == 1
        clock(2026, 10, 23)
        assert world.call("get", "/api/review")["count"] == 0
        assert stored(user["id"], row["id"])["needs_review"] == 0
        [decision] = decisions(world, "auto_confirm")
        assert (decision["target_id"], decision["detail"]["category"][1]) == (row["id"], row["category_id"])

    def test_off_keeps_everything(self, client, auth, flash, clock):
        world = World(client, auth, None)
        clock(2026, 11, 30)
        send(client, auth, detection("PURCHASE", 3200, at=ms(2026, 10, 20, 12, 0), app=FLASH, merchant="RESTAURANTE"))
        assert world.call("get", "/api/review")["count"] == 1
        assert decisions(world) == []

    def test_an_edited_row_leaves_too(self, client, auth, flash, user, clock):
        world = World(client, auth, None)
        review_days(world, 3)
        clock(2026, 10, 21)
        send(client, auth, detection("PURCHASE", 3200, at=ms(2026, 10, 20, 12, 0), app=FLASH, merchant="RESTAURANTE"))
        [row] = [entry for entry in world.transactions(flash) if entry["amount"] == 32.0]
        world.call("patch", f"/api/transactions/{row['id']}", json={"category_id": world.category_id("Alimentação")})
        clock(2026, 10, 25)
        assert world.call("get", "/api/review")["count"] == 0
        assert stored(user["id"], row["id"])["category_id"] == world.category_id("Alimentação")

    def test_a_fed_row_waits_for_the_bank_then_takes_its_category(self, world, user, clock):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        review_days(world, 3)
        clock(2026, 10, 20)
        _notice(world)
        clock(2026, 10, 24)
        assert world.call("get", "/api/review")["count"] == 1  # o banco ainda nao falou
        world.fake.add_tx(account, bank_tx(-19.9, "2026-10-20", "LOJA 123", category_id=GROCERIES))
        world.sync(item_id)
        assert world.call("get", "/api/review")["count"] == 0
        [row] = world.transactions(mine)
        assert (row["needs_review"], row["category_id"]) == (0, world.category_id("Alimentação"))
        assert {entry["kind"] for entry in decisions(world)} == {"pluggy_category", "auto_confirm"}
        assert_identity(user["id"])

    def test_a_dead_connection_holds_nothing_forever(self, world, clock):
        _item_id, made = _setup(world)
        review_days(world, 3)
        clock(2026, 10, 20)
        _notice(world)
        clock(2026, 10, 25)
        assert world.call("get", "/api/review")["count"] == 1
        clock(2026, 10, 26)  # 3 dias + BANK_WAIT_MAX_DAYS (3)
        assert world.call("get", "/api/review")["count"] == 0
        assert made

    def test_a_card_purchase_leaves_with_all_installments(self, client, auth, user, clock):
        world = World(client, auth, None)
        notifications_on(client, auth)
        card = world.call("post", "/api/credit-cards", json={"name": "Itaú Visa", "due_day": 10, "closing_day": 3})["id"]
        review_days(world, 3)
        clock(2026, 10, 21)
        send(client, auth, detection("CREDIT_PURCHASE", 30000, at=ms(2026, 10, 20, 12, 0), app=ITAU,
                                     merchant="LOJA 123", installments=3))
        rows = world.card_rows(card)
        assert rows and all(row["needs_review"] == 1 for row in rows)
        clock(2026, 10, 23)
        assert world.call("get", "/api/review")["count"] == 0
        assert all(row["needs_review"] == 0 for row in world.card_rows(card))
        assert len(decisions(world, "auto_confirm")) == 1
        assert user

    def test_concurrent_reads_confirm_and_record_once(self, client, auth, flash, user, clock, monkeypatch):
        # Inicio pede /api/home, /api/home/panels e /api/budgets juntos e cada leitura
        # passa por confirm_due: as tres viam a linha ainda a revisar e cada uma
        # gravava um auto_confirm (3 por linha no servidor, 2026-11-25). Aqui a
        # segunda leitura ve a lista velha, como a que leu antes do commit da primeira.
        world = World(client, auth, None)
        review_days(world, 3)
        clock(2026, 10, 21)
        send(client, auth, detection("PURCHASE", 3200, at=ms(2026, 10, 20, 12, 0), app=FLASH, merchant="RESTAURANTE"))
        clock(2026, 10, 24)
        db = importlib.import_module("db")
        review_auto = importlib.import_module("services.review_auto")
        with db.get_db() as conn:
            stale = review_auto._due_transactions(conn, user["id"], "2026-10-21")
        assert len(stale) == 1
        assert world.call("get", "/api/review")["count"] == 0
        monkeypatch.setattr(review_auto, "_due_transactions", lambda *_args: stale)
        with db.get_db() as conn:
            assert review_auto.confirm_due(conn, user["id"], date(2026, 10, 24)) == 0
        assert len(decisions(world, "auto_confirm")) == 1

    def test_concurrent_reads_confirm_a_card_purchase_once(self, client, auth, user, clock, monkeypatch):
        world = World(client, auth, None)
        notifications_on(client, auth)
        world.call("post", "/api/credit-cards", json={"name": "Itaú Visa", "due_day": 10, "closing_day": 3})
        review_days(world, 3)
        clock(2026, 10, 21)
        send(client, auth, detection("CREDIT_PURCHASE", 30000, at=ms(2026, 10, 20, 12, 0), app=ITAU,
                                     merchant="LOJA 123", installments=3))
        clock(2026, 10, 23)
        db = importlib.import_module("db")
        review_auto = importlib.import_module("services.review_auto")
        with db.get_db() as conn:
            stale = review_auto._due_purchases(conn, user["id"], "2026-10-20")
        assert len(stale) == 1
        assert world.call("get", "/api/review")["count"] == 0
        monkeypatch.setattr(review_auto, "_due_purchases", lambda *_args: stale)
        with db.get_db() as conn:
            assert review_auto.confirm_due(conn, user["id"], date(2026, 10, 23)) == 0
        assert len(decisions(world, "auto_confirm")) == 1

    def test_undo_puts_it_back_for_good(self, client, auth, flash, user, clock):
        world = World(client, auth, None)
        review_days(world, 3)
        clock(2026, 10, 21)
        send(client, auth, detection("PURCHASE", 3200, at=ms(2026, 10, 20, 12, 0), app=FLASH, merchant="RESTAURANTE"))
        clock(2026, 10, 24)
        assert world.call("get", "/api/review")["count"] == 0
        [decision] = decisions(world, "auto_confirm")
        world.call("post", f"/api/review/auto/{decision['id']}/undo")
        assert world.call("get", "/api/review")["count"] == 1
        clock(2026, 10, 30)
        assert world.call("get", "/api/review")["count"] == 1
        assert user

    def test_decisions_are_per_user(self, client, auth, flash, other_user, clock):
        world = World(client, auth, None)
        review_days(world, 3)
        clock(2026, 10, 21)
        send(client, auth, detection("PURCHASE", 3200, at=ms(2026, 10, 20, 12, 0), app=FLASH, merchant="RESTAURANTE"))
        clock(2026, 10, 24)
        world.call("get", "/api/review")
        [decision] = decisions(world, "auto_confirm")
        [row] = rows_of("auto_decisions", "id = ?", (decision["id"],))
        assert row["user_id"] != other_user["id"]
