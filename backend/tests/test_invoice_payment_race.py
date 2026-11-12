"""Uma fatura e paga uma vez so, mesmo com dois pedidos ao mesmo tempo.

`settle_invoice()` le os itens em aberto e depois grava o pagamento. Sem uma
transacao de escrita aberta antes da leitura, dois pedidos simultaneos (toque
duplo em Pagar, um reenvio do cliente, ou Pagar enquanto uma leitura do Inicio
aplica o debito automatico da mesma fatura) liam os mesmos itens e gravavam
dois pagamentos: a conta era debitada duas vezes.

Os testes forcam a intercalacao: a leitura dos itens de dentro de
`settle_invoice()` espera o outro pedido chegar ao mesmo ponto (uma barreira)
antes de seguir. Com a transacao de escrita aberta primeiro (db.begin_write),
o segundo pedido so le depois do commit do primeiro, e a barreira desiste.
"""

import importlib
import threading
from datetime import date

import pytest
from finance_world import World, freeze

PAYMENT_TYPES = ("CC_INVOICE_PAYMENT", "CC_AUTOPAY")


@pytest.fixture()
def world(client, user):
    return World(client, user)


@pytest.fixture()
def clock(app_module, monkeypatch):
    return freeze(monkeypatch, date(2026, 9, 1))


@pytest.fixture()
def meet_at_the_read(app_module, monkeypatch):
    """Faz dois pedidos se encontrarem logo depois de `settle_invoice()` ler os
    itens em aberto (a primeira leitura feita com `inside` ligado em cada thread)."""
    invoices = importlib.import_module("services.invoices")
    original_lines = invoices.invoice_open_lines
    original_settle = invoices.settle_invoice
    barrier = threading.Barrier(2, timeout=1.5)
    state = threading.local()

    def lines(*args, **kwargs):
        result = original_lines(*args, **kwargs)
        if getattr(state, "inside", False) and not getattr(state, "met", False):
            state.met = True
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                pass
        return result

    def settle(*args, **kwargs):
        state.inside = True
        try:
            return original_settle(*args, **kwargs)
        finally:
            state.inside = False

    monkeypatch.setattr(invoices, "invoice_open_lines", lines)
    monkeypatch.setattr(invoices, "settle_invoice", settle)
    monkeypatch.setattr(importlib.import_module("routes.cards"), "settle_invoice", settle)


def together(app_module, *calls):
    """Roda cada chamada numa thread, com um cliente proprio; devolve os status na ordem."""
    statuses = [None] * len(calls)

    def run(index, call):
        statuses[index] = call(app_module.app.test_client()).status_code

    threads = [threading.Thread(target=run, args=(index, call)) for index, call in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return statuses


def payments(world):
    return [row for row in world.get("/api/transactions") if row.get("source_type") in PAYMENT_TYPES]


def balance(world, name):
    return next(account["balance"] for account in world.get("/api/accounts") if account["name"] == name)


def test_two_pay_requests_at_once_pay_the_invoice_once(world, clock, meet_at_the_read, app_module):
    banco = world.account("Banco", initial=1000)
    card = world.card()
    world.purchase(card, 100, "2026-09-10")
    clock.set("2026-10-20")
    line = world.get("/api/cc-expenses")[0]
    body = {
        "card_id": card["id"], "invoice_month": line["invoice_month"], "invoice_year": line["invoice_year"],
        "account_id": banco["id"],
    }

    def pay(client):
        return client.post("/api/cc-expenses/pay-invoice", headers=world.auth, json=body)

    statuses = together(app_module, pay, pay)

    assert sorted(statuses) == [201, 409]
    assert [row["amount"] for row in payments(world)] == [100.0]
    assert balance(world, "Banco") == 900
    [paid] = world.get("/api/cc-expenses")
    assert paid["status"] == "PAID" and paid["paid_by"] == payments(world)[0]["id"]


def test_pagar_and_the_autopay_at_once_pay_the_invoice_once(world, clock, meet_at_the_read, app_module):
    banco = world.account("Banco", initial=1000)
    card = world.card(autopay_account_id=banco["id"])
    world.purchase(card, 100, "2026-09-10")
    line = world.get("/api/cc-expenses")[0]  # antes do vencimento: esta leitura nao debita
    clock.set("2026-10-10")  # o dia do vencimento: a leitura do Inicio debita
    body = {
        "card_id": card["id"], "invoice_month": line["invoice_month"], "invoice_year": line["invoice_year"],
        "account_id": banco["id"],
    }

    def pay(client):
        return client.post("/api/cc-expenses/pay-invoice", headers=world.auth, json=body)

    def home(client):
        return client.get("/api/home", headers=world.auth)

    statuses = together(app_module, pay, home)

    assert statuses[1] == 200 and statuses[0] in (201, 409)
    assert [row["amount"] for row in payments(world)] == [100.0]
    assert balance(world, "Banco") == 900
