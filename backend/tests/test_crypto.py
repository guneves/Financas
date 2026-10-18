"""Bitcoin na carteira: cotacao automatica em reais e o IR do criptoativo.

O Bitcoin fica na classe "Outros" (o CHECK das migrations nao aceita uma
classe nova sem reconstruir `assets`), com o ticker canonico BTC. O que estes
testes fixam:

- "bitcoin", "BTC-BRL" e "BTC" sao a mesma posicao, chamada "Bitcoin", e so em
  reais;
- a cotacao vem do Yahoo como BTC-BRL (nunca da brapi), uma por ativo, e a
  Posicao a usa; fracoes de satoshi nao se perdem;
- IR (services/crypto_tax.py): isento no mes em que o total vendido de cripto
  fica em ate R$ 35 mil; acima, 15% do ganho (progressivo acima de R$ 5
  milhoes), sem compensar prejuizo; Bens e Direitos no grupo 08, codigo 01.
"""

import importlib

import pytest

from asset_classes import crypto_ticker, is_quoted_asset


@pytest.fixture()
def market(app_module, prices_module, monkeypatch):
    """O yfinance "existe", mas so responde o que esta em `quotes`."""
    quotes = {}
    calls = []

    def _download(yf_symbols, *, period, interval):
        calls.append(list(yf_symbols))
        return {symbol: quotes[symbol] for symbol in yf_symbols if symbol in quotes}

    monkeypatch.setattr(prices_module, "yf", object(), raising=False)
    monkeypatch.setattr(prices_module, "download_close_prices", _download)
    with prices_module._price_cache_lock:
        prices_module._price_cache.clear()
    return quotes, calls


@pytest.fixture()
def crypto_tax(app_module):
    return importlib.import_module("services.crypto_tax")


def trade(client, auth, quantity, price, date, *, ticker="BTC", currency=None):
    sale = quantity < 0
    payload = {
        "asset_class": "OTHER",
        "ticker_or_name": ticker,
        "quantity": quantity,
        "average_price": price,
        "current_price": price,
        "metadata": {"sale_date": date, "sale_price": price} if sale else {"purchase_date": date},
    }
    if currency:
        payload["currency"] = currency
    return client.post("/api/investments", headers=auth, json=payload)


def ok(response):
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    return response.get_json()


def btc_position(client, auth):
    body = ok(client.get("/api/investments/portfolio", headers=auth))
    return next(item for item in body["assets"] if item["ticker"] == "BTC")


def report(client, auth, year=2025):
    return ok(client.get(f"/api/tax-report?year={year}", headers=auth))


class TestIdentity:
    def test_the_aliases_are_one_ticker(self):
        assert crypto_ticker("bitcoin") == "BTC"
        assert crypto_ticker(" btc-brl ") == "BTC"
        assert crypto_ticker("XBT") == "BTC"
        assert crypto_ticker("Ouro") is None

    def test_only_other_class_bitcoin_is_quoted_crypto(self):
        assert is_quoted_asset("OTHER", "BTC")
        assert not is_quoted_asset("OTHER", "Ouro")
        assert not is_quoted_asset("FIXED_INCOME", "BTC")

    def test_bitcoin_by_any_name_is_one_position(self, client, auth, market):
        ok(trade(client, auth, 0.01, 300000.0, "2025-01-10", ticker="bitcoin"))
        ok(trade(client, auth, 0.00012345, 400000.0, "2025-02-10", ticker="BTC-BRL"))
        held = btc_position(client, auth)
        assert held["name"] == "Bitcoin"
        assert held["market_kind"] == "CRIPTO"
        # Satoshi a satoshi: a Posicao arredondava a quantidade em 4 casas.
        assert held["quantity"] == pytest.approx(0.01012345, abs=1e-9)

    def test_bitcoin_is_bought_in_reais(self, client, auth, market):
        response = trade(client, auth, 0.01, 60000.0, "2025-01-10", currency="USD")
        assert response.status_code == 400
        assert "reais" in response.get_json()["error"]

    def test_a_sale_above_the_position_is_refused(self, client, auth, market):
        ok(trade(client, auth, 0.01, 300000.0, "2025-01-10"))
        assert trade(client, auth, -0.02, 300000.0, "2025-02-10").status_code == 400


class TestQuote:
    def test_the_quote_is_btc_brl_on_yahoo_and_never_brapi(self, prices_module, market, monkeypatch):
        quotes, calls = market
        quotes["BTC-BRL"] = 612345.67
        monkeypatch.setattr(prices_module.brapi_client, "is_configured", lambda: True)

        def _brapi(tickers):
            assert "BTC" not in tickers
            return {}

        monkeypatch.setattr(prices_module.brapi_client, "get_market_prices", _brapi)
        assert prices_module.download_market_prices(["BTC"]) == {"BTC": 612345.67}
        assert calls and all(symbols == ["BTC-BRL"] for symbols in calls)

    def test_update_prices_values_the_position_at_the_market(self, client, auth, market):
        quotes, _ = market
        ok(trade(client, auth, 0.02, 300000.0, "2025-01-10"))
        quotes["BTC-BRL"] = 500000.0
        ok(client.post("/api/investments/update-prices", headers=auth, json={"force": True}))
        held = btc_position(client, auth)
        assert held["current_price"] == pytest.approx(500000.0)
        assert held["current_value"] == pytest.approx(10000.0)
        assert held["total_invested"] == pytest.approx(6000.0)

    def test_one_quote_serves_every_purchase(self, client, auth, market):
        # Em "Outros" a cotacao era por operacao; o Bitcoin tem uma so, do ativo.
        quotes, _ = market
        ok(trade(client, auth, 0.01, 300000.0, "2025-01-10"))
        ok(trade(client, auth, 0.01, 400000.0, "2025-02-10"))
        quotes["BTC-BRL"] = 450000.0
        ok(client.post("/api/investments/update-prices", headers=auth, json={"force": True}))
        assert btc_position(client, auth)["current_value"] == pytest.approx(9000.0)


class TestCapitalGainTax:
    def test_brackets_apply_each_to_its_slice(self, crypto_tax):
        assert crypto_tax.capital_gain_tax(-10) == 0
        assert crypto_tax.capital_gain_tax(1000) == pytest.approx(150.0)
        assert crypto_tax.capital_gain_tax(6_000_000) == pytest.approx(750_000 + 175_000)

    def test_the_limit_is_on_the_total_sold_not_the_gain(self, crypto_tax):
        result = crypto_tax.monthly_crypto_tax([
            {"id": "a", "month": "2025-03", "gross": 20000, "result": 5000},
            {"id": "b", "month": "2025-03", "gross": 15000, "result": 3000},
            {"id": "c", "month": "2025-04", "gross": 20000, "result": 4000},
            {"id": "d", "month": "2025-04", "gross": 15001, "result": -2000},
        ])
        assert result["months"]["2025-03"]["exempt"] is True
        assert result["tax_by_sale"]["a"] == 0 and result["tax_by_sale"]["b"] == 0
        # Abril passa de R$ 35 mil: o ganho paga 15% e o prejuizo nao compensa.
        assert result["months"]["2025-04"]["exempt"] is False
        assert result["tax_by_sale"]["c"] == pytest.approx(600.0)
        assert result["tax_by_sale"]["d"] == 0
        assert result["months"]["2025-04"]["tax"] == pytest.approx(600.0)


class TestTaxReport:
    def test_a_month_up_to_35k_is_exempt(self, client, auth, market):
        ok(trade(client, auth, 0.1, 200000.0, "2025-01-10"))
        ok(trade(client, auth, -0.1, 300000.0, "2025-03-10"))  # vende R$ 30 mil, ganho R$ 10 mil
        body = report(client, auth)
        gain = next(item for item in body["ganho_de_capital"] if item["ticker"] == "BTC")
        assert gain["crypto"] is True and gain["exempt"] is True
        assert gain["tax_estimate"] == 0
        line = next(item for item in body["rendimentos_isentos"] if item["line"].startswith("05 - "))
        assert line["amount"] == pytest.approx(10000.0)
        assert "05 - Ganho de capital" in body["irpf_text"]["sections"][1]["text"]

    def test_above_35k_the_gain_pays_15(self, client, auth, market):
        ok(trade(client, auth, 0.2, 200000.0, "2025-01-10"))
        ok(trade(client, auth, -0.2, 300000.0, "2025-03-10"))  # vende R$ 60 mil, ganho R$ 20 mil
        body = report(client, auth)
        gain = next(item for item in body["ganho_de_capital"] if item["ticker"] == "BTC")
        assert gain["exempt"] is False
        assert gain["tax_estimate"] == pytest.approx(3000.0)
        assert not any(item["line"].startswith("05 - ") for item in body["rendimentos_isentos"])

    def test_the_sale_carries_the_same_tax_as_the_report(self, client, auth, market):
        ok(trade(client, auth, 0.1, 200000.0, "2025-01-10"))
        sale = ok(trade(client, auth, -0.1, 300000.0, "2025-03-10"))[0]
        rows = ok(client.get("/api/investment-realized-results", headers=auth))
        rows = rows if isinstance(rows, list) else rows.get("items") or rows.get("results")
        row = next(item for item in rows if item["source_transaction_id"] == sale["id"])
        assert row["tax_amount"] == 0
        assert row["metadata"]["tax_method"] == "ganho_de_capital_cripto"

    def test_bens_e_direitos_is_group_08_code_01(self, client, auth, market):
        ok(trade(client, auth, 0.01234567, 300000.0, "2025-01-10"))
        body = report(client, auth)
        bens = next(item for item in body["bens_e_direitos"] if item["ticker"] == "BTC")
        assert (bens["group"], bens["code"]) == ("08", "01")
        assert bens["quantity"] == pytest.approx(0.01234567)
        text = body["irpf_text"]["sections"][0]["text"]
        assert "Grupo: 08 - Criptoativos" in text
        assert "0,01234567 BTC - Bitcoin" in text

    def test_another_other_asset_keeps_the_15_estimate(self, client, auth, market):
        ok(trade(client, auth, 1, 1000.0, "2025-01-10", ticker="Ouro"))
        ok(trade(client, auth, -1, 1500.0, "2025-03-10", ticker="Ouro"))
        gain = next(item for item in report(client, auth)["ganho_de_capital"] if item["ticker"] == "OURO")
        assert gain["crypto"] is False
        assert gain["tax_estimate"] == pytest.approx(75.0)
