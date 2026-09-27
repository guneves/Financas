"""Alocacao por setor (022): setor por ativo, preenchido pela brapi ou a mao.

O que estes testes fixam:

- brapi_client.get_sectors le a /quote/list pagina a pagina, para quando achou
  tudo, e guarda a lista em memoria (a segunda leitura nao vai a rede);
- a leitura da alocacao por setor preenche, uma vez, os ativos em carteira
  nunca consultados: acao pelo setor traduzido, FII pelo segmento; renda fixa
  e exterior nao vao a brapi e ficam em "Sem setor";
- os setores somam o valor liquido da carteira, e "Sem setor" vem por ultimo;
- o setor manual vence a brapi (nem o "Buscar setores" sobrescreve), e setor
  vazio devolve o ativo ao automatico;
- brapi sem token ou fora do ar nao quebra a leitura;
- o filtro por classe;
- nada de outro usuario aparece nem pode ser editado.
"""

import importlib
import io
import json
from datetime import timedelta

import pytest

import brapi_client


# ---------------------------------------------------------------------------
# brapi_client.get_sectors (modulo puro, urlopen substituido)
# ---------------------------------------------------------------------------

class _FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False


def list_item(symbol, sector, subsector=None, sub_type="stock"):
    return {"stock": symbol, "name": symbol, "sector": sector, "subsector": subsector,
            "type": "fund" if sub_type == "fii" else "stock", "subType": sub_type}


@pytest.fixture()
def list_pages(monkeypatch):
    """Duas paginas da /quote/list; devolve a lista de URLs pedidas."""
    pages = {
        1: [list_item("PETR4", "Energy Minerals", "Petróleo e Gás Integrado"),
            list_item("ITUB4", "Finance", "Bancos")],
        2: [list_item("HGLG11", "Finance", "Logística", "fii")],
    }
    calls = []

    def _urlopen(request, timeout=None):
        calls.append(request.full_url)
        page = int(request.full_url.split("page=")[1].split("&")[0])
        body = {"stocks": pages.get(page, []), "hasNextPage": page < len(pages)}
        return _FakeResponse(json.dumps(body).encode("utf-8"))

    monkeypatch.setenv("BRAPI_TOKEN", "token-de-teste")
    monkeypatch.setattr(brapi_client.urllib.request, "urlopen", _urlopen)
    brapi_client.clear_sector_cache()
    yield calls
    brapi_client.clear_sector_cache()


def test_get_sectors_stops_at_the_page_that_has_everything(list_pages):
    found = brapi_client.get_sectors(["petr4", "ITUB4"])
    assert set(found) == {"PETR4", "ITUB4"}
    assert found["PETR4"].sector == "Energy Minerals"
    assert found["ITUB4"].subsector == "Bancos"
    assert len(list_pages) == 1 and "/quote/list" in list_pages[0]


def test_get_sectors_walks_the_pages_and_caches_the_list(list_pages):
    found = brapi_client.get_sectors(["HGLG11", "XPTO3"])
    assert set(found) == {"HGLG11"}          # ticker desconhecido nao e erro
    assert found["HGLG11"].sub_type == "fii"
    assert len(list_pages) == 2
    # A lista inteira esta em memoria: nem o desconhecido volta a rede.
    brapi_client.get_sectors(["PETR4", "XPTO3"])
    assert len(list_pages) == 2
    brapi_client.get_sectors(["PETR4"], force=True)
    assert len(list_pages) == 3


# ---------------------------------------------------------------------------
# Alocacao por setor (rotas)
# ---------------------------------------------------------------------------

BRAPI_SECTORS = {
    "PETR4": brapi_client.SectorInfo("PETR4", "Energy Minerals", "Petróleo e Gás Integrado", "stock", "stock"),
    "ITUB4": brapi_client.SectorInfo("ITUB4", "Finance", "Bancos", "stock", "stock"),
    "HGLG11": brapi_client.SectorInfo("HGLG11", "Finance", "Logística", "fund", "fii"),
}


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
    prices = importlib.import_module("services.prices")
    monkeypatch.setattr(prices, "download_close_prices", lambda symbols, **kwargs: {})
    # Nenhuma cotacao pela brapi nestes testes: so o setor e simulado.
    monkeypatch.setattr(brapi_client, "get_stock_quotes", lambda *args, **kwargs: {})


@pytest.fixture()
def brapi(monkeypatch):
    """brapi configurada, com a lista de setores acima; conta as consultas."""
    calls = []

    def get_sectors(symbols, *, force=False, timeout=None, now=None):
        calls.append({"symbols": list(symbols), "force": force})
        return {symbol: BRAPI_SECTORS[symbol] for symbol in symbols if symbol in BRAPI_SECTORS}

    monkeypatch.setattr(brapi_client, "is_configured", lambda: True)
    monkeypatch.setattr(brapi_client, "get_sectors", get_sectors)
    return calls


def buy(client, auth, ticker, quantity, price, *, asset_class="STOCKS", currency=None):
    payload = {
        "asset_class": asset_class,
        "ticker_or_name": ticker,
        "quantity": quantity,
        "average_price": price,
        "current_price": price,
        "metadata": {"purchase_date": "2025-01-10"},
    }
    if currency:
        payload["currency"] = currency
    response = client.post("/api/investments", headers=auth, json=payload)
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    body = response.get_json()
    return body[0] if isinstance(body, list) else body


def sectors(client, auth, asset_class=None):
    query = {"asset_class": asset_class} if asset_class else {}
    response = client.get("/api/allocation/sectors", headers=auth, query_string=query)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def bucket(body, label):
    return next(item for item in body["sectors"] if item["label"] == label)


def set_sector(client, auth, asset_id, sector, segment=None):
    return client.patch(f"/api/assets/{asset_id}/sector", headers=auth,
                        json={"sector": sector, "segment": segment})


@pytest.fixture()
def portfolio(client, auth):
    """PETR4 4.000, ITUB4 2.000, HGLG11 3.000, CDB 1.000, AAPL (US$ 10 x 10 x 5,00 = 500)."""
    return {
        "PETR4": buy(client, auth, "PETR4", 100, 40.0)["asset_id"],
        "ITUB4": buy(client, auth, "ITUB4", 100, 20.0)["asset_id"],
        "HGLG11": buy(client, auth, "HGLG11", 20, 150.0, asset_class="REIT")["asset_id"],
        "CDB": buy(client, auth, "CDB BANCO X", 1, 1000.0, asset_class="FIXED_INCOME")["asset_id"],
        "AAPL": buy(client, auth, "AAPL", 10, 10.0, currency="USD")["asset_id"],
    }


def test_reading_fills_sectors_from_brapi_once(client, auth, portfolio, brapi):
    body = sectors(client, auth)
    assert body["fetch"]["status"] == "ok"
    # So acao/FII em reais vao a brapi — nem renda fixa nem o ativo em dolar.
    assert sorted(brapi[0]["symbols"]) == ["HGLG11", "ITUB4", "PETR4"]

    petroleo = bucket(body, "Petróleo e gás")
    assert petroleo["value"] == 4000
    assert petroleo["assets"][0]["segment"] == "Petróleo e Gás Integrado"
    assert petroleo["assets"][0]["source"] == "BRAPI"
    assert bucket(body, "Financeiro")["value"] == 2000
    # FII: o setor e o segmento, nao o "Finance" da brapi.
    assert bucket(body, "Logística")["classes"] == ["REIT"]

    # Ja consultados: a proxima leitura nao pergunta de novo.
    sectors(client, auth)
    assert len(brapi) == 1


def test_sectors_add_up_to_the_net_portfolio_and_no_sector_is_last(
    client, auth, user, portfolio, brapi, portfolio_module
):
    body = sectors(client, auth)
    snapshot = portfolio_module.build_portfolio_snapshot(user["id"])
    assert body["total"] == pytest.approx(snapshot["current_net_balance"], abs=0.01)
    assert sum(item["value"] for item in body["sectors"]) == pytest.approx(body["total"], abs=0.01)

    last = body["sectors"][-1]
    assert last["sector"] is None and last["label"] == "Sem setor"
    assert sorted(item["ticker"] for item in last["assets"]) == ["AAPL", "CDB BANCO X"]
    assert body["unassigned_value"] == last["value"]
    assert sum(item["percent"] for item in body["sectors"]) == pytest.approx(100, abs=0.05)


def test_a_manual_sector_wins_over_brapi(client, auth, portfolio, brapi):
    assert set_sector(client, auth, portfolio["CDB"], "Bancos", "CDB").status_code == 200
    assert set_sector(client, auth, portfolio["PETR4"], "Energia").status_code == 200

    body = sectors(client, auth)
    assert "PETR4" not in brapi[0]["symbols"]     # manual nem e consultado
    energia = bucket(body, "Energia")
    assert energia["assets"][0]["ticker"] == "PETR4"
    assert energia["assets"][0]["source"] == "MANUAL"
    assert bucket(body, "Bancos")["assets"][0]["segment"] == "CDB"

    # "Buscar setores" pergunta de novo por todos, menos os manuais.
    refreshed = client.post("/api/allocation/sectors/refresh", headers=auth)
    assert refreshed.status_code == 200
    assert brapi[-1]["force"] is True
    assert "PETR4" not in brapi[-1]["symbols"]
    assert bucket(refreshed.get_json(), "Energia")["value"] == 4000


def test_an_empty_sector_hands_the_asset_back_to_brapi(client, auth, portfolio, brapi):
    sectors(client, auth)
    set_sector(client, auth, portfolio["PETR4"], "Energia")
    assert set_sector(client, auth, portfolio["PETR4"], "  ").status_code == 200

    body = sectors(client, auth)
    assert brapi[-1]["symbols"] == ["PETR4"]      # so ele volta a ser consultado
    assert bucket(body, "Petróleo e gás")["assets"][0]["source"] == "BRAPI"


def test_without_a_token_everything_is_unassigned_and_retried_later(client, auth, portfolio, monkeypatch):
    monkeypatch.setattr(brapi_client, "is_configured", lambda: False)
    body = sectors(client, auth)
    assert body["fetch"]["status"] == "unconfigured"
    assert [item["label"] for item in body["sectors"]] == ["Sem setor"]
    assert body["unassigned_percent"] == 100

    # Nada foi marcado como consultado: com o token, a leitura preenche.
    calls = []
    monkeypatch.setattr(brapi_client, "is_configured", lambda: True)
    monkeypatch.setattr(
        brapi_client, "get_sectors",
        lambda symbols, **kwargs: calls.append(symbols) or {s: BRAPI_SECTORS[s] for s in symbols if s in BRAPI_SECTORS},
    )
    assert bucket(sectors(client, auth), "Financeiro")["value"] == 2000
    assert len(calls) == 1


def test_a_brapi_failure_does_not_break_the_reading(client, auth, portfolio, monkeypatch):
    def broken(symbols, **kwargs):
        raise brapi_client.BrapiUnavailableError("fora do ar")

    monkeypatch.setattr(brapi_client, "is_configured", lambda: True)
    monkeypatch.setattr(brapi_client, "get_sectors", broken)
    body = sectors(client, auth)
    assert body["fetch"]["status"] == "error"
    assert body["total"] > 0
    assert [item["label"] for item in body["sectors"]] == ["Sem setor"]


def test_a_ticker_brapi_does_not_know_is_not_asked_again(client, auth, brapi):
    buy(client, auth, "WEGE3", 10, 10.0)   # fora da lista simulada acima
    assert bucket(sectors(client, auth), "Sem setor")["value"] == 100
    sectors(client, auth)
    assert len(brapi) == 1


def test_the_class_filter(client, auth, portfolio, brapi):
    body = sectors(client, auth, asset_class="REIT")
    assert body["asset_class"] == "REIT"
    assert body["total"] == 3000
    assert [item["label"] for item in body["sectors"]] == ["Logística"]
    assert body["sectors"][0]["percent"] == 100


def test_invalid_manual_sectors_are_refused(client, auth, portfolio):
    assert client.patch(f"/api/assets/{portfolio['PETR4']}/sector", headers=auth, json={}).status_code == 400
    assert set_sector(client, auth, portfolio["PETR4"], "x" * 61).status_code == 400
    assert set_sector(client, auth, "nao-existe", "Energia").status_code == 400


def test_another_users_assets_are_invisible_and_untouchable(client, auth, portfolio, brapi, other_user):
    response = set_sector(client, other_user["headers"], portfolio["PETR4"], "Invasao")
    assert response.status_code == 400

    stranger = sectors(client, other_user["headers"])
    assert stranger["total"] == 0 and stranger["sectors"] == []
    assert "Invasao" not in stranger["suggestions"]

    # O mesmo ticker em outro usuario tem o setor dele.
    other_petr = buy(client, other_user["headers"], "PETR4", 10, 40.0)["asset_id"]
    set_sector(client, other_user["headers"], other_petr, "Setor do outro")
    mine = sectors(client, auth)
    assert bucket(mine, "Petróleo e gás")["value"] == 4000
    assert all(item["label"] != "Setor do outro" for item in mine["sectors"])
    assert "Setor do outro" not in mine["suggestions"]
