"""Apuracao mensal da renda variavel e o IR de cada venda.

O que estes testes fixam:

- `market_catalog.tax_kind()`: acao (unit incluida), ETF, BDR (pelo catalogo ou
  pelo final do ticker), ETF de renda fixa e FII;
- `monthly_apuration()` (services/variable_income_tax.py): a isencao de R$ 20
  mil e so das acoes (Lei 11.033/2004, art. 3o, I); ETF e BDR pagam 15% sem
  isencao, nao contam no limite e dividem o saldo de prejuizo com as acoes; FII
  20% com saldo proprio; o imposto do mes e repartido entre as vendas com lucro;
- pela API: o IR de cada venda na lista de Operacoes e a parte dela no imposto
  do mes da aba IR (uma venda isenta sai com IR 0); ETF de renda fixa fica fora
  do DARF; Bens e Direitos sugere o codigo de ETF e de BDR; o isentometro nao
  conta a venda simulada de um ETF;
- o custo dos proventos (yield on cost) nao soma a corretagem duas vezes.
"""

import importlib
import io
import zipfile

import pytest


@pytest.fixture()
def catalog(app_module):
    return importlib.import_module("market_catalog")


@pytest.fixture()
def rules(app_module):
    return importlib.import_module("services.variable_income_tax")


class TestTaxKind:
    @pytest.mark.parametrize("ticker, asset_class, expected", [
        ("PETR4", "STOCKS", "ACAO"),
        ("TAEE11", "STOCKS", "ACAO"),      # unit e acao
        ("IVVB11", "STOCKS", "ETF"),
        ("AAPL34", "STOCKS", "BDR"),
        ("XPTO34", "STOCKS", "BDR"),       # fora do catalogo: pelo final do ticker
        ("LFTB11", "STOCKS", "ETF_RF"),
        ("IMAB11", "STOCKS", "ETF_RF"),
        ("LEVE3", "STOCKS", "ACAO"),       # fora do catalogo fixo: acao
        ("HGLG11", "REIT", "FII"),
        ("CDB X", "FIXED_INCOME", None),
    ])
    def test_kinds(self, catalog, ticker, asset_class, expected):
        assert catalog.tax_kind(ticker, asset_class) == expected


def sale(sale_id, month, bucket, gross, result):
    return {"id": sale_id, "month": month, "bucket": bucket, "gross": gross, "result": result}


class TestMonthlyApuration:
    def test_an_exempt_stock_sale_owes_nothing(self, rules):
        out = rules.monthly_apuration([sale("s1", "2025-02", "ACAO", 6000, 1000)])
        entry = out["months"][0]
        assert entry["stocks"]["exempt"] is True
        assert entry["stocks"]["exempt_gain"] == 1000
        assert out["tax_by_sale"]["s1"] == 0

    def test_an_etf_pays_15_with_no_exemption_and_does_not_count_in_the_limit(self, rules):
        out = rules.monthly_apuration([
            sale("acao", "2025-03", "ACAO", 15000, 1000),
            sale("etf", "2025-03", "COMMON", 10000, 2000),
        ])
        entry = out["months"][0]
        # As vendas de acoes (15 mil) seguem abaixo do limite: ganho da acao isento.
        assert entry["stocks"]["sales"] == 15000
        assert entry["stocks"]["exempt_gain"] == 1000
        assert entry["etfs"] == {"sales": 10000, "result": 2000}
        assert entry["stocks"]["taxable"] == 2000
        assert entry["stocks"]["tax"] == 300
        assert out["tax_by_sale"] == {"acao": 0, "etf": 300}

    def test_a_stock_loss_in_an_exempt_month_offsets_an_etf_gain(self, rules):
        out = rules.monthly_apuration([
            sale("acao", "2025-04", "ACAO", 5000, -500),
            sale("bdr", "2025-04", "COMMON", 3000, 800),
        ])
        entry = out["months"][0]
        assert entry["stocks"]["common_result"] == 300
        assert entry["stocks"]["tax"] == 45
        assert out["tax_by_sale"]["bdr"] == 45

    def test_above_the_limit_the_month_tax_is_split_among_winners(self, rules):
        out = rules.monthly_apuration([
            sale("a", "2025-05", "ACAO", 15000, 3000),
            sale("b", "2025-05", "ACAO", 10000, 1000),
            sale("c", "2025-05", "ACAO", 5000, -2000),
        ])
        entry = out["months"][0]
        assert entry["stocks"]["taxable"] == 2000
        assert entry["stocks"]["tax"] == 300
        assert out["tax_by_sale"] == {"a": 225, "b": 75, "c": 0}

    def test_losses_carry_over_and_an_exempt_gain_does_not_consume_them(self, rules):
        out = rules.monthly_apuration([
            sale("loss", "2025-01", "ACAO", 25000, -1000),
            sale("exempt", "2025-02", "ACAO", 5000, 400),
            sale("taxed", "2025-03", "ACAO", 30000, 3000),
        ])
        jan, feb, mar = out["months"]
        assert jan["stocks"]["loss_balance"] == 1000
        assert feb["stocks"]["loss_balance"] == 1000
        assert mar["stocks"]["loss_used"] == 1000
        assert mar["stocks"]["tax"] == 300
        assert out["tax_by_sale"]["taxed"] == 300

    def test_reits_pay_20_with_their_own_loss_pool(self, rules):
        out = rules.monthly_apuration([
            sale("acao", "2025-06", "ACAO", 30000, -5000),
            sale("fii", "2025-06", "FII", 11000, 1000),
        ])
        entry = out["months"][0]
        assert entry["reits"]["tax"] == 200
        assert entry["stocks"]["loss_balance"] == 5000
        assert out["tax_by_sale"]["fii"] == 200

    def test_the_split_adds_up_to_the_cent(self, rules):
        out = rules.monthly_apuration([
            sale(f"s{index}", "2025-07", "COMMON", 1000, 33.33) for index in range(3)
        ])
        assert sum(out["tax_by_sale"].values()) == pytest.approx(out["months"][0]["stocks"]["tax"], abs=0.001)


# --- Pela API ---------------------------------------------------------------


def trade(client, auth, ticker, quantity, price, date, *, asset_class="STOCKS", costs=0.0):
    sale_row = quantity < 0
    metadata = {"sale_date": date, "sale_price": price} if sale_row else {"purchase_date": date}
    metadata["other_costs"] = costs
    payload = {
        "asset_class": asset_class,
        "ticker_or_name": ticker,
        "quantity": quantity,
        # Como a tela: o preco da compra ja traz os custos.
        "average_price": price if sale_row else (quantity * price + costs) / quantity,
        "current_price": price,
        "metadata": metadata,
    }
    response = client.post("/api/investments", headers=auth, json=payload)
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()[0]


def sales_by_ticker(client, auth):
    rows = client.get("/api/investments", headers=auth).get_json()
    return {row["ticker_or_name"]: row for row in rows if row["quantity"] < 0}


def report(client, auth, year=2025):
    response = client.get(f"/api/tax-report?year={year}", headers=auth)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def test_an_exempt_sale_shows_no_tax_in_operacoes(client, auth):
    # O caso da PETR4 no seed: R$ 1.142,70 vendidos no mes, Operacoes dizia IR R$ 20,58.
    trade(client, auth, "PETR4", 52, 38.48, "2024-04-07")
    trade(client, auth, "PETR4", -26, 43.95, "2024-05-20")
    sale_row = sales_by_ticker(client, auth)["PETR4"]
    assert sale_row["realized_profit"] > 0
    assert sale_row["realized_tax_amount"] == 0
    assert sale_row["realized_net_profit_after_tax"] == sale_row["realized_profit"]
    assert sale_row["realized_metadata"]["tax_method"] == "apuracao_mensal"


def test_the_tax_of_each_sale_adds_up_to_the_month_in_the_ir_tab(client, auth):
    trade(client, auth, "VALE3", 1000, 20.0, "2025-01-10")
    trade(client, auth, "ITUB4", 1000, 10.0, "2025-01-10")
    trade(client, auth, "VALE3", -1000, 25.0, "2025-03-10")   # 25 mil, ganho 5.000
    trade(client, auth, "ITUB4", -1000, 9.0, "2025-03-12")    # 9 mil, prejuizo 1.000
    rows = sales_by_ticker(client, auth)
    march = next(item for item in report(client, auth)["renda_variavel"]["months"] if item["month"] == "2025-03")
    assert march["stocks"]["tax"] == 600
    assert rows["VALE3"]["realized_tax_amount"] == 600
    assert rows["ITUB4"]["realized_tax_amount"] == 0


def test_an_etf_sale_is_taxed_and_does_not_use_the_stock_exemption(client, auth):
    trade(client, auth, "IVVB11", 100, 300.0, "2025-01-10")
    trade(client, auth, "IVVB11", -50, 340.0, "2025-02-10")   # vendas 17 mil, ganho 2.000
    body = report(client, auth)
    feb = next(item for item in body["renda_variavel"]["months"] if item["month"] == "2025-02")
    assert feb["stocks"]["sales"] == 0
    assert feb["etfs"]["result"] == 2000
    assert feb["stocks"]["tax"] == 300
    assert feb["darf"] == 300
    assert not any(item["line"].startswith("20") for item in body["rendimentos_isentos"])
    assert sales_by_ticker(client, auth)["IVVB11"]["realized_tax_amount"] == 300
    bens = next(item for item in body["bens_e_direitos"] if item["ticker"] == "IVVB11")
    assert (bens["group"], bens["code"]) == ("07", "09")


def test_a_bdr_gets_its_own_bens_code(client, auth):
    trade(client, auth, "AAPL34", 10, 50.0, "2025-01-10")
    bens = next(item for item in report(client, auth)["bens_e_direitos"] if item["ticker"] == "AAPL34")
    assert (bens["group"], bens["code"]) == ("04", "04")


def test_a_fixed_income_etf_stays_out_of_the_darf(client, auth):
    # IR retido na fonte pelo administrador (Lei 13.043/2014): nada de DARF.
    trade(client, auth, "IMAB11", 100, 100.0, "2025-01-10")
    trade(client, auth, "IMAB11", -100, 110.0, "2025-06-10")
    body = report(client, auth)
    assert not any(item["month"] == "2025-06" and item["darf"] for item in body["renda_variavel"]["months"])
    assert [item["ticker"] for item in body["renda_variavel"]["fixed_income_etfs"]] == ["IMAB11"]


def test_the_meter_ignores_a_planned_etf_sale(client, auth):
    trade(client, auth, "PETR4", 1000, 10.0, "2025-01-10")
    trade(client, auth, "PETR4", -1000, 15.0, "2025-02-10")   # 15 mil em acoes
    stock = client.get(
        "/api/tax-report/exemption?month=2025-02&planned_sale=8000&ticker=VALE3", headers=auth,
    ).get_json()
    etf = client.get(
        "/api/tax-report/exemption?month=2025-02&planned_sale=8000&ticker=IVVB11", headers=auth,
    ).get_json()
    assert stock["eligible"] is True and stock["would_exceed"] is True
    assert etf["eligible"] is False and etf["would_exceed"] is False
    assert etf["sales_after"] == 15000


def test_the_yield_on_cost_counts_the_buy_costs_once(client, auth):
    buy = trade(client, auth, "BBAS3", 100, 10.0, "2025-01-10", costs=10.0)   # custo 1.010
    response = client.post(
        "/api/investment-proceeds", headers=auth,
        json={"asset_id": buy["asset_id"], "proceeds_type": "DIVIDEND", "record_date": "2025-03-01",
              "payment_date": "2025-03-15", "amount_per_unit": 1.01},
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    item = response.get_json()
    assert item["cost_basis_at_record_date"] == 1010.0   # antes: 1.020 (corretagem duas vezes)
    assert item["yield_on_cost_percent"] == 10.0


def irpf_blocks(body, section_key):
    section = next(item for item in body["irpf_text"]["sections"] if item["key"] == section_key)
    return [block["text"] for block in section["blocks"]]


def test_the_irpf_text_puts_an_etf_in_the_common_stock_line(client, auth):
    trade(client, auth, "IVVB11", 100, 300.0, "2025-01-10")
    trade(client, auth, "IVVB11", -50, 340.0, "2025-02-10")
    text = "\n".join(irpf_blocks(report(client, auth), "renda_variavel"))
    assert "Mercado à vista - ações (R$): 2.000,00" in text
    assert "ETFs e BDRs: vendas 17.000,00" in text


def test_the_export_declares_the_net_exclusive_income(client, auth):
    buy = trade(client, auth, "PETR4", 100, 10.0, "2025-01-10")
    response = client.post(
        "/api/investment-proceeds", headers=auth,
        json={"asset_id": buy["asset_id"], "proceeds_type": "JCP", "record_date": "2025-03-01",
              "payment_date": "2025-03-15", "gross_amount": 100, "tax_amount": 15},
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    export = client.get("/api/tax-report/export?year=2025", headers=auth)
    assert export.status_code == 200
    sheet = zipfile.ZipFile(io.BytesIO(export.get_data())).read("xl/worksheets/sheet3.xml").decode()
    assert "Bruto (R$)" in sheet
    # Linha do JCP: valor declarado 85 (liquido), bruto 100, IR 15.
    assert ">85<" in sheet or ">85.0<" in sheet
