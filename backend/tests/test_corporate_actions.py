"""Eventos corporativos: desdobramento, grupamento e bonificacao (Fase 6, 017).

O que estes testes fixam:

- desdobramento e grupamento reescalam quantidade e preco das operacoes
  anteriores a data ex, sem mudar o total nem o caixa ligado;
- depois do desdobramento as cotas novas podem ser vendidas, e o FIFO usa o
  custo por cota ajustado;
- bonificacao cria as cotas novas com o custo atribuido e sem caixa;
- as guardas: nada lancado antes do ultimo evento, a operacao da bonificacao
  nao se edita nem se exclui sozinha, eventos em ordem de data, e so o ultimo
  evento, sem operacao depois dele, pode ser desfeito;
- desfazer volta exatamente ao que era;
- renda fixa nao tem evento, e nada de outro usuario e visto ou alterado.
"""

import importlib

import pytest


@pytest.fixture(autouse=True)
def no_market(app_module, monkeypatch):
    """Registrar um evento busca a cotacao nova no mercado; aqui, sem rede."""
    monkeypatch.setattr(
        importlib.import_module("routes.investments"), "refresh_market_prices",
        lambda *args, **kwargs: {"updated_count": 0},
    )


def post_movement(client, auth, *, quantity, price, date, ticker="PETR4", sale=False):
    metadata = {"sale_date": date, "sale_price": price} if sale else {"purchase_date": date}
    return client.post(
        "/api/investments",
        headers=auth,
        json={
            "asset_class": "STOCKS",
            "ticker_or_name": ticker,
            "quantity": -quantity if sale else quantity,
            "average_price": price,
            "current_price": price,
            "metadata": metadata,
        },
    )


def buy(client, auth, **kwargs):
    response = post_movement(client, auth, **kwargs)
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    body = response.get_json()
    return body[0] if isinstance(body, list) else body


def create_action(client, auth, asset_id, **fields):
    payload = {"asset_id": asset_id, "action_type": "SPLIT", "ex_date": "2026-02-01", "ratio_from": 1, "ratio_to": 2}
    payload.update(fields)
    return client.post("/api/corporate-actions", headers=auth, json=payload)


def movements(client, auth):
    return client.get("/api/investments", headers=auth).get_json()


def position(client, auth, ticker="PETR4"):
    portfolio = client.get("/api/investments/portfolio?refresh_prices=false", headers=auth).get_json()
    return next(asset for asset in portfolio["assets"] if asset.get("ticker") == ticker)


def cash_entries(client, auth):
    return [
        item for item in client.get("/api/transactions", headers=auth).get_json()
        if item.get("source_type") == "INVESTMENT_TRANSACTION"
    ]


class TestSplit:
    def test_a_split_doubles_quantity_and_halves_the_price(self, client, auth):
        purchase = buy(client, auth, quantity=100, price=10.0, date="2026-01-10")
        response = create_action(client, auth, purchase["asset_id"])
        assert response.status_code == 201, response.get_data(as_text=True)
        assert response.get_json()["price_refreshed"] is False

        row = next(item for item in movements(client, auth) if item["id"] == purchase["id"])
        assert row["quantity"] == pytest.approx(200)
        assert row["average_price"] == pytest.approx(5.0)
        assert row["metadata"]["corporate_adjustments"][0]["quantity_before"] == 100
        # O caixa da compra nao muda: continua 1.000.
        assert [entry["amount"] for entry in cash_entries(client, auth)] == [pytest.approx(1000.0)]
        assert position(client, auth)["quantity"] == pytest.approx(200)

    def test_the_new_shares_can_be_sold_with_the_adjusted_cost(self, client, auth):
        purchase = buy(client, auth, quantity=100, price=10.0, date="2026-01-10")
        create_action(client, auth, purchase["asset_id"])
        response = post_movement(client, auth, quantity=200, price=6.0, date="2026-03-01", sale=True)
        assert response.status_code in (200, 201), response.get_data(as_text=True)

        sale = next(item for item in movements(client, auth) if item["quantity"] < 0)
        assert sale["realized_cost_basis"] == pytest.approx(1000.0)
        assert sale["realized_profit"] == pytest.approx(200.0)

    def test_a_reverse_split_groups_shares(self, client, auth):
        purchase = buy(client, auth, quantity=100, price=1.0, date="2026-01-10")
        response = create_action(client, auth, purchase["asset_id"], action_type="REVERSE_SPLIT", ratio_from=10, ratio_to=1)
        assert response.status_code == 201, response.get_data(as_text=True)
        assert position(client, auth)["quantity"] == pytest.approx(10)
        assert position(client, auth)["average_price"] == pytest.approx(10.0)

    def test_the_ratio_must_match_the_type(self, client, auth):
        purchase = buy(client, auth, quantity=100, price=10.0, date="2026-01-10")
        assert create_action(client, auth, purchase["asset_id"], ratio_from=2, ratio_to=1).status_code == 400
        assert create_action(
            client, auth, purchase["asset_id"], action_type="REVERSE_SPLIT", ratio_from=1, ratio_to=2,
        ).status_code == 400


class TestBonus:
    def test_bonus_adds_shares_at_the_attributed_cost_without_cash(self, client, auth):
        purchase = buy(client, auth, quantity=100, price=10.0, date="2026-01-10")
        response = create_action(
            client, auth, purchase["asset_id"], action_type="BONUS", ratio_from=10, ratio_to=1, bonus_unit_cost=2,
        )
        assert response.status_code == 201, response.get_data(as_text=True)

        held = position(client, auth)
        assert held["quantity"] == pytest.approx(110)
        # (1.000 + 10 x 2) / 110, em centavos.
        assert held["average_price"] == pytest.approx(9.27)
        assert len(cash_entries(client, auth)) == 1

    def test_the_bonus_movement_is_locked(self, client, auth):
        purchase = buy(client, auth, quantity=100, price=10.0, date="2026-01-10")
        action = create_action(client, auth, purchase["asset_id"], action_type="BONUS", ratio_from=10, ratio_to=1).get_json()
        bonus_id = action["bonus_transaction_id"]
        assert client.delete(f"/api/investments/{bonus_id}", headers=auth).status_code == 409
        assert client.patch(f"/api/investments/{bonus_id}", headers=auth, json={"quantity": 50}).status_code == 409


class TestGuards:
    def test_nothing_can_be_entered_before_the_event(self, client, auth):
        purchase = buy(client, auth, quantity=100, price=10.0, date="2026-01-10")
        create_action(client, auth, purchase["asset_id"])
        response = post_movement(client, auth, quantity=10, price=10.0, date="2026-01-20")
        assert response.status_code == 400
        assert "desdobramento" in response.get_json()["error"]
        assert post_movement(client, auth, quantity=10, price=5.0, date="2026-02-10").status_code in (200, 201)

    def test_editing_a_movement_across_the_event_is_refused(self, client, auth):
        purchase = buy(client, auth, quantity=100, price=10.0, date="2026-01-10")
        create_action(client, auth, purchase["asset_id"])
        response = client.patch(
            f"/api/investments/{purchase['id']}", headers=auth,
            json={"metadata": {"purchase_date": "2026-02-15"}},
        )
        assert response.status_code == 409
        # Mudar o preco sem mudar de lado da data ex vale, e o ajuste fica.
        edited = client.patch(
            f"/api/investments/{purchase['id']}", headers=auth,
            json={"average_price": 5.5, "metadata": {"purchase_date": "2026-01-12"}},
        )
        assert edited.status_code == 200, edited.get_data(as_text=True)
        assert edited.get_json()["metadata"]["corporate_adjustments"]

    def test_events_are_recorded_in_date_order(self, client, auth):
        purchase = buy(client, auth, quantity=100, price=10.0, date="2026-01-10")
        assert create_action(client, auth, purchase["asset_id"], ex_date="2026-03-01").status_code == 201
        assert create_action(client, auth, purchase["asset_id"], ex_date="2026-02-01").status_code == 400

    def test_an_event_needs_a_position(self, client, auth):
        purchase = buy(client, auth, quantity=100, price=10.0, date="2026-05-10")
        assert create_action(client, auth, purchase["asset_id"], ex_date="2026-02-01").status_code == 400

    def test_fixed_income_has_no_corporate_actions(self, client, auth):
        response = client.post(
            "/api/investments", headers=auth,
            json=[{
                "asset_class": "FIXED_INCOME", "ticker_or_name": "CDB X", "quantity": 1,
                "average_price": 1000, "current_price": 1000,
                "metadata": {"fixed_income_type": "CDB", "rate_type": "PRE", "annual_rate": 10, "purchase_date": "2026-01-02"},
            }],
        )
        asset_id = response.get_json()[0]["asset_id"]
        assert create_action(client, auth, asset_id).status_code == 400


class TestUndo:
    def test_deleting_a_split_restores_the_original_values(self, client, auth):
        purchase = buy(client, auth, quantity=100, price=10.0, date="2026-01-10")
        action = create_action(client, auth, purchase["asset_id"]).get_json()
        assert client.delete(f"/api/corporate-actions/{action['id']}", headers=auth).status_code == 200

        row = next(item for item in movements(client, auth) if item["id"] == purchase["id"])
        assert row["quantity"] == 100
        assert row["average_price"] == 10.0
        assert "corporate_adjustments" not in row["metadata"]

    def test_deleting_a_bonus_removes_its_shares(self, client, auth):
        purchase = buy(client, auth, quantity=100, price=10.0, date="2026-01-10")
        action = create_action(client, auth, purchase["asset_id"], action_type="BONUS", ratio_from=10, ratio_to=1).get_json()
        assert client.delete(f"/api/corporate-actions/{action['id']}", headers=auth).status_code == 200
        assert position(client, auth)["quantity"] == pytest.approx(100)

    def test_an_event_with_later_movements_cannot_be_undone(self, client, auth):
        purchase = buy(client, auth, quantity=100, price=10.0, date="2026-01-10")
        action = create_action(client, auth, purchase["asset_id"]).get_json()
        post_movement(client, auth, quantity=50, price=6.0, date="2026-03-01", sale=True)
        assert client.delete(f"/api/corporate-actions/{action['id']}", headers=auth).status_code == 409

    def test_only_the_latest_event_can_be_undone(self, client, auth):
        purchase = buy(client, auth, quantity=100, price=10.0, date="2026-01-10")
        first = create_action(client, auth, purchase["asset_id"]).get_json()
        second = create_action(client, auth, purchase["asset_id"], ex_date="2026-03-01").get_json()
        assert client.delete(f"/api/corporate-actions/{first['id']}", headers=auth).status_code == 409
        assert client.delete(f"/api/corporate-actions/{second['id']}", headers=auth).status_code == 200
        assert client.delete(f"/api/corporate-actions/{first['id']}", headers=auth).status_code == 200
        assert position(client, auth)["quantity"] == pytest.approx(100)


class TestIsolation:
    def test_another_users_asset_and_events_are_out_of_reach(self, client, user, other_user):
        purchase = buy(client, user["headers"], quantity=100, price=10.0, date="2026-01-10")
        assert create_action(client, other_user["headers"], purchase["asset_id"]).status_code == 400
        action = create_action(client, user["headers"], purchase["asset_id"]).get_json()
        assert client.get("/api/corporate-actions", headers=other_user["headers"]).get_json() == []
        assert client.delete(f"/api/corporate-actions/{action['id']}", headers=other_user["headers"]).status_code == 404
