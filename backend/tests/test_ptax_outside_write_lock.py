"""A PTAX nunca e buscada no BCB com a transacao de escrita aberta.

O pull grava tudo numa transacao so. `in_reais_now()` (o movimento em outra
moeda numa conta em reais) chamava `fx.rate_on()` nessa conexao, que ia ao BCB:
com o BCB lento, a trava de escrita do SQLite ficava presa pela espera inteira
e qualquer edicao do dono respondia 500 ("database is locked") depois do
busy_timeout. Agora o cambio e buscado antes (`open_finance_auto.prefetch_rates`,
na fase de rede do pull e antes da passada das notificacoes) e, dentro da
transacao, so o guardado e lido.
"""

import importlib

import pytest
from tests.open_finance_world import (  # noqa: F401
    World,
    bank_tx,
    connected,
    fake_pluggy,
    open_finance_module,
)

NOW = "2026-10-27"


@pytest.fixture()
def world(client, auth, fake_pluggy, db_module, user):  # noqa: F811
    made = World(client, auth, fake_pluggy)
    with db_module.get_db() as conn:
        for key in ("open_finance_auto_record", "auto_record_notifications"):
            conn.execute(
                "INSERT OR REPLACE INTO user_settings (user_id, setting_key, value) VALUES (?, ?, '1')",
                (user["id"], key),
            )
    return made


@pytest.fixture()
def bcb(app_module, monkeypatch):
    """Um BCB falso (USD = 5,00 em 27/10) que anota se cada busca aconteceu com
    uma transacao aberta na conexao que a pediu."""
    fx = importlib.import_module("services.fx")
    fx.reset_fetch_throttle()
    calls = []
    original = fx.fetch_and_store

    def watched(conn, *args, **kwargs):
        calls.append(conn.in_transaction)
        return original(conn, *args, **kwargs)

    monkeypatch.setattr(fx, "fetch_and_store", watched)
    monkeypatch.setattr(fx, "fetch_bcb_window", lambda series, start, end: [{"data": "27/10/2026", "valor": "5.0"}])
    yield calls
    fx.reset_fetch_throttle()


def foreign_purchase(amount=-100.0):
    tx = bank_tx(amount, NOW, description="COMPRA EXTERIOR")
    tx["currencyCode"] = "USD"
    return tx


def test_the_pull_fetches_the_ptax_before_its_write_transaction(world, bcb):
    item_id, _pluggy, made = connected(world)
    pluggy_id, _of, account_id = made["bank"]
    world.fake.add_tx(pluggy_id, foreign_purchase())
    world.sync(item_id)
    assert bcb and not any(bcb), "o BCB foi consultado com a transacao de escrita aberta"
    # E nada espera: o mesmo pull grava a compra em reais, pela PTAX do dia.
    assert [(row["type"], row["amount"]) for row in world.transactions(account_id)] == [("EXPENSE", 500.0)]


def test_inside_a_transaction_only_the_stored_rate_is_read(world, bcb, db_module, user):
    fx = importlib.import_module("services.fx")
    with db_module.get_db() as conn:
        conn.execute("UPDATE users SET username = username WHERE id = ?", (user["id"],))
        assert conn.in_transaction
        with pytest.raises(fx.FxUnavailable):
            fx.rate_on(conn, user["id"], "USD", NOW, fetch=False)
        assert bcb == []
        # Fora de `fetch=False` nada muda: busca e guarda.
        assert fx.rate_on(conn, user["id"], "USD", NOW) == 5.0
        assert fx.rate_on(conn, user["id"], "USD", NOW, fetch=False) == 5.0


def test_prefetch_does_nothing_with_a_transaction_open(world, bcb, db_module, user):
    auto = importlib.import_module("services.open_finance_auto")
    with db_module.get_db() as conn:
        conn.execute("UPDATE users SET username = username WHERE id = ?", (user["id"],))
        auto.prefetch_rates(conn, user["id"], [("USD", NOW)])
        assert bcb == []
    with db_module.get_db() as conn:
        auto.prefetch_rates(conn, user["id"], [("USD", NOW), ("XXX", NOW)])
        assert bcb == [False]
        assert not conn.in_transaction  # o cambio guardado ja foi confirmado: nenhuma trava fica
        assert fx_rate(conn, user) == 5.0


def fx_rate(conn, user):
    return conn.execute(
        "SELECT rate FROM fx_rates WHERE user_id = ? AND currency = 'USD' AND rate_date = ?", (user["id"], NOW),
    ).fetchone()["rate"]
