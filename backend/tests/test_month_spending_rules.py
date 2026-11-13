"""O que conta como gasto e como receita do mes, nas tres telas que somam.

Inicio (`GET /api/home`, services/home.py), o plano do mes
(`GET /api/monthly-plan`, services/monthly_plan.py) e o orcamento
(`GET /api/budgets`, services/budgets.py) somam o mes cada um com a sua
consulta. As condicoes de cada linha moram em services/spending_rules.py; este
arquivo fixa, linha a linha, o que cada tela conta. As tres somam igual
(decisoes do dono de 2026-11-13, antes divergencias):

1. despesa/receita digitada numa conta Corretora: nenhuma tela conta (o plano e
   o orcamento seguem o Inicio);
2. categoria que comeca com "pagamento fatura", em qualquer caixa: e pagamento
   de fatura em todas;
3. o pagamento de fatura fica fora das despesas e das receitas em todas.
"""

from datetime import date

import pytest

from finance_world import World, freeze

MONTH = "2026-10"
DAY = "2026-10-05"


@pytest.fixture()
def world(client, user, app_module, monkeypatch):
    freeze(monkeypatch, date(2026, 10, 20))
    return World(client, user)


def figures(world):
    home = world.home()["summary"]
    plan = world.get(f"/api/monthly-plan?month={MONTH}")
    budgets = world.get(f"/api/budgets?month={MONTH}")
    return {
        "home_expense": home["expense"], "home_income": home["income"],
        "plan_spent": plan["spend"]["realized"], "plan_income": plan["income"]["received"],
        "budget_spent": budgets["totals"]["plan_spent"],
    }


@pytest.fixture()
def base(world):
    """Um plano e uma conta; devolve (conta, figuras antes)."""
    bank = world.account("Banco", initial=10000)
    world.call("put", "/api/monthly-plan", json={
        "month": MONTH, "income_amount": 5000, "invest_percent": 20, "spend_percent": 80,
    })
    return bank


def delta(world, before):
    after = figures(world)
    return {key: round(after[key] - before[key], 2) for key in after}


ALL = {"home_expense", "plan_spent", "budget_spent"}


def spent(amount, screens=ALL, income=()):
    result = {key: 0.0 for key in ("home_expense", "home_income", "plan_spent", "plan_income", "budget_spent")}
    for key in screens:
        result[key] = float(amount)
    for key in income:
        result[key] = float(amount)
    return result


class TestWhatEveryScreenAgreesOn:
    def test_a_plain_expense_counts_everywhere(self, world, base):
        before = figures(world)
        world.tx("EXPENSE", 100, DAY, base)
        assert delta(world, before) == spent(100)

    def test_a_plain_income_is_income(self, world, base):
        before = figures(world)
        world.tx("INCOME", 5000, DAY, base, category="Salário")
        assert delta(world, before) == spent(5000, screens=(), income=("home_income", "plan_income"))

    def test_a_split_expense_counts_the_owners_part(self, world, base):
        before = figures(world)
        world.tx("EXPENSE", 60, DAY, base, share_mode="SPLIT", share_others_amount=20, share_person="Ana")
        assert delta(world, before) == spent(40)

    def test_an_expense_of_someone_else_counts_nothing(self, world, base):
        before = figures(world)
        world.tx("EXPENSE", 30, DAY, base, share_mode="OTHERS", share_person="Ana")
        assert delta(world, before) == spent(0)

    def test_a_card_purchase_counts_whole_in_the_purchase_month_and_a_refund_subtracts(self, world, base):
        before = figures(world)
        card = world.card()
        world.purchase(card, 300, DAY, installments=3)
        world.refund(card, 50, DAY)
        assert delta(world, before) == spent(250)

    def test_an_invoice_payment_never_counts(self, world, base, monkeypatch):
        card = world.card()
        world.purchase(card, 200, "2026-09-10")
        before = figures(world)
        line = world.get("/api/cc-expenses")[0]
        world.pay(card, line["invoice_month"], line["invoice_year"], base)
        assert delta(world, before) == spent(0)

    def test_a_legacy_invoice_payment_by_category_name_never_counts(self, world, base):
        before = figures(world)
        world.insert_tx("EXPENSE", 10, DAY, base, category="Pagamento Fatura Nubank")
        assert delta(world, before) == spent(0)

    def test_transfers_never_count(self, world, base):
        other = world.account("Poupança")
        broker = world.account("XP", type_="BROKERAGE")
        before = figures(world)
        world.transfer(500, DAY, base, other)
        world.transfer(300, DAY, base, broker)
        assert delta(world, before) == spent(0)

    @pytest.mark.parametrize("source_type", [
        "MONTH_SUMMARY", "INVESTMENT_TRANSACTION", "INVESTMENT_PROCEED", "BROKER_STATEMENT", "BANK_INVESTMENT",
    ])
    def test_rows_that_are_not_spending_by_origin(self, world, base, source_type):
        before = figures(world)
        world.insert_tx("EXPENSE", 70, DAY, base, source_type=source_type)
        world.insert_tx("INCOME", 90, DAY, base, source_type=source_type)
        assert delta(world, before) == spent(0)

    def test_the_conta_global_is_outside_every_reais_total(self, world, base):
        wise = world.account("Wise", currency="USD")
        before = figures(world)
        world.insert_tx("EXPENSE", 25, DAY, wise)
        world.insert_tx("INCOME", 80, DAY, wise)
        assert delta(world, before) == spent(0)


class TestWhereTheScreensUsedToDisagree:
    """Decisoes do dono de 2026-11-13: as tres telas somam igual."""

    def test_an_expense_typed_in_the_corretora_counts_nowhere(self, world, base):
        broker = world.account("XP", type_="BROKERAGE", initial=1000)
        before = figures(world)
        world.tx("EXPENSE", 40, DAY, broker)
        assert delta(world, before) == spent(0)

    def test_an_income_typed_in_the_corretora_counts_nowhere(self, world, base):
        broker = world.account("XP", type_="BROKERAGE", initial=1000)
        before = figures(world)
        world.tx("INCOME", 15, DAY, broker, category="Salário")
        assert delta(world, before) == spent(0)

    @pytest.mark.parametrize("category", [
        "pagamento fatura antiga", "PAGAMENTO FATURA NUBANK", "Pagamento fatura Black",
    ])
    def test_the_pagamento_fatura_category_in_any_case_is_no_expense(self, world, base, category):
        before = figures(world)
        world.insert_tx("EXPENSE", 7, DAY, base, category=category)
        assert delta(world, before) == spent(0)

    @pytest.mark.parametrize("category", ["Pagamento Fatura devolvida", "pagamento fatura devolvida"])
    def test_an_income_named_pagamento_fatura_is_no_income(self, world, base, category):
        before = figures(world)
        world.insert_tx("INCOME", 3, DAY, base, category=category)
        assert delta(world, before) == spent(0)

    def test_an_income_with_an_invoice_payment_origin_is_no_income(self, world, base):
        before = figures(world)
        world.insert_tx("INCOME", 9, DAY, base, source_type="CC_INVOICE_PAYMENT")
        assert delta(world, before) == spent(0)

    def test_a_category_that_only_contains_the_words_still_counts(self, world, base):
        before = figures(world)
        world.insert_tx("EXPENSE", 12, DAY, base, category="Taxa de pagamento fatura")
        assert delta(world, before) == spent(12)


class TestThePanelsFollowTheSummary:
    """`GET /api/home/panels` soma o gasto com a mesma regra do resumo."""

    def total(self, world):
        return world.get("/api/home/panels")["spending_total"]

    def test_a_lowercase_pagamento_fatura_is_out_of_the_panels(self, world, base):
        world.tx("EXPENSE", 100, DAY, base)
        before = self.total(world)
        world.insert_tx("EXPENSE", 7, DAY, base, category="pagamento fatura antiga")
        assert self.total(world) == before

    def test_an_expense_in_the_corretora_is_out_of_the_panels(self, world, base):
        broker = world.account("XP", type_="BROKERAGE", initial=1000)
        world.tx("EXPENSE", 100, DAY, base)
        before = self.total(world)
        world.tx("EXPENSE", 40, DAY, broker)
        assert self.total(world) == before
