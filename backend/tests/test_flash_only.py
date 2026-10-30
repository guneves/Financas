"""Open Finance e a unica fonte dos bancos; o celular so fala do Flash
(dono, 2026-10-30, services/inbox.py `notification_wanted()`).

O que estes testes protegem:

- qualquer aviso que nao seja do Flash responde `ignored`, nao deixa item nem
  deteccao, com ou sem mapeamento e seja qual for a preferencia antiga: um APK
  velho continua mandando tudo;
- a compra do Flash (app, ou Samsung Wallet "Card used for Meal and Voucher")
  grava na hora na conta do Flash, a revisar: nenhum banco vai avisar dela;
- o aviso de credito do Flash (o deposito do beneficio) nao grava: a receita e
  digitada pelo dono;
- Samsung e app do Flash da mesma compra sao uma linha, nas duas ordens;
- a negativa do app do Flash desfaz a compra que o Samsung gravou, se intocada;
- o freio de emergencia volta ao Aprovar; `ignore_notifications` nao existe mais
  para escrita e so se le como true (APK antigo).
"""

import importlib
import time

import pytest

from open_finance_world import World, connected, fake_pluggy, open_finance_module  # noqa: F401
from test_inbox import BB, ITAU, SAMSUNG, create_account, detection, ms, send

FLASH = "br.com.flashapp"
BTG = "com.btg.pactual.banking"
BTG_INVEST = "com.btg.pactual.digital.mobile"
MEAL = "Card used for Meal and Voucher"
INBOX_SETTINGS = "/api/inbox/settings"


def notify_rows(user_id):
    db = importlib.import_module("db")
    with db.get_db() as conn:
        return conn.execute("SELECT * FROM notify_detections WHERE user_id = ?", (user_id,)).fetchall()


def pending(client, auth):
    return client.get("/api/inbox", headers=auth).get_json()["items"]


def rows(client, auth):
    return client.get("/api/transactions", headers=auth).get_json()


def cards(client, auth):
    return client.get("/api/cc-expenses", headers=auth).get_json()


def samsung_flash(amount=3200, at=None, **extra):
    return detection("PURCHASE", amount, at=at or int(time.time() * 1000), app=SAMSUNG, card_name=MEAL, **extra)


@pytest.fixture()
def flash(client, auth):
    """Conta e cartao so debito do Flash, um cartao de banco ao lado, e o gravar
    sozinho ligado. Devolve o id da conta do Flash."""
    account = create_account(client, auth, "Flash")
    create_account(client, auth, "Itaú")
    assert client.post(
        "/api/credit-cards",
        json={"name": "Flash", "credit_enabled": False, "debit_account_id": account}, headers=auth,
    ).status_code == 201
    assert client.post(
        "/api/credit-cards", json={"name": "Itaú Visa", "due_day": 10, "closing_day": 3}, headers=auth,
    ).status_code == 201
    assert client.patch(INBOX_SETTINGS, json={"auto_record": True}, headers=auth).status_code == 200
    return account


class TestOnlyFlashPasses:
    @pytest.mark.parametrize("app", [ITAU, BB, BTG, BTG_INVEST, "com.android.shell", "com.nu.production"])
    @pytest.mark.parametrize("kind", ["CREDIT_PURCHASE", "DEBIT_PURCHASE", "PURCHASE", "PIX_OUT", "PIX_IN", "DECLINED"])
    def test_a_bank_is_ignored_and_leaves_no_trace(self, client, auth, user, flash, app, kind):
        [result] = send(client, auth, detection(kind, 4590, app=app, counterparty="Fulano"))
        assert (result["status"], result["item_id"]) == ("ignored", None)
        assert pending(client, auth) == [] and rows(client, auth) == [] and cards(client, auth) == []
        assert notify_rows(user["id"]) == []

    @pytest.mark.parametrize("card_name", ["BTG Pactual Banking", "Itaú Visa", None])
    def test_another_card_on_samsung_is_ignored(self, client, auth, flash, card_name):
        extra = {"card_name": card_name} if card_name else {}
        [result] = send(client, auth, detection("PURCHASE", 4590, app=SAMSUNG, **extra))
        assert result["status"] == "ignored"
        assert rows(client, auth) == [] and cards(client, auth) == []

    def test_a_bank_app_claiming_to_be_flash_is_ignored(self, client, auth, flash):
        [result] = send(client, auth, detection("PURCHASE", 4590, app=ITAU, issuer="flash", card_name=MEAL))
        assert result["status"] == "ignored"

    def test_it_does_not_depend_on_the_old_setting_or_on_a_mapping(self, client, auth, user, fake_pluggy):
        inbox = importlib.import_module("services.inbox")
        db = importlib.import_module("db")
        with db.get_db() as conn:
            inbox.save_setting(conn, user["id"], "open_finance_ignore_notifications", "0")
        [result] = send(client, auth, detection("DEBIT_PURCHASE", 4590, app=ITAU))
        assert result["status"] == "ignored"
        world = World(client, auth, fake_pluggy)
        connected(world, connector_name="Itaú")
        [result] = send(client, auth, detection("DEBIT_PURCHASE", 4590, app=ITAU))
        assert result["status"] == "ignored"
        assert world.pending() == []

    def test_a_resend_is_still_ignored(self, client, auth, flash):
        sent = detection("PIX_OUT", 4590, app=ITAU)
        assert [send(client, auth, sent)[0]["status"] for _ in range(2)] == ["ignored", "ignored"]


class TestFlashRecordsAtOnce:
    def test_samsung_alone_does_not_wait(self, client, auth, user, flash):
        body = client.post("/api/inbox/detections", json={"detections": [samsung_flash()]}, headers=auth).get_json()
        assert body["auto_recorded"] == {"recorded": 1, "linked": 0, "held": 0}
        [row] = rows(client, auth)
        assert (row["type"], row["account_id"], row["amount"], row["needs_review"]) == ("EXPENSE", flash, 32.0, 1)
        assert pending(client, auth) == [] and cards(client, auth) == []

    def test_the_flash_app(self, client, auth, flash):
        send(client, auth, detection("PURCHASE", 3200, app=FLASH, merchant="RESTAURANTE"))
        [row] = rows(client, auth)
        assert (row["account_id"], row["description"], row["needs_review"]) == (flash, "RESTAURANTE", 1)

    def test_a_debit_notice_of_the_flash_app(self, client, auth, flash):
        send(client, auth, detection("DEBIT_PURCHASE", 3200, app=FLASH))
        [row] = rows(client, auth)
        assert (row["type"], row["account_id"]) == ("EXPENSE", flash)

    def test_samsung_then_the_app_is_one_row(self, client, auth, flash):
        now = int(time.time() * 1000)
        send(client, auth, samsung_flash(at=now))
        [result] = send(client, auth, detection("PURCHASE", 3200, at=now + 5000, app=FLASH))
        assert result["status"] == "matched"
        assert len(rows(client, auth)) == 1

    def test_the_app_then_samsung_is_one_row(self, client, auth, flash):
        now = int(time.time() * 1000)
        send(client, auth, detection("PURCHASE", 3200, at=now, app=FLASH))
        send(client, auth, samsung_flash(at=now + 5000))
        assert len(rows(client, auth)) == 1

    def test_the_brake_sends_it_back_to_aprovar(self, client, auth, flash):
        client.patch(INBOX_SETTINGS, json={"auto_record": False}, headers=auth)
        send(client, auth, samsung_flash())
        assert rows(client, auth) == []
        assert len(pending(client, auth)) == 1


class TestFlashCreditIsTyped:
    @pytest.mark.parametrize("kind", ["PIX_IN", "TRANSFER_IN", "REFUND", "CREDIT_PURCHASE"])
    @pytest.mark.parametrize("source", [{"app": FLASH}, {"app": SAMSUNG, "card_name": MEAL}])
    def test_a_credit_notice_records_nothing(self, client, auth, user, flash, kind, source):
        [result] = send(client, auth, detection(kind, 50000, **source))
        assert result["status"] == "ignored"
        assert rows(client, auth) == [] and pending(client, auth) == [] and cards(client, auth) == []
        assert notify_rows(user["id"]) == []


class TestDeclined:
    def declined(self, at):
        return detection("DECLINED", 3200, at=at, app=FLASH)

    def test_the_flash_app_undoes_what_samsung_recorded(self, client, auth, flash):
        now = int(time.time() * 1000)
        send(client, auth, samsung_flash(at=now))
        assert len(rows(client, auth)) == 1
        [result] = send(client, auth, self.declined(now + 5000))
        assert result["status"] == "declined"
        assert rows(client, auth) == [] and pending(client, auth) == []
        assert client.get("/api/review", headers=auth).get_json()["count"] == 0

    def test_in_the_same_batch_nothing_is_recorded(self, client, auth, flash):
        now = int(time.time() * 1000)
        send(client, auth, samsung_flash(at=now), self.declined(now + 5000))
        assert rows(client, auth) == []

    def test_a_row_the_owner_reviewed_stays(self, client, auth, flash):
        now = int(time.time() * 1000)
        send(client, auth, samsung_flash(at=now))
        [row] = rows(client, auth)
        client.post("/api/review", json={"items": [{"table": "transactions", "id": row["id"]}]}, headers=auth)
        send(client, auth, self.declined(now + 5000))
        assert len(rows(client, auth)) == 1

    def test_another_users_decline_does_not_touch_it(self, client, auth, flash, other_user):
        now = int(time.time() * 1000)
        send(client, auth, samsung_flash(at=now))
        send(client, other_user["headers"], self.declined(now + 5000))
        assert len(rows(client, auth)) == 1


class TestTheOldSetting:
    def test_get_says_true_and_patch_refuses(self, client, auth, fake_pluggy):
        settings = "/api/open-finance/settings"
        assert client.get(settings, headers=auth).get_json()["ignore_notifications"] is True
        assert client.patch(settings, json={"ignore_notifications": False}, headers=auth).status_code == 400
