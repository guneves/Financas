"""Quem fala e do que: a porta das notificacoes (docs/notifications-pluggy-design.md
§4, dono 2026-11-04; services/inbox.py `notification_wanted()` e o interruptor
`bank_notifications`).

O que estes testes protegem:

- Itau, BB e BTG Banking mandam todo tipo que o parser reconhece, e gravam na
  hora; o app da BTG Investimentos so o Pix/TED (a ordem, o provento, a
  aplicacao sao da Pluggy), e a transferencia vira a da Corretora;
- o Samsung Wallet so fala do cartao do Flash; um app desconhecido nunca;
- as palavras de investimento barram um Pix/TED e tudo da corretora, nunca o
  estabelecimento de uma compra no cartao ("FUNDO DE QUINTAL BAR");
- o interruptor desligado (Ajustes > Avisos dos bancos, ou o padrao do
  ambiente): so o Flash passa, e o banco nao deixa rastro, nem de um APK velho,
  para que ligar de novo nao grave avisos velhos;
- a compra do Flash (app, ou Samsung Wallet "Card used for Meal and Voucher")
  grava na hora na conta do Flash, a revisar;
- o aviso de credito do Flash (o deposito do beneficio) nao grava: a receita e
  digitada pelo dono;
- Samsung e app do Flash da mesma compra sao uma linha, nas duas ordens;
- a negativa do app do Flash desfaz a compra que o Samsung gravou, se intocada;
- o freio de emergencia volta ao Aprovar; `ignore_notifications` nao existe mais
  para escrita e so se le como true (APK antigo).

Nada aqui usa `any_bank_notifications`: ele pula a porta.
"""

import importlib
import time

import pytest

from open_finance_world import World, fake_pluggy, open_finance_module  # noqa: F401
from test_inbox import BB, ITAU, SAMSUNG, create_account, detection, ms, send
from test_open_finance_auto import meupluggy

FLASH = "br.com.flashapp"
BTG = "com.btg.pactual.banking"
BTG_INVEST = "com.btg.pactual.digital.mobile"
MEAL = "Card used for Meal and Voucher"
INBOX_SETTINGS = "/api/inbox/settings"
ALL_KINDS = ["CREDIT_PURCHASE", "DEBIT_PURCHASE", "PURCHASE", "PIX_OUT", "TRANSFER_OUT", "PIX_IN", "TRANSFER_IN",
             "REFUND", "DECLINED"]
MOVEMENTS = ["PIX_OUT", "TRANSFER_OUT", "PIX_IN", "TRANSFER_IN"]


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


def bank_switch(client, auth, value):
    response = client.patch(INBOX_SETTINGS, json={"bank_notifications": value}, headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()["bank_notifications"] is value


def nothing_left(client, auth, user_id):
    assert pending(client, auth) == [] and rows(client, auth) == [] and cards(client, auth) == []
    assert notify_rows(user_id) == []


@pytest.fixture()
def flash(client, auth):
    """Conta e cartao so debito do Flash, a conta e o cartao do Itau ao lado, e
    o gravar sozinho ligado. Devolve o id da conta do Flash."""
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


def wanted(**detection_fields):
    inbox = importlib.import_module("services.inbox")
    return inbox.notification_wanted({"merchant": None, "counterparty": None, **detection_fields})


class TestThePolicyTable:
    @pytest.mark.parametrize("app", [ITAU, BB, BTG])
    @pytest.mark.parametrize("kind", ALL_KINDS)
    def test_a_bank_app_sends_every_kind(self, client, auth, user, flash, app, kind):
        [result] = send(client, auth, detection(kind, 4590, app=app, counterparty="Fulano"))
        assert result["status"] != "ignored"
        assert notify_rows(user["id"]) != []

    def test_an_itau_debit_purchase_is_recorded_at_once(self, client, auth, flash):
        itau = next(row["id"] for row in client.get("/api/accounts", headers=auth).get_json() if row["name"] == "Itaú")
        send(client, auth, detection("DEBIT_PURCHASE", 4590, app=ITAU))
        [row] = rows(client, auth)
        assert (row["type"], row["account_id"], row["amount"], row["needs_review"]) == ("EXPENSE", itau, 45.9, 1)

    @pytest.mark.parametrize("kind", ["CREDIT_PURCHASE", "DEBIT_PURCHASE", "PURCHASE", "REFUND", "DECLINED"])
    def test_the_brokerage_app_never_sends_anything_but_a_transfer(self, client, auth, user, flash, kind):
        [result] = send(client, auth, detection(kind, 123400, app=BTG_INVEST, merchant="PETR4"))
        assert (result["status"], result["item_id"]) == ("ignored", None)
        nothing_left(client, auth, user["id"])

    def test_a_brokerage_order_is_ignored(self, client, auth, user, flash):
        [result] = send(client, auth, detection("PURCHASE", 123400, app=BTG_INVEST,
                                                merchant="Sua ordem de compra de PETR4 foi executada"))
        assert result["status"] == "ignored"
        nothing_left(client, auth, user["id"])

    @pytest.mark.parametrize("kind", MOVEMENTS)
    def test_the_brokerage_app_sends_transfers(self, kind):
        assert wanted(app=BTG_INVEST, kind=kind)

    @pytest.mark.parametrize("counterparty", ["Resgate CDB", "Dividendo PETR4", "JCP ITSA4", "Aplicação Tesouro Direto"])
    def test_an_investment_transfer_of_the_brokerage_app_is_ignored(self, counterparty):
        assert not wanted(app=BTG_INVEST, kind="TRANSFER_IN", counterparty=counterparty)

    def test_a_transfer_into_the_brokerage_is_a_transfer_into_the_corretora(self, client, auth, fake_pluggy):
        world = World(client, auth, fake_pluggy)
        assert client.patch(INBOX_SETTINGS, json={"auto_record": True}, headers=auth).status_code == 200
        made = meupluggy(world)
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        [result] = send(client, auth, detection("TRANSFER_IN", 50000, at=ms(2026, 10, 22, 9, 0), app=BTG_INVEST,
                                                merchant=None))
        assert result["status"] != "ignored"
        [row] = [row for row in world.transactions() if row["amount"] == 500.0]
        assert (row["type"], row["transfer_account_id"]) == ("TRANSFER", made["corretora"])

    @pytest.mark.parametrize("card_name", ["BTG Pactual Banking", "Itaú Visa", "Ourocard", None])
    @pytest.mark.parametrize("kind", ["PURCHASE", "CREDIT_PURCHASE", "DEBIT_PURCHASE"])
    def test_another_card_on_samsung_is_ignored(self, client, auth, user, flash, card_name, kind):
        extra = {"card_name": card_name} if card_name else {}
        [result] = send(client, auth, detection(kind, 4590, app=SAMSUNG, **extra))
        assert result["status"] == "ignored"
        nothing_left(client, auth, user["id"])

    @pytest.mark.parametrize("app", ["com.android.shell", "com.nu.production", "com.whatsapp"])
    @pytest.mark.parametrize("kind", ["PURCHASE", "PIX_OUT", "PIX_IN"])
    def test_an_unknown_app_is_ignored(self, client, auth, user, flash, app, kind):
        [result] = send(client, auth, detection(kind, 4590, app=app, counterparty="Fulano"))
        assert result["status"] == "ignored"
        nothing_left(client, auth, user["id"])

    def test_a_bank_app_claiming_to_be_flash_follows_the_bank_rules(self):
        """O emissor que o APK manda nao faz do Itau o Flash: o credito passa
        (o Flash nunca manda CREDIT_PURCHASE)."""
        assert wanted(app=ITAU, kind="CREDIT_PURCHASE", issuer="flash", card_name=MEAL)
        assert not wanted(app=FLASH, kind="CREDIT_PURCHASE")


class TestInvestmentWords:
    @pytest.mark.parametrize("app", [ITAU, BB, BTG])
    @pytest.mark.parametrize("counterparty", [
        "TESOURO DIRETO", "Aplicação CDB", "Resgate LCI", "LCA BTG", "Fundo de Investimento XP", "Provento",
        "dividendos",
    ])
    def test_a_pix_to_an_investment_is_ignored(self, app, counterparty):
        assert not wanted(app=app, kind="PIX_OUT", counterparty=counterparty)
        assert not wanted(app=app, kind="TRANSFER_IN", merchant=counterparty)

    def test_the_tesouro_direto_pix_leaves_no_trace(self, client, auth, user, flash):
        [result] = send(client, auth, detection("PIX_OUT", 10000, app=ITAU, merchant=None, counterparty="TESOURO DIRETO"))
        assert result["status"] == "ignored"
        nothing_left(client, auth, user["id"])

    @pytest.mark.parametrize("merchant", ["FUNDO DE QUINTAL BAR", "TESOURO DO MAR RESTAURANTE", "RESGATE PET SHOP",
                                          "CDB MOTOS"])
    @pytest.mark.parametrize("kind", ["CREDIT_PURCHASE", "DEBIT_PURCHASE", "PURCHASE"])
    def test_a_card_purchase_merchant_is_never_an_investment(self, merchant, kind):
        assert wanted(app=ITAU, kind=kind, merchant=merchant)

    def test_a_card_purchase_at_fundo_de_quintal_is_recorded(self, client, auth, flash):
        send(client, auth, detection("DEBIT_PURCHASE", 8900, app=ITAU, merchant="FUNDO DE QUINTAL BAR"))
        [row] = rows(client, auth)
        assert (row["type"], row["description"]) == ("EXPENSE", "FUNDO DE QUINTAL BAR")

    @pytest.mark.parametrize("counterparty", ["Fulano Fundo", "Ordem Silva", "Tesouro do Mar Ltda", "Jcpenha"])
    def test_a_word_inside_a_name_is_not_an_investment(self, counterparty):
        """Fronteira de palavra, e so as expressoes inteiras ("tesouro direto",
        "fundo de investimento", "ordem de compra")."""
        assert wanted(app=ITAU, kind="PIX_OUT", counterparty=counterparty)

    def test_rende_facil_stays_ignored(self, client, auth, user, flash):
        [result] = send(client, auth, detection("PIX_OUT", 10000, app=BB, merchant="RENDE FACIL"))
        assert result["status"] == "ignored"
        nothing_left(client, auth, user["id"])


class TestTheSwitch:
    def test_on_by_default_and_patch_takes_booleans_only(self, client, auth):
        assert client.get(INBOX_SETTINGS, headers=auth).get_json()["bank_notifications"] is True
        for bad in ("false", 0, None, "1"):
            assert client.patch(INBOX_SETTINGS, json={"bank_notifications": bad}, headers=auth).status_code == 400
        assert client.get(INBOX_SETTINGS, headers=auth).get_json()["bank_notifications"] is True
        bank_switch(client, auth, False)
        assert client.get(INBOX_SETTINGS, headers=auth).get_json()["bank_notifications"] is False
        bank_switch(client, auth, True)

    def test_it_is_per_user(self, client, auth, other_user):
        bank_switch(client, auth, False)
        assert client.get(INBOX_SETTINGS, headers=other_user["headers"]).get_json()["bank_notifications"] is True

    @pytest.mark.parametrize("app", [ITAU, BB, BTG, BTG_INVEST])
    @pytest.mark.parametrize("kind", ["PURCHASE", "DEBIT_PURCHASE", "PIX_OUT", "TRANSFER_IN", "DECLINED"])
    def test_off_a_bank_leaves_no_trace(self, client, auth, user, flash, app, kind):
        """Tambem o APK velho, que manda a compra do banco sem perguntar."""
        bank_switch(client, auth, False)
        [result] = send(client, auth, detection(kind, 4590, app=app, counterparty="Fulano"))
        assert (result["status"], result["item_id"]) == ("ignored", None)
        nothing_left(client, auth, user["id"])

    def test_off_the_flash_still_passes(self, client, auth, flash):
        bank_switch(client, auth, False)
        send(client, auth, samsung_flash())
        send(client, auth, detection("PURCHASE", 1500, at=ms(2026, 10, 11, 12), app=FLASH, merchant="LANCHE"))
        assert sorted(row["account_id"] for row in rows(client, auth)) == [flash, flash]

    def test_turning_it_on_records_nothing_old(self, client, auth, user, flash):
        bank_switch(client, auth, False)
        send(client, auth, detection("DEBIT_PURCHASE", 4590, app=ITAU))
        bank_switch(client, auth, True)
        nothing_left(client, auth, user["id"])
        send(client, auth, detection("DEBIT_PURCHASE", 4590, app=ITAU))
        assert len(rows(client, auth)) == 1

    def test_the_environment_default_off(self, client, auth, user, flash, monkeypatch):
        inbox = importlib.import_module("services.inbox")
        monkeypatch.setattr(inbox, "BANK_NOTIFICATIONS_DEFAULT", False)
        assert client.get(INBOX_SETTINGS, headers=auth).get_json()["bank_notifications"] is False
        [result] = send(client, auth, detection("DEBIT_PURCHASE", 4590, app=ITAU))
        assert result["status"] == "ignored"
        nothing_left(client, auth, user["id"])
        bank_switch(client, auth, True)
        send(client, auth, detection("DEBIT_PURCHASE", 4590, app=ITAU))
        assert len(rows(client, auth)) == 1

    def test_the_environment_default_on(self, client, auth, flash, monkeypatch):
        inbox = importlib.import_module("services.inbox")
        monkeypatch.setattr(inbox, "BANK_NOTIFICATIONS_DEFAULT", True)
        assert client.get(INBOX_SETTINGS, headers=auth).get_json()["bank_notifications"] is True
        send(client, auth, detection("DEBIT_PURCHASE", 4590, app=ITAU))
        assert len(rows(client, auth)) == 1


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

    def test_a_row_the_owner_only_reviewed_is_undone(self, client, auth, flash):
        # Fase 4: "intocado" e o snapshot; o "e meu" nao protege uma compra negada.
        now = int(time.time() * 1000)
        send(client, auth, samsung_flash(at=now))
        [row] = rows(client, auth)
        client.post("/api/review", json={"items": [{"table": "transactions", "id": row["id"]}]}, headers=auth)
        send(client, auth, self.declined(now + 5000))
        assert rows(client, auth) == []

    def test_a_row_the_owner_recategorised_stays(self, client, auth, flash):
        now = int(time.time() * 1000)
        send(client, auth, samsung_flash(at=now))
        [row] = rows(client, auth)
        categories = {entry["name"]: entry["id"] for entry in client.get("/api/categories", headers=auth).get_json()
                      if not entry.get("parent_id")}
        client.post("/api/review", json={"items": [{"table": "transactions", "id": row["id"],
                                                    "category_id": categories["Lazer"]}]}, headers=auth)
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
