"""A linha que cada caminho de criacao grava, coluna por coluna.

Um lancamento, uma transferencia, uma compra no cartao e um estorno nascem por
dois caminhos: as rotas ("+ Novo") e o motor do Aprovar
(`inbox_decisions.create_entry()`, que grava "como se o dono tivesse
digitado"). Cada um tinha o seu INSERT, com a sua lista de colunas; desde
services/entries.py o INSERT e um so. Este arquivo fixa a linha inteira de cada
caminho (menos ids e carimbos de hora), para a troca nao mudar nenhuma coluna.
"""

import importlib

import pytest

from finance_world import World

VOLATILE = {"id", "created_at", "updated_at", "user_id"}


@pytest.fixture()
def world(client, user):
    return World(client, user)


def stored(table, where, params):
    db = importlib.import_module("db")
    with db.get_db() as conn:
        rows = conn.execute(f"SELECT * FROM {table} WHERE {where} ORDER BY rowid", params).fetchall()
    return [{key: row[key] for key in row.keys() if key not in VOLATILE} for row in rows]


def named(row, mapping):
    """Troca ids desta execucao por nomes fixos."""
    return {key: mapping.get(value, value) if isinstance(value, str) else value for key, value in row.items()}


def engine_entry(user, item):
    db = importlib.import_module("db")
    decisions = importlib.import_module("services.inbox_decisions")
    with db.get_db() as conn:
        return decisions.create_entry(conn, user["id"], item)


def base_item(**fields):
    item = {
        "id": "item-1", "entry_type": "EXPENSE", "direction": "OUT", "amount": 45.9,
        "occurred_at": "2026-10-05T12:30:00-03:00", "client_key": "notify:abc", "description": "Padaria",
        "category": "Alimentação", "category_id": None, "installments": 1,
        "account_id": None, "transfer_account_id": None, "transfer_amount": None, "card_id": None,
    }
    item.update(fields)
    return item


class TestTheRoutes:
    def test_an_expense(self, world, user):
        bank = world.account("Banco")
        row = world.call("post", "/api/transactions", json={
            "type": "EXPENSE", "amount": 45.9, "date": "2026-10-05", "account_id": bank["id"],
            "category": "Alimentação", "description": "Padaria", "client_id": "client-0001",
        }).get_json()
        [line] = stored("transactions", "id = ?", (row["id"],))
        food = world.category_id("Alimentação")
        assert named(line, {bank["id"]: "BANK", food: "FOOD"}) == {
            "account_id": "BANK", "amount": 45.9, "date": "2026-10-05", "category": "Alimentação",
            "description": "Padaria", "type": "EXPENSE", "source_type": None, "source_id": None,
            "transfer_account_id": None, "client_id": "client-0001", "share_mode": None, "share_others_amount": None,
            "share_person": None, "share_settled_at": None, "category_id": "FOOD", "needs_review": 0,
            "transfer_amount": None, "card_id": None, "occurred_at": None, "share_paid_by": None, "metadata": None,
        }

    def test_a_transfer(self, world, user):
        bank, savings = world.account("Banco"), world.account("Poupança")
        row = world.transfer(300, "2026-10-05", bank, savings)
        [line] = stored("transactions", "id = ?", (row["id"],))
        line = named(line, {bank["id"]: "BANK", savings["id"]: "SAVINGS"})
        assert (line["type"], line["account_id"], line["transfer_account_id"], line["amount"]) == (
            "TRANSFER", "BANK", "SAVINGS", 300.0)
        assert (line["category"], line["category_id"], line["transfer_amount"], line["needs_review"]) == (
            "Transferencia", None, None, 0)
        assert (line["source_type"], line["source_id"], line["occurred_at"], line["card_id"]) == (None, None, None, None)

    def test_a_card_purchase_in_three(self, world, user):
        card = world.card()
        made = world.call("post", "/api/cc-expenses/purchases", json={
            "card_id": card["id"], "total_amount": 100, "purchase_date": "2026-10-05", "description": "Loja",
            "installments": 3, "category": "Alimentação", "client_id": "client-0002",
        }).get_json()
        lines = stored("cc_expenses", "client_id = ?", ("client-0002",))
        assert len(made if isinstance(made, list) else made.get("items", made.get("expenses", [1, 2, 3]))) == 3
        assert [(l["amount"], l["installment_info"], l["invoice_month"], l["invoice_year"]) for l in lines] == [
            (33.34, "1/3", 11, 2026), (33.33, "2/3", 12, 2026), (33.33, "3/3", 1, 2027)]
        food = world.category_id("Alimentação")
        first = named(lines[0], {card["id"]: "CARD", food: "FOOD"})
        assert first == {
            "card_id": "CARD", "category": "Alimentação", "description": "Loja", "amount": 33.34,
            "purchase_date": "2026-10-05", "invoice_month": 11, "invoice_year": 2026, "installment_info": "1/3",
            "status": "OPEN", "client_id": "client-0002", "share_mode": None, "share_others_amount": None,
            "share_person": None, "share_settled_at": None, "kind": "PURCHASE", "category_id": "FOOD",
            "paid_by": None, "needs_review": 0, "occurred_at": None, "refund_of": None, "share_paid_by": None,
        }


class TestTheEngine:
    def test_an_expense(self, world, user):
        bank = world.account("Banco")
        table, row_id = engine_entry(user, base_item(account_id=bank["id"]))
        [line] = stored(table, "id = ?", (row_id,))
        assert named(line, {bank["id"]: "BANK"}) == {
            "account_id": "BANK", "amount": 45.9, "date": "2026-10-05", "category": "Alimentação",
            "description": "Padaria", "type": "EXPENSE", "source_type": None, "source_id": None,
            "transfer_account_id": None, "client_id": "notify:abc", "share_mode": None, "share_others_amount": None,
            "share_person": None, "share_settled_at": None, "category_id": None, "needs_review": 0,
            "transfer_amount": None, "card_id": None, "occurred_at": "2026-10-05T12:30:00-03:00",
            "share_paid_by": None, "metadata": None,
        }

    def test_a_transfer(self, world, user):
        bank, savings = world.account("Banco"), world.account("Poupança")
        table, row_id = engine_entry(user, base_item(
            entry_type="TRANSFER", account_id=bank["id"], transfer_account_id=savings["id"], category=None,
            description="Pix",
        ))
        [line] = stored(table, "id = ?", (row_id,))
        line = named(line, {bank["id"]: "BANK", savings["id"]: "SAVINGS"})
        assert (line["type"], line["account_id"], line["transfer_account_id"], line["amount"]) == (
            "TRANSFER", "BANK", "SAVINGS", 45.9)
        assert (line["category"], line["transfer_amount"], line["occurred_at"], line["client_id"]) == (
            "Transferencia", None, "2026-10-05T12:30:00-03:00", "notify:abc")

    def test_a_card_purchase_in_two(self, world, user):
        card = world.card()
        table, first_id = engine_entry(user, base_item(entry_type="CARD", card_id=card["id"], installments=2, amount=100.01))
        lines = stored(table, "client_id = ?", ("notify:abc",))
        assert [(l["amount"], l["installment_info"], l["invoice_month"], l["status"], l["kind"]) for l in lines] == [
            (50.01, "1/2", 11, "OPEN", "PURCHASE"), (50.0, "2/2", 12, "OPEN", "PURCHASE")]
        assert {l["occurred_at"] for l in lines} == {"2026-10-05T12:30:00-03:00"}
        assert {l["description"] for l in lines} == {"Padaria"}

    def test_a_card_refund(self, world, user):
        card = world.card()
        table, row_id = engine_entry(user, base_item(
            entry_type="CARD", direction="IN", card_id=card["id"], amount=20, description="Estorno Loja",
        ))
        [line] = stored(table, "id = ?", (row_id,))
        assert (line["kind"], line["amount"], line["installment_info"], line["status"], line["client_id"]) == (
            "REFUND", 20.0, "1/1", "OPEN", "notify:abc")
