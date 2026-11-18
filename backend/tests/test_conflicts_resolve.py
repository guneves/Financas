"""Tudo automatico, Fase 1.4 (docs/automation-prompt.md): os conflitos da
Pluggy se resolvem sozinhos (services/conflict_resolution.py).

- `changed`: 7 dias depois de apontado, o valor do banco vale, menos no valor
  que o dono digitou (atual != snapshot), com comprovante ou divisao;
- `vanished`: sai so pela prova do saldo (a regra das orfas);
- cada resolucao fica em GET /api/review/auto, com "Desfazer".
"""

import importlib

import pytest

from identity_check import assert_identity
from open_finance_world import World, bank_tx, fake_pluggy, open_finance_module  # noqa: F401
from test_auto_record import rows_of
from test_open_finance_orphans import Bank, world  # noqa: F401

pytestmark = pytest.mark.usefixtures("any_bank_notifications")


def decisions(world, kind=None):
    return [entry for entry in world.call("get", "/api/review/auto")["items"] if kind is None or entry["kind"] == kind]


def of_row(user_id, pluggy_id):
    [row] = rows_of("open_finance_transactions", "user_id = ? AND pluggy_transaction_id = ?", (user_id, pluggy_id))
    return row


def age_conflict(user_id, pluggy_id, stamp):
    db = importlib.import_module("db")
    with db.get_db() as conn:
        conn.execute(
            "UPDATE open_finance_transactions SET conflict_at = ? WHERE user_id = ? AND pluggy_transaction_id = ?",
            (stamp, user_id, pluggy_id),
        )


def recorded(bank, amount=-45.9, day="2026-10-20"):
    tx = bank_tx(amount, day, "PADARIA")
    bank.world.fake.add_tx(bank.pluggy_account, tx)
    bank.sync()
    [row] = bank.rows()
    return tx, row


def edit(world, row, **changes):
    body = {**{key: row[key] for key in ("account_id", "amount", "date", "type", "category")}, **changes}
    world.call("patch", f"/api/transactions/{row['id']}", json=body)


class TestChanged:
    def _conflict(self, world, user, **edits):
        bank = Bank(world)
        tx, row = recorded(bank)
        edit(world, row, **(edits or {"description": "padaria do bairro"}))
        tx["amount"] = -49.9
        bank.sync()
        assert of_row(user["id"], tx["id"])["conflict"] == "changed"
        return bank, tx, row

    def test_after_seven_days_the_bank_amount_wins(self, world, user):
        bank, tx, row = self._conflict(world, user)
        age_conflict(user["id"], tx["id"], "2026-10-24T10:00:00Z")
        bank.sync()
        [after] = bank.rows()
        assert (after["id"], after["amount"], after["description"]) == (row["id"], 49.9, "padaria do bairro")
        assert of_row(user["id"], tx["id"])["conflict"] is None
        [decision] = decisions(world, "conflict_changed")
        assert (decision["detail"]["before_cents"], decision["detail"]["after_cents"]) == (4590, 4990)
        # O banco muda de novo: segue (o snapshot andou).
        tx["amount"] = -51.9
        bank.sync()
        assert bank.rows()[0]["amount"] == 51.9
        assert_identity(user["id"])

    def test_inside_seven_days_it_stays(self, world, user):
        bank, tx, _row = self._conflict(world, user)
        age_conflict(user["id"], tx["id"], "2026-10-25T10:00:00Z")
        bank.sync()
        assert bank.rows()[0]["amount"] == 45.9
        assert decisions(world) == []

    def test_a_typed_amount_stays(self, world, user):
        bank, tx, _row = self._conflict(world, user, amount=47.0)
        age_conflict(user["id"], tx["id"], "2026-10-01T10:00:00Z")
        bank.sync()
        assert bank.rows()[0]["amount"] == 47.0
        assert of_row(user["id"], tx["id"])["conflict"] == "changed"

    def test_undo_puts_the_owners_amount_back_and_the_conflict(self, world, user):
        bank, tx, row = self._conflict(world, user)
        age_conflict(user["id"], tx["id"], "2026-10-24T10:00:00Z")
        bank.sync()
        [decision] = decisions(world, "conflict_changed")
        world.call("post", f"/api/review/auto/{decision['id']}/undo")
        assert bank.rows()[0]["amount"] == 45.9
        assert of_row(user["id"], tx["id"])["conflict"] == "changed"
        bank.sync()  # desfeita, nao volta
        assert bank.rows()[0]["amount"] == 45.9
        assert row


class TestVanished:
    def _vanished(self, world, user, balance):
        bank = Bank(world)
        bank.balance(-45.9)
        tx, row = recorded(bank)
        edit(world, row, category="Lazer")
        # Um pull vazio nao some com nada: o banco traz outra linha.
        world.fake.add_tx(bank.pluggy_account, bank_tx(-1, "2026-10-21", "OUTRA"))
        world.fake.drop_tx(bank.pluggy_account, tx["id"])
        bank.balance(balance)
        bank.sync()
        return bank, tx, row

    def test_the_balance_proves_it_so_it_leaves(self, world, user):
        bank, tx, row = self._vanished(world, user, -1.0)  # o banco nunca tirou os R$ 45,90
        assert [entry["amount"] for entry in bank.rows()] == [1.0]
        assert of_row(user["id"], tx["id"])["role"] == "REMOVED"
        [decision] = decisions(world, "conflict_vanished")
        assert decision["target_id"] == row["id"]
        assert bank.overview()["difference"] == 0
        assert_identity(user["id"])

    def test_the_balance_still_counts_it_so_it_stays(self, world, user):
        bank, tx, _row = self._vanished(world, user, -46.9)
        assert len(bank.rows()) == 2
        assert of_row(user["id"], tx["id"])["conflict"] == "vanished"
        assert decisions(world) == []

    def test_undo_brings_the_row_back(self, world, user):
        bank, _tx, row = self._vanished(world, user, -1.0)
        [decision] = decisions(world, "conflict_vanished")
        world.call("post", f"/api/review/auto/{decision['id']}/undo")
        [back] = [entry for entry in bank.rows() if entry["id"] == row["id"]]
        assert (back["amount"], back["category"]) == (45.9, "Lazer")
        bank.sync()
        assert len(bank.rows()) == 2
