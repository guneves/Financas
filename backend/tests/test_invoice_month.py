"""Axis 3, second half: which invoice a purchase lands in.

This rule used to live in `frontend/src/pages/Carteira.jsx`, where it could not
be tested. It moved to the backend on 2026-09-15 (`compute_invoice_start`,
`split_installments`, `POST /api/cc-expenses/purchases`) and these tests pin the
behaviour that the frontend had, including the year rollover and the
cent-exact installment split.
"""

import pytest


@pytest.fixture()
def card(client, auth):
    """Fechamento antes do vencimento — o caso comum de um cartao brasileiro."""
    response = client.post(
        "/api/credit-cards",
        headers=auth,
        json={"name": "Cartao Fatura", "due_day": 10, "closing_day": 3},
    )
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    body = response.get_json()
    return body[0] if isinstance(body, list) else body


def make_card(client, auth, name, due_day, closing_day):
    response = client.post(
        "/api/credit-cards",
        headers=auth,
        json={"name": name, "due_day": due_day, "closing_day": closing_day},
    )
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    body = response.get_json()
    return body[0] if isinstance(body, list) else body


def create_purchase(client, auth, card, **overrides):
    payload = {
        "card_id": card["id"],
        "category": "Compras",
        "description": "Compra parcelada",
        "total_amount": 300.0,
        "purchase_date": "2026-03-01",
        "installments": 3,
    }
    payload.update(overrides)
    return client.post("/api/cc-expenses/purchases", headers=auth, json=payload)


# --- compute_invoice_start ---------------------------------------------------

def test_purchase_before_closing_stays_in_the_current_invoice(app_module):
    assert app_module.compute_invoice_start("2026-03-01", due_day=10, closing_day=3) == {
        "invoice_month": 3,
        "invoice_year": 2026,
    }


def test_purchase_on_closing_day_rolls_to_the_next_invoice(app_module):
    assert app_module.compute_invoice_start("2026-03-03", due_day=10, closing_day=3) == {
        "invoice_month": 4,
        "invoice_year": 2026,
    }


def test_purchase_after_closing_rolls_to_the_next_invoice(app_module):
    assert app_module.compute_invoice_start("2026-03-20", due_day=10, closing_day=3) == {
        "invoice_month": 4,
        "invoice_year": 2026,
    }


def test_december_purchase_rolls_into_january_of_the_next_year(app_module):
    assert app_module.compute_invoice_start("2026-12-20", due_day=10, closing_day=3) == {
        "invoice_month": 1,
        "invoice_year": 2027,
    }


def test_closing_after_due_shifts_the_cycle_one_month_forward(app_module):
    """Fechamento depois do vencimento: o ciclo ja esta deslocado."""
    assert app_module.compute_invoice_start("2026-03-10", due_day=5, closing_day=28) == {
        "invoice_month": 4,
        "invoice_year": 2026,
    }


def test_closing_after_due_and_purchase_past_closing_skips_two_months(app_module):
    assert app_module.compute_invoice_start("2026-03-28", due_day=5, closing_day=28) == {
        "invoice_month": 5,
        "invoice_year": 2026,
    }


def test_missing_closing_day_falls_back_to_seven_days_before_due(app_module):
    assert app_module.default_closing_day(10) == 3
    assert app_module.compute_invoice_start("2026-03-01", due_day=10, closing_day=None) == {
        "invoice_month": 3,
        "invoice_year": 2026,
    }


def test_missing_closing_day_wraps_when_due_day_is_early(app_module):
    """Vencimento no dia 3: o fechamento presumido cai no mes anterior, dia 26."""
    assert app_module.default_closing_day(3) == 26


def test_add_invoice_months_normalizes_the_year(app_module):
    assert app_module.add_invoice_months(11, 2026, 3) == (2, 2027)
    assert app_module.add_invoice_months(1, 2026, 12) == (1, 2027)
    assert app_module.add_invoice_months(12, 2026, 0) == (12, 2026)


# --- split_installments ------------------------------------------------------

def test_installments_divide_exactly_when_they_can(app_module):
    assert app_module.split_installments(300.0, 3) == [100.0, 100.0, 100.0]


def test_installment_remainder_goes_to_the_first_installments(app_module):
    parcels = app_module.split_installments(100.0, 3)
    assert parcels == [33.34, 33.33, 33.33]
    assert app_module.rounded_money(sum(parcels)) == 100.0


def test_installments_never_lose_a_cent(app_module):
    for total, count in ((0.01, 1), (10.0, 7), (1234.56, 12), (99.99, 6)):
        parcels = app_module.split_installments(total, count)
        assert len(parcels) == count
        assert app_module.rounded_money(sum(parcels)) == app_module.rounded_money(total)


# --- POST /api/cc-expenses/purchases ----------------------------------------

def test_purchase_endpoint_creates_one_row_per_installment(client, auth, card):
    response = create_purchase(client, auth, card, purchase_date="2026-03-01")
    assert response.status_code == 201, response.get_data(as_text=True)

    rows = response.get_json()
    assert [row["installment_info"] for row in rows] == ["1/3", "2/3", "3/3"]
    assert [(row["invoice_month"], row["invoice_year"]) for row in rows] == [
        (3, 2026),
        (4, 2026),
        (5, 2026),
    ]
    assert sum(row["amount"] for row in rows) == pytest.approx(300.0)
    assert all(row["status"] == "OPEN" for row in rows)
    assert all(row["purchase_date"] == "2026-03-01" for row in rows)


def test_purchase_endpoint_rolls_installments_across_the_year(client, auth, card):
    response = create_purchase(
        client,
        auth,
        card,
        purchase_date="2026-11-20",
        installments=4,
        total_amount=400.0,
    )
    assert response.status_code == 201

    rows = response.get_json()
    assert [(row["invoice_month"], row["invoice_year"]) for row in rows] == [
        (12, 2026),
        (1, 2027),
        (2, 2027),
        (3, 2027),
    ]


def test_purchase_endpoint_uses_the_card_closing_day(client, auth):
    early = make_card(client, auth, "Fecha cedo", due_day=10, closing_day=3)
    late = make_card(client, auth, "Fecha tarde", due_day=10, closing_day=25)

    early_rows = create_purchase(
        client, auth, early, purchase_date="2026-03-01", installments=1, total_amount=50.0
    ).get_json()
    late_rows = create_purchase(
        client, auth, late, purchase_date="2026-03-01", installments=1, total_amount=50.0
    ).get_json()

    # Mesmo dia de compra, faturas diferentes: quem fecha no dia 3 ainda pega
    # marco; quem fecha depois do vencimento ja esta com o ciclo deslocado.
    assert (early_rows[0]["invoice_month"], early_rows[0]["invoice_year"]) == (3, 2026)
    assert (late_rows[0]["invoice_month"], late_rows[0]["invoice_year"]) == (4, 2026)


def test_purchase_endpoint_rejects_another_users_card(client, auth, other_user):
    foreign = make_card(client, other_user["headers"], "Cartao alheio", due_day=10, closing_day=3)
    response = create_purchase(client, auth, foreign)
    assert response.status_code in (400, 403, 404)

    listed = client.get("/api/cc-expenses", headers=auth).get_json()
    assert listed == []


def test_purchase_endpoint_requires_authentication(client, auth, card):
    response = client.post(
        "/api/cc-expenses/purchases",
        json={
            "card_id": card["id"],
            "category": "Compras",
            "description": "Sem token",
            "total_amount": 100.0,
            "purchase_date": "2026-03-01",
            "installments": 1,
        },
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "overrides",
    [
        {"total_amount": 0},
        {"total_amount": -10},
        {"installments": 0},
        {"installments": 2.5},
        {"purchase_date": "01/03/2026"},
        {"description": ""},
        {"category": ""},
    ],
)
def test_purchase_endpoint_rejects_invalid_payloads(client, auth, card, overrides):
    response = create_purchase(client, auth, card, **overrides)
    assert response.status_code == 400, response.get_data(as_text=True)
    assert client.get("/api/cc-expenses", headers=auth).get_json() == []
