"""GET /api/home/panels: os quatro paineis de historico do Inicio no servidor.

Cobre o que `pages/Dashboard.jsx` montava no cliente (buildSpending, o ritmo,
a projecao das faturas e os parcelamentos), para o Inicio nativo. O dia
congelado e 2026-10-20; o cartao de `World.card()` fecha dia 3 e vence dia 10,
entao uma compra de outubro depois do dia 3 cai na fatura de novembro.
"""

from datetime import date

import pytest

from finance_world import World, freeze


@pytest.fixture()
def world(client, user):
    return World(client, user)


@pytest.fixture()
def clock(app_module, monkeypatch):
    return freeze(monkeypatch, date(2026, 10, 20))


def categories(panels):
    return {item["name"]: item for item in panels["categories"]}


# --- Despesas por categoria ---------------------------------------------------

def test_bank_expense_and_card_purchase_in_full_in_the_purchase_month(world, clock):
    banco = world.account("Banco", initial=1000)
    card = world.card()
    world.tx("EXPENSE", 40, "2026-10-02", banco, "Alimentação")
    world.purchase(card, 300, "2026-10-12", installments=3)

    item = categories(world.panels())["Alimentação"]
    assert (item["value"], item["cash"], item["credit"]) == (340, 40, 300)
    assert world.panels()["spending_total"] == 340


def test_invoice_payment_transfer_income_and_corretora_are_not_spending(world, clock):
    banco = world.account("Banco", initial=1000)
    outro = world.account("Outro banco")
    corretora = world.account("Corretora", "BROKERAGE", initial=1000)
    world.insert_tx("EXPENSE", 100, "2026-10-03", banco, source_type="CC_INVOICE_PAYMENT")
    world.insert_tx("EXPENSE", 70, "2026-10-04", banco, category="Pagamento Fatura Nubank")
    world.insert_tx("EXPENSE", 50, "2026-10-05", banco, source_type="INVESTMENT_TRANSACTION")
    world.tx("EXPENSE", 20, "2026-10-06", corretora, "Outros")
    world.transfer(30, "2026-10-07", banco, outro)
    world.transfer(30, "2026-10-07", banco, corretora)
    world.tx("INCOME", 500, "2026-10-08", banco, "Receita")
    world.tx("EXPENSE", 9.99, "2026-10-09", banco, "Outros")

    panels = world.panels()
    assert panels["categories"] == [
        {"name": "Outros", "value": 9.99, "cash": 9.99, "credit": 0, "delta": None},
    ]


def test_only_the_owners_part_and_refunds_subtract(world, clock):
    banco = world.account("Banco")
    card = world.card()
    world.tx("EXPENSE", 100, "2026-10-02", banco, "Lazer", share_mode="SPLIT",
             share_person="Ana", share_others_amount=40)
    world.tx("EXPENSE", 80, "2026-10-02", banco, "Lazer", share_mode="OTHERS", share_person="Ana")
    world.purchase(card, 200, "2026-10-05", category="Lazer")
    world.refund(card, 50, "2026-10-15")

    by_name = categories(world.panels())
    assert by_name["Lazer"]["value"] == 260
    # O estorno entra pela categoria dele ("Outros" quando vem sem): negativo, fica fora da lista.
    assert all(item["value"] > 0 for item in by_name.values())


def test_delta_against_the_whole_previous_month_and_sorted_by_value(world, clock):
    banco = world.account("Banco")
    world.tx("EXPENSE", 100, "2026-09-25", banco, "Alimentação")
    world.tx("EXPENSE", 150, "2026-10-01", banco, "Alimentação")
    world.tx("EXPENSE", 300, "2026-10-01", banco, "Moradia")

    panels = world.panels()
    assert [item["name"] for item in panels["categories"]] == ["Moradia", "Alimentação"]
    by_name = categories(panels)
    assert by_name["Alimentação"]["delta"] == 50.0
    assert by_name["Moradia"]["delta"] is None


# --- Ritmo de gastos ----------------------------------------------------------

def test_pace_against_the_average_of_months_with_spending(world, clock):
    banco = world.account("Banco")
    world.tx("EXPENSE", 100, "2026-10-05", banco)
    world.tx("EXPENSE", 999, "2026-10-25", banco)  # depois de hoje: nao entra no acumulado
    world.tx("EXPENSE", 60, "2026-09-10", banco)
    world.tx("EXPENSE", 40, "2026-09-28", banco)
    world.tx("EXPENSE", 20, "2026-07-01", banco)
    # Agosto sem nenhum gasto: fora da media.

    pace = world.panels()["pace"]
    assert pace["today_day"] == 20
    assert pace["days_in_month"] == 31
    assert len(pace["rows"]) == 31
    assert pace["current_to_date"] == 100
    # Ate o dia 20: setembro 60, julho 20 -> media 40.
    assert pace["average_to_date"] == 40
    assert pace["average_month"] == 60
    assert pace["vs_average"] == 150.0
    assert pace["months"] == [{"month": "2026-09", "to_date": 60}, {"month": "2026-07", "to_date": 20}]
    rows = {row["day"]: row for row in pace["rows"]}
    assert rows[4] == {"day": 4, "current": 0, "average": 10}
    assert rows[20]["current"] == 100
    assert rows[21]["current"] is None
    assert rows[31]["average"] == 60


def test_pace_without_history_has_no_average(world, clock):
    banco = world.account("Banco")
    world.tx("EXPENSE", 10, "2026-10-01", banco)

    pace = world.panels()["pace"]
    assert pace["months"] == []
    assert pace["vs_average"] is None
    assert all(row["average"] is None for row in pace["rows"])


def test_average_keeps_fractions_of_a_cent_until_rounding(world, clock):
    banco = world.account("Banco")
    world.tx("EXPENSE", 0.01, "2026-09-01", banco)
    world.tx("EXPENSE", 0.01, "2026-08-01", banco)
    world.tx("EXPENSE", 0.02, "2026-07-01", banco)

    pace = world.panels()["pace"]
    # 4 centavos / 3 meses = 1,33 centavo -> R$ 0,01.
    assert pace["average_to_date"] == 0.01
    assert pace["average_month"] == 0.01


# --- Proximas faturas ---------------------------------------------------------

def test_projection_six_months_from_the_next_invoice_without_the_overdue(world, clock):
    card = world.card()
    world.purchase(card, 300, "2026-10-12", installments=3)
    world.purchase(card, 50, "2026-09-01")  # fatura de setembro, venceu 10/09: fica fora

    panels = world.panels()
    assert [item["month"] for item in panels["invoice_projection"]] == [
        "2026-11", "2026-12", "2027-01", "2027-02", "2027-03", "2027-04",
    ]
    assert [item["value"] for item in panels["invoice_projection"]] == [100, 100, 100, 0, 0, 0]
    assert [item["next"] for item in panels["invoice_projection"]] == [True, False, False, False, False, False]
    assert panels["next_invoice_months"] == ["2026-11"]
    assert [(item["description"], item["installment_info"], item["amount"]) for item in panels["next_invoice_items"]] == [
        ("Loja", "1/3", 100),
    ]


def test_projection_without_cards_starts_this_month(world, clock):
    panels = world.panels()
    assert panels["invoice_projection"][0] == {"month": "2026-10", "value": 0, "next": False}
    assert panels["next_invoice_items"] == []
    assert panels["installments"] == []
    assert panels["installments_total"] == 0


def test_a_refund_lowers_the_projection(world, clock):
    card = world.card()
    world.purchase(card, 100, "2026-10-12")
    world.refund(card, 30, "2026-10-15")

    assert world.panels()["invoice_projection"][0]["value"] == 70


# --- Parcelamentos abertos ----------------------------------------------------

def test_installments_grouped_by_purchase_with_paid_and_remaining(world, clock):
    banco = world.account("Banco", initial=5000)
    card = world.card()
    world.purchase(card, 300, "2026-09-01", description="TV", installments=3)  # 1/3 em setembro
    world.purchase(card, 300, "2026-10-12", description="Sofá", installments=3)
    world.purchase(card, 300, "2026-10-12", description="Sofá", installments=3)  # outra compra igual
    world.purchase(card, 80, "2026-10-12", description="Mercado")
    world.pay(card, 9, 2026, banco)

    panels = world.panels()
    rows = [(item["description"], item["remaining"], item["paid"], item["total_installments"], item["remaining_amount"])
            for item in panels["installments"]]
    assert rows == [
        ("TV", 2, 1, 3, 200),
        ("Sofá", 3, 0, 3, 300),
        ("Sofá", 3, 0, 3, 300),
    ]
    assert panels["installments"][0]["next_invoice_month"] == 10
    assert panels["installments"][0]["card_name"] == "Nubank"
    assert panels["installments_total"] == 800


def test_user_isolation(client, world, other_user, clock):
    banco = world.account("Banco")
    world.tx("EXPENSE", 10, "2026-10-01", banco)
    world.purchase(world.card(), 300, "2026-10-12", installments=3)

    other = World(client, other_user)
    panels = other.panels()
    assert panels["categories"] == []
    assert panels["installments"] == []
    assert all(item["value"] == 0 for item in panels["invoice_projection"])


def test_requires_login(client):
    assert client.get("/api/home/panels").status_code == 401
