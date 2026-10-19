"""Historico dos graficos: o que vai a rede e quando (Evolucao e Rentabilidade).

Os fechamentos diarios (Yahoo) e as series do BCB ficam em cache por ticker /
por serie, desde o piso de `history_fetch_floor()`: trocar de periodo ou de
classe le o cache, recortado na janela pedida. A rentabilidade pede as buscas
de uma vez, entao espera a mais lenta, nao a soma.

A rede e trocada onde e lida: `download_daily_history` em `services.prices`
(o `get_daily_history` de verdade roda, com o cache), `fetch_bcb_series` em
`services.fixed_income` e `download_monthly_history` em `services.benchmarks`.
"""

import importlib
import threading
from datetime import date, datetime, timedelta

import pytest


def fake_daily(tickers, start_date, calls):
    """Um fechamento por dia util desde `start_date`; o preco depende so do dia."""
    calls.append((tuple(tickers), start_date))
    start = date.fromisoformat(start_date)
    prices = {}
    for ticker in tickers:
        days, day = {}, start
        while day <= date.today():
            if day.weekday() < 5:
                days[day.isoformat()] = 10.0 + day.toordinal() % 7
            day += timedelta(days=1)
        prices[ticker] = days
    splits = {ticker: [(start_date, 2.0)] if ticker == "PETR4" else [] for ticker in tickers}
    return {"prices": prices, "splits": splits}


def fake_bcb(code, start, end=None, calls=None):
    if calls is not None:
        calls.append((code, start))
    end = end or datetime.now()
    days, day = [], start
    while day <= end:
        if day.weekday() < 5:
            days.append((day, 0.0004))
        day += timedelta(days=1)
    return days


@pytest.fixture()
def history_cache(prices_module, fixed_income_module):
    prices_module._daily_history_cache.clear()
    fixed_income_module._index_history_cache.clear()
    yield
    prices_module._daily_history_cache.clear()
    fixed_income_module._index_history_cache.clear()


class TestDailyHistoryCache:
    def test_one_download_serves_every_window(self, prices_module, history_cache, monkeypatch):
        calls = []
        monkeypatch.setattr(prices_module, "download_daily_history", lambda tickers, start: fake_daily(tickers, start, calls))
        year_ago = (date.today() - timedelta(days=365)).isoformat()
        month_ago = (date.today() - timedelta(days=30)).isoformat()

        first = prices_module.get_daily_history(["PETR4", "VALE3"], year_ago)
        # Baixa desde o piso, nao desde a janela.
        assert calls == [(("PETR4", "VALE3"), prices_module.history_fetch_floor().isoformat())]
        assert min(first["prices"]["PETR4"]) >= year_ago

        # Janela menor e um ticker so: le o cache.
        shorter = prices_module.get_daily_history(["vale3"], month_ago)
        assert len(calls) == 1
        assert shorter["prices"]["VALE3"] == fake_daily(["VALE3"], month_ago, [])["prices"]["VALE3"]

    def test_the_slice_matches_a_download_from_the_window(self, prices_module, history_cache, monkeypatch):
        calls = []
        monkeypatch.setattr(prices_module, "download_daily_history", lambda tickers, start: fake_daily(tickers, start, calls))
        prices_module.get_daily_history(["PETR4"], (date.today() - timedelta(days=700)).isoformat())

        window = (date.today() - timedelta(days=90)).isoformat()
        cached = prices_module.get_daily_history(["PETR4"], window)
        assert len(calls) == 1
        assert cached["prices"]["PETR4"] == fake_daily(["PETR4"], window, [])["prices"]["PETR4"]
        # O desdobramento do inicio do piso fica fora da janela, como num download dela.
        assert cached["splits"]["PETR4"] == []

    def test_only_the_missing_ticker_is_downloaded(self, prices_module, history_cache, monkeypatch):
        calls = []
        monkeypatch.setattr(prices_module, "download_daily_history", lambda tickers, start: fake_daily(tickers, start, calls))
        start = (date.today() - timedelta(days=200)).isoformat()
        prices_module.get_daily_history(["PETR4"], start)
        both = prices_module.get_daily_history(["PETR4", "ITSA4"], start)
        assert [tickers for tickers, _ in calls] == [("PETR4",), ("ITSA4",)]
        assert set(both["prices"]) == {"PETR4", "ITSA4"}

    def test_a_start_before_the_cache_downloads_again(self, prices_module, history_cache, monkeypatch):
        calls = []
        monkeypatch.setattr(prices_module, "download_daily_history", lambda tickers, start: fake_daily(tickers, start, calls))
        prices_module.get_daily_history(["PETR4"], (date.today() - timedelta(days=30)).isoformat())
        older = (prices_module.history_fetch_floor() - timedelta(days=400)).isoformat()
        prices_module.get_daily_history(["PETR4"], older)
        assert calls[-1] == (("PETR4",), older)

    def test_a_stale_entry_is_served_and_refreshed_in_the_background(self, prices_module, history_cache, monkeypatch):
        calls = []
        monkeypatch.setattr(prices_module, "download_daily_history", lambda tickers, start: fake_daily(tickers, start, calls))
        start = (date.today() - timedelta(days=30)).isoformat()
        first = prices_module.get_daily_history(["PETR4"], start)
        prices_module._daily_history_cache["PETR4"]["updated_at"] -= prices_module.HISTORY_CACHE_TTL_SECONDS + 1

        # O pedido nao espera: le o cache vencido e agenda o download.
        release = threading.Event()
        def slow(tickers, start_date):
            release.wait(5)
            return fake_daily(tickers, start_date, calls)
        monkeypatch.setattr(prices_module, "download_daily_history", slow)
        served = prices_module.get_daily_history(["PETR4"], start)
        assert served["prices"] == first["prices"]
        assert len(calls) == 1

        release.set()
        prices_module.wait_history_refreshes(timeout=5)
        assert len(calls) == 2
        assert prices_module.history_cache_state(
            prices_module.time.time() - prices_module._daily_history_cache["PETR4"]["updated_at"],
        ) == "fresh"

    def test_a_failed_background_refresh_keeps_the_old_history(self, prices_module, history_cache, monkeypatch):
        monkeypatch.setattr(prices_module, "download_daily_history", lambda tickers, start: fake_daily(tickers, start, []))
        start = (date.today() - timedelta(days=30)).isoformat()
        first = prices_module.get_daily_history(["PETR4"], start)
        prices_module._daily_history_cache["PETR4"]["updated_at"] -= prices_module.HISTORY_CACHE_TTL_SECONDS + 1

        # Yahoo fora: o download devolve o ticker sem fechamentos.
        monkeypatch.setattr(
            prices_module, "download_daily_history",
            lambda tickers, start_date: {"prices": {t: {} for t in tickers}, "splits": {t: [] for t in tickers}},
        )
        prices_module.get_daily_history(["PETR4"], start)
        prices_module.wait_history_refreshes(timeout=5)
        assert prices_module.get_daily_history(["PETR4"], start)["prices"] == first["prices"]

    def test_an_entry_past_the_stale_limit_downloads_in_the_request(self, prices_module, history_cache, monkeypatch):
        calls = []
        monkeypatch.setattr(prices_module, "download_daily_history", lambda tickers, start: fake_daily(tickers, start, calls))
        start = (date.today() - timedelta(days=30)).isoformat()
        prices_module.get_daily_history(["PETR4"], start)
        prices_module._daily_history_cache["PETR4"]["updated_at"] -= prices_module.HISTORY_CACHE_STALE_MAX_SECONDS + 1
        prices_module.get_daily_history(["PETR4"], start)
        assert len(calls) == 2

    def test_the_caller_cannot_change_the_cache(self, prices_module, history_cache, monkeypatch):
        monkeypatch.setattr(prices_module, "download_daily_history", lambda tickers, start: fake_daily(tickers, start, []))
        start = (date.today() - timedelta(days=30)).isoformat()
        prices_module.get_daily_history(["PETR4"], start)["prices"]["PETR4"].clear()
        assert prices_module.get_daily_history(["PETR4"], start)["prices"]["PETR4"]


class TestBcbSeriesCache:
    def test_the_cdi_is_fetched_once_for_any_later_start(self, fixed_income_module, history_cache, monkeypatch):
        calls = []
        monkeypatch.setattr(fixed_income_module, "fetch_bcb_series", lambda code, start, end=None: fake_bcb(code, start, end, calls))
        year_ago = datetime.now() - timedelta(days=365)
        fixed_income_module.cdi_since(year_ago)
        recent = datetime.combine(date.today() - timedelta(days=20), datetime.min.time())
        series = fixed_income_module.cdi_since(recent)
        assert len(calls) == 1
        assert series == fake_bcb(fixed_income_module.BCB_SERIES_CDI, recent)

    def test_a_stale_cdi_is_served_and_refreshed_in_the_background(self, fixed_income_module, prices_module, history_cache, monkeypatch):
        calls = []
        monkeypatch.setattr(fixed_income_module, "fetch_bcb_series", lambda code, start, end=None: fake_bcb(code, start, end, calls))
        year_ago = datetime.now() - timedelta(days=365)
        fixed_income_module.cdi_since(year_ago)
        stamp, since, series = fixed_income_module._index_history_cache["cdi"]
        fixed_income_module._index_history_cache["cdi"] = (stamp - fixed_income_module.HISTORY_CACHE_TTL_SECONDS - 1, since, series)

        def down(code, start, end=None):
            calls.append((code, start))
            raise RuntimeError("BCB fora")
        monkeypatch.setattr(fixed_income_module, "fetch_bcb_series", down)
        assert fixed_income_module.cdi_since(year_ago) == [item for item in series if item[0] >= year_ago.replace(hour=0, minute=0, second=0, microsecond=0)]
        prices_module.wait_history_refreshes(timeout=5)
        # A busca rodou, falhou, e o cache antigo continua la.
        assert len(calls) == 2
        assert fixed_income_module._index_history_cache["cdi"][2] == series

    def test_ipca_is_shared_with_the_benchmarks(self, fixed_income_module, history_cache, monkeypatch):
        benchmarks = importlib.import_module("services.benchmarks")
        calls = []
        monkeypatch.setattr(fixed_income_module, "fetch_bcb_series", lambda code, start, end=None: fake_bcb(code, start, end, calls))
        first_purchase = datetime.now() - timedelta(days=400)
        fixed_income_module.index_history(first_purchase, True)
        assert [code for code, _ in calls] == [fixed_income_module.BCB_SERIES_CDI, fixed_income_module.BCB_SERIES_IPCA]

        window = date.today().replace(day=1) - timedelta(days=90)
        benchmarks.start_ipca_fetch(window).result(timeout=5)
        assert len(calls) == 2


# --- rota -------------------------------------------------------------------------

@pytest.fixture()
def network(app_module, prices_module, fixed_income_module, history_cache, monkeypatch):
    routes = importlib.import_module("routes.investments")
    benchmarks = importlib.import_module("services.benchmarks")
    benchmarks.reset_fetch_throttle()
    state = {"daily": [], "bcb": [], "index": [], "barrier": None}

    def daily(tickers, start):
        if state["barrier"]:
            state["barrier"].wait()
        return fake_daily(tickers, start, state["daily"])

    def bcb(code, start, end=None):
        if state["barrier"] and code == fixed_income_module.BCB_SERIES_CDI:
            state["barrier"].wait()
        return fake_bcb(code, start, end, state["bcb"])

    def index_closes(tickers, start):
        state["index"].append(start)
        return {}

    monkeypatch.setattr(prices_module, "yf", None)
    monkeypatch.setattr(routes, "yf", object())
    monkeypatch.setattr(prices_module, "download_daily_history", daily)
    monkeypatch.setattr(fixed_income_module, "fetch_bcb_series", bcb)
    monkeypatch.setattr(benchmarks, "download_monthly_history", index_closes)
    monkeypatch.setattr(benchmarks.brapi_client, "is_configured", lambda: False)
    return state


def buy(client, auth, ticker, months_ago):
    when = (date.today() - timedelta(days=30 * months_ago)).isoformat()
    response = client.post("/api/investments", headers=auth, json={
        "asset_class": "STOCKS", "ticker_or_name": ticker, "quantity": 10,
        "average_price": 10.0, "current_price": 12.0, "metadata": {"purchase_date": when},
    })
    assert response.status_code in (200, 201), response.get_data(as_text=True)


class TestRoutes:
    def test_switching_period_and_class_reads_the_cache(self, client, auth, network):
        buy(client, auth, "PETR4", 20)
        for params in ({"months": 12}, {"months": 24}, {"months": "all"}, {"months": 6, "asset_class": "STOCKS"}):
            response = client.get("/api/investments/returns", headers=auth, query_string=params)
            assert response.status_code == 200, response.get_data(as_text=True)
        for months in (12, 60):
            assert client.get(f"/api/investments/history?months={months}", headers=auth).status_code == 200

        assert len(network["daily"]) == 1
        # O CDI da janela uma vez; os fechamentos dos indices uma vez, desde o piso.
        cdi = importlib.import_module("services.fixed_income").BCB_SERIES_CDI
        assert [code for code, _ in network["bcb"]].count(cdi) == 1
        floor = importlib.import_module("services.prices").history_fetch_floor()
        assert network["index"] == [floor.strftime("%Y-%m-%d")]

    def test_prices_and_the_cdi_are_fetched_at_the_same_time(self, client, auth, network):
        buy(client, auth, "PETR4", 3)
        # Cada busca so termina quando a outra tambem comecou: em sequencia, a
        # barreira estoura e a resposta sai sem precos ou sem CDI.
        network["barrier"] = threading.Barrier(2, timeout=3)
        body = client.get("/api/investments/returns?months=6", headers=auth).get_json()
        assert not network["barrier"].broken
        assert body["cdi_available"] is True
        assert body["twr_percent"] is not None


def test_a_narrower_fetch_finishing_last_keeps_the_wider_cdi_cache(fixed_income_module, history_cache, monkeypatch):
    floor = importlib.import_module("services.prices").history_fetch_floor()
    floor = datetime(floor.year, floor.month, floor.day)
    old_purchase = datetime(floor.year - 3, 1, 2)
    calls = []

    def racing(code, start, end=None):
        # O CDI da janela (desde o piso) termina depois do da renda fixa (desde 3 anos antes).
        if start == floor:
            fixed_income_module.cdi_since(old_purchase)
        return fake_bcb(code, start, end, calls)

    monkeypatch.setattr(fixed_income_module, "fetch_bcb_series", racing)
    fixed_income_module.cdi_since(datetime.now() - timedelta(days=60))
    assert fixed_income_module._index_history_cache["cdi"][1] == old_purchase
    fixed_income_module.cdi_since(old_purchase)
    assert len(calls) == 2
