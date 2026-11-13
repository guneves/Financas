"""O gasto do mes no Inicio: o que o JavaScript da web calcula e o que o
servidor entrega em GET /api/home/panels (lido pelo APK), para os mesmos dados.

A web ainda baixa o historico inteiro e soma no navegador
(frontend/src/lib/homeSpending.js); o servidor soma em services/home_panels.py.
Sao duas implementacoes da mesma conta. Este teste monta um mes com cada tipo
de linha e compara as duas, categoria por categoria, em centavos: e a condicao
para a web poder trocar a soma dela pela do servidor sem mudar um numero.

Precisa do `node` (roda o modulo de verdade, nao uma copia); sem ele, pula.
"""

import json
import os
import shutil
import subprocess
from datetime import date

import pytest
from finance_world import World, freeze

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "frontend", "src", "lib", "homeSpending.parity.mjs",
)
MONTH = "2026-10"
DAY = "2026-10-05"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="sem node para rodar o calculo da web")


@pytest.fixture()
def world(client, user, app_module, monkeypatch):
    freeze(monkeypatch, date(2026, 10, 20))
    return World(client, user)


def web_spending(world):
    payload = {
        "transactions": world.get("/api/transactions"),
        "ccExpenses": world.get("/api/cc-expenses"),
        "accounts": world.get("/api/accounts?include_archived=1"),
        "month": MONTH,
    }
    done = subprocess.run(
        ["node", SCRIPT], input=json.dumps(payload), capture_output=True, text=True, timeout=60, check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def server_spending(world):
    panels = world.panels()
    def cents(value):
        return round(value * 100)

    return {
        "total": cents(panels["spending_total"]),
        "categories": {
            item["name"]: {"value": cents(item["value"]), "cash": cents(item["cash"]), "credit": cents(item["credit"])}
            for item in panels["categories"]
        },
    }


def test_the_web_and_the_server_count_the_same_month(world):
    bank = world.account("Banco", initial=10000)
    savings = world.account("Poupança")
    broker = world.account("XP", type_="BROKERAGE", initial=1000)
    wise = world.account("Wise", currency="USD")
    card = world.card()
    world.tx("EXPENSE", 100, DAY, bank, category="Alimentação")
    world.tx("EXPENSE", 33.33, "2026-10-07", bank, category="Transporte")
    world.tx("EXPENSE", 60, DAY, bank, category="Lazer", share_mode="SPLIT", share_others_amount=20, share_person="Ana")
    world.tx("EXPENSE", 30, DAY, bank, category="Lazer", share_mode="OTHERS", share_person="Ana")
    world.tx("INCOME", 5000, DAY, bank, category="Salário")
    world.tx("EXPENSE", 40, DAY, broker, category="Alimentação")
    world.transfer(500, DAY, bank, savings)
    world.transfer(300, DAY, bank, broker)
    world.purchase(card, 300, DAY, installments=3, category="Alimentação")
    world.purchase(card, 80, "2026-10-09", category="Lazer")
    world.refund(card, 50, "2026-10-10")
    world.purchase(card, 200, "2026-09-10")
    old = next(row for row in world.get("/api/cc-expenses") if row["purchase_date"] == "2026-09-10")
    world.pay(card, old["invoice_month"], old["invoice_year"], bank)
    world.insert_tx("EXPENSE", 70, DAY, bank, source_type="MONTH_SUMMARY")
    world.insert_tx("EXPENSE", 90, DAY, bank, source_type="INVESTMENT_TRANSACTION")
    world.insert_tx("EXPENSE", 10, DAY, bank, category="Pagamento Fatura Nubank")
    world.insert_tx("EXPENSE", 25, DAY, wise)
    world.tx("EXPENSE", 12.5, "2026-09-28", bank, category="Alimentação")

    web, server = web_spending(world), server_spending(world)
    assert web["categories"] == server["categories"]
    assert web["total"] == server["total"]
    # E o numero em si: 100 + 33,33 + 40 (a parte do dono) + 300 + 80 - 50 (estorno).
    assert server["total"] == 50333
