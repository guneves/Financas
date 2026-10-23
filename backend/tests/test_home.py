"""GET /api/home: o saldo em contas, as contas e o fluxo do mes, no servidor.

Carrega os casos de `transactions.test.js` (o saldo consolidado sem a
Corretora, a visao bancaria de `bankingTransactions()`, o estorno no cartao,
investimento pela origem da linha) e cobre `buildMonthlyFlow()` de
`lib/cashFlow.js`, que nao tinha teste: a parte do dono, o cartao no mes da
compra, o pagamento de fatura fora da despesa, o saldo de fim de mes que
termina no saldo do topo, centavos exatos.

O mes congelado e 2026-10 salvo onde o teste diz outro.
"""

import importlib
from datetime import date, timedelta

import pytest

from finance_world import World, freeze


@pytest.fixture()
def world(client, user):
    return World(client, user)


@pytest.fixture()
def clock(app_module, monkeypatch):
    return freeze(monkeypatch, date(2026, 10, 20))


def balances(home):
    return {account["name"]: account["balance"] for account in home["accounts"]}


def month(home, key):
    return next(item for item in home["flow"] if item["month"] == key)


ZERO_SUMMARY = {
    "income": 0, "expense": 0, "result": 0, "invested": 0, "redeemed": 0,
    "investment_net": 0, "others_paid": 0, "others_received": 0, "others_net": 0,
}


# --- transactions.test.js --------------------------------------------------

def test_corretora_is_not_saldo_em_conta(world, clock):
    banco = world.account("Banco", initial=800)
    world.account("Poupança", "SAVINGS", initial=500)
    corretora = world.account("Corretora", "BROKERAGE", initial=5000)
    world.tx("INCOME", 200, "2026-10-05", banco, "Receita")
    world.tx("INCOME", 2000, "2026-10-05", corretora, "Receita")

    home = world.home(months=2)
    assert home["consolidated_balance"] == 1500
    # Setembro, antes de qualquer linha: o saldo inicial sem a Corretora.
    assert month(home, "2026-09")["balance"] == 1300
    assert {"Banco": 1000, "Poupança": 500, "Corretora": 7000}.items() <= balances(home).items()
    assert {account["type"] for account in home["accounts"]} >= {"CHECKING", "SAVINGS", "BROKERAGE"}


def test_rows_inside_the_corretora_stay_out(world, clock):
    banco = world.account("Banco", initial=100)
    corretora = world.account("Corretora", "BROKERAGE")
    world.insert_tx("EXPENSE", 900, "2026-10-07", corretora, source_type="INVESTMENT_TRANSACTION")
    world.insert_tx("INCOME", 40, "2026-10-08", corretora, source_type="INVESTMENT_TRANSACTION")
    world.tx("EXPENSE", 50, "2026-10-06", banco, "Alimentação", "Mercado")

    summary = world.home()["summary"]
    assert (summary["expense"], summary["income"], summary["invested"], summary["redeemed"]) == (50, 0, 0, 0)


def test_transfer_to_corretora_is_aporte_back_is_resgate(world, clock):
    banco = world.account("Banco", initial=1000)
    poupanca = world.account("Poupança", "SAVINGS", initial=0)
    corretora = world.account("Corretora", "BROKERAGE", initial=0)
    world.transfer(300, "2026-10-03", banco, corretora)
    world.transfer(100, "2026-10-04", corretora, poupanca)

    home = world.home()
    summary = home["summary"]
    assert (summary["invested"], summary["redeemed"], summary["expense"], summary["income"]) == (300, 100, 0, 0)
    assert summary["investment_net"] == 200
    assert balances(home)["Banco"] == 700 and balances(home)["Poupança"] == 100
    assert home["consolidated_balance"] == 800
    assert home["flow"][-1]["balance"] == 800


def test_bank_to_bank_and_brokerage_to_brokerage_are_not_flow(world, clock):
    banco = world.account("Banco", initial=100)
    poupanca = world.account("Poupança", "SAVINGS")
    corretora = world.account("Corretora", "BROKERAGE", initial=50)
    xp = world.account("XP", "BROKERAGE")
    world.transfer(10, "2026-10-03", banco, poupanca)
    world.transfer(10, "2026-10-03", corretora, xp)

    home = world.home()
    assert home["summary"] == ZERO_SUMMARY
    assert home["consolidated_balance"] == 100
    assert home["flow"][-1]["balance"] == 100


def test_without_corretora_an_expense_is_an_expense(world, clock):
    banco = world.account("Banco", initial=10)
    poupanca = world.account("Poupança", "SAVINGS", initial=5)
    world.tx("EXPENSE", 1, "2026-10-03", banco)

    home = world.home()
    assert home["summary"]["expense"] == 1
    assert home["consolidated_balance"] == sum(account["balance"] for account in home["accounts"]) == 14
    assert poupanca["id"] in {account["id"] for account in home["accounts"]}


def test_corretora_balance_is_not_in_home(world, clock):
    world.account("Banco", initial=250)
    world.account("Corretora", "BROKERAGE", initial=7000)
    home = world.home()
    assert home["consolidated_balance"] == 250
    assert home["flow"][-1]["balance"] == 250


def test_card_refund_subtracts_from_expense_in_its_month(world, clock):
    world.account("Banco")
    card = world.card()
    world.purchase(card, 100, "2026-10-05")
    world.refund(card, 30, "2026-10-12")
    world.refund(card, 5, "2026-09-12")

    home = world.home(months=2)
    assert month(home, "2026-10")["expense"] == 70
    assert month(home, "2026-09")["expense"] == -5


def test_investimento_category_is_an_ordinary_expense(world, clock):
    banco = world.account("Banco", initial=1000)
    corretora = world.account("Corretora", "BROKERAGE")
    world.call("post", "/api/categories", json={"name": "Investimento", "kind": "EXPENSE"})
    world.tx("EXPENSE", 20, "2026-10-02", banco, "Investimento")
    world.insert_tx("EXPENSE", 300, "2026-10-03", banco, source_type="INVESTMENT_TRANSACTION")
    world.insert_tx("INCOME", 45, "2026-10-04", banco, source_type="INVESTMENT_TRANSACTION")
    world.transfer(100, "2026-10-05", banco, corretora)

    summary = world.home()["summary"]
    assert summary["expense"] == 20
    assert summary["invested"] == 400
    assert summary["redeemed"] == 45
    assert summary["income"] == 0


def test_next_invoices_match_cc_invoices(world, clock):
    nubank = world.card("Nubank")
    late = world.card("Tarde", due_day=5, closing_day=25)
    world.purchase(nubank, 1000, "2026-10-10")
    world.purchase(nubank, 200, "2026-10-11")
    world.purchase(nubank, 50, "2026-11-04")
    world.purchase(late, 70.10, "2026-10-26")
    clock.set("2026-11-05")

    home = world.home()
    flagged = [
        (card["card_id"], item["invoice_month"], item["invoice_year"], item["total"])
        for card in world.invoices()["cards"] for item in card["invoices"] if item["next"]
    ]
    assert sorted(flagged) == sorted(
        (item["card_id"], item["invoice_month"], item["invoice_year"], item["total"]) for item in home["next_invoices"]
    )
    first = home["next_invoices"][0]
    assert (first["card_name"], first["invoice_month"], first["closed"], first["payable"], first["item_count"]) == (
        "Nubank", 11, True, True, 2,
    )
    assert home["next_invoices_total"] == 1270.10
    # A fatura de dezembro do "Tarde" fecha em 25/11; a de novembro do Nubank ja fechou.
    assert home["next_closing_date"] == "2026-11-25"


# --- cashFlow.js -------------------------------------------------------------

def test_income_and_expense_are_the_owners_part(world, clock):
    banco = world.account("Banco")
    world.tx("INCOME", 1000, "2026-10-05", banco, "Receita",
             share_mode="SPLIT", share_person="Ana", share_others_amount=400)
    world.tx("EXPENSE", 100, "2026-10-06", banco, "Lazer", share_mode="OTHERS", share_person="Bia")

    summary = world.home()["summary"]
    assert (summary["income"], summary["others_received"]) == (600, 400)
    assert (summary["expense"], summary["others_paid"]) == (0, 100)
    assert summary["others_net"] == 300


def test_card_purchase_counts_in_purchase_month_not_invoice(world, clock):
    card = world.card()
    world.purchase(card, 300, "2026-10-28")
    clock.set("2026-11-05")

    home = world.home(months=2)
    assert month(home, "2026-10")["expense"] == 300
    assert month(home, "2026-11")["expense"] == 0


def test_card_installments_count_in_full_in_purchase_month(world, clock):
    card = world.card()
    world.purchase(card, 300, "2026-10-12", installments=3)
    clock.set("2026-12-15")

    home = world.home(months=3)
    assert [item["expense"] for item in home["flow"]] == [300, 0, 0]


def test_paid_card_rows_still_count(world, clock):
    banco = world.account("Banco", initial=1000)
    card = world.card()
    world.purchase(card, 120, "2026-10-01")
    clock.set("2026-10-11")
    world.pay(card, 10, 2026, banco)

    home = world.home()
    assert home["summary"]["expense"] == 120
    assert home["consolidated_balance"] == 880


def test_card_share_split_proportionally(world, clock):
    card = world.card()
    rows = world.purchase(card, 300, "2026-10-12", installments=3)
    world.call("patch", f"/api/cc-expenses/{rows[0]['id']}/share",
               json={"share_mode": "SPLIT", "share_person": "Ana", "share_others_amount": 90})

    summary = world.home()["summary"]
    assert (summary["expense"], summary["others_paid"]) == (210, 90)


def test_invoice_payment_is_never_expense(world, clock):
    banco = world.account("Banco", initial=1000)
    world.insert_tx("EXPENSE", 100, "2026-10-03", banco, source_type="CC_INVOICE_PAYMENT")
    world.insert_tx("EXPENSE", 50, "2026-10-04", banco, source_type="CC_AUTOPAY")
    world.insert_tx("EXPENSE", 25, "2026-10-05", banco, category="Pagamento Fatura Nubank")
    # O prefixo e o do cliente (startsWith): com outra caixa e despesa.
    world.insert_tx("EXPENSE", 1, "2026-10-06", banco, category="pagamento fatura")

    home = world.home()
    assert home["summary"]["expense"] == 1
    assert home["consolidated_balance"] == 824
    assert home["flow"][-1]["balance"] == 824


def test_transfer_between_banks_is_not_flow(world, clock):
    banco = world.account("Banco", initial=500)
    poupanca = world.account("Poupança", "SAVINGS")
    world.transfer(200, "2026-10-03", banco, poupanca)

    home = world.home()
    assert home["summary"] == ZERO_SUMMARY
    assert home["flow"][-1]["net"] == 0
    assert balances(home)["Poupança"] == 200


def test_result_is_income_minus_expense(world, clock):
    banco = world.account("Banco", initial=5000)
    corretora = world.account("Corretora", "BROKERAGE")
    world.tx("INCOME", 3000, "2026-10-05", banco, "Receita")
    world.tx("EXPENSE", 800, "2026-10-06", banco, "Moradia")
    world.tx("EXPENSE", 90, "2026-10-07", banco, "Lazer", share_mode="OTHERS", share_person="Bia")
    world.transfer(1000, "2026-10-08", banco, corretora)

    summary = world.home()["summary"]
    assert summary["result"] == 2200
    assert summary["investment_net"] == 1000
    assert summary["others_net"] == -90


def test_net_includes_investment_and_others(world, clock):
    banco = world.account("Banco", initial=5000)
    corretora = world.account("Corretora", "BROKERAGE", initial=1000)
    world.tx("INCOME", 3000, "2026-10-05", banco, "Receita", share_mode="SPLIT", share_person="Ana", share_others_amount=100)
    world.tx("EXPENSE", 800, "2026-10-06", banco, "Moradia", share_mode="SPLIT", share_person="Ana", share_others_amount=300)
    world.transfer(1000, "2026-10-08", banco, corretora)
    world.transfer(250, "2026-10-09", corretora, banco)

    current = world.home()["flow"][-1]
    # 2900 - 500 - 1000 + 250 + 100 - 300
    assert current["net"] == 1450
    assert (current["income"], current["expense"], current["invested"], current["redeemed"]) == (2900, 500, 1000, 250)
    assert (current["others_received"], current["others_paid"]) == (100, 300)


def test_month_end_balance_ends_at_consolidated(world, clock):
    banco = world.account("Banco", initial=1234.56)
    velha = world.account("Velha", initial=100)
    corretora = world.account("Corretora", "BROKERAGE", initial=900)
    card = world.card()
    world.tx("EXPENSE", 40, "2026-02-10", velha)
    world.archive_account(velha)
    for index, key in enumerate(("2025-11", "2026-03", "2026-07", "2026-10")):
        world.tx("INCOME", 1000 + index, f"{key}-05", banco, "Receita")
        world.tx("EXPENSE", 333.33, f"{key}-06", banco, "Moradia")
    world.transfer(500, "2026-04-01", banco, corretora)
    world.purchase(card, 99.99, "2026-09-02")

    home = world.home(months=12)
    assert len(home["flow"]) == 12
    assert home["flow"][0]["month"] == "2025-11" and home["flow"][-1]["month"] == "2026-10"
    assert home["flow"][-1]["balance"] == home["consolidated_balance"]
    assert home["summary"]["income"] == home["flow"][-1]["income"]


def test_opening_includes_rows_before_the_window(world, clock):
    banco = world.account("Banco", initial=100)
    world.tx("EXPENSE", 30, "2025-09-15", banco)

    home = world.home(months=12)
    assert [item["balance"] for item in home["flow"]] == [70] * 12
    assert all(item["expense"] == 0 and item["income"] == 0 for item in home["flow"])


def test_archived_account_rows_still_count(world, clock):
    world.account("Banco", initial=10)
    velha = world.account("Velha", initial=100)
    world.tx("EXPENSE", 40, "2026-10-02", velha)
    world.archive_account(velha)

    home = world.home()
    assert home["summary"]["expense"] == 40
    assert home["consolidated_balance"] == 70
    archived = next(account for account in home["accounts"] if account["name"] == "Velha")
    assert archived["archived_at"]


def test_empty_month_is_zero_not_missing(world, clock):
    banco = world.account("Banco", initial=0)
    world.tx("EXPENSE", 10, "2026-09-03", banco)

    flow = world.home(months=3)["flow"]
    assert [item["month"] for item in flow] == ["2026-08", "2026-09", "2026-10"]
    empty = {"income": 0, "expense": 0, "invested": 0, "redeemed": 0, "others_paid": 0, "others_received": 0, "net": 0}
    assert {key: flow[0][key] for key in empty} == empty
    assert {key: flow[2][key] for key in empty} == empty
    assert flow[1]["expense"] == 10


def test_months_param_bounds(world, clock):
    for raw in ("0", "25", "abc", "-1"):
        world.call("get", "/api/home", expected=400, query_string={"months": raw})
    assert len(world.home()["flow"]) == 1
    assert len(world.home(months=24)["flow"]) == 24
    assert world.home()["month"] == "2026-10" and world.home()["today"] == "2026-10-20"


def test_cents_exact(world, clock):
    banco = world.account("Banco", initial=0)
    for amount in (0.10, 0.20, 0.30):
        world.tx("EXPENSE", amount, "2026-10-03", banco)
    assert world.home()["summary"]["expense"] == 0.60

    other = world.account("Outra", initial=0)
    for _ in range(3):
        world.tx("EXPENSE", 33.33, "2026-10-04", other)
    world.tx("EXPENSE", 0.01, "2026-10-04", other)
    home = world.home()
    assert home["summary"]["expense"] == 100.60
    assert home["consolidated_balance"] == -100.60


def test_autopay_debited_today_is_in_home(world, clock):
    banco = world.account("Banco", initial=1000)
    clock.set("2026-09-01")
    card = world.card(autopay_account_id=banco["id"])
    world.purchase(card, 100, "2026-09-10")
    clock.set("2026-10-10")

    home = world.home()
    assert home["consolidated_balance"] == 900
    assert home["summary"]["expense"] == 0
    assert balances(home)["Banco"] == 900


def test_paid_provento_in_bank_account_is_redeemed(world, client, monkeypatch, app_module):
    prices = importlib.import_module("services.prices")
    monkeypatch.setattr(prices, "download_close_prices", lambda symbols, **kwargs: {})
    today = date.today() + timedelta(days=1)
    clock = freeze(monkeypatch, today)
    corretora = world.account("Carteira", "BROKERAGE")
    bought = world.call("post", "/api/investments", json={
        "asset_class": "STOCKS", "ticker_or_name": "PETR4", "quantity": 100,
        "average_price": 10.0, "current_price": 10.0,
        "metadata": {"purchase_date": (today - timedelta(days=800)).isoformat(), "cash_account_id": None},
    }).get_json()
    world.call("post", "/api/investment-proceeds", json={
        "asset_id": bought[0]["asset_id"], "proceeds_type": "DIVIDEND",
        "record_date": (today - timedelta(days=700)).isoformat(),
        "payment_date": today.isoformat(), "gross_amount": 50.0,
    })
    # A leitura grava o provento na Corretora; ali ele nao e da area bancaria.
    assert world.home()["summary"]["redeemed"] == 0
    # A linha fica na conta em que nasceu: com ela fora da carteira, e resgate.
    world.call("patch", f"/api/accounts/{corretora['id']}", json={"type": "CHECKING"})
    summary = world.home()["summary"]
    assert (summary["redeemed"], summary["income"]) == (50, 0)
    assert clock.value == today


def test_investido_matches_monthly_plan(world, clock):
    banco = world.account("Banco", initial=5000)
    poupanca = world.account("Poupança", "SAVINGS")
    corretora = world.account("Corretora", "BROKERAGE")
    world.transfer(1000, "2026-10-03", banco, corretora)
    world.transfer(300, "2026-10-04", corretora, poupanca)
    world.insert_tx("EXPENSE", 200, "2026-10-05", banco, source_type="INVESTMENT_TRANSACTION")
    world.insert_tx("INCOME", 70, "2026-10-06", banco, source_type="INVESTMENT_TRANSACTION")
    world.insert_tx("EXPENSE", 999, "2026-10-07", corretora, source_type="INVESTMENT_TRANSACTION")

    summary = world.home()["summary"]
    plan = world.get("/api/monthly-plan", query_string={"month": "2026-10"})
    assert summary["investment_net"] == plan["actual"]["invested"] == 830
    assert (summary["invested"], summary["redeemed"]) == (plan["actual"]["aportes"], plan["actual"]["resgates"])


def test_user_isolation(client, world, other_user, clock):
    banco = world.account("Banco", initial=10)
    world.tx("EXPENSE", 5, "2026-10-03", banco)
    other = World(client, other_user)
    home = other.home()
    assert "Banco" not in balances(home)
    assert home["summary"]["expense"] == 0
    assert home["consolidated_balance"] == 0
