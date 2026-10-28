"""Liquidacao na conta investimento (049): services/settlement.py + broker_cash.py.

O que estes testes fixam:

- o calendario: D+2 dias uteis para acoes/FIIs/ETFs na B3, sem fim de semana
  nem feriado nacional (Finados, Carnaval pela Pascoa); D+1 no exterior; renda
  fixa, Tesouro e cripto no dia;
- o lancamento ligado a operacao fica na data da liquidacao, com o valor
  liquidado (`settlement_amount`) quando informado; `settlement_date` manda e
  nunca vem antes da operacao;
- GET /api/investments/settlement: `settled` (o que ja liquidou ate hoje),
  `in_transit` (operacoes depois de hoje e proventos anunciados), `expected`;
  leva para a liquidacao o lancamento gravado ainda na data do pregao.
"""

import importlib
from datetime import date

import pytest

TODAY = date(2026, 10, 27)  # terca


@pytest.fixture(autouse=True)
def frozen(app_module, monkeypatch):
    invoices = importlib.import_module("services.invoices")
    monkeypatch.setattr(invoices, "local_today", lambda: TODAY)
    prices = importlib.import_module("services.prices")
    monkeypatch.setattr(prices, "download_close_prices", lambda symbols, **kwargs: {})


def corretora(client, auth, initial=10000.0):
    response = client.post(
        "/api/accounts", headers=auth,
        json={"name": "BTG investimentos", "type": "BROKERAGE", "initial_balance": initial},
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["id"]


def trade(client, auth, account_id, *, quantity=100, price=10.0, day="2026-10-26", ticker="PETR4",
          asset_class="STOCKS", **metadata):
    key = "purchase_date" if quantity > 0 else "sale_date"
    meta = {key: day, "cash_account_id": account_id, **metadata}
    if quantity < 0:
        meta.setdefault("sale_price", price)
    response = client.post("/api/investments", headers=auth, json={
        "asset_class": asset_class, "ticker_or_name": ticker, "quantity": quantity,
        "average_price": price, "current_price": price, "metadata": meta,
    })
    return response


def bought(client, auth, account_id, **kwargs):
    response = trade(client, auth, account_id, **kwargs)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()[0]


def cash_row(client, auth, investment_id):
    response = client.get("/api/transactions", headers=auth)
    [row] = [item for item in response.get_json() if item.get("source_id") == investment_id]
    return row


def settlement(client, auth):
    response = client.get("/api/investments/settlement", headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


@pytest.fixture()
def cal(app_module):
    return importlib.import_module("services.settlement")


class TestCalendar:
    def test_two_business_days_skip_the_weekend(self, cal):
        assert cal.add_business_days(date(2026, 10, 22), 2) == date(2026, 10, 26)  # quinta -> segunda

    def test_finados_is_not_a_settlement_day(self, cal):
        assert cal.add_business_days(date(2026, 10, 30), 2) == date(2026, 11, 4)  # sexta -> quarta

    def test_carnival_comes_from_easter(self, cal):
        assert cal.easter(2026) == date(2026, 4, 5)
        assert cal.add_business_days(date(2026, 2, 13), 1) == date(2026, 2, 18)  # sexta -> quarta de cinzas

    def test_days_by_class(self, cal):
        assert cal.settlement_days("STOCKS") == 2
        assert cal.settlement_days("REIT") == 2
        assert cal.settlement_days("STOCKS", "USD") == 1
        assert cal.settlement_days("FIXED_INCOME") == 0
        assert cal.settlement_days("OTHER") == 0

    def test_an_explicit_date_wins(self, cal):
        assert cal.settlement_date("2026-10-27", "STOCKS", metadata={"settlement_date": "2026-10-28"}) == "2026-10-28"
        assert cal.settlement_date("2026-10-27", "STOCKS") == "2026-10-29"


class TestTheLinkedRowSettles:
    def test_a_b3_buy_moves_the_cash_on_d_plus_2(self, client, auth):
        account = corretora(client, auth)
        investment = bought(client, auth, account, day="2026-10-26")
        row = cash_row(client, auth, investment["id"])
        assert (row["date"], row["amount"]) == ("2026-10-28", 1000.0)

    def test_fixed_income_moves_the_cash_the_same_day(self, client, auth):
        account = corretora(client, auth)
        investment = bought(
            client, auth, account, asset_class="FIXED_INCOME", ticker="CDB X", quantity=1, price=1000.0,
            day="2026-10-26",
        )
        assert cash_row(client, auth, investment["id"])["date"] == "2026-10-26"

    def test_the_settled_amount_carries_the_fees(self, client, auth):
        account = corretora(client, auth)
        investment = bought(client, auth, account, quantity=100, price=52.0, settlement_amount=5201.57)
        assert cash_row(client, auth, investment["id"])["amount"] == 5201.57

    def test_a_sale_settled_net_of_fees(self, client, auth):
        account = corretora(client, auth)
        bought(client, auth, account, day="2026-10-20")
        sale = trade(client, auth, account, quantity=-100, price=59.15, day="2026-10-27",
                     settlement_amount=5913.20, settlement_date="2026-10-29")
        assert sale.status_code == 201, sale.get_data(as_text=True)
        row = cash_row(client, auth, sale.get_json()[0]["id"])
        assert (row["type"], row["date"], row["amount"]) == ("INCOME", "2026-10-29", 5913.20)

    def test_settlement_before_the_trade_is_refused(self, client, auth):
        account = corretora(client, auth)
        response = trade(client, auth, account, day="2026-10-26", settlement_date="2026-10-25")
        assert response.status_code == 400

    def test_editing_the_settlement_moves_the_row(self, client, auth):
        account = corretora(client, auth)
        investment = bought(client, auth, account, day="2026-10-26")
        metadata = {**investment["metadata"], "settlement_date": "2026-10-27", "settlement_amount": 1000.05}
        response = client.patch(f"/api/investments/{investment['id']}", headers=auth, json={"metadata": metadata})
        assert response.status_code == 200, response.get_data(as_text=True)
        row = cash_row(client, auth, investment["id"])
        assert (row["date"], row["amount"]) == ("2026-10-27", 1000.05)


class TestTheSettlementView:
    def test_settled_in_transit_and_expected(self, client, auth):
        account = corretora(client, auth, initial=10000.0)
        bought(client, auth, account, day="2026-10-23")  # liquida 27/10 (hoje): ja saiu
        bought(client, auth, account, day="2026-10-26", ticker="VALE3", price=20.0)  # liquida 28/10
        view = settlement(client, auth)
        assert view["today"] == "2026-10-27"
        assert view["settled"] == 9000.0
        assert [(item["date"], item["amount"], item["kind"]) for item in view["in_transit"]] == [
            ("2026-10-28", -2000.0, "operation"),
        ]
        assert view["expected"] == 7000.0

    def test_an_announced_provento_is_in_transit(self, client, auth):
        account = corretora(client, auth, initial=0.0)
        investment = bought(client, auth, account, day="2026-10-01")
        response = client.post("/api/investment-proceeds", headers=auth, json={
            "asset_id": investment["asset_id"], "proceeds_type": "DIVIDEND",
            "record_date": "2026-10-27", "payment_date": "2026-11-10", "gross_amount": 17.05,
        })
        assert response.status_code == 201, response.get_data(as_text=True)
        view = settlement(client, auth)
        proceed = [item for item in view["in_transit"] if item["kind"] == "proceed"]
        assert [(item["date"], item["amount"]) for item in proceed] == [("2026-11-10", 17.05)]
        assert view["expected"] == pytest.approx(view["settled"] + 17.05)

    def test_a_row_still_on_the_trade_date_is_moved(self, client, auth, db_module, user):
        account = corretora(client, auth)
        investment = bought(client, auth, account, day="2026-10-26")
        with db_module.get_db() as conn:
            conn.execute(
                "UPDATE transactions SET date = '2026-10-26' WHERE source_id = ? AND user_id = ?",
                (investment["id"], user["id"]),
            )
        settlement(client, auth)
        assert cash_row(client, auth, investment["id"])["date"] == "2026-10-28"

    def test_without_a_corretora_there_is_no_view(self, client, auth):
        assert client.get("/api/investments/settlement", headers=auth).status_code == 404

    def test_another_users_trades_never_show(self, client, auth, other_user):
        account = corretora(client, auth)
        bought(client, auth, account, day="2026-10-26")
        corretora(client, other_user["headers"], initial=0.0)
        view = settlement(client, other_user["headers"])
        assert (view["settled"], view["in_transit"]) == (0.0, [])
