"""Rende Facil do Banco do Brasil (dono, 2026-10-27): a aplicacao automatica da
conta corrente nunca entra no app.

O que estes testes protegem:
- a linha da Pluggy "RENDE FACIL"/"REND.FACIL" e COVERED: nao vira item no
  Aprovar, nem lancamento com Gravar sozinho, nem aparece na conferencia;
- o aviso do celular com esse texto e ignorado;
- o resto da mesma conta segue o caminho de sempre.
"""

import importlib
import uuid

import pytest

from open_finance_world import World, bank_tx, connected, fake_pluggy, open_finance_module  # noqa: F401


@pytest.fixture()
def world(client, auth, fake_pluggy):
    return World(client, auth, fake_pluggy)


def bank_check(world):
    [item] = world.overview()["items"]
    return next(account for account in item["accounts"] if account["type"] == "BANK")["check"]


class TestText:
    @pytest.mark.parametrize("text", [
        "RENDE FACIL Rende Facil", "REND.FACIL Rende Facil", "RENDE FACIL", "Aplicação Rende Fácil",
    ])
    def test_the_bb_auto_investment(self, text):
        assert importlib.import_module("services.inbox").is_auto_invest(text)

    @pytest.mark.parametrize("text", ["PADARIA RENDER", "PIX - RECEBIDO 26/10", "FACIL MERCADO", "", None])
    def test_anything_else(self, text):
        assert not importlib.import_module("services.inbox").is_auto_invest(text)


class TestPluggy:
    def test_never_an_item_and_never_in_the_check(self, world):
        item_id, _p, made = connected(world, connector_name="Banco do Brasil")
        world.fake.add_tx(
            made["bank"][0],
            bank_tx(-100, "2026-10-09", "RENDE FACIL Rende Facil"),
            bank_tx(105, "2026-10-13", "REND.FACIL Rende Facil"),
            bank_tx(-45.9, "2026-10-20", "PADARIA"),
        )
        world.sync(item_id)

        assert [item["description"] for item in world.pending()] == ["Padaria"]
        check = bank_check(world)
        assert [entry["description"] for entry in check["awaiting"]] == ["PADARIA"]
        assert check["bank_only"] == []

    def test_gravar_sozinho_records_only_the_rest(self, world):
        item_id, _p, made = connected(world, connector_name="Banco do Brasil")
        world.call("patch", "/api/open-finance/settings", json={"auto_record": True})
        world.fake.add_tx(
            made["bank"][0],
            bank_tx(-9.81, "2026-10-19", "RENDE FACIL Rende Facil"),
            bank_tx(-45.9, "2026-10-20", "PADARIA"),
        )
        world.sync(item_id)

        rows = world.transactions(made["bank"][2])
        assert [row["description"] for row in rows] == ["Padaria"]
        assert bank_check(world)["bank_only"] == []


class TestNotification:
    def test_the_phone_notice_is_ignored(self, client, auth):
        body = {
            "key": uuid.uuid4().hex + uuid.uuid4().hex,
            "app": "br.com.bb.android",
            "kind": "DEBIT_PURCHASE",
            "amount_cents": 1000,
            "posted_ms": 1793280000000,
            "utc_offset_minutes": -180,
            "merchant": "RENDE FACIL",
        }
        response = client.post("/api/inbox/detections", json={"detections": [body]}, headers=auth)
        assert response.status_code == 200, response.get_data(as_text=True)
        assert response.get_json()["results"][0]["status"] == "ignored"
        assert client.get("/api/inbox", headers=auth).get_json()["items"] == []
