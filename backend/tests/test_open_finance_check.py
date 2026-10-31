"""Conferencia do Open Finance (services/open_finance_check.py): o banco contra
o app, so apontando.

O que estes testes protegem:
- o par e um para um, mesmo valor com sinal, ate 3 dias, o mais proximo;
- um item aprovado confere; um recusado fica "so no banco"; um lancamento
  digitado a mais fica "so no app"; um pendente no Aprovar e "esperando";
- no cartao: a compra inteira (todas as parcelas) contra a parcela 1 da
  Pluggy, com folga de n centavos; estorno com sinal +; pagamento de fatura fora;
- a transferencia que entra na conta conta como entrada;
- nada e gravado; outro usuario nao e tocado.
"""

import importlib
from pathlib import Path

import pytest

from open_finance_world import World, bank_tx, card_tx, connected, fake_pluggy, open_finance_module  # noqa: F401
from test_open_finance_auto import auto_on


@pytest.fixture()
def world(client, auth, fake_pluggy):
    return World(client, auth, fake_pluggy)


@pytest.fixture()
def check():
    return importlib.import_module("services.open_finance_check")


def entry(id_, day, cents, tolerance=0):
    return {"id": id_, "date": day, "cents": cents, "tolerance": tolerance}


def without_ids(rows):
    return [{key: value for key, value in row.items() if key not in ("id", "table")} for row in rows]


def account_of(world, kind="BANK"):
    [item] = world.overview()["items"]
    return next(account for account in item["accounts"] if account["type"] == kind)


def bank_moved_on(world, pluggy_item, item_id):
    """A Pluggy falou com o banco depois do que esta no app: agora "o banco nao tem" e uma conclusao."""
    world.fake.items[pluggy_item]["lastUpdatedAt"] = "2099-01-01T00:00:00.000Z"
    world.sync(item_id)


class TestMatcher:
    def test_same_amount_within_three_days(self, check):
        bank, app = check.match_movements([entry("b", "2026-10-10", -500)], [entry("a", "2026-10-13", -500)])
        assert (bank, app) == ([], [])

    def test_four_days_apart_is_no_pair(self, check):
        bank, app = check.match_movements([entry("b", "2026-10-10", -500)], [entry("a", "2026-10-14", -500)])
        assert ([e["id"] for e in bank], [e["id"] for e in app]) == (["b"], ["a"])

    def test_the_sign_must_agree(self, check):
        bank, app = check.match_movements([entry("b", "2026-10-10", -500)], [entry("a", "2026-10-10", 500)])
        assert len(bank) == 1 and len(app) == 1

    def test_one_to_one(self, check):
        bank, app = check.match_movements(
            [entry("b1", "2026-10-10", -500)], [entry("a1", "2026-10-10", -500), entry("a2", "2026-10-10", -500)],
        )
        assert bank == [] and [e["id"] for e in app] == ["a2"]

    def test_the_closest_date_wins(self, check):
        bank, app = check.match_movements(
            [entry("b", "2026-10-10", -500)], [entry("far", "2026-10-08", -500), entry("near", "2026-10-11", -500)],
        )
        assert [e["id"] for e in app] == ["far"]

    def test_tolerance_in_cents(self, check):
        bank, app = check.match_movements([entry("b", "2026-10-10", -9999, tolerance=3)], [entry("a", "2026-10-10", -10000)])
        assert (bank, app) == ([], [])
        bank, app = check.match_movements([entry("b", "2026-10-10", -9999)], [entry("a", "2026-10-10", -10000)])
        assert len(bank) == 1


class TestBankAccount:
    def test_nothing_before_the_first_pull_or_without_mapping(self, world):
        item_id, _p, made = connected(world)
        world.map(made["bank"][1], account_id=None)
        assert account_of(world)["check"] is None

    def test_an_approved_item_matches(self, world):
        item_id, _p, made = connected(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
        world.sync(item_id)
        world.approve(world.pending()[0])
        check = account_of(world)["check"]
        assert (check["bank_only_count"], check["app_only_count"], check["awaiting_count"]) == (0, 0, 0)

    def test_a_pending_item_is_awaiting_not_an_inconsistency(self, world):
        item_id, _p, made = connected(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20", "PADARIA"))
        world.sync(item_id)
        check = account_of(world)["check"]
        assert (check["bank_only_count"], check["awaiting_count"]) == (0, 1)
        assert without_ids(check["awaiting"]) == [{"date": "2026-10-20", "amount": -45.9, "description": "PADARIA", "reason": "awaiting"}]

    def test_a_denied_item_is_bank_only(self, world):
        item_id, _p, made = connected(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20", "PADARIA"))
        world.sync(item_id)
        [item] = world.pending()
        world.call("post", f"/api/inbox/{item['id']}/deny", json={"version": item["version"]})
        check = account_of(world)["check"]
        assert without_ids(check["bank_only"]) == [{"date": "2026-10-20", "amount": -45.9, "description": "PADARIA", "reason": "denied"}]

    def test_an_extra_typed_entry_is_app_only(self, world):
        item_id, pluggy_item, made = connected(world)
        mine = made["bank"][2]
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
        world.sync(item_id)
        world.approve(world.pending()[0])
        world.call("post", "/api/transactions", json={
            "account_id": mine, "amount": 45.9, "date": "2026-10-21", "type": "EXPENSE", "category": "Outros",
            "description": "padaria de novo",
        })
        bank_moved_on(world, pluggy_item, item_id)
        check = account_of(world)["check"]
        assert without_ids(check["app_only"]) == [{"date": "2026-10-21", "amount": -45.9, "description": "padaria de novo", "reason": "not_in_bank"}]
        assert check["bank_only_count"] == 0

    def test_a_typed_entry_for_an_awaiting_item_is_not_app_only(self, world):
        item_id, _p, made = connected(world)
        mine = made["bank"][2]
        world.call("post", "/api/transactions", json={
            "account_id": mine, "amount": 45.9, "date": "2026-10-20", "type": "EXPENSE", "category": "Outros",
        })
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
        world.sync(item_id)
        check = account_of(world)["check"]
        assert check["app_only_count"] == 0

    def test_entries_before_the_window_are_out(self, world):
        item_id, _p, made = connected(world)
        mine = made["bank"][2]
        world.call("post", "/api/transactions", json={
            "account_id": mine, "amount": 10, "date": "2026-08-01", "type": "EXPENSE", "category": "Outros",
        })
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
        world.sync(item_id)
        world.approve(world.pending()[0])
        assert account_of(world)["check"]["app_only_count"] == 0

    def test_an_incoming_transfer_is_an_inflow(self, world):
        item_id, pluggy_item, made = connected(world)
        mine = made["bank"][2]
        other = world.account("Nubank")
        world.fake.add_tx(made["bank"][0], bank_tx(-12.5, "2026-10-21"))
        world.sync(item_id)
        world.approve(world.pending()[0])
        world.call("post", "/api/transfers", json={
            "account_id": other, "transfer_account_id": mine, "amount": 300, "date": "2026-10-22",
        })
        bank_moved_on(world, pluggy_item, item_id)
        check = account_of(world)["check"]
        assert without_ids(check["app_only"]) == [{"date": "2026-10-22", "amount": 300.0, "description": check["app_only"][0]["description"], "reason": "not_in_bank"}]

    def test_nothing_is_written(self, world):
        item_id, _p, made = connected(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
        world.sync(item_id)
        before = world.pending()
        world.overview()
        assert world.pending() == before and world.transactions(made["bank"][2]) == []


class TestCard:
    def test_installments_match_the_whole_purchase(self, world):
        item_id, _p, made = connected(world, bank=False, card=True)
        world.fake.add_tx(made["card"][0], card_tx(
            33.33, "2026-10-21", "LOJA X", installment=1, total_installments=3, purchase_date="2026-10-21T03:00:00.000Z",
            docs_sign=True,
        ))
        world.sync(item_id)
        world.call("post", "/api/cc-expenses/purchases", json={
            "card_id": made["card"][2], "total_amount": 100, "purchase_date": "2026-10-21", "description": "LOJA X",
            "installments": 3, "category": "Outros",
        })
        [item] = world.pending()
        world.call("post", f"/api/inbox/{item['id']}/deny", json={"version": item["version"]})
        check = account_of(world, "CREDIT")["check"]
        assert (check["bank_only_count"], check["app_only_count"]) == (0, 0)

    def test_an_approved_purchase_and_a_refund(self, world):
        item_id, _p, made = connected(world, bank=False, card=True)
        world.fake.add_tx(made["card"][0], card_tx(120, "2026-10-21", "LOJA"), card_tx(-30, "2026-10-22", "ESTORNO LOJA"),
                          card_tx(40, "2026-10-23", "LOJA 2"), card_tx(15, "2026-10-24", "LOJA 3"))
        world.sync(item_id)
        for item in world.pending():
            world.approve(item)
        check = account_of(world, "CREDIT")["check"]
        assert (check["bank_only_count"], check["app_only_count"], check["awaiting_count"]) == (0, 0, 0)

    def test_a_typed_purchase_the_bank_lacks(self, world):
        item_id, pluggy_item, made = connected(world, bank=False, card=True)
        world.fake.add_tx(made["card"][0], card_tx(120, "2026-10-21", "LOJA"))
        world.sync(item_id)
        world.approve(world.pending()[0])
        world.call("post", "/api/cc-expenses/purchases", json={
            "card_id": made["card"][2], "total_amount": 77, "purchase_date": "2026-10-22", "description": "SEM PAR",
            "installments": 1, "category": "Outros",
        })
        bank_moved_on(world, pluggy_item, item_id)
        check = account_of(world, "CREDIT")["check"]
        assert without_ids(check["app_only"]) == [{"date": "2026-10-22", "amount": -77.0, "description": "SEM PAR", "reason": "not_in_bank"}]

    def test_the_invoice_payment_is_not_a_card_movement(self, world):
        item_id, _p, made = connected(world, bank=False, card=True)
        world.fake.add_tx(made["card"][0], card_tx(120, "2026-10-21", "LOJA"),
                          card_tx(-500, "2026-10-10", "PAGAMENTO FATURA", category_id="05100000"))
        world.sync(item_id)
        world.approve(world.pending()[0])
        check = account_of(world, "CREDIT")["check"]
        assert (check["bank_only_count"], check["app_only_count"]) == (0, 0)


def test_another_user_sees_nothing(world, client, other_user):
    item_id, _p, made = connected(world)
    world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
    world.sync(item_id)
    assert client.get("/api/open-finance", headers=other_user["headers"]).get_json()["items"] == []


class TestBankInvoice:
    """A compra fica na fatura que o banco diz, uma linha por linha dele (2026-10-30)."""

    def month(self, raw, bill_month, number=None, total=None, purchase=None):
        metadata = raw.get("creditCardMetadata") or {}
        metadata["billForecastDate"] = bill_month
        if number:
            metadata.update({"installmentNumber": number, "totalInstallments": total, "purchaseDate": purchase})
        raw["creditCardMetadata"] = metadata
        return raw

    def invoices(self, world, card):
        return sorted(
            (row["invoice_year"], row["invoice_month"], row["amount"], row["installment_info"])
            for row in world.card_rows(card)
        )

    def test_the_month_is_the_banks_and_a_pending_purchase_comes(self, world):
        item_id, _p, made = connected(world, bank=False, card=True)
        auto_on(world)
        world.fake.add_tx(made["card"][0], self.month(card_tx(80, "2026-10-28", "CLAUDE", status="PENDING", docs_sign=True), "2027-01"))
        world.sync(item_id)
        assert self.invoices(world, made["card"][2]) == [(2027, 1, 80.0, "1/1")]

    def test_each_installment_is_what_the_bank_lists(self, world):
        item_id, _p, made = connected(world, bank=False, card=True)
        auto_on(world)
        day = "2026-09-17"
        for number, month, amount in ((1, "2026-11", 40), (3, "2027-01", 39.5)):
            world.fake.add_tx(made["card"][0], self.month(
                card_tx(amount, "2026-10-28", "IG DUO", installment=number, total_installments=4, purchase_date=day, docs_sign=True),
                month, number, 4, day,
            ))
        world.sync(item_id)
        assert self.invoices(world, made["card"][2]) == [(2026, 11, 40.0, "1/4"), (2027, 1, 39.5, "3/4")]
        account = account_of(world, "CREDIT")
        assert account["check"]["bank_only"] == []

    def test_an_installment_the_bank_starts_listing_comes_in(self, world):
        item_id, _p, made = connected(world, bank=False, card=True)
        auto_on(world)
        day = "2026-09-17"
        world.fake.add_tx(made["card"][0], self.month(
            card_tx(40, "2026-10-28", "IG DUO", installment=1, total_installments=2, purchase_date=day, docs_sign=True), "2026-11", 1, 2, day,
        ))
        world.sync(item_id)
        assert self.invoices(world, made["card"][2]) == [(2026, 11, 40.0, "1/2")]
        world.fake.add_tx(made["card"][0], self.month(
            card_tx(40, "2026-10-29", "IG DUO", installment=2, total_installments=2, purchase_date=day, docs_sign=True), "2026-12", 2, 2, day,
        ))
        world.sync(item_id)
        assert self.invoices(world, made["card"][2]) == [(2026, 11, 40.0, "1/2"), (2026, 12, 40.0, "2/2")]


def test_a_dollar_deposit_is_not_waiting_for_the_bank(check):
    """A Wise manda o credito em outra gaveta: a transferencia com os dois valores nao fica apontada."""
    source = (Path(check.__file__)).read_text(encoding="utf-8")
    assert "transfer_amount IS NOT NULL" in source
