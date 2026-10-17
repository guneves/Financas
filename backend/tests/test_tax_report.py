"""Relatorio anual de IR (Fase 6): regras de apuracao.

O que estes testes fixam:

- acoes: venda de ate R$ 20 mil no mes e isenta (e o ganho isento nao consome
  prejuizo); acima disso, 15% sobre o ganho menos o prejuizo acumulado;
- FII: 20%, sem isencao, com prejuizo proprio;
- DARF abaixo de R$ 10 acumula para o mes seguinte;
- Bens e Direitos: custo medio em 31/12 do ano e do ano anterior, com codigo;
- dividendos isentos, JCP em tributacao exclusiva com o IR retido;
- exterior: 15% sobre o resultado do ano;
- a exportacao sai com uma aba por secao, e nada de outro usuario entra.
"""

import importlib
import io
import zipfile
from datetime import datetime, timedelta

import pytest


@pytest.fixture(autouse=True)
def offline(app_module, monkeypatch):
    fx = importlib.import_module("services.fx")
    fx.reset_fetch_throttle()

    def ptax(series, start, end):
        rows, day = [], start.date()
        while day <= end.date():
            if day.weekday() < 5:
                rows.append({"data": day.strftime("%d/%m/%Y"), "valor": "5.0000"})
            day += timedelta(days=1)
        return rows

    monkeypatch.setattr(fx, "fetch_bcb_window", ptax)


def trade(client, auth, ticker, quantity, price, date, *, asset_class="STOCKS", currency=None):
    sale = quantity < 0
    payload = {
        "asset_class": asset_class,
        "ticker_or_name": ticker,
        "quantity": quantity,
        "average_price": price,
        "current_price": price,
        "metadata": {"sale_date": date, "sale_price": price} if sale else {"purchase_date": date},
    }
    if currency:
        payload["currency"] = currency
    response = client.post("/api/investments", headers=auth, json=payload)
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    body = response.get_json()
    return body[0] if isinstance(body, list) else body


def report(client, auth, year=2025):
    response = client.get(f"/api/tax-report?year={year}", headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def month(body, key):
    return next(item for item in body["renda_variavel"]["months"] if item["month"] == key)


def test_stock_sales_up_to_20k_are_exempt_and_above_pay_15(client, auth):
    trade(client, auth, "PETR4", 1000, 10.0, "2025-01-10")
    trade(client, auth, "PETR4", -500, 12.0, "2025-02-10")   # vendas 6.000, ganho 1.000
    trade(client, auth, "PETR4", -500, 50.0, "2025-03-10")   # vendas 25.000, ganho 20.000
    body = report(client, auth)

    feb, mar = month(body, "2025-02"), month(body, "2025-03")
    assert feb["stocks"]["exempt"] is True and feb["stocks"]["exempt_gain"] == 1000
    assert feb["darf"] == 0
    assert mar["stocks"]["taxable"] == 20000
    assert mar["stocks"]["tax"] == 3000
    assert mar["darf"] == 3000
    exempt_line = next(item for item in body["rendimentos_isentos"] if item["line"].startswith("20"))
    assert exempt_line["amount"] == 1000


def test_losses_offset_later_taxable_gains(client, auth):
    trade(client, auth, "VALE3", 1000, 30.0, "2025-04-10")
    trade(client, auth, "VALE3", -1000, 20.0, "2025-05-10")  # vendas 20.000, prejuizo 10.000
    trade(client, auth, "VALE3", 1000, 20.0, "2025-06-10")
    trade(client, auth, "VALE3", -1000, 35.0, "2025-07-10")  # vendas 35.000, ganho 15.000
    body = report(client, auth)

    assert month(body, "2025-05")["stocks"]["loss_balance"] == 10000
    july = month(body, "2025-07")["stocks"]
    assert july["loss_used"] == 10000
    assert july["taxable"] == 5000
    assert july["tax"] == 750


def test_an_exempt_gain_does_not_consume_the_loss(client, auth):
    trade(client, auth, "ITUB4", 1000, 30.0, "2025-04-10")
    trade(client, auth, "ITUB4", -1000, 20.0, "2025-05-10")  # prejuizo 10.000
    trade(client, auth, "ITUB4", 100, 20.0, "2025-06-10")
    trade(client, auth, "ITUB4", -100, 30.0, "2025-07-10")   # vendas 3.000, ganho isento 1.000
    body = report(client, auth)
    assert month(body, "2025-07")["stocks"]["loss_balance"] == 10000


def test_reits_pay_20_with_no_exemption(client, auth):
    trade(client, auth, "HGLG11", 100, 100.0, "2025-01-10", asset_class="REIT")
    trade(client, auth, "HGLG11", -100, 110.0, "2025-02-10", asset_class="REIT")
    feb = month(report(client, auth), "2025-02")
    assert feb["reits"]["taxable"] == 1000
    assert feb["reits"]["tax"] == 200


def test_small_darf_rolls_to_the_next_month(client, auth):
    trade(client, auth, "HGLG11", 10, 100.0, "2025-01-10", asset_class="REIT")
    trade(client, auth, "HGLG11", -5, 104.0, "2025-02-10", asset_class="REIT")  # ganho 20, IR 4
    trade(client, auth, "HGLG11", -5, 106.0, "2025-03-10", asset_class="REIT")  # ganho 30, IR 6
    body = report(client, auth)
    assert month(body, "2025-02")["darf"] == 0
    assert month(body, "2025-02")["darf_carried"] == 4
    assert month(body, "2025-03")["darf"] == 10


def test_bens_e_direitos_uses_the_average_cost_at_year_end(client, auth):
    trade(client, auth, "PETR4", 100, 10.0, "2024-06-10")
    trade(client, auth, "PETR4", 100, 20.0, "2025-03-10")
    trade(client, auth, "PETR4", -150, 30.0, "2025-08-10")   # custo medio 15: ficam 50 a 15
    trade(client, auth, "HGLG11", 10, 100.0, "2025-01-10", asset_class="REIT")
    body = report(client, auth)

    petr = next(item for item in body["bens_e_direitos"] if item["ticker"] == "PETR4")
    assert (petr["group"], petr["code"]) == ("03", "01")
    assert petr["quantity_previous"] == 100 and petr["cost_previous"] == 1000
    # FIFO dava 1.000 (as 50 da compra a 20); a Receita quer o custo medio.
    assert petr["quantity"] == 50 and petr["cost"] == 750
    assert "Custo de aquisição em 31/12/2025: R$ 750,00" in petr["description"]
    fii = next(item for item in body["bens_e_direitos"] if item["ticker"] == "HGLG11")
    assert (fii["group"], fii["code"]) == ("07", "03")


def test_dividends_are_exempt_and_jcp_is_exclusive(client, auth):
    buy = trade(client, auth, "PETR4", 100, 10.0, "2025-01-10")
    for kind, gross, tax in (("DIVIDEND", 50, 0), ("JCP", 100, 15)):
        response = client.post(
            "/api/investment-proceeds", headers=auth,
            json={"asset_id": buy["asset_id"], "proceeds_type": kind, "record_date": "2025-03-01",
                  "payment_date": "2025-03-20", "gross_amount": gross, "tax_amount": tax},
        )
        assert response.status_code == 201, response.get_data(as_text=True)
    body = report(client, auth)
    assert {"line": "09 - Lucros e dividendos recebidos", "amount": 50.0} in body["rendimentos_isentos"]
    jcp = next(item for item in body["tributacao_exclusiva"] if item["line"].startswith("10"))
    assert (jcp["gross"], jcp["withheld"]) == (100, 15)


def test_foreign_gains_are_taxed_yearly_at_15(client, auth):
    trade(client, auth, "AAPL", 10, 100.0, "2025-02-03", currency="USD")
    trade(client, auth, "AAPL", -10, 120.0, "2025-05-05", currency="USD")  # 10 x 20 x 5,00
    body = report(client, auth)
    assert body["exterior"]["result"] == 1000
    assert body["exterior"]["tax"] == 150
    # E fica fora da apuracao mensal de acoes da B3.
    assert all(item["stocks"]["sales"] == 0 for item in body["renda_variavel"]["months"])


def test_export_has_one_sheet_per_section(client, auth):
    trade(client, auth, "PETR4", 100, 10.0, "2025-01-10")
    response = client.get("/api/tax-report/export?year=2025", headers=auth)
    assert response.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(response.get_data()))
    names = sorted(name for name in archive.namelist() if name.startswith("xl/worksheets/"))
    assert names == ["xl/worksheets/sheet1.xml", "xl/worksheets/sheet2.xml", "xl/worksheets/sheet3.xml"]
    assert "Bens e Direitos" in archive.read("xl/workbook.xml").decode()
    assert "PETR4" in archive.read("xl/worksheets/sheet1.xml").decode()


def test_the_export_carries_the_foreign_result_only_when_there_is_one(client, auth, other_user):
    # The screens are reais-only, so a foreign sale can only come from the API —
    # but if one exists its estimated tax must not vanish from the report.
    def income_sheet(headers):
        response = client.get("/api/tax-report/export?year=2025", headers=headers)
        assert response.status_code == 200
        archive = zipfile.ZipFile(io.BytesIO(response.get_data()))
        return archive.read("xl/worksheets/sheet3.xml").decode()

    trade(client, other_user["headers"], "PETR4", 100, 10.0, "2025-01-10")
    assert "Exterior" not in income_sheet(other_user["headers"])

    trade(client, auth, "AAPL", 10, 100.0, "2025-02-03", currency="USD")
    trade(client, auth, "AAPL", -10, 120.0, "2025-05-05", currency="USD")  # 10 x 20 x 5,00
    sheet = income_sheet(auth)
    assert "Exterior (Lei 14.754/2023)" in sheet
    assert "<v>1000.0</v>" in sheet and "<v>150.0</v>" in sheet


def test_invalid_year_is_refused(client, auth):
    assert client.get("/api/tax-report?year=abc", headers=auth).status_code == 400
    assert client.get(f"/api/tax-report?year={datetime.now().year + 1}", headers=auth).status_code == 400


def test_another_users_trades_stay_out(client, user, other_user):
    trade(client, other_user["headers"], "PETR4", 100, 10.0, "2025-01-10")
    body = report(client, user["headers"])
    assert body["bens_e_direitos"] == []
    assert body["renda_variavel"]["months"] == []


# --- Proventos no relatorio: o que tax_report le de services/proceeds.py ---


def proceed(client, headers, asset_id, payment_date, gross, *, kind="DIVIDEND", tax=0):
    response = client.post(
        "/api/investment-proceeds", headers=headers,
        json={"asset_id": asset_id, "proceeds_type": kind, "record_date": payment_date,
              "payment_date": payment_date, "gross_amount": gross, "tax_amount": tax},
    )
    assert response.status_code == 201, response.get_data(as_text=True)


def test_proceeds_are_the_calendar_year_inclusive_and_ordered_by_payment(client, auth):
    buy = trade(client, auth, "PETR4", 100, 10.0, "2024-06-10")
    # Gravados fora de ordem; o relatorio lista por data de pagamento.
    for date, gross in (("2025-12-31", 4), ("2026-01-01", 8), ("2025-06-15", 2),
                        ("2024-12-31", 16), ("2025-01-01", 1)):
        proceed(client, auth, buy["asset_id"], date, gross)
    proceed(client, auth, buy["asset_id"], "2025-03-10", 32, kind="AMORTIZATION")
    body = report(client, auth)

    # Amortizacao nao e rendimento: fica fora da lista e das linhas.
    assert [item["date"] for item in body["proventos"]] == ["2025-01-01", "2025-06-15", "2025-12-31"]
    assert [item["gross"] for item in body["proventos"]] == [1, 2, 4]
    assert {"line": "09 - Lucros e dividendos recebidos", "amount": 7.0} in body["rendimentos_isentos"]


def test_a_scheduled_proceed_stays_out_until_paid(client, auth):
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    buy = trade(client, auth, "HGLG11", 10, 100.0, (today - timedelta(days=400)).isoformat(), asset_class="REIT")
    proceed(client, auth, buy["asset_id"], today.isoformat(), 3)
    proceed(client, auth, buy["asset_id"], tomorrow.isoformat(), 5)
    body = report(client, auth, year=today.year)

    assert [item["date"] for item in body["proventos"]] == [today.isoformat()]
    assert {"line": "99 - Rendimentos de FII", "amount": 3.0} in body["rendimentos_isentos"]


def test_a_foreign_proceed_is_taken_as_recorded_in_reais(client, auth):
    buy = trade(client, auth, "AAPL", 10, 100.0, "2025-02-03", currency="USD")
    proceed(client, auth, buy["asset_id"], "2025-05-15", 10, kind="JCP", tax=1.5)
    body = report(client, auth)

    jcp = next(item for item in body["tributacao_exclusiva"] if item["line"].startswith("10"))
    assert (jcp["gross"], jcp["withheld"]) == (10, 1.5)   # sem PTAX (5,00) aplicada
    assert body["proventos"] == [{"date": "2025-05-15", "ticker": "AAPL", "type": "JCP", "gross": 10, "tax": 1.5}]


def test_another_users_proceeds_stay_out(client, user, other_user):
    theirs = trade(client, other_user["headers"], "PETR4", 100, 10.0, "2025-01-10")
    proceed(client, other_user["headers"], theirs["asset_id"], "2025-03-20", 50)
    mine = trade(client, user["headers"], "VALE3", 100, 10.0, "2025-01-10")
    proceed(client, user["headers"], mine["asset_id"], "2025-04-20", 7)
    body = report(client, user["headers"])

    assert [item["ticker"] for item in body["proventos"]] == ["VALE3"]
    assert {"line": "09 - Lucros e dividendos recebidos", "amount": 7.0} in body["rendimentos_isentos"]
