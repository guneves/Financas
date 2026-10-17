"""Tipo do papel na posicao: a classe STOCKS junta acao, ETF e BDR, e a tela
de posicao separa um do outro por `market_kind` (catalogo da B3)."""


def buy(client, auth, asset_class, ticker):
    response = client.post(
        "/api/investments",
        headers=auth,
        json={
            "asset_class": asset_class,
            "ticker_or_name": ticker,
            "quantity": 10,
            "average_price": 10,
            "current_price": 10,
            "metadata": {"purchase_date": "2026-01-10"},
        },
    )
    assert response.status_code in (200, 201), response.get_json()


def test_position_carries_the_catalog_kind(client, auth, portfolio_module, user):
    buy(client, auth, "STOCKS", "PETR4")
    buy(client, auth, "STOCKS", "BOVA11")
    buy(client, auth, "STOCKS", "XPBR31")
    buy(client, auth, "REIT", "MXRF11")
    buy(client, auth, "OTHER", "Relogio")

    assets = portfolio_module.build_portfolio_snapshot(user["id"])["assets"]
    kinds = {asset["ticker"]: asset["market_kind"] for asset in assets}
    assert kinds == {
        "PETR4": "ACAO",
        "BOVA11": "ETF",
        "XPBR31": "BDR",
        "MXRF11": "FII",
        "RELOGIO": None,
    }


def test_unknown_ticker_falls_back_to_the_class_kind(portfolio_module):
    assert portfolio_module.asset_market_kind("STOCKS", "ZZZZ3") == "ACAO"
    assert portfolio_module.asset_market_kind("REIT", "ZZZZ11") == "FII"
    assert portfolio_module.asset_market_kind("FIXED_INCOME", "CDB") is None
