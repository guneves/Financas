"""Conta global (dono, 2026-10-27): a conta Wise em dolar.

O que estes testes protegem:
- mapear: a conta em dolar da Pluggy so vai para uma conta em dolar do app
  (e a sugestao e a unica dela); reais com dolar e recusado nos dois sentidos;
- a linha da Pluggy da conta global fica em dolar do item ao lancamento, ao
  saldo e a Conferencia — nunca convertida;
- o Pix em reais para "WISE BRASIL CORRETORA DE CAMBIO" e o credito em dolar
  na Wise sao UMA transferencia (o que saiu em reais, o que entrou em dolar),
  em qualquer ordem de pull, pelo dia e pela contraparte, nunca pelos
  centavos; dois no mesmo dia vao para o par de cambio mais perto da PTAX;
- a transferencia nunca e despesa nem receita: Resumo do mes, plano e
  orcamento nao mudam; o que a conta global faz sozinha fica fora dos totais
  em reais, do Extrato e da fila de revisao em reais;
- POST /api/transfers e PATCH entre moedas pedem o valor no destino;
- a conta "Wise" criada em reais (so recebeu Pix) vira global, e o pull da
  Pluggy da a cada transferencia o dolar que a Wise creditou, sem duplicar.
"""

import importlib
from datetime import timedelta

import pytest

from open_finance_world import World, bank_tx, connected, fake_pluggy, open_finance_module  # noqa: F401

SETTINGS = "/api/open-finance/settings"
WISE_BRASIL = "WISE BRASIL CORRETORA DE CAMBIO LTDA."
# Os tres Pix do dono (2026-10-06/07) e o que a Wise creditou em dolar.
PIX = [("2026-10-06", 253.53, 46.10), ("2026-10-06", 101.43, 18.44), ("2026-10-07", 204.47, 37.18)]
RATE = 5.50


@pytest.fixture(autouse=True)
def offline(app_module, monkeypatch):
    fx = importlib.import_module("services.fx")
    fx.reset_fetch_throttle()

    def ptax(series, start, end):
        rows, day = [], start.date()
        while day <= end.date():
            if day.weekday() < 5:
                rows.append({"data": day.strftime("%d/%m/%Y"), "valor": f"{RATE:.4f}"})
            day += timedelta(days=1)
        return rows

    monkeypatch.setattr(fx, "fetch_bcb_window", ptax)


@pytest.fixture()
def world(client, auth, fake_pluggy):
    return World(client, auth, fake_pluggy)


def rows_of(table, where="1=1", params=()):
    db = importlib.import_module("db")
    with db.get_db() as conn:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table} WHERE {where}", params).fetchall()]


def pull(world, item_id):
    """Puxa de novo desde o comeco (os Pix de 06/10 ficam antes da sobreposicao
    de um segundo pull)."""
    db = importlib.import_module("db")
    with db.get_db() as conn:
        conn.execute("UPDATE open_finance_accounts SET synced_until = NULL")
    world.sync(item_id)


def usd_tx(amount, day, description="Received money", **extra):
    tx = bank_tx(amount, day, description=description, **extra)
    tx["currencyCode"] = "USD"
    return tx


def pix_to_wise(amount, day):
    return bank_tx(-amount, day, description="Pix enviado", payment_method="PIX", counterparty=WISE_BRASIL,
                   category_id="05070000")


def balance(world, account_id):
    return next(row for row in world.call("get", "/api/accounts") if row["id"] == account_id)


def global_world(world, *, map_wise=True):
    """BTG (reais) e Wise (dolar) no MeuPluggy, as duas mapeadas; Gravar
    sozinho ligado. Devolve um dict com os ids."""
    fake = world.fake
    pluggy_item = fake.add_item("MeuPluggy")
    btg_pluggy = fake.add_account(pluggy_item, "BANK", name="BTG Banking", number="0002/2-2", balance=170.0)
    wise_pluggy = fake.add_account(pluggy_item, "BANK", name="Wise USD", number="USD-1", balance=101.72)
    fake.accounts[pluggy_item][1]["currencyCode"] = "USD"
    body = world.connect(pluggy_item)
    item = next(entry for entry in body["items"] if entry["id"] == body["item_id"])
    by_number = {entry["number"]: entry for entry in item["accounts"]}
    btg = world.account("BTG conta corrente", initial_balance=729.43)
    wise = world.account("Wise", institution="Wise", currency="USD")
    world.map(by_number["0002/2-2"]["id"], account_id=btg)
    if map_wise:
        world.map(by_number["USD-1"]["id"], account_id=wise)
    else:
        world.map(by_number["USD-1"]["id"], ignore=True)
    world.call("patch", SETTINGS, json={"auto_record": True})
    return {
        "item": body["item_id"], "btg": btg, "wise": wise, "btg_pluggy": btg_pluggy, "wise_pluggy": wise_pluggy,
        "btg_of": by_number["0002/2-2"]["id"], "wise_of": by_number["USD-1"]["id"],
    }


def transfers(world):
    rows = world.call("get", "/api/transactions")
    return sorted(
        ((row["date"], row["amount"], row["transfer_amount"]) for row in rows if row["type"] == "TRANSFER"),
    )


# ---------------------------------------------------------------------------
# Mapear
# ---------------------------------------------------------------------------

class TestMapping:
    def setup_accounts(self, world):
        fake = world.fake
        pluggy_item = fake.add_item("MeuPluggy")
        fake.add_account(pluggy_item, "BANK", name="Wise USD", number="USD-1")
        fake.add_account(pluggy_item, "BANK", name="BTG Banking", number="BRL-1")
        fake.accounts[pluggy_item][0]["currencyCode"] = "USD"
        body = world.connect(pluggy_item)
        item = next(entry for entry in body["items"] if entry["id"] == body["item_id"])
        return {entry["number"]: entry for entry in item["accounts"]}

    def test_dollar_goes_to_dollar_and_is_suggested(self, world):
        wise = world.account("Wise", currency="USD")
        world.account("BTG conta corrente")
        accounts = self.setup_accounts(world)
        assert accounts["USD-1"]["currency"] == "USD"
        assert accounts["USD-1"]["suggested_id"] == wise
        world.map(accounts["USD-1"]["id"], account_id=wise)

    def test_dollar_to_reais_is_refused(self, world):
        reais = world.account("BTG conta corrente")
        accounts = self.setup_accounts(world)
        error = world.map(accounts["USD-1"]["id"], expected=400, account_id=reais)["error"]
        assert "USD" in error

    def test_reais_to_dollar_is_refused(self, world):
        wise = world.account("Wise", currency="USD")
        accounts = self.setup_accounts(world)
        error = world.map(accounts["BRL-1"]["id"], expected=400, account_id=wise)["error"]
        assert "reais" in error
        assert accounts["BRL-1"]["suggested_id"] != wise


# ---------------------------------------------------------------------------
# A linha em dolar
# ---------------------------------------------------------------------------

class TestDollarRows:
    def test_a_wise_row_stays_in_dollars(self, world):
        ids = global_world(world)
        # amountInAccountCurrency e para o cartao em reais; aqui a conta e em dolar.
        tx = usd_tx(12.34, "2026-10-20", description="Interest")
        tx["amountInAccountCurrency"] = 12.34
        world.fake.add_tx(ids["wise_pluggy"], tx)
        pull(world, ids["item"])

        [row] = rows_of("open_finance_transactions", "of_account_id = ?", (ids["wise_of"],))
        assert (row["currency"], row["amount_cents"]) == ("USD", 1234)
        own = world.call("get", f"/api/transactions?account_id={ids['wise']}")
        assert [(r["type"], r["amount"]) for r in own] == [("INCOME", 12.34)]
        assert balance(world, ids["wise"])["balance"] == 12.34
        assert balance(world, ids["wise"])["balance_brl"] == pytest.approx(12.34 * RATE)

    def test_the_dollar_row_stays_out_of_reais(self, world):
        ids = global_world(world)
        world.fake.add_tx(ids["wise_pluggy"], usd_tx(-9.99, "2026-10-20", description="Spotify"))
        world.fake.add_tx(ids["wise_pluggy"], usd_tx(50.0, "2026-10-20", description="Interest"))
        pull(world, ids["item"])
        assert len(world.call("get", f"/api/transactions?account_id={ids['wise']}")) == 2

        # Extrato, revisao, Resumo do mes e plano sao em reais.
        assert world.call("get", "/api/transactions") == []
        assert world.call("get", "/api/review")["items"] == []
        home = world.call("get", "/api/home")
        assert home["review_count"] == 0
        assert home["summary"]["income"] == 0
        assert home["summary"]["expense"] == 0
        # Revisada na tela dela, por id.
        wise_rows = world.call("get", f"/api/transactions?account_id={ids['wise']}&review=1")
        assert len(wise_rows) == 2
        world.call("post", "/api/review", json={"items": [{"table": "transactions", "id": r["id"]} for r in wise_rows]})
        assert world.call("get", f"/api/transactions?account_id={ids['wise']}&review=1") == []

    def test_the_conference_is_in_dollars(self, world):
        ids = global_world(world)
        world.fake.accounts[next(iter(world.fake.accounts))][1]["balance"] = 50.0
        world.fake.add_tx(ids["wise_pluggy"], usd_tx(50.0, "2026-10-20", description="Interest"))
        pull(world, ids["item"])
        wise = next(
            account for item in world.overview()["items"] for account in item["accounts"]
            if account["id"] == ids["wise_of"]
        )
        assert wise["currency"] == "USD"
        assert (wise["pluggy_balance"], wise["app_balance"], wise["difference"]) == (50.0, 50.0, 0)
        assert wise["check"]["bank_only"] == [] and wise["check"]["app_only"] == []


# ---------------------------------------------------------------------------
# A transferencia entre moedas
# ---------------------------------------------------------------------------

def add_pix(world, ids, *, real=True, dollar=True):
    for day, brl, usd in PIX:
        if real:
            world.fake.add_tx(ids["btg_pluggy"], pix_to_wise(brl, day))
        if dollar:
            world.fake.add_tx(ids["wise_pluggy"], usd_tx(usd, day))


EXPECTED = sorted((day, brl, usd) for day, brl, usd in PIX)


class TestCrossCurrencyTransfer:
    def assert_three_transfers(self, world, ids):
        assert transfers(world) == EXPECTED
        rows = world.call("get", "/api/transactions") + world.call("get", f"/api/transactions?account_id={ids['wise']}")
        assert {row["type"] for row in rows} == {"TRANSFER"}
        assert balance(world, ids["btg"])["balance"] == 170.0
        assert balance(world, ids["wise"])["balance"] == pytest.approx(101.72)
        assert not world.pending()

    def test_one_pull_with_both_sides(self, world):
        ids = global_world(world)
        add_pix(world, ids)
        pull(world, ids["item"])
        self.assert_three_transfers(world, ids)

    def test_reais_first_then_dollars(self, world):
        ids = global_world(world)
        add_pix(world, ids, dollar=False)
        pull(world, ids["item"])
        # A ponta em reais espera a outra: nunca despesa.
        assert transfers(world) == []
        assert world.call("get", "/api/transactions") == []
        add_pix(world, ids, real=False)
        pull(world, ids["item"])
        self.assert_three_transfers(world, ids)

    def test_dollars_first_then_reais(self, world):
        ids = global_world(world)
        add_pix(world, ids, real=False)
        pull(world, ids["item"])
        # Os creditos sao de 06/10: passado o prazo de espera, viraram receita
        # em dolar (intocadas, a revisar)...
        income = [r for r in world.call("get", f"/api/transactions?account_id={ids['wise']}") if r["type"] == "INCOME"]
        assert len(income) == 3
        add_pix(world, ids, dollar=False)
        pull(world, ids["item"])
        # ... e a ponta em reais faz de cada uma a transferencia (a mesma linha).
        self.assert_three_transfers(world, ids)
        assert {row["id"] for row in income} == {
            row["id"] for row in world.call("get", f"/api/transactions?account_id={ids['wise']}")
        }

    def test_an_edited_dollar_income_is_left_alone(self, world):
        ids = global_world(world)
        add_pix(world, ids, real=False)
        pull(world, ids["item"])
        income = world.call("get", f"/api/transactions?account_id={ids['wise']}")
        for row in income:
            world.call("patch", f"/api/transactions/{row['id']}", json={"description": "Dolar"})
        add_pix(world, ids, dollar=False)
        pull(world, ids["item"])
        # Editada pelo dono: nao e refeita; o Pix espera (nunca despesa).
        assert transfers(world) == []
        assert world.call("get", "/api/transactions") == []

    def test_never_spent_nor_income(self, world):
        ids = global_world(world)
        add_pix(world, ids)
        pull(world, ids["item"])
        home = world.call("get", "/api/home")
        assert home["summary"]["income"] == 0
        assert home["summary"]["expense"] == 0
        plan = world.call("get", "/api/monthly-plan?month=2026-10")
        assert plan.get("spent", 0) in (0, None) or plan["spent"] == 0
        # Consolidado: so o BTG em reais; a Wise fica fora (dono, 2026-10-30).
        assert home["consolidated_balance"] == pytest.approx(170.0)

    def test_wise_not_connected_keeps_the_pix_waiting(self, world):
        ids = global_world(world, map_wise=False)
        add_pix(world, ids, dollar=False)
        pull(world, ids["item"])
        assert world.call("get", "/api/transactions") == []
        waiting = world.pending()
        assert len(waiting) == 3
        assert {item["entry_type"] for item in waiting} == {"TRANSFER"}
        # O dono completa: a conta global e quanto entrou.
        item = waiting[0]
        refused = world.approve(item, expected=400, transfer_account_id=ids["wise"])
        assert "outra moeda" in refused["error"]
        fresh = next(entry for entry in world.pending() if entry["id"] == item["id"])
        world.approve(fresh, transfer_account_id=ids["wise"], transfer_amount=10.0)
        assert balance(world, ids["wise"])["balance"] == 10.0


# ---------------------------------------------------------------------------
# A API das transferencias
# ---------------------------------------------------------------------------

class TestTransferApi:
    def test_create_needs_the_dollar_amount(self, world):
        btg = world.account("BTG conta corrente", initial_balance=1000)
        wise = world.account("Wise", currency="USD")
        body = {"amount": 253.53, "date": "2026-10-06", "account_id": btg, "transfer_account_id": wise}
        assert "moedas diferentes" in world.call("post", "/api/transfers", expected=400, json=body)["error"]
        made = world.call("post", "/api/transfers", expected=201, json={**body, "transfer_amount": 46.10})
        assert (made["amount"], made["transfer_amount"]) == (253.53, 46.10)
        assert balance(world, btg)["balance"] == pytest.approx(1000 - 253.53)
        assert balance(world, wise)["balance"] == 46.10

        world.call("patch", f"/api/transactions/{made['id']}", json={"transfer_amount": 46.2})
        assert balance(world, wise)["balance"] == 46.2

    def test_same_currency_refuses_a_second_amount(self, world):
        a = world.account("A")
        b = world.account("B")
        body = {"amount": 10, "date": "2026-10-06", "account_id": a, "transfer_account_id": b, "transfer_amount": 2}
        assert world.call("post", "/api/transfers", expected=400, json=body)["error"]

    def test_a_dollar_account_is_never_the_default(self, world):
        wise = world.account("Wise", currency="USD")
        assert world.call("patch", f"/api/accounts/{wise}", expected=400, json={"is_default": True})["error"]


# ---------------------------------------------------------------------------
# A "Wise" criada em reais vira a conta global
# ---------------------------------------------------------------------------

class TestConvert:
    def legacy(self, world):
        """O que o dono tinha: "Wise" em reais com os tres Pix da BTG."""
        fake = world.fake
        pluggy_item = fake.add_item("MeuPluggy")
        btg_pluggy = fake.add_account(pluggy_item, "BANK", name="BTG Banking", number="0002/2-2", balance=170.0)
        wise_pluggy = fake.add_account(pluggy_item, "BANK", name="Wise USD", number="USD-1", balance=101.72)
        fake.accounts[pluggy_item][1]["currencyCode"] = "USD"
        body = world.connect(pluggy_item)
        item = next(entry for entry in body["items"] if entry["id"] == body["item_id"])
        by_number = {entry["number"]: entry for entry in item["accounts"]}
        btg = world.account("BTG conta corrente", initial_balance=729.43)
        wise = world.account("Wise")
        world.map(by_number["0002/2-2"]["id"], account_id=btg)
        world.map(by_number["USD-1"]["id"], ignore=True)
        world.call("patch", SETTINGS, json={"auto_record": True})
        # Os Pix ja estavam no app como transferencias (2026-10-27).
        for day, brl, _usd in PIX:
            world.call("post", "/api/transfers", json={
                "amount": brl, "date": day, "account_id": btg, "transfer_account_id": wise,
                "description": "Pix para Wise",
            })
        return {"item": body["item_id"], "btg": btg, "wise": wise, "wise_pluggy": wise_pluggy,
                "wise_of": by_number["USD-1"]["id"]}

    def test_the_owner_case(self, world):
        ids = self.legacy(world)
        # Antes: tres transferencias em reais, Wise com R$ 559,43.
        assert transfers(world) == sorted((day, brl, None) for day, brl, _ in PIX)
        assert balance(world, ids["wise"])["balance"] == pytest.approx(559.43)

        world.call("patch", f"/api/accounts/{ids['wise']}", json={"currency": "USD"})
        # Sem o dolar ainda, nada entra: nunca R$ contado como US$.
        assert balance(world, ids["wise"])["balance"] == 0
        assert balance(world, ids["btg"])["balance"] == 170.0

        world.map(ids["wise_of"], account_id=ids["wise"])
        for day, _brl, usd in PIX:
            world.fake.add_tx(ids["wise_pluggy"], usd_tx(usd, day))
        pull(world, ids["item"])

        assert transfers(world) == EXPECTED
        assert balance(world, ids["wise"])["balance"] == pytest.approx(101.72)
        assert balance(world, ids["btg"])["balance"] == 170.0
        assert world.call("get", f"/api/transactions?account_id={ids['wise']}&review=1") == []
        assert [r["type"] for r in world.call("get", f"/api/transactions?account_id={ids['wise']}")] == ["TRANSFER"] * 3
        assert not world.pending()

    def test_an_account_with_its_own_rows_does_not_convert(self, world):
        account = world.account("Nubank")
        world.call("post", "/api/transactions", json={
            "amount": 10, "date": "2026-10-01", "category": "Lazer", "type": "EXPENSE", "account_id": account,
        })
        error = world.call("patch", f"/api/accounts/{account}", expected=400, json={"currency": "USD"})["error"]
        assert "conta global" in error

    def test_a_dollar_account_never_goes_back(self, world):
        wise = world.account("Wise", currency="USD")
        assert world.call("patch", f"/api/accounts/{wise}", expected=400, json={"currency": "BRL"})["error"]
