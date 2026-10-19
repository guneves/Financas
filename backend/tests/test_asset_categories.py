"""Categoria de cada ativo (owner, 2026-10-19): ETF e ETF, nao Acao; Tesouro
Direto e uma categoria propria, separada da Renda fixa; a renda fixa tem
setor pelo indexador (Pre-fixado, Pos-fixado, IPCA+) em vez de "Sem setor".

O que estes testes fixam:

- a categoria e calculada na leitura (`services/asset_categories.py`): a classe
  do banco nao muda, e /api/assets, /api/investments e a carteira a devolvem;
- Tesouro Direto e o tipo de titulo TESOURO, ou um titulo sem tipo cujo nome
  comeca por "Tesouro"; o indexador sai do metadata, ou do nome do Tesouro;
- a alocacao por setor poe a renda fixa no setor do indexador, com o tipo como
  segmento; o setor manual ainda vence; titulo sem remuneracao segue sem setor;
- o servidor recusa o tipo de provento que a classe nao recebe (cupom fora da
  renda fixa, dividendo/JCP em renda fixa, JCP em FII), so quando o ativo ou o
  tipo mudam.
"""

import importlib

import pytest


@pytest.fixture(autouse=True)
def offline(app_module, monkeypatch):
    prices = importlib.import_module("services.prices")
    monkeypatch.setattr(prices, "download_close_prices", lambda symbols, **kwargs: {})


@pytest.fixture()
def categories(app_module):
    return importlib.import_module("services.asset_categories")


def buy(client, auth, asset_class, ticker, metadata=None, price=1000.0, quantity=1):
    response = client.post(
        "/api/investments",
        headers=auth,
        json=[{
            "asset_class": asset_class,
            "ticker_or_name": ticker,
            "quantity": quantity,
            "average_price": price,
            "current_price": price,
            "metadata": {"purchase_date": "2025-01-02", "cash_account_id": None, **(metadata or {})},
        }],
    )
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    return response.get_json()[0]["asset_id"]


TESOURO_IPCA = {"fixed_income_type": "TESOURO", "rate_type": "POS", "indexer": "IPCA", "annual_rate": 0.065}
CDB_CDI = {"fixed_income_type": "CDB", "rate_type": "POS", "indexer": "CDI", "cdi_percentage": 1.1}
LCA_PRE = {"fixed_income_type": "LCA", "rate_type": "PRE", "annual_rate": 0.12}


class TestTheCategoryRule:
    def test_stocks_split_into_acao_etf_and_bdr(self, categories):
        assert categories.asset_category("STOCKS", "PETR4") == "ACAO"
        assert categories.asset_category("STOCKS", "BOVA11") == "ETF"
        assert categories.asset_category("STOCKS", "IMAB11") == "ETF"     # ETF de renda fixa
        assert categories.asset_category("STOCKS", "XPBR31") == "BDR"
        assert categories.asset_category("REIT", "MXRF11") == "FII"

    def test_treasury_by_type_or_by_name(self, categories):
        assert categories.asset_category("FIXED_INCOME", "TESOURO SELIC 2029", "TESOURO") == "TESOURO"
        assert categories.asset_category("FIXED_INCOME", "NTN-B 2035", "TESOURO") == "TESOURO"
        # Titulo antigo, sem tipo: o nome decide.
        assert categories.asset_category("FIXED_INCOME", "Tesouro IPCA+ 2035") == "TESOURO"
        # Com outro tipo escolhido, o nome nao vence.
        assert categories.asset_category("FIXED_INCOME", "TESOURO SELIC 2029", "CDB") == "RENDA_FIXA"
        assert categories.asset_category("FIXED_INCOME", "CDB BANCO X") == "RENDA_FIXA"

    def test_other_and_crypto(self, categories):
        assert categories.asset_category("OTHER", "BTC") == "CRIPTO"
        assert categories.asset_category("OTHER", "RELOGIO") == "OTHER"

    @pytest.mark.parametrize("metadata,name,expected", [
        ({"rate_type": "PRE", "annual_rate": 0.12}, None, "PRE"),
        ({"rate_type": "POS", "indexer": "CDI", "cdi_percentage": 1.1}, None, "POS"),
        ({"rate_type": "POS", "indexer": "CDI_PLUS", "annual_rate": 0.015}, None, "POS"),
        ({"rate_type": "POS", "indexer": "IPCA", "annual_rate": 0.06}, None, "IPCA"),
        ({"cdi_percentage": 1.0}, None, "POS"),                       # lancamento antigo
        ({}, "TESOURO SELIC 2029", "POS"),
        ({}, "TESOURO PREFIXADO 2031", "PRE"),
        ({}, "TESOURO IPCA+ COM JUROS SEMESTRAIS 2040", "IPCA"),
        ({}, "TESOURO RENDA+ APOSENTADORIA EXTRA 2065", "IPCA"),
        ({}, "CDB BANCO X", None),
    ])
    def test_rate_kind(self, categories, metadata, name, expected):
        assert categories.rate_kind(metadata, name) == expected


class TestTheApi:
    def test_assets_carry_their_category(self, client, auth):
        etf = buy(client, auth, "STOCKS", "BOVA11", price=100, quantity=10)
        stock = buy(client, auth, "STOCKS", "PETR4", price=30, quantity=10)
        treasury = buy(client, auth, "FIXED_INCOME", "TESOURO IPCA+ 2035", TESOURO_IPCA)
        cdb = buy(client, auth, "FIXED_INCOME", "CDB BANCO X", CDB_CDI)

        response = client.get("/api/assets", headers=auth)
        assert response.status_code == 200
        by_id = {item["id"]: item for item in response.get_json()}
        assert by_id[etf]["category"] == "ETF" and by_id[etf]["category_label"] == "ETFs"
        assert by_id[etf]["asset_class"] == "STOCKS"          # o banco nao muda
        assert by_id[stock]["category"] == "ACAO"
        assert by_id[treasury]["category"] == "TESOURO"
        assert by_id[treasury]["category_label"] == "Tesouro Direto"
        assert by_id[treasury]["rate_kind"] == "IPCA"
        assert by_id[cdb]["category"] == "RENDA_FIXA"
        assert by_id[cdb]["rate_kind_label"] == "Pós-fixado"

    def test_movements_and_positions_carry_it_too(self, client, auth, portfolio_module, user):
        buy(client, auth, "STOCKS", "BOVA11", price=100, quantity=10)
        buy(client, auth, "FIXED_INCOME", "TESOURO IPCA+ 2035", TESOURO_IPCA)

        movements = client.get("/api/investments", headers=auth).get_json()
        labels = {item["ticker_or_name"]: item["asset_category_label"] for item in movements}
        assert labels == {"BOVA11": "ETFs", "TESOURO IPCA+ 2035": "Tesouro Direto"}

        positions = portfolio_module.build_portfolio_snapshot(user["id"])["assets"]
        categories = {item["ticker"]: (item["category"], item["class"]) for item in positions}
        assert categories == {
            "BOVA11": ("ETF", "STOCKS"),
            "TESOURO IPCA+ 2035": ("TESOURO", "FIXED_INCOME"),
        }

    def test_a_treasury_title_is_taxed_like_other_fixed_income(self, client, auth):
        # O tipo novo passa pela validacao e nao e isento.
        asset_id = buy(client, auth, "FIXED_INCOME", "TESOURO PREFIXADO 2029",
                       {"fixed_income_type": "TESOURO", "rate_type": "PRE", "annual_rate": 0.13})
        response = client.post("/api/investment-proceeds", headers=auth, json={
            "asset_id": asset_id, "proceeds_type": "INTEREST",
            "payment_date": "2025-12-01", "gross_amount": 100,
        })
        assert response.status_code == 201, response.get_data(as_text=True)
        # Aplicacao em 02/01/2025, pagamento em 01/12/2025: 333 dias -> 20%.
        assert response.get_json()["tax_amount"] == 20.0


class TestFixedIncomeSectors:
    def sectors(self, client, auth):
        response = client.get("/api/allocation/sectors", headers=auth)
        assert response.status_code == 200, response.get_data(as_text=True)
        return {item["label"]: item for item in response.get_json()["sectors"]}

    def test_fixed_income_is_grouped_by_its_indexer(self, client, auth):
        buy(client, auth, "FIXED_INCOME", "CDB BANCO X", CDB_CDI)
        buy(client, auth, "FIXED_INCOME", "LCA BANCO Y", LCA_PRE)
        buy(client, auth, "FIXED_INCOME", "TESOURO IPCA+ 2035", TESOURO_IPCA)
        buy(client, auth, "FIXED_INCOME", "TESOURO SELIC 2029")       # sem metadata: pelo nome

        body = self.sectors(client, auth)
        assert set(body) == {"Pós-fixado", "Pré-fixado", "IPCA+"}
        pos = body["Pós-fixado"]
        assert sorted(item["ticker"] for item in pos["assets"]) == ["CDB BANCO X", "TESOURO SELIC 2029"]
        segments = {item["ticker"]: (item["segment"], item["source"], item["category_label"]) for item in pos["assets"]}
        assert segments["CDB BANCO X"] == ("CDB", "INDEXER", "Renda fixa")
        assert segments["TESOURO SELIC 2029"] == ("Tesouro Direto", "INDEXER", "Tesouro Direto")
        assert body["IPCA+"]["assets"][0]["segment"] == "Tesouro Direto"

    def test_manual_sector_still_wins_and_a_title_without_rate_has_none(self, client, auth):
        cdb = buy(client, auth, "FIXED_INCOME", "CDB BANCO X", CDB_CDI)
        buy(client, auth, "FIXED_INCOME", "TITULO SEM TAXA")
        response = client.patch(f"/api/assets/{cdb}/sector", headers=auth, json={"sector": "Bancos"})
        assert response.status_code == 200

        body = self.sectors(client, auth)
        assert set(body) == {"Bancos", "Sem setor"}
        assert body["Bancos"]["assets"][0]["source"] == "MANUAL"


class TestProceedsTypeByClass:
    def post(self, client, auth, asset_id, proceeds_type, **fields):
        return client.post("/api/investment-proceeds", headers=auth, json={
            "asset_id": asset_id, "proceeds_type": proceeds_type,
            "record_date": "2025-06-01", "payment_date": "2025-06-15", "gross_amount": 50,
            **fields,
        })

    def test_refuses_what_the_class_never_pays(self, client, auth):
        stock = buy(client, auth, "STOCKS", "PETR4", price=30, quantity=10)
        fii = buy(client, auth, "REIT", "MXRF11", price=10, quantity=100)
        cdb = buy(client, auth, "FIXED_INCOME", "CDB BANCO X", CDB_CDI)

        assert self.post(client, auth, stock, "INTEREST").status_code == 400
        assert self.post(client, auth, fii, "JCP").status_code == 400
        assert self.post(client, auth, cdb, "DIVIDEND").status_code == 400
        assert self.post(client, auth, cdb, "JCP").status_code == 400

        assert self.post(client, auth, stock, "JCP").status_code == 201
        assert self.post(client, auth, fii, "DIVIDEND").status_code == 201
        assert self.post(client, auth, fii, "AMORTIZATION").status_code == 201
        assert self.post(client, auth, cdb, "INTEREST").status_code == 201
        assert self.post(client, auth, cdb, "AMORTIZATION").status_code == 201

    def test_an_edit_that_keeps_type_and_asset_is_not_refused(self, client, auth, db_module):
        fii = buy(client, auth, "REIT", "MXRF11", price=10, quantity=100)
        created = self.post(client, auth, fii, "DIVIDEND").get_json()
        # Um JCP de FII gravado antes da regra (direto no banco) ainda se edita.
        with db_module.get_db() as conn:
            conn.execute("UPDATE investment_proceeds SET proceeds_type = 'JCP' WHERE id = ?", (created["id"],))
        response = client.patch(f"/api/investment-proceeds/{created['id']}", headers=auth, json={"notes": "ok"})
        assert response.status_code == 200, response.get_data(as_text=True)
        response = client.patch(f"/api/investment-proceeds/{created['id']}", headers=auth,
                                json={"proceeds_type": "INTEREST"})
        assert response.status_code == 400
