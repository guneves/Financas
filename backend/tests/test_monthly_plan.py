"""Plano do mes (025, 038): a renda, quanto dela investir e gastar, e os alertas.

O que estes testes fixam (os da 038 — renda, percentuais, Saldo do plano,
conversao — estao em test_monthly_plan_income.py):

- o gasto do mes soma saidas das contas e compras no cartao (inteiras, no mes
  da compra), e deixa de fora transferencia (o aporte digitado e uma, para a
  Corretora), pagamento de fatura, o caixa das operacoes e o provento pago;
  uma categoria chamada "Investimento" e uma categoria como outra (039);
- o aporte do mes e aportes - resgates das operacoes da carteira;
- um mes sem plano proprio herda o mais recente anterior; apagar o do mes volta
  a herdar;
- cada alerta: plano maior que a renda, gasto estourado / no ritmo de estourar
  / perto do limite / dentro do plano, aporte feito / pendente / que faltou, e
  meta com data coberta ou nao pelo aporte planejado;
- validacao, rounded_money() e nada de outro usuario.
"""

import importlib
from datetime import date

import pytest

TODAY = date(2025, 12, 15)


@pytest.fixture(autouse=True)
def frozen_today(app_module, monkeypatch):
    for name in ("services.monthly_plan", "services.goals"):
        monkeypatch.setattr(importlib.import_module(name), "local_today", lambda: TODAY)


def put_plan(client, auth, month, spend, invest, income=10000):
    """Plano em reais, para ler os testes: os % de `spend` e `invest` sobre `income`."""
    payload = {
        "month": month,
        "income_amount": income,
        "spend_percent": spend * 100 / income,
        "invest_percent": invest * 100 / income,
    }
    response = client.put("/api/monthly-plan", headers=auth, json=payload)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def get_plan(client, auth, month):
    response = client.get("/api/monthly-plan", headers=auth, query_string={"month": month})
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def add_entry(client, auth, amount, day, *, kind="EXPENSE", category="Mercado"):
    response = client.post("/api/transactions", headers=auth, json={
        "amount": amount, "date": day, "category": category, "type": kind, "description": "teste",
    })
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    return response.get_json()


def buy(client, auth, ticker, quantity, price, day):
    response = client.post("/api/investments", headers=auth, json={
        "asset_class": "STOCKS",
        "ticker_or_name": ticker,
        "quantity": quantity,
        "average_price": price,
        "current_price": price,
        "metadata": {"purchase_date": day},
    })
    assert response.status_code in (200, 201), response.get_data(as_text=True)


def codes(body):
    return [flag["code"] for flag in body["flags"]]


def flag(body, code):
    return next(item for item in body["flags"] if item["code"] == code)


# --- plano e heranca --------------------------------------------------------


def test_no_plan_returns_actuals_without_flags(client, auth):
    add_entry(client, auth, 100, "2025-12-02")
    body = get_plan(client, auth, "2025-12")
    assert body["plan"] is None
    assert body["flags"] == []
    assert body["actual"]["spent"] == 100
    assert body["period"] == "CURRENT"


def test_plan_carries_forward_until_changed(client, auth):
    put_plan(client, auth, "2025-10", 3000, 1000)
    november = get_plan(client, auth, "2025-11")
    assert november["plan"]["inherited"] is True
    assert november["plan"]["source_month"] == "2025-10"
    assert november["plan"]["spend_amount"] == 3000

    put_plan(client, auth, "2025-12", 2500, 1500)
    assert get_plan(client, auth, "2025-11")["plan"]["spend_amount"] == 3000
    december = get_plan(client, auth, "2025-12")
    assert december["plan"]["inherited"] is False
    assert december["plan"]["invest_amount"] == 1500
    # Antes do primeiro plano nao ha plano.
    assert get_plan(client, auth, "2025-09")["plan"] is None


def test_put_replaces_same_month_and_delete_falls_back(client, auth):
    put_plan(client, auth, "2025-11", 3000, 1000)
    put_plan(client, auth, "2025-12", 2000, 500)
    put_plan(client, auth, "2025-12", 2200, 600)
    assert get_plan(client, auth, "2025-12")["plan"]["spend_amount"] == 2200

    response = client.delete("/api/monthly-plan", headers=auth, query_string={"month": "2025-12"})
    assert response.status_code == 200
    assert response.get_json()["plan"]["source_month"] == "2025-11"
    again = client.delete("/api/monthly-plan", headers=auth, query_string={"month": "2025-12"})
    assert again.status_code == 404


def test_amounts_are_rounded_half_up(client, auth):
    # 100,005 de renda vira 100,01; 50% disso, 50,005, vira 50,01 (o banker's
    # rounding daria 50,00); 12,5% -> 12,50125 -> 12,50.
    response = client.put("/api/monthly-plan", headers=auth, json={
        "month": "2025-12", "income_amount": 100.005, "spend_percent": 50, "invest_percent": 12.5,
    })
    body = response.get_json()
    assert body["plan"]["income_amount"] == 100.01
    assert body["plan"]["spend_amount"] == 50.01
    assert body["plan"]["invest_amount"] == 12.5
    # Sem destino fecha a renda ao centavo: 100,01 - 50,01 - 12,50.
    assert body["plan"]["unallocated_amount"] == 37.5


@pytest.mark.parametrize("payload", [
    {"month": "2025-12", "income_amount": 1000, "spend_percent": -1, "invest_percent": 0},
    {"month": "2025-12", "income_amount": 1000, "spend_percent": 10, "invest_percent": "x"},
    {"month": "2025-12", "income_amount": 1000, "spend_percent": 10},
    {"month": "2025-12", "income_amount": 1000, "spend_percent": 101, "invest_percent": 0},
    {"month": "2025-12", "income_amount": 1000, "spend_percent": 60, "invest_percent": 40.01},
    {"month": "12/2025", "income_amount": 1000, "spend_percent": 10, "invest_percent": 0},
    {"income_amount": 1000, "spend_percent": 10, "invest_percent": 0},
    # Sem renda nao ha plano.
    {"month": "2025-12", "spend_percent": 10, "invest_percent": 0},
    {"month": "2025-12", "income_amount": 0, "spend_percent": 10, "invest_percent": 0},
    {"month": "2025-12", "income_amount": -5, "spend_percent": 10, "invest_percent": 0},
    {"month": "2025-12", "income_amount": 0.004, "spend_percent": 10, "invest_percent": 0},
    # O plano antigo, em reais, nao e mais aceito.
    {"month": "2025-12", "spend_amount": 3000, "invest_amount": 1000},
])
def test_invalid_payload_is_refused(client, auth, payload):
    response = client.put("/api/monthly-plan", headers=auth, json=payload)
    assert response.status_code == 400


# --- o que conta como gasto e aporte ----------------------------------------


def test_spending_excludes_transfers_investments_and_invoice_payments(client, auth):
    bank = client.post("/api/accounts", headers=auth, json={"name": "Banco", "type": "CHECKING"}).get_json()
    broker = client.post("/api/accounts", headers=auth, json={"name": "BTG", "type": "BROKERAGE"}).get_json()
    add_entry(client, auth, 300, "2025-12-03")
    add_entry(client, auth, 450, "2025-12-05", category="Pagamento Fatura Nubank")
    add_entry(client, auth, 5000, "2025-12-01", kind="INCOME", category="Salario")
    add_entry(client, auth, 999, "2025-11-30")  # outro mes
    for origin, target in ((bank, broker), (broker, bank)):  # aporte e resgate
        response = client.post("/api/transfers", headers=auth, json={
            "amount": 1000, "date": "2025-12-04",
            "account_id": origin["id"], "transfer_account_id": target["id"],
        })
        assert response.status_code == 201, response.get_data(as_text=True)
    body = get_plan(client, auth, "2025-12")
    assert body["actual"]["spent_accounts"] == 300
    assert body["actual"]["income"] == 5000


def test_a_category_named_investimento_is_just_a_category(client, auth):
    response = client.post("/api/categories", headers=auth, json={"name": "Investimento", "kind": "BOTH"})
    assert response.status_code == 201, response.get_data(as_text=True)
    add_entry(client, auth, 120, "2025-12-03", category="Investimento")
    body = get_plan(client, auth, "2025-12")
    assert body["actual"]["spent_accounts"] == 120


def test_card_purchase_counts_in_full_in_purchase_month(client, auth):
    response = client.post("/api/credit-cards", headers=auth, json={"name": "Cartao", "due_day": 12, "closing_day": 5})
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    card = response.get_json()
    card = card[0] if isinstance(card, list) else card
    response = client.post("/api/cc-expenses/purchases", headers=auth, json={
        "card_id": card["id"], "category": "Casa", "description": "Sofa",
        "total_amount": 900, "purchase_date": "2025-12-10", "installments": 3,
    })
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    body = get_plan(client, auth, "2025-12")
    assert body["actual"]["spent_cards"] == 900
    assert body["actual"]["spent"] == 900
    assert get_plan(client, auth, "2026-01")["actual"]["spent_cards"] == 0


def test_invested_is_net_of_redemptions(client, auth):
    buy(client, auth, "PETR4", 100, 30.0, "2025-12-02")   # 3.000
    buy(client, auth, "VALE3", 10, 50.0, "2025-11-20")    # outro mes
    response = client.post("/api/investments", headers=auth, json={
        "asset_class": "STOCKS", "ticker_or_name": "PETR4", "quantity": -20,
        "average_price": 35.0, "current_price": 35.0,
        "metadata": {"purchase_date": "2025-12-08"},
    })
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    body = get_plan(client, auth, "2025-12")
    assert body["actual"]["aportes"] == 3000
    assert body["actual"]["resgates"] == 700
    assert body["actual"]["invested"] == 2300


# --- alertas ----------------------------------------------------------------


def test_plan_leftover_is_what_has_no_destination(client, auth):
    ok = put_plan(client, auth, "2026-01", 3000, 1500, income=5000)
    assert ok["period"] == "FUTURE"
    assert "PLAN_OVER_INCOME" not in codes(ok)
    assert ok["plan"]["planned_leftover"] == 500
    assert ok["unallocated"] == {"percent": 10, "amount": 500}


def test_spend_over_flag(client, auth):
    put_plan(client, auth, "2025-12", 1000, 0)
    add_entry(client, auth, 1200.5, "2025-12-02")
    body = get_plan(client, auth, "2025-12")
    assert flag(body, "SPEND_OVER") == {"code": "SPEND_OVER", "tone": "loss", "amount": 200.5}
    assert body["progress"]["spend_remaining"] == -200.5


def test_spend_pace_flag_projects_month_end(client, auth):
    # Dia 15 de 31: 700 gastos de 1.000 -> projecao 700/15*31 = 1.446,67.
    put_plan(client, auth, "2025-12", 1000, 0)
    add_entry(client, auth, 700, "2025-12-10")
    body = get_plan(client, auth, "2025-12")
    pace = flag(body, "SPEND_PACE")
    assert pace["tone"] == "warning"
    assert pace["amount"] == 1446.67
    assert pace["over"] == 446.67


def test_spend_near_flag_when_on_pace_but_close(client, auth, monkeypatch):
    monkeypatch.setattr(importlib.import_module("services.monthly_plan"), "local_today", lambda: date(2025, 12, 29))
    put_plan(client, auth, "2025-12", 1000, 0)
    add_entry(client, auth, 850, "2025-12-10")
    body = get_plan(client, auth, "2025-12")
    assert "SPEND_PACE" not in codes(body)
    assert flag(body, "SPEND_NEAR")["amount"] == 150


def test_no_pace_flag_in_first_days(client, auth, monkeypatch):
    monkeypatch.setattr(importlib.import_module("services.monthly_plan"), "local_today", lambda: date(2025, 12, 3))
    put_plan(client, auth, "2025-12", 3000, 0)
    add_entry(client, auth, 1500, "2025-12-01")  # aluguel no dia 1
    assert codes(get_plan(client, auth, "2025-12")) == []


def test_past_month_kept_and_missed(client, auth):
    put_plan(client, auth, "2025-11", 2000, 1000)
    add_entry(client, auth, 1500, "2025-11-10")
    buy(client, auth, "PETR4", 10, 40.0, "2025-11-12")   # 400 de 1.000
    body = get_plan(client, auth, "2025-11")
    assert body["period"] == "PAST"
    assert flag(body, "SPEND_KEPT")["amount"] == 500
    assert flag(body, "INVEST_MISSED")["amount"] == 600
    assert not any(code.startswith("GOAL_") for code in codes(body))


def test_invest_pending_then_done(client, auth, monkeypatch):
    put_plan(client, auth, "2025-12", 2000, 1000)
    pending = flag(get_plan(client, auth, "2025-12"), "INVEST_PENDING")
    assert pending == {"code": "INVEST_PENDING", "tone": "info", "amount": 1000, "days_left": 16}

    monkeypatch.setattr(importlib.import_module("services.monthly_plan"), "local_today", lambda: date(2025, 12, 27))
    assert flag(get_plan(client, auth, "2025-12"), "INVEST_PENDING")["tone"] == "warning"

    buy(client, auth, "PETR4", 40, 25.0, "2025-12-20")
    done = get_plan(client, auth, "2025-12")
    assert flag(done, "INVEST_DONE")["amount"] == 1000
    assert done["progress"]["invest_percent"] == 100


def test_goal_with_date_checked_against_planned_investment(client, auth):
    # Meta de 12.000 na carteira para 2026-12 (12 meses), sem rentabilidade:
    # precisa de 1.000/mes.
    response = client.post("/api/goals", headers=auth, json={
        "name": "Reserva", "kind": "PORTFOLIO", "target_amount": 12000, "target_date": "2026-12-31",
    })
    assert response.status_code == 201, response.get_data(as_text=True)
    client.post("/api/goals", headers=auth, json={"name": "Sem data", "kind": "PORTFOLIO", "target_amount": 5000})

    short = put_plan(client, auth, "2025-12", 2000, 600)
    goal = flag(short, "GOAL_SHORT")
    assert goal["goal_name"] == "Reserva"
    assert goal["amount"] == 1000
    assert goal["missing"] == 400
    assert goal["target_month"] == "2026-12"
    assert [code for code in codes(short) if code.startswith("GOAL_")] == ["GOAL_SHORT"]

    covered = put_plan(client, auth, "2025-12", 2000, 1000)
    assert flag(covered, "GOAL_COVERED")["missing"] == 0


# --- isolamento -------------------------------------------------------------


def test_other_user_sees_nothing(client, auth, other_user):
    put_plan(client, auth, "2025-12", 2000, 1000)
    add_entry(client, auth, 300, "2025-12-02")
    other = other_user["headers"]
    response = client.get("/api/monthly-plan", headers=other, query_string={"month": "2025-12"})
    assert response.status_code == 200
    body = response.get_json()
    assert body["plan"] is None
    assert body["actual"]["spent"] == 0
    delete = client.delete("/api/monthly-plan", headers=other, query_string={"month": "2025-12"})
    assert delete.status_code == 404
    assert get_plan(client, auth, "2025-12")["plan"]["spend_amount"] == 2000
