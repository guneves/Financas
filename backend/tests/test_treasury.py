"""Tesouro Direto marcado a mercado, agrupado por titulo e liquido de taxas.

Owner, 2026-10-19: "agrupe os mesmos titulos em um so ... uma taxa media
apropriada ... o valor exato dos titulos, considerando taxas e marcacao a
mercado" (comparado ao extrato da BTG).

- o arquivo do Tesouro Transparente e lido pelo cabecalho (";", decimal com
  virgula, dd/mm/aaaa) e o titulo e achado pelo nome que o dono deu, inclusive
  o da corretora ("NTNB Princ") e o Renda+ pelo ano da conversao;
- quantos titulos uma compra comprou: valor aplicado / PU da compra (na taxa
  contratada, num titulo sem cupom), ou o numero informado;
- bruto = titulos x PU de venda do dia; liquido = bruto - custodia (0,20% a.a.
  pro rata die desde D+1, nunca antes de 2025) - IOF - IR, compra a compra;
  Selic isento de custodia ate R$ 10 mil;
- duas compras do mesmo titulo sao uma posicao, com a taxa media que da o
  mesmo valor no vencimento; o resgate tira titulos da compra;
- sem o arquivo, a posicao agrupa do mesmo jeito, pela curva;
- a evolucao e a rentabilidade usam o mesmo PU, e "Atualizar cotacoes" grava
  o valor de mercado como cotacao (fonte "tesouro").
"""

from datetime import date, datetime, timedelta
import importlib

import pytest

TODAY = date.today()
D1 = TODAY - timedelta(days=400)
D2 = TODAY - timedelta(days=100)
MATURITY = date(2045, 5, 15)

HEADER = "Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;PU Compra Manha;PU Venda Manha;PU Base Manha"


def br(value):
    return f"{value:.2f}".replace(".", ",")


def row(title, maturity, day, buy_rate, sell_rate, buy_pu, sell_pu, base_pu=None):
    return ";".join([
        title, maturity.strftime("%d/%m/%Y"), day.strftime("%d/%m/%Y"),
        br(buy_rate), br(sell_rate), br(buy_pu), br(sell_pu), br(base_pu or sell_pu),
    ])


def prices_csv(extra_rows=()):
    rows = [
        HEADER,
        # Fora de ordem de proposito: o arquivo real nao vem ordenado.
        row("Tesouro IPCA+", MATURITY, TODAY, 6.30, 6.20, 1205.00, 1200.00),
        row("Tesouro IPCA+", MATURITY, D1, 6.50, 6.62, 1000.00, 995.00),
        row("Tesouro IPCA+", MATURITY, D2, 6.00, 6.12, 1100.00, 1095.00),
        row("Tesouro IPCA+ com Juros Semestrais", date(2045, 5, 15), TODAY, 6.1, 6.2, 4000.0, 3990.0),
        row("Tesouro Renda+ Aposentadoria Extra", date(2084, 12, 15), D1, 6.90, 7.02, 180.00, 179.00),
        row("Tesouro Renda+ Aposentadoria Extra", date(2084, 12, 15), TODAY, 6.80, 6.92, 216.50, 215.95),
        row("Tesouro Selic", date(2029, 3, 1), D1, 0.05, 0.07, 15000.00, 14990.00),
        row("Tesouro Selic", date(2029, 3, 1), TODAY, 0.05, 0.07, 17000.00, 16990.00),
        *extra_rows,
    ]
    return "\n".join(rows) + "\n"


@pytest.fixture()
def tesouro(app_module):
    module = importlib.import_module("tesouro_client")
    yield module
    module.set_prices(None)


@pytest.fixture()
def treasury(app_module):
    return importlib.import_module("services.treasury")


@pytest.fixture()
def prices(tesouro):
    loaded = tesouro.parse_prices_csv(prices_csv())
    tesouro.set_prices(loaded)
    return loaded


IPCA_TERMS = {"fixed_income_type": "TESOURO", "rate_type": "POS", "indexer": "IPCA"}


def buy(client, auth, name, applied, day, rate=None, **metadata):
    terms = dict(IPCA_TERMS)
    if rate is not None:
        terms["annual_rate"] = rate
    else:
        terms["annual_rate"] = 0.06
    response = client.post(
        "/api/investments",
        headers=auth,
        json=[{
            "asset_class": "FIXED_INCOME",
            "ticker_or_name": name,
            "quantity": 1,
            "average_price": applied,
            "current_price": applied,
            "metadata": {**terms, "purchase_date": day.isoformat(), "cash_account_id": None, **metadata},
        }],
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()[0]["id"]


def portfolio(client, auth):
    response = client.get("/api/investments/portfolio?refresh_prices=false", headers=auth)
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def treasury_assets(body):
    return [asset for asset in body["assets"] if asset.get("category") == "TESOURO"]


def custody(units_pus, rate=0.002):
    """sum(titulos x PU x dias) x 0,20% / 365."""
    return rate * sum(units * pu * days for units, pu, days in units_pus) / 365


def ir_rate(days):
    return 0.225 if days <= 180 else 0.20 if days <= 360 else 0.175 if days <= 720 else 0.15


class TestThePricesFile:
    def test_reads_by_header_and_sorts_each_title(self, tesouro):
        prices = tesouro.parse_prices_csv(prices_csv())
        series = prices.find_title("Tesouro IPCA+ 2045")
        assert series.maturity == MATURITY
        assert series.latest()["sell_pu"] == 1200.00
        assert series.row_on_or_before(D1 + timedelta(days=3))["buy_pu"] == 1000.00
        assert series.purchase_row(D1 - timedelta(days=5))["date"] == D1
        assert prices.latest_date == TODAY

    @pytest.mark.parametrize("name,expected_type,expected_maturity", [
        ("Tesouro IPCA+ 2045", "TESOURO IPCA+", MATURITY),
        ("TESOURO IPCA+ 2045 (NTNB PRINC)", "TESOURO IPCA+", MATURITY),
        ("NTN-B Principal 2045", "TESOURO IPCA+", MATURITY),
        ("Tesouro IPCA + 2045", "TESOURO IPCA+", MATURITY),
        ("Tesouro IPCA+ com Juros Semestrais 2045", "TESOURO IPCA+ COM JUROS SEMESTRAIS", MATURITY),
        ("NTN-B 2045", "TESOURO IPCA+ COM JUROS SEMESTRAIS", MATURITY),
        # O Renda+ leva o ano da conversao no nome; vence 19 anos depois.
        ("Tesouro Renda+ Aposentadoria Extra 2065", "TESOURO RENDA+ APOSENTADORIA EXTRA", date(2084, 12, 15)),
        ("TESOURO RENDA+ APOSENTADORIA EXTRA 2084", "TESOURO RENDA+ APOSENTADORIA EXTRA", date(2084, 12, 15)),
        ("Tesouro Selic 2029", "TESOURO SELIC", date(2029, 3, 1)),
    ])
    def test_finds_the_title_by_the_owners_name(self, tesouro, name, expected_type, expected_maturity):
        series = tesouro.parse_prices_csv(prices_csv()).find_title(name)
        assert series is not None
        assert (series.title_type, series.maturity) == (expected_type, expected_maturity)

    @pytest.mark.parametrize("name", ["Tesouro IPCA+", "Tesouro IPCA+ 2035", "CDB Banco X 2045"])
    def test_no_title_without_a_matching_type_and_year(self, tesouro, name):
        assert tesouro.parse_prices_csv(prices_csv()).find_title(name) is None

    def test_a_file_without_the_columns_is_refused(self, tesouro):
        with pytest.raises(ValueError):
            tesouro.parse_prices_csv("a;b;c\n1;2;3\n")


class TestTheRules:
    def test_purchase_pu_moves_to_the_contracted_rate(self, treasury, prices):
        series = prices.find_title("Tesouro IPCA+ 2045")
        assert treasury.purchase_pu(series, D1, {**IPCA_TERMS, "annual_rate": 0.065}) == pytest.approx(1000.00)
        # Comprou a 6,60% numa hora em que o arquivo dizia 6,50%: pagou menos.
        years = treasury.business_years(D1, MATURITY)
        adjusted = treasury.purchase_pu(series, D1, {**IPCA_TERMS, "annual_rate": 0.066})
        assert adjusted == pytest.approx(1000.00 * (1.065 / 1.066) ** years)
        # Uma taxa absurda nao mexe no PU (outro titulo ou erro de digitacao).
        assert treasury.purchase_pu(series, D1, {**IPCA_TERMS, "annual_rate": 0.12}) == pytest.approx(1000.00)

    def test_the_average_rate_gives_the_same_value_at_maturity(self, treasury):
        lots = [
            {"cost": 1000.0, "rate": 0.065, "purchase_date": D1},
            {"cost": 2200.0, "rate": 0.060, "purchase_date": D2},
        ]
        average = treasury.average_rate(lots, MATURITY)
        terms = [(lot["cost"], lot["rate"], treasury.business_years(lot["purchase_date"], MATURITY)) for lot in lots]
        assert sum(c * (1 + average) ** t for c, _, t in terms) == pytest.approx(sum(c * (1 + r) ** t for c, r, t in terms))
        # Pesa mais a compra mais longa: acima da media simples pelo custo.
        assert (1000 * 0.065 + 2200 * 0.06) / 3200 < average < 0.065

    def test_without_maturity_the_average_is_by_cost(self, treasury):
        lots = [
            {"cost": 1000.0, "rate": 0.065, "purchase_date": D1},
            {"cost": 3000.0, "rate": 0.061, "purchase_date": D1},
        ]
        assert treasury.average_rate(lots, None) == pytest.approx(0.062)
        # Com o vencimento, a convexidade poe a taxa equivalente pouco acima.
        assert 0.062 < treasury.average_rate(lots, MATURITY) < 0.0621
        assert treasury.average_rate(lots[:1], MATURITY) == pytest.approx(0.065)

    def test_iof_in_the_first_month(self, treasury):
        assert treasury.iof_rate(10) == pytest.approx(0.66)
        assert treasury.iof_rate(29) == pytest.approx(0.03)
        assert treasury.iof_rate(30) == 0


class TestTheGroupedPosition:
    def test_two_buys_of_the_same_title_are_one_position_at_market(self, client, auth, prices):
        first = buy(client, auth, "Tesouro IPCA+ 2045", 1000.00, D1, rate=0.065)
        second = buy(client, auth, "TESOURO IPCA+ 2045 (NTNB PRINC)", 2200.00, D2, rate=0.060)

        body = portfolio(client, auth)
        [position] = treasury_assets(body)
        assert {lot["id"] for lot in position["lots"]} == {first, second}
        # 1 titulo a R$ 1.000 + 2 a R$ 1.100, vendidos hoje a R$ 1.200.
        assert position["quantity"] == pytest.approx(3.0)
        assert position["current_price"] == pytest.approx(1200.00)
        assert position["current_value"] == pytest.approx(3600.00)
        assert position["total_invested"] == pytest.approx(3200.00)
        assert position["treasury"]["maturity_date"] == "2045-05-15"
        assert position["treasury"]["valuation"] == "MARKET"
        assert position["treasury"]["price_date"] == TODAY.isoformat()
        assert position["quote"]["source"] == "tesouro"
        assert 0.06 < position["metadata"]["annual_rate"] < 0.065

        custody_first = custody([(1, 995.00, (D2 - D1).days - 1), (1, 1095.00, (TODAY - D2).days)])
        custody_second = custody([(2, 1095.00, (TODAY - D2).days - 1)])
        ir_first = (1200 - custody_first - 1000) * ir_rate((TODAY - D1).days)
        ir_second = (2400 - custody_second - 2200) * ir_rate((TODAY - D2).days)
        expected_net = 3600 - custody_first - custody_second - ir_first - ir_second
        assert position["treasury"]["custody"] == pytest.approx(custody_first + custody_second, abs=0.01)
        assert position["treasury"]["income_tax"] == pytest.approx(ir_first + ir_second, abs=0.01)
        assert position["net_value"] == pytest.approx(expected_net, abs=0.01)
        assert position["taxes"] == pytest.approx(3600 - expected_net, abs=0.01)
        assert body["current_balance"] == pytest.approx(3600.00)
        assert body["current_net_balance"] == pytest.approx(expected_net, abs=0.01)

    def test_typed_units_win(self, client, auth, prices):
        buy(client, auth, "Tesouro Renda+ Aposentadoria Extra 2065", 7500.00, D1, rate=0.069, treasury_units=42.79)
        [position] = treasury_assets(portfolio(client, auth))
        assert position["quantity"] == pytest.approx(42.79)
        assert position["current_value"] == pytest.approx(42.79 * 215.95, abs=0.01)
        assert position["treasury"]["maturity_date"] == "2084-12-15"

    def test_a_redemption_takes_titles_out_of_its_buy(self, client, auth, prices):
        first = buy(client, auth, "Tesouro IPCA+ 2045", 1000.00, D1, rate=0.065)
        buy(client, auth, "Tesouro IPCA+ 2045", 2200.00, D2, rate=0.060)
        response = client.post("/api/investments", headers=auth, json=[{
            "asset_class": "FIXED_INCOME",
            "ticker_or_name": "Tesouro IPCA+ 2045",
            "quantity": -1,
            "average_price": 500.00,
            "current_price": 600.00,
            "metadata": {
                "is_redemption": True, "affects_position": True, "related_id": first,
                "redemption_date": TODAY.isoformat(), "cash_account_id": None,
            },
        }])
        assert response.status_code == 201, response.get_json()
        [position] = treasury_assets(portfolio(client, auth))
        lot = next(item for item in position["lots"] if item["id"] == first)
        assert lot["units"] == pytest.approx(0.5)
        assert lot["gross"] == pytest.approx(600.00)
        assert position["quantity"] == pytest.approx(2.5)
        assert position["total_invested"] == pytest.approx(2700.00)

    def test_iof_on_a_buy_younger_than_30_days(self, client, auth, tesouro):
        recent = TODAY - timedelta(days=10)
        tesouro.set_prices(tesouro.parse_prices_csv(prices_csv([
            row("Tesouro IPCA+", MATURITY, recent, 6.20, 6.32, 1190.00, 1185.00),
        ])))
        buy(client, auth, "Tesouro IPCA+ 2045", 1190.00, recent, rate=0.062)
        [position] = treasury_assets(portfolio(client, auth))
        [lot] = position["lots"]
        lot_custody = custody([(1, 1185.00, 9)])
        income = 1200 - lot_custody - 1190
        assert lot["iof"] == pytest.approx(income * 0.66, abs=0.01)
        assert lot["income_tax"] == pytest.approx((income - income * 0.66) * 0.225, abs=0.01)

    def test_selic_custody_is_exempt_up_to_ten_thousand(self, client, auth, prices):
        buy(client, auth, "Tesouro Selic 2029", 7500.00, D1, rate=None,
            **{"indexer": "CDI", "cdi_percentage": 1.0, "annual_rate": None})
        [position] = treasury_assets(portfolio(client, auth))
        assert position["current_value"] == pytest.approx(0.5 * 16990.00)
        assert position["treasury"]["custody"] == 0

    def test_without_the_file_it_still_groups_on_the_curve(self, client, auth, tesouro):
        tesouro.set_prices(None)
        buy(client, auth, "Tesouro IPCA+ 2045", 1000.00, D1, rate=0.065)
        buy(client, auth, "Tesouro IPCA+ 2045", 2200.00, D2, rate=0.060)
        [position] = treasury_assets(portfolio(client, auth))
        assert len(position["lots"]) == 2
        assert position["treasury"]["valuation"] == "CURVE"
        assert position["current_value"] == pytest.approx(3200.00)
        assert position["treasury"]["maturity_date"] is None

    def test_other_fixed_income_stays_one_row_per_buy(self, client, auth, prices):
        for applied in (1000.0, 2000.0):
            client.post("/api/investments", headers=auth, json=[{
                "asset_class": "FIXED_INCOME", "ticker_or_name": "CDB BANCO X 2045", "quantity": 1,
                "average_price": applied, "current_price": applied,
                "metadata": {"fixed_income_type": "CDB", "rate_type": "POS", "indexer": "CDI",
                             "cdi_percentage": 1.1, "purchase_date": D1.isoformat(), "cash_account_id": None},
            }])
        body = portfolio(client, auth)
        assert len([asset for asset in body["assets"] if asset["class"] == "FIXED_INCOME"]) == 2
        assert treasury_assets(body) == []


class TestTheOtherScreens:
    def test_the_evolution_ends_on_the_position(self, client, auth, prices):
        buy(client, auth, "Tesouro IPCA+ 2045", 1000.00, D1, rate=0.065)
        buy(client, auth, "Tesouro IPCA+ 2045", 2200.00, D2, rate=0.060)
        snapshot = portfolio(client, auth)
        response = client.get("/api/investments/history", headers=auth, query_string={"months": 3})
        assert response.status_code == 200
        last = response.get_json()["evolution"][-1]
        assert last["patrimonioBruto"] == pytest.approx(snapshot["current_balance"], abs=0.01)
        assert last["patrimonio"] == pytest.approx(snapshot["current_net_balance"], abs=0.01)
        # A rentabilidade termina no mesmo bruto.
        response = client.get("/api/investments/returns", headers=auth, query_string={"months": 3, "asset_class": "FIXED_INCOME"})
        assert response.status_code == 200
        assert response.get_json()["series"][-1]["value"] == pytest.approx(snapshot["current_balance"], abs=0.01)

    @pytest.mark.parametrize("path", [
        "/api/investments/portfolio/export",
        "/api/allocation",
        "/api/allocation/sectors",
        "/api/goals",
        "/api/investments/returns?months=3",
        "/api/investment-positions",
    ])
    def test_screens_reading_the_snapshot_take_the_grouped_title(self, client, auth, prices, path):
        buy(client, auth, "Tesouro IPCA+ 2045", 1000.00, D1, rate=0.065)
        buy(client, auth, "Tesouro IPCA+ 2045", 2200.00, D2, rate=0.060)
        portfolio(client, auth)
        response = client.get(path, headers=auth)
        assert response.status_code == 200, response.get_data(as_text=True)[:300]

    def test_a_past_month_reads_that_days_price(self, app_module, treasury, prices):
        metadata = {**IPCA_TERMS, "annual_rate": 0.065, "purchase_date": D1.isoformat()}
        value = treasury.market_value_on(
            "FIXED_INCOME", "Tesouro IPCA+ 2045", metadata, 1000.0, 1000.0, D2 + timedelta(days=5), prices,
        )
        assert value == pytest.approx(1095.00)
        assert treasury.market_value_on(
            "FIXED_INCOME", "Tesouro IPCA+ 2045", metadata, 1000.0, 1000.0, D1 - timedelta(days=1), prices,
        ) is None
        assert treasury.market_value_on(
            "FIXED_INCOME", "CDB X 2045", {**metadata, "fixed_income_type": "CDB"}, 1000.0, 1000.0, TODAY, prices,
        ) is None

    def test_update_prices_records_the_market_value(self, client, auth, prices):
        first = buy(client, auth, "Tesouro IPCA+ 2045", 1000.00, D1, rate=0.065)
        response = client.post("/api/investments/update-prices", headers=auth, json={})
        assert response.status_code == 200, response.get_json()
        updated = [item for item in response.get_json()["updated_assets"] if item.get("investment_id") == first]
        assert [item["source"] for item in updated] == ["tesouro"]
        assert updated[0]["price"] == pytest.approx(1200.00)
        assert not [item for item in response.get_json()["failed_assets"] if item.get("investment_id") == first]


class TestTheDownload:
    def test_latin1_file_and_discovery_when_the_address_moves(self, tesouro, monkeypatch):
        import urllib.error

        new_url = "https://example.invalid/novo/PrecoTaxaTesouroDireto.csv"
        calls = []

        def fake_get(url):
            calls.append(url)
            if url == "https://example.invalid/antigo.csv":
                raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
            if url == tesouro.TESOURO_PACKAGE_URL:
                return (
                    '{"result": {"resources": [{"name": "Metadados", "url": "https://x/meta.pdf"},'
                    f' {{"name": "Preço e Taxa", "url": "{new_url}"}}]}}}}'
                ).encode()
            assert url == new_url
            return prices_csv().replace("Tipo Titulo", "Tipo Título").encode("latin-1")

        monkeypatch.setattr(tesouro, "TESOURO_PRICES_URL", "https://example.invalid/antigo.csv")
        monkeypatch.setattr(tesouro, "_http_get", fake_get)
        tesouro.reset_cache()
        prices = tesouro.get_prices(wait=True)
        assert prices is not None
        assert prices.find_title("Tesouro IPCA+ 2045").latest()["sell_pu"] == 1200.00
        assert calls[-1] == new_url
        # Fresco: a proxima leitura nao vai a rede.
        calls.clear()
        assert tesouro.get_prices() is prices
        assert calls == []

    def test_a_failed_download_keeps_what_there_was(self, tesouro, monkeypatch):
        old = tesouro.parse_prices_csv(prices_csv(), fetched_at=0)
        tesouro.set_prices(old)

        def failing(url):
            raise OSError("sem rede")

        monkeypatch.setattr(tesouro, "TESOURO_PRICES_URL", "https://example.invalid/antigo.csv")
        monkeypatch.setattr(tesouro, "_http_get", failing)
        # Velho demais para ser preco de mercado, e o download falhou: nada.
        assert tesouro.get_prices(wait=True) is None
        tesouro.wait_refresh()
        assert tesouro.get_prices() is None
