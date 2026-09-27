"""Indices de comparacao da Rentabilidade (IPCA, Ibovespa, IFIX, IDIV).

services/benchmarks.py e o bloco `benchmarks` de GET /api/investments/returns.
Nenhum teste vai a rede: `download_monthly_history` e trocado em
`services.benchmarks`, `get_history` / `is_configured` no modulo `brapi_client`,
e `fetch_bcb_series` em `services.fixed_income` (onde cada nome e lido).
"""

import importlib
import io
import json
from datetime import date, datetime, timedelta

import pytest

import brapi_client


@pytest.fixture()
def benchmarks_module(app_module):
    return importlib.import_module("services.benchmarks")


@pytest.fixture()
def returns_module(app_module):
    return importlib.import_module("services.returns")


def month_start(months):
    subtract_months = importlib.import_module("dates").subtract_months
    return subtract_months(datetime.now().replace(day=1), months)


def key(months):
    return month_start(months).strftime("%Y-%m")


def iso(months):
    return month_start(months).strftime("%Y-%m-%d")


# --- funcoes puras ---------------------------------------------------------------

class TestPure:
    def test_month_end_close_is_the_last_close_of_the_month(self, benchmarks_module):
        closes = [
            (date(2026, 1, 30), 100.0),
            (date(2026, 1, 15), 90.0),
            (date(2026, 2, 27), 110.0),
            (date(2026, 2, 10), 0),
        ]
        assert benchmarks_module.month_end_closes(closes) == {"2026-01": 100.0, "2026-02": 110.0}

    def test_monthly_return_needs_this_and_the_previous_month(self, benchmarks_module):
        closes = [(date(2025, 12, 31), 100.0), (date(2026, 1, 30), 110.0), (date(2026, 3, 31), 99.0)]
        result = benchmarks_module.monthly_returns_from_closes(
            closes, ["2025-12", "2026-01", "2026-02", "2026-03"],
        )
        # Dezembro nao tem novembro; fevereiro nao tem fechamento; marco nao tem fevereiro.
        assert result == {"2026-01": pytest.approx(0.10)}

    def test_january_looks_back_to_december(self, benchmarks_module):
        assert benchmarks_module.previous_month_key("2026-01") == "2025-12"
        assert benchmarks_module.previous_month_key("2026-10") == "2026-09"

    def test_ipca_monthly(self, benchmarks_module):
        series = [(datetime(2026, 1, 1), 0.005), (datetime(2026, 2, 1), 0.003)]
        result = benchmarks_module.ipca_monthly_returns(series, ["2026-01", "2026-02", "2026-03"])
        assert result == {"2026-01": pytest.approx(0.005), "2026-02": pytest.approx(0.003)}

    def test_close_date_for_current_and_past_months(self, benchmarks_module):
        today = date(2026, 9, 26)
        assert benchmarks_module.close_date_for("2026-09", today) == today
        assert benchmarks_module.close_date_for("2026-02", today) == date(2026, 2, 28)

    def test_accumulation_skips_missing_months(self, returns_module):
        path = returns_module.accumulate_benchmark(
            {"2026-02": 0.10, "2026-03": 0.10}, ["2026-01", "2026-02", "2026-03", "2026-04"],
        )
        assert path[0] is None
        assert path[1] == pytest.approx(0.10)
        assert path[2] == pytest.approx(0.21)
        assert path[3] is None

    def test_summary_complete_and_partial(self, returns_module):
        keys = ["2026-01", "2026-02"]
        full = returns_module.benchmark_summary(
            "IBOV", {"label": "Ibovespa", "monthly": {"2026-01": 0.1, "2026-02": 0.1}}, keys, keys, 0.30,
        )
        assert full["complete"] is True
        assert full["period_percent"] == pytest.approx(21.0)
        assert full["difference_pp"] == pytest.approx(9.0)
        assert full["note"] is None

        partial = returns_module.benchmark_summary(
            "IPCA", {"label": "IPCA", "monthly": {"2026-01": 0.005}}, keys, keys, 0.30,
        )
        assert partial["complete"] is False
        assert partial["available"] is True
        assert partial["months_covered"] == 1
        assert partial["difference_pp"] is None
        assert "ainda nao divulgado" in partial["note"]


# --- rota -------------------------------------------------------------------------

PETR4 = {3: 10.0, 2: 11.0, 1: 12.0, 0: 12.0}
# Ibovespa: fechamento por meses atras (0 = mes atual).
IBOV = {4: 100.0, 3: 100.0, 2: 110.0, 1: 121.0, 0: 121.0}
IPCA_MONTHS = (4, 3, 2, 1)  # o do mes atual ainda nao saiu


class Network:
    """Estado das fontes falsas: o que cada uma devolve e quantas vezes foi chamada."""

    def __init__(self):
        self.index_history = {"^BVSP": {key(n): v for n, v in IBOV.items()}, "IFIX.SA": {key(0): 3700.0}}
        self.index_error = False
        self.brapi_configured = False
        self.brapi = {}
        self.brapi_calls = []
        self.ipca_error = False
        self.index_calls = 0


@pytest.fixture()
def network(app_module, prices_module, monkeypatch, benchmarks_module):
    routes = importlib.import_module("routes.investments")
    fixed_income = importlib.import_module("services.fixed_income")
    integrations = importlib.import_module("integrations")
    fixed_income._index_history_cache.clear()
    benchmarks_module.reset_fetch_throttle()
    integrations.reset_provider_status()
    state = Network()

    def fake_history(tickers, start_date):
        return {ticker: {key(n): price for n, price in PETR4.items()} if ticker == "PETR4" else {} for ticker in tickers}

    def fake_index_history(tickers, start_date):
        state.index_calls += 1
        if state.index_error:
            return {ticker: {} for ticker in tickers}
        return {ticker: dict(state.index_history.get(ticker, {})) for ticker in tickers}

    def fake_bcb(code, start, end=None):
        if code == fixed_income.BCB_SERIES_IPCA:
            if state.ipca_error:
                raise RuntimeError("BCB fora do ar")
            return [(month_start(n), 0.005) for n in IPCA_MONTHS if month_start(n) >= start]
        end = end or datetime.now()
        days, day = [], start
        while day <= end:
            if day.weekday() < 5:
                days.append((day, 0.0004))
            day += timedelta(days=1)
        return days

    def fake_brapi_history(symbol, **kwargs):
        state.brapi_calls.append(symbol)
        if symbol not in state.brapi:
            raise brapi_client.BrapiHTTPError(404, "Nenhum resultado", [symbol])
        return state.brapi[symbol]

    monkeypatch.setattr(prices_module, "yf", None)
    monkeypatch.setattr(routes, "yf", object())
    monkeypatch.setattr(routes, "get_monthly_history", fake_history)
    monkeypatch.setattr(fixed_income, "fetch_bcb_series", fake_bcb)
    monkeypatch.setattr(benchmarks_module, "download_monthly_history", fake_index_history)
    monkeypatch.setattr(brapi_client, "is_configured", lambda: state.brapi_configured)
    monkeypatch.setattr(brapi_client, "get_history", fake_brapi_history)
    return state


def buy_petr4(client, headers):
    response = client.post("/api/investments", headers=headers, json={
        "asset_class": "STOCKS",
        "ticker_or_name": "PETR4",
        "quantity": 100,
        "average_price": 10.0,
        "current_price": 12.0,
        "metadata": {"purchase_date": iso(3)},
    })
    assert response.status_code in (200, 201), response.get_data(as_text=True)


def returns(client, headers, **params):
    response = client.get("/api/investments/returns", headers=headers, query_string=params)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def by_code(body):
    return {item["code"]: item for item in body["benchmarks"]}


class TestEndpoint:
    def test_benchmarks_are_aligned_to_the_portfolio_months(self, client, auth, network):
        buy_petr4(client, auth)
        body = returns(client, auth, months=3)
        assert [item["code"] for item in body["benchmarks"]] == ["IPCA", "IBOV", "IFIX", "IDIV"]
        assert [item["month_key"] for item in body["series"]] == [key(2), key(1), key(0)]

        ibov = by_code(body)["IBOV"]
        # 100 -> 110 -> 121 -> 121: +10%, +10%, 0%.
        assert ibov["complete"] is True
        assert ibov["period_percent"] == pytest.approx(21.0)
        assert ibov["difference_pp"] == pytest.approx(body["twr_percent"] - 21.0, abs=0.01)
        path = [item["benchmarks"]["IBOV"]["accumulated_percent"] for item in body["series"]]
        assert path == [pytest.approx(10.0), pytest.approx(21.0), pytest.approx(21.0)]
        assert body["series"][0]["benchmarks"]["IBOV"]["return_percent"] == pytest.approx(10.0)

        # CDI segue como antes.
        assert body["cdi_available"] is True

    def test_ipca_accumulates_monthly_and_the_current_month_is_pending(self, client, auth, network):
        buy_petr4(client, auth)
        ipca = by_code(returns(client, auth, months=3))["IPCA"]
        assert ipca["months_covered"] == 2
        assert ipca["complete"] is False
        assert ipca["period_percent"] == pytest.approx(round((1.005 ** 2 - 1) * 100, 2))
        assert "ainda nao divulgado" in ipca["note"]

    def test_an_index_without_history_is_unavailable_with_a_note(self, client, auth, network):
        buy_petr4(client, auth)
        body = returns(client, auth, months=3)
        items = by_code(body)
        # IDIV: nenhum provedor devolveu nada.
        assert items["IDIV"]["available"] is False
        assert items["IDIV"]["period_percent"] is None
        assert "Sem cotacao do IDIV" in items["IDIV"]["note"]
        assert all(item["benchmarks"]["IDIV"]["accumulated_percent"] is None for item in body["series"])
        # IFIX: so o fechamento de hoje, guardado; sem o mes anterior nao ha retorno.
        assert items["IFIX"]["available"] is False
        assert "guarda o fechamento" in items["IFIX"]["note"]

    def test_everything_offline_still_answers(self, client, auth, network):
        network.index_error = True
        network.ipca_error = True
        buy_petr4(client, auth)
        body = returns(client, auth, months=3)
        # A carteira (10 -> 11 -> 12 -> 12) continua calculada.
        assert body["twr_percent"] == pytest.approx(20.0, abs=0.01)
        assert all(item["available"] is False for item in body["benchmarks"])
        assert by_code(body)["IPCA"]["note"] == "O BCB nao respondeu o IPCA."
        status = importlib.import_module("integrations").provider_snapshot("yfinance")
        assert status.get("consecutive_failures", 0) >= 1

    def test_brapi_fills_in_when_yfinance_has_nothing(self, client, auth, network):
        network.index_error = True
        network.brapi_configured = True
        network.brapi = {
            "^BVSP": [
                (month_start(3).date() + timedelta(days=27), 100.0),
                (month_start(2).date() + timedelta(days=27), 110.0),
                (month_start(1).date() + timedelta(days=27), 121.0),
                (date.today(), 133.1),
            ],
        }
        buy_petr4(client, auth)
        ibov = by_code(returns(client, auth, months=3))["IBOV"]
        assert ibov["period_percent"] == pytest.approx(33.1)
        assert ibov["source"] == "brapi"
        # A brapi nao conhece o IDIV: nem e perguntada.
        assert "IDIV" not in network.brapi_calls
        assert importlib.import_module("integrations").provider_snapshot("brapi").get("last_success")

    def test_closes_are_cached_and_reused_offline(self, client, auth, network, benchmarks_module):
        buy_petr4(client, auth)
        first = by_code(returns(client, auth, months=3))["IBOV"]
        assert first["source"] == "yfinance"
        assert network.index_calls == 1

        # Dentro do TTL nao busca de novo.
        returns(client, auth, months=3)
        assert network.index_calls == 1

        # Sem rede depois do TTL: le o que ficou guardado.
        benchmarks_module.reset_fetch_throttle()
        network.index_error = True
        again = by_code(returns(client, auth, months=3))["IBOV"]
        assert again["period_percent"] == pytest.approx(21.0)
        assert again["source"] == "cache"

    def test_stored_closes_belong_to_their_user(self, client, auth, other_user, network, benchmarks_module):
        buy_petr4(client, auth)
        assert by_code(returns(client, auth, months=3))["IBOV"]["available"] is True

        # O outro usuario, sem rede, nao ve os fechamentos guardados pelo primeiro.
        network.index_error = True
        buy_petr4(client, other_user["headers"])
        assert by_code(returns(client, other_user["headers"], months=3))["IBOV"]["available"] is False

        db = importlib.import_module("db")
        with db.get_db() as conn:
            mine = benchmarks_module.stored_closes(conn, other_user["id"], "IBOV", date(2000, 1, 1))
        assert mine == []

    def test_a_month_close_is_overwritten_by_a_later_fetch(self, client, auth, user, network, benchmarks_module):
        db = importlib.import_module("db")
        today = date.today()
        with db.get_db() as conn:
            benchmarks_module.store_closes(conn, user["id"], "IFIX", [(today, 3000.0)], "yfinance")
            benchmarks_module.store_closes(conn, user["id"], "IFIX", [(today, 3100.0)], "brapi")
            rows = benchmarks_module.stored_closes(conn, user["id"], "IFIX", today)
        assert rows == [(today, 3100.0)]


# --- brapi_client.get_history --------------------------------------------------------

class _FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False


def test_brapi_get_history_parses_daily_closes(monkeypatch):
    monkeypatch.setenv("BRAPI_TOKEN", "token-de-teste")
    calls = []
    payload = {"results": [{"symbol": "^BVSP", "historicalDataPrice": [
        {"date": 1790305200, "close": 183477.0},
        {"date": 1790218800, "close": 183966.0},
        {"date": None, "close": 1.0},
        {"date": 1790391600, "close": None},
    ]}]}

    def fake_urlopen(request, timeout=None):
        calls.append(request.full_url)
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(brapi_client.urllib.request, "urlopen", fake_urlopen)
    closes = brapi_client.get_history("^bvsp")
    assert [close for _, close in closes] == [183966.0, 183477.0]
    assert closes[0][0] < closes[1][0]
    assert "/quote/%5EBVSP?" in calls[0]
    assert "range=3mo" in calls[0] and "interval=1d" in calls[0]


def test_brapi_get_history_unknown_symbol_is_a_typed_error(monkeypatch):
    import urllib.error

    monkeypatch.setenv("BRAPI_TOKEN", "token-de-teste")

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, io.BytesIO(b'{"message":"Nenhum resultado"}'))

    monkeypatch.setattr(brapi_client.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(brapi_client.BrapiHTTPError) as excinfo:
        brapi_client.get_history("IDIV")
    assert excinfo.value.status == 404
