"""Proventos pagos entram na conta da carteira (services/proceeds_cash.py).

O que estes testes fixam:

- um provento pago a partir do dia em que a conta virou Corretora vira uma
  receita nessa conta (valor liquido, data de pagamento, categoria
  "Investimento"), uma vez so, por mais leituras que haja;
- agendado nao entra ate o dia do pagamento; pago antes da conta virar a da
  carteira nao entra (ja esta no saldo inicial);
- o lancamento acompanha o provento: editar muda o valor, excluir tira;
- sem conta Corretora nada e gravado; o lancamento nao e editavel nem
  excluivel pelo extrato; nada de outro usuario.
"""

import importlib
from datetime import date, timedelta

import pytest

TODAY = date.today()


def days(offset):
    return (TODAY + timedelta(days=offset)).isoformat()


@pytest.fixture(autouse=True)
def offline(app_module, monkeypatch):
    prices = importlib.import_module("services.prices")
    monkeypatch.setattr(prices, "download_close_prices", lambda symbols, **kwargs: {})


@pytest.fixture()
def clock(app_module, monkeypatch):
    """Muda o "hoje" de services.invoices, que proceeds_cash le."""
    invoices = importlib.import_module("services.invoices")

    def set_today(offset):
        monkeypatch.setattr(invoices, "local_today", lambda: TODAY + timedelta(days=offset))

    return set_today


def create_account(client, auth, name, account_type):
    response = client.post("/api/accounts", headers=auth, json={"name": name, "type": account_type})
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def buy(client, auth, ticker="PETR4"):
    response = client.post(
        "/api/investments",
        headers=auth,
        json={
            "asset_class": "STOCKS",
            "ticker_or_name": ticker,
            "quantity": 100,
            "average_price": 10.0,
            "current_price": 10.0,
            # Fora do extrato: aqui so o provento importa.
            "metadata": {"purchase_date": days(-800), "cash_account_id": None},
        },
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()[0]["asset_id"]


def provento(client, auth, asset_id, paid_on, gross=50.0, kind="DIVIDEND"):
    response = client.post(
        "/api/investment-proceeds",
        headers=auth,
        json={
            "asset_id": asset_id,
            "proceeds_type": kind,
            "record_date": days(-700),
            "payment_date": paid_on,
            "gross_amount": gross,
        },
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def proceed_rows(client, auth):
    response = client.get("/api/transactions", headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    return [item for item in response.get_json() if item.get("source_type") == "INVESTMENT_PROCEED"]


def balance_of(client, auth, account_id):
    response = client.get("/api/accounts", headers=auth, query_string={"include_archived": 1})
    return next(item["balance"] for item in response.get_json() if item["id"] == account_id)


def test_a_paid_provento_is_income_in_the_portfolio_account(client, auth, clock):
    brokerage = create_account(client, auth, "BTG Corretora", "BROKERAGE")
    asset_id = buy(client, auth)
    clock(10)
    item = provento(client, auth, asset_id, days(5), gross=50.0)

    rows = proceed_rows(client, auth)
    assert len(rows) == 1
    row = rows[0]
    assert row["account_id"] == brokerage["id"]
    assert row["type"] == "INCOME"
    assert row["amount"] == pytest.approx(item["net_amount"])
    assert row["date"][:10] == days(5)
    assert row["category"] == "Investimento"
    assert row["source_id"] == item["id"]
    assert "PETR4" in row["description"]
    assert balance_of(client, auth, brokerage["id"]) == pytest.approx(50.0)
    # Ler de novo nao grava outra linha.
    assert len(proceed_rows(client, auth)) == 1


def test_a_scheduled_provento_waits_for_its_payment_day(client, auth, clock):
    brokerage = create_account(client, auth, "BTG Corretora", "BROKERAGE")
    asset_id = buy(client, auth)
    provento(client, auth, asset_id, days(5))
    assert proceed_rows(client, auth) == []
    assert balance_of(client, auth, brokerage["id"]) == pytest.approx(0.0)

    clock(5)
    assert len(proceed_rows(client, auth)) == 1


def test_proventos_paid_before_the_account_was_the_portfolios_stay_out(client, auth):
    create_account(client, auth, "BTG Corretora", "BROKERAGE")
    asset_id = buy(client, auth)
    provento(client, auth, asset_id, days(-30))
    assert proceed_rows(client, auth) == []


def test_linking_an_account_counts_from_that_day(client, auth, clock):
    banking = create_account(client, auth, "BTG Banking", "CHECKING")
    asset_id = buy(client, auth)
    clock(20)
    provento(client, auth, asset_id, days(10), gross=10.0)
    assert proceed_rows(client, auth) == []  # sem conta da carteira

    response = client.patch(f"/api/accounts/{banking['id']}", headers=auth, json={"type": "BROKERAGE"})
    assert response.status_code == 200, response.get_data(as_text=True)
    assert response.get_json()["metadata"]["portfolio_since"] == days(20)
    provento(client, auth, asset_id, days(20), gross=30.0)

    rows = proceed_rows(client, auth)
    assert [row["amount"] for row in rows] == [pytest.approx(30.0)]
    assert rows[0]["account_id"] == banking["id"]


def test_the_lancamento_follows_its_provento(client, auth, clock):
    create_account(client, auth, "BTG Corretora", "BROKERAGE")
    asset_id = buy(client, auth)
    clock(10)
    item = provento(client, auth, asset_id, days(5), gross=50.0)
    assert proceed_rows(client, auth)[0]["amount"] == pytest.approx(50.0)

    response = client.patch(
        f"/api/investment-proceeds/{item['id']}", headers=auth, json={"gross_amount": 80.0},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    assert proceed_rows(client, auth)[0]["amount"] == pytest.approx(80.0)

    # De volta ao futuro: agendado de novo, sai do saldo.
    response = client.patch(
        f"/api/investment-proceeds/{item['id']}", headers=auth, json={"payment_date": days(30)},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    assert proceed_rows(client, auth) == []

    clock(30)
    assert len(proceed_rows(client, auth)) == 1
    assert client.delete(f"/api/investment-proceeds/{item['id']}", headers=auth).status_code == 200
    assert proceed_rows(client, auth) == []


def test_without_a_brokerage_nothing_is_written(client, auth, clock):
    asset_id = buy(client, auth)
    clock(10)
    provento(client, auth, asset_id, days(5))
    assert proceed_rows(client, auth) == []


def test_the_lancamento_is_not_edited_or_deleted_from_the_statement(client, auth, clock):
    create_account(client, auth, "BTG Corretora", "BROKERAGE")
    asset_id = buy(client, auth)
    clock(10)
    provento(client, auth, asset_id, days(5))
    row = proceed_rows(client, auth)[0]

    response = client.patch(f"/api/transactions/{row['id']}", headers=auth, json={"amount": 1})
    assert response.status_code == 409
    assert "Proventos" in response.get_json()["error"]
    assert client.delete(f"/api/transactions/{row['id']}", headers=auth).status_code == 409
    assert proceed_rows(client, auth)[0]["amount"] == pytest.approx(row["amount"])


def test_another_users_brokerage_never_receives_it(client, auth, other_user, clock):
    create_account(client, other_user["headers"], "Corretora dele", "BROKERAGE")
    asset_id = buy(client, auth)
    clock(10)
    provento(client, auth, asset_id, days(5))
    assert proceed_rows(client, auth) == []
    assert proceed_rows(client, other_user["headers"]) == []


def test_import_rules_never_recategorize_a_paid_provento(client, auth, clock):
    """Recategorizado, o provento saia de "Investimento" e o plano do mes o
    contava como receita (revisao de 2026-10-18)."""
    create_account(client, auth, "BTG Corretora", "BROKERAGE")
    asset_id = buy(client, auth)
    clock(10)
    provento(client, auth, asset_id, days(5))
    [row] = proceed_rows(client, auth)
    rule = client.post("/api/import-rules", headers=auth, json={"pattern": "petr4", "category": "Receita"})
    assert rule.status_code == 201, rule.get_data(as_text=True)

    preview = client.post("/api/import-rules/apply/preview", headers=auth, json={}).get_json()
    assert row["id"] not in [item["id"] for item in preview["items"]]
    applied = client.post("/api/import-rules/apply", headers=auth, json={"transaction_ids": [row["id"]]})
    assert applied.status_code in (200, 400)
    assert proceed_rows(client, auth)[0]["category"] == "Investimento"
