"""Juros (cupom) e amortizacao de renda fixa, registrados a mao (040).

Owner, 2026-10-19: nenhuma fonte traz o cupom de uma debenture, CRI/CRA ou do
Tesouro com juros semestrais, entao os pagamentos futuros sao digitados em
Proventos e entram na conta da carteira no dia do pagamento. O que fica fixo:

- o tipo INTEREST existe (a tabela foi refeita) e nao pede data com: sem ela,
  vale a data de pagamento — o mesmo para a amortizacao;
- o IR padrao do cupom e a tabela regressiva desde a aplicacao (Lei
  11.033/2004, art. 1o), zero no titulo isento; cupom fora da renda fixa e
  recusado (test_asset_categories.py);
- "repetir" grava todos os pagamentos de uma vez (ou nenhum), cada um com a
  aliquota da propria data, no mesmo dia do mes (ou no ultimo do mes curto);
- pago, entra na conta da carteira como "Juros"; agendado, espera o dia;
- no relatorio de IR, cupom com IR e tributacao exclusiva (06), sem IR e
  isento (12); a amortizacao devolve capital e fica de fora.
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


def create_title(client, auth, *, name="DEBENTURE X", kind="DEBENTURE", purchase_date="2025-01-02", price=1000):
    response = client.post(
        "/api/investments",
        json=[{
            "asset_class": "FIXED_INCOME",
            "ticker_or_name": name,
            "quantity": 1,
            "average_price": price,
            "current_price": price,
            "metadata": {
                "fixed_income_type": kind,
                "rate_type": "PRE",
                "annual_rate": 12,
                "purchase_date": purchase_date,
                "cash_account_id": None,
            },
        }],
        headers=auth,
    )
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    return response.get_json()[0]["asset_id"]


def post_proceed(client, auth, **fields):
    return client.post("/api/investment-proceeds", headers=auth, json=fields)


def interest(client, auth, asset_id, payment_date, gross=100.0, **fields):
    response = post_proceed(
        client, auth,
        asset_id=asset_id, proceeds_type="INTEREST", payment_date=payment_date, gross_amount=gross,
        **fields,
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()


def all_proceeds(client, auth):
    response = client.get("/api/investment-proceeds?status=ALL&date_from=2000-01-01&date_to=2100-12-31", headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


class TestTheInterestType:
    def test_a_coupon_is_accepted_without_a_record_date(self, client, auth):
        asset_id = create_title(client, auth)
        item = interest(client, auth, asset_id, "2025-07-15")
        assert item["proceeds_type"] == "INTEREST"
        assert item["record_date"] == "2025-07-15"
        assert item["payment_date"] == "2025-07-15"
        assert item["gross_amount"] == 100.0

    def test_an_amortization_also_takes_the_payment_date(self, client, auth):
        asset_id = create_title(client, auth)
        response = post_proceed(
            client, auth,
            asset_id=asset_id, proceeds_type="AMORTIZATION", payment_date="2025-07-15", gross_amount=250,
        )
        assert response.status_code == 201, response.get_data(as_text=True)
        item = response.get_json()
        assert item["record_date"] == "2025-07-15"
        assert item["tax_amount"] == 0

    def test_a_dividend_still_needs_its_record_date(self, client, auth):
        asset_id = create_title(client, auth)
        response = post_proceed(
            client, auth,
            asset_id=asset_id, proceeds_type="DIVIDEND", payment_date="2025-07-15", gross_amount=10,
        )
        assert response.status_code == 400

    def test_the_type_survives_the_filter(self, client, auth):
        asset_id = create_title(client, auth)
        interest(client, auth, asset_id, "2025-07-15")
        response = client.get(
            "/api/investment-proceeds?proceeds_type=INTEREST&date_from=2025-01-01&date_to=2025-12-31",
            headers=auth,
        )
        assert response.status_code == 200
        assert [item["proceeds_type"] for item in response.get_json()] == ["INTEREST"]


class TestTheCouponTax:
    @pytest.mark.parametrize("payment_date, rate", [
        ("2025-06-01", 0.225),   # 150 dias
        ("2025-12-01", 0.200),   # 333 dias
        ("2026-06-01", 0.175),   # 515 dias
        ("2027-06-01", 0.150),   # mais de 720 dias
    ])
    def test_the_regressive_table_counts_from_the_purchase(self, client, auth, payment_date, rate):
        asset_id = create_title(client, auth, purchase_date="2025-01-02")
        item = interest(client, auth, asset_id, payment_date, gross=200.0)
        assert item["tax_amount"] == pytest.approx(200.0 * rate)
        assert item["net_amount"] == pytest.approx(200.0 * (1 - rate))

    def test_a_tax_free_title_withholds_nothing(self, client, auth):
        asset_id = create_title(client, auth, name="CRA Y", kind="CRA")
        item = interest(client, auth, asset_id, "2025-06-01", gross=200.0)
        assert item["tax_amount"] == 0
        assert item["net_amount"] == 200.0

    def test_a_typed_tax_wins(self, client, auth):
        asset_id = create_title(client, auth)
        item = interest(client, auth, asset_id, "2025-06-01", gross=200.0, tax_amount=10)
        assert item["tax_amount"] == 10.0

    def test_moving_the_payment_recomputes_the_rate(self, client, auth):
        asset_id = create_title(client, auth, purchase_date="2025-01-02")
        item = interest(client, auth, asset_id, "2025-06-01", gross=200.0)
        response = client.patch(
            f"/api/investment-proceeds/{item['id']}", headers=auth,
            json={"payment_date": "2027-06-01", "record_date": "2027-06-01"},
        )
        assert response.status_code == 200, response.get_data(as_text=True)
        assert response.get_json()["tax_amount"] == pytest.approx(30.0)

    def test_interest_on_a_stock_is_refused(self, client, auth):
        # Cupom e de renda fixa (owner, 2026-10-19: so os ativos que podem ter
        # aquele provento); antes passava com IR 0.
        response = client.post(
            "/api/investments", headers=auth,
            json={
                "asset_class": "STOCKS", "ticker_or_name": "PETR4", "quantity": 10,
                "average_price": 10, "current_price": 10,
                "metadata": {"purchase_date": "2025-01-02", "cash_account_id": None},
            },
        )
        assert response.status_code == 201, response.get_data(as_text=True)
        asset_id = response.get_json()[0]["asset_id"]
        refused = post_proceed(
            client, auth,
            asset_id=asset_id, proceeds_type="INTEREST", payment_date="2025-06-01", gross_amount=50.0,
        )
        assert refused.status_code == 400
        assert "renda fixa" in refused.get_json()["error"]


class TestRepeatingPayments:
    def test_semiannual_coupons_until_maturity(self, client, auth):
        asset_id = create_title(client, auth, purchase_date="2025-01-02")
        response = post_proceed(
            client, auth,
            asset_id=asset_id, proceeds_type="INTEREST", payment_date="2025-07-15", gross_amount=60,
            repeat={"every_months": 6, "count": 4},
        )
        assert response.status_code == 201, response.get_data(as_text=True)
        items = response.get_json()
        assert [item["payment_date"] for item in items] == ["2025-07-15", "2026-01-15", "2026-07-15", "2027-01-15"]
        assert [item["record_date"] for item in items] == ["2025-07-15", "2026-01-15", "2026-07-15", "2027-01-15"]
        # Cada pagamento com a aliquota da propria data: 194, 378, 559 e 743 dias.
        assert [item["tax_amount"] for item in items] == pytest.approx([12.0, 10.5, 10.5, 9.0])
        assert len(all_proceeds(client, auth)) == 4

    def test_the_day_is_kept_and_clamped_in_short_months(self, client, auth):
        asset_id = create_title(client, auth)
        response = post_proceed(
            client, auth,
            asset_id=asset_id, proceeds_type="AMORTIZATION", payment_date="2025-01-31", gross_amount=100,
            repeat={"every_months": 1, "count": 3},
        )
        assert response.status_code == 201, response.get_data(as_text=True)
        assert [item["payment_date"] for item in response.get_json()] == ["2025-01-31", "2025-02-28", "2025-03-31"]

    @pytest.mark.parametrize("repeat", [
        {"every_months": 5, "count": 3},
        {"every_months": 6, "count": 0},
        {"every_months": 6, "count": 500},
        {"every_months": "x", "count": 2},
        "semestral",
    ])
    def test_an_invalid_repeat_writes_nothing(self, client, auth, repeat):
        asset_id = create_title(client, auth)
        response = post_proceed(
            client, auth,
            asset_id=asset_id, proceeds_type="INTEREST", payment_date="2025-07-15", gross_amount=60,
            repeat=repeat,
        )
        assert response.status_code == 400, response.get_data(as_text=True)
        assert all_proceeds(client, auth) == []

    def test_one_bad_payment_writes_none_of_them(self, client, auth):
        # Tributo maior que o bruto: recusado na primeira linha, nada fica.
        asset_id = create_title(client, auth)
        response = post_proceed(
            client, auth,
            asset_id=asset_id, proceeds_type="INTEREST", payment_date="2025-07-15", gross_amount=60,
            tax_amount=100, repeat={"every_months": 6, "count": 3},
        )
        assert response.status_code == 400
        assert all_proceeds(client, auth) == []

    def test_without_repeat_the_answer_is_still_one_item(self, client, auth):
        asset_id = create_title(client, auth)
        item = interest(client, auth, asset_id, "2025-07-15")
        assert isinstance(item, dict)


class TestTheCouponReachesTheAccount:
    def test_paid_lands_in_the_portfolio_account_and_scheduled_waits(self, client, auth):
        response = client.post("/api/accounts", headers=auth, json={"name": "BTG Corretora", "type": "BROKERAGE"})
        assert response.status_code == 201, response.get_data(as_text=True)
        brokerage = response.get_json()
        asset_id = create_title(client, auth, kind="CRA", purchase_date=days(-400))
        paid = interest(client, auth, asset_id, days(0), gross=80.0)
        interest(client, auth, asset_id, days(30), gross=80.0)

        rows = [
            item for item in client.get("/api/transactions", headers=auth).get_json()
            if item.get("source_type") == "INVESTMENT_PROCEED"
        ]
        assert len(rows) == 1
        assert rows[0]["account_id"] == brokerage["id"]
        assert rows[0]["source_id"] == paid["id"]
        assert rows[0]["amount"] == pytest.approx(80.0)
        assert rows[0]["description"].startswith("Juros")


class TestTheTaxReport:
    def test_taxed_coupons_are_exclusive_tax_free_ones_exempt_amortization_out(self, client, auth):
        taxed = create_title(client, auth, name="DEBENTURE X", kind="DEBENTURE", purchase_date="2024-01-02")
        free = create_title(client, auth, name="CRA Y", kind="CRA", purchase_date="2024-01-02")
        interest(client, auth, taxed, "2025-03-10", gross=100.0)
        interest(client, auth, free, "2025-03-10", gross=40.0)
        response = post_proceed(
            client, auth, asset_id=taxed, proceeds_type="AMORTIZATION", payment_date="2025-03-10", gross_amount=500,
        )
        assert response.status_code == 201

        report = client.get("/api/tax-report?year=2025", headers=auth).get_json()
        exclusive = {item["line"]: item for item in report["tributacao_exclusiva"]}
        exempt = {item["line"]: item["amount"] for item in report["rendimentos_isentos"]}
        line_06 = exclusive["06 - Rendimentos de aplicações financeiras"]
        assert line_06["gross"] == pytest.approx(100.0)
        assert line_06["withheld"] == pytest.approx(17.5)  # 433 dias
        # Declarado liquido: o servidor manda o `net` (a tela nao subtrai mais).
        assert line_06["net"] == 82.5
        assert exempt["12 - Rendimentos de LCI, LCA, CRI e CRA"] == pytest.approx(40.0)
        assert [item["type"] for item in report["proventos"]] == ["INTEREST", "INTEREST"]


def test_migration_040_keeps_the_existing_proceeds(db_module):
    # A tabela refeita guarda as colunas de 026 e os indices.
    with db_module.get_db() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(investment_proceeds)")}
        indexes = {row["name"] for row in conn.execute("PRAGMA index_list(investment_proceeds)")}
    assert {"sync_key", "sync_locked", "metadata", "net_amount"} <= columns
    assert {
        "idx_investment_proceeds_user_payment",
        "idx_investment_proceeds_asset_payment",
        "idx_investment_proceeds_user_type_payment",
        "idx_investment_proceeds_user_sync_key",
    } <= indexes
