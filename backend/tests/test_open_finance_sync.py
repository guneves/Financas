"""Open Finance -> Aprovar (services/open_finance_inbox.py).

O que estes testes protegem:
- nada vira lancamento sem aprovar; aprovar grava com a origem OPEN_FINANCE
  (source_id = id da Pluggy) ou, no cartao, o client_id da compra (035);
- puxar de novo, a folga de 7 dias e reconectar nao duplicam nada;
- a notificacao e a transacao da Pluggy da mesma compra sao UM item, chegue
  quem chegar primeiro, e a compra ja aprovada nao volta;
- parcela 2..n nunca vira item; a parcela 1 traz a compra inteira;
- estorno no cartao vira REFUND; pagamento de fatura nunca vira lancamento;
- as duas pontas de uma transferencia entre contas conectadas sao uma TRANSFER;
- a transacao que some ou muda de valor antes da aprovacao tira o item;
- outro usuario nao e tocado.
"""

import importlib
import uuid
from datetime import datetime

import pytest

from open_finance_world import World, bank_tx, card_tx, connected, fake_pluggy, open_finance_module  # noqa: F401
from test_inbox import BRT, ITAU, detection, ms, send


@pytest.fixture()
def world(client, auth, fake_pluggy):
    return World(client, auth, fake_pluggy)


def rows_of(world, table, where="1=1", params=()):
    db = importlib.import_module("db")
    with db.get_db() as conn:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table} WHERE {where}", params).fetchall()]


class TestPullIntoAprovar:
    def test_a_bank_debit_waits_ready_with_the_mapped_account(self, world):
        item_id, _pluggy_item, made = connected(world)
        pluggy_account, _of, mine = made["bank"]
        tx_id = world.fake.add_tx(pluggy_account, bank_tx(-45.9, "2026-10-20", "PADARIA BOM PAO"))
        body = world.sync(item_id)
        assert body["result"]["counts"] == {"new": 1}
        [item] = world.pending()
        assert (item["entry_type"], item["direction"], item["amount"]) == ("EXPENSE", "OUT", 45.9)
        assert (item["account_id"], item["occurred_at"], item["needs"], item["guessed"]) == (mine, "2026-10-20", [], [])
        assert item["client_key"] == f"pluggy:{tx_id}"
        [source] = item["sources"]
        assert source["source"] == "open_finance" and source["connector_name"] == "Itaú"
        assert world.transactions(mine) == []

    def test_income_is_income(self, world):
        item_id, _p, made = connected(world)
        world.fake.add_tx(made["bank"][0], bank_tx(8500, "2026-10-24", "SALARIO EMPRESA XYZ", category="Salary"))
        world.sync(item_id)
        [item] = world.pending()
        assert (item["entry_type"], item["direction"], item["category"]) == ("INCOME", "IN", "Receita")

    def test_approving_records_the_origin(self, world):
        item_id, _p, made = connected(world)
        tx_id = world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
        world.sync(item_id)
        [item] = world.pending()
        world.approve(item)
        [row] = world.transactions(made["bank"][2])
        stored = rows_of(world, "transactions", "id = ?", (row["id"],))[0]
        assert (stored["source_type"], stored["source_id"]) == ("OPEN_FINANCE", tx_id)
        assert stored["client_id"] == f"pluggy:{tx_id}"
        assert (row["type"], row["amount"], row["date"]) == ("EXPENSE", 45.9, "2026-10-20")

    def test_pending_status_is_skipped(self, world):
        item_id, _p, made = connected(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-10, "2026-10-26", status="PENDING"))
        body = world.sync(item_id)
        assert body["result"]["counts"] == {"skipped_pending": 1}
        assert world.pending() == []

    def test_an_existing_typed_entry_is_offered_as_the_same(self, world):
        item_id, _p, made = connected(world)
        mine = made["bank"][2]
        world.call("post", "/api/transactions", json={
            "account_id": mine, "amount": 45.9, "date": "2026-10-20", "type": "EXPENSE",
            "category": "Alimentação", "description": "Padaria",
        })
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
        world.sync(item_id)
        [item] = world.pending()
        assert item["reason"] == "possible_duplicate" and len(item["candidates"]) == 1
        world.approve(item, candidate={"table": "transactions", "id": item["candidates"][0]["id"]})
        assert len(world.transactions(mine)) == 1


class TestIdempotency:
    def test_a_repull_is_a_no_op(self, world):
        item_id, _p, made = connected(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"), bank_tx(-10, "2026-10-21"))
        world.sync(item_id)
        body = world.sync(item_id)
        assert body["result"]["counts"] == {"known": 2}
        assert len(world.pending()) == 2

    def test_after_approval_a_repull_brings_nothing_back(self, world):
        item_id, _p, made = connected(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
        world.sync(item_id)
        world.approve(world.pending()[0])
        world.sync(item_id)
        assert world.pending() == []
        assert len(world.transactions(made["bank"][2])) == 1

    def test_the_window_starts_30_days_back_then_overlaps_7_days(self, world, invoices_module, monkeypatch):
        item_id, _p, made = connected(world)
        pluggy_account = made["bank"][0]
        # A conexao ja fez o primeiro pull (o item estava UPDATED).
        assert world.fake.windows(pluggy_account) == ["2026-09-27"]
        monkeypatch.setattr(invoices_module, "local_today", lambda: datetime(2026, 11, 3).date())
        world.sync(item_id)
        assert world.fake.windows(pluggy_account)[-1] == "2026-10-20"

    def test_the_first_window_follows_the_setting(self, world):
        world.call("patch", "/api/open-finance/settings", json={"first_sync_days": 90})
        _item_id, _p, made = connected(world)
        assert world.fake.windows(made["bank"][0]) == ["2026-07-29"]

    def test_reconnecting_does_not_duplicate(self, world):
        item_id, pluggy_item, made = connected(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
        world.sync(item_id)
        world.call("delete", f"/api/open-finance/items/{item_id}", json={"confirm": "Itaú"})
        world.fake.items[pluggy_item] = {**world.fake.items.get(pluggy_item, {}), "id": pluggy_item,
                                         "status": "UPDATED", "connector": {"name": "Itaú"}}
        world.connect(pluggy_item)
        world.sync(item_id)
        assert len(world.pending()) == 1

    def test_a_manual_update_is_not_asked_twice_in_a_row(self, world):
        item_id, _p, _made = connected(world)
        world.sync(item_id)
        world.sync(item_id)
        assert len([call for call in world.fake.calls if call[0] == "update_item"]) == 1

    def test_no_update_within_an_hour_of_pluggys_last_read(self, world):
        # Conectar conta como uma atualizacao: a Pluggy recusa outra em menos de 1 h.
        item_id, pluggy_item, made = connected(world)
        recent = datetime.now().astimezone().isoformat()
        world.fake.items[pluggy_item]["lastUpdatedAt"] = recent
        db = importlib.import_module("db")
        with db.get_db() as conn:
            conn.execute("UPDATE open_finance_items SET pluggy_updated_at = ? WHERE id = ?", (recent, item_id))
        world.fake.add_tx(made["bank"][0], bank_tx(-10, "2026-10-26"))
        world.sync(item_id)
        assert not [call for call in world.fake.calls if call[0] == "update_item"]
        assert len(world.pending()) == 1

    def test_a_refused_update_still_pulls(self, world):
        pluggy_client = importlib.import_module("pluggy_client")
        item_id, _p, made = connected(world)
        world.fake.refuse_update = pluggy_client.PluggyError(
            "Client updates on this item are allowed at most every 1 hours.", status=400,
        )
        world.fake.add_tx(made["bank"][0], bank_tx(-10, "2026-10-26"))
        body = world.sync(item_id)
        assert body["result"]["counts"] == {"new": 1}
        assert world.overview()["items"][0]["last_sync_error"] is None

    def test_pluggy_down_is_an_error_for_the_button(self, world):
        pluggy_client = importlib.import_module("pluggy_client")
        item_id, _p, _made = connected(world)
        world.fake.refuse_update = pluggy_client.PluggyError("A Pluggy nao respondeu.")
        world.sync(item_id, expected=502)
        assert world.overview()["items"][0]["last_sync_error"] == "A Pluggy nao respondeu."


class TestSameMovementAsANotification:
    def test_notification_first_then_pluggy_is_one_item(self, world):
        item_id, _p, made = connected(world, connector_name="Itaú")
        mine = made["bank"][2]
        send(world.client, world.auth, detection(
            "DEBIT_PURCHASE", 4590, at=ms(2026, 10, 20, 14, 32), app=ITAU, merchant="PADARIA BOM PAO",
        ))
        [before] = world.pending()
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20", "COMPRA CARTAO DEB PADARIA"))
        body = world.sync(item_id)
        assert body["result"]["counts"] == {"merged": 1}
        [item] = world.pending()
        assert item["id"] == before["id"]
        assert {source["source"] for source in item["sources"]} == {"notification", "open_finance"}
        # A conta vem do mapeamento: certa, nao palpite.
        assert (item["account_id"], item["guessed"], item["needs"]) == (mine, [], [])
        assert item["description"] == "PADARIA BOM PAO"

    def test_pluggy_first_then_notification_is_one_item(self, world):
        item_id, _p, made = connected(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20", "COMPRA CARTAO DEB PADARIA"))
        world.sync(item_id)
        [before] = world.pending()
        [result] = send(world.client, world.auth, detection(
            "DEBIT_PURCHASE", 4590, at=ms(2026, 10, 20, 14, 32), app=ITAU, merchant="PADARIA BOM PAO",
        ))
        assert result["status"] == "merged" and result["item_id"] == before["id"]
        [item] = world.pending()
        assert item["description"] == "PADARIA BOM PAO"
        assert item["account_id"] == made["bank"][2]

    def test_a_card_purchase_without_method_joins_the_card_item(self, world):
        item_id, _p, made = connected(world, bank=False, card=True)
        card_id = made["card"][2]
        send(world.client, world.auth, detection("PURCHASE", 8990, at=ms(2026, 10, 22, 9, 0), app=ITAU))
        world.fake.add_tx(made["card"][0], card_tx(89.9, "2026-10-22", "SMART FIT", docs_sign=True))
        world.sync(item_id)
        [item] = world.pending()
        assert (item["entry_type"], item["card_id"], item["needs"]) == ("CARD", card_id, [])

    def test_an_approved_notification_is_not_brought_back(self, world):
        item_id, _p, made = connected(world)
        mine = made["bank"][2]
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 4590, at=ms(2026, 10, 20, 14, 32), app=ITAU))
        [item] = world.pending()
        world.approve(item, account_id=mine)
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
        body = world.sync(item_id)
        assert body["result"]["counts"] == {"matched": 1}
        assert world.pending() == []
        assert len(world.transactions(mine)) == 1

    def test_a_denied_notification_stays_denied(self, world):
        item_id, _p, made = connected(world)
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 4590, at=ms(2026, 10, 20, 14, 32), app=ITAU))
        [item] = world.pending()
        world.call("post", f"/api/inbox/{item['id']}/deny", json={"version": item["version"]})
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
        assert world.sync(item_id)["result"]["counts"] == {"denied": 1}
        assert world.pending() == []

    def test_two_same_purchases_stay_two(self, world):
        item_id, _p, made = connected(world)
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 1000, at=ms(2026, 10, 20, 9, 0), app=ITAU))
        world.fake.add_tx(made["bank"][0], bank_tx(-10, "2026-10-20"), bank_tx(-10, "2026-10-20"))
        world.sync(item_id)
        items = world.pending()
        assert len(items) == 2
        assert sorted(len(item["sources"]) for item in items) == [1, 2]

    def test_a_different_day_or_amount_is_not_the_same(self, world):
        item_id, _p, made = connected(world)
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 4590, at=ms(2026, 10, 23, 9, 0), app=ITAU))
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-26"), bank_tx(-45.91, "2026-10-23"))
        world.sync(item_id)
        assert len(world.pending()) == 3

    def test_a_split_separates_them_again(self, world):
        item_id, _p, made = connected(world)
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 4590, at=ms(2026, 10, 20, 9, 0), app=ITAU))
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
        world.sync(item_id)
        [item] = world.pending()
        source = next(entry for entry in item["sources"] if entry["source"] == "open_finance")
        world.call("post", f"/api/inbox/{item['id']}/split",
                   json={"version": item["version"], "source": "open_finance", "source_id": source["id"]})
        items = world.pending()
        assert len(items) == 2
        assert sorted(entry["sources"][0]["source"] for entry in items) == ["notification", "open_finance"]


class TestCardInstallments:
    def test_installment_one_is_the_purchase_and_the_rest_never_become_items(self, world):
        item_id, _p, made = connected(world, bank=False, card=True)
        pluggy_card, _of, card_id = made["card"]
        world.fake.add_tx(
            pluggy_card,
            card_tx(50, "2026-10-21", "LOJA X", installment=1, total_installments=3, purchase_date="2026-10-21T03:00:00.000Z",
                    docs_sign=True),
        )
        world.sync(item_id)
        [item] = world.pending()
        assert (item["entry_type"], item["amount"], item["installments"]) == ("CARD", 150.0, 3)
        world.approve(item)
        rows = world.card_rows(card_id)
        assert sorted(row["installment_info"] for row in rows) == ["1/3", "2/3", "3/3"]
        assert {row["client_id"] for row in rows} == {item["client_key"]}
        # As parcelas 2 e 3 chegam nos meses seguintes: cobertas, nunca itens.
        world.fake.add_tx(
            pluggy_card,
            card_tx(50, "2026-10-26", "LOJA X", installment=2, total_installments=3, docs_sign=True),
            card_tx(50, "2026-10-27", "LOJA X", installment=3, total_installments=3, docs_sign=True),
        )
        body = world.sync(item_id)
        assert body["result"]["counts"]["covered"] == 2
        assert world.pending() == []
        assert len(world.card_rows(card_id)) == 3

    def test_a_later_installment_of_an_old_purchase_is_covered_too(self, world):
        item_id, _p, made = connected(world, bank=False, card=True)
        world.fake.add_tx(made["card"][0], card_tx(55.9, "2026-10-20", installment=4, total_installments=6, docs_sign=True))
        assert world.sync(item_id)["result"]["counts"] == {"covered": 1}
        assert world.pending() == []

    def test_the_invoice_month_is_the_apps(self, world, invoices_module):
        item_id, _p, made = connected(world, bank=False, card=True)
        card_id = made["card"][2]
        world.fake.add_tx(made["card"][0], card_tx(100, "2026-10-25", "LOJA", docs_sign=True))
        world.sync(item_id)
        world.approve(world.pending()[0])
        [row] = world.card_rows(card_id)
        expected = invoices_module.compute_invoice_start("2026-10-25", 10, 3)
        assert (row["invoice_month"], row["invoice_year"]) == (expected["invoice_month"], expected["invoice_year"])


class TestRefundsAndInvoicePayments:
    def test_a_card_credit_is_a_refund(self, world):
        item_id, _p, made = connected(world, bank=False, card=True)
        pluggy_card, _of, card_id = made["card"]
        world.fake.add_tx(pluggy_card, card_tx(120, "2026-10-21", "LOJA"), card_tx(-30, "2026-10-22", "ESTORNO LOJA"),
                          card_tx(40, "2026-10-23", "LOJA 2"), card_tx(15, "2026-10-24", "LOJA 3"))
        world.sync(item_id)
        refund = next(item for item in world.pending() if item["direction"] == "IN")
        assert (refund["entry_type"], refund["amount"], refund["category"]) == ("CARD", 30.0, "Estorno")
        assert refund["recurring"] is None
        world.approve(refund)
        [row] = [row for row in world.card_rows(card_id) if row["kind"] == "REFUND"]
        assert (row["amount"], row["installment_info"]) == (30.0, "1/1")

    def test_invoice_payments_never_become_entries(self, world):
        item_id, _p, made = connected(world, card=True)
        world.fake.add_tx(made["bank"][0], bank_tx(-838.5, "2026-10-22", "PAGAMENTO FATURA", category_id="05100000"))
        world.fake.add_tx(made["card"][0], card_tx(-838.5, "2026-10-22", "PAGAMENTO RECEBIDO", category_id="05100000"))
        body = world.sync(item_id)
        assert body["result"]["counts"] == {"invoice_payment": 2}
        assert world.pending() == []
        card_account = next(
            account for account in world.overview()["items"][0]["accounts"] if account["type"] == "CREDIT"
        )
        # O pagamento ensinou o sinal do cartao (sandbox: compra negativa).
        assert (card_account["charge_sign"], card_account["charge_sign_source"]) == (-1, "payment")


class TestTransfers:
    def test_both_connected_sides_are_one_transfer(self, world):
        itau_item, _p1, itau = connected(world, connector_name="Itaú")
        bb_item, _p2, bb = connected(world, connector_name="Banco do Brasil")
        itau, bb = itau["bank"], bb["bank"]
        out_id = world.fake.add_tx(itau[0], bank_tx(-300, "2026-10-20", "PIX ENVIADO GUSTAVO", category_id="04020000"))
        world.fake.add_tx(bb[0], bank_tx(300, "2026-10-20", "PIX RECEBIDO GUSTAVO", category_id="04020000"))
        world.sync(itau_item)
        world.sync(bb_item)
        [item] = world.pending()
        assert (item["entry_type"], item["account_id"], item["transfer_account_id"]) == ("TRANSFER", itau[2], bb[2])
        assert item["needs"] == []
        world.approve(item)
        [row] = [row for row in world.transactions() if row["type"] == "TRANSFER"]
        assert (row["account_id"], row["transfer_account_id"], row["amount"]) == (itau[2], bb[2], 300.0)
        stored = rows_of(world, "transactions", "id = ?", (row["id"],))[0]
        assert (stored["source_type"], stored["source_id"]) == ("OPEN_FINANCE", out_id)
        assert len([row for row in world.transactions() if row["type"] != "TRANSFER"]) == 0

    def test_one_side_same_owner_asks_the_other_account(self, world):
        item_id, _p, made = connected(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-300, "2026-10-20", "PIX ENVIADO", category_id="04020000"))
        world.sync(item_id)
        [item] = world.pending()
        assert (item["entry_type"], item["reason"], item["needs"]) == ("TRANSFER", "own_transfer", ["transfer_account"])

    def test_a_third_party_pix_is_an_expense(self, world):
        item_id, _p, made = connected(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-80, "2026-10-20", "PIX ENVIADO ANA", category_id="05090004",
                                                   payment_method="PIX", counterparty="Ana Souza"))
        world.sync(item_id)
        [item] = world.pending()
        assert (item["entry_type"], item["reason"]) == ("EXPENSE", "external_transfer")

    def test_a_plain_purchase_never_pairs_as_a_transfer(self, world):
        itau_item, _p1, itau = connected(world, connector_name="Itaú")
        bb_item, _p2, bb = connected(world, connector_name="Banco do Brasil")
        itau, bb = itau["bank"], bb["bank"]
        world.fake.add_tx(itau[0], bank_tx(-300, "2026-10-20", "COMPRA LOJA"))
        world.fake.add_tx(bb[0], bank_tx(300, "2026-10-20", "PIX RECEBIDO", category_id="05070000"))
        world.sync(itau_item)
        world.sync(bb_item)
        assert sorted(item["entry_type"] for item in world.pending()) == ["EXPENSE", "INCOME"]


class TestVanished:
    def test_a_transaction_that_disappears_takes_its_item_out(self, world):
        item_id, _p, made = connected(world)
        tx_id = world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
        world.sync(item_id)
        world.fake.drop_tx(made["bank"][0], tx_id)
        assert world.sync(item_id)["result"]["removed"] == 1
        assert world.pending() == []
        [gone] = world.decided()
        assert (gone["state"], gone["reason"]) == ("REMOVED", "vanished")

    def test_with_a_notification_too_the_item_stays(self, world):
        item_id, _p, made = connected(world)
        send(world.client, world.auth, detection("DEBIT_PURCHASE", 4590, at=ms(2026, 10, 20, 9, 0), app=ITAU))
        tx_id = world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
        world.sync(item_id)
        world.fake.drop_tx(made["bank"][0], tx_id)
        world.sync(item_id)
        [item] = world.pending()
        assert [source["role"] for source in item["sources"] if source["source"] == "open_finance"] == ["REMOVED"]

    def test_a_changed_amount_replaces_the_item(self, world):
        item_id, _p, made = connected(world)
        tx_id = world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
        world.sync(item_id)
        world.fake.transactions[made["bank"][0]][0]["amount"] = -49.9
        world.sync(item_id)
        [item] = world.pending()
        assert item["amount"] == 49.9 and item["client_key"] == f"pluggy:{tx_id}"
        assert [entry["reason"] for entry in world.decided()] == ["changed"]

    def test_an_approved_one_is_left_alone(self, world):
        item_id, _p, made = connected(world)
        tx_id = world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
        world.sync(item_id)
        world.approve(world.pending()[0])
        world.fake.drop_tx(made["bank"][0], tx_id)
        world.sync(item_id)
        assert len(world.transactions(made["bank"][2])) == 1
        assert [entry["state"] for entry in world.decided()] == ["APPROVED"]

    def test_out_of_the_window_is_not_vanished(self, world, invoices_module, monkeypatch):
        item_id, _p, made = connected(world)
        tx_id = world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-21"))
        world.sync(item_id)
        # Um pull em 20/11 olha de 13/11 em diante: o de 21/10 ja nao esta na janela.
        monkeypatch.setattr(invoices_module, "local_today", lambda: datetime(2026, 11, 20).date())
        world.sync(item_id)
        world.fake.drop_tx(made["bank"][0], tx_id)
        world.sync(item_id)
        assert len(world.pending()) == 1


class TestOtherUser:
    def test_the_same_pluggy_transaction_for_two_users_is_two_rows(self, client, world, other_user):
        item_id, _p, made = connected(world)
        shared = bank_tx(-45.9, "2026-10-20")
        world.fake.add_tx(made["bank"][0], shared)
        world.sync(item_id)
        other = World(client, other_user["headers"], world.fake)
        other_item, _p2, other_made = connected(other)
        world.fake.add_tx(other_made["bank"][0], dict(shared))
        other.sync(other_item)
        assert len(world.pending()) == 1 and len(other.pending()) == 1
        assert world.pending()[0]["id"] != other.pending()[0]["id"]

    def test_another_users_notification_never_pairs(self, client, world, other_user):
        item_id, _p, made = connected(world)
        send(client, other_user["headers"], detection("DEBIT_PURCHASE", 4590, at=ms(2026, 10, 20, 9, 0), app=ITAU))
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
        world.sync(item_id)
        [item] = world.pending()
        assert [source["source"] for source in item["sources"]] == ["open_finance"]
        other_items = client.get("/api/inbox", headers=other_user["headers"]).get_json()["items"]
        assert [source["source"] for source in other_items[0]["sources"]] == ["notification"]


class TestBalanceCheck:
    def test_pluggy_balance_next_to_the_apps_never_adjusted(self, world):
        item_id, _p, made = connected(world)
        mine = made["bank"][2]
        world.call("post", "/api/transactions", json={
            "account_id": mine, "amount": 200, "date": "2026-10-01", "type": "INCOME", "category": "Receita",
        })
        [account] = world.overview()["items"][0]["accounts"]
        assert (account["pluggy_balance"], account["app_balance"], account["difference"]) == (1000.0, 200.0, 800.0)
        assert len(world.transactions(mine)) == 1


class TestBackgroundRound:
    def test_the_round_pulls_every_user_with_items(self, world, app_module):
        refresh = importlib.import_module("services.open_finance_refresh")
        item_id, _p, made = connected(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
        refresh.reset_attempts()
        results = refresh.refresh_all_users(__import__("time").time() + 7 * 3600)
        assert any(item_id in value for value in results.values())
        assert len(world.pending()) == 1
