"""B3 catalog: ticker search and the guard on creating an investment.

Two things are tested here. The first is the search ranking, which is what makes
the autocomplete usable: an entry whose ticker starts with what was typed comes
before one that merely contains it. The second is the guard on
`POST /api/investments` — a buy of a quoted asset only goes through with a paper
from the catalog, or with an asset the user already held before the catalog
existed.
"""

import importlib
import pytest


@pytest.fixture()
def catalog(app_module):
    return importlib.import_module("market_catalog")


class TestCatalogSearch:
    def test_prefix_matches_come_first(self, catalog):
        results = catalog.search("PETR")
        tickers = [entry["ticker"] for entry in results]

        assert tickers[:2] == ["PETR3", "PETR4"]

    def test_search_is_case_insensitive_and_ignores_the_sa_suffix(self, catalog):
        assert catalog.lookup("petr4")["ticker"] == "PETR4"
        assert catalog.lookup("PETR4.SA")["ticker"] == "PETR4"

    def test_search_also_matches_the_company_name(self, catalog):
        tickers = [entry["ticker"] for entry in catalog.search("Magazine")]
        assert "MGLU3" in tickers

    def test_etfs_and_fiis_are_in_the_catalog(self, catalog):
        assert catalog.lookup("BOVA11")["kind"] == "ETF"
        assert catalog.lookup("IVVB11")["kind"] == "ETF"
        assert catalog.lookup("MXRF11")["kind"] == "FII"
        assert catalog.lookup("AAPL34")["kind"] == "BDR"

    def test_fiis_are_classified_as_reit_and_etfs_as_stocks(self, catalog):
        assert catalog.lookup("MXRF11")["asset_class"] == "REIT"
        assert catalog.lookup("BOVA11")["asset_class"] == "STOCKS"

    def test_asset_class_filter_excludes_the_other_classes(self, catalog):
        results = catalog.search("11", asset_class="REIT", limit=100)
        assert results
        assert all(entry["asset_class"] == "REIT" for entry in results)

    def test_unknown_ticker_is_not_found(self, catalog):
        assert catalog.lookup("PETR5") is None
        assert catalog.is_known("PETR4") is True

    def test_limit_is_respected(self, catalog):
        assert len(catalog.search("", limit=5)) == 5


class TestTickerSearchEndpoint:
    def test_search_returns_matching_tickers(self, client, auth):
        response = client.get("/api/market/tickers?q=vale", headers=auth)
        assert response.status_code == 200

        body = response.get_json()
        assert body[0]["ticker"] == "VALE3"
        assert body[0]["asset_class"] == "STOCKS"

    def test_search_can_be_scoped_to_a_class(self, client, auth):
        response = client.get("/api/market/tickers?q=11&asset_class=REIT&limit=50", headers=auth)
        assert response.status_code == 200
        assert all(entry["asset_class"] == "REIT" for entry in response.get_json())

    def test_detail_returns_404_for_an_unknown_ticker(self, client, auth):
        assert client.get("/api/market/tickers/PETR9", headers=auth).status_code == 404
        assert client.get("/api/market/tickers/PETR4", headers=auth).status_code == 200

    def test_search_requires_authentication(self, client):
        assert client.get("/api/market/tickers?q=vale").status_code == 401


def buy(ticker, asset_class="STOCKS", quantity=10, price=10.0):
    return [{
        "asset_class": asset_class,
        "ticker_or_name": ticker,
        "quantity": quantity,
        "average_price": price,
        "current_price": price,
        "metadata": {"purchase_date": "2026-02-10"},
    }]


class TestPurchaseGuard:
    def test_known_stock_is_accepted(self, client, auth):
        response = client.post("/api/investments", json=buy("PETR4"), headers=auth)
        assert response.status_code in (200, 201), response.get_data(as_text=True)

    def test_known_etf_is_accepted(self, client, auth):
        response = client.post("/api/investments", json=buy("BOVA11"), headers=auth)
        assert response.status_code in (200, 201), response.get_data(as_text=True)

    def test_unknown_ticker_is_refused(self, client, auth):
        response = client.post("/api/investments", json=buy("PETR9"), headers=auth)
        assert response.status_code == 400
        assert "PETR9" in response.get_json()["error"]

    def test_ticker_is_stored_without_the_sa_suffix(self, client, auth):
        response = client.post("/api/investments", json=buy("wege3.sa"), headers=auth)
        assert response.status_code in (200, 201), response.get_data(as_text=True)

        tickers = [item["ticker_or_name"] for item in client.get("/api/investments", headers=auth).get_json()]
        assert "WEGE3" in tickers

    def test_selling_with_the_sa_suffix_finds_the_position_bought_without_it(self, client, auth):
        # As duas pontas normalizam igual; se a venda nao normalizasse, ela nao
        # acharia a posicao gravada como PETR3 e seria recusada.
        client.post("/api/investments", json=buy("PETR3", quantity=100), headers=auth)

        response = client.post(
            "/api/investments",
            json=[{
                "asset_class": "STOCKS",
                "ticker_or_name": "petr3.sa",
                "quantity": -40,
                "average_price": 10.0,
                "metadata": {"sale_date": "2026-03-10", "sale_price": 12.0},
            }],
            headers=auth,
        )
        assert response.status_code in (200, 201), response.get_data(as_text=True)

    def test_fii_bought_as_stocks_is_refused_with_the_right_class(self, client, auth):
        response = client.post("/api/investments", json=buy("MXRF11"), headers=auth)
        assert response.status_code == 400
        assert "Fundos Imobiliarios" in response.get_json()["error"]

    def test_fii_bought_as_reit_is_accepted(self, client, auth):
        response = client.post("/api/investments", json=buy("MXRF11", asset_class="REIT"), headers=auth)
        assert response.status_code in (200, 201), response.get_data(as_text=True)

    def test_free_text_still_works_for_classes_without_quotes(self, client, auth):
        response = client.post(
            "/api/investments",
            json=[{
                "asset_class": "CATTLE",
                "ticker_or_name": "Bezerro Nelore",
                "quantity": 5,
                "average_price": 2000.0,
                "metadata": {"purchase_date": "2026-02-10"},
            }],
            headers=auth,
        )
        assert response.status_code in (200, 201), response.get_data(as_text=True)

    def test_legacy_position_outside_the_catalog_can_still_be_traded(self, client, user, app_module):
        # Ativo gravado direto no banco, como uma posicao anterior ao catalogo.
        _seed_legacy_asset(app_module, user["id"], "legacy-asset-1", "OLDX3")

        response = client.post("/api/investments", json=buy("OLDX3"), headers=user["headers"])
        assert response.status_code in (200, 201), response.get_data(as_text=True)

    def test_selling_does_not_need_the_catalog(self, client, user, app_module):
        _seed_legacy_asset(app_module, user["id"], "legacy-asset-2", "OLDY3")
        client.post("/api/investments", json=buy("OLDY3", quantity=10), headers=user["headers"])

        response = client.post(
            "/api/investments",
            json=[{
                "asset_class": "STOCKS",
                "ticker_or_name": "OLDY3",
                "quantity": -4,
                "average_price": 10.0,
                "metadata": {"sale_date": "2026-03-10", "sale_price": 12.0},
            }],
            headers=user["headers"],
        )
        assert response.status_code in (200, 201), response.get_data(as_text=True)


def _seed_legacy_asset(app_module, user_id, asset_id, ticker):
    with importlib.import_module("db").get_db() as conn:
        conn.execute(
            "INSERT INTO assets (id, user_id, asset_class, ticker, name) VALUES (?, ?, ?, ?, ?)",
            (asset_id, user_id, "STOCKS", ticker, ticker),
        )


# ---------------------------------------------------------------------------
# A B3 inteira: a /quote/list da brapi entra atras do catalogo fixo
# ---------------------------------------------------------------------------


def _listing_item(symbol, name, listing_type, sub_type):
    brapi_client = importlib.import_module("brapi_client")
    return brapi_client.SectorInfo(symbol=symbol, name=name, type=listing_type, sub_type=sub_type)


@pytest.fixture()
def b3_listing(app_module, monkeypatch):
    """Patches brapi's full listing; returns the call counter and a failure switch."""
    brapi_client = importlib.import_module("brapi_client")
    market_listing = importlib.import_module("services.market_listing")
    market_listing.reset_cache()
    state = {"calls": 0, "fail": False}
    items = [
        _listing_item("LEVE3", "MAHLE-METAL LEVE S.A.", "stock", "stock"),
        _listing_item("LEVE3F", "MAHLE-METAL LEVE S.A.", "stock", "stock"),
        _listing_item("FESA4", "CIA FERRO LIGAS DA BAHIA - FERBASA", "stock", "stock"),
        _listing_item("SAPR11", "CIA SANEAMENTO DO PARANA - SANEPAR", "stock", "unit"),
        _listing_item("RZAG11", "RZAG11", "fund", "fi-agro"),
        _listing_item("JURO11", "JURO11", "fund", "fi-infra"),
        _listing_item("PETR4", "PETROLEO BRASILEIRO S.A. PETROBRAS", "stock", "stock"),
    ]

    def fake_get_listing(**kwargs):
        state["calls"] += 1
        if state["fail"]:
            raise brapi_client.BrapiUnavailableError("fora do ar")
        return {item.symbol: item for item in items}

    monkeypatch.setattr(brapi_client, "is_configured", lambda: True)
    monkeypatch.setattr(brapi_client, "get_listing", fake_get_listing)
    yield state
    market_listing.reset_cache()


class TestFullB3Listing:
    def test_listing_types_map_to_catalog_kinds(self, catalog):
        assert catalog.entry_from_listing("leve3", "MAHLE", "stock", "stock")["asset_class"] == "STOCKS"
        assert catalog.entry_from_listing("SAPR11", "SANEPAR", "stock", "unit")["kind"] == "ACAO"
        assert catalog.entry_from_listing("BOVA11", "BOVA11", "fund", "etf")["kind"] == "ETF"
        assert catalog.entry_from_listing("RZAG11", "RZAG11", "fund", "fi-agro")["asset_class"] == "REIT"
        assert catalog.entry_from_listing("AAPL34", "AAPL34", "bdr", "bdr")["kind"] == "BDR"
        # Tributacao que nenhuma classe do app cobre: fica fora.
        assert catalog.entry_from_listing("JURO11", "JURO11", "fund", "fi-infra") is None
        assert catalog.entry_from_listing("XPTO11", "XPTO11", "fund", None) is None

    def test_search_finds_a_small_cap_outside_the_fixed_catalog(self, client, auth, b3_listing):
        response = client.get("/api/market/tickers?q=leve", headers=auth)
        assert response.status_code == 200
        # O fracionario nao aparece como outro papel.
        assert [entry["ticker"] for entry in response.get_json()] == ["LEVE3"]

        response = client.get("/api/market/tickers?q=ferbasa", headers=auth)
        assert [entry["ticker"] for entry in response.get_json()] == ["FESA4"]

    def test_fixed_catalog_name_wins_over_the_listing(self, client, auth, b3_listing):
        body = client.get("/api/market/tickers/PETR4", headers=auth).get_json()
        assert body["name"] == "Petrobras PN"

    def test_detail_and_purchase_accept_a_listed_ticker(self, client, auth, b3_listing):
        assert client.get("/api/market/tickers/FESA4", headers=auth).status_code == 200
        response = client.post("/api/investments", json=buy("fesa4"), headers=auth)
        assert response.status_code in (200, 201), response.get_data(as_text=True)

    def test_excluded_fund_type_is_still_refused(self, client, auth, b3_listing):
        response = client.post("/api/investments", json=buy("JURO11", asset_class="REIT"), headers=auth)
        assert response.status_code == 400

    def test_listing_is_fetched_once_and_cached(self, client, auth, b3_listing):
        client.get("/api/market/tickers?q=leve", headers=auth)
        client.get("/api/market/tickers?q=fesa", headers=auth)
        assert b3_listing["calls"] == 1

    def test_brapi_down_falls_back_to_the_fixed_catalog_and_backs_off(self, client, auth, b3_listing):
        b3_listing["fail"] = True
        response = client.get("/api/market/tickers?q=vale", headers=auth)
        assert response.status_code == 200
        assert response.get_json()[0]["ticker"] == "VALE3"
        assert client.get("/api/market/tickers/LEVE3", headers=auth).status_code == 404
        # A falha nao e tentada de novo a cada tecla.
        client.get("/api/market/tickers?q=leve", headers=auth)
        assert b3_listing["calls"] == 1

    def test_known_ticker_does_not_need_the_listing(self, client, auth, b3_listing):
        assert client.get("/api/market/tickers/PETR4", headers=auth).status_code == 200
        assert b3_listing["calls"] == 0
