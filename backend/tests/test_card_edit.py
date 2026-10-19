"""Corrigir um cartao e o que sobrou do endpoint antigo de compras (revisao de 2026-10-18).

O PATCH so aceitava a conta do debito automatico: errou o nome, o vencimento
ou o fechamento, so restava excluir e perder o historico. E o fechamento no
dia 29 a 31 fecha no ultimo dia de um mes mais curto: a compra desse dia vai
para a proxima fatura, nao para uma que ja aparece fechada.
"""

import pytest


def make_card(client, auth, name="Cartao", due_day=10, closing_day=3):
    response = client.post(
        "/api/credit-cards", headers=auth, json={"name": name, "due_day": due_day, "closing_day": closing_day}
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def patch(client, auth, card, body):
    return client.patch(f"/api/credit-cards/{card['id']}", headers=auth, json=body)


class TestEditingACard:
    def test_name_due_day_and_closing_day_can_be_fixed(self, client, auth):
        card = make_card(client, auth, "Nubak", due_day=10, closing_day=3)
        response = patch(client, auth, card, {"name": "Nubank", "due_day": 15, "closing_day": 8})
        assert response.status_code == 200, response.get_data(as_text=True)
        body = response.get_json()
        assert (body["name"], body["due_day"], body["closing_day"]) == ("Nubank", 15, 8)

    def test_the_new_days_decide_the_next_purchases(self, client, auth):
        card = make_card(client, auth, due_day=10, closing_day=3)
        patch(client, auth, card, {"due_day": 20, "closing_day": 12})
        rows = client.post("/api/cc-expenses/purchases", headers=auth, json={
            "card_id": card["id"], "category": "Compras", "description": "Mesa",
            "total_amount": 100, "purchase_date": "2026-03-05", "installments": 1,
        }).get_json()
        # Antes do fechamento novo (12): fatura de marco, nao de abril.
        assert (rows[0]["invoice_month"], rows[0]["invoice_year"]) == (3, 2026)

    def test_editing_keeps_the_autopay(self, client, auth):
        card = make_card(client, auth)
        account_id = client.get("/api/accounts", headers=auth).get_json()[0]["id"]
        patch(client, auth, card, {"autopay_account_id": account_id})
        body = patch(client, auth, card, {"name": "Outro nome"}).get_json()
        assert body["autopay_account_id"] == account_id

    def test_a_repeated_name_is_refused(self, client, auth):
        make_card(client, auth, "Visa")
        card = make_card(client, auth, "Master")
        response = patch(client, auth, card, {"name": "Visa"})
        assert response.status_code == 409
        names = sorted(item["name"] for item in client.get("/api/credit-cards", headers=auth).get_json())
        assert names == ["Master", "Visa"]

    @pytest.mark.parametrize("body", [{}, {"due_day": 0}, {"closing_day": 32}, {"name": ""}])
    def test_invalid_edits_are_refused(self, client, auth, body):
        card = make_card(client, auth)
        assert patch(client, auth, card, body).status_code == 400

    def test_another_users_card_is_not_found(self, client, auth, other_user):
        card = make_card(client, auth)
        response = client.patch(
            f"/api/credit-cards/{card['id']}", headers=other_user["headers"], json={"name": "Meu"}
        )
        assert response.status_code == 404


class TestClosingDayInAShortMonth:
    @pytest.mark.parametrize("closing_day,due_day", [(30, 10), (31, 5), (29, 31)])
    def test_a_purchase_on_the_clamped_closing_day_goes_to_an_open_invoice(
        self, invoices_module, closing_day, due_day
    ):
        start = invoices_module.compute_invoice_start("2026-02-28", due_day=due_day, closing_day=closing_day)
        closing = invoices_module.invoice_closing_date(
            start["invoice_month"], start["invoice_year"], due_day, closing_day
        )
        # A fatura em que a compra cai ainda nao tinha fechado no dia da compra.
        assert closing.isoformat() > "2026-02-28"

    def test_the_day_before_the_clamped_closing_stays(self, invoices_module):
        # Fecha "dia 30": em fevereiro, 28/02. A compra de 27/02 fica na fatura que fecha nele.
        start = invoices_module.compute_invoice_start("2026-02-27", due_day=10, closing_day=30)
        assert (start["invoice_month"], start["invoice_year"]) == (3, 2026)
        start = invoices_module.compute_invoice_start("2026-02-28", due_day=10, closing_day=30)
        assert (start["invoice_month"], start["invoice_year"]) == (4, 2026)

    def test_long_months_are_unchanged(self, invoices_module):
        assert invoices_module.compute_invoice_start("2026-03-29", due_day=10, closing_day=30) == {
            "invoice_month": 4, "invoice_year": 2026,
        }
        assert invoices_module.compute_invoice_start("2026-03-30", due_day=10, closing_day=30) == {
            "invoice_month": 5, "invoice_year": 2026,
        }


class TestTheOldListEndpoint:
    def line(self, card, **extra):
        return {
            "card_id": card["id"], "category": "Compras", "description": "Compra", "amount": 10.005,
            "purchase_date": "2026-03-01", "invoice_month": 3, "invoice_year": 2026,
            "installment_info": "1/1", **extra,
        }

    def test_the_amount_is_rounded_half_up(self, client, auth):
        card = make_card(client, auth)
        rows = client.post("/api/cc-expenses", headers=auth, json=self.line(card)).get_json()
        assert rows[0]["amount"] == 10.01

    def test_a_paid_line_is_refused(self, client, auth):
        card = make_card(client, auth)
        response = client.post("/api/cc-expenses", headers=auth, json=self.line(card, status="PAID"))
        assert response.status_code == 400
        assert client.get("/api/cc-expenses", headers=auth).get_json() == []
