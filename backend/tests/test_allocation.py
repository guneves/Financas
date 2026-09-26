"""Alocacao alvo da carteira (020): atual x meta e a sugestao de aporte.

O que estes testes fixam:

- meta de classe e percentual da carteira; meta de ativo e percentual DENTRO
  da classe;
- metas de classe somam 100%, e as de ativo somam 100% em cada classe que
  tenha alguma — senao o PUT recusa e nada muda;
- o PUT troca o conjunto inteiro (mandar vazio apaga);
- a sugestao reparte o aporte na proporcao da falta de cada classe (e, dentro
  dela, de cada ativo), sem vender nada, e a soma bate no centavo;
- "oportunidade" = abaixo da meta na classe e cotado abaixo do preco medio;
- nada de outro usuario aparece nem pode receber meta.
"""

import importlib
from datetime import timedelta

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


def buy(client, auth, ticker, quantity, price, *, current=None, asset_class="STOCKS"):
    payload = {
        "asset_class": asset_class,
        "ticker_or_name": ticker,
        "quantity": quantity,
        "average_price": price,
        "current_price": current if current is not None else price,
        "metadata": {"purchase_date": "2025-01-10"},
    }
    response = client.post("/api/investments", headers=auth, json=payload)
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    body = response.get_json()
    return body[0] if isinstance(body, list) else body


def allocation(client, auth, contribution=None):
    query = {"contribution": contribution} if contribution is not None else {}
    response = client.get("/api/allocation", headers=auth, query_string=query)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def put_targets(client, auth, classes=None, assets=None):
    return client.put(
        "/api/allocation/targets",
        headers=auth,
        json={"classes": classes or {}, "assets": assets or {}},
    )


def klass(body, key):
    return next(item for item in body["classes"] if item["asset_class"] == key)


def asset(body, ticker):
    for item in body["classes"]:
        for entry in item["assets"]:
            if entry["ticker"] == ticker:
                return entry
    raise AssertionError(ticker)


@pytest.fixture()
def portfolio(client, auth):
    """Acoes 6.000 (PETR4 4.000 + VALE3 2.000) e FII 4.000: carteira de 10.000."""
    petr = buy(client, auth, "PETR4", 100, 40.0)
    vale = buy(client, auth, "VALE3", 100, 25.0, current=20.0)  # 2.000, abaixo do medio
    buy(client, auth, "MXRF11", 400, 10.0, asset_class="REIT")
    return {"PETR4": petr["asset_id"], "VALE3": vale["asset_id"]}


def test_without_targets_shows_the_current_split_only(client, auth, portfolio):
    body = allocation(client, auth)
    assert body["total"] == 10000
    assert body["has_targets"] is False
    stocks = klass(body, "STOCKS")
    assert stocks["value"] == 6000 and stocks["percent"] == 60
    assert stocks["target_percent"] is None and stocks["gap_value"] is None
    assert asset(body, "PETR4")["percent_in_class"] == pytest.approx(66.67)


def test_class_targets_must_add_up_to_100(client, auth, portfolio):
    response = put_targets(client, auth, classes={"STOCKS": 50, "REIT": 40})
    assert response.status_code == 400
    assert "100%" in response.get_json()["error"]
    assert allocation(client, auth)["has_targets"] is False


def test_asset_targets_must_add_up_to_100_within_their_class(client, auth, portfolio):
    response = put_targets(client, auth, assets={portfolio["PETR4"]: 50, portfolio["VALE3"]: 30})
    assert response.status_code == 400
    assert "Acoes" in response.get_json()["error"]


def test_targets_show_the_gap_per_class_and_per_asset(client, auth, portfolio):
    response = put_targets(
        client, auth,
        classes={"STOCKS": 50, "REIT": 50},
        assets={portfolio["PETR4"]: 50, portfolio["VALE3"]: 50},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    stocks, reits = klass(body, "STOCKS"), klass(body, "REIT")
    assert stocks["target_percent"] == 50 and stocks["diff_percent"] == 10
    assert stocks["gap_value"] == -1000   # 1.000 acima da meta
    assert reits["gap_value"] == 1000
    assert asset(body, "PETR4")["gap_value"] == -1000   # meta 3.000 de 6.000
    assert asset(body, "VALE3")["gap_value"] == 1000


def test_contribution_goes_to_what_is_short_and_adds_up_to_the_cent(client, auth, portfolio):
    put_targets(
        client, auth,
        classes={"STOCKS": 60, "REIT": 40},
        assets={portfolio["PETR4"]: 50, portfolio["VALE3"]: 50},
    )
    # Depois do aporte a carteira tem 11.000: Acoes precisam 600, FII 400.
    body = allocation(client, auth, contribution=1000)
    stocks, reits = klass(body, "STOCKS"), klass(body, "REIT")
    assert stocks["suggested"] == 600 and reits["suggested"] == 400
    # Acoes ficam com 6.600: meta 3.300 cada; PETR4 ja tem 4.000, entao tudo vai para VALE3.
    assert asset(body, "PETR4")["suggested"] == 0
    assert asset(body, "VALE3")["suggested"] == 600

    odd = allocation(client, auth, contribution=100.01)
    assert sum(item["suggested"] for item in odd["classes"]) == pytest.approx(100.01, abs=1e-9)


def test_an_opportunity_is_below_target_and_below_the_average_price(client, auth, portfolio):
    put_targets(
        client, auth,
        classes={"STOCKS": 60, "REIT": 40},
        assets={portfolio["PETR4"]: 50, portfolio["VALE3"]: 50},
    )
    body = allocation(client, auth)
    assert [item["ticker"] for item in body["opportunities"]] == ["VALE3"]
    assert asset(body, "VALE3")["below_average_price"] is True
    assert asset(body, "PETR4")["below_average_price"] is False


def test_put_replaces_the_whole_set(client, auth, portfolio):
    put_targets(client, auth, classes={"STOCKS": 60, "REIT": 40})
    assert allocation(client, auth)["has_class_targets"] is True
    response = put_targets(client, auth)
    assert response.status_code == 200
    assert response.get_json()["has_targets"] is False


def test_a_class_with_a_target_but_no_position_is_listed(client, auth, portfolio):
    put_targets(client, auth, classes={"STOCKS": 50, "REIT": 30, "FIXED_INCOME": 20})
    body = allocation(client, auth, contribution=500)
    fixed = klass(body, "FIXED_INCOME")
    assert fixed["value"] == 0 and fixed["gap_value"] == 2000
    assert fixed["suggested"] > 0


def test_invalid_percentages_are_refused(client, auth, portfolio):
    assert put_targets(client, auth, classes={"STOCKS": 120, "REIT": -20}).status_code == 400
    assert put_targets(client, auth, classes={"CRYPTO": 100}).status_code == 400
    assert client.get("/api/allocation?contribution=-1", headers=auth).status_code == 400


def test_another_users_asset_cannot_get_a_target(client, auth, portfolio, other_user):
    response = client.put(
        "/api/allocation/targets",
        headers=other_user["headers"],
        json={"assets": {portfolio["PETR4"]: 100}},
    )
    assert response.status_code == 400
    put_targets(client, auth, classes={"STOCKS": 60, "REIT": 40})
    stranger = client.get("/api/allocation", headers=other_user["headers"]).get_json()
    assert stranger["classes"] == [] and stranger["has_targets"] is False


def test_concentration_lists_assets_above_10_percent(client, auth, portfolio):
    buy(client, auth, "ITSA4", 100, 5.0)  # 500 de 10.500: 4,76%, fica de fora
    concentration = allocation(client, auth)["concentration"]
    assert concentration["threshold_percent"] == 10
    over = concentration["assets_over_threshold"]
    # Empate em 38,10% desempata pelo ticker.
    assert [item["ticker"] for item in over] == ["MXRF11", "PETR4", "VALE3"]
    assert over[0]["percent"] == pytest.approx(38.1) and over[0]["asset_class"] == "REIT"
    assert over[2]["value"] == 2000 and over[2]["percent"] == pytest.approx(19.05)


def test_exactly_10_percent_is_not_concentrated(client, auth):
    buy(client, auth, "PETR4", 100, 10.0)   # 1.000 = 10%
    buy(client, auth, "BOVA11", 90, 100.0)  # 9.000
    over = allocation(client, auth)["concentration"]["assets_over_threshold"]
    assert [item["ticker"] for item in over] == ["BOVA11"]


def test_foreign_exposure_comes_from_the_asset_currency(client, auth, portfolio):
    concentration = allocation(client, auth)["concentration"]
    assert concentration["has_foreign_exposure"] is False
    assert concentration["foreign_currencies"] == [] and concentration["foreign_percent"] == 0

    response = client.post("/api/investments", headers=auth, json={
        "asset_class": "STOCKS", "ticker_or_name": "AAPL", "currency": "USD",
        "quantity": 2, "average_price": 100.0, "current_price": 100.0,
        "metadata": {"purchase_date": "2025-01-10"},
    })
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    concentration = allocation(client, auth)["concentration"]
    assert concentration["has_foreign_exposure"] is True
    assert concentration["foreign_currencies"] == ["USD"]
    assert concentration["foreign_value"] == 1000  # 2 x US$ 100 x 5,00
    assert concentration["foreign_percent"] == pytest.approx(9.09)


def test_empty_portfolio_has_no_concentration(client, auth):
    concentration = allocation(client, auth)["concentration"]
    assert concentration["assets_over_threshold"] == []
    assert concentration["has_foreign_exposure"] is False
