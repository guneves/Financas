"""As regras do dono de 2026-10-31.

- parcela adiantada: a Pluggy segue listando PENDING, o credito de desconto manda;
- pagamento que o app ja tem: a saida do banco liga nele, nunca grava um segundo
  (os 11 pagamentos em dobro de 02:41 UTC);
- aplicacao num fundo do banco e resgate nao sao despesa nem receita;
- a linha do mes do Inter fica fora de todo total, e no saldo;
- repasse: receita de outra pessoa; o pago pelos outros abate a receita ao ser marcado;
- so a Flash se digita: conta e cartao da Pluggy recusam.
"""

import importlib
import uuid

import pytest

from open_finance_world import World, bank_tx, card_tx, connected, fake_pluggy, open_finance_module  # noqa: F401
from test_open_finance_auto import auto_on


@pytest.fixture()
def world(client, auth, fake_pluggy):
    return World(client, auth, fake_pluggy)


def rows_of(table, where, params):
    db = importlib.import_module("db")
    with db.get_db() as conn:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table} WHERE {where}", params).fetchall()]


def billed(raw, month, number=None, total=None, purchase=None):
    metadata = raw.get("creditCardMetadata") or {}
    metadata["billForecastDate"] = month
    if number:
        metadata.update({"installmentNumber": number, "totalInstallments": total, "purchaseDate": purchase})
    raw["creditCardMetadata"] = metadata
    return raw


def discount(number, total, name, day, month):
    raw = billed({
        **card_tx(1, day, f"Desconto Na Parcela {number} De {total} {name}", docs_sign=True),
        "amount": -0.1, "type": "CREDIT",
    }, month)
    return raw


class TestAnticipatedInstallments:
    """Rota e Ig na BTG: 2/3 cobradas em outubro, a Pluggy ainda lista 3 em dezembro."""

    def lines(self, world, card):
        return sorted(
            (row["installment_info"], row["invoice_year"], row["invoice_month"], row["status"], row["amount"])
            for row in world.card_rows(card) if row["kind"] == "PURCHASE"
        )

    def scene(self, world):
        item_id, _p, made = connected(world, bank=True, card=True)
        auto_on(world)
        card_pluggy, card = made["card"][0], made["card"][2]
        day = "2026-08-27"
        for number, month in ((1, "2026-09"), (2, "2026-10")):
            world.fake.add_tx(card_pluggy, billed(
                card_tx(9.29, "2026-10-20", "Rota Transportes", installment=number, total_installments=4, purchase_date=day, docs_sign=True),
                month, number, 4, day,
            ))
        # Listada como futura; a 3 o banco nem lista mais.
        world.fake.add_tx(card_pluggy, billed(
            card_tx(9.29, "2026-10-20", "Rota Transportes", installment=4, total_installments=4, purchase_date=day,
                    docs_sign=True, status="PENDING"),
            "2026-12", 4, 4, day,
        ))
        world.fake.add_tx(card_pluggy, discount(3, 4, "Rota Transportes", "2026-10-21", "2026-10"))
        world.fake.add_tx(card_pluggy, discount(4, 4, "Rota Transportes", "2026-10-21", "2026-10"))
        return item_id, made, card

    def test_each_goes_to_the_invoice_of_its_discount(self, world):
        item_id, _made, card = self.scene(world)
        world.sync(item_id)
        assert self.lines(world, card) == [
            ("1/4", 2026, 9, "OPEN", 9.29), ("2/4", 2026, 10, "OPEN", 9.29),
            ("3/4", 2026, 10, "OPEN", 9.29), ("4/4", 2026, 10, "OPEN", 9.29),
        ]

    def test_nothing_is_left_in_a_future_invoice_and_a_new_pull_keeps_it(self, world):
        item_id, _made, card = self.scene(world)
        world.sync(item_id)
        world.sync(item_id)
        assert {(row["invoice_year"], row["invoice_month"]) for row in world.card_rows(card)} <= {(2026, 9), (2026, 10)}
        assert sum(1 for row in world.card_rows(card) if row["kind"] == "PURCHASE") == 4

    def test_a_paid_invoice_takes_them_as_paid_and_keeps_the_payment(self, world):
        item_id, made, card = self.scene(world)
        world.sync(item_id)
        db = importlib.import_module("db")
        with db.get_db() as conn:
            conn.execute(
                "UPDATE cc_expenses SET status = 'PAID', paid_by = 'pay-1' WHERE card_id = ? AND invoice_year = 2026"
                " AND invoice_month = 10 AND installment_info <> '4/4'",
                (card,),
            )
            conn.execute(
                "UPDATE cc_expenses SET status = 'OPEN', invoice_year = 2026, invoice_month = 12, paid_by = NULL"
                " WHERE card_id = ? AND installment_info = '4/4'",
                (card,),
            )
        world.sync(item_id)
        lines = {line[0]: line for line in self.lines(world, card)}
        assert lines["4/4"][1:4] == (2026, 10, "PAID")
        assert rows_of("cc_expenses", "card_id = ? AND installment_info = '4/4'", (card,))[0]["paid_by"] == "pay-1"

    def test_another_purchase_of_the_same_text_is_left_alone(self, world):
        item_id, made, card = self.scene(world)
        later = "2026-10-25"
        world.fake.add_tx(made["card"][0], billed(
            card_tx(9.29, "2026-10-25", "Rota Transportes", installment=1, total_installments=4, purchase_date=later,
                    docs_sign=True, status="PENDING"),
            "2027-01", 1, 4, later,
        ))
        world.sync(item_id)
        assert ("1/4", 2027, 1, "OPEN", 9.29) in self.lines(world, card)

    def test_two_purchases_the_discount_finds_the_one_not_billed(self, world):
        item_id, made, card = self.scene(world)
        later = "2026-09-27"
        for number, month in ((1, "2026-10"), (3, "2026-12")):
            world.fake.add_tx(made["card"][0], billed(
                card_tx(20, "2026-10-20", "Rota Transportes", installment=number, total_installments=4, purchase_date=later,
                        docs_sign=True, status="PENDING"),
                month, number, 4, later,
            ))
        world.sync(item_id)
        lines = self.lines(world, card)
        assert ("3/4", 2026, 10, "OPEN", 9.29) in lines
        assert ("3/4", 2026, 12, "OPEN", 20.0) in lines

    def test_the_check_counts_the_installment_the_bank_stopped_listing(self, world):
        item_id, made, card = self.scene(world)
        world.sync(item_id)
        account = next(
            row for item in world.overview()["items"] for row in item["accounts"] if row["type"] == "CREDIT"
        )
        assert [row for row in account["check"]["app_only"] if "Rota" in (row["description"] or "")] == []
        assert [row for row in account["check"]["bank_only"] if "Rota" in (row["description"] or "")] == []


class TestKeptPayment:
    def scene(self, world, user, amount, day):
        item_id, _p, made = connected(world, bank=True, card=True)
        auto_on(world)
        bank = made["bank"][2]
        self.kept = str(uuid.uuid4())
        db = importlib.import_module("db")
        with db.get_db() as conn:
            conn.execute(
                """INSERT INTO transactions (id, user_id, account_id, amount, date, category, description, type, source_type, source_id)
                   VALUES (?, ?, ?, ?, ?, 'Pagamento Fatura Black', 'Pagamento', 'EXPENSE', 'CC_AUTOPAY', ?)""",
                (self.kept, user["id"], bank, amount, day, f"card:{self.kept}"),
            )
        return item_id, made, bank

    def payments(self, bank):
        return rows_of("transactions", "account_id = ? AND source_type IN ('CC_AUTOPAY', 'CC_INVOICE_PAYMENT')", (bank,))

    def test_the_same_day_is_the_same_payment_at_the_banks_amount(self, world, user):
        item_id, made, bank = self.scene(world, user, 405.33, "2026-10-20")
        world.fake.add_tx(made["bank"][0], bank_tx(-382.36, "2026-10-20", "CardBankslip", category_id="05100000"))
        world.sync(item_id)
        world.sync(item_id)
        [payment] = self.payments(bank)
        assert (payment["id"], payment["amount"]) == (self.kept, 382.36)

    def test_the_same_amount_days_apart_is_the_same_payment(self, world, user):
        item_id, made, bank = self.scene(world, user, 382.36, "2026-10-17")
        world.fake.add_tx(made["bank"][0], bank_tx(-382.36, "2026-10-20", "CardBankslip", category_id="05100000"))
        world.sync(item_id)
        assert len(self.payments(bank)) == 1

    def test_two_bank_payments_on_the_day_the_closest_takes_it(self, world, user):
        item_id, made, bank = self.scene(world, user, 500, "2026-10-20")
        world.fake.add_tx(made["bank"][0], bank_tx(-200, "2026-10-20", "CardBankslip", category_id="05100000"))
        world.fake.add_tx(made["bank"][0], bank_tx(-499.5, "2026-10-20", "CardBankslip", category_id="05100000"))
        world.sync(item_id)
        assert sorted(row["amount"] for row in self.payments(bank)) == [200.0, 499.5]
        assert next(row for row in self.payments(bank) if row["id"] == self.kept)["amount"] == 499.5

    def test_another_amount_on_another_day_is_another_payment(self, world, user):
        item_id, made, bank = self.scene(world, user, 500, "2026-10-17")
        world.fake.add_tx(made["bank"][0], bank_tx(-382.36, "2026-10-20", "CardBankslip", category_id="05100000"))
        world.sync(item_id)
        assert len(self.payments(bank)) == 2


class TestBankInvestment:
    def test_it_is_neither_expense_nor_income_and_stays_in_the_balance(self, world, user):
        item_id, _p, made = connected(world)
        auto_on(world)
        bank_pluggy, bank = made["bank"][0], made["bank"][2]
        world.fake.add_tx(bank_pluggy, bank_tx(-1000, "2026-10-20", "RF LP SELIC", category_id="03020000", category="Fixed income"))
        world.fake.add_tx(bank_pluggy, bank_tx(501.1, "2026-10-24", "RF LP SELIC", category_id="03020000", category="Fixed income"))
        world.sync(item_id)
        rows = {row["type"]: row for row in world.transactions(bank)}
        assert {row["source_type"] for row in rows.values()} == {"BANK_INVESTMENT"}
        assert not any(row["needs_review"] for row in rows.values())
        home = importlib.import_module("services.home")
        accounts = importlib.import_module("services.accounts")
        db = importlib.import_module("db")
        with db.get_db() as conn:
            listed = [dict(row) for row in accounts.account_balance_rows(conn, user["id"])]
            [october] = home.monthly_flow(conn, user["id"], listed, ["2026-10"])
        assert (october["expense"], october["income"]) == (0, 0)
        assert (october["invested"], october["redeemed"]) == (1000.0, 501.1)
        assert october["balance"] == -498.9

    def test_rende_facil_is_still_out_of_the_app(self, world):
        item_id, _p, made = connected(world)
        auto_on(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-20, "2026-10-20", "RENDE FACIL", category_id="03010000"))
        world.sync(item_id)
        assert world.transactions(made["bank"][2]) == []


def own_flow(user, month):
    home = importlib.import_module("services.home")
    accounts = importlib.import_module("services.accounts")
    db = importlib.import_module("db")
    with db.get_db() as conn:
        listed = [dict(row) for row in accounts.account_balance_rows(conn, user["id"])]
        return home.monthly_flow(conn, user["id"], listed, [month])[0]


class TestMonthSummary:
    @pytest.fixture()
    def inter(self, client, auth, user):
        response = client.post("/api/accounts", json={"name": "Inter", "type": "CHECKING", "initial_balance": 1000}, headers=auth)
        account = response.get_json()["id"]
        db = importlib.import_module("db")
        with db.get_db() as conn:
            conn.execute(
                """INSERT INTO transactions (id, user_id, account_id, amount, date, category, description, type, source_type, source_id)
                   VALUES (?, ?, ?, 300, '2026-08-31', 'Outros', 'Gastos no Inter', 'EXPENSE', 'MONTH_SUMMARY', 'inter:2026-08')""",
                (str(uuid.uuid4()), user["id"], account),
            )
        return account

    def test_the_flow_keeps_the_balance_and_not_the_expense(self, inter, user):
        august = own_flow(user, "2026-08")
        assert (august["expense"], august["balance"]) == (0, 700.0)

    def test_the_plan_does_not_count_it(self, inter, user):
        plan = importlib.import_module("services.monthly_plan")
        db = importlib.import_module("db")
        with db.get_db() as conn:
            assert plan.month_banking_totals(conn, user["id"], "2026-08") == (0, 0, 0)

    def test_the_statement_totals_do_not_count_it(self, inter, client, auth):
        pages = importlib.import_module("services.transaction_pages")
        assert pages.statement_totals([{"source_type": "MONTH_SUMMARY", "type": "EXPENSE", "amount": 300}])["expense"] == 0


class TestRepasse:
    def income(self, client, auth, account, amount=620, date="2026-03-26"):
        response = client.post("/api/transactions", headers=auth, json={
            "account_id": account, "amount": amount, "date": date, "type": "INCOME", "category": "Receita",
        })
        assert response.status_code == 201, response.get_data(as_text=True)
        return response.get_json()["id"]

    @pytest.fixture()
    def account(self, client, auth):
        return client.post("/api/accounts", json={"name": "Banco", "type": "CHECKING"}, headers=auth).get_json()["id"]

    def test_a_repasse_leaves_the_income_not_the_balance(self, client, auth, user, account):
        row = self.income(client, auth, account)
        response = client.post("/api/review", headers=auth, json={"items": [
            {"table": "transactions", "id": row, "repasse": True, "person": "Pai"},
        ]})
        assert response.status_code == 200, response.get_data(as_text=True)
        march = own_flow(user, "2026-03")
        assert (march["income"], march["others_received"], march["balance"]) == (0, 620.0, 620.0)
        [saved] = rows_of("transactions", "id = ?", (row,))
        assert (saved["share_mode"], saved["share_person"]) == ("OTHERS", "Pai")
        assert saved["share_settled_at"]

    def test_only_an_income_can_be_one(self, client, auth, account):
        row = client.post("/api/transactions", headers=auth, json={
            "account_id": account, "amount": 10, "date": "2026-03-26", "type": "EXPENSE", "category": "Outros",
        }).get_json()["id"]
        response = client.post("/api/review", headers=auth, json={"items": [{"table": "transactions", "id": row, "repasse": True}]})
        assert response.status_code == 400

    def settle(self, user, amount, stamp):
        db = importlib.import_module("db")
        with db.get_db() as conn:
            account = conn.execute("SELECT id FROM accounts WHERE user_id = ? LIMIT 1", (user["id"],)).fetchone()["id"]
            conn.execute(
                """INSERT INTO transactions (id, user_id, account_id, amount, date, category, type, share_mode, share_person, share_settled_at)
                   VALUES (?, ?, ?, ?, '2026-03-26', 'Alimentação', 'EXPENSE', 'OTHERS', 'Pai', ?)""",
                (str(uuid.uuid4()), user["id"], account, amount, stamp),
            )

    def test_what_was_paid_for_others_cuts_the_income_once_marked(self, client, auth, user, account):
        self.income(client, auth, account, 1000)
        self.settle(user, 617.16, "2026-03-27T12:00:00.000Z")
        march = own_flow(user, "2026-03")
        assert (march["income"], march["others_received"]) == (382.84, 617.16)
        assert (march["expense"], march["others_paid"]) == (0, 617.16)

    def test_an_unmarked_share_does_not(self, client, auth, user, account):
        self.income(client, auth, account, 1000)
        self.settle(user, 617.16, None)
        assert own_flow(user, "2026-03")["income"] == 1000.0

    def test_a_repasse_already_covers_it(self, client, auth, user, account):
        row = self.income(client, auth, account, 620)
        self.income(client, auth, account, 1800, "2026-03-31")
        client.post("/api/review", headers=auth, json={"items": [{"table": "transactions", "id": row, "repasse": True}]})
        self.settle(user, 617.16, "2026-03-27T12:00:00.000Z")
        assert own_flow(user, "2026-03")["income"] == 1800.0

    def test_a_repasse_of_the_month_before_covers_it(self, client, auth, user, account):
        row = self.income(client, auth, account, 620, "2026-02-28")
        self.income(client, auth, account, 1800, "2026-03-31")
        client.post("/api/review", headers=auth, json={"items": [{"table": "transactions", "id": row, "repasse": True}]})
        self.settle(user, 617.16, "2026-03-02T12:00:00.000Z")
        assert own_flow(user, "2026-03")["income"] == 1800.0

    def test_a_dollar_share_does_not_cut_the_income(self, client, auth, user, account):
        self.income(client, auth, account, 1000)
        wise = client.post("/api/accounts", json={"name": "Wise", "type": "CHECKING", "currency": "USD"}, headers=auth).get_json()["id"]
        db = importlib.import_module("db")
        with db.get_db() as conn:
            conn.execute(
                """INSERT INTO transactions (id, user_id, account_id, amount, date, category, type, share_mode, share_person, share_settled_at)
                   VALUES (?, ?, ?, 100, '2026-03-26', 'Outros', 'EXPENSE', 'OTHERS', 'Pai', '2026-03-27T12:00:00.000Z')""",
                (str(uuid.uuid4()), user["id"], wise),
            )
        assert own_flow(user, "2026-03")["income"] == 1000.0

    def test_the_plan_says_the_same_income_as_the_summary(self, client, auth, user, account):
        self.income(client, auth, account, 1000)
        self.settle(user, 617.16, "2026-03-27T12:00:00.000Z")
        body = client.get("/api/monthly-plan?month=2026-03", headers=auth).get_json()
        assert body["income"]["received"] == own_flow(user, "2026-03")["income"] == 382.84

    def test_the_mark_counts_on_the_local_day(self, client, auth, user, account):
        self.income(client, auth, account, 1000, "2026-04-02")
        # 02:00 UTC de 1/4 ainda e 31/3 em Sao Paulo.
        self.settle(user, 100, "2026-04-01T02:00:00.000Z")
        assert own_flow(user, "2026-04")["income"] == 1000.0


class TestOnlyFlashIsTyped:
    @pytest.fixture(autouse=True)
    def enforced(self, app_module, monkeypatch):
        monkeypatch.setattr(importlib.import_module("services.manual_entries"), "MANUAL_ONLY_OFF_PLUGGY", True)

    def test_a_connected_account_refuses_a_typed_row(self, world):
        _item, _p, made = connected(world)
        response = world.client.post("/api/transactions", headers=world.auth, json={
            "account_id": made["bank"][2], "amount": 10, "date": "2026-10-20", "type": "EXPENSE", "category": "Outros",
        })
        assert response.status_code == 400
        assert "Pluggy" in response.get_json()["error"]

    def test_a_connected_card_refuses_a_purchase_and_a_refund(self, world):
        _item, _p, made = connected(world, bank=False, card=True)
        purchase = world.client.post("/api/cc-expenses/purchases", headers=world.auth, json={
            "card_id": made["card"][2], "description": "Loja", "total_amount": 10, "purchase_date": "2026-10-20",
            "installments": 1, "category": "Outros",
        })
        refund = world.client.post("/api/cc-expenses/refunds", headers=world.auth, json={
            "card_id": made["card"][2], "description": "Loja", "amount": 10, "purchase_date": "2026-10-20",
        })
        assert (purchase.status_code, refund.status_code) == (400, 400)

    def test_an_unconnected_account_still_takes_it(self, world):
        flash = world.account("Flash")
        response = world.client.post("/api/transactions", headers=world.auth, json={
            "account_id": flash, "amount": 10, "date": "2026-10-20", "type": "EXPENSE", "category": "Outros",
        })
        assert response.status_code == 201

    def test_a_transfer_needs_one_side_without_pluggy(self, world):
        _item, _p, made = connected(world)
        flash = world.account("Flash")
        typed = world.client.post("/api/transfers", headers=world.auth, json={
            "account_id": made["bank"][2], "transfer_account_id": flash, "amount": 10, "date": "2026-10-20",
        })
        assert typed.status_code in (200, 201)

    def test_the_lists_say_which_are_connected(self, world):
        _item, _p, made = connected(world, bank=True, card=True)
        flash = world.account("Flash")
        accounts = {row["id"]: row["pluggy"] for row in world.client.get("/api/accounts", headers=world.auth).get_json()}
        cards = {row["id"]: row["pluggy"] for row in world.client.get("/api/credit-cards", headers=world.auth).get_json()}
        assert accounts[made["bank"][2]] is True and accounts[flash] is False
        assert cards[made["card"][2]] is True
