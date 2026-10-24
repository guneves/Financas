"""Criacoes de investimentos idempotentes por `client_id` (042), como o "+ Novo" (024).

A fila do celular reenvia o mesmo envio quando nao sabe se ele chegou. Com o
mesmo client_id:

- POST /api/investments (uma operacao ou uma lista), o resgate, POST
  /api/investment-proceeds (com ou sem `repeat`) e POST /api/corporate-actions
  devolvem o que a primeira entrega gravou (200) e nao gravam de novo;
- a busca vem antes da validacao (a segunda entrega nao e recusada por um
  estado que a primeira mudou);
- uma lista leva um client_id so; um id mal formado e recusado;
- o mesmo id de outro usuario nao enxerga nada.
"""

import importlib

import pytest

from test_treasury import D1, TODAY, buy as treasury_buy, portfolio, prices, tesouro, treasury_assets  # noqa: F401

CID = "0b9f6c2e-1d4a-4e8b-9c3f-2a7d5e6f8a10"


@pytest.fixture(autouse=True)
def no_market(app_module, monkeypatch):
    monkeypatch.setattr(
        importlib.import_module("routes.investments"), "refresh_market_prices",
        lambda *args, **kwargs: {"updated_count": 0},
    )
    prices_module = importlib.import_module("services.prices")
    monkeypatch.setattr(prices_module, "download_close_prices", lambda symbols, **kwargs: {})


def title(name="CDB BANCO X 2045", price=1000.0, **extra):
    return {
        "asset_class": "FIXED_INCOME", "ticker_or_name": name, "quantity": 1,
        "average_price": price, "current_price": price,
        "metadata": {"fixed_income_type": "CDB", "rate_type": "PRE", "annual_rate": 12,
                     "purchase_date": "2025-01-02", "cash_account_id": None},
        **extra,
    }


def movements(client, auth):
    return client.get("/api/investments", headers=auth).get_json()


class TestMovements:
    def test_a_second_delivery_returns_the_first(self, client, auth):
        first = client.post("/api/investments", headers=auth, json=title(client_id=CID))
        assert first.status_code == 201, first.get_json()
        again = client.post("/api/investments", headers=auth, json=title(client_id=CID, price=2000.0))
        assert again.status_code == 200
        assert [item["id"] for item in again.get_json()] == [item["id"] for item in first.get_json()]
        assert again.get_json()[0]["average_price"] == 1000.0
        assert len(movements(client, auth)) == 1

    def test_a_list_is_one_delivery(self, client, auth):
        items = [title("CDB A 2045", client_id=CID), title("CDB B 2045", client_id=CID)]
        first = client.post("/api/investments", headers=auth, json=items)
        assert first.status_code == 201, first.get_json()
        again = client.post("/api/investments", headers=auth, json=items)
        assert again.status_code == 200
        assert [item["ticker_or_name"] for item in again.get_json()] == ["CDB A 2045", "CDB B 2045"]
        assert len(movements(client, auth)) == 2

    @pytest.mark.parametrize("ids", [(CID, None), (CID, "outro-envio-123")])
    def test_a_list_with_different_ids_is_refused(self, client, auth, ids):
        items = [title("CDB A 2045", client_id=ids[0]), title("CDB B 2045", client_id=ids[1])]
        assert client.post("/api/investments", headers=auth, json=items).status_code == 400
        assert movements(client, auth) == []

    def test_a_malformed_id_is_refused(self, client, auth):
        response = client.post("/api/investments", headers=auth, json=title(client_id="curto"))
        assert response.status_code == 400
        assert "client_id" in response.get_json()["error"]

    def test_the_lookup_runs_before_validation(self, client, auth):
        assert client.post("/api/investments", headers=auth, json=title(client_id=CID)).status_code == 201
        broken = title(client_id=CID)
        broken["quantity"] = 0
        assert client.post("/api/investments", headers=auth, json=broken).status_code == 200

    def test_another_user_with_the_same_id_writes_their_own(self, client, auth, other_user):
        assert client.post("/api/investments", headers=auth, json=title(client_id=CID)).status_code == 201
        theirs = client.post("/api/investments", headers=other_user["headers"], json=title(client_id=CID))
        assert theirs.status_code == 201
        assert len(movements(client, other_user["headers"])) == 1
        assert len(movements(client, auth)) == 1

    def test_without_an_id_nothing_changes(self, client, auth):
        for _ in range(2):
            assert client.post("/api/investments", headers=auth, json=title()).status_code == 201
        assert len(movements(client, auth)) == 2


class TestRedemption:
    def test_a_repeated_redemption_is_written_once(self, client, auth, prices):
        treasury_buy(client, auth, "Tesouro IPCA+ 2045", 1000.00, D1, rate=0.065)
        [position] = treasury_assets(portfolio(client, auth))
        payload = {"position_id": position["id"], "amount": 600, "date": TODAY.isoformat(),
                   "cash_account_id": None, "client_id": CID}
        first = client.post("/api/investments/redemptions", headers=auth, json=payload)
        assert first.status_code == 201, first.get_json()
        # A posicao ja nao e a mesma (o resgate tirou titulos): a busca vem antes.
        again = client.post("/api/investments/redemptions", headers=auth, json={**payload, "amount": 99999})
        assert again.status_code == 200
        assert [item["id"] for item in again.get_json()] == [item["id"] for item in first.get_json()]
        assert len([m for m in movements(client, auth) if m["quantity"] < 0]) == 1


def create_fixed_income_asset(client, auth):
    response = client.post("/api/investments", headers=auth, json=title("DEBENTURE X"))
    assert response.status_code == 201
    return response.get_json()[0]["asset_id"]


def all_proceeds(client, auth):
    return client.get(
        "/api/investment-proceeds?status=ALL&date_from=2000-01-01&date_to=2100-12-31", headers=auth,
    ).get_json()


class TestProceeds:
    def test_a_single_proceed_comes_back_as_itself(self, client, auth):
        asset_id = create_fixed_income_asset(client, auth)
        payload = {"asset_id": asset_id, "proceeds_type": "INTEREST", "payment_date": "2025-07-15",
                   "gross_amount": 60, "client_id": CID}
        first = client.post("/api/investment-proceeds", headers=auth, json=payload)
        assert first.status_code == 201, first.get_json()
        again = client.post("/api/investment-proceeds", headers=auth, json=payload)
        assert again.status_code == 200
        assert again.get_json()["id"] == first.get_json()["id"]
        assert len(all_proceeds(client, auth)) == 1

    def test_a_repeat_comes_back_as_the_list(self, client, auth):
        asset_id = create_fixed_income_asset(client, auth)
        payload = {"asset_id": asset_id, "proceeds_type": "INTEREST", "payment_date": "2025-07-15",
                   "gross_amount": 60, "repeat": {"every_months": 6, "count": 3}, "client_id": CID}
        first = client.post("/api/investment-proceeds", headers=auth, json=payload)
        assert first.status_code == 201, first.get_json()
        again = client.post("/api/investment-proceeds", headers=auth, json=payload)
        assert again.status_code == 200
        assert [item["id"] for item in again.get_json()] == [item["id"] for item in first.get_json()]
        assert len(all_proceeds(client, auth)) == 3

    def test_a_malformed_id_is_refused(self, client, auth):
        asset_id = create_fixed_income_asset(client, auth)
        response = client.post("/api/investment-proceeds", headers=auth, json={
            "asset_id": asset_id, "proceeds_type": "INTEREST", "payment_date": "2025-07-15",
            "gross_amount": 60, "client_id": "x y",
        })
        assert response.status_code == 400
        assert all_proceeds(client, auth) == []


class TestCorporateActions:
    def test_a_repeated_split_is_applied_once(self, client, auth):
        bought = client.post("/api/investments", headers=auth, json={
            "asset_class": "STOCKS", "ticker_or_name": "PETR4", "quantity": 100,
            "average_price": 30, "current_price": 30,
            "metadata": {"purchase_date": "2026-01-10", "cash_account_id": None},
        })
        assert bought.status_code == 201, bought.get_json()
        asset_id = bought.get_json()[0]["asset_id"]
        payload = {"asset_id": asset_id, "action_type": "SPLIT", "ex_date": "2026-02-01",
                   "ratio_from": 1, "ratio_to": 2, "client_id": CID}
        first = client.post("/api/corporate-actions", headers=auth, json=payload)
        assert first.status_code == 201, first.get_json()
        again = client.post("/api/corporate-actions", headers=auth, json=payload)
        assert again.status_code == 200
        assert again.get_json()["id"] == first.get_json()["id"]
        assert len(client.get("/api/corporate-actions", headers=auth).get_json()) == 1
        # Desdobrado uma vez so: 100 viram 200, nao 400.
        assert [m["quantity"] for m in movements(client, auth)] == [200]
