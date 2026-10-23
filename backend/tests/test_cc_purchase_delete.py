"""DELETE /api/cc-expenses/purchases/<id>: a compra inteira, num pedido so.

Substitui o "busca /candidates, filtra no centavo, manda a lista" da tela
Cartoes (proposta B9). A compra e o client_id (035): qualquer parcela leva as
outras, uma corrida igual no mesmo dia fica. So as parcelas em aberto saem —
a paga fica com a fatura dela (037) — e os comprovantes das que saem vao
junto, o arquivo depois do commit.
"""

import importlib
import io
import os
from datetime import date

import pytest

from finance_world import World, freeze

PDF = b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"


@pytest.fixture()
def world(client, user):
    return World(client, user)


@pytest.fixture()
def clock(app_module, monkeypatch):
    return freeze(monkeypatch, date(2026, 10, 20))


def rows(world):
    return world.get("/api/cc-expenses")


def delete(world, item_id, expected=200):
    return world.call("delete", f"/api/cc-expenses/purchases/{item_id}", expected=expected).get_json()


def upload(world, expense_id):
    response = world.client.post(
        f"/api/cc-expenses/{expense_id}/attachments",
        data={"file": (io.BytesIO(PDF), "nota.pdf")},
        headers=world.auth,
        content_type="multipart/form-data",
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def stored_path(world, attachment_id):
    with importlib.import_module("db").get_db() as conn:
        row = conn.execute("SELECT stored_name FROM cc_expense_attachments WHERE id = ?", (attachment_id,)).fetchone()
    return importlib.import_module("services.attachments").attachment_path(world.user["id"], row["stored_name"])


def paid_first_installment(world, clock):
    bank = world.account("Banco", initial=1000)
    card = world.card()
    installments = world.purchase(card, 300, "2026-10-10", "TV", installments=3)
    clock.set("2026-11-05")
    payment = world.pay(card, 11, 2026, bank)
    return card, installments, payment


def test_deletes_open_installments_keeps_paid(world, clock):
    _, installments, payment = paid_first_installment(world, clock)

    body = delete(world, installments[0]["id"])
    assert body["deleted"] == 2 and body["kept_paid"] == 1
    assert set(body["ids"]) == {installments[1]["id"], installments[2]["id"]}
    left = rows(world)
    assert [(row["id"], row["status"]) for row in left] == [(installments[0]["id"], "PAID")]
    # O pagamento da fatura continua no extrato.
    assert payment["transaction"]["id"] in {row["id"] for row in world.get("/api/transactions")}


def test_any_installment_id_works(world, clock):
    _, installments, _ = paid_first_installment(world, clock)
    body = delete(world, installments[2]["id"])
    assert (body["deleted"], body["kept_paid"]) == (2, 1)


def test_all_paid_is_409_and_writes_nothing(world, clock):
    bank = world.account("Banco", initial=1000)
    card = world.card()
    rows_created = world.purchase(card, 50, "2026-10-10")
    clock.set("2026-11-05")
    world.pay(card, 11, 2026, bank)

    response = world.call("delete", f"/api/cc-expenses/purchases/{rows_created[0]['id']}", expected=409)
    assert "Nenhuma parcela em aberto" in response.get_json()["error"]
    assert [row["status"] for row in rows(world)] == ["PAID"]


def test_another_purchase_is_untouched(world, clock):
    card = world.card()
    first = world.purchase(card, 10, "2026-10-10", "Uber")
    second = world.purchase(card, 10, "2026-10-10", "Uber")

    assert delete(world, first[0]["id"])["ids"] == [first[0]["id"]]
    assert [row["id"] for row in rows(world)] == [second[0]["id"]]


def test_legacy_purchase_by_legacy_client_id(world, clock):
    card = world.card()
    created = world.purchase(card, 90, "2026-10-10", "Antiga", installments=3)
    other = world.purchase(card, 30, "2026-10-10", "Antiga")
    # Uma compra de antes de 024: o backfill da 035 deu a ela legacy:<id>.
    world.set_rows(
        "UPDATE cc_expenses SET client_id = ? WHERE client_id = ?",
        (f"legacy:{created[0]['id']}", created[0]["client_id"]),
    )

    body = delete(world, created[1]["id"])
    assert body["deleted"] == 3
    assert [row["id"] for row in rows(world)] == [other[0]["id"]]


def test_refund_row(world, clock):
    card = world.card()
    world.purchase(card, 100, "2026-10-10")
    refund_id = world.refund(card, 30, "2026-10-12")["id"]

    assert delete(world, refund_id) == {"deleted": 1, "kept_paid": 0, "ids": [refund_id]}
    assert [row["kind"] for row in rows(world)] == ["PURCHASE"]


def test_receipt_files_removed_after_commit(world, clock):
    _, installments, _ = paid_first_installment(world, clock)
    paid_receipt = upload(world, installments[0]["id"])
    open_receipt = upload(world, installments[1]["id"])
    paid_path = stored_path(world, paid_receipt["id"])
    open_path = stored_path(world, open_receipt["id"])
    assert os.path.exists(paid_path) and os.path.exists(open_path)

    delete(world, installments[1]["id"])
    assert not os.path.exists(open_path)
    assert os.path.exists(paid_path)
    remaining = world.get(f"/api/cc-expenses/{installments[0]['id']}/attachments")
    assert [item["id"] for item in remaining] == [paid_receipt["id"]]


def test_other_user_404(client, world, other_user, clock):
    card = world.card()
    created = world.purchase(card, 10, "2026-10-10")
    other = World(client, other_user)
    response = other.call("delete", f"/api/cc-expenses/purchases/{created[0]['id']}", expected=404)
    assert response.get_json()["error"] == "Compra nao encontrada."
    assert len(rows(world)) == 1
