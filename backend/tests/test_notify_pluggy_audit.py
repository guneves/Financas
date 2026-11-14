"""Notificacoes + Pluggy: os defeitos achados na auditoria de 2026-11-13.

- a compra no cartao com a fatura ja paga nunca sai para ser refeita do jeito
  do banco (037: fatura paga e historia);
- o par aproximado que so ficou unico depois junta os dois ja gravados (duas
  compras no exterior na mesma loja, avisadas antes de o banco listar qualquer
  uma): uma linha por compra, nunca tres;
- o banco muda o valor de uma transacao sob a MESMA id: o lancamento revisado ou
  com outra categoria segue o banco, como na sucessao e no par aproximado; so o
  valor que o dono digitou fica;
- duas transferencias iguais entre contas do dono no mesmo dia sao duas;
- uma data torta da Pluggy pula a transacao, nunca derruba o pull.

Cada cenario termina com `assert_identity()`.
"""

import importlib
from datetime import date

import pytest

from finance_world import freeze
from identity_check import assert_identity
from open_finance_world import World, bank_tx, card_tx, connected, fake_pluggy, open_finance_module  # noqa: F401
from test_auto_record import category_id, confirm, notifications_on, rows_of
from test_inbox import ITAU, detection, ms, send
from test_open_finance_auto import meupluggy

pytestmark = pytest.mark.usefixtures("any_bank_notifications")

PIX = "05000000"


@pytest.fixture()
def world(client, auth, fake_pluggy):
    notifications_on(client, auth)
    return World(client, auth, fake_pluggy)


def _setup(world, **kwargs):
    item_id, _p, made = connected(world, connector_name="Itaú", **kwargs)
    world.call("patch", "/api/open-finance/settings", json={"auto_record": True, "include_pending": True})
    return item_id, made


def _of_row(pluggy_id):
    [row] = rows_of("open_finance_transactions", "pluggy_transaction_id = ?", (pluggy_id,))
    return row


def _set_amount(world, account, tx_id, amount):
    for tx in world.fake.transactions[account]:
        if tx["id"] == tx_id:
            tx["amount"], tx["status"] = amount, "POSTED"


class TestPaidInvoiceIsHistory:
    def test_a_paid_card_purchase_is_never_redone_the_banks_way(self, world, user, monkeypatch):
        item_id, made = _setup(world, bank=True, card=True)
        account, _of, card = made["card"]
        mine = made["bank"][2]
        # Fecha dia 3, vence dia 10: a compra de 26/10 e da fatura de novembro.
        send(world.client, world.auth, detection("CREDIT_PURCHASE", 12000, at=ms(2026, 10, 26, 23, 50), app=ITAU,
                                                 merchant="LOJA X"))
        [row] = world.card_rows(card)
        freeze(monkeypatch, date(2026, 11, 5))
        world.call("post", "/api/cc-expenses/pay-invoice", json={
            "card_id": card, "invoice_month": row["invoice_month"], "invoice_year": row["invoice_year"],
            "account_id": mine,
        })
        # O banco lista a compra com a data do dia seguinte (a virada da meia-noite).
        bank_id = world.fake.add_tx(account, card_tx(120, "2026-10-27", "LOJA X", docs_sign=True))
        world.sync(item_id)
        assert [(entry["id"], entry["status"]) for entry in world.card_rows(card)] == [(row["id"], "PAID")]
        linked = _of_row(bank_id)
        assert (linked["role"], linked["target_id"]) == ("MATCHED", row["id"])
        assert world.pending() == []
        assert_identity(user["id"])


class TestLateNearMatch:
    def _two_top_ups(self, world):
        item_id, made = _setup(world, bank=False, card=True)
        account, _of, card = made["card"]
        for day, cents in ((20, 10000), (21, 10500)):
            send(world.client, world.auth, detection(
                "CREDIT_PURCHASE", cents, at=ms(2026, 10, day, 12, 0), app=ITAU, merchant="CLAUDE.AI",
                international=True,
            ))
        return item_id, account, card

    def test_two_foreign_purchases_at_one_merchant_end_as_two_rows(self, world, user):
        item_id, account, card = self._two_top_ups(world)
        # A primeira linha do banco cabe nos dois avisos: ambigua, grava sozinha.
        first = world.fake.add_tx(account, card_tx(103, "2026-10-25", "CLAUDE.AI SUBSCRIPTION", docs_sign=True))
        world.sync(item_id)
        assert sorted(entry["amount"] for entry in world.card_rows(card)) == [100.0, 103.0, 105.0]
        # A segunda so cabe no aviso de 105: o par dela e unico, e o que sobra tambem.
        second = world.fake.add_tx(account, card_tx(114, "2026-10-26", "CLAUDE.AI SUBSCRIPTION", docs_sign=True))
        body = world.sync(item_id)["result"]
        assert sorted(entry["amount"] for entry in world.card_rows(card)) == [103.0, 114.0]
        assert body["counts"].get("near_match") == 2
        targets = {_of_row(first)["target_id"], _of_row(second)["target_id"]}
        assert len(targets) == 2 and None not in targets
        assert world.pending() == []
        assert_identity(user["id"])
        # Outro pull nao mexe em mais nada.
        world.sync(item_id)
        assert sorted(entry["amount"] for entry in world.card_rows(card)) == [103.0, 114.0]

    def test_a_bank_row_the_owner_touched_stays_two_rows(self, world, user):
        item_id, account, card = self._two_top_ups(world)
        world.fake.add_tx(account, card_tx(103, "2026-10-25", "CLAUDE.AI SUBSCRIPTION", docs_sign=True))
        world.sync(item_id)
        [alone] = [entry for entry in world.card_rows(card) if entry["amount"] == 103.0]
        confirm(world.client, world.auth, {
            "table": "cc_expenses", "id": alone["id"], "category_id": category_id(world.client, world.auth, "Lazer"),
        })
        world.fake.add_tx(account, card_tx(114, "2026-10-26", "CLAUDE.AI SUBSCRIPTION", docs_sign=True))
        world.sync(item_id)
        # A recategorizada pelo dono nunca sai: a Conferencia aponta a que sobrou.
        assert sorted(entry["amount"] for entry in world.card_rows(card)) == [100.0, 103.0, 114.0]
        assert_identity(user["id"])


class TestSameIdAmountChange:
    def _recorded(self, world):
        item_id, made = _setup(world)
        account, _of, mine = made["bank"]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 10000, at=ms(2026, 10, 22, 12, 0), app=ITAU,
                                                 merchant="RESTAURANTE SABOR"))
        pending_id = world.fake.add_tx(account, bank_tx(-100, "2026-10-22", "RESTAURANTE SABOR", status="PENDING"))
        world.sync(item_id)
        [row] = world.transactions(mine)
        return item_id, account, mine, pending_id, row

    def test_a_recategorised_row_takes_the_banks_amount(self, world, user):
        item_id, account, mine, pending_id, row = self._recorded(world)
        category = category_id(world.client, world.auth, "Lazer")
        confirm(world.client, world.auth, {"table": "transactions", "id": row["id"], "category_id": category})
        _set_amount(world, account, pending_id, -112)
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert (after["id"], after["amount"], after["category_id"]) == (row["id"], 112.0, category)
        bank = _of_row(pending_id)
        assert (bank["amount_cents"], bank["conflict"]) == (11200, None)
        # E o proximo ajuste do banco ainda vale.
        _set_amount(world, account, pending_id, -115)
        world.sync(item_id)
        assert [entry["amount"] for entry in world.transactions(mine)] == [115.0]
        assert_identity(user["id"])

    def test_an_amount_the_owner_typed_stays(self, world, user):
        item_id, account, mine, pending_id, row = self._recorded(world)
        world.call("patch", f"/api/transactions/{row['id']}", json={"amount": 105})
        _set_amount(world, account, pending_id, -112)
        world.sync(item_id)
        [after] = world.transactions(mine)
        assert (after["id"], after["amount"]) == (row["id"], 105.0)
        bank = _of_row(pending_id)
        assert (bank["conflict"], bank["conflict_amount_cents"]) == ("changed", 11200)
        assert_identity(user["id"])


@pytest.mark.parametrize("order", ["out_in_out_in", "out_out_in_in", "in_in_out_out", "out_in_in_out"])
def test_two_identical_own_transfers_are_two_transfers(world, user, order):
    made = meupluggy(world)
    world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
    itau, bb = made["itau:0001/1-1"][2], made["bb:0003/3-3"][2]
    for step in order.split("_"):
        key, amount, text = (
            ("itau:0001/1-1", -700, "PIX ENVIADO") if step == "out" else ("bb:0003/3-3", 700, "PIX RECEBIDO")
        )
        world.fake.add_tx(made[key][0], bank_tx(amount, "2026-10-22", text, category_id=PIX, counterparty="Fulano Dono"))
        world.sync(made["items"]["itau" if step == "out" else "bb"])
    rows = [row for row in world.transactions() if row["amount"] == 700.0]
    assert sorted((row["type"], row["account_id"], row["transfer_account_id"]) for row in rows) == [
        ("TRANSFER", itau, bb), ("TRANSFER", itau, bb),
    ]
    assert_identity(user["id"])


def test_a_malformed_date_skips_the_row_instead_of_failing_the_pull():
    rows = importlib.import_module("services.open_finance_rows")
    with pytest.raises(rows.Skip):
        rows.local_moment("2026-13-45")
    with pytest.raises(rows.Skip):
        rows.normalize_transaction({"id": "x", "amount": -10, "date": "2026-13-45"}, "BANK")
