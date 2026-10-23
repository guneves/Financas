"""Metas financeiras (021): valor atual, progresso e previsao.

O que estes testes fixam:

- o valor atual de cada tipo: carteira (liquido), patrimonio (carteira +
  contas), classe de ativo, e renda mensal (proventos liquidos de 12 meses / 12);
- a previsao em meses com aporte mensal, com e sem rentabilidade esperada;
  sem aporte e sem rentabilidade nao ha previsao;
- com data desejada: o aporte mensal necessario e se o plano chega a tempo;
- validacao (classe obrigatoria so para ASSET_CLASS, valor > 0, data futura);
- dinheiro por rounded_money(), e nada de outro usuario.
"""

import importlib
from datetime import date

import pytest


@pytest.fixture(autouse=True)
def frozen_today(app_module, monkeypatch):
    goals = importlib.import_module("services.goals")
    monkeypatch.setattr(goals, "local_today", lambda: date(2025, 12, 15))


def buy(client, auth, ticker, quantity, price, *, asset_class="STOCKS"):
    response = client.post("/api/investments", headers=auth, json={
        "asset_class": asset_class,
        "ticker_or_name": ticker,
        "quantity": quantity,
        "average_price": price,
        "current_price": price,
        "metadata": {"purchase_date": "2025-01-10"},
    })
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    body = response.get_json()
    return body[0] if isinstance(body, list) else body


def create_goal(client, auth, **payload):
    payload.setdefault("name", "Meta")
    payload.setdefault("kind", "PORTFOLIO")
    return client.post("/api/goals", headers=auth, json=payload)


def created(response):
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def test_portfolio_goal_progress(client, auth):
    buy(client, auth, "PETR4", 100, 25.0)   # 2.500
    goal = created(create_goal(client, auth, target_amount=10000, monthly_contribution=1000))
    assert goal["current"] == 2500
    assert goal["remaining"] == 7500
    assert goal["percent"] == 25
    assert goal["reached"] is False
    # 2.500 + 8 x 1.000 = 10.500: oito meses, sem rentabilidade.
    assert goal["estimated_months"] == 8
    assert goal["estimated_month"] == "2026-08"


def test_expected_return_shortens_the_estimate(client, auth):
    buy(client, auth, "PETR4", 1000, 100.0)   # 100.000
    plain = created(create_goal(client, auth, target_amount=500000, monthly_contribution=2000))
    grown = created(create_goal(client, auth, target_amount=500000, monthly_contribution=2000, annual_return_percent=10))
    assert plain["estimated_months"] == 200
    assert grown["estimated_months"] < 120


def test_no_contribution_and_no_return_has_no_estimate(client, auth):
    goal = created(create_goal(client, auth, target_amount=1000))
    assert goal["estimated_months"] is None and goal["estimated_month"] is None


def test_a_reached_goal_is_zero_months_away(client, auth):
    buy(client, auth, "PETR4", 100, 25.0)
    goal = created(create_goal(client, auth, target_amount=2000))
    assert goal["reached"] is True and goal["estimated_months"] == 0 and goal["remaining"] == 0


def test_net_worth_adds_the_accounts(client, auth):
    buy(client, auth, "PETR4", 100, 25.0)
    response = client.post("/api/accounts", headers=auth, json={"name": "Reserva", "type": "SAVINGS", "initial_balance": 1500})
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    goal = created(create_goal(client, auth, kind="NET_WORTH", target_amount=10000))
    # A compra saiu da conta padrao (vinculo investimento <-> caixa), entao
    # o patrimonio e a carteira mais o saldo de todas as contas.
    accounts = client.get("/api/accounts?include_archived=1", headers=auth).get_json()
    cash = sum(item["balance_brl"] for item in accounts)
    assert goal["current"] == pytest.approx(2500 + cash)


def test_asset_class_goal_counts_only_that_class(client, auth):
    buy(client, auth, "PETR4", 100, 25.0)
    buy(client, auth, "MXRF11", 100, 10.0, asset_class="REIT")
    goal = created(create_goal(client, auth, kind="ASSET_CLASS", asset_class="REIT", target_amount=5000))
    assert goal["current"] == 1000
    assert goal["asset_class_label"] == "Fundos Imobiliarios"


def test_monthly_income_is_twelve_months_of_net_proceeds_over_twelve(client, auth):
    stock = buy(client, auth, "PETR4", 100, 25.0)
    for record, payment, gross in (("2025-03-01", "2025-03-20", 60.0), ("2025-09-01", "2025-09-20", 60.0),
                                   ("2024-11-01", "2024-11-20", 999.0)):
        response = client.post("/api/investment-proceeds", headers=auth, json={
            "asset_id": stock["asset_id"], "proceeds_type": "DIVIDEND",
            "record_date": record, "payment_date": payment, "gross_amount": gross,
        })
        # O de 2024 e anterior a compra: recusado, e de qualquer forma fora da janela.
        if record.startswith("2024"):
            continue
        assert response.status_code == 201, response.get_data(as_text=True)
    goal = created(create_goal(client, auth, kind="MONTHLY_INCOME", target_amount=500, monthly_contribution=1000))
    assert goal["current"] == 10   # 120 / 12
    assert goal["income_last_12_months"] == 120
    assert goal["percent"] == 2
    assert goal["estimated_months"] is None   # renda nao tem previsao por aporte


def test_target_date_gives_the_required_contribution(client, auth):
    goal = created(create_goal(client, auth, target_amount=12000, target_date="2026-12-01", monthly_contribution=500))
    # 12 meses de dez/25 a dez/26, sem rentabilidade: 1.000 por mes.
    assert goal["required_contribution"] == 1000
    assert goal["on_track"] is False
    fast = created(create_goal(client, auth, target_amount=12000, target_date="2026-12-01", monthly_contribution=1500))
    assert fast["on_track"] is True


def test_required_contribution_is_money_rounded(client, auth):
    goal = created(create_goal(client, auth, target_amount=1000, target_date="2026-03-01"))
    # 1.000 / 3 = 333,333... -> 333,33 (ROUND_HALF_UP no centavo)
    assert goal["required_contribution"] == 333.33


def test_validation(client, auth):
    assert create_goal(client, auth, target_amount=0).status_code == 400
    assert create_goal(client, auth, kind="ASSET_CLASS", target_amount=100).status_code == 400
    assert create_goal(client, auth, kind="WHATEVER", target_amount=100).status_code == 400
    assert create_goal(client, auth, target_amount=100, target_date="2025-12-20").status_code == 400
    assert create_goal(client, auth, target_amount=100, annual_return_percent=500).status_code == 400
    # classe mandada numa meta de carteira e ignorada, nao gravada
    goal = created(create_goal(client, auth, target_amount=100, asset_class="STOCKS"))
    assert goal["asset_class"] is None


def test_edit_and_delete(client, auth):
    goal = created(create_goal(client, auth, target_amount=1000))
    response = client.patch(f"/api/goals/{goal['id']}", headers=auth, json={"target_amount": 2000, "name": "Reserva"})
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()["target_amount"] == 2000
    assert response.get_json()["name"] == "Reserva"
    assert client.delete(f"/api/goals/{goal['id']}", headers=auth).get_json() == {"deleted": True}
    assert client.get(f"/api/goals/{goal['id']}", headers=auth).status_code == 404


def test_another_user_cannot_see_or_touch_a_goal(client, auth, other_user):
    goal = created(create_goal(client, auth, target_amount=1000))
    stranger = other_user["headers"]
    assert client.get("/api/goals", headers=stranger).get_json() == []
    assert client.get(f"/api/goals/{goal['id']}", headers=stranger).status_code == 404
    assert client.patch(f"/api/goals/{goal['id']}", headers=stranger, json={"target_amount": 1}).status_code == 404
    assert client.delete(f"/api/goals/{goal['id']}", headers=stranger).status_code == 404
    assert client.get(f"/api/goals/{goal['id']}", headers=auth).status_code == 200


def test_an_edit_keeps_a_target_date_that_has_since_arrived(client, auth, monkeypatch):
    goal = created(create_goal(client, auth, target_amount=1000, target_date="2026-03-01"))
    goals = importlib.import_module("services.goals")
    monkeypatch.setattr(goals, "local_today", lambda: date(2026, 3, 10))
    # A tela manda a data guardada de volta: renomear nao pode ser recusado.
    response = client.patch(f"/api/goals/{goal['id']}", headers=auth,
                            json={"name": "Reserva", "target_date": "2026-03-01"})
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()["name"] == "Reserva"
    omitted = client.patch(f"/api/goals/{goal['id']}", headers=auth, json={"target_amount": 2000})
    assert omitted.status_code == 200, omitted.get_data(as_text=True)
    # Uma data nova continua tendo de ser futura.
    moved = client.patch(f"/api/goals/{goal['id']}", headers=auth, json={"target_date": "2026-02-01"})
    assert moved.status_code == 400
