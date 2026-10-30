"""Editar uma compra no cartao e as compras no debito na tela Cartoes (049).

O que estes testes protegem:

- PATCH /api/cc-expenses/purchases/<id> troca a categoria (pelo id) e a
  descricao de todas as parcelas da compra, pagas inclusive, e de nenhuma outra;
  valor e fatura ficam;
- a compra no debito guarda o cartao (`card_id`) quando o "+ Novo" ou o Aprovar
  sabem qual e, e so numa despesa da conta do cartao;
- GET /api/cc-invoices lista em `debit_cards` as compras no debito de cada
  cartao, da mais nova para a mais antiga; um cartao so debito tambem lista as
  despesas sem cartao da conta dele, nunca um pagamento de fatura nem receita.
"""

from datetime import date

import pytest

from finance_world import World, freeze
from test_card_debit import BTG, detection, pending, send


@pytest.fixture()
def world(client, user):
    return World(client, user)


@pytest.fixture()
def clock(app_module, monkeypatch):
    return freeze(monkeypatch, date(2026, 10, 20))


def category(world, name, parent=None):
    body = {"name": name, "kind": "EXPENSE"}
    if parent:
        body["parent_id"] = parent
    return world.call("post", "/api/categories", json=body).get_json()


def rows_of(world, purchase):
    ids = {row["id"] for row in purchase}
    return [row for row in world.get("/api/cc-expenses") if row["id"] in ids]


class TestEditPurchase:
    def test_category_and_description_change_on_every_installment(self, world, clock):
        card = world.card("Nubank")
        other = world.purchase(card, 90, "2026-10-01", "Mercado", installments=1)
        purchase = world.purchase(card, 300, "2026-10-01", "Loja", installments=3)
        lazer = category(world, "Passeios")

        response = world.call(
            "patch", f"/api/cc-expenses/purchases/{purchase[1]['id']}",
            json={"category_id": lazer["id"], "description": "Cinema"},
        ).get_json()

        assert len(response) == 3
        rows = rows_of(world, purchase)
        assert {(row["category"], row["category_id"], row["description"]) for row in rows} == {
            ("Passeios", lazer["id"], "Cinema"),
        }
        assert sorted(row["amount"] for row in rows) == [100, 100, 100]
        assert [(row["invoice_year"], row["invoice_month"]) for row in rows] == [
            (row["invoice_year"], row["invoice_month"]) for row in purchase
        ]
        [untouched] = rows_of(world, other)
        assert (untouched["category"], untouched["description"]) == ("Alimentação", "Mercado")

    def test_a_paid_installment_changes_too(self, world, clock):
        bank = world.account("Banco", initial=1000)
        card = world.card("Nubank")
        purchase = world.purchase(card, 200, "2026-09-20", "Loja", installments=2)
        clock.set("2026-10-05")
        world.pay(card, 10, 2026, bank)
        assert {row["status"] for row in rows_of(world, purchase)} == {"PAID", "OPEN"}

        lazer = category(world, "Passeios")
        world.call("patch", f"/api/cc-expenses/purchases/{purchase[0]['id']}", json={"category_id": lazer["id"]})
        assert {row["category_id"] for row in rows_of(world, purchase)} == {lazer["id"]}

    def test_a_subcategory_keeps_its_id(self, world, clock):
        card = world.card("Nubank")
        purchase = world.purchase(card, 50, "2026-10-01", "Loja")
        lazer = category(world, "Passeios")
        sub = category(world, "Outros", parent=lazer["id"])
        world.call("patch", f"/api/cc-expenses/purchases/{purchase[0]['id']}", json={"category_id": sub["id"]})
        [row] = rows_of(world, purchase)
        assert (row["category"], row["category_id"]) == ("Outros", sub["id"])

    def test_the_invoice_screen_shows_the_new_category(self, world, clock):
        card = world.card("Nubank")
        purchase = world.purchase(card, 50, "2026-10-10", "Loja")
        lazer = category(world, "Passeios")
        world.call("patch", f"/api/cc-expenses/purchases/{purchase[0]['id']}", json={"category_id": lazer["id"]})
        [shown] = world.invoices()["cards"][0]["invoices"][0]["purchases"]
        assert (shown["category"], shown["category_id"]) == ("Passeios", lazer["id"])

    def test_a_refund_can_be_recategorized(self, world, clock):
        card = world.card("Nubank")
        refund = world.refund(card, 20, "2026-10-10")
        lazer = category(world, "Passeios")
        [row] = world.call(
            "patch", f"/api/cc-expenses/purchases/{refund['id']}", json={"category_id": lazer["id"]},
        ).get_json()
        assert (row["kind"], row["category_id"]) == ("REFUND", lazer["id"])

    def test_refusals(self, world, clock, client, other_user):
        card = world.card("Nubank")
        purchase = world.purchase(card, 50, "2026-10-01", "Loja")
        path = f"/api/cc-expenses/purchases/{purchase[0]['id']}"
        world.call("patch", path, expected=400, json={})
        world.call("patch", path, expected=400, json={"category_id": "nao-existe"})
        world.call("patch", path, expected=400, json={"description": ""})
        world.call("patch", "/api/cc-expenses/purchases/nao-existe", expected=404, json={"description": "x"})
        response = client.patch(path, json={"description": "x"}, headers=other_user["headers"])
        assert response.status_code == 404
        [row] = rows_of(world, purchase)
        assert row["description"] == "Loja"

    def test_an_archived_category_is_refused(self, world, clock):
        card = world.card("Nubank")
        purchase = world.purchase(card, 50, "2026-10-01", "Loja")
        lazer = category(world, "Passeios")
        world.call("delete", f"/api/categories/{lazer['id']}")
        world.call(
            "patch", f"/api/cc-expenses/purchases/{purchase[0]['id']}", expected=400,
            json={"category_id": lazer["id"]},
        )


class TestDebitPurchases:
    def debit_tx(self, world, card, account, amount, day, description="Mercado", expected=(201,)):
        return world.call("post", "/api/transactions", expected=expected, json={
            "type": "EXPENSE", "amount": amount, "date": day, "account_id": account["id"],
            "category": "Alimentação", "description": description, "card_id": card["id"],
        }).get_json()

    def test_a_debit_purchase_keeps_its_card_and_lists_newest_first(self, world, clock):
        bank = world.account("Conta BTG", initial=1000)
        card = world.card("BTG", debit_account_id=bank["id"])
        older = self.debit_tx(world, card, bank, 30, "2026-10-02", "Padaria")
        newer = self.debit_tx(world, card, bank, 45.5, "2026-10-15", "Mercado")
        last_month = self.debit_tx(world, card, bank, 10, "2026-09-28", "Feira")
        world.tx("EXPENSE", 99, "2026-10-16", bank, description="Pix sem cartao")

        assert newer["card_id"] == card["id"]
        [entry] = world.invoices()["debit_cards"]
        assert (entry["card_id"], entry["account_id"], entry["credit_enabled"]) == (card["id"], bank["id"], True)
        assert [row["id"] for row in entry["purchases"]] == [newer["id"], older["id"], last_month["id"]]
        assert entry["month_total"] == 75.5
        assert entry["since"] == "2026-09-01"

    def test_the_card_must_debit_from_that_account(self, world, clock):
        bank = world.account("Conta BTG")
        other = world.account("Itaú")
        debit = world.card("BTG", debit_account_id=bank["id"])
        credit_only = world.card("Nubank")
        self.debit_tx(world, debit, other, 10, "2026-10-02", expected=400)
        self.debit_tx(world, credit_only, bank, 10, "2026-10-02", expected=400)
        world.call("post", "/api/transactions", expected=400, json={
            "type": "INCOME", "amount": 10, "date": "2026-10-02", "account_id": bank["id"],
            "category": "Outros", "card_id": debit["id"],
        })

    def test_moving_it_to_another_account_takes_it_off_the_card(self, world, clock):
        bank = world.account("Conta BTG")
        other = world.account("Itaú")
        card = world.card("BTG", debit_account_id=bank["id"])
        row = self.debit_tx(world, card, bank, 10, "2026-10-02")
        kept = world.call("patch", f"/api/transactions/{row['id']}", json={"description": "Feira"}).get_json()
        assert kept["card_id"] == card["id"]
        moved = world.call("patch", f"/api/transactions/{row['id']}", json={"account_id": other["id"]}).get_json()
        assert moved["card_id"] is None
        assert world.invoices()["debit_cards"][0]["purchases"] == []

    def test_a_debit_only_card_lists_the_expenses_of_its_account(self, world, clock):
        flash = world.account("Flash", initial=500)
        card = world.card("Flash", credit_enabled=False, debit_account_id=flash["id"])
        expense = world.tx("EXPENSE", 20, "2026-10-10", flash, description="Restaurante")
        world.tx("INCOME", 500, "2026-10-01", flash, description="Recarga")
        world.insert_tx("EXPENSE", 15, "2026-10-11", flash, source_type="CC_INVOICE_PAYMENT")
        world.tx("EXPENSE", 5, "2026-08-31", flash, description="Fora da janela")

        [entry] = world.invoices()["debit_cards"]
        assert entry["card_id"] == card["id"]
        assert [(row["id"], row["linked"]) for row in entry["purchases"]] == [(expense["id"], False)]
        assert entry["month_total"] == 20

    def test_two_debit_cards_on_one_account_list_only_their_own(self, world, clock):
        bank = world.account("Conta")
        first = world.card("Débito A", credit_enabled=False, debit_account_id=bank["id"])
        second = world.card("Débito B", credit_enabled=False, debit_account_id=bank["id"])
        mine = self.debit_tx(world, first, bank, 10, "2026-10-02")
        world.tx("EXPENSE", 99, "2026-10-03", bank, description="Sem cartao")
        listed = {entry["card_id"]: [row["id"] for row in entry["purchases"]] for entry in world.invoices()["debit_cards"]}
        assert listed == {first["id"]: [mine["id"]], second["id"]: []}

    def test_a_credit_only_card_has_no_debit_list(self, world, clock):
        world.card("Nubank")
        assert world.invoices()["debit_cards"] == []

    def test_an_approved_debit_notification_keeps_the_card(self, client, auth, any_bank_notifications):
        create = client.post("/api/accounts", json={"name": "Conta BTG", "type": "CHECKING"}, headers=auth)
        banking = create.get_json()["id"]
        card = client.post(
            "/api/credit-cards",
            json={"name": "BTG", "due_day": 10, "closing_day": 3, "debit_account_id": banking},
            headers=auth,
        ).get_json()
        send(client, auth, detection(kind="DEBIT_PURCHASE", app=BTG, merchant="Mercado"))
        [item] = pending(client, auth)
        response = client.post(f"/api/inbox/{item['id']}/approve", json={"version": item["version"]}, headers=auth)
        assert response.status_code == 200, response.get_data(as_text=True)
        [row] = [row for row in client.get("/api/transactions", headers=auth).get_json() if row["account_id"] == banking]
        assert row["card_id"] == card["id"]


class TestInvoiceFixes:
    def test_an_old_purchase_never_puts_an_installment_in_a_paid_invoice(self, world, clock):
        bank = world.account("Banco", initial=1000)
        card = world.card("Nubank")
        world.purchase(card, 50, "2026-09-20", "Antes")
        world.pay(card, 10, 2026, bank)

        # Compra de 01/08 em 3x: agosto e setembro estao livres, outubro ja foi paga.
        rows = world.purchase(card, 300, "2026-08-01", "Antiga", installments=3)
        assert [(row["invoice_month"], row["installment_info"], row["status"]) for row in rows] == [
            (8, "1/3", "OPEN"), (9, "2/3", "OPEN"), (11, "3/3", "OPEN"),
        ]

    def test_an_archived_card_is_never_autopaid(self, world, clock):
        bank = world.account("Banco", initial=1000)
        card = world.card("Nubank", autopay_account_id=bank["id"])
        purchase = world.purchase(card, 80, "2026-10-10", "Loja")
        world.set_rows("UPDATE credit_cards SET archived_at = '2026-10-15T00:00:00Z' WHERE id = ?", (card["id"],))
        clock.set("2026-11-12")
        world.invoices()
        [row] = rows_of(world, purchase)
        assert row["status"] == "OPEN"
