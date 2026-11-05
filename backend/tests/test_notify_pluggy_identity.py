"""Notificacoes + Pluggy: um movimento, uma linha (docs/notifications-pluggy-design.md).

O que estes testes protegem (Fase 1a):

- a vaga de cada canal (I2): uma notificacao nunca esconde um lancamento da
  Pluggy, nem o contrario; dentro do mesmo canal, duas compras iguais ficam duas;
- a sucessao da Pluggy: a pendente que liquida com OUTRA id e a mesma
  observacao, entao o lancamento fica o mesmo (mesma id), revisado ou nao, na
  conta e no cartao (com as parcelas e o comprovante), no BB que arredonda, com
  gemeos, sem cruzar parcelas e sem nada sumir num pull vazio; a ligada (MATCHED)
  que sai sem sucessora vira `vanished` e a Conferencia aponta;
- o lado adivinhado de uma transferencia gravada (defeito R) passa a ser o do
  banco; editado pelo dono, fica;
- os gemeos C-H do desenho continuam certos.

Cada teste termina com `assert_identity()` (I1/I2).
"""

import importlib

import pytest

from identity_check import assert_identity
from open_finance_world import World, bank_tx, card_tx, connected, fake_pluggy, open_finance_module  # noqa: F401
from test_auto_record import confirm, notifications_on, rows_of
from test_inbox import BB, ITAU, detection, ms, send
from test_open_finance_auto import meupluggy

pytestmark = pytest.mark.usefixtures("any_bank_notifications")

BROKERAGE = "com.btg.pactual.digital.mobile"
SELF_TRANSFER = "04000000"


@pytest.fixture()
def world(client, auth, fake_pluggy):
    notifications_on(client, auth)
    client.patch("/api/open-finance/settings", json={"auto_record": True}, headers=auth)
    return World(client, auth, fake_pluggy)


def _setup(world, connector_name="Itaú", **kwargs):
    item_id, _p, made = connected(world, connector_name=connector_name, **kwargs)
    world.call("patch", "/api/open-finance/settings", json={"auto_record": True, "include_pending": True})
    return item_id, made


def of_rows(user_id, where="1=1", params=()):
    return rows_of("open_finance_transactions", f"user_id = ? AND {where}", (user_id, *params))


def of_row(user_id, pluggy_id):
    [row] = of_rows(user_id, "pluggy_transaction_id = ?", (pluggy_id,))
    return row


def posted_after_pending(world, account, pending_id, posted):
    """A pendente sai do banco e a liquidada chega com outra id."""
    world.fake.drop_tx(account, pending_id)
    return world.fake.add_tx(account, posted)


def with_bill(raw, month):
    raw["creditCardMetadata"] = {**(raw.get("creditCardMetadata") or {}), "billForecastDate": f"{month}-10"}
    return raw


# ---------------------------------------------------------------------------
# A e B: a pendente que liquida com outra id
# ---------------------------------------------------------------------------

class TestSuccession:
    def test_a_reviewed_row_keeps_its_id(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 4590, at=ms(2026, 10, 20, 14, 32), app=ITAU))
        [row] = world.transactions(mine)
        confirm(world.client, world.auth, {"table": "transactions", "id": row["id"]})
        pending_id = world.fake.add_tx(account, bank_tx(-45.9, "2026-10-20", "PADARIA", status="PENDING"))
        world.sync(item_id)
        posted_id = posted_after_pending(world, account, pending_id, bank_tx(-45.9, "2026-10-20", "COMPRA CARTAO DEB PADARIA"))
        body = world.sync(item_id)["result"]
        [after] = world.transactions(mine)
        assert after["id"] == row["id"]
        assert body["counts"].get("succeeded") == 1
        old, new = of_row(user["id"], pending_id), of_row(user["id"], posted_id)
        assert (old["role"], old["superseded_by"], old["target_id"]) == ("REMOVED", new["id"], None)
        # "E meu" sem mudar nada nao e toque (Fase 4): a Pluggy e a fonte.
        assert (new["role"], new["target_id"], new["conflict"]) == ("SOURCE", row["id"], None)
        assert world.pending() == []
        assert_identity(user["id"])

    def test_b_an_untouched_row_keeps_its_id_and_follows_the_new_id(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 4590, at=ms(2026, 10, 20, 14, 32), app=ITAU))
        [row] = world.transactions(mine)
        pending_id = world.fake.add_tx(account, bank_tx(-45.9, "2026-10-20", "PADARIA", status="PENDING"))
        world.sync(item_id)
        [linked] = world.transactions(mine)
        assert (linked["id"], linked["source_id"]) == (row["id"], pending_id)
        posted_id = posted_after_pending(world, account, pending_id, bank_tx(-45.9, "2026-10-20", "COMPRA CARTAO DEB PADARIA"))
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert (after["id"], after["source_type"], after["source_id"]) == (row["id"], "OPEN_FINANCE", posted_id)
        assert after["needs_review"] == 0  # padaria: comerciante conhecido (Fase 4)
        new = of_row(user["id"], posted_id)
        assert (new["role"], new["target_id"]) == ("SOURCE", row["id"])
        assert_identity(user["id"])

    def test_b_pluggy_only_pending_posts_under_a_new_id(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        pending_id = world.fake.add_tx(account, bank_tx(-45.9, "2026-10-20", "PADARIA", status="PENDING"))
        world.sync(item_id)
        [row] = world.transactions(mine)
        posted_id = posted_after_pending(world, account, pending_id, bank_tx(-45.9, "2026-10-21", "COMPRA PADARIA"))
        world.sync(item_id)
        [after] = world.transactions(mine)
        # Intocada e desta transacao: a data do banco vale, e o snapshot acompanha.
        assert (after["id"], after["source_id"], after["date"]) == (row["id"], posted_id, "2026-10-21")
        new = of_row(user["id"], posted_id)
        assert new["role"] == "SOURCE"
        open_finance_inbox = importlib.import_module("services.open_finance_inbox")
        db = importlib.import_module("db")
        with db.get_db() as conn:
            assert open_finance_inbox.untouched(conn, user["id"], new)
        assert_identity(user["id"])

    def test_b_on_a_card_purchase_keeps_installments_and_the_receipt(self, world, user):
        item_id, made = _setup(world, bank=False, card=True)
        account, _of, card = made["card"]
        send(world.client, world.auth, detection("CREDIT_PURCHASE", 30000, at=ms(2026, 10, 20, 10, 0), app=ITAU,
                                                 installments=3, merchant="LOJA X"))
        rows = world.card_rows(card)
        assert len(rows) == 3
        pending_id = world.fake.add_tx(account, card_tx(
            100, "2026-10-20", "LOJA X", installment=1, total_installments=3, total_amount=300,
            purchase_date="2026-10-20", docs_sign=True, status="PENDING",
        ))
        world.sync(item_id)
        first = min(rows, key=lambda row: row["installment_info"])
        receipt = world.client.post(
            f"/api/cc-expenses/{first['id']}/attachments",
            data={"file": (__import__("io").BytesIO(b"%PDF-1.4\n%%EOF\n"), "nota.pdf")},
            headers=world.auth, content_type="multipart/form-data",
        )
        assert receipt.status_code == 201, receipt.get_data(as_text=True)
        posted_id = posted_after_pending(world, account, pending_id, card_tx(
            100, "2026-10-20", "LOJA X", installment=1, total_installments=3, total_amount=300,
            purchase_date="2026-10-20", docs_sign=True,
        ))
        world.sync(item_id)
        after = world.card_rows(card)
        assert sorted((row["id"], row["installment_info"], row["amount"]) for row in after) == sorted(
            (row["id"], row["installment_info"], row["amount"]) for row in rows
        )
        stored = rows_of("cc_expenses", "user_id = ? AND card_id = ?", (user["id"], card))
        assert {row["client_id"] for row in stored} == {f"pluggy:{posted_id}"}
        files = world.call("get", f"/api/cc-expenses/{first['id']}/attachments")
        assert len(files) == 1
        assert_identity(user["id"])

    def test_a_card_succession_keeps_the_invoice_and_a_later_mirror_moves_it(self, world, user):
        item_id, made = _setup(world, bank=False, card=True)
        account, _of, card = made["card"]
        pending = with_bill(card_tx(80, "2026-10-20", "SMART FIT", docs_sign=True, status="PENDING"), "2026-11")
        world.fake.add_tx(account, pending)
        world.sync(item_id)
        [row] = world.card_rows(card)
        before = (row["id"], row["invoice_month"], row["invoice_year"])
        posted = with_bill(card_tx(80, "2026-10-20", "SMART FIT", docs_sign=True), "2026-11")
        posted_after_pending(world, account, pending["id"], posted)
        world.sync(item_id)
        [row] = world.card_rows(card)
        assert (row["id"], row["invoice_month"], row["invoice_year"]) == before
        # O banco passa a compra para a fatura seguinte: o espelho ainda move.
        world.fake.transactions[account][0]["creditCardMetadata"]["billForecastDate"] = "2026-12-10"
        world.sync(item_id)
        [row] = world.card_rows(card)
        assert (row["id"], row["invoice_month"], row["invoice_year"]) == (before[0], 12, 2026)
        assert_identity(user["id"])

    def test_banco_do_brasil_rounding_succeeds_too(self, world, user):
        item_id, made = _setup(world, connector_name="Banco do Brasil")
        account, _of, mine = made["bank"]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 1819, at=ms(2026, 10, 21, 12, 0), app=BB))
        [row] = world.transactions(mine)
        pending_id = world.fake.add_tx(account, bank_tx(-19, "2026-10-21", "COMPRA COM CARTAO", status="PENDING"))
        world.sync(item_id)
        posted_after_pending(world, account, pending_id, bank_tx(-19, "2026-10-21", "COMPRA COM CARTAO"))
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert (after["id"], after["amount"]) == (row["id"], 18.19)
        assert_identity(user["id"])

    def test_twin_pendings_post_as_twins(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        first = world.fake.add_tx(account, bank_tx(-8, "2026-10-21", "CAFE", status="PENDING"))
        second = world.fake.add_tx(account, bank_tx(-8, "2026-10-21", "CAFE", status="PENDING"))
        world.sync(item_id)
        ids = sorted(row["id"] for row in world.transactions(mine))
        assert len(ids) == 2
        posted_after_pending(world, account, first, bank_tx(-8, "2026-10-21", "CAFE"))
        posted_after_pending(world, account, second, bank_tx(-8, "2026-10-21", "CAFE"))
        body = world.sync(item_id)["result"]
        assert sorted(row["id"] for row in world.transactions(mine)) == ids
        assert body["counts"].get("succeeded") == 2
        assert_identity(user["id"])

    def test_never_across_installment_numbers(self, world, user):
        item_id, made = _setup(world, bank=False, card=True)
        account, _of, _card = made["card"]
        pending_id = world.fake.add_tx(account, card_tx(
            100, "2026-10-20", "LOJA X", installment=1, total_installments=3, total_amount=300,
            purchase_date="2026-10-20", docs_sign=True, status="PENDING",
        ))
        world.sync(item_id)
        second_id = posted_after_pending(world, account, pending_id, card_tx(
            100, "2026-10-20", "LOJA X", installment=2, total_installments=3, purchase_date="2026-10-20",
            docs_sign=True,
        ))
        body = world.sync(item_id)["result"]
        assert "succeeded" not in body["counts"]
        assert of_row(user["id"], pending_id)["superseded_by"] is None
        assert of_row(user["id"], second_id)["role"] == "COVERED"
        assert_identity(user["id"])

    def test_an_empty_pull_vanishes_nothing_and_succeeds_nothing(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        pending_id = world.fake.add_tx(account, bank_tx(-45.9, "2026-10-20", "PADARIA", status="PENDING"))
        world.sync(item_id)
        [row] = world.transactions(mine)
        world.fake.drop_tx(account, pending_id)
        body = world.sync(item_id)["result"]
        assert [entry["id"] for entry in world.transactions(mine)] == [row["id"]]
        assert (body["removed"], body["counts"].get("succeeded")) == (0, None)
        kept = of_row(user["id"], pending_id)
        assert (kept["role"], kept["conflict"]) == ("SOURCE", None)
        assert_identity(user["id"])

    def test_a_matched_row_that_leaves_without_successor_is_flagged(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 4590, at=ms(2026, 10, 20, 14, 32), app=ITAU))
        [row] = world.transactions(mine)
        # Tocado pelo dono (outra categoria): a Pluggy so liga.
        confirm(world.client, world.auth, {"table": "transactions", "id": row["id"], "category_id": world.category_id("Lazer")})
        pending_id = world.fake.add_tx(account, bank_tx(-45.9, "2026-10-20", "PADARIA", status="PENDING"))
        world.sync(item_id)
        assert of_row(user["id"], pending_id)["role"] == "MATCHED"
        world.fake.drop_tx(account, pending_id)
        world.fake.add_tx(account, bank_tx(-30, "2026-10-24", "MERCADO"))
        world.sync(item_id)
        gone = of_row(user["id"], pending_id)
        assert (gone["role"], gone["conflict"]) == ("MATCHED", "vanished")
        assert row["id"] in [entry["id"] for entry in world.transactions(mine)]
        conflicts = [
            conflict
            for item in world.overview()["items"] for entry in item["accounts"]
            for conflict in ((entry.get("check") or {}).get("conflicts") or [])
        ]
        assert [(entry["amount"], entry["reason"]) for entry in conflicts] == [(-45.9, "vanished")]
        assert_identity(user["id"])

    def test_the_35_day_window_never_succeeds_across_weeks(self, world, user):
        # Uma pendente de 20 dias atras ainda liquida pela sucessao; uma linha de
        # 20 dias que sumiu nunca e "continuada" por uma nova de hoje.
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        old_pending = world.fake.add_tx(account, bank_tx(-45.9, "2026-10-07", "PADARIA", status="PENDING"))
        old_posted = world.fake.add_tx(account, bank_tx(-8, "2026-10-07", "CAFE"))
        # O pull de quando a conta foi mapeada nao trouxe nada: o primeiro de
        # verdade le os 30 dias da primeira busca.
        db = importlib.import_module("db")
        with db.get_db() as conn:
            conn.execute("UPDATE open_finance_accounts SET synced_until = NULL WHERE user_id = ?", (user["id"],))
        world.sync(item_id)
        before = {row["amount"]: row["id"] for row in world.transactions(mine)}
        posted_after_pending(world, account, old_pending, bank_tx(-45.9, "2026-10-08", "PADARIA"))
        new_cafe = posted_after_pending(world, account, old_posted, bank_tx(-8, "2026-10-27", "CAFE"))
        world.sync(item_id)
        after = sorted((row["amount"], row["date"], row["id"]) for row in world.transactions(mine))
        assert after[1] == (45.9, "2026-10-08", before[45.9])
        # O cafe de 20 dias saiu (intocado e do banco) e o de hoje e outro.
        assert after[0][:2] == (8.0, "2026-10-27") and after[0][2] != before[8.0]
        assert of_row(user["id"], old_posted)["superseded_by"] is None
        assert of_row(user["id"], new_cafe)["role"] == "SOURCE"
        assert_identity(user["id"])


# ---------------------------------------------------------------------------
# Gemeos e as duas ordens (C-H do desenho): continuam certos
# ---------------------------------------------------------------------------

class TestTwins:
    def test_c_two_identical_3x_purchases_are_six_installments(self, world, user):
        item_id, made = _setup(world, bank=False, card=True)
        account, _of, card = made["card"]
        for minute in (0, 5):
            send(world.client, world.auth, detection("CREDIT_PURCHASE", 30000, at=ms(2026, 10, 20, 10, minute),
                                                     app=ITAU, installments=3, merchant="LOJA X"))
        for _ in range(2):
            world.fake.add_tx(account, card_tx(
                100, "2026-10-20", "LOJA X", installment=1, total_installments=3, total_amount=300,
                purchase_date="2026-10-20", docs_sign=True,
            ))
        world.sync(item_id)
        assert len(world.card_rows(card)) == 6
        assert_identity(user["id"])

    def test_d_two_coffees_both_notified(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 800, at=ms(2026, 10, 21, 8, 0), app=ITAU, merchant="CAFE"))
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 800, at=ms(2026, 10, 21, 8, 30), app=ITAU, merchant="CAFE"))
        world.fake.add_tx(account, bank_tx(-8, "2026-10-21", "CAFE"), bank_tx(-8, "2026-10-21", "CAFE"))
        world.sync(item_id)
        assert len(world.transactions(mine)) == 2
        assert_identity(user["id"])

    def test_e_two_coffees_one_notified(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 800, at=ms(2026, 10, 21, 8, 0), app=ITAU, merchant="CAFE"))
        world.fake.add_tx(account, bank_tx(-8, "2026-10-21", "CAFE"), bank_tx(-8, "2026-10-21", "CAFE"))
        world.sync(item_id)
        assert len(world.transactions(mine)) == 2
        assert_identity(user["id"])

    def test_f_pluggy_first_then_the_notification(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        world.fake.add_tx(account, bank_tx(-45.9, "2026-10-20", "COMPRA CARTAO DEB PADARIA"))
        world.sync(item_id)
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 4590, at=ms(2026, 10, 20, 14, 32), app=ITAU))
        assert len(world.transactions(mine)) == 1
        assert_identity(user["id"])

    def test_g_two_coffees_from_pluggy_then_two_notifications(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        world.fake.add_tx(account, bank_tx(-8, "2026-10-21", "CAFE"), bank_tx(-8, "2026-10-21", "CAFE"))
        world.sync(item_id)
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 800, at=ms(2026, 10, 21, 8, 0), app=ITAU, merchant="CAFE"))
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 800, at=ms(2026, 10, 21, 8, 30), app=ITAU, merchant="CAFE"))
        assert len(world.transactions(mine)) == 2
        assert_identity(user["id"])

    def test_three_coffees_three_notifications_three_bank_lines(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        for minute in (0, 20, 40):
            send(world.client, world.auth, detection("DEBIT_PURCHASE", 800, at=ms(2026, 10, 21, 8, minute), app=ITAU,
                                                     merchant="CAFE"))
        world.fake.add_tx(account, *(bank_tx(-8, "2026-10-21", "CAFE") for _ in range(3)))
        world.sync(item_id)
        assert len(world.transactions(mine)) == 3
        assert_identity(user["id"])

    def test_h_pix_to_the_brokerage_notified_on_both_sides(self, world, user):
        made = meupluggy(world)
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        itau_account, _o, itau = made["itau:0001/1-1"]
        broker_account, _b, corretora = made["btg:0002/2-2X"]
        send(
            world.client, world.auth,
            detection("PIX_OUT", 50000, at=ms(2026, 10, 22, 9, 0), app=ITAU, merchant=None, counterparty="Fulano Dono"),
            detection("TRANSFER_IN", 50000, at=ms(2026, 10, 22, 9, 1), app=BROKERAGE, merchant=None),
        )
        world.fake.add_tx(itau_account, bank_tx(-500, "2026-10-22", "PIX ENVIADO", category_id=SELF_TRANSFER))
        world.fake.add_tx(broker_account, bank_tx(500, "2026-10-22", "RECEBIMENTO TRANSFERÊNCIA", category_id=SELF_TRANSFER))
        for item in made["items"].values():
            world.sync(item)
        rows = [row for row in world.transactions() if row["amount"] == 500.0]
        assert [(row["type"], row["account_id"], row["transfer_account_id"]) for row in rows] == [
            ("TRANSFER", itau, corretora)
        ]
        assert_identity(user["id"])


# ---------------------------------------------------------------------------
# R: o lado adivinhado de uma transferencia gravada segue o banco
# ---------------------------------------------------------------------------

def _btg_notifies_500_in(world):
    send(world.client, world.auth, detection("TRANSFER_IN", 50000, at=ms(2026, 10, 22, 9, 0), app=BROKERAGE, merchant=None))


def _bank_shows_itau_to_the_brokerage(world, made):
    world.fake.add_tx(made["itau:0001/1-1"][0], bank_tx(-500, "2026-10-22", "PIX ENVIADO", category_id=SELF_TRANSFER))
    world.fake.add_tx(made["btg:0002/2-2X"][0], bank_tx(500, "2026-10-22", "RECEBIMENTO TRANSFERÊNCIA",
                                                       category_id=SELF_TRANSFER))


def _account_id(world, name):
    return next(row["id"] for row in world.call("get", "/api/accounts") if row["name"] == name)


def _balance(world, account_id):
    return next(row["balance"] for row in world.call("get", "/api/accounts") if row["id"] == account_id)


class TestGuessedSide:
    @pytest.mark.parametrize("order", [("itau", "btg"), ("btg", "itau")])
    def test_r_the_guessed_origin_follows_the_bank(self, world, user, order):
        made = meupluggy(world)
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        itau, corretora = made["itau:0001/1-1"][2], made["corretora"]
        btg = _account_id(world, "BTG conta corrente")
        _btg_notifies_500_in(world)
        [recorded] = [row for row in world.transactions() if row["amount"] == 500.0]
        assert (recorded["account_id"], recorded["transfer_account_id"]) == (btg, corretora)
        before = {account: _balance(world, account) for account in (itau, btg)}
        _bank_shows_itau_to_the_brokerage(world, made)
        for bank in order:
            world.sync(made["items"][bank])
        rows = [row for row in world.transactions() if row["amount"] == 500.0]
        assert [(row["id"], row["type"], row["account_id"], row["transfer_account_id"]) for row in rows] == [
            (recorded["id"], "TRANSFER", itau, corretora)
        ]
        assert rows[0]["description"] == "Itaú -> BTG Corretora"
        assert _balance(world, itau) == before[itau] - 500
        assert _balance(world, btg) == before[btg] + 500
        assert_identity(user["id"])

    def test_r_an_origin_the_owner_edited_stays(self, world, user):
        made = meupluggy(world)
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        corretora = made["corretora"]
        bb = made["bb:0003/3-3"][2]
        _btg_notifies_500_in(world)
        [recorded] = [row for row in world.transactions() if row["amount"] == 500.0]
        edited = world.client.patch(
            f"/api/transactions/{recorded['id']}", json={"account_id": bb}, headers=world.auth,
        )
        assert edited.status_code == 200, edited.get_data(as_text=True)
        _bank_shows_itau_to_the_brokerage(world, made)
        world.sync(made["items"]["itau"])
        rows = [row for row in world.transactions() if row["amount"] == 500.0 and row["type"] == "TRANSFER"]
        assert [(row["id"], row["account_id"], row["transfer_account_id"]) for row in rows] == [
            (recorded["id"], bb, corretora)
        ]
        assert_identity(user["id"])


# ---------------------------------------------------------------------------
# Os canais: uma notificacao nunca esconde um lancamento da Pluggy
# ---------------------------------------------------------------------------

class TestChannels:
    def test_claim_helpers_are_scoped_per_channel(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 4590, at=ms(2026, 10, 20, 14, 32), app=ITAU))
        [row] = world.transactions(mine)
        inbox = importlib.import_module("services.inbox")
        db = importlib.import_module("db")
        with db.get_db() as conn:
            assert inbox.notification_claimed(conn, user["id"], "transactions", row["id"])
            assert not inbox.pluggy_claimed(conn, user["id"], "transactions", row["id"])
        world.fake.add_tx(account, bank_tx(-45.9, "2026-10-20", "COMPRA CARTAO DEB PADARIA"))
        world.sync(item_id)
        with db.get_db() as conn:
            assert inbox.pluggy_claimed(conn, user["id"], "transactions", row["id"])
            [of] = of_rows(user["id"])
            assert not inbox.pluggy_claimed(conn, user["id"], "transactions", row["id"], exclude_item_id=of["item_id"])
        assert_identity(user["id"])

    def test_a_typed_row_is_free_for_both_channels(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        typed = world.call("post", "/api/transactions", json={
            "amount": 45.9, "date": "2026-10-20", "type": "EXPENSE", "category": "Alimentação", "account_id": mine,
            "description": "padaria",
        })
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 4590, at=ms(2026, 10, 20, 14, 32), app=ITAU))
        world.fake.add_tx(account, bank_tx(-45.9, "2026-10-20", "COMPRA CARTAO DEB PADARIA"))
        world.sync(item_id)
        assert [row["id"] for row in world.transactions(mine)] == [typed["id"]]
        assert_identity(user["id"])


def test_the_identity_script_reads_without_migrating(tmp_path, user, client, auth):
    """scripts/check_identity.py le o banco em modo somente leitura e, sem
    violacao, nao imprime nada."""
    import sqlite3
    import subprocess
    import sys

    config = importlib.import_module("config")
    copy = tmp_path / "copy.db"
    source = sqlite3.connect(config.DATABASE_PATH)
    target = sqlite3.connect(copy)
    source.backup(target)
    source.close()
    target.close()
    backend = importlib.import_module("identity_invariants").__file__.rsplit("identity_invariants", 1)[0]
    result = subprocess.run(
        [sys.executable, "scripts/check_identity.py", "--email", user["email"], "--database", str(copy)],
        cwd=backend, capture_output=True, text=True, check=False,
    )
    assert (result.returncode, result.stdout) == (0, ""), result.stderr
    missing = subprocess.run(
        [sys.executable, "scripts/check_identity.py", "--email", "ninguem@example.com", "--database", str(copy)],
        cwd=backend, capture_output=True, text=True, check=False,
    )
    assert missing.returncode == 2


# ===========================================================================
# Fase 1b
# ===========================================================================

PIX = "05000000"


def _amount_rows(world, amount, account_id=None):
    return [row for row in world.transactions(account_id) if row["amount"] == amount]


def _learn_self(user, name="Fulano Dono"):
    inbox = importlib.import_module("services.inbox")
    db = importlib.import_module("db")
    with db.get_db() as conn:
        inbox.learn_self(conn, user["id"], [{"kind": "PIX_OUT", "counterparty": name}])


# ---------------------------------------------------------------------------
# I: as duas pontas de um Pix entre contas do dono, cada uma no seu envio
# ---------------------------------------------------------------------------

class TestOwnTransferAbsorbs:
    def test_i_sides_in_separate_uploads_are_one_transfer(self, world, user):
        made = meupluggy(world)
        itau, bb = made["itau:0001/1-1"][2], made["bb:0003/3-3"][2]
        send(world.client, world.auth, detection("PIX_OUT", 70000, at=ms(2026, 10, 22, 9, 0), app=ITAU, merchant=None,
                                                 counterparty="Fulano Dono"))
        [first] = _amount_rows(world, 700.0)
        assert first["type"] == "EXPENSE"
        send(world.client, world.auth, detection("PIX_IN", 70000, at=ms(2026, 10, 22, 9, 1), app=BB, merchant=None,
                                                 counterparty="Fulano Dono"))
        rows = _amount_rows(world, 700.0)
        assert [(row["id"], row["type"], row["account_id"], row["transfer_account_id"]) for row in rows] == [
            (first["id"], "TRANSFER", itau, bb)
        ]
        assert world.pending() == []
        assert_identity(user["id"])

    def test_i_then_both_pluggy_sides_stay_one_transfer(self, world, user):
        made = meupluggy(world)
        itau, bb = made["itau:0001/1-1"][2], made["bb:0003/3-3"][2]
        send(world.client, world.auth, detection("PIX_OUT", 70000, at=ms(2026, 10, 22, 9, 0), app=ITAU, merchant=None,
                                                 counterparty="Fulano Dono"))
        send(world.client, world.auth, detection("PIX_IN", 70000, at=ms(2026, 10, 22, 9, 1), app=BB, merchant=None,
                                                 counterparty="Fulano Dono"))
        out_id = world.fake.add_tx(made["itau:0001/1-1"][0], bank_tx(-700, "2026-10-22", "PIX ENVIADO", category_id=PIX,
                                                                    counterparty="Fulano Dono"))
        in_id = world.fake.add_tx(made["bb:0003/3-3"][0], bank_tx(700, "2026-10-22", "PIX RECEBIDO", category_id=PIX,
                                                                 counterparty="Fulano Dono"))
        for item in made["items"].values():
            world.sync(item)
        rows = _amount_rows(world, 700.0)
        assert [(row["type"], row["account_id"], row["transfer_account_id"]) for row in rows] == [("TRANSFER", itau, bb)]
        assert {of_row(user["id"], out_id)["target_id"], of_row(user["id"], in_id)["target_id"]} == {rows[0]["id"]}
        assert_identity(user["id"])

    def test_one_side_notified_pluggy_brings_the_other(self, world, user):
        made = meupluggy(world)
        itau, bb = made["itau:0001/1-1"][2], made["bb:0003/3-3"][2]
        send(world.client, world.auth, detection("PIX_OUT", 70000, at=ms(2026, 10, 22, 9, 0), app=ITAU, merchant=None,
                                                 counterparty="Fulano Dono"))
        [first] = _amount_rows(world, 700.0)
        in_id = world.fake.add_tx(made["bb:0003/3-3"][0], bank_tx(700, "2026-10-22", "PIX RECEBIDO", category_id=PIX,
                                                                 counterparty="Fulano Dono"))
        world.sync(made["items"]["bb"])
        rows = _amount_rows(world, 700.0)
        assert [(row["id"], row["type"], row["account_id"], row["transfer_account_id"]) for row in rows] == [
            (first["id"], "TRANSFER", itau, bb)
        ]
        assert of_row(user["id"], in_id)["target_id"] == first["id"]
        # A ponta do Itau, depois, so liga.
        world.fake.add_tx(made["itau:0001/1-1"][0], bank_tx(-700, "2026-10-22", "PIX ENVIADO", category_id=PIX,
                                                           counterparty="Fulano Dono"))
        world.sync(made["items"]["itau"])
        assert len(_amount_rows(world, 700.0)) == 1
        assert_identity(user["id"])

    def test_a_third_party_on_the_other_side_stays_despesa(self, world, user):
        made = meupluggy(world)
        send(world.client, world.auth, detection("PIX_OUT", 70000, at=ms(2026, 10, 22, 9, 0), app=ITAU, merchant=None,
                                                 counterparty="Maria Silva"))
        send(world.client, world.auth, detection("PIX_IN", 70000, at=ms(2026, 10, 22, 9, 1), app=BB, merchant=None,
                                                 counterparty="Fulano Dono"))
        assert sorted(row["type"] for row in _amount_rows(world, 700.0)) == ["EXPENSE", "INCOME"]
        assert made  # o mundo tem as duas contas
        assert_identity(user["id"])


class TestNothingWaits:
    def test_an_own_transfer_with_one_side_is_recorded_at_once(self, world, user):
        made = meupluggy(world)
        itau, bb = made["itau:0001/1-1"][2], made["bb:0003/3-3"][2]
        _learn_self(user)
        send(world.client, world.auth, detection("PIX_OUT", 70000, at=ms(2026, 10, 22, 9, 0), app=ITAU, merchant=None,
                                                 counterparty="Fulano Dono"))
        [row] = _amount_rows(world, 700.0)
        assert (row["type"], row["account_id"], row["needs_review"]) == ("EXPENSE", itau, 1)
        assert world.pending() == []
        # A outra ponta chega e a mesma linha vira a transferencia.
        send(world.client, world.auth, detection("PIX_IN", 70000, at=ms(2026, 10, 22, 9, 2), app=BB, merchant=None,
                                                 counterparty="Fulano Dono"))
        [after] = _amount_rows(world, 700.0)
        assert (after["id"], after["type"], after["account_id"], after["transfer_account_id"]) == (
            row["id"], "TRANSFER", itau, bb,
        )
        assert_identity(user["id"])

    def test_a_one_sided_transfer_into_the_brokerage_waits(self, world, user):
        world.account("Itaú")
        world.account("Corretora", type_="BROKERAGE")
        send(world.client, world.auth, detection("TRANSFER_IN", 50000, at=ms(2026, 10, 22, 9, 0), app=BROKERAGE,
                                                 merchant=None))
        assert world.transactions() == []
        [item] = world.pending()
        assert item["entry_type"] == "TRANSFER"
        assert_identity(user["id"])


# ---------------------------------------------------------------------------
# A mesma compra com outro valor (J-S, design §3.7)
# ---------------------------------------------------------------------------

def _notify(world, amount_cents, day, merchant, kind="DEBIT_PURCHASE", hour=12, **extra):
    send(world.client, world.auth, detection(kind, amount_cents, at=ms(2026, 10, day, hour, 0), app=ITAU,
                                             merchant=merchant, **extra))


class TestNearMatch:
    def test_j_international_estimate_takes_the_banks_amount(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        _notify(world, 5230, 22, "AMAZON PRIME", international=True)
        [row] = world.transactions(mine)
        world.fake.add_tx(account, bank_tx(-55.10, "2026-10-22", "AMAZON PRIME BR"))
        body = world.sync(item_id)["result"]
        [after] = world.transactions(mine)
        assert (after["id"], after["amount"]) == (row["id"], 55.1)
        assert body["counts"].get("near_match") == 1
        assert world.pending() == []
        assert_identity(user["id"])

    def test_k_a_tip_takes_the_banks_amount(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        _notify(world, 10000, 22, "RESTAURANTE SABOR")
        [row] = world.transactions(mine)
        world.fake.add_tx(account, bank_tx(-112, "2026-10-22", "RESTAURANTE SABOR LTDA"))
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert (after["id"], after["amount"]) == (row["id"], 112.0)
        assert_identity(user["id"])

    def test_l_the_bank_first_then_the_notification(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        world.fake.add_tx(account, bank_tx(-55.10, "2026-10-22", "AMAZON PRIME BR"))
        world.sync(item_id)
        [row] = world.transactions(mine)
        _notify(world, 5230, 22, "AMAZON PRIME", international=True)
        [after] = world.transactions(mine)
        assert (after["id"], after["amount"]) == (row["id"], 55.1)
        assert_identity(user["id"])

    def test_m_two_notifications_one_bank_line_is_ambiguous(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        _notify(world, 3000, 22, "SUPERMERCADO BOM", hour=10)
        _notify(world, 4000, 22, "SUPERMERCADO BOM", hour=11)
        world.fake.add_tx(account, bank_tx(-34, "2026-10-22", "SUPERMERCADO BOM"))
        world.sync(item_id)
        assert sorted(row["amount"] for row in world.transactions(mine)) == [30.0, 34.0, 40.0]
        assert_identity(user["id"])

    def test_n_a_pix_never_near_matches(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        send(world.client, world.auth, detection("PIX_OUT", 10000, at=ms(2026, 10, 22, 9, 0), app=ITAU, merchant=None,
                                                 counterparty="Maria Silva"))
        world.fake.add_tx(account, bank_tx(-105, "2026-10-22", "PIX ENVIADO MARIA SILVA", category_id=PIX,
                                           counterparty="Maria Silva"))
        world.sync(item_id)
        assert sorted(row["amount"] for row in world.transactions(mine)) == [100.0, 105.0]
        assert_identity(user["id"])

    def test_another_merchant_never_near_matches(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        _notify(world, 10000, 22, "RESTAURANTE SABOR")
        world.fake.add_tx(account, bank_tx(-112, "2026-10-22", "POSTO SHELL"))
        world.sync(item_id)
        assert sorted(row["amount"] for row in world.transactions(mine)) == [100.0, 112.0]
        assert_identity(user["id"])

    def test_outside_the_band_is_another_purchase(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        _notify(world, 10000, 22, "RESTAURANTE SABOR")
        world.fake.add_tx(account, bank_tx(-140, "2026-10-22", "RESTAURANTE SABOR"))
        world.sync(item_id)
        assert sorted(row["amount"] for row in world.transactions(mine)) == [100.0, 140.0]
        assert_identity(user["id"])

    def test_installments_never_near_match(self, world, user):
        item_id, made = _setup(world, bank=False, card=True)
        account, _of, card = made["card"]
        _notify(world, 30000, 22, "LOJA X", kind="CREDIT_PURCHASE", installments=3)
        world.fake.add_tx(account, card_tx(110, "2026-10-22", "LOJA X", installment=1, total_installments=3,
                                           total_amount=330, purchase_date="2026-10-22", docs_sign=True))
        world.sync(item_id)
        stored = rows_of("cc_expenses", "user_id = ? AND card_id = ?", (user["id"], card))
        assert len({row["client_id"] for row in stored}) == 2
        assert_identity(user["id"])

    def test_o_an_amount_the_owner_typed_stays(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        _notify(world, 10000, 22, "RESTAURANTE SABOR")
        [row] = world.transactions(mine)
        world.call("patch", f"/api/transactions/{row['id']}", json={"amount": 105})
        bank_id = world.fake.add_tx(account, bank_tx(-112, "2026-10-22", "RESTAURANTE SABOR"))
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert (after["id"], after["amount"]) == (row["id"], 105.0)
        linked = of_row(user["id"], bank_id)
        assert (linked["role"], linked["target_id"], linked["conflict"], linked["conflict_amount_cents"]) == (
            "MATCHED", row["id"], "changed", 11200,
        )
        assert_identity(user["id"])

    def test_a_reviewed_and_recategorised_row_takes_the_banks_amount(self, world, user, client, auth):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        _notify(world, 10000, 22, "RESTAURANTE SABOR")
        [row] = world.transactions(mine)
        category = next(entry["id"] for entry in world.call("get", "/api/categories") if entry["name"] == "Lazer"
                        ) if any(entry["name"] == "Lazer" for entry in world.call("get", "/api/categories")) else None
        if category is None:
            category = world.call("post", "/api/categories", json={"name": "Lazer", "kind": "EXPENSE"})["id"]
        confirm(client, auth, {"table": "transactions", "id": row["id"], "category_id": category})
        world.fake.add_tx(account, bank_tx(-112, "2026-10-22", "RESTAURANTE SABOR"))
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert (after["id"], after["amount"], after["category_id"], after["needs_review"]) == (
            row["id"], 112.0, category, 0,
        )
        assert_identity(user["id"])

    def test_p_pending_then_posted_with_another_amount_under_a_new_id(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        pending_id = world.fake.add_tx(account, bank_tx(-100, "2026-10-22", "RESTAURANTE SABOR", status="PENDING"))
        world.sync(item_id)
        [row] = world.transactions(mine)
        posted_after_pending(world, account, pending_id, bank_tx(-112, "2026-10-22", "RESTAURANTE SABOR"))
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert (after["id"], after["amount"]) == (row["id"], 112.0)
        assert_identity(user["id"])

    def test_q_a_dollar_notification_is_recorded_at_ptax(self, world, user, monkeypatch):
        monkeypatch.setattr(importlib.import_module("services.fx"), "rate_on", lambda *args, **kwargs: 5.0)
        item_id, made = _setup(world, bank=False, card=True)
        account, _of, card = made["card"]
        _notify(world, 2000, 22, "OPENAI", kind="CREDIT_PURCHASE", currency="USD")
        [row] = world.card_rows(card)
        assert row["amount"] == 100.0
        assert world.pending() == []
        raw = card_tx(104.5, "2026-10-22", "OPENAI *CHATGPT", docs_sign=True)
        raw.update({"currencyCode": "USD", "amount": 20.0, "amountInAccountCurrency": 104.5})
        bank_id = world.fake.add_tx(account, raw)
        world.sync(item_id)
        [after] = world.card_rows(card)
        assert (after["id"], after["amount"]) == (row["id"], 104.5)
        assert of_row(user["id"], bank_id)["original_currency"] == "USD"
        assert_identity(user["id"])

    def test_q_without_ptax_it_waits(self, world, user, monkeypatch):
        fx = importlib.import_module("services.fx")

        def no_rate(*args, **kwargs):
            raise fx.FxUnavailable("sem PTAX")

        monkeypatch.setattr(fx, "rate_on", no_rate)
        _setup(world, bank=False, card=True)
        _notify(world, 2000, 22, "OPENAI", kind="CREDIT_PURCHASE", currency="USD")
        assert world.call("get", "/api/cc-expenses") == []
        assert len(world.pending()) == 1
        assert_identity(user["id"])

    def _claude(self, world, international=True):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        extra = {"international": True} if international else {}
        _notify(world, 11000, 17, "CLAUDE.AI", **extra)
        [row] = world.transactions(mine)
        world.sync(item_id)  # a Pluggy ainda nao lista
        assert [entry["id"] for entry in world.transactions(mine)] == [row["id"]]
        return item_id, account, mine, row

    def test_s_the_claude_charge_posted_nine_days_later(self, world, user):
        item_id, account, mine, row = self._claude(world)
        world.fake.add_tx(account, bank_tx(-112.40, "2026-10-26", "CLAUDE.AI SUBSCRIPTION"))
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert (after["id"], after["amount"], after["date"]) == (row["id"], 112.4, "2026-10-26")
        assert world.pending() == []
        assert_identity(user["id"])

    def test_s2_posted_with_the_purchase_date_and_the_same_amount(self, world, user):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        _notify(world, 11000, 21, "CLAUDE.AI", international=True)
        [row] = world.transactions(mine)
        world.fake.add_tx(account, bank_tx(-110, "2026-10-21", "CLAUDE.AI SUBSCRIPTION"))
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert (after["id"], after["amount"]) == (row["id"], 110.0)
        assert_identity(user["id"])

    def test_s3_domestic_nine_days_later_is_two_rows(self, world, user):
        item_id, account, mine, _row = self._claude(world, international=False)
        world.fake.add_tx(account, bank_tx(-112.40, "2026-10-26", "CLAUDE.AI SUBSCRIPTION"))
        world.sync(item_id)
        assert sorted(row["amount"] for row in world.transactions(mine)) == [110.0, 112.4]
        assert_identity(user["id"])


class TestNearRules:
    @pytest.mark.parametrize("merchant, other, expected", [
        ("SMART FIT", "SMARTFIT", True),
        ("PADARIA BOM PAO", "COMPRA CARTAO DEB PADARIA", True),
        ("CLAUDE.AI", "CLAUDE.AI SUBSCRIPTION", True),
        ("COMPRA", "COMPRA CARTAO DEBITO", False),
        ("LOJA ONLINE", "LOJA ONLINE", False),
        ("RESTAURANTE SABOR", "POSTO SHELL", False),
        (None, "PADARIA", False),
    ])
    def test_merchant_agrees(self, merchant, other, expected):
        assert importlib.import_module("services.inbox").merchant_agrees(merchant, None, other) is expected

    @pytest.mark.parametrize("notified, bank, international, expected", [
        (10000, 11000, True, True),
        (10000, 11001, True, False),
        (10000, 9000, True, True),
        (10000, 8999, True, False),
        (10000, 13000, False, True),
        (10000, 13001, False, False),
        (10000, 7000, False, True),
        (0, 100, False, False),
    ])
    def test_near_amount_band_edges(self, notified, bank, international, expected):
        assert importlib.import_module("services.inbox").near_amount(notified, bank, international) is expected

    def test_the_international_flag_must_be_a_boolean(self, world):
        [result] = send(world.client, world.auth, detection(international="sim"))
        assert result["status"] == "invalid"

    def test_the_flag_and_the_currency_are_stored(self, world, user):
        _setup(world)
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 1000, app=ITAU, international=True))
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 1000, at=ms(2026, 10, 11), app=ITAU, currency="EUR"))
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 1000, at=ms(2026, 10, 12), app=ITAU))
        stored = rows_of("notify_detections", "user_id = ? ORDER BY posted_ms", (user["id"],))
        assert [row["international"] for row in stored] == [1, 1, 0]


# ---------------------------------------------------------------------------
# Regressoes do gerador de cenarios (test_notify_pluggy_fuzz.py, sessao 5)
# ---------------------------------------------------------------------------

class TestFuzzRegressions:
    @pytest.mark.parametrize("order", [("itau", "btg"), ("btg", "itau")])
    def test_a_late_brokerage_notice_joins_the_transfer_pluggy_completed(self, world, user, order):
        """Semente 0: o Itau avisa o Pix para a Corretora, a Pluggy traz as duas
        pontas (uma TRANSFER), e so depois chega o aviso do BTG Investimentos
        (celular sem rede). A vaga da notificacao na ponta de entrada esta
        livre (a Pluggy ocupa a dela, I2): o aviso entra na mesma
        transferencia, nunca abre uma segunda."""
        made = meupluggy(world)
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        itau, corretora = made["itau:0001/1-1"][2], made["corretora"]
        send(world.client, world.auth, detection("PIX_OUT", 10838, at=ms(2026, 10, 21, 12, 4), app=ITAU, merchant=None,
                                                 counterparty="Fulano Dono"))
        world.fake.add_tx(made["itau:0001/1-1"][0], bank_tx(-108.38, "2026-10-21", "PIX ENVIADO",
                                                           category_id=SELF_TRANSFER, counterparty="Fulano Dono"))
        world.fake.add_tx(made["btg:0002/2-2X"][0], bank_tx(108.38, "2026-10-21", "RECEBIMENTO TRANSFERÊNCIA",
                                                           category_id=SELF_TRANSFER))
        for bank in order:
            world.sync(made["items"][bank])
        [recorded] = _amount_rows(world, 108.38)
        [result] = send(world.client, world.auth, detection("TRANSFER_IN", 10838, at=ms(2026, 10, 21, 12, 5),
                                                            app=BROKERAGE, merchant=None))
        assert result["status"] == "matched"
        rows = _amount_rows(world, 108.38)
        assert [(row["id"], row["type"], row["account_id"], row["transfer_account_id"]) for row in rows] == [
            (recorded["id"], "TRANSFER", itau, corretora)
        ]
        assert world.pending() == []
        assert_identity(user["id"])
