"""Resgate de renda fixa no servidor (POST /api/investments/redemptions) e a
exclusao do Tesouro agrupado numa transacao so (DELETE /api/investments/by-assets).

Antes, a tela fazia a conta (`allocateTreasuryRedemption()` em
lib/treasury.js) e mandava um resgate por compra. Agora:

- a divisao PEPS e a de sempre, com os mesmos casos de treasury.test.js:
  a compra mais antiga primeiro, custo proporcional ao bruto tirado dela, a
  posicao inteira e nem um centavo a mais;
- a rota acha a posicao pela carteira e grava um resgate por compra, todos
  ou nenhum; um titulo so (CDB) tem custo = preco medio x valor / bruto;
- `cash_account_id` como no POST de operacoes;
- a exclusao de varios ativos desfaz tudo se um deles nao confere.
"""

import importlib

import pytest

from test_treasury import D1, D2, TODAY, buy, portfolio, prices, tesouro, treasury_assets  # noqa: F401

LOTS = [
    {"id": "b", "purchase_date": "2026-07-11", "invested": 2200, "gross": 2400},
    {"id": "a", "purchase_date": "2025-09-14", "invested": 1000, "gross": 1200},
]


@pytest.fixture()
def treasury(app_module):
    return importlib.import_module("services.treasury")


class TestThePepsSplit:
    """Os casos de treasury.test.js, um a um."""

    def test_a_redemption_takes_the_oldest_buy_first_cost_in_proportion(self, treasury):
        assert treasury.allocate_treasury_redemption(LOTS, 600) == [{"lot_id": "a", "amount": 600, "cost": 500}]
        parts = treasury.allocate_treasury_redemption(LOTS, 1800)
        assert [(part["lot_id"], part["amount"]) for part in parts] == [("a", 1200), ("b", 600)]
        assert parts[0]["cost"] == 1000
        assert parts[1]["cost"] == 550

    def test_the_whole_position_and_not_a_cent_more(self, treasury):
        ValidationError = importlib.import_module("validators").ValidationError
        assert [part["amount"] for part in treasury.allocate_treasury_redemption(LOTS, 3600)] == [1200, 2400]
        with pytest.raises(ValidationError, match="saldo bruto"):
            treasury.allocate_treasury_redemption(LOTS, 3600.01)
        with pytest.raises(ValidationError, match="valor"):
            treasury.allocate_treasury_redemption(LOTS, 0)

    def test_a_single_title_costs_average_price_times_the_share_redeemed(self, treasury):
        position = {"id": "cdb", "average_price": 1000, "current_value": 1250}
        assert treasury.redemption_parts(position, 500) == [{"lot_id": "cdb", "amount": 500, "cost": 400}]


def redeem(client, auth, **payload):
    return client.post("/api/investments/redemptions", headers=auth, json=payload)


def movements(client, auth):
    return client.get("/api/investments", headers=auth).get_json()


class TestTheRedemptionRoute:
    def test_a_grouped_title_is_redeemed_oldest_buy_first(self, client, auth, prices):
        first = buy(client, auth, "Tesouro IPCA+ 2045", 1000.00, D1, rate=0.065)
        second = buy(client, auth, "Tesouro IPCA+ 2045", 2200.00, D2, rate=0.060)
        [position] = treasury_assets(portfolio(client, auth))

        response = redeem(client, auth, position_id=position["id"], amount=1800, date=TODAY.isoformat(),
                          cash_account_id=None)
        assert response.status_code == 201, response.get_json()
        parts = response.get_json()
        assert [part["metadata"]["related_id"] for part in parts] == [first, second]
        assert [part["average_price"] for part in parts] == pytest.approx([1000.00, 550.00])
        assert [part["current_price"] for part in parts] == pytest.approx([1200.00, 600.00])
        assert all(part["quantity"] == -1 and part["metadata"]["is_redemption"] for part in parts)
        assert all(part["metadata"]["redemption_date"] == TODAY.isoformat() for part in parts)

        [after] = treasury_assets(portfolio(client, auth))
        assert after["total_invested"] == pytest.approx(3200.00 - 1550.00)
        assert [lot["id"] for lot in after["lots"]] == [second]

    def test_more_than_the_gross_writes_nothing(self, client, auth, prices):
        buy(client, auth, "Tesouro IPCA+ 2045", 1000.00, D1, rate=0.065)
        buy(client, auth, "Tesouro IPCA+ 2045", 2200.00, D2, rate=0.060)
        [position] = treasury_assets(portfolio(client, auth))
        before = len(movements(client, auth))

        response = redeem(client, auth, position_id=position["id"], amount=3600.01, date=TODAY.isoformat())
        assert response.status_code == 400
        assert "saldo bruto" in response.get_json()["error"]
        assert len(movements(client, auth)) == before

    def test_a_single_cdb_keeps_the_proportional_cost(self, client, auth, prices):
        response = client.post("/api/investments", headers=auth, json=[{
            "asset_class": "FIXED_INCOME", "ticker_or_name": "CDB BANCO X 2045", "quantity": 1,
            "average_price": 1000.0, "current_price": 1000.0,
            "metadata": {"fixed_income_type": "CDB", "rate_type": "PRE", "annual_rate": 12,
                         "purchase_date": D1.isoformat(), "cash_account_id": None},
        }])
        assert response.status_code == 201
        [position] = [asset for asset in portfolio(client, auth)["assets"] if asset["class"] == "FIXED_INCOME"]
        amount = 300.0
        expected_cost = position["average_price"] * (amount / position["current_value"])

        response = redeem(client, auth, position_id=position["id"], amount=amount, date=TODAY.isoformat(),
                          cash_account_id=None)
        assert response.status_code == 201, response.get_json()
        [part] = response.get_json()
        assert part["metadata"]["related_id"] == position["id"]
        assert part["average_price"] == pytest.approx(expected_cost)
        assert part["current_price"] == pytest.approx(amount)

    def test_without_the_key_the_cash_lands_in_the_corretora(self, client, auth, prices):
        corretora = client.post("/api/accounts", headers=auth, json={"name": "Corretora", "type": "BROKERAGE"}).get_json()
        buy(client, auth, "Tesouro IPCA+ 2045", 1000.00, D1, rate=0.065)
        [position] = treasury_assets(portfolio(client, auth))
        response = redeem(client, auth, position_id=position["id"], amount=600, date=TODAY.isoformat())
        assert response.status_code == 201, response.get_json()
        [part] = response.get_json()
        assert part["metadata"]["cash_account_id"] == corretora["id"]

    @pytest.mark.parametrize("payload, status", [
        ({"position_id": "nao-existe", "amount": 10, "date": TODAY.isoformat()}, 404),
        ({"amount": 10, "date": TODAY.isoformat()}, 400),
        ({"position_id": "x", "amount": 0, "date": TODAY.isoformat()}, 400),
        ({"position_id": "x", "amount": 10}, 400),
    ])
    def test_refusals(self, client, auth, prices, payload, status):
        assert redeem(client, auth, **payload).status_code == status

    def test_another_users_position_is_not_found(self, client, auth, other_user, prices):
        buy(client, auth, "Tesouro IPCA+ 2045", 1000.00, D1, rate=0.065)
        [position] = treasury_assets(portfolio(client, auth))
        response = redeem(client, other_user["headers"], position_id=position["id"], amount=100,
                          date=TODAY.isoformat())
        assert response.status_code == 404


def delete_assets(client, auth, **payload):
    return client.delete("/api/investments/by-assets", headers=auth, json=payload)


class TestTheGroupedDelete:
    def two_assets(self, client, auth):
        buy(client, auth, "Tesouro IPCA+ 2045", 1000.00, D1, rate=0.065)
        buy(client, auth, "TESOURO IPCA+ 2045 (NTNB PRINC)", 2200.00, D2, rate=0.060)
        [position] = treasury_assets(portfolio(client, auth))
        assert len(position["asset_ids"]) == 2
        return position

    def test_every_asset_of_the_title_goes_at_once(self, client, auth, prices):
        position = self.two_assets(client, auth)
        response = delete_assets(client, auth, asset_ids=position["asset_ids"], asset_class="FIXED_INCOME")
        assert response.status_code == 200, response.get_json()
        assert response.get_json()["deleted"] == 2
        assert treasury_assets(portfolio(client, auth)) == []
        assert movements(client, auth) == []

    @pytest.mark.parametrize("bad, status", [("nao-existe", 404), (None, 409)])
    def test_one_refusal_keeps_them_all(self, client, auth, prices, bad, status):
        position = self.two_assets(client, auth)
        if bad is None:
            # Outro ativo do dono, de outra classe: a guarda recusa.
            other = client.post("/api/investments", headers=auth, json=[{
                "asset_class": "OTHER", "ticker_or_name": "OBRA DE ARTE", "quantity": 1,
                "average_price": 10, "current_price": 10,
                "metadata": {"purchase_date": D1.isoformat(), "cash_account_id": None},
            }])
            assert other.status_code == 201, other.get_json()
            bad = other.get_json()[0]["asset_id"]
        response = delete_assets(client, auth, asset_ids=[*position["asset_ids"], bad], asset_class="FIXED_INCOME")
        assert response.status_code == status
        assert len(treasury_assets(portfolio(client, auth))[0]["lots"]) == 2

    def test_another_users_assets_are_not_found(self, client, auth, other_user, prices):
        position = self.two_assets(client, auth)
        response = delete_assets(client, other_user["headers"], asset_ids=position["asset_ids"],
                                 asset_class="FIXED_INCOME")
        assert response.status_code == 404
        assert len(treasury_assets(portfolio(client, auth))) == 1

    @pytest.mark.parametrize("payload", [{"asset_class": "FIXED_INCOME"}, {"asset_ids": [], "asset_class": "FIXED_INCOME"},
                                         {"asset_ids": ["x"]}])
    def test_refused_without_ids_or_class(self, client, auth, payload):
        assert delete_assets(client, auth, **payload).status_code == 400
