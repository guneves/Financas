"""Aprovar (028): o que o celular traz espera o dono, um item por movimento.

O que estes testes protegem:

- nada vira lancamento sem o dono aprovar, e a hora da fonte fica (a data e a
  local: uma compra as 22h30 em Brasilia fica no dia dela);
- a mesma compra notificada pelo banco e pelo Samsung Wallet e um item so;
  duas compras de mesmo valor ficam duas;
- sem credito/debito, ou sem saber o cartao/conta, o dono decide, e a escolha
  lembrada decide da proxima vez;
- uma transferencia entre contas do dono e uma linha TRANSFER, nunca uma
  despesa e uma receita;
- o rascunho corrigido e o que entra; dois aparelhos nao se atropelam (409);
- user_id em tudo.
"""

import importlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.usefixtures("any_bank_notifications")

BRT = timezone(timedelta(hours=-3))
ITAU = "com.itau"
BB = "br.com.bb.android"
SAMSUNG = "com.samsung.android.spay"


def create_account(client, auth, name="Itaú"):
    response = client.post("/api/accounts", json={"name": name, "type": "CHECKING"}, headers=auth)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["id"]


def create_card(client, auth, name="Itaú Visa"):
    response = client.post(
        "/api/credit-cards", json={"name": name, "due_day": 10, "closing_day": 3}, headers=auth,
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["id"]


def rows(client, auth, account_id=None):
    items = client.get("/api/transactions", headers=auth).get_json()
    if account_id:
        items = [item for item in items if item["account_id"] == account_id]
    return items


def card_rows(client, auth, card_id):
    return [item for item in client.get("/api/cc-expenses", headers=auth).get_json() if item["card_id"] == card_id]


def ms(year, month, day, hour=12, minute=0, second=0):
    """O instante em Brasilia, em milissegundos (o posted_ms do celular)."""
    return int(datetime(year, month, day, hour, minute, second, tzinfo=BRT).timestamp() * 1000)


def detection(kind="CREDIT_PURCHASE", amount_cents=4590, at=None, app=ITAU, **extra):
    body = {
        "key": uuid.uuid4().hex + uuid.uuid4().hex,
        "app": app,
        "kind": kind,
        "amount_cents": amount_cents,
        "posted_ms": at or ms(2026, 10, 10, 14, 32, 5),
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


def decided(client, auth):
    return client.get("/api/inbox?view=decided", headers=auth).get_json()["items"]


def approve(client, auth, item, expected=200, **payload):
    response = client.post(
        f"/api/inbox/{item['id']}/approve", json={"version": item["version"], **payload}, headers=auth,
    )
    assert response.status_code == expected, response.get_data(as_text=True)
    return response.get_json()


def patch(client, auth, item, expected=200, **payload):
    response = client.patch(f"/api/inbox/{item['id']}", json={"version": item["version"], **payload}, headers=auth)
    assert response.status_code == expected, response.get_data(as_text=True)
    return response.get_json()


def hints(client, auth):
    return client.get("/api/inbox/hints", headers=auth).get_json()


@pytest.fixture()
def one_card(client, auth):
    return create_card(client, auth, "Itaú Visa")


@pytest.fixture()
def one_account(client, auth):
    return create_account(client, auth, "Itaú")


class TestTimestamps:
    def test_a_detection_waits_with_the_time_it_happened(self, client, auth, one_card):
        [result] = send(client, auth, detection(at=ms(2026, 10, 10, 14, 32, 5)))
        assert result["status"] == "new"
        [item] = pending(client, auth)
        assert item["occurred_at"] == "2026-10-10T14:32:05-03:00"
        assert item["source_occurred_at"] == "2026-10-10T14:32:05-03:00"
        assert (item["entry_type"], item["amount"], item["description"]) == ("CARD", 45.9, "PADARIA BOM PAO")
        assert card_rows(client, auth, one_card) == []
        assert item["sources"][0]["app_label"] == "Itaú"

    def test_a_late_evening_purchase_stays_on_its_local_day(self, client, auth, one_card):
        send(client, auth, detection(at=ms(2026, 10, 17, 22, 30)))
        [item] = pending(client, auth)
        assert item["occurred_at"] == "2026-10-17T22:30:00-03:00"
        approve(client, auth, item)
        [row] = card_rows(client, auth, one_card)
        assert row["purchase_date"] == "2026-10-17"
        assert row["occurred_at"] == "2026-10-17T22:30:00-03:00"

    def test_notification_when_is_the_time_when_it_is_close(self, client, auth, one_card):
        posted = ms(2026, 10, 10, 14, 35)
        send(client, auth, detection(at=posted, when_ms=ms(2026, 10, 10, 14, 31)))
        assert pending(client, auth)[0]["occurred_at"] == "2026-10-10T14:31:00-03:00"
        send(client, auth, detection(at=posted, when_ms=ms(2026, 9, 1)))
        times = sorted(item["occurred_at"] for item in pending(client, auth))
        assert times == ["2026-10-10T14:31:00-03:00", "2026-10-10T14:35:00-03:00"]

    def test_the_owner_can_correct_the_time_and_the_source_time_stays(self, client, auth, one_account):
        send(client, auth, detection(kind="DEBIT_PURCHASE"))
        [item] = pending(client, auth)
        item = patch(client, auth, item, occurred_at="2026-10-09T20:15", amount=50, description="Padaria",
                     account_id=one_account)
        assert item["occurred_at"] == "2026-10-09T20:15:00-03:00"
        assert item["source_occurred_at"] == "2026-10-10T14:32:05-03:00"
        assert set(item["edited"]) >= {"occurred_at", "amount", "description"}
        # A conta enviada igual ao palpite confirma o palpite.
        assert item["confirm"] == []
        approve(client, auth, item)
        [row] = rows(client, auth, one_account)
        assert (row["date"], row["occurred_at"], row["amount"], row["description"]) == (
            "2026-10-09", "2026-10-09T20:15:00-03:00", 50, "Padaria",
        )


class TestOneMovementOneItem:
    def test_the_same_notification_twice_is_one_item(self, client, auth, one_card):
        same = detection()
        assert send(client, auth, same)[0]["status"] == "new"
        assert send(client, auth, same)[0]["status"] == "known"
        assert len(pending(client, auth)) == 1

    def test_samsung_first_then_the_bank_is_one_item_with_the_banks_words(self, client, auth, one_card):
        send(client, auth, detection(kind="PURCHASE", app=SAMSUNG, merchant="Padaria", card_last4="1234",
                                     at=ms(2026, 10, 10, 14, 32)))
        [item] = pending(client, auth)
        assert "method" in item["needs"]
        [result] = send(client, auth, detection(kind="CREDIT_PURCHASE", app=ITAU, merchant="PADARIA BOM PAO LTDA",
                                                card_last4="1234", at=ms(2026, 10, 10, 14, 33)))
        assert result["status"] == "merged"
        [item] = pending(client, auth)
        assert (item["entry_type"], item["description"]) == ("CARD", "PADARIA BOM PAO LTDA")
        assert "method" not in item["needs"]
        assert sorted(source["app"] for source in item["sources"]) == sorted([ITAU, SAMSUNG])

    def test_the_bank_first_then_samsung_changes_nothing(self, client, auth, one_card):
        send(client, auth, detection(at=ms(2026, 10, 10, 14, 32)))
        [result] = send(client, auth, detection(kind="PURCHASE", app=SAMSUNG, merchant="Outro nome",
                                                at=ms(2026, 10, 10, 14, 40)))
        assert result["status"] == "merged"
        [item] = pending(client, auth)
        assert item["description"] == "PADARIA BOM PAO"
        roles = {source["app"]: source["role"] for source in item["sources"]}
        assert roles == {ITAU: "SOURCE", SAMSUNG: "PAIRED"}

    def test_samsung_after_the_owner_approved_is_not_a_second_entry(self, client, auth, one_card):
        send(client, auth, detection(at=ms(2026, 10, 10, 14, 32)))
        approve(client, auth, pending(client, auth)[0])
        [result] = send(client, auth, detection(kind="PURCHASE", app=SAMSUNG, at=ms(2026, 10, 10, 14, 35)))
        assert result["status"] == "matched"
        assert pending(client, auth) == []
        assert len(card_rows(client, auth, one_card)) == 1

    def test_outside_the_window_or_another_card_they_are_two(self, client, auth, one_card):
        send(client, auth, detection(card_last4="1234", at=ms(2026, 10, 10, 14, 0)))
        send(client, auth, detection(kind="PURCHASE", app=SAMSUNG, card_last4="9999", at=ms(2026, 10, 10, 14, 1)))
        send(client, auth, detection(kind="PURCHASE", app=SAMSUNG, at=ms(2026, 10, 10, 14, 11)))
        assert len(pending(client, auth)) == 3

    def test_two_same_amount_purchases_stay_two(self, client, auth, one_card):
        send(
            client, auth,
            detection(at=ms(2026, 10, 10, 9, 0)),
            detection(at=ms(2026, 10, 10, 9, 4)),
            detection(kind="PURCHASE", app=SAMSUNG, at=ms(2026, 10, 10, 9, 1)),
            detection(kind="PURCHASE", app=SAMSUNG, at=ms(2026, 10, 10, 9, 5)),
        )
        items = pending(client, auth)
        assert len(items) == 2
        assert all(len(item["sources"]) == 2 for item in items)

    def test_the_banks_decline_cancels_the_held_samsung(self, client, auth, one_card):
        send(client, auth, detection(kind="PURCHASE", app=SAMSUNG, at=ms(2026, 10, 10, 14, 0)))
        [result] = send(client, auth, detection(kind="DECLINED", at=ms(2026, 10, 10, 14, 1)))
        assert result["status"] == "declined"
        assert pending(client, auth) == []
        assert decided(client, auth)[0]["reason"] == "declined"

    def test_samsungs_decline_does_not_cancel_the_bank(self, client, auth, one_card):
        send(client, auth, detection(at=ms(2026, 10, 10, 14, 0)))
        send(client, auth, detection(kind="DECLINED", app=SAMSUNG, at=ms(2026, 10, 10, 14, 1)))
        assert len(pending(client, auth)) == 1

    def test_a_wrong_pair_can_be_split(self, client, auth, one_card):
        send(
            client, auth,
            detection(at=ms(2026, 10, 10, 9, 0)),
            detection(kind="PURCHASE", app=SAMSUNG, at=ms(2026, 10, 10, 9, 1)),
        )
        [item] = pending(client, auth)
        samsung = next(source for source in item["sources"] if source["app"] == SAMSUNG)
        response = client.post(
            f"/api/inbox/{item['id']}/split",
            json={"version": item["version"], "source": "notification", "source_id": samsung["id"]},
            headers=auth,
        )
        assert response.status_code == 200, response.get_data(as_text=True)
        items = pending(client, auth)
        assert len(items) == 2
        assert all(len(entry["sources"]) == 1 for entry in items)
        # Os dois aprovados sao duas compras, cada uma com o client_id dela.
        for entry in items:
            if entry["needs"]:
                entry = patch(client, auth, entry, entry_type="CARD", card_id=one_card)
            approve(client, auth, entry)
        assert len(card_rows(client, auth, one_card)) == 2


class TestTheOwnerDecides:
    def test_a_vague_purchase_asks_credit_or_debit_and_remembers(self, client, auth, one_account):
        card_id = create_card(client, auth, "Itaú Visa")
        create_card(client, auth, "Itaú Black")
        send(client, auth, detection(kind="PURCHASE", app=SAMSUNG, card_last4="1234"))
        [item] = pending(client, auth)
        assert item["entry_type"] is None
        assert "method" in item["needs"]
        assert item["ready"] is False
        assert approve(client, auth, item, expected=400)["error"].startswith("Diga se foi no crédito")
        item = patch(client, auth, item, entry_type="CARD", card_id=card_id)
        assert item["needs"] == []
        approve(client, auth, item)
        assert len(card_rows(client, auth, card_id)) == 1
        [hint] = hints(client, auth)
        assert (hint["entry_type"], hint["card_id"]) == ("CARD", card_id)
        assert "final 1234" in hint["label"]

        send(client, auth, detection(kind="PURCHASE", app=SAMSUNG, card_last4="1234", at=ms(2026, 10, 12)))
        [item] = pending(client, auth)
        assert (item["entry_type"], item["card_id"], item["needs"], item["ready"]) == ("CARD", card_id, [], True)

    def test_an_unknown_card_is_chosen_once_and_decides_the_others(self, client, auth):
        create_card(client, auth, "Cartão A")
        chosen = create_card(client, auth, "Cartão B")
        send(
            client, auth,
            detection(card_last4="5678", at=ms(2026, 10, 10, 9, 0)),
            detection(card_last4="5678", amount_cents=1000, at=ms(2026, 10, 10, 18, 0)),
        )
        first, second = sorted(pending(client, auth), key=lambda item: item["occurred_at"])
        assert first["needs"] == ["card"] and second["needs"] == ["card"]
        approve(client, auth, first, card_id=chosen)
        [left] = pending(client, auth)
        assert (left["card_id"], left["needs"], left["ready"]) == (chosen, [], True)

    def test_a_guess_is_filled_but_waits_for_a_confirmation(self, client, auth):
        itau = create_card(client, auth, "Itaú Visa")
        create_card(client, auth, "BB Ourocard")
        send(client, auth, detection())
        [item] = pending(client, auth)
        assert item["card_id"] == itau
        assert item["confirm"] == ["card"]
        assert item["ready"] is False
        response = client.post("/api/inbox/approve-ready", json={"ids": [item["id"]]}, headers=auth)
        assert response.get_json()["skipped"][0]["reason"] == "needs_decision"
        approve(client, auth, item)
        assert hints(client, auth)[0]["card_id"] == itau

    def test_approve_ready_approves_what_needs_nothing(self, client, auth, one_card):
        # O unico cartao e um palpite ate o dono confirmar uma vez.
        send(client, auth, detection(at=ms(2026, 10, 9)))
        approve(client, auth, pending(client, auth)[0])
        send(client, auth, detection(at=ms(2026, 10, 10, 9)), detection(amount_cents=999, at=ms(2026, 10, 10, 10)))
        items = pending(client, auth)
        assert all(item["ready"] for item in items)
        response = client.post("/api/inbox/approve-ready", json={"ids": [item["id"] for item in items]}, headers=auth)
        assert len(response.get_json()["approved"]) == 2
        assert response.get_json()["pending_count"] == 0
        assert len(card_rows(client, auth, one_card)) == 3

    def test_a_typed_entry_is_offered_and_then_matched_by_memory(self, client, auth, one_account):
        typed = client.post(
            "/api/transactions",
            json={"amount": 45.9, "date": "2026-10-10", "category": "Padaria", "type": "EXPENSE",
                  "account_id": one_account},
            headers=auth,
        ).get_json()
        send(client, auth, detection(kind="DEBIT_PURCHASE"))
        [item] = pending(client, auth)
        assert [candidate["id"] for candidate in item["candidates"]] == [typed["id"]]
        matched = approve(client, auth, item, candidate={"table": "transactions", "id": typed["id"]})
        assert matched["state"] == "MATCHED"
        assert len(rows(client, auth, one_account)) == 1

        client.post(
            "/api/transactions",
            json={"amount": 20, "date": "2026-10-12", "category": "Padaria", "type": "EXPENSE",
                  "account_id": one_account},
            headers=auth,
        )
        # Lembrado ou nao, o que a notificacao trouxe passa pelo Aprovar: o
        # lancamento digitado vem como candidato, e o dono diz que e o mesmo.
        [result] = send(client, auth, detection(kind="DEBIT_PURCHASE", amount_cents=2000, at=ms(2026, 10, 12)))
        assert result["status"] == "new"
        [second] = pending(client, auth)
        assert second["reason"] == "possible_duplicate"
        assert len(second["candidates"]) == 1
        approve(client, auth, second, candidate={"table": "transactions", "id": second["candidates"][0]["id"]})
        assert pending(client, auth) == []
        # A notificacao ja explicou o primeiro: uma segunda de mesmo valor nao o rouba.
        [again] = send(client, auth, detection(kind="DEBIT_PURCHASE", at=ms(2026, 10, 10, 15)))
        assert again["status"] == "new"

    def test_deny_and_restore(self, client, auth, one_card):
        send(client, auth, detection())
        [item] = pending(client, auth)
        response = client.post(f"/api/inbox/{item['id']}/deny", json={"version": item["version"]}, headers=auth)
        assert response.get_json()["state"] == "DENIED"
        assert pending(client, auth) == []
        denied = decided(client, auth)[0]
        response = client.post(f"/api/inbox/{denied['id']}/restore", json={"version": denied["version"]}, headers=auth)
        assert response.status_code == 200
        assert len(pending(client, auth)) == 1
        assert card_rows(client, auth, one_card) == []

    def test_two_devices_do_not_overwrite_each_other(self, client, auth, one_card):
        send(client, auth, detection())
        [stale] = pending(client, auth)
        patch(client, auth, stale, description="No celular")
        response = client.patch(
            f"/api/inbox/{stale['id']}", json={"version": stale["version"], "description": "No computador"},
            headers=auth,
        )
        assert response.status_code == 409
        assert response.get_json()["item"]["description"] == "No celular"
        fresh = pending(client, auth)[0]
        approve(client, auth, fresh)
        late = client.post(f"/api/inbox/{fresh['id']}/deny", json={"version": fresh["version"]}, headers=auth)
        assert late.status_code == 409

    def test_an_entry_already_sent_by_the_phone_is_not_doubled(self, client, auth, one_account):
        found = detection(kind="DEBIT_PURCHASE")
        send(client, auth, found)
        response = client.post(
            "/api/transactions",
            json={"amount": 45.9, "date": "2026-10-10", "category": "Padaria", "type": "EXPENSE",
                  "account_id": one_account, "client_id": found["key"]},
            headers=auth,
        )
        assert response.status_code == 201
        assert response.get_json()["matched_inbox"] is True
        assert pending(client, auth) == []
        assert len(rows(client, auth, one_account)) == 1

    def test_forgetting_a_choice_asks_again(self, client, auth):
        create_card(client, auth, "A")
        chosen = create_card(client, auth, "B")
        send(client, auth, detection(card_last4="1111"))
        approve(client, auth, pending(client, auth)[0], card_id=chosen)
        [hint] = hints(client, auth)
        assert client.delete(f"/api/inbox/hints/{hint['id']}", headers=auth).status_code == 200
        send(client, auth, detection(card_last4="1111", at=ms(2026, 10, 11)))
        assert pending(client, auth)[0]["needs"] == ["card"]


class TestOwnTransfers:
    def test_pix_out_and_pix_in_notifications_make_one_transfer(self, client, auth):
        itau = create_account(client, auth, "Itaú")
        bb = create_account(client, auth, "BB")
        send(
            client, auth,
            detection(kind="PIX_OUT", amount_cents=30000, app=ITAU, at=ms(2026, 10, 10, 10, 0)),
            detection(kind="PIX_IN", amount_cents=30000, app=BB, at=ms(2026, 10, 10, 10, 0, 20)),
        )
        [item] = pending(client, auth)
        assert (item["entry_type"], item["account_id"], item["transfer_account_id"]) == ("TRANSFER", itau, bb)
        # As duas contas eram palpites (o app de cada banco): o dono confirma.
        assert sorted(item["confirm"]) == ["account", "transfer_account"]
        approve(client, auth, item)
        assert [entry["type"] for entry in rows(client, auth)] == ["TRANSFER"]
        # Cada lado lembrado: o proximo Pix recebido no BB ja sabe a conta.
        send(client, auth, detection(kind="PIX_IN", amount_cents=999, app=BB, at=ms(2026, 10, 12)))
        [item] = pending(client, auth)
        assert (item["entry_type"], item["account_id"], item["ready"]) == ("INCOME", bb, True)

    def test_typing_the_transfer_that_waits_in_aprovar_takes_its_place(self, client, auth):
        # Era 500 (o _absorb recebia um argumento a mais) e nada era gravado;
        # o celular, com a transferencia na fila, reenviava para sempre.
        itau = create_account(client, auth, "Itaú")
        bb = create_account(client, auth, "BB")
        send(
            client, auth,
            detection(kind="PIX_OUT", amount_cents=30000, app=ITAU, at=ms(2026, 10, 10, 10, 0)),
            detection(kind="PIX_IN", amount_cents=30000, app=BB, at=ms(2026, 10, 10, 10, 0, 20)),
        )
        [item] = pending(client, auth)
        assert item["entry_type"] == "TRANSFER"
        payload = {
            "amount": 300, "date": "2026-10-10", "account_id": itau, "transfer_account_id": bb,
            "client_id": str(uuid.uuid4()),
        }
        response = client.post("/api/transfers", json=payload, headers=auth)
        assert response.status_code == 201, response.get_data(as_text=True)
        assert response.get_json()["matched_inbox"] is True
        assert pending(client, auth) == []
        [closed] = decided(client, auth)
        assert (closed["state"], closed["target_id"]) == ("MATCHED", response.get_json()["id"])
        # O reenvio da fila (mesmo client_id) devolve o mesmo, sem gravar outro.
        again = client.post("/api/transfers", json=payload, headers=auth)
        assert again.status_code == 200
        assert [entry["type"] for entry in rows(client, auth)] == ["TRANSFER"]

    def test_a_one_sided_transfer_is_remembered(self, client, auth):
        itau = create_account(client, auth, "Itaú")
        brokerage = create_account(client, auth, "Corretora")
        send(client, auth, detection(
            kind="TRANSFER_OUT", amount_cents=100000, app=ITAU, at=ms(2026, 10, 10),
            merchant="TED 0001 MESMA TITULARIDADE",
        ))
        [item] = pending(client, auth)
        item = patch(client, auth, item, entry_type="TRANSFER", account_id=itau, transfer_account_id=brokerage)
        approve(client, auth, item)
        assert [entry["type"] for entry in rows(client, auth)] == ["TRANSFER"]

        send(client, auth, detection(
            kind="TRANSFER_OUT", amount_cents=75000, app=ITAU, at=ms(2026, 10, 15),
            merchant="TED 0002 MESMA TITULARIDADE",
        ))
        [item] = pending(client, auth)
        assert (item["entry_type"], item["transfer_account_id"], item["ready"]) == ("TRANSFER", brokerage, True)


class TestValidationAndIsolation:
    @pytest.mark.parametrize("change", [
        {"key": "x"},
        {"kind": "WHATEVER"},
        {"amount_cents": 0},
        {"card_last4": "12a4"},
        {"posted_ms": 5},
        {"app": "not a package"},
    ])
    def test_a_bad_detection_is_refused_alone(self, client, auth, change):
        good = detection()
        bad = {**detection(), **change}
        results = send(client, auth, good, bad)
        assert results[0]["status"] == "new"
        assert results[1]["status"] == "invalid"

    def test_another_user_sees_nothing_and_decides_nothing(self, client, auth, other_user, one_card):
        same = detection()
        send(client, auth, same)
        [item] = pending(client, auth)
        other = other_user["headers"]
        assert pending(client, other) == []
        assert client.post(f"/api/inbox/{item['id']}/approve", json={}, headers=other).status_code == 404
        assert client.patch(f"/api/inbox/{item['id']}", json={"amount": 1}, headers=other).status_code == 404
        # A mesma chave para outro usuario e outra deteccao.
        assert send(client, other, same)[0]["status"] == "new"
        approve(client, auth, item)
        hint_id = hints(client, auth)[0]["id"] if hints(client, auth) else None
        if hint_id:
            assert client.delete(f"/api/inbox/hints/{hint_id}", headers=other).status_code == 404

    def test_the_text_never_comes_in(self, client, auth, one_card):
        body = detection(title="Compra aprovada", text="Compra de R$ 45,90 no PADARIA")
        send(client, auth, body)
        db = importlib.import_module("db")
        with db.get_db() as conn:
            columns = [row[1] for row in conn.execute("PRAGMA table_info(notify_detections)").fetchall()]
        assert "text" not in columns and "title" not in columns
