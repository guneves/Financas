"""Axis 5: no endpoint may return or touch another user's data.

Every table carries `user_id`. These tests create two users, have the first one
write, and assert the second one can neither read nor destroy any of it.
"""

import pytest


@pytest.fixture()
def owner_data(client, user):
    """A transaction, a credit card, an invoice line and an investment."""
    auth = user["headers"]

    transaction = client.post(
        "/api/transactions",
        headers=auth,
        json={
            "type": "EXPENSE",
            "category": "Alimentacao",
            "description": "Mercado",
            "amount": 250.0,
            "date": "2026-03-05",
        },
    )
    assert transaction.status_code in (200, 201), transaction.get_data(as_text=True)
    transaction = transaction.get_json()
    transaction = transaction[0] if isinstance(transaction, list) else transaction

    card = client.post(
        "/api/credit-cards",
        headers=auth,
        json={"name": "Cartao Titular", "due_day": 10, "closing_day": 3},
    )
    assert card.status_code in (200, 201), card.get_data(as_text=True)
    card = card.get_json()
    card = card[0] if isinstance(card, list) else card

    expense = client.post(
        "/api/cc-expenses",
        headers=auth,
        json={
            "card_id": card["id"],
            "category": "Compras",
            "description": "Notebook",
            "amount": 4000.0,
            "purchase_date": "2026-03-01",
            "invoice_month": 3,
            "invoice_year": 2026,
            "installment_info": "1/1",
        },
    )
    assert expense.status_code in (200, 201), expense.get_data(as_text=True)
    expense = expense.get_json()
    expense = expense[0] if isinstance(expense, list) else expense

    investment = client.post(
        "/api/investments",
        headers=auth,
        json={
            "asset_class": "STOCKS",
            "ticker_or_name": "ISOL4",
            "quantity": 100,
            "average_price": 20.0,
            "current_price": 20.0,
            "metadata": {"purchase_date": "2026-02-01"},
        },
    )
    assert investment.status_code in (200, 201), investment.get_data(as_text=True)
    investment = investment.get_json()
    investment = investment[0] if isinstance(investment, list) else investment

    return {
        "auth": auth,
        "transaction": transaction,
        "card": card,
        "expense": expense,
        "investment": investment,
    }


class TestReadsAreScopedToTheOwner:
    def test_a_stranger_sees_no_transactions(self, client, owner_data, other_user):
        response = client.get("/api/transactions", headers=other_user["headers"])
        assert response.status_code == 200
        ids = {item["id"] for item in response.get_json()}
        assert owner_data["transaction"]["id"] not in ids

    def test_a_stranger_sees_no_credit_cards(self, client, owner_data, other_user):
        response = client.get("/api/credit-cards", headers=other_user["headers"])
        assert response.status_code == 200
        ids = {item["id"] for item in response.get_json()}
        assert owner_data["card"]["id"] not in ids

    def test_a_stranger_sees_no_invoice_lines(self, client, owner_data, other_user):
        response = client.get("/api/cc-expenses", headers=other_user["headers"])
        assert response.status_code == 200
        ids = {item["id"] for item in response.get_json()}
        assert owner_data["expense"]["id"] not in ids

    def test_a_stranger_sees_no_investments_assets_or_positions(self, client, owner_data, other_user):
        headers = other_user["headers"]
        investment_id = owner_data["investment"]["id"]
        asset_id = owner_data["investment"]["asset_id"]

        investments = client.get("/api/investments", headers=headers)
        assert investment_id not in {i["id"] for i in investments.get_json()}

        assets = client.get("/api/assets", headers=headers)
        assert asset_id not in {a["id"] for a in assets.get_json()}

        positions = client.get("/api/investment-positions", headers=headers)
        assert asset_id not in {p.get("asset_id") for p in positions.get_json()}

    def test_me_returns_the_caller_not_the_owner(self, client, owner_data, other_user):
        response = client.get("/api/auth/me", headers=other_user["headers"])
        assert response.status_code == 200
        assert response.get_json()["user"]["email"] == other_user["email"]


class TestWritesCannotReachAnotherUsersRows:
    def test_a_stranger_cannot_delete_a_transaction(self, client, owner_data, other_user):
        item_id = owner_data["transaction"]["id"]
        response = client.delete("/api/transactions/" + item_id, headers=other_user["headers"])
        assert response.status_code in (400, 403, 404) or response.get_json().get("deleted") == 0

        still_there = client.get("/api/transactions", headers=owner_data["auth"])
        assert item_id in {item["id"] for item in still_there.get_json()}

    def test_a_stranger_cannot_delete_a_credit_card(self, client, owner_data, other_user):
        card_id = owner_data["card"]["id"]
        response = client.delete("/api/credit-cards/" + card_id, headers=other_user["headers"])
        assert response.status_code in (400, 403, 404) or response.get_json().get("deleted") == 0

        still_there = client.get("/api/credit-cards", headers=owner_data["auth"])
        assert card_id in {item["id"] for item in still_there.get_json()}

    def test_a_stranger_cannot_attach_an_expense_to_someone_elses_card(self, client, owner_data, other_user):
        response = client.post(
            "/api/cc-expenses",
            headers=other_user["headers"],
            json={
                "card_id": owner_data["card"]["id"],
                "category": "Compras",
                "description": "Invasao",
                "amount": 10.0,
                "purchase_date": "2026-03-02",
                "invoice_month": 3,
                "invoice_year": 2026,
                "installment_info": "1/1",
            },
        )
        assert response.status_code in (400, 403, 404)

    def test_a_stranger_cannot_settle_someone_elses_invoice(self, client, owner_data, other_user):
        response = client.patch(
            "/api/cc-expenses/invoice-status",
            headers=other_user["headers"],
            json={
                "card_id": owner_data["card"]["id"],
                "invoice_month": 3,
                "invoice_year": 2026,
                "status": "PAID",
            },
        )
        assert response.status_code in (400, 403, 404)

        owner_view = client.get("/api/cc-expenses", headers=owner_data["auth"]).get_json()
        expense = [e for e in owner_view if e["id"] == owner_data["expense"]["id"]][0]
        assert expense["status"] == "OPEN"

    def test_a_stranger_cannot_delete_an_investment(self, client, owner_data, other_user):
        investment_id = owner_data["investment"]["id"]
        response = client.delete("/api/investments/" + investment_id, headers=other_user["headers"])
        assert response.status_code in (400, 403, 404) or response.get_json().get("deleted") == 0

        still_there = client.get("/api/investments", headers=owner_data["auth"])
        assert investment_id in {item["id"] for item in still_there.get_json()}

    def test_a_stranger_cannot_delete_an_asset(self, client, owner_data, other_user):
        asset_id = owner_data["investment"]["asset_id"]
        response = client.delete(
            "/api/investments/by-asset/" + asset_id + "?asset_class=STOCKS",
            headers=other_user["headers"],
        )
        assert response.status_code in (400, 403, 404) or response.get_json().get("deleted") == 0

        still_there = client.get("/api/assets", headers=owner_data["auth"])
        assert asset_id in {item["id"] for item in still_there.get_json()}


class TestAuthenticationIsRequired:
    @pytest.mark.parametrize(
        "path",
        [
            "/api/transactions",
            "/api/credit-cards",
            "/api/cc-expenses",
            "/api/assets",
            "/api/investments",
            "/api/investment-positions",
            "/api/investment-proceeds",
            "/api/database/status",
            "/api/auth/me",
        ],
    )
    def test_protected_endpoints_reject_anonymous_callers(self, client, path):
        assert client.get(path).status_code == 401

    def test_a_tampered_token_is_rejected(self, client, user):
        bad = user["token"][:-4] + "AAAA"
        response = client.get("/api/auth/me", headers={"Authorization": "Bearer " + bad})
        assert response.status_code == 401

    def test_health_stays_public(self, client):
        assert client.get("/api/health").status_code == 200
