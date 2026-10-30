"""Aprovar: quando a escolha da conta/cartao nao fica lembrada.

O que estes testes protegem:

- a notificacao sem o final do cartao, com mais de uma conta ativa no banco
  dela (pelo campo de banco, nunca pelo nome): nada fica lembrado, nem palpite,
  e o item pergunta toda vez — inclusive quando havia uma escolha lembrada de
  antes;
- contas "sem banco" nao entram na conta: com menos de duas no banco, vale o
  de sempre (lembra e decide sozinho da proxima vez);
- o final do cartao na notificacao desfaz a ambiguidade;
- "Sempre perguntar a conta/cartao" (Ajustes, desligado por padrao): todo item
  pede confirmar, inclusive o lembrado, e "Aprovar todos" nao leva nenhum;
- user_id na preferencia.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.usefixtures("any_bank_notifications")

BRT = timezone(timedelta(hours=-3))
ITAU = "com.itau"


def create_account(client, auth, name, institution=None, type_="CHECKING"):
    body = {"name": name, "type": type_}
    if institution is not None:
        body["institution"] = institution
    response = client.post("/api/accounts", json=body, headers=auth)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["id"]


def create_card(client, auth, name):
    response = client.post("/api/credit-cards", json={"name": name, "due_day": 10, "closing_day": 3}, headers=auth)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["id"]


def ms(day, hour=12):
    return int(datetime(2026, 10, day, hour, 0, tzinfo=BRT).timestamp() * 1000)


def detection(kind="PIX_OUT", amount_cents=4590, day=10, **extra):
    body = {
        "key": uuid.uuid4().hex + uuid.uuid4().hex,
        "app": ITAU,
        "kind": kind,
        "amount_cents": amount_cents,
        "posted_ms": ms(day),
        "utc_offset_minutes": -180,
        "merchant": "PADARIA BOM PAO",
    }
    body.update(extra)
    return body


def send(client, auth, *detections):
    response = client.post("/api/inbox/detections", json={"detections": list(detections)}, headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["results"]


def pending(client, auth):
    response = client.get("/api/inbox", headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["items"]


def approve(client, auth, item, expected=200, **payload):
    response = client.post(f"/api/inbox/{item['id']}/approve", json={"version": item["version"], **payload}, headers=auth)
    assert response.status_code == expected, response.get_data(as_text=True)
    return response.get_json()


def hints(client, auth):
    return client.get("/api/inbox/hints", headers=auth).get_json()


def set_always_ask(client, auth, value):
    response = client.patch("/api/inbox/settings", json={"always_ask": value}, headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


class TestAmbiguousBank:
    def test_two_accounts_at_the_bank_ask_every_time(self, client, auth):
        corrente = create_account(client, auth, "Conta corrente", "Itaú")
        create_account(client, auth, "Conta salário", "Itaú")
        send(client, auth, detection())
        [item] = pending(client, auth)
        assert item["account_id"] is None
        assert item["needs"] == ["account"]
        assert item["ambiguous"] is True

        approve(client, auth, item, account_id=corrente)
        assert hints(client, auth) == []

        send(client, auth, detection(day=11))
        [again] = pending(client, auth)
        assert again["account_id"] is None and again["needs"] == ["account"]
        assert again["ready"] is False

    def test_an_old_remembered_choice_stops_deciding_once_a_second_account_exists(self, client, auth):
        corrente = create_account(client, auth, "Conta corrente", "Itaú")
        create_account(client, auth, "Nubank", "Nubank")
        send(client, auth, detection())
        [item] = pending(client, auth)
        # Uma so no Itau: o palpite vem, e aprovar lembra.
        assert item["account_id"] == corrente and item["ambiguous"] is False
        approve(client, auth, item)
        assert len(hints(client, auth)) == 1

        create_account(client, auth, "Conta salário", "Itaú")
        send(client, auth, detection(day=11))
        [again] = pending(client, auth)
        assert again["account_id"] is None
        assert again["needs"] == ["account"]
        assert again["ambiguous"] is True

    def test_accounts_without_a_bank_fall_back_to_remembering(self, client, auth):
        # O nome diz Itau, mas o campo de banco esta vazio: o app nao conta.
        first = create_account(client, auth, "Itaú corrente")
        create_account(client, auth, "Itaú salário")
        send(client, auth, detection())
        [item] = pending(client, auth)
        assert item["ambiguous"] is False
        approve(client, auth, item, account_id=first)
        assert [hint["account_id"] for hint in hints(client, auth)] == [first]

        send(client, auth, detection(day=11))
        [again] = pending(client, auth)
        assert again["account_id"] == first and again["ready"] is True

    def test_one_account_with_the_bank_and_one_without_is_not_ambiguous(self, client, auth):
        corrente = create_account(client, auth, "Conta corrente", "Itaú")
        create_account(client, auth, "Carteira")
        send(client, auth, detection())
        [item] = pending(client, auth)
        assert item["ambiguous"] is False
        approve(client, auth, item, account_id=corrente)
        assert len(hints(client, auth)) == 1

    def test_the_card_final_settles_it(self, client, auth):
        # Uma compra no debito com o final: a chave lembrada e desse cartao.
        corrente = create_account(client, auth, "Conta corrente", "Itaú")
        create_account(client, auth, "Conta salário", "Itaú")
        send(client, auth, detection(kind="DEBIT_PURCHASE", card_last4="1234"))
        [item] = pending(client, auth)
        assert item["ambiguous"] is False
        approve(client, auth, item, account_id=corrente)
        send(client, auth, detection(kind="DEBIT_PURCHASE", card_last4="1234", day=11))
        [again] = pending(client, auth)
        assert again["account_id"] == corrente and again["ready"] is True

    def test_an_archived_account_does_not_count(self, client, auth):
        corrente = create_account(client, auth, "Conta corrente", "Itaú")
        old = create_account(client, auth, "Conta antiga", "Itaú")
        assert client.delete(f"/api/accounts/{old}", headers=auth).status_code == 200
        send(client, auth, detection())
        [item] = pending(client, auth)
        assert item["ambiguous"] is False and item["account_id"] == corrente

    def test_cards_have_no_bank_field_so_they_keep_todays_behaviour(self, client, auth):
        visa = create_card(client, auth, "Itaú Visa")
        create_card(client, auth, "Itaú Master")
        send(client, auth, detection(kind="CREDIT_PURCHASE"))
        [item] = pending(client, auth)
        assert item["ambiguous"] is False
        approve(client, auth, item, card_id=visa)
        assert [hint["card_id"] for hint in hints(client, auth)] == [visa]

    def test_a_pending_twin_is_not_decided_by_the_choice(self, client, auth):
        corrente = create_account(client, auth, "Conta corrente", "Itaú")
        create_account(client, auth, "Conta salário", "Itaú")
        send(client, auth, detection(), detection(amount_cents=1200))
        first, second = pending(client, auth)
        approve(client, auth, first, account_id=corrente)
        [left] = pending(client, auth)
        assert left["id"] == second["id"] and left["account_id"] is None


class TestAlwaysAsk:
    def test_off_by_default_and_per_user(self, client, auth, other_user):
        assert client.get("/api/inbox/settings", headers=auth).get_json()["always_ask"] is False
        assert set_always_ask(client, auth, True)["always_ask"] is True
        assert client.get("/api/inbox/settings", headers=auth).get_json()["always_ask"] is True
        assert client.get("/api/inbox/settings", headers=other_user["headers"]).get_json()["always_ask"] is False

    def test_refuses_anything_but_a_boolean(self, client, auth):
        response = client.patch("/api/inbox/settings", json={"always_ask": "sim"}, headers=auth)
        assert response.status_code == 400

    def test_a_remembered_choice_still_fills_but_waits_for_confirmation(self, client, auth):
        corrente = create_account(client, auth, "Conta corrente", "Itaú")
        send(client, auth, detection())
        approve(client, auth, pending(client, auth)[0])
        send(client, auth, detection(day=11))
        [remembered] = pending(client, auth)
        assert remembered["ready"] is True

        set_always_ask(client, auth, True)
        [item] = pending(client, auth)
        assert item["account_id"] == corrente
        assert item["confirm"] == ["account"]
        assert item["ready"] is False

        response = client.post("/api/inbox/approve-ready", json={"ids": [item["id"]]}, headers=auth)
        assert response.get_json()["approved"] == []

        # Aprovar o item, um a um, e a confirmacao.
        approve(client, auth, item)
        assert pending(client, auth) == []

    def test_choosing_on_the_item_confirms_it(self, client, auth):
        create_account(client, auth, "Conta corrente", "Itaú")
        other = create_account(client, auth, "Nubank", "Nubank")
        set_always_ask(client, auth, True)
        send(client, auth, detection())
        [item] = pending(client, auth)
        response = client.patch(
            f"/api/inbox/{item['id']}", json={"version": item["version"], "account_id": other}, headers=auth,
        )
        assert response.status_code == 200
        assert response.get_json()["confirm"] == [] and response.get_json()["ready"] is True

    def test_turning_it_off_brings_back_the_bulk_approval(self, client, auth):
        create_account(client, auth, "Conta corrente", "Itaú")
        send(client, auth, detection())
        approve(client, auth, pending(client, auth)[0])
        set_always_ask(client, auth, True)
        send(client, auth, detection(day=11))
        assert pending(client, auth)[0]["ready"] is False
        set_always_ask(client, auth, False)
        assert pending(client, auth)[0]["ready"] is True
