"""A funcao debito de um cartao (041) e o Flash no Aprovar.

O que estes testes protegem:

- um cartao pode ter credito, debito ou os dois; sem nenhuma funcao e recusado;
- a compra no debito e uma despesa na conta do cartao: um cartao so debito nao
  aceita compra de fatura, estorno nem debito automatico;
- tirar o credito de um cartao com fatura em aberto e recusado; dar credito a um
  so debito pede vencimento e fechamento;
- no Aprovar, a compra num cartao so debito (o Flash, pelo app ou pelo Samsung
  Wallet "Card used for Meal and Voucher") vira despesa na conta dele, nunca
  item de fatura, e nao pareia com a compra de outro banco de mesmo valor.
"""

import uuid
from datetime import datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))
SAMSUNG = "com.samsung.android.spay"
FLASH = "br.com.flashapp"
BTG = "com.btg.pactual.banking"


def create_account(client, auth, name):
    response = client.post("/api/accounts", json={"name": name, "type": "CHECKING"}, headers=auth)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["id"]


def create_card(client, auth, expected=201, **payload):
    response = client.post("/api/credit-cards", json=payload, headers=auth)
    assert response.status_code == expected, response.get_data(as_text=True)
    return response.get_json()


def patch_card(client, auth, card_id, expected=200, **payload):
    response = client.patch(f"/api/credit-cards/{card_id}", json=payload, headers=auth)
    assert response.status_code == expected, response.get_data(as_text=True)
    return response.get_json()


def ms(year, month, day, hour=12, minute=0, second=0):
    return int(datetime(year, month, day, hour, minute, second, tzinfo=BRT).timestamp() * 1000)


def detection(kind="PURCHASE", amount_cents=4681, at=None, app=SAMSUNG, **extra):
    body = {
        "key": uuid.uuid4().hex + uuid.uuid4().hex,
        "app": app,
        "kind": kind,
        "amount_cents": amount_cents,
        "posted_ms": at or ms(2026, 10, 21, 20, 28, 24),
        "utc_offset_minutes": -180,
        "merchant": "DOCEPAOPITUBA",
    }
    body.update(extra)
    return body


def send(client, auth, *detections):
    response = client.post("/api/inbox/detections", json={"detections": list(detections)}, headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["results"]


def pending(client, auth):
    return client.get("/api/inbox", headers=auth).get_json()["items"]


class TestCardFunctions:
    def test_a_card_is_credit_by_default(self, client, auth):
        card = create_card(client, auth, name="Itaú Visa", due_day=10, closing_day=3)
        assert card["credit_enabled"] == 1
        assert card["debit_account_id"] is None

    def test_a_credit_card_can_also_have_debit(self, client, auth):
        account = create_account(client, auth, "BTG Banking")
        card = create_card(client, auth, name="BTG", due_day=10, closing_day=3, debit_account_id=account)
        assert card["credit_enabled"] == 1
        assert card["debit_account_id"] == account

    def test_a_debit_only_card_needs_no_dates(self, client, auth):
        account = create_account(client, auth, "Flash")
        card = create_card(client, auth, name="Flash", credit_enabled=False, debit_account_id=account)
        assert card["credit_enabled"] == 0
        assert card["debit_account_id"] == account

    def test_a_card_without_any_function_is_refused(self, client, auth):
        body = create_card(client, auth, expected=400, name="Nada", credit_enabled=False)
        assert "credito ou debito" in body["error"]

    def test_a_debit_only_card_has_no_autopay(self, client, auth):
        account = create_account(client, auth, "Flash")
        create_card(
            client, auth, expected=400, name="Flash", credit_enabled=False,
            debit_account_id=account, autopay_account_id=account,
        )

    def test_the_debit_account_must_be_the_users_and_active(self, client, auth, other_user):
        theirs = create_account(client, other_user["headers"], "Deles")
        create_card(client, auth, expected=400, name="X", credit_enabled=False, debit_account_id=theirs)
        mine = create_account(client, auth, "Arquivada")
        assert client.delete(f"/api/accounts/{mine}", headers=auth).status_code == 200
        create_card(client, auth, expected=400, name="Y", credit_enabled=False, debit_account_id=mine)

    def test_the_brokerage_account_is_not_a_debit_account(self, client, auth):
        response = client.post("/api/accounts", json={"name": "Corretora", "type": "BROKERAGE"}, headers=auth)
        assert response.status_code == 201, response.get_data(as_text=True)
        body = create_card(
            client, auth, expected=400, name="X", credit_enabled=False, debit_account_id=response.get_json()["id"],
        )
        assert "corretora" in body["error"]

    def test_an_edit_keeps_an_archived_debit_account(self, client, auth):
        account = create_account(client, auth, "Flash")
        card = create_card(client, auth, name="Flash", credit_enabled=False, debit_account_id=account)
        assert client.delete(f"/api/accounts/{account}", headers=auth).status_code == 200
        updated = patch_card(client, auth, card["id"], name="Flash VR", debit_account_id=account)
        assert updated["debit_account_id"] == account

    def test_a_debit_only_card_takes_no_invoice_purchase(self, client, auth):
        account = create_account(client, auth, "Flash")
        card = create_card(client, auth, name="Flash", credit_enabled=False, debit_account_id=account)
        response = client.post("/api/cc-expenses/purchases", json={
            "card_id": card["id"], "category": "Alimentação", "description": "Padaria",
            "total_amount": 46.81, "purchase_date": "2026-10-21", "installments": 1,
        }, headers=auth)
        assert response.status_code == 400
        assert "so tem a funcao debito" in response.get_json()["error"]
        response = client.post("/api/cc-expenses/refunds", json={
            "card_id": card["id"], "description": "Estorno", "amount": 10, "purchase_date": "2026-10-21",
        }, headers=auth)
        assert response.status_code == 400
        assert "so tem a funcao debito" in response.get_json()["error"]

    def test_removing_credit_with_an_open_invoice_is_refused(self, client, auth):
        account = create_account(client, auth, "BTG Banking")
        card = create_card(client, auth, name="BTG", due_day=10, closing_day=3, debit_account_id=account)
        response = client.post("/api/cc-expenses/purchases", json={
            "card_id": card["id"], "category": "Alimentação", "description": "Mercado",
            "total_amount": 100, "purchase_date": "2026-10-21", "installments": 1,
        }, headers=auth)
        assert response.status_code == 201, response.get_data(as_text=True)
        patch_card(client, auth, card["id"], expected=409, credit_enabled=False)

    def test_removing_credit_turns_autopay_off(self, client, auth):
        account = create_account(client, auth, "BTG Banking")
        card = create_card(
            client, auth, name="BTG", due_day=10, closing_day=3,
            debit_account_id=account, autopay_account_id=account,
        )
        updated = patch_card(client, auth, card["id"], credit_enabled=False)
        assert updated["credit_enabled"] == 0
        assert updated["autopay_account_id"] is None

    def test_removing_both_functions_is_refused(self, client, auth):
        card = create_card(client, auth, name="Itaú Visa", due_day=10, closing_day=3)
        patch_card(client, auth, card["id"], expected=400, credit_enabled=False)

    def test_giving_credit_to_a_debit_only_card_needs_the_dates(self, client, auth):
        account = create_account(client, auth, "Flash")
        card = create_card(client, auth, name="Flash", credit_enabled=False, debit_account_id=account)
        patch_card(client, auth, card["id"], expected=400, credit_enabled=True)
        updated = patch_card(client, auth, card["id"], credit_enabled=True, due_day=15, closing_day=8)
        assert (updated["credit_enabled"], updated["due_day"], updated["closing_day"]) == (1, 15, 8)

    def test_another_users_card_is_not_found(self, client, auth, other_user):
        account = create_account(client, other_user["headers"], "Flash")
        card = create_card(
            client, other_user["headers"], name="Flash", credit_enabled=False, debit_account_id=account,
        )
        patch_card(client, auth, card["id"], expected=404, credit_enabled=True, due_day=1, closing_day=1)


class TestAprovar:
    def test_samsung_meal_and_voucher_lands_in_the_flash_account(self, client, auth):
        flash_account = create_account(client, auth, "Flash")
        create_card(client, auth, name="Itaú Visa", due_day=10, closing_day=3)
        create_card(client, auth, name="Flash", credit_enabled=False, debit_account_id=flash_account)
        [result] = send(client, auth, detection(card_name="Card used for Meal and Voucher"))
        assert result["status"] == "new"
        [item] = pending(client, auth)
        assert item["entry_type"] == "EXPENSE"
        assert item["account_id"] == flash_account
        assert item["card_id"] is None
        assert "account" in item["guessed"]
        assert item["description"] == "DOCEPAOPITUBA"

        response = client.post(
            f"/api/inbox/{item['id']}/approve", json={"version": item["version"]}, headers=auth,
        )
        assert response.status_code == 200, response.get_data(as_text=True)
        rows = [row for row in client.get("/api/transactions", headers=auth).get_json() if row["account_id"] == flash_account]
        assert [(row["type"], row["amount"], row["description"]) for row in rows] == [("EXPENSE", 46.81, "DOCEPAOPITUBA")]
        assert client.get("/api/cc-expenses", headers=auth).get_json() == []

        # Lembrado: a proxima compra do mesmo cartao ja vem pronta para a conta do Flash.
        send(client, auth, detection(amount_cents=1250, at=ms(2026, 10, 22, 12), card_name="Card used for Meal and Voucher"))
        [item] = pending(client, auth)
        assert (item["entry_type"], item["account_id"], item["guessed"]) == ("EXPENSE", flash_account, [])

    def test_the_flash_app_lands_in_the_flash_account(self, client, auth):
        flash_account = create_account(client, auth, "Flash")
        create_account(client, auth, "Itaú")
        create_card(client, auth, name="Flash", credit_enabled=False, debit_account_id=flash_account)
        send(client, auth, detection(app=FLASH, merchant="RESTAURANTE"))
        [item] = pending(client, auth)
        assert (item["entry_type"], item["account_id"]) == ("EXPENSE", flash_account)
        assert item["hint_label"].startswith("Flash")

    def test_flash_and_a_btg_purchase_of_the_same_amount_stay_two(self, client, auth):
        flash_account = create_account(client, auth, "Flash")
        create_card(client, auth, name="Flash", credit_enabled=False, debit_account_id=flash_account)
        create_card(client, auth, name="BTG", due_day=10, closing_day=3)
        at = ms(2026, 10, 21, 20, 28, 24)
        send(
            client, auth,
            detection(card_name="Card used for Meal and Voucher", at=at),
            detection(app=BTG, merchant="Doce Pao", at=at + 500),
        )
        assert len(pending(client, auth)) == 2

    def test_samsung_and_the_bank_of_the_same_purchase_stay_one(self, client, auth):
        # Captura de 2026-10-21: Samsung "BTG Pactual Banking / DROGASIL 1439 R$ 17,11" e o
        # BTG "Sua compra de R$ 17,11 em Drogasil foi autorizada", 250 ms depois.
        create_card(client, auth, name="BTG", due_day=10, closing_day=3)
        at = ms(2026, 10, 21, 20, 31, 37)
        send(
            client, auth,
            detection(card_name="BTG Pactual Banking", merchant="DROGASIL 1439", amount_cents=1711, at=at),
            detection(app=BTG, merchant="Drogasil", amount_cents=1711, at=at + 250),
        )
        [item] = pending(client, auth)
        assert item["description"] == "Drogasil"

    def test_a_debit_purchase_on_a_combo_card_uses_its_debit_account(self, client, auth):
        create_account(client, auth, "Itaú")
        banking = create_account(client, auth, "Conta BTG")
        create_card(client, auth, name="BTG", due_day=10, closing_day=3, debit_account_id=banking)
        send(client, auth, detection(kind="DEBIT_PURCHASE", app=BTG, merchant="Mercado"))
        [item] = pending(client, auth)
        assert (item["entry_type"], item["account_id"]) == ("EXPENSE", banking)

    def test_a_purchase_without_method_on_a_combo_card_still_asks(self, client, auth):
        banking = create_account(client, auth, "Conta BTG")
        card = create_card(client, auth, name="BTG", due_day=10, closing_day=3, debit_account_id=banking)
        send(client, auth, detection(app=BTG, merchant="Mercado"))
        [item] = pending(client, auth)
        assert item["entry_type"] is None
        assert "method" in item["needs"]
        # Escolhido o metodo, o cartao (credito) e a conta (debito) ja estao la.
        assert (item["card_id"], item["account_id"]) == (card["id"], banking)

    def test_a_debit_only_card_is_never_a_card_target(self, client, auth):
        flash_account = create_account(client, auth, "Flash")
        create_card(client, auth, name="Flash", credit_enabled=False, debit_account_id=flash_account)
        # Um credito explicito num app que nao e o do Flash nao cai no Flash.
        send(client, auth, detection(kind="CREDIT_PURCHASE", app=BTG, merchant="Loja"))
        [item] = pending(client, auth)
        assert item["entry_type"] == "CARD"
        assert item["card_id"] is None
        assert "card" in item["needs"]
