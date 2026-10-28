"""Gravar sozinho e revisar (045, services/auto_record.py, services/review.py).

O que estes testes protegem:

- a notificacao (Flash e todos os bancos) vira lancamento na hora, sem
  Aprovar, e nasce a revisar; o que ela nao sabe vira palpite (o cartao do
  emissor, a conta padrao), nunca uma espera;
- so espera: o aviso do Samsung sem o do banco (NOTIFY_WINDOW_MS) e a
  transferencia entre contas do dono com uma ponta so; o interruptor desligado
  volta ao Aprovar;
- o que o dono ja digitou e ligado, nunca duplicado, e nao pede revisao;
- a Pluggy confere o que a notificacao gravou: mesmo movimento, a transacao
  so se liga (origem OPEN_FINANCE); outra data ou outro cartao, o lancamento
  intocado e refeito do jeito do banco; revisado, fica; o banco que lanca
  ate 5 dias depois do aviso e o mesmo movimento, nunca um segundo; o BB, que
  arredonda o valor para cima (18,19 -> 19,00), tambem;
- revisar: confirma e (opcional) troca a categoria, na compra todas as
  parcelas; lote tudo ou nada; user_id;
- as compras no cartao no Extrato: uma linha por compra, com os filtros.
"""

import importlib
import time

import pytest

from open_finance_world import World, bank_tx, card_tx, connected, fake_pluggy, open_finance_module  # noqa: F401
from test_inbox import ITAU, SAMSUNG, create_account, create_card, detection, ms, send

FLASH = "br.com.flashapp"
INBOX_SETTINGS = "/api/inbox/settings"


def notifications_on(client, auth):
    response = client.patch(INBOX_SETTINGS, json={"auto_record": True}, headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()["auto_record"] is True


def pending(client, auth):
    return client.get("/api/inbox", headers=auth).get_json()["items"]


def transactions(client, auth, **params):
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return client.get(f"/api/transactions{'?' + query if query else ''}", headers=auth).get_json()


def card_rows(client, auth):
    return client.get("/api/cc-expenses", headers=auth).get_json()


def review_queue(client, auth):
    response = client.get("/api/review", headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def confirm(client, auth, *items, expected=200):
    response = client.post("/api/review", json={"items": list(items)}, headers=auth)
    assert response.status_code == expected, response.get_data(as_text=True)
    return response.get_json()


def category_id(client, auth, name):
    for category in client.get("/api/categories", headers=auth).get_json():
        if category["name"] == name:
            return category["id"]
    response = client.post("/api/categories", json={"name": name, "kind": "EXPENSE"}, headers=auth)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["id"]


@pytest.fixture()
def auto(client, auth):
    notifications_on(client, auth)


# ---------------------------------------------------------------------------
# A notificacao vira lancamento
# ---------------------------------------------------------------------------

class TestNotificationsRecordAlone:
    def test_a_credit_purchase_is_a_card_purchase_at_once(self, client, auth, auto):
        card = create_card(client, auth, "Itaú Visa")
        response = client.post("/api/inbox/detections", json={"detections": [detection()]}, headers=auth)
        assert response.get_json()["auto_recorded"] == {"recorded": 1, "linked": 0, "held": 0}
        [row] = card_rows(client, auth)
        assert (row["card_id"], row["amount"], row["purchase_date"], row["needs_review"]) == (card, 45.9, "2026-10-10", 1)
        assert pending(client, auth) == []

    def test_a_flash_purchase_is_recorded_too(self, client, auth, auto):
        flash_account = create_account(client, auth, "Flash")
        response = client.post(
            "/api/credit-cards",
            json={"name": "Flash", "due_day": 10, "closing_day": 3, "credit_enabled": False,
                  "debit_account_id": flash_account},
            headers=auth,
        )
        assert response.status_code == 201, response.get_data(as_text=True)
        send(client, auth, detection("PURCHASE", 3200, app=FLASH, merchant="RESTAURANTE"))
        [row] = transactions(client, auth)
        assert (row["type"], row["account_id"], row["amount"], row["needs_review"]) == ("EXPENSE", flash_account, 32.0, 1)

    def test_two_cards_of_the_bank_take_the_first_and_wait_for_review(self, client, auth, auto):
        first = create_card(client, auth, "Itaú Azul")
        create_card(client, auth, "Itaú Platinum")
        send(client, auth, detection())
        [row] = card_rows(client, auth)
        assert (row["card_id"], row["needs_review"]) == (first, 1)
        # Ambiguo: nada fica lembrado (o proximo tambem e palpite).
        assert client.get("/api/inbox/hints", headers=auth).get_json() == []

    def test_a_pix_with_no_account_known_goes_to_the_default_account(self, client, auth, auto):
        create_account(client, auth, "Nubank")
        create_account(client, auth, "Caixa")
        send(client, auth, detection("PIX_OUT", 1500, counterparty="Fulano de Tal"))
        [row] = transactions(client, auth)
        default = next(account for account in client.get("/api/accounts", headers=auth).get_json() if account["is_default"])
        assert (row["type"], row["account_id"], row["needs_review"]) == ("EXPENSE", default["id"], 1)

    def test_a_typed_look_alike_is_linked_not_duplicated(self, client, auth, auto):
        account = create_account(client, auth, "Itaú")
        typed = client.post(
            "/api/transactions",
            json={"amount": 45.9, "date": "2026-10-10", "type": "EXPENSE", "category": "Alimentação",
                  "account_id": account, "description": "padaria"},
            headers=auth,
        ).get_json()
        send(client, auth, detection("DEBIT_PURCHASE"))
        [row] = transactions(client, auth)
        assert (row["id"], row["needs_review"]) == (typed["id"], 0)

    def test_the_same_notification_twice_is_one_row(self, client, auth, auto):
        create_card(client, auth)
        sent = detection()
        send(client, auth, sent)
        send(client, auth, sent)
        assert len(card_rows(client, auth)) == 1

    def test_switched_off_it_waits_in_aprovar(self, client, auth):
        create_card(client, auth)
        response = client.patch(INBOX_SETTINGS, json={"auto_record": False}, headers=auth)
        assert response.get_json()["auto_record"] is False
        send(client, auth, detection())
        assert card_rows(client, auth) == []
        assert len(pending(client, auth)) == 1

    def test_turning_it_on_records_what_was_waiting(self, client, auth):
        create_card(client, auth)
        send(client, auth, detection())
        assert len(pending(client, auth)) == 1
        notifications_on(client, auth)
        assert pending(client, auth) == []
        assert len(card_rows(client, auth)) == 1

    def test_the_setting_refuses_anything_but_a_boolean(self, client, auth):
        response = client.patch(INBOX_SETTINGS, json={"auto_record": "sim"}, headers=auth)
        assert response.status_code == 400

    def test_another_user_is_not_touched(self, client, auth, auto, other_user):
        create_card(client, other_user["headers"])
        send(client, other_user["headers"], detection())
        assert card_rows(client, other_user["headers"]) == []
        assert len(pending(client, other_user["headers"])) == 1


class TestWhatWaits:
    def test_samsung_alone_waits_for_the_bank_then_records(self, client, auth, auto, user):
        create_card(client, auth)
        now = int(time.time() * 1000)
        send(client, auth, detection("PURCHASE", 4590, at=now, app=SAMSUNG, card_name="Itaú Visa"))
        assert card_rows(client, auth) == []
        auto_record = importlib.import_module("services.auto_record")
        db = importlib.import_module("db")
        inbox = importlib.import_module("services.inbox")
        with db.get_db() as conn:
            counts = auto_record.record_notifications(conn, user["id"], now_ms=now + inbox.NOTIFY_WINDOW_MS + 1)
        assert counts["recorded"] == 1
        assert len(card_rows(client, auth)) == 1

    def test_samsung_then_the_bank_is_one_row_with_the_banks_words(self, client, auth, auto):
        create_card(client, auth)
        now = int(time.time() * 1000)
        send(client, auth, detection("PURCHASE", 4590, at=now, app=SAMSUNG, merchant="Padaria"))
        send(client, auth, detection("CREDIT_PURCHASE", 4590, at=now + 5000, merchant="PADARIA BOM PAO"))
        [row] = card_rows(client, auth)
        assert row["description"] == "PADARIA BOM PAO"

    def test_the_bank_then_samsung_is_one_row(self, client, auth, auto):
        create_card(client, auth)
        send(client, auth, detection("CREDIT_PURCHASE", 4590, at=ms(2026, 10, 10, 14, 0)))
        send(client, auth, detection("PURCHASE", 4590, at=ms(2026, 10, 10, 14, 1), app=SAMSUNG))
        assert len(card_rows(client, auth)) == 1

    def test_an_own_transfer_waits_for_the_other_side_then_is_one_transfer(self, client, auth, auto):
        itau = create_account(client, auth, "Itaú")
        bb = create_account(client, auth, "Banco do Brasil")
        send(client, auth, detection("PIX_OUT", 50000, at=ms(2026, 10, 10, 9, 0), counterparty="Fulano Dono"))
        # Saida sem a entrada ainda: um Pix comum (pode ser de outra pessoa).
        [first] = transactions(client, auth)
        assert first["type"] == "EXPENSE"
        client.delete(f"/api/transactions/{first['id']}", headers=auth)
        # As duas pontas no mesmo envio: uma transferencia.
        send(
            client, auth,
            detection("PIX_OUT", 70000, at=ms(2026, 10, 11, 9, 0), counterparty="Fulano Dono"),
            detection("PIX_IN", 70000, at=ms(2026, 10, 11, 9, 1), app="br.com.bb.android", counterparty="Fulano Dono"),
        )
        rows = [row for row in transactions(client, auth) if row["amount"] == 700.0]
        assert [(row["type"], row["account_id"], row["transfer_account_id"]) for row in rows] == [("TRANSFER", itau, bb)]


# ---------------------------------------------------------------------------
# A Pluggy confere o que a notificacao gravou
# ---------------------------------------------------------------------------

@pytest.fixture()
def world(client, auth, fake_pluggy):
    notifications_on(client, auth)
    response = client.patch("/api/open-finance/settings", json={"auto_record": True}, headers=auth)
    world = World(client, auth, fake_pluggy)
    world.auto_response = response
    return world


def rows_of(table, where="1=1", params=()):
    db = importlib.import_module("db")
    with db.get_db() as conn:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table} WHERE {where}", params).fetchall()]


class TestPluggyReconciles:
    def test_same_movement_links_silently(self, world, user):
        item_id, _p, made = connected(world, connector_name="Itaú")
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        mine = made["bank"][2]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 4590, at=ms(2026, 10, 20, 14, 32), app=ITAU))
        [before] = world.transactions(mine)
        pluggy_id = world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20", "COMPRA CARTAO DEB PADARIA"))
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert after["id"] == before["id"]
        assert (after["source_type"], after["source_id"], after["needs_review"]) == ("OPEN_FINANCE", pluggy_id, 1)
        [of_row] = rows_of("open_finance_transactions", "user_id = ? AND pluggy_transaction_id = ?", (user["id"], pluggy_id))
        assert (of_row["role"], of_row["target_id"]) == ("SOURCE", before["id"])
        assert world.pending() == []

    def test_another_date_redoes_the_untouched_row_the_banks_way(self, world):
        item_id, _p, made = connected(world, connector_name="Itaú")
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        mine = made["bank"][2]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 4590, at=ms(2026, 10, 20, 23, 50), app=ITAU))
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-21", "COMPRA CARTAO DEB PADARIA"))
        world.sync(item_id)
        [row] = world.transactions(mine)
        assert (row["date"], row["source_type"], row["needs_review"]) == ("2026-10-21", "OPEN_FINANCE", 1)

    def test_another_card_moves_the_purchase(self, world):
        item_id, _p, made = connected(world, connector_name="Itaú", bank=False, card=True)
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        mapped = made["card"][2]
        guessed = world.card("Itaú Azul")
        assert guessed != mapped
        send(world.client, world.auth, detection("CREDIT_PURCHASE", 8990, at=ms(2026, 10, 22, 9, 0), app=ITAU))
        before = [row["card_id"] for row in world.call("get", "/api/cc-expenses")]
        assert len(before) == 1
        world.fake.add_tx(made["card"][0], card_tx(89.9, "2026-10-22", "SMART FIT", docs_sign=True))
        world.sync(item_id)
        [row] = world.call("get", "/api/cc-expenses")
        assert (row["card_id"], row["amount"], row["needs_review"]) == (mapped, 89.9, 1)

    def test_a_reviewed_row_is_never_redone(self, world):
        item_id, _p, made = connected(world, connector_name="Itaú")
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        mine = made["bank"][2]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 4590, at=ms(2026, 10, 20, 23, 50), app=ITAU))
        [row] = world.transactions(mine)
        confirm(world.client, world.auth, {"table": "transactions", "id": row["id"]})
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-21"))
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert (after["id"], after["date"], after["needs_review"]) == (row["id"], "2026-10-20", 0)

    def test_the_bank_posting_days_later_is_the_same_movement(self, world):
        # O debito do fim de semana: o aviso no sabado, o banco na segunda.
        item_id, _p, made = connected(world, connector_name="Itaú")
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        mine = made["bank"][2]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 4590, at=ms(2026, 10, 17, 14, 0), app=ITAU))
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20", "COMPRA CARTAO DEB PADARIA"))
        world.sync(item_id)
        [row] = world.transactions(mine)
        assert (row["date"], row["source_type"], row["needs_review"]) == ("2026-10-20", "OPEN_FINANCE", 1)
        assert world.pending() == []

    def test_a_reviewed_row_posted_days_later_is_only_linked(self, world, user):
        item_id, _p, made = connected(world, connector_name="Itaú")
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        mine = made["bank"][2]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 4590, at=ms(2026, 10, 17, 14, 0), app=ITAU))
        [row] = world.transactions(mine)
        confirm(world.client, world.auth, {"table": "transactions", "id": row["id"]})
        pluggy_id = world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert (after["id"], after["date"]) == (row["id"], "2026-10-17")
        [of_row] = rows_of("open_finance_transactions", "user_id = ? AND pluggy_transaction_id = ?", (user["id"], pluggy_id))
        assert (of_row["role"], of_row["target_id"]) == ("MATCHED", row["id"])

    def test_a_week_later_is_another_purchase(self, world):
        item_id, _p, made = connected(world, connector_name="Itaú")
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        mine = made["bank"][2]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 4590, at=ms(2026, 10, 13, 14, 0), app=ITAU))
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20", "COMPRA CARTAO DEB PADARIA"))
        world.sync(item_id)
        assert sorted(row["date"] for row in world.transactions(mine)) == ["2026-10-13", "2026-10-20"]

    def test_the_same_amount_on_the_notified_day_keeps_its_pair(self, world):
        # Duas compras iguais, so a primeira avisou: cada linha do banco e uma.
        item_id, _p, made = connected(world, connector_name="Itaú")
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        mine = made["bank"][2]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 800, at=ms(2026, 10, 21, 8, 0), app=ITAU))
        world.fake.add_tx(made["bank"][0], bank_tx(-8, "2026-10-21", "CAFE"))
        world.fake.add_tx(made["bank"][0], bank_tx(-8, "2026-10-23", "CAFE"))
        world.sync(item_id)
        rows = world.transactions(mine)
        assert sorted(row["date"] for row in rows) == ["2026-10-21", "2026-10-23"]
        assert {row["source_type"] for row in rows} == {"OPEN_FINANCE"}

    def test_pluggy_alone_is_recorded_for_review(self, world):
        item_id, _p, made = connected(world)
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        world.fake.add_tx(made["bank"][0], bank_tx(-12, "2026-10-25", "PADARIA"))
        world.sync(item_id)
        [row] = world.transactions(made["bank"][2])
        assert row["needs_review"] == 1


BB = "br.com.bb.android"


class TestBancoDoBrasilRoundsUp:
    """O BB manda a Pluggy o valor arredondado para cima, em reais inteiros
    (dono, 2026-10-27: 18,19 chega 19,00). A notificacao tem os centavos."""

    def test_a_debit_notified_with_cents_is_the_same_movement(self, world, user):
        item_id, _p, made = connected(world, connector_name="Banco do Brasil")
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        mine = made["bank"][2]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 1819, at=ms(2026, 10, 21, 12, 0), app=BB))
        [before] = world.transactions(mine)
        pluggy_id = world.fake.add_tx(made["bank"][0], bank_tx(-19, "2026-10-21", "COMPRA COM CARTAO"))
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert (after["id"], after["amount"], after["source_type"]) == (before["id"], 18.19, "OPEN_FINANCE")
        [of_row] = rows_of("open_finance_transactions", "user_id = ? AND pluggy_transaction_id = ?", (user["id"], pluggy_id))
        assert (of_row["role"], of_row["target_id"]) == ("SOURCE", before["id"])

    def test_a_card_purchase_notified_with_cents_is_one_purchase(self, world):
        item_id, _p, made = connected(world, connector_name="Banco do Brasil", bank=False, card=True)
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        send(world.client, world.auth, detection("CREDIT_PURCHASE", 1819, at=ms(2026, 10, 22, 9, 0), app=BB))
        world.fake.add_tx(made["card"][0], card_tx(19, "2026-10-22", "LOJA", docs_sign=True))
        world.sync(item_id)
        [row] = world.call("get", "/api/cc-expenses")
        assert (row["card_id"], row["amount"]) == (made["card"][2], 18.19)

    def test_the_notification_after_the_bank_joins_its_item(self, world):
        # O celular ficou sem rede: a Pluggy (19,00) chegou antes do aviso (18,19).
        item_id, _p, made = connected(world, connector_name="Banco do Brasil")
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        mine = made["bank"][2]
        world.fake.add_tx(made["bank"][0], bank_tx(-19, "2026-10-21", "COMPRA COM CARTAO"))
        world.sync(item_id)
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 1819, at=ms(2026, 10, 21, 12, 0), app=BB))
        assert len(world.transactions(mine)) == 1

    def test_the_invoice_payment_links_to_the_apps_payment(self, world, user):
        item_id, _p, made = connected(world, connector_name="Banco do Brasil")
        pluggy_account, _of, mine = made["bank"]
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        payment = world.call("post", "/api/transactions", json={
            "account_id": mine, "amount": 18.19, "date": "2026-10-21", "type": "EXPENSE", "category": "Outros",
            "description": "Fatura",
        })["id"]
        db = importlib.import_module("db")
        with db.get_db() as conn:
            conn.execute("UPDATE transactions SET source_type = 'CC_INVOICE_PAYMENT', source_id = 'x' WHERE id = ?", (payment,))
        tx_id = world.fake.add_tx(pluggy_account, bank_tx(-19, "2026-10-21", "PAGAMENTO FATURA", category_id="05100000"))
        world.sync(item_id)
        assert [row["id"] for row in world.transactions(mine)] == [payment]
        [of_row] = rows_of("open_finance_transactions", "user_id = ? AND pluggy_transaction_id = ?", (user["id"], tx_id))
        assert (of_row["role"], of_row["target_id"]) == ("INVOICE_PAYMENT", payment)

    def test_another_bank_keeps_the_exact_cents(self, world):
        item_id, _p, made = connected(world, connector_name="Itaú")
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        mine = made["bank"][2]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 1819, at=ms(2026, 10, 21, 12, 0), app=ITAU))
        world.fake.add_tx(made["bank"][0], bank_tx(-19, "2026-10-21", "COMPRA COM CARTAO"))
        world.sync(item_id)
        assert sorted(row["amount"] for row in world.transactions(mine)) == [18.19, 19.0]


def test_pluggy_is_on_by_default_when_the_owner_never_chose(client, auth, fake_pluggy, monkeypatch):
    open_finance_auto = importlib.import_module("services.open_finance_auto")
    auto_record = importlib.import_module("services.auto_record")
    monkeypatch.setattr(open_finance_auto, "AUTO_RECORD_DEFAULT", True)
    monkeypatch.setattr(auto_record, "AUTO_RECORD_DEFAULT", True)
    assert client.get("/api/open-finance/settings", headers=auth).get_json()["auto_record"] is True
    assert client.get(INBOX_SETTINGS, headers=auth).get_json()["auto_record"] is True


# ---------------------------------------------------------------------------
# Revisar
# ---------------------------------------------------------------------------

class TestReview:
    def test_the_queue_lists_accounts_and_cards_newest_first(self, client, auth, auto):
        create_card(client, auth)
        create_account(client, auth, "Itaú")
        send(client, auth, detection("CREDIT_PURCHASE", 4590, at=ms(2026, 10, 10, 9, 0)))
        send(client, auth, detection("PIX_OUT", 1000, at=ms(2026, 10, 12, 9, 0), counterparty="Fulano"))
        body = review_queue(client, auth)
        assert body["count"] == 2
        assert [(item["table"], item["date"]) for item in body["items"]] == [
            ("transactions", "2026-10-12"), ("cc_expenses", "2026-10-10"),
        ]
        assert body["items"][1]["card_name"] == "Itaú Visa"
        assert client.get("/api/home", headers=auth).get_json()["review_count"] == 2

    def test_confirming_drops_the_badge_and_sets_the_category(self, client, auth, auto):
        account = create_account(client, auth, "Itaú")
        send(client, auth, detection("DEBIT_PURCHASE", 4590))
        [row] = transactions(client, auth)
        mercado = category_id(client, auth, "Mercado")
        body = confirm(client, auth, {"table": "transactions", "id": row["id"], "category_id": mercado})
        assert body == {"reviewed": 1, "count": 0}
        [after] = transactions(client, auth)
        assert (after["needs_review"], after["category_id"], after["category"], after["account_id"]) == (
            0, mercado, "Mercado", account,
        )

    def test_a_card_purchase_is_reviewed_with_every_installment(self, client, auth, auto):
        create_card(client, auth)
        send(client, auth, detection("CREDIT_PURCHASE", 30000, installments=3))
        rows = card_rows(client, auth)
        assert len(rows) == 3 and {row["needs_review"] for row in rows} == {1}
        [item] = review_queue(client, auth)["items"]
        assert (item["amount"], item["installments"]) == (300.0, 3)
        lazer = category_id(client, auth, "Lazer")
        confirm(client, auth, {"table": "cc_expenses", "id": item["id"], "category_id": lazer})
        assert {(row["needs_review"], row["category_id"]) for row in card_rows(client, auth)} == {(0, lazer)}

    def test_without_a_category_it_keeps_the_one_it_has(self, client, auth, auto):
        create_account(client, auth, "Itaú")
        send(client, auth, detection("DEBIT_PURCHASE", 4590))
        [row] = transactions(client, auth)
        confirm(client, auth, {"table": "transactions", "id": row["id"]})
        [after] = transactions(client, auth)
        assert (after["needs_review"], after["category"]) == (0, row["category"])

    def test_a_batch_is_all_or_nothing(self, client, auth, auto):
        create_account(client, auth, "Itaú")
        send(client, auth, detection("DEBIT_PURCHASE", 4590))
        [row] = transactions(client, auth)
        confirm(
            client, auth, {"table": "transactions", "id": row["id"]}, {"table": "transactions", "id": "nao-existe"},
            expected=404,
        )
        assert transactions(client, auth)[0]["needs_review"] == 1

    def test_refuses_a_bad_payload(self, client, auth):
        assert client.post("/api/review", json={"items": []}, headers=auth).status_code == 400
        assert client.post("/api/review", json={"items": [{"table": "users", "id": "x"}]}, headers=auth).status_code == 400

    def test_another_users_row_is_not_found(self, client, auth, auto, other_user):
        create_account(client, auth, "Itaú")
        send(client, auth, detection("DEBIT_PURCHASE", 4590))
        [row] = transactions(client, auth)
        confirm(client, other_user["headers"], {"table": "transactions", "id": row["id"]}, expected=404)
        assert review_queue(client, other_user["headers"])["count"] == 0

    def test_the_extrato_filters_what_awaits_review(self, client, auth, auto):
        account = create_account(client, auth, "Itaú")
        client.post(
            "/api/transactions",
            json={"amount": 10, "date": "2026-10-01", "type": "EXPENSE", "category": "Outros", "account_id": account},
            headers=auth,
        )
        send(client, auth, detection("DEBIT_PURCHASE", 4590))
        assert len(transactions(client, auth)) == 2
        [only] = transactions(client, auth, review=1)
        assert only["amount"] == 45.9

    def test_typed_rows_never_need_review(self, client, auth):
        account = create_account(client, auth, "Itaú")
        client.post(
            "/api/transactions",
            json={"amount": 10, "date": "2026-10-01", "type": "EXPENSE", "category": "Outros", "account_id": account},
            headers=auth,
        )
        assert transactions(client, auth)[0]["needs_review"] == 0
        assert review_queue(client, auth)["count"] == 0


# ---------------------------------------------------------------------------
# As compras no cartao no Extrato
# ---------------------------------------------------------------------------

def statement(client, auth, **params):
    query = "&".join(f"{key}={value}" for key, value in params.items())
    response = client.get(f"/api/cc-expenses/statement{'?' + query if query else ''}", headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def purchase(client, auth, card, amount, date, installments=1, description="LOJA", category="Outros"):
    response = client.post(
        "/api/cc-expenses/purchases",
        json={"card_id": card, "total_amount": amount, "purchase_date": date, "installments": installments,
              "description": description, "category": category},
        headers=auth,
    )
    assert response.status_code in (200, 201), response.get_data(as_text=True)


class TestCardStatement:
    def test_one_line_per_purchase_with_the_total(self, client, auth):
        card = create_card(client, auth, "Itaú Visa")
        purchase(client, auth, card, 300, "2026-10-05", installments=3, description="TV")
        purchase(client, auth, card, 20, "2026-10-07", description="CAFE")
        rows = statement(client, auth)
        assert [(row["description"], row["amount"], row["installments"], row["type"]) for row in rows] == [
            ("CAFE", 20.0, 1, "CARD"), ("TV", 300.0, 3, "CARD"),
        ]
        assert rows[1]["card_name"] == "Itaú Visa"

    def test_the_extrato_filters_apply(self, client, auth):
        card = create_card(client, auth)
        account = create_account(client, auth, "Itaú")
        purchase(client, auth, card, 300, "2026-10-05", installments=3, description="TV")
        purchase(client, auth, card, 20, "2026-10-07", description="CAFE")
        assert [row["description"] for row in statement(client, auth, q="caf")] == ["CAFE"]
        assert [row["description"] for row in statement(client, auth, **{"from": "2026-10-06"})] == ["CAFE"]
        assert [row["description"] for row in statement(client, auth, min_amount=100)] == ["TV"]
        assert statement(client, auth, type="TRANSFER") == []
        assert statement(client, auth, type="INCOME") == []
        assert statement(client, auth, account_id=account) == []
        assert statement(client, auth, review=1) == []

    def test_refuses_a_bad_filter(self, client, auth):
        response = client.get("/api/cc-expenses/statement?from=2026-13-01", headers=auth)
        assert response.status_code == 400

    def test_only_the_users_own(self, client, auth, other_user):
        card = create_card(client, auth)
        purchase(client, auth, card, 20, "2026-10-07")
        assert statement(client, other_user["headers"]) == []
