"""GET /api/attention: "Precisa de atencao", os avisos do Inicio e do sino.

Carrega os casos de `attentionRules.test.js` (fatura vencida, fechada,
debito automatico sem saldo, recorrencias, orcamento, estorno) e fixa as
chaves byte a byte como o cliente as escrevia: os avisos dispensados em cada
aparelho dependem delas. `undismissedItems` e `addDismissed` ficam no cliente.

Cartao padrao: fecha dia 3, vence dia 10.
"""

from datetime import date, timedelta

import pytest

from finance_world import World, freeze


@pytest.fixture()
def world(client, user):
    return World(client, user)


@pytest.fixture()
def clock(app_module, monkeypatch):
    return freeze(monkeypatch, date(2026, 10, 18))


def kinds(items):
    return [item["kind"] for item in items]


def by_kind(items, kind):
    return [item for item in items if item["kind"] == kind]


def test_overdue_is_past_due_summed_per_invoice(world, clock):
    card = world.card("Nubank")
    world.purchase(card, 100, "2026-09-10")
    world.purchase(card, 50, "2026-09-12")
    world.purchase(card, 70, "2026-10-10")

    items = world.attention()
    [overdue] = by_kind(items, "INVOICE_OVERDUE")
    assert overdue["total"] == 150 and overdue["item_count"] == 2
    assert overdue["tone"] == "danger"
    assert overdue["invoices"] == [{
        "card_id": card["id"], "card_name": "Nubank", "invoice_month": 10, "invoice_year": 2026,
        "due_date": "2026-10-10", "total": 150, "count": 2,
    }]
    assert overdue["key"] == f"fatura-vencida:{card['id']}|2026-10"


def test_overdue_key_month_is_not_zero_padded(world, clock):
    card = world.card()
    world.purchase(card, 10, "2026-08-10")
    [overdue] = by_kind(world.attention(), "INVOICE_OVERDUE")
    assert overdue["key"] == f"fatura-vencida:{card['id']}|2026-9"


def test_overdue_starts_the_day_after_due(world, clock):
    card = world.card()
    world.purchase(card, 10, "2026-09-10")
    clock.set("2026-10-10")
    assert by_kind(world.attention(), "INVOICE_OVERDUE") == []
    clock.set("2026-10-11")
    assert len(by_kind(world.attention(), "INVOICE_OVERDUE")) == 1


def test_payable_one_per_card_only_closed(world, clock):
    first = world.card("Um")
    second = world.card("Dois", due_day=10, closing_day=8)
    world.purchase(first, 100, "2026-10-10")
    world.purchase(first, 20, "2026-10-11")
    world.purchase(second, 40, "2026-10-10")
    clock.set("2026-11-05")  # a do Um fechou em 03/11; a do Dois fecha em 08/11

    [payable] = by_kind(world.attention(), "INVOICE_PAYABLE")
    assert payable["invoices"] == [{"card_id": first["id"], "invoice_month": 11, "invoice_year": 2026, "total": 120}]
    assert payable["total"] == 120 and payable["tone"] == "warning"
    assert payable["key"] == f"fatura-fechada:{first['id']}|2026-11"


def test_payable_hidden_while_an_invoice_is_overdue(world, clock):
    banco = world.account("Banco", initial=1000)
    card = world.card()
    other = world.card("Outro")
    world.purchase(other, 30, "2026-09-10")  # 10/2026, vencida em 05/11
    world.purchase(card, 100, "2026-10-10")  # 11/2026, fechada em 05/11
    clock.set("2026-11-05")
    assert kinds(world.attention()) == ["INVOICE_OVERDUE"]

    world.pay(other, 10, 2026, banco)
    assert kinds(world.attention()) == ["INVOICE_PAYABLE"]


def test_autopay_shortfall_in_the_next_31_days(world, clock):
    itau = world.account("Itaú", initial=80)
    clock.set("2026-09-01")
    card = world.card("Débito", due_day=25, closing_day=18, autopay_account_id=itau["id"])
    world.purchase(card, 100, "2026-10-01")   # 10/2026, vence 25/10
    world.purchase(card, 300, "2026-11-20")   # 12/2026, vence 25/12: fora da janela
    clock.set("2026-10-18")

    [shortfall] = by_kind(world.attention(), "AUTOPAY_SHORTFALL")
    assert shortfall == {
        "key": f"debito-sem-saldo:{itau['id']}:2026-10-25",
        "kind": "AUTOPAY_SHORTFALL", "tone": "danger",
        "account_id": itau["id"], "account_name": "Itaú",
        "total": 100, "first_due": "2026-10-25", "balance": 80, "missing": 20,
    }


def test_shortfall_window_is_inclusive(world, clock):
    itau = world.account("Itaú", initial=0)
    clock.set("2026-08-01")
    card = world.card(due_day=18, closing_day=11, autopay_account_id=itau["id"])
    world.purchase(card, 10, "2026-10-12")    # 11/2026, vence 18/11
    clock.set("2026-10-18")                   # 18/11 = hoje + 31
    assert len(by_kind(world.attention(), "AUTOPAY_SHORTFALL")) == 1
    clock.set("2026-10-17")                   # 18/11 = hoje + 32
    assert by_kind(world.attention(), "AUTOPAY_SHORTFALL") == []


def test_shortfall_skips_archived_corretora_and_no_rate_accounts(world, clock):
    banco = world.account("Banco", initial=0)
    archived = world.account("Arquivada", initial=0)
    corretora = world.account("Corretora", "BROKERAGE", initial=0)
    dollar = world.account("Dólar", initial=0)
    clock.set("2026-09-01")
    for name, account in (("A", archived), ("C", corretora), ("D", dollar)):
        card = world.card(name, autopay_account_id=banco["id"])
        world.set_rows("UPDATE credit_cards SET autopay_account_id = ? WHERE id = ?", (account["id"], card["id"]))
        world.purchase(card, 10, "2026-10-12")
    clock.set("2026-10-18")
    # A Corretora nao tem saldo no Inicio: nunca entra.
    assert {item["account_id"] for item in by_kind(world.attention(), "AUTOPAY_SHORTFALL")} == {archived["id"], dollar["id"]}

    world.archive_account(archived)
    assert [item["account_id"] for item in by_kind(world.attention(), "AUTOPAY_SHORTFALL")] == [dollar["id"]]
    # Moeda sem cambio hoje: nao da para dizer se o saldo cobre.
    world.set_rows("UPDATE accounts SET currency = 'XYZ' WHERE id = ?", (dollar["id"],))
    assert by_kind(world.attention(), "AUTOPAY_SHORTFALL") == []


def test_refund_credit_is_neither_overdue_nor_payable(world, clock):
    one = world.card("Um")
    two = world.card("Dois")
    world.purchase(one, 100, "2026-09-10")
    world.refund(one, 30, "2026-09-12")
    world.purchase(two, 10, "2026-09-10")
    world.refund(two, 50, "2026-09-12")
    [overdue] = by_kind(world.attention(), "INVOICE_OVERDUE")
    assert overdue["total"] == 70
    assert [item["card_id"] for item in overdue["invoices"]] == [one["id"]]

    three = world.card("Tres")
    world.purchase(three, 10, "2026-10-10")
    world.refund(three, 40, "2026-10-12")
    clock.set("2026-11-05")
    world.set_rows("DELETE FROM cc_expenses WHERE card_id IN (?, ?)", (one["id"], two["id"]))
    assert by_kind(world.attention(), "INVOICE_PAYABLE") == []


def recurrence(world, account, start, **extra):
    return world.call("post", "/api/recurring", json={
        "type": "EXPENSE", "amount": 59.9, "frequency": "MONTHLY", "start_date": start,
        "description": "Streaming", "category": "Lazer", "account_id": account["id"], **extra,
    }).get_json()


def test_keys_identify_the_case(world, monkeypatch, app_module):
    real_today = date.today()
    clock = freeze(monkeypatch, real_today)
    banco = world.account("Banco", initial=1000)
    item = recurrence(world, banco, (real_today - timedelta(days=70)).isoformat())

    [before] = by_kind(world.attention(), "RECURRING")
    assert before["key"] == f"recorrencias:{item['id']}@x{before['count']}"
    world.call("post", "/api/recurring/run")
    assert by_kind(world.attention(), "RECURRING") == []

    clock.set(real_today + timedelta(days=40))
    [after] = by_kind(world.attention(), "RECURRING")
    last = next(row for row in world.get("/api/recurring")["items"] if row["id"] == item["id"])["last_occurrence_date"]
    assert last and after["key"] == f"recorrencias:{item['id']}@{last}x{after['count']}"
    assert after["key"] != before["key"]


def plan_month(world, month, *budgets):
    world.call("put", "/api/monthly-plan", json={"month": month, "income_amount": 10000, "invest_percent": 10, "spend_percent": 50})
    for category_id, percent in budgets:
        world.call("post", "/api/budgets", json={"month": month, "category_id": category_id, "planned_percent": percent})


def test_over_budget_key_follows_the_month(world, clock):
    banco = world.account("Banco", initial=1000)
    plan_month(world, "2026-10", (world.category_id("Alimentação"), 1))
    world.tx("EXPENSE", 80, "2026-10-05", banco, "Alimentação", "Mercado")
    [over] = by_kind(world.attention(), "OVER_BUDGET")
    assert over["key"] == f"orcamento:2026-10:{world.category_id('Alimentação')}"
    assert over["category_name"] == "Alimentação" and over["category_id"] == world.category_id("Alimentação")
    assert (over["spent"], over["available"], over["tone"]) == (80, 50, "warning")

    clock.set("2026-11-02")
    world.tx("EXPENSE", 80, "2026-11-01", banco, "Alimentação", "Mercado")
    [november] = by_kind(world.attention(), "OVER_BUDGET")
    assert november["key"] == f"orcamento:2026-11:{world.category_id('Alimentação')}"


def test_item_order_and_stable_keys(world, monkeypatch, app_module):
    real_today = date.today()
    freeze(monkeypatch, real_today)
    month = real_today.strftime("%Y-%m")
    banco = world.account("Banco", initial=1000)
    plan_month(world, month, (world.category_id("Lazer"), 1), (world.category_id("Moradia"), 50))
    world.tx("EXPENSE", 80, real_today.isoformat(), banco, "Lazer")
    world.tx("EXPENSE", 10, real_today.isoformat(), banco, "Moradia")
    recurrence(world, banco, (real_today - timedelta(days=40)).isoformat())
    recurrence(world, banco, (real_today - timedelta(days=10)).isoformat(), description="Academia")

    items = world.attention()
    assert kinds(items) == ["RECURRING", "OVER_BUDGET"]
    assert items[0]["count"] == world.get("/api/recurring")["pending_count"] >= 2
    assert [item["key"] for item in world.attention()] == [item["key"] for item in items]


def test_over_budget_sorted_by_overspend_with_parent_name(world, clock):
    banco = world.account("Banco", initial=1000)
    mercado = world.call("post", "/api/categories", json={
        "name": "Mercado", "kind": "EXPENSE", "parent_id": world.category_id("Alimentação"),
    }).get_json()
    plan_month(world, "2026-10", (mercado["id"], 1), (world.category_id("Lazer"), 1))
    world.call("post", "/api/transactions", json={
        "type": "EXPENSE", "amount": 70, "date": "2026-10-05", "account_id": banco["id"], "category_id": mercado["id"],
    })
    world.tx("EXPENSE", 120, "2026-10-05", banco, "Lazer")

    over = by_kind(world.attention(), "OVER_BUDGET")
    assert [item["category_name"] for item in over] == ["Lazer", "Alimentação › Mercado"]
    assert [item["spent"] - item["available"] for item in over] == [70, 20]


def test_blocked_recurrence_still_counts_as_pending(world, monkeypatch, app_module):
    real_today = date.today()
    freeze(monkeypatch, real_today)
    world.account("Banco", initial=10)
    velha = world.account("Velha", initial=10)
    recurrence(world, velha, (real_today - timedelta(days=40)).isoformat())
    world.archive_account(velha)

    run = world.call("post", "/api/recurring/run").get_json()
    assert run["blocked"]
    [item] = by_kind(world.attention(), "RECURRING")
    assert item["count"] == world.get("/api/recurring")["pending_count"] > 0


def test_user_isolation(client, world, other_user, clock):
    banco = world.account("Banco", initial=0)
    card = world.card(autopay_account_id=banco["id"])
    world.purchase(card, 10, "2026-09-10")
    recurrence(world, banco, "2026-08-01")
    assert world.attention()

    assert World(client, other_user).attention() == []
