"""GET /api/cc-invoices: as faturas em aberto por cartao, somadas no servidor.

Carrega os casos de `attentionRules.test.js` sobre a proxima fatura, a vencida
e a mais proxima (nextInvoices, nearestOpenInvoice), e o agrupamento que a tela
Cartoes fazia (`openInvoicesByCard`): total com sinal (estorno abate), Pagar so
em fatura fechada e sem credito, as futuras dobradas e uma entrada por linha.

Cartao padrao: fecha dia 3, vence dia 10 — uma compra em 10/10 cai na fatura
11/2026, que fecha em 03/11 e vence em 10/11.
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


def invoice(data, card, year, month):
    entry = next(item for item in data["cards"] if item["card_id"] == card["id"])
    return next(item for item in entry["invoices"] if (item["invoice_year"], item["invoice_month"]) == (year, month))


def flagged(data, flag):
    return [
        (card["card_name"], item["invoice_year"], item["invoice_month"], item["total"])
        for card in data["cards"] for item in card["invoices"] if item[flag]
    ]


def test_refund_subtracts_purchase_adds(world, clock):
    card = world.card()
    world.purchase(card, 120.50, "2026-10-10")
    world.refund(card, 40, "2026-10-12")
    other = world.card("Outro")
    world.refund(other, 40, "2026-09-12")
    clock.set("2026-10-05")

    data = world.invoices()
    assert invoice(data, card, 2026, 11)["total"] == 80.50
    credit = invoice(data, other, 2026, 10)
    assert credit["total"] == -40
    assert credit["closed"] is True and credit["payable"] is False
    assert data["open_total"] == 40.50


def test_credit_invoice_is_past_due_not_payable(world, clock):
    card = world.card()
    world.refund(card, 50, "2026-09-12")
    clock.set("2026-10-15")

    data = world.invoices()
    item = invoice(data, card, 2026, 10)
    assert item["past_due"] is True
    assert item["payable"] is False
    # A vencida que conta para "a mais proxima" e so a que cobra algo.
    assert item["nearest"] is False
    assert data["nearest"] is None


def test_two_identical_rides_are_two_purchases(world, clock):
    card = world.card()
    world.purchase(card, 10, "2026-10-10", "Uber")
    world.purchase(card, 10, "2026-10-10", "Uber")

    item = invoice(world.invoices(), card, 2026, 11)
    assert item["total"] == 20
    assert item["item_count"] == 2
    assert len(item["purchases"]) == 2
    assert len({purchase["client_id"] for purchase in item["purchases"]}) == 2


def test_installments_share_the_purchase(world, clock):
    card = world.card()
    world.purchase(card, 100, "2026-10-10", "Geladeira", installments=3)

    data = world.invoices()
    amounts = [invoice(data, card, 2026, month)["purchases"][0] for month in (11, 12)]
    amounts.append(invoice(data, card, 2027, 1)["purchases"][0])
    assert [item["amount"] for item in amounts] == [33.34, 33.33, 33.33]
    assert {item["installments_open"] for item in amounts} == {3}
    assert {item["installments_paid"] for item in amounts} == {0}
    assert [item["installment_info"] for item in amounts] == ["1/3", "2/3", "3/3"]
    assert amounts[1]["installment_current"] == 2 and amounts[1]["installment_total"] == 3


def test_installment_counts(world, clock):
    bank = world.account("Banco", initial=1000)
    card = world.card()
    world.purchase(card, 300, "2026-10-10", "TV", installments=3)
    clock.set("2026-11-05")
    world.pay(card, 11, 2026, bank)

    entry = invoice(world.invoices(), card, 2026, 12)["purchases"][0]
    assert entry["installments_open"] == 2
    assert entry["installments_paid"] == 1


def test_next_closes_before_due_is_this_months(world, clock):
    card = world.card()
    world.purchase(card, 1000, "2026-10-10")
    world.purchase(card, 200, "2026-10-11")
    world.purchase(card, 50, "2026-11-04")
    clock.set("2026-11-05")

    data = world.invoices()
    november = invoice(data, card, 2026, 11)
    assert november["next"] is True
    assert november["total"] == 1200
    assert november["closed"] is True and november["payable"] is True
    assert november["item_count"] == 2
    assert november["closing_date"] == "2026-11-03" and november["due_date"] == "2026-11-10"
    assert invoice(data, card, 2026, 12)["next"] is False


def test_due_day_is_not_past_due(world, clock):
    card = world.card()
    world.purchase(card, 100, "2026-10-10")
    world.purchase(card, 40, "2026-11-04")

    clock.set("2026-11-10")
    data = world.invoices()
    assert invoice(data, card, 2026, 11)["next"] is True
    assert invoice(data, card, 2026, 11)["past_due"] is False

    clock.set("2026-11-11")
    data = world.invoices()
    november = invoice(data, card, 2026, 11)
    assert invoice(data, card, 2026, 12)["next"] is True
    assert november["past_due"] is True and november["nearest"] is True
    assert data["nearest"] == {"card_id": card["id"], "invoice_month": 11, "invoice_year": 2026}


def test_next_closes_after_due_is_next_months(world, clock):
    card = world.card("Tarde", due_day=5, closing_day=25)
    world.purchase(card, 300, "2026-11-10")
    clock.set("2026-11-26")

    december = invoice(world.invoices(), card, 2026, 12)
    assert december["next"] is True
    assert december["total"] == 300
    assert december["closed"] is True
    assert december["closing_date"] == "2026-11-25"


def test_one_next_per_card_by_due_date_paid_ignored(world, clock):
    bank = world.account("Banco", initial=5000)
    nubank = world.card("Nubank")
    late = world.card("Tarde", due_day=5, closing_day=25)
    world.purchase(nubank, 100, "2026-10-10")
    clock.set("2026-11-05")
    world.pay(nubank, 11, 2026, bank)
    world.purchase(nubank, 80, "2026-11-05")
    world.purchase(late, 300, "2026-11-10")
    clock.set("2026-11-12")

    assert flagged(world.invoices(), "next") == [("Nubank", 2026, 12, 80), ("Tarde", 2026, 12, 300)]
    home = world.home()
    assert [(item["card_name"], item["invoice_month"], item["total"]) for item in home["next_invoices"]] == [
        ("Tarde", 12, 300), ("Nubank", 12, 80),
    ]


def test_nearest_overdue_first_else_first_next(world, clock):
    assert world.invoices() == {"today": "2026-10-20", "nearest": None, "open_total": 0, "cards": []}

    card = world.card()
    late = world.card("Tarde", due_day=5, closing_day=25)
    world.purchase(card, 100, "2026-10-10")
    world.purchase(late, 70, "2026-11-10")
    clock.set("2026-11-05")
    assert world.invoices()["nearest"] == {"card_id": card["id"], "invoice_month": 11, "invoice_year": 2026}

    clock.set("2026-11-20")
    data = world.invoices()
    assert data["nearest"] == {"card_id": card["id"], "invoice_month": 11, "invoice_year": 2026}
    assert flagged(data, "nearest") == [("Nubank", 2026, 11, 100)]


def test_future_is_after_first_not_closed(world, clock):
    card = world.card()
    world.purchase(card, 90, "2026-09-10")
    world.purchase(card, 300, "2026-10-10", installments=3)
    clock.set("2026-11-05")

    data = world.invoices()
    flags = [(item["key"], item["closed"], item["future"]) for item in data["cards"][0]["invoices"]]
    assert flags == [
        ("2026-10", True, False),
        ("2026-11", True, False),
        ("2026-12", False, False),
        ("2027-01", False, True),
    ]


def test_sorted_by_card_name_then_month_then_description(world, clock):
    zeta = world.card("Zeta")
    alamo = world.card("álamo")
    beta = world.card("Beta")
    for card in (zeta, alamo, beta):
        world.purchase(card, 10, "2026-11-04", "uber")
        world.purchase(card, 10, "2026-11-04", "Água")
        world.purchase(card, 10, "2026-11-04", "Bar")
        world.purchase(card, 10, "2026-10-10", "Antes")

    data = world.invoices()
    assert [card["card_name"] for card in data["cards"]] == ["álamo", "Beta", "Zeta"]
    first = data["cards"][0]
    assert [item["key"] for item in first["invoices"]] == ["2026-11", "2026-12"]
    assert [item["description"] for item in first["invoices"][1]["purchases"]] == ["Água", "Bar", "uber"]
    assert first["total"] == 40 and data["open_total"] == 120


def test_card_fields_and_only_open_rows(world, clock):
    bank = world.account("Banco", initial=1000)
    clock.set("2026-09-01")  # o debito automatico vale das faturas que vencem dai em diante
    card = world.card(autopay_account_id=bank["id"])
    world.purchase(card, 100, "2026-09-10")
    world.purchase(card, 25, "2026-10-10")
    clock.set("2026-10-11")  # o debito automatico paga a de outubro na leitura

    data = world.invoices()
    entry = data["cards"][0]
    assert {key: entry[key] for key in ("card_name", "due_day", "closing_day", "autopay_account_id", "credit_enabled")} == {
        "card_name": "Nubank", "due_day": 10, "closing_day": 3,
        "autopay_account_id": bank["id"], "credit_enabled": True,
    }
    assert [item["key"] for item in entry["invoices"]] == ["2026-11"]
    assert entry["total"] == 25


def test_user_isolation(client, world, other_user, clock):
    card = world.card()
    world.purchase(card, 100, "2026-10-10")
    other = World(client, other_user)
    assert other.invoices()["cards"] == []
    assert other.home()["next_invoices"] == []
