"""Entradas fora do normal recusadas com 400, nunca um 500 nem um valor errado gravado.

Achados numa caca a bugs (2026-10-22) mandando payloads estranhos a cada rota:

- um corpo JSON que nao e objeto (lista, texto, numero) virava 500 no `.get()`;
- `rounded_money()` devolvia 0.0 para 1e26 ou mais (a precisao padrao do
  Decimal), e 0,004 passava pelo "maior que zero" e era gravado como R$ 0,00
  (ou batia no CHECK amount > 0 do banco: 500);
- uma data em 9999 era aceita; a fatura dela caia no ano 10000 e toda leitura
  de Cartoes passava a responder 500;
- `credit_enabled` com lista ou objeto, e o ano da fatura enorme, eram 500.
"""

import uuid

import pytest

from money import MAX_MONEY, rounded_money


def create_account(client, auth, name="Banco"):
    response = client.post("/api/accounts", json={"name": name, "type": "CHECKING"}, headers=auth)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["id"]


def create_card(client, auth, name="Visa"):
    response = client.post(
        "/api/credit-cards", json={"name": name, "due_day": 10, "closing_day": 3}, headers=auth,
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["id"]


def expense(account_id, **fields):
    return {"amount": 10, "date": "2026-10-01", "type": "EXPENSE", "account_id": account_id,
            "category": "Outros", "description": "teste", **fields}


class TestJsonBody:
    @pytest.mark.parametrize("body", ["texto", 5, ["a"], [{"amount": 10}]])
    def test_a_body_that_is_not_an_object_is_a_400(self, client, auth, body):
        response = client.post("/api/transactions", json=body, headers=auth)
        assert response.status_code == 400, response.get_data(as_text=True)

    def test_the_list_routes_still_take_a_list(self, client, auth):
        card_id = create_card(client, auth)
        response = client.post("/api/cc-expenses", json=[{
            "card_id": card_id, "category": "Outros", "description": "Lista", "amount": 15,
            "purchase_date": "2026-10-01", "invoice_month": 11, "invoice_year": 2026, "installment_info": "1/1",
        }], headers=auth)
        assert response.status_code == 201, response.get_data(as_text=True)
        assert client.post("/api/cc-expenses", json=[], headers=auth).status_code == 400


class TestMoney:
    def test_rounded_money_keeps_large_values(self):
        # Antes: InvalidOperation no quantize e 0.0 sem aviso.
        assert rounded_money(1e27) == 1e27
        assert rounded_money(123456789012345678901234567.894) == pytest.approx(1.2345678901234568e26)
        assert rounded_money(0.125) == 0.13

    @pytest.mark.parametrize("amount", [0.004, 0.0049])
    def test_an_amount_that_rounds_to_zero_is_refused(self, client, auth, amount):
        account_id = create_account(client, auth)
        response = client.post("/api/transactions", json=expense(account_id, amount=amount), headers=auth)
        assert response.status_code == 400
        assert "R$ 0,01" in response.get_json()["error"]
        assert client.get("/api/transactions", headers=auth).get_json() == []

    def test_half_a_cent_rounds_up_and_is_kept(self, client, auth):
        account_id = create_account(client, auth)
        response = client.post("/api/transactions", json=expense(account_id, amount=0.005), headers=auth)
        assert response.status_code == 201, response.get_data(as_text=True)
        assert response.get_json()["amount"] == 0.01

    def test_an_amount_above_the_ceiling_is_refused(self, client, auth):
        account_id = create_account(client, auth)
        response = client.post("/api/transactions", json=expense(account_id, amount=1e27), headers=auth)
        assert response.status_code == 400
        response = client.post("/api/transactions", json=expense(account_id, amount=MAX_MONEY), headers=auth)
        assert response.status_code == 201

    @pytest.mark.parametrize("amount", [0.001, 1e308])
    def test_a_recurrence_amount_is_a_400_not_the_check_constraint(self, client, auth, amount):
        response = client.post("/api/recurring", json={
            "amount": amount, "type": "EXPENSE", "category": "Outros", "description": "Feira",
            "frequency": "MONTHLY", "start_date": "2026-01-10",
        }, headers=auth)
        assert response.status_code == 400, response.get_data(as_text=True)

    def test_a_negative_initial_balance_is_still_allowed(self, client, auth):
        account_id = create_account(client, auth)
        response = client.patch(f"/api/accounts/{account_id}", json={"initial_balance": -250.255}, headers=auth)
        assert response.status_code == 200, response.get_data(as_text=True)
        assert response.get_json()["initial_balance"] == -250.26

    def test_a_card_purchase_that_rounds_to_zero_is_refused(self, client, auth):
        card_id = create_card(client, auth)
        response = client.post("/api/cc-expenses/purchases", json={
            "card_id": card_id, "description": "Nada", "total_amount": 0.001,
            "purchase_date": "2026-10-01", "installments": 1, "category": "Outros",
        }, headers=auth)
        assert response.status_code == 400
        assert client.get("/api/cc-expenses", headers=auth).get_json() == []


class TestDates:
    @pytest.mark.parametrize("value", ["9999-12-31", "2200-01-01", "1899-12-31", "0999-01-01"])
    def test_a_year_out_of_range_is_refused(self, client, auth, value):
        account_id = create_account(client, auth)
        response = client.post("/api/transactions", json=expense(account_id, date=value), headers=auth)
        assert response.status_code == 400

    def test_a_refund_in_9999_no_longer_breaks_the_cards_screen(self, client, auth):
        card_id = create_card(client, auth)
        response = client.post("/api/cc-expenses/refunds", json={
            "card_id": card_id, "amount": 5, "purchase_date": "9999-12-31", "description": "Estorno",
        }, headers=auth)
        assert response.status_code == 400
        assert client.get("/api/cc-expenses", headers=auth).status_code == 200

    def test_a_month_out_of_range_is_refused(self, client, auth):
        response = client.get("/api/budgets", query_string={"month": "9999-12"}, headers=auth)
        assert response.status_code == 400

    def test_run_through_year_one_is_a_400(self, client, auth):
        response = client.post("/api/recurring/run", json={"through": "0001-01-01"}, headers=auth)
        assert response.status_code == 400

    def test_the_edges_of_the_range_are_accepted(self, client, auth):
        account_id = create_account(client, auth)
        for value in ("1900-01-01", "2199-12-31"):
            response = client.post("/api/transactions", json=expense(account_id, date=value), headers=auth)
            assert response.status_code == 201, response.get_data(as_text=True)

    def test_an_inbox_date_without_time_is_checked_like_one_with_time(self, client, auth):
        create_account(client, auth, "Itaú")
        response = client.post("/api/inbox/detections", json={"detections": [{
            "key": uuid.uuid4().hex, "app": "com.itau", "kind": "PIX_OUT", "amount_cents": 4590,
            "posted_ms": 1791648000000, "utc_offset_minutes": -180, "counterparty": "Fulano",
        }]}, headers=auth)
        assert response.status_code == 200, response.get_data(as_text=True)
        [item] = client.get("/api/inbox", headers=auth).get_json()["items"]
        response = client.patch(
            f"/api/inbox/{item['id']}", json={"version": item["version"], "occurred_at": "9999-12-31"}, headers=auth,
        )
        assert response.status_code == 400
        response = client.patch(
            f"/api/inbox/{item['id']}", json={"version": item["version"], "occurred_at": "2026-10-09"}, headers=auth,
        )
        assert response.status_code == 200, response.get_data(as_text=True)


class TestCards:
    @pytest.mark.parametrize("value", [[], {"a": 1}, "talvez"])
    def test_credit_enabled_that_is_not_a_flag_is_a_400(self, client, auth, value):
        card_id = create_card(client, auth)
        response = client.patch(f"/api/credit-cards/{card_id}", json={"credit_enabled": value}, headers=auth)
        assert response.status_code == 400
        response = client.post("/api/credit-cards", json={"name": "Outro", "credit_enabled": value}, headers=auth)
        assert response.status_code == 400

    @pytest.mark.parametrize("year", [10**20, 1e308, 2200])
    def test_an_invoice_year_out_of_range_is_a_400(self, client, auth, year):
        card_id = create_card(client, auth)
        account_id = create_account(client, auth)
        response = client.post("/api/cc-expenses/pay-invoice", json={
            "card_id": card_id, "invoice_month": 9, "invoice_year": year,
            "account_id": account_id, "payment_date": "2026-10-15",
        }, headers=auth)
        assert response.status_code == 400


def operation(client, auth, **fields):
    payload = {"ticker_or_name": "VALE3", "asset_class": "STOCKS", "quantity": 10, "average_price": 30,
               "current_price": 30, "metadata": {"purchase_date": "2026-02-05"}, **fields}
    return client.post("/api/investments", headers=auth, json=payload)


def sale(client, auth):
    return operation(client, auth, quantity=-1, current_price=35,
                     metadata={"sale_date": "2026-03-05", "sale_price": 35})


class TestInvestments:
    @pytest.mark.parametrize("fields", [{"quantity": 1e308}, {"average_price": 1e308}, {"current_price": 1e308}])
    def test_a_number_too_big_is_refused_and_does_not_block_later_operations(self, client, auth, fields):
        # Antes: custo infinito, resultado realizado NaN, e o NOT NULL do banco
        # recusava esta e toda operacao seguinte do dono (500).
        assert operation(client, auth, **fields).status_code == 400
        assert operation(client, auth).status_code == 201
        assert sale(client, auth).status_code == 201

    @pytest.mark.parametrize("value", ["0999-01-01", "9999-12-31", "abc", "2026-02-30"])
    def test_a_bad_operation_date_is_refused(self, client, auth, value):
        # "abc" virava a data de hoje sem aviso; "0999" era gravado "999" e
        # derrubava o relatorio de IR.
        response = operation(client, auth, metadata={"purchase_date": value})
        assert response.status_code == 400
        assert client.get("/api/tax-report?year=2026", headers=auth).status_code == 200

    def test_an_edit_with_a_bad_date_is_refused(self, client, auth):
        created = operation(client, auth)
        assert created.status_code == 201
        movement_id = created.get_json()[0]["id"]
        response = client.patch(f"/api/investments/{movement_id}", headers=auth,
                                json={"metadata": {"purchase_date": "0999-01-01"}})
        assert response.status_code == 400

    @pytest.mark.parametrize("value", [["CDB"], {"a": 1}])
    def test_a_fixed_income_type_that_is_not_text_is_a_400(self, client, auth, value):
        response = client.post("/api/investments", headers=auth, json={
            "ticker_or_name": "CDB X", "asset_class": "FIXED_INCOME", "quantity": 1, "average_price": 1000,
            "metadata": {"purchase_date": "2025-01-05", "fixed_income_type": value, "cdi_percentage": 100},
        })
        assert response.status_code == 400

    def test_a_repeated_proceed_from_9999_is_a_400(self, client, auth):
        asset_id = operation(client, auth).get_json()[0]["asset_id"]
        response = client.post("/api/investment-proceeds", headers=auth, json={
            "asset_id": asset_id, "proceeds_type": "DIVIDEND", "record_date": "9999-12-01",
            "payment_date": "9999-12-31", "gross_amount": 50, "repeat": {"every_months": 1, "count": 2},
        })
        assert response.status_code == 400


def test_a_purchase_smaller_than_its_installments_is_refused(client, auth):
    card_id = create_card(client, auth)
    response = client.post("/api/cc-expenses/purchases", json={
        "card_id": card_id, "description": "Chiclete", "total_amount": 0.02,
        "purchase_date": "2026-10-01", "installments": 3, "category": "Outros",
    }, headers=auth)
    assert response.status_code == 400
    assert "R$ 0,01" in response.get_json()["error"]
    assert client.get("/api/cc-expenses", headers=auth).get_json() == []
    response = client.post("/api/cc-expenses/purchases", json={
        "card_id": card_id, "description": "Chiclete", "total_amount": 0.03,
        "purchase_date": "2026-10-01", "installments": 3, "category": "Outros",
    }, headers=auth)
    assert response.status_code == 201
    assert [row["amount"] for row in response.get_json()] == [0.01, 0.01, 0.01]
