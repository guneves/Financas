"""Aprovar (031): quem esta do outro lado de um Pix separa transferencia de despesa.

O que estes testes protegem, na sequencia que a captura do dono mostrou
(2026-10-17; nomes e CPF trocados):

- um Pix do BB para o BTG e um Pix do Itau para o BTG, cada um com as duas
  pontas notificadas, viram uma transferencia cada, e o outro lado (o dono)
  fica aprendido;
- aprendido o dono, uma ponta so ja vem transferencia, com a conta do outro
  lado pela instituicao que a notificacao citou; a outra ponta, se chega
  depois, completa o mesmo item;
- um Pix para outra pessoa e despesa (recebido de outra pessoa, receita), e
  duas pontas de mesmo valor com pessoas diferentes nunca se juntam;
- o BTG posta cada compra duas vezes: um item so;
- toda deteccao acaba no Aprovar.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

BRT = timezone(timedelta(hours=-3))
ITAU = "com.itau"
BB = "br.com.bb.android"
BTG = "com.btg.pactual.banking"
SAMSUNG = "com.samsung.android.spay"
OWNER_DOC = "123456"


def ms(year, month, day, hour=12, minute=0, second=0, millis=0):
    return int(datetime(year, month, day, hour, minute, second, tzinfo=BRT).timestamp() * 1000) + millis


def detection(app, kind, amount_cents, at, **extra):
    body = {
        "key": uuid.uuid4().hex + uuid.uuid4().hex,
        "app": app,
        "kind": kind,
        "amount_cents": amount_cents,
        "posted_ms": at,
        "utc_offset_minutes": -180,
    }
    body.update(extra)
    return body


# As formas que cada banco deu (captura de 2026-10-17).
def bb_pix_out(amount_cents, at, name="Fulano R Silva", bank="BANCO BTG PACTUAL S."):
    return detection(BB, "PIX_OUT", amount_cents, at, counterparty=name, counterparty_bank=bank)


def btg_pix_in(amount_cents, at, name="Fulano N Souza Silva", doc=OWNER_DOC):
    return detection(BTG, "PIX_IN", amount_cents, at, counterparty=name, counterparty_doc=doc)


def itau_pix_out(amount_cents, at, name="FULANO", doc=OWNER_DOC):
    return detection(ITAU, "PIX_OUT", amount_cents, at, counterparty=name, counterparty_doc=doc)


def itau_pix_in(amount_cents, at, name="FULANO", doc=OWNER_DOC):
    return detection(ITAU, "PIX_IN", amount_cents, at, counterparty=name, counterparty_doc=doc)


def send(client, auth, *detections):
    response = client.post("/api/inbox/detections", json={"detections": list(detections)}, headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["results"]


def pending(client, auth):
    return client.get("/api/inbox", headers=auth).get_json()["items"]


def approve(client, auth, item, expected=200, **payload):
    response = client.post(
        f"/api/inbox/{item['id']}/approve", json={"version": item["version"], **payload}, headers=auth,
    )
    assert response.status_code == expected, response.get_data(as_text=True)
    return response.get_json()


def create_account(client, auth, name):
    response = client.post("/api/accounts", json={"name": name, "type": "CHECKING"}, headers=auth)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["id"]


@pytest.fixture()
def accounts(client, auth):
    return {
        "bb": create_account(client, auth, "Banco do Brasil"),
        "itau": create_account(client, auth, "Itaú"),
        "btg": create_account(client, auth, "BTG"),
    }


def learn_owner(client, auth):
    """A primeira transferencia da captura: BB -> BTG, as duas pontas."""
    send(client, auth, bb_pix_out(1, ms(2026, 10, 17, 4, 11, 54)), btg_pix_in(1, ms(2026, 10, 17, 4, 11, 57)))
    [item] = pending(client, auth)
    approve(client, auth, item)


class TestTheCapturedSequence:
    def test_both_legs_make_one_transfer_each(self, client, auth, accounts):
        results = send(
            client, auth,
            bb_pix_out(1, ms(2026, 10, 17, 4, 11, 54)),
            btg_pix_in(1, ms(2026, 10, 17, 4, 11, 57)),
            itau_pix_out(1, ms(2026, 10, 17, 4, 29, 30)),
            btg_pix_in(1, ms(2026, 10, 17, 4, 29, 31), name="Fulano Neves Souza Silva"),
        )
        assert [result["status"] for result in results] == ["new", "merged", "new", "merged"]
        items = sorted(pending(client, auth), key=lambda item: item["occurred_at"])
        assert [item["entry_type"] for item in items] == ["TRANSFER", "TRANSFER"]
        assert (items[0]["account_id"], items[0]["transfer_account_id"]) == (accounts["bb"], accounts["btg"])
        assert (items[1]["account_id"], items[1]["transfer_account_id"]) == (accounts["itau"], accounts["btg"])
        assert all(item["reason"] == "own_transfer" for item in items)
        # Contas pelo nome do banco: palpites, que o dono confirma uma vez.
        assert all(item["needs"] == [] for item in items)

    def test_the_owner_is_learned_from_a_paired_transfer(self, client, auth, accounts):
        send(client, auth, bb_pix_out(1, ms(2026, 10, 17, 4, 11, 54)), btg_pix_in(1, ms(2026, 10, 17, 4, 11, 57)))
        keys = {hint["hint_key"] for hint in client.get("/api/inbox/hints", headers=auth).get_json()}
        assert f"self:doc:{OWNER_DOC}" in keys
        assert "self:name:fulano r silva" in keys

    def test_one_leg_alone_is_a_transfer_once_the_owner_is_known(self, client, auth, accounts):
        learn_owner(client, auth)
        # O BB notifica o Pix para o Itau; o Itau ainda nao avisou.
        [result] = send(client, auth, bb_pix_out(5000, ms(2026, 10, 18, 9), bank="ITAÚ UNIBANCO S.A."))
        assert result["status"] == "new"
        [item] = pending(client, auth)
        assert item["entry_type"] == "TRANSFER"
        assert (item["account_id"], item["transfer_account_id"]) == (accounts["bb"], accounts["itau"])
        assert item["reason"] == "own_transfer"
        assert "transfer_account" in item["confirm"]
        # A entrada no Itau chega depois: completa o mesmo item, sem palpite.
        [late] = send(client, auth, itau_pix_in(5000, ms(2026, 10, 18, 9, 0, 2)))
        assert late["status"] == "merged"
        [item] = pending(client, auth)
        assert item["transfer_account_id"] == accounts["itau"]
        assert item["needs"] == []
        approve(client, auth, item)
        rows = client.get("/api/transactions", headers=auth).get_json()
        transfers = [row for row in rows if row["type"] == "TRANSFER" and row["amount"] == 50]
        assert len(transfers) == 1

    def test_one_leg_without_the_other_bank_asks_for_it(self, client, auth, accounts):
        learn_owner(client, auth)
        # O Itau nao diz a instituicao do outro lado.
        send(client, auth, itau_pix_out(2000, ms(2026, 10, 18, 10)))
        [item] = pending(client, auth)
        assert (item["entry_type"], item["account_id"], item["transfer_account_id"]) == (
            "TRANSFER", accounts["itau"], None,
        )
        assert item["needs"] == ["transfer_account"]
        # Chega a entrada no BTG: o outro lado se preenche.
        send(client, auth, btg_pix_in(2000, ms(2026, 10, 18, 10, 0, 1)))
        [item] = pending(client, auth)
        assert (item["account_id"], item["transfer_account_id"]) == (accounts["itau"], accounts["btg"])
        assert item["needs"] == []

    def test_approving_a_one_sided_transfer_teaches_the_owner(self, client, auth, accounts):
        # Nada aprendido: um Pix do Itau sozinho e despesa para "FULANO".
        send(client, auth, itau_pix_out(3000, ms(2026, 10, 18, 11)))
        [item] = pending(client, auth)
        assert (item["entry_type"], item["reason"]) == ("EXPENSE", "external_transfer")
        approve(client, auth, item, entry_type="TRANSFER", transfer_account_id=accounts["btg"])
        # O proximo, de mesmo CPF, ja vem transferencia.
        send(client, auth, itau_pix_out(4000, ms(2026, 10, 19, 11)))
        [item] = pending(client, auth)
        assert item["entry_type"] == "TRANSFER"


class TestExternalTransfers:
    def test_a_pix_to_someone_else_is_an_expense(self, client, auth, accounts):
        learn_owner(client, auth)
        send(client, auth, bb_pix_out(8000, ms(2026, 10, 18, 12), name="Maria Souza", bank="NU PAGAMENTOS - IP"))
        [item] = pending(client, auth)
        assert (item["entry_type"], item["direction"], item["account_id"]) == ("EXPENSE", "OUT", accounts["bb"])
        assert item["description"] == "Pix para Maria Souza"
        assert item["reason"] == "external_transfer"

    def test_a_pix_from_someone_else_is_income(self, client, auth, accounts):
        learn_owner(client, auth)
        send(client, auth, itau_pix_in(15000, ms(2026, 10, 18, 12), name="JOAO", doc="987654"))
        [item] = pending(client, auth)
        assert (item["entry_type"], item["direction"], item["account_id"]) == ("INCOME", "IN", accounts["itau"])
        assert item["description"] == "Pix de JOAO"

    def test_same_amount_with_different_people_never_pairs(self, client, auth, accounts):
        # Pagou R$ 50 a Maria pelo Itau e recebeu R$ 50 de Joao no BTG, no mesmo dia.
        send(
            client, auth,
            itau_pix_out(5000, ms(2026, 10, 18, 13), name="MARIA", doc="111222"),
            btg_pix_in(5000, ms(2026, 10, 18, 13, 5), name="Joao Pereira", doc="333444"),
        )
        items = pending(client, auth)
        assert sorted(item["entry_type"] for item in items) == ["EXPENSE", "INCOME"]
        keys = {hint["hint_key"] for hint in client.get("/api/inbox/hints", headers=auth).get_json()}
        assert not any(key.startswith("self:") for key in keys)

    def test_a_known_owner_doc_does_not_pair_with_a_stranger(self, client, auth, accounts):
        learn_owner(client, auth)
        send(client, auth, itau_pix_out(7000, ms(2026, 10, 18, 14)))
        send(client, auth, btg_pix_in(7000, ms(2026, 10, 18, 14, 1), name="Joao Pereira", doc="333444"))
        items = sorted(pending(client, auth), key=lambda item: item["occurred_at"])
        assert [item["entry_type"] for item in items] == ["TRANSFER", "INCOME"]


class TestEverythingGoesToAprovar:
    def test_the_bank_posting_a_purchase_twice_is_one_item(self, client, auth, accounts):
        at = ms(2026, 10, 17, 14, 1, 15, 298)
        twice = [
            detection(BTG, "PURCHASE", 1958, at, when_ms=at - 11, merchant="Drogaria São Paulo"),
            detection(BTG, "PURCHASE", 1958, at + 24, when_ms=at - 11, merchant="Drogaria São Paulo"),
        ]
        results = send(client, auth, *twice)
        assert [result["status"] for result in results] == ["new", "repeated"]
        [item] = pending(client, auth)
        assert item["description"] == "Drogaria São Paulo"
        assert item["entry_type"] is None
        assert item["needs"] == ["method"]

    def test_two_real_purchases_of_the_same_amount_stay_two(self, client, auth, accounts):
        first = ms(2026, 10, 17, 14)
        send(
            client, auth,
            detection(BTG, "PURCHASE", 1000, first, when_ms=first, merchant="Cafe"),
            detection(BTG, "PURCHASE", 1000, first + 40_000, when_ms=first + 40_000, merchant="Cafe"),
        )
        assert len(pending(client, auth)) == 2

    def test_the_bank_wins_over_samsung_wallet(self, client, auth, accounts):
        at = ms(2026, 10, 18, 15)
        results = send(
            client, auth,
            detection(SAMSUNG, "PURCHASE", 2590, at, merchant="MERCADO"),
            detection(BTG, "PURCHASE", 2590, at + 3000, merchant="Mercado Bom Preco"),
        )
        assert [result["status"] for result in results] == ["new", "merged"]
        [item] = pending(client, auth)
        assert item["description"] == "Mercado Bom Preco"
        roles = {source["app"]: source["role"] for source in item["sources"]}
        assert roles == {BTG: "SOURCE", SAMSUNG: "PAIRED"}

    def test_a_remembered_choice_still_waits_for_the_owner(self, client, auth, accounts):
        typed = client.post(
            "/api/transactions",
            json={"amount": 12, "date": "2026-10-18", "category": "Outros", "type": "EXPENSE",
                  "account_id": accounts["itau"]},
            headers=auth,
        ).get_json()
        send(client, auth, itau_pix_out(1200, ms(2026, 10, 18, 16), name="PADARIA", doc="555666"))
        [item] = pending(client, auth)
        assert [candidate["id"] for candidate in item["candidates"]] == [typed["id"]]

    def test_counterparty_is_kept_only_for_pix_and_transfers(self, client, auth, accounts):
        send(client, auth, detection(BTG, "PURCHASE", 990, ms(2026, 10, 18, 17), merchant="X", counterparty="Y"))
        [item] = pending(client, auth)
        assert item["sources"][0]["counterparty"] is None

    def test_a_bad_document_is_refused(self, client, auth, accounts):
        [result] = send(client, auth, itau_pix_out(100, ms(2026, 10, 18, 18), doc="12"))
        assert result["status"] == "invalid"
