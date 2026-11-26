"""Tudo automatico, Fase 1.3 (automation-prompt): nada espera o dono.

- A ponta so da Corretora (a Pluggy da BTG Investimentos traz a TED, o banco
  nao): passada TRANSFER_MATCH_DAYS, vira o aporte/resgate com o banco ao lado
  adivinhado (`guessed`). A ponta real que chega depois junta (mesma conta) ou
  move o palpite (outra conta), nunca uma linha a mais.
- O Pix em reais para a conta global, so avisado: ja vira a despesa em reais na
  hora (nada a decidir).
- O valor em outra moeda sem a PTAX do dia: a ultima antes dele, marcada.
Cada decisao fica em GET /api/review/auto, com "Desfazer".
"""

import importlib
from datetime import date, datetime, timedelta

import pytest

from finance_world import freeze
from identity_check import assert_identity
from open_finance_world import World, bank_tx, connected, fake_pluggy, open_finance_module  # noqa: F401
from test_auto_record import notifications_on
from test_global_account import WISE_BRASIL
from test_inbox import BB, ITAU, detection, ms, send
from test_open_finance_auto import auto_on, meupluggy

pytestmark = pytest.mark.usefixtures("any_bank_notifications")

TRANSFER = "04000000"
BROKERAGE = "com.btg.pactual.digital.mobile"
RATE = 5.5


@pytest.fixture()
def world(client, auth, fake_pluggy):
    return World(client, auth, fake_pluggy)


@pytest.fixture()
def clock(monkeypatch):
    dates = importlib.import_module("dates")

    def set_day(year, month, day):
        # O relogio de todos: dates.now_source, e o local_today que
        # open_finance_world congelou modulo a modulo (2026-10-27).
        monkeypatch.setattr(dates, "now_source", lambda: datetime(year, month, day, 12))
        freeze(monkeypatch, date(year, month, day))
    return set_day


@pytest.fixture()
def ptax(app_module, monkeypatch):
    """A PTAX so nos dias que o teste da (o BCB fora no resto)."""
    fx = importlib.import_module("services.fx")
    fx.reset_fetch_throttle()
    days = set()

    def window(series, start, end):
        rows, day = [], start.date()
        while day <= end.date():
            if day.isoformat() in days:
                rows.append({"data": day.strftime("%d/%m/%Y"), "valor": f"{RATE:.4f}"})
            day += timedelta(days=1)
        return rows

    monkeypatch.setattr(fx, "fetch_bcb_window", window)
    return days


def decisions(world, kind=None):
    return [entry for entry in world.call("get", "/api/review/auto")["items"] if kind is None or entry["kind"] == kind]


def thousand(world):
    return [row for row in world.transactions() if row["amount"] == 1000.0]


# ---------------------------------------------------------------------------
# A ponta so da Corretora
# ---------------------------------------------------------------------------

class TestTheCorretoraAlone:
    def _broker_only(self, world, clock):
        made = meupluggy(world)
        auto_on(world)
        broker, _of, corretora = made["btg:0002/2-2X"]
        clock(2026, 10, 20)
        world.fake.add_tx(broker, bank_tx(1000, "2026-10-20", "TED RECEBIDA", category_id=TRANSFER))
        world.sync(made["items"]["btg"])
        assert thousand(world) == []  # dentro da janela: espera a outra ponta
        clock(2026, 10, 22)
        world.sync(made["items"]["btg"])
        return made, corretora

    def test_after_the_window_it_is_an_aporte_with_the_bank_guessed(self, world, user, clock):
        made, corretora = self._broker_only(world, clock)
        btg_id = made["btg:0002/2-2"][2]
        [row] = thousand(world)
        assert (row["type"], row["account_id"], row["transfer_account_id"], row["needs_review"]) == (
            "TRANSFER", btg_id, corretora, 1,
        )
        [decision] = decisions(world, "transfer_guess")
        assert decision["target_id"] == row["id"]
        assert world.pending() == []
        assert_identity(user["id"])

    def test_the_real_side_on_the_guessed_account_joins(self, world, user, clock):
        made, _corretora = self._broker_only(world, clock)
        [first] = thousand(world)
        world.fake.add_tx(made["btg:0002/2-2"][0], bank_tx(-1000, "2026-10-20", "TED BTG INVEST", category_id=TRANSFER))
        world.sync(made["items"]["btg"])
        assert [row["id"] for row in thousand(world)] == [first["id"]]
        assert_identity(user["id"])

    def test_the_real_side_on_another_bank_moves_the_guess(self, world, user, clock):
        made, corretora = self._broker_only(world, clock)
        [first] = thousand(world)
        bb = made["bb:0003/3-3"]
        world.fake.add_tx(bb[0], bank_tx(-1000, "2026-10-20", "TED BTG INVEST", category_id=TRANSFER))
        world.sync(made["items"]["bb"])
        [row] = thousand(world)
        assert (row["id"], row["account_id"], row["transfer_account_id"]) == (first["id"], bb[2], corretora)
        assert_identity(user["id"])

    def test_the_other_side_inside_the_window_is_the_old_way(self, world, user, clock):
        made = meupluggy(world)
        auto_on(world)
        broker, _of, corretora = made["btg:0002/2-2X"]
        clock(2026, 10, 20)
        world.fake.add_tx(broker, bank_tx(1000, "2026-10-20", "TED RECEBIDA", category_id=TRANSFER))
        world.sync(made["items"]["btg"])
        world.fake.add_tx(made["btg:0002/2-2"][0], bank_tx(-1000, "2026-10-20", "TED BTG INVEST", category_id=TRANSFER))
        world.sync(made["items"]["btg"])
        [row] = thousand(world)
        assert (row["type"], row["transfer_account_id"]) == ("TRANSFER", corretora)
        assert decisions(world) == []
        assert_identity(user["id"])

    def test_both_notices_join_the_waiting_corretora_item(self, world, user, clock):
        # 2026-11-18 (fuzz seed 4): o aviso do Itau entra na saida do item que a
        # Corretora abriu; o da BTG Investimentos, na entrada do MESMO item —
        # nunca uma segunda transferencia com o banco adivinhado.
        made = meupluggy(world)
        auto_on(world)
        broker, _of, corretora = made["btg:0002/2-2X"]
        itau = made["itau:0001/1-1"][2]
        clock(2026, 10, 20)
        world.fake.add_tx(broker, bank_tx(1000, "2026-10-20", "TED RECEBIDA", category_id=TRANSFER))
        world.sync(made["items"]["btg"])
        send(world.client, world.auth, detection("PIX_OUT", 100000, at=ms(2026, 10, 20, 9, 0), app=ITAU,
                                                 merchant=None, counterparty="BTG PACTUAL"))
        send(world.client, world.auth, detection("TRANSFER_IN", 100000, at=ms(2026, 10, 20, 9, 1), app=BROKERAGE,
                                                 merchant=None))
        world.sync(made["items"]["btg"])
        [row] = thousand(world)
        assert (row["type"], row["account_id"], row["transfer_account_id"]) == ("TRANSFER", itau, corretora)
        assert_identity(user["id"])

    def test_undo_puts_it_back_in_review(self, world, clock):
        _made, _corretora = self._broker_only(world, clock)
        [row] = thousand(world)
        world.call("post", "/api/review", json={"items": [{"table": "transactions", "id": row["id"]}]})
        [decision] = decisions(world, "transfer_guess")
        world.call("post", f"/api/review/auto/{decision['id']}/undo")
        assert world.call("get", "/api/review")["count"] == 1


# ---------------------------------------------------------------------------
# O Pix para a conta global, so avisado
# ---------------------------------------------------------------------------

class TestTheGlobalPixAlone:
    def _setup(self, world, client, auth):
        notifications_on(client, auth)
        bb = world.account("BB", institution="Banco do Brasil")
        wise = world.account("Wise", institution="Wise", currency="USD")
        return bb, wise

    def _notice(self, client, auth, day=20):
        send(client, auth, detection("PIX_OUT", 55000, at=ms(2026, 10, day, 9, 0), app=BB, merchant=None,
                                     counterparty=WISE_BRASIL))

    def test_the_reais_side_is_an_expense_at_once(self, world, client, auth, user, clock, ptax):
        # Ja nao esperava: o aviso grava a despesa em reais na hora, e o
        # credito em dolar, quando vier pela Pluggy, faz a transferencia.
        bb, _wise = self._setup(world, client, auth)
        clock(2026, 10, 20)
        self._notice(client, auth)
        [row] = [row for row in world.transactions(bb) if row["amount"] == 550.0]
        assert (row["type"], row["needs_review"]) == ("EXPENSE", 1)
        assert decisions(world) == []
        assert_identity(user["id"])


# ---------------------------------------------------------------------------
# Outra moeda sem a PTAX do dia
# ---------------------------------------------------------------------------

class TestTheRateFallback:
    def _usd(self, world, ptax_days, ptax):
        item_id, _p, made = connected(world)
        auto_on(world)
        ptax.update(ptax_days)
        tx = bank_tx(-10.0, "2026-10-20", "COMPRA EXTERIOR")
        tx["currencyCode"] = "USD"
        world.fake.add_tx(made["bank"][0], tx)
        world.sync(item_id)
        return made["bank"][2]

    def test_without_the_days_ptax_it_takes_the_last_one(self, world, user, ptax):
        # So a de 09/10 guardada, e o BCB fora desde entao.
        db = importlib.import_module("db")
        with db.get_db() as conn:
            conn.execute(
                "INSERT INTO fx_rates (user_id, currency, rate_date, rate) VALUES (?, 'USD', '2026-10-09', ?)",
                (user["id"], RATE),
            )
        mine = self._usd(world, set(), ptax)
        [row] = world.transactions(mine)
        assert (row["amount"], row["needs_review"]) == (55.0, 1)
        [decision] = decisions(world, "fx_fallback")
        assert (decision["detail"]["rate_date"], decision["detail"]["day"]) == ("2026-10-09", "2026-10-20")
        world.call("post", "/api/review", json={"items": [{"table": "transactions", "id": row["id"]}]})
        world.call("post", f"/api/review/auto/{decision['id']}/undo")
        assert world.transactions(mine)[0]["needs_review"] == 1
        assert_identity(user["id"])

    def test_a_weekend_is_the_normal_rule_and_no_decision(self, world, ptax):
        mine = self._usd(world, {"2026-10-16"}, ptax)  # sexta; 20/10 sem PTAX ainda guardada
        [row] = world.transactions(mine)
        assert row["amount"] == 55.0
        assert decisions(world) == []
