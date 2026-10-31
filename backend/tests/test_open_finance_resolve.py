"""Os botoes da Conferencia (dono, 2026-10-30): "Lancar" e "Aconteceu".

O que estes testes protegem:
- um movimento so no banco vira um lancamento, uma vez, a revisar; a transferencia
  de uma ponta so vira despesa/receita pelo lado que o banco viu;
- um lancamento que o banco nao tem fica porque o dono disse, sai de "so no app" e
  pode voltar; o de outro usuario nunca.
"""

import pytest

from open_finance_world import World, bank_tx, connected, fake_pluggy, open_finance_module  # noqa: F401
from test_open_finance_auto import auto_on
from test_open_finance_check import account_of, bank_moved_on


@pytest.fixture()
def world(client, auth, fake_pluggy):
    return World(client, auth, fake_pluggy)


class TestRecord:
    def denied(self, world, amount=-45.9):
        item_id, _pluggy, made = connected(world)
        world.fake.add_tx(made["bank"][0], bank_tx(amount, "2026-10-20", "PADARIA"))
        world.sync(item_id)
        [item] = world.pending()
        world.call("post", f"/api/inbox/{item['id']}/deny", json={"version": item["version"]})
        return made

    def test_a_refused_movement_becomes_an_entry_to_review(self, world):
        made = self.denied(world)
        [row] = account_of(world)["check"]["bank_only"]
        body = world.call("post", "/api/open-finance/check/record", json={"row_id": row["id"]})
        assert body["recorded"]["target_table"] == "transactions"
        [entry] = world.transactions(made["bank"][2])
        assert (entry["type"], entry["amount"], entry["needs_review"]) == ("EXPENSE", 45.9, 1)
        assert account_of(world)["check"]["bank_only"] == []

    def test_twice_is_refused(self, world):
        made = self.denied(world)
        [row] = account_of(world)["check"]["bank_only"]
        world.call("post", "/api/open-finance/check/record", json={"row_id": row["id"]})
        world.call("post", "/api/open-finance/check/record", expected=400, json={"row_id": row["id"]})
        assert len(world.transactions(made["bank"][2])) == 1

    def test_a_one_sided_transfer_takes_the_side_the_bank_saw(self, world):
        item_id, _pluggy, made = connected(world)
        auto_on(world)
        world.fake.add_tx(made["bank"][0], bank_tx(800, "2026-10-29", "TED recebida", category_id="04000000"))
        world.sync(item_id)
        sources = world.call("get", "/api/open-finance")["items"][0]["accounts"][0]["check"]
        row = (sources["bank_only"] or sources["awaiting"])[0]
        world.call("post", "/api/open-finance/check/record", json={"row_id": row["id"]})
        [entry] = world.transactions(made["bank"][2])
        assert (entry["type"], entry["amount"]) == ("INCOME", 800.0)

    def test_an_unknown_row(self, world):
        connected(world)
        world.call("post", "/api/open-finance/check/record", expected=404, json={"row_id": "nada"})


class TestConfirm:
    def only_in_the_app(self, world):
        item_id, pluggy_item, made = connected(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
        world.sync(item_id)
        world.approve(world.pending()[0])
        world.call("post", "/api/transactions", json={
            "account_id": made["bank"][2], "amount": 12.0, "date": "2026-10-21", "type": "EXPENSE", "category": "Outros",
            "description": "feira em dinheiro",
        })
        bank_moved_on(world, pluggy_item, item_id)
        [row] = account_of(world)["check"]["app_only"]
        return row

    def test_it_leaves_the_list_and_can_come_back(self, world):
        row = self.only_in_the_app(world)
        assert row["table"] == "transactions"
        world.call("post", "/api/open-finance/check/confirm", json={"table": row["table"], "id": row["id"]})
        check = account_of(world)["check"]
        assert (check["app_only"], check["app_only_count"]) == ([], 0)
        assert [entry["id"] for entry in check["confirmed"]] == [row["id"]]
        world.call("post", "/api/open-finance/check/confirm", json={"table": row["table"], "id": row["id"], "undo": True})
        assert [entry["id"] for entry in account_of(world)["check"]["app_only"]] == [row["id"]]

    def test_another_users_entry_is_not_found(self, world, client, other_user):
        row = self.only_in_the_app(world)
        response = client.post(
            "/api/open-finance/check/confirm", headers=other_user["headers"], json={"table": row["table"], "id": row["id"]},
        )
        assert response.status_code == 404

    def test_a_bad_table_is_refused(self, world):
        connected(world)
        world.call("post", "/api/open-finance/check/confirm", expected=400, json={"table": "users", "id": "x"})
