"""Proventos (juros, amortizacao) lancados contra um titulo de renda fixa.

Registrado em next-steps como "erro do backend". Nao reproduz como 500 nem no
codigo da epoca; a unica recusa e a de nao haver posicao na data com, e ela
agora diz qual data conferir.
"""


def create_cdb(client, auth, purchase_date="2025-01-02", price=1000):
    response = client.post(
        "/api/investments",
        json=[{
            "asset_class": "FIXED_INCOME",
            "ticker_or_name": "CDB PROVENTO",
            "quantity": 1,
            "average_price": price,
            "current_price": price,
            "metadata": {
                "fixed_income_type": "CDB",
                "rate_type": "POS",
                "indexer": "CDI",
                "cdi_percentage": 1.1,
                "purchase_date": purchase_date,
            },
        }],
        headers=auth,
    )
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    return response.get_json()[0]["asset_id"]


def proceed(asset_id, **fields):
    body = {
        "asset_id": asset_id,
        "proceeds_type": "AMORTIZATION",
        "record_date": "2025-06-02",
        "payment_date": "2025-06-02",
        "declared_date": None,
        "ex_date": None,
        "amount_per_unit": None,
        "eligible_quantity": None,
        "gross_amount": None,
        "tax_amount": None,
        "notes": "",
    }
    body.update(fields)
    return body


def test_gross_amount_on_a_cdb_is_accepted(client, auth):
    asset_id = create_cdb(client, auth)
    response = client.post("/api/investment-proceeds", json=proceed(asset_id, gross_amount=50), headers=auth)
    assert response.status_code == 201, response.get_data(as_text=True)
    item = response.get_json()
    assert item["gross_amount"] == 50.0
    assert item["eligible_quantity"] == 1.0
    assert item["asset"]["asset_class"] == "FIXED_INCOME"
    assert item["cost_basis_at_record_date"] == 1000.0


def test_amount_per_unit_on_a_cdb_uses_the_single_unit(client, auth):
    asset_id = create_cdb(client, auth)
    response = client.post(
        "/api/investment-proceeds",
        json=proceed(asset_id, proceeds_type="DIVIDEND", amount_per_unit=12.5),
        headers=auth,
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    assert response.get_json()["gross_amount"] == 12.5


def test_no_position_on_the_record_date_names_the_date(client, auth):
    # Comprado depois da data com: 400 com a data, nao um erro generico.
    asset_id = create_cdb(client, auth, purchase_date="2025-07-01")
    response = client.post(
        "/api/investment-proceeds",
        json=proceed(asset_id, amount_per_unit=10),
        headers=auth,
    )
    assert response.status_code == 400
    assert "02/06/2025" in response.get_json()["error"]


def test_gross_amount_without_position_is_still_accepted(client, auth):
    asset_id = create_cdb(client, auth, purchase_date="2025-07-01")
    response = client.post("/api/investment-proceeds", json=proceed(asset_id, gross_amount=30), headers=auth)
    assert response.status_code == 201, response.get_data(as_text=True)
    assert response.get_json()["gross_amount"] == 30.0
