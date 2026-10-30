"""Preferencias do Open Finance (GET/PATCH /api/open-finance/settings) e o que
elas mudam: a busca automatica por usuario (services/open_finance_refresh.py)
e "Trazer pendentes" (PENDING da Pluggy).

O que estes testes protegem:
- cada campo validado, PATCH parcial, nada gravado se um campo e invalido;
- nao existe aprovacao automatica (auto_approve e recusado);
- a busca automatica respeita o intervalo de cada usuario, 0 desliga, e uma
  tentativa que falha nao e repetida a cada passo da thread;
- pendentes: desligado pula; ligado entra, a mesma id liquidada atualiza a
  linha, uma id nova tira o item (REMOVED);
- outro usuario nao e tocado.
"""

import importlib
from datetime import datetime, timezone

import pytest

from open_finance_world import World, bank_tx, card_tx, connected, fake_pluggy, open_finance_module  # noqa: F401

SETTINGS = "/api/open-finance/settings"


@pytest.fixture()
def world(client, auth, fake_pluggy):
    return World(client, auth, fake_pluggy)


@pytest.fixture()
def refresh():
    module = importlib.import_module("services.open_finance_refresh")
    module.reset_attempts()
    yield module
    module.reset_attempts()


def rows_of(table, where="1=1", params=()):
    db = importlib.import_module("db")
    with db.get_db() as conn:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table} WHERE {where}", params).fetchall()]


def set_last_sync(item_id, stamp):
    db = importlib.import_module("db")
    with db.get_db() as conn:
        conn.execute("UPDATE open_finance_items SET last_sync_at = ? WHERE id = ?", (stamp, item_id))


def epoch(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()


class TestSettingsApi:
    def test_defaults(self, world):
        body = world.call("get", SETTINGS)
        assert body == {"first_sync_days": 30, "sync_hours": 6, "min_sync_hours": 6, "include_pending": False,
                        "auto_sync_available": False, "auto_record": False,
                        "auto_record_blockers": ["Conecte um banco antes de gravar sozinho."],
                        "ignore_notifications": True}

    def test_a_partial_patch_keeps_the_rest(self, world):
        body = world.call("patch", SETTINGS, json={"sync_hours": 8})
        assert (body["sync_hours"], body["first_sync_days"], body["include_pending"]) == (8, 30, False)
        body = world.call("patch", SETTINGS, json={"include_pending": True, "first_sync_days": 90})
        assert (body["sync_hours"], body["first_sync_days"], body["include_pending"]) == (8, 90, True)
        assert world.call("get", SETTINGS)["sync_hours"] == 8
        assert world.overview()["first_sync_days"] == 90

    @pytest.mark.parametrize("payload", [
        {"sync_hours": 25}, {"sync_hours": -1}, {"sync_hours": 1}, {"sync_hours": 5}, {"sync_hours": 0.5}, {"sync_hours": "6"}, {"sync_hours": True},
        {"sync_hours": None},
        {"first_sync_days": 0}, {"first_sync_days": 366}, {"first_sync_days": "x"}, {"first_sync_days": True},
        {"include_pending": "true"}, {"include_pending": 1}, {"include_pending": None},
        {"auto_approve": True}, {"auto_approve": False}, {"aprovar_sources": "open_finance_only"},
        {"ignore_notifications": False}, {"ignore_notifications": True},
        {},
    ])
    def test_invalid_values_are_refused(self, world, payload):
        world.call("patch", SETTINGS, expected=400, json=payload)

    def test_one_bad_field_writes_nothing(self, world):
        world.call("patch", SETTINGS, expected=400, json={"sync_hours": 12, "first_sync_days": 0})
        assert world.call("get", SETTINGS)["sync_hours"] == 6

    def test_zero_turns_the_automatic_pull_off(self, world):
        assert world.call("patch", SETTINGS, json={"sync_hours": 0})["sync_hours"] == 0
        assert world.call("get", SETTINGS)["sync_hours"] == 0

    def test_a_zero_nobody_chose_is_automatic(self, world, user):
        # Um "0" de antes de 2026-10-30 nao diz que o dono escolheu: toda conta
        # mapeada atualiza sozinha. So "Desligada" em Ajustes grava a escolha.
        inbox = importlib.import_module("services.inbox")
        db = importlib.import_module("db")
        with db.get_db() as conn:
            inbox.save_setting(conn, user["id"], "open_finance_sync_hours", "0")
        assert world.call("get", SETTINGS)["sync_hours"] == 6

    def test_the_message_says_why_below_one_hour(self, client, auth):
        response = client.patch(SETTINGS, json={"sync_hours": 30}, headers=auth)
        assert "hora" in response.get_json()["error"]

    def test_settings_are_per_user(self, world, client, other_user):
        world.call("patch", SETTINGS, json={"sync_hours": 12, "include_pending": True})
        other = client.get(SETTINGS, headers=other_user["headers"]).get_json()
        assert (other["sync_hours"], other["include_pending"]) == (6, False)

    def test_stored_in_user_settings(self, world, user):
        world.call("patch", SETTINGS, json={"sync_hours": 12})
        [row] = rows_of("user_settings", "setting_key = 'open_finance_sync_hours' AND user_id = ?", (user["id"],))
        assert row["value"] == "12"


class TestPerUserInterval:
    def test_due_only_after_the_users_interval(self, world, refresh, user):
        item_id, _p, _made = connected(world)
        world.call("patch", SETTINGS, json={"sync_hours": 8})
        set_last_sync(item_id, "2026-10-27T10:00:00Z")
        assert user["id"] not in refresh.due_user_ids(epoch("2026-10-27T17:59:00"))
        assert user["id"] in refresh.due_user_ids(epoch("2026-10-27T18:00:00"))

    def test_zero_is_never_due(self, world, refresh, user):
        item_id, _p, _made = connected(world)
        world.call("patch", SETTINGS, json={"sync_hours": 0})
        set_last_sync(item_id, "2026-10-20T10:00:00Z")
        assert user["id"] not in refresh.due_user_ids(epoch("2026-10-27T10:00:00"))

    def test_the_default_is_six_hours(self, world, refresh, user):
        item_id, _p, _made = connected(world)
        set_last_sync(item_id, "2026-10-27T10:00:00Z")
        assert user["id"] not in refresh.due_user_ids(epoch("2026-10-27T15:59:00"))
        assert user["id"] in refresh.due_user_ids(epoch("2026-10-27T16:00:00"))

    def test_a_zero_nobody_chose_is_due(self, world, refresh, user):
        item_id, _p, _made = connected(world)
        inbox = importlib.import_module("services.inbox")
        db = importlib.import_module("db")
        with db.get_db() as conn:
            inbox.save_setting(conn, user["id"], "open_finance_sync_hours", "0")
        set_last_sync(item_id, "2026-10-27T10:00:00Z")
        assert user["id"] in refresh.due_user_ids(epoch("2026-10-27T16:00:00"))

    def test_a_never_pulled_item_is_due(self, world, refresh, user):
        item_id, _p, _made = connected(world)
        set_last_sync(item_id, None)
        assert user["id"] in refresh.due_user_ids(epoch("2026-10-27T10:00:00"))

    def test_the_round_pulls_and_records_the_attempt(self, world, refresh, monkeypatch, open_finance_module, user):
        item_id, _p, made = connected(world)
        world.call("patch", SETTINGS, json={"sync_hours": 6})
        set_last_sync(item_id, "2026-10-27T02:00:00Z")
        world.fake.add_tx(made["bank"][0], bank_tx(-45.9, "2026-10-20"))
        calls = []
        real = open_finance_module.sync_user

        def failing(current_user_id):
            calls.append(current_user_id)
            raise RuntimeError("Pluggy fora")

        monkeypatch.setattr(open_finance_module, "sync_user", failing)
        now = epoch("2026-10-27T10:00:00")
        refresh.refresh_all_users(now)
        refresh.refresh_all_users(now + 15 * 60)
        assert calls.count(user["id"]) == 1  # a falha nao repete a cada passo
        monkeypatch.setattr(open_finance_module, "sync_user", real)
        results = refresh.refresh_all_users(now + 6 * 3600)
        assert item_id in results[user["id"]]
        assert len(world.pending()) == 1

    def test_each_user_has_their_own_interval(self, world, refresh, client, user, other_user, fake_pluggy):
        item_id, _p, _made = connected(world)
        set_last_sync(item_id, "2026-10-27T10:00:00Z")
        world.call("patch", SETTINGS, json={"sync_hours": 6})
        other_world = World(client, other_user["headers"], fake_pluggy)
        other_item, _p2, _m2 = connected(other_world)
        set_last_sync(other_item, "2026-10-27T10:00:00Z")
        other_world.call("patch", SETTINGS, json={"sync_hours": 24})
        due = refresh.due_user_ids(epoch("2026-10-27T16:00:00"))
        assert user["id"] in due and other_user["id"] not in due
        due = refresh.due_user_ids(epoch("2026-10-28T10:00:00"))
        assert user["id"] in due and other_user["id"] in due


class TestIncludePending:
    def test_off_skips_pending(self, world):
        item_id, _p, made = connected(world)
        world.fake.add_tx(made["bank"][0], bank_tx(-10, "2026-10-26", status="PENDING"))
        assert world.sync(item_id)["result"]["counts"] == {"skipped_pending": 1}
        assert world.pending() == []

    def test_on_brings_pending_into_aprovar(self, world):
        item_id, _p, made = connected(world)
        world.call("patch", SETTINGS, json={"include_pending": True})
        world.fake.add_tx(made["bank"][0], bank_tx(-10, "2026-10-26", status="PENDING"))
        assert world.sync(item_id)["result"]["counts"] == {"new": 1}
        [item] = world.pending()
        assert item["amount"] == 10

    def test_the_same_id_posting_updates_in_place(self, world):
        item_id, _p, made = connected(world)
        world.call("patch", SETTINGS, json={"include_pending": True})
        tx_id = world.fake.add_tx(made["bank"][0], bank_tx(-10, "2026-10-25", "PADARIA", status="PENDING"))
        world.sync(item_id)
        [before] = world.pending()
        world.fake.drop_tx(made["bank"][0], tx_id)
        world.fake.add_tx(made["bank"][0], bank_tx(-10, "2026-10-26", "PADARIA BOM PAO", tx_id=tx_id))
        assert world.sync(item_id)["result"]["counts"] == {"known": 1}
        [after] = world.pending()
        assert after["id"] == before["id"]
        [row] = rows_of("open_finance_transactions", "pluggy_transaction_id = ?", (tx_id,))
        assert (row["date"], row["description"], row["role"]) == ("2026-10-26", "PADARIA BOM PAO", "SOURCE")

    def test_a_new_id_on_posting_removes_the_old_item(self, world):
        item_id, _p, made = connected(world)
        world.call("patch", SETTINGS, json={"include_pending": True})
        old_id = world.fake.add_tx(made["bank"][0], bank_tx(-10, "2026-10-25", status="PENDING"))
        world.sync(item_id)
        [old_item] = world.pending()
        world.fake.drop_tx(made["bank"][0], old_id)
        world.fake.add_tx(made["bank"][0], bank_tx(-10, "2026-10-26"))
        world.sync(item_id)
        [new_item] = world.pending()
        assert new_item["id"] != old_item["id"]
        [old_row] = rows_of("open_finance_transactions", "pluggy_transaction_id = ?", (old_id,))
        assert old_row["role"] == "REMOVED"
        [removed] = rows_of("inbox_items", "id = ?", (old_item["id"],))
        assert removed["state"] == "REMOVED"

    def test_turning_it_off_keeps_what_was_pulled(self, world):
        item_id, _p, made = connected(world)
        world.call("patch", SETTINGS, json={"include_pending": True})
        world.fake.add_tx(made["bank"][0], bank_tx(-10, "2026-10-26", status="PENDING"))
        world.sync(item_id)
        world.call("patch", SETTINGS, json={"include_pending": False})
        world.sync(item_id)
        assert len(world.pending()) == 1

    def test_card_pending_on(self, world):
        item_id, _p, made = connected(world, bank=False, card=True)
        world.call("patch", SETTINGS, json={"include_pending": True})
        world.fake.add_tx(made["card"][0], card_tx(30, "2026-10-26", status="PENDING"))
        assert world.sync(item_id)["result"]["counts"] == {"new": 1}

    def test_only_this_users_setting_counts(self, world, client, other_user, fake_pluggy):
        world.call("patch", SETTINGS, json={"include_pending": True})
        other_world = World(client, other_user["headers"], fake_pluggy)
        other_item, _p, made = connected(other_world)
        other_world.fake.add_tx(made["bank"][0], bank_tx(-10, "2026-10-26", status="PENDING"))
        assert other_world.sync(other_item)["result"]["counts"] == {"skipped_pending": 1}
