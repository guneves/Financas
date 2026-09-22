"""Correcao da renda fixa por indexador: % do CDI, CDI+, IPCA+ e prefixado.

As funcoes sao puras -- recebem as series do BCB ja buscadas -- para que as
regras sejam testadas sem rede.
"""

from datetime import datetime

import pytest


def test_legacy_metadata_is_read_as_percent_of_cdi(app_module):
    assert app_module.fixed_income_rate_terms({"cdi_percentage": 1.1}) == ("CDI", 1.1)


def test_rate_terms_by_indexer(app_module):
    terms = app_module.fixed_income_rate_terms
    assert terms({"rate_type": "POS", "indexer": "CDI_PLUS", "annual_rate": 0.015}) == ("CDI_PLUS", 0.015)
    assert terms({"rate_type": "POS", "indexer": "IPCA", "annual_rate": 0.065}) == ("IPCA", 0.065)
    # Prefixado ignora um indexador que tenha sobrado no metadata.
    assert terms({"rate_type": "PRE", "indexer": "CDI", "annual_rate": 0.125}) == ("PRE", 0.125)


def test_missing_or_invalid_rate_is_rejected(app_module):
    terms = app_module.fixed_income_rate_terms
    assert terms({}) == (None, None)
    assert terms({"rate_type": "PRE"}) == (None, None)
    assert terms({"rate_type": "POS", "indexer": "CDI", "cdi_percentage": 0}) == (None, None)
    assert terms({"rate_type": "POS", "indexer": "SELIC", "annual_rate": 0.1}) == (None, None)


def test_percent_of_cdi_compounds_each_day(app_module):
    factor = app_module.fixed_income_accrual_factor("CDI", 1.1, [0.0005, 0.0005])
    assert factor == pytest.approx((1 + 0.0005 * 1.1) ** 2)


def test_prefixed_uses_252_business_days(app_module):
    # 252 dias uteis = um ano: o fator e exatamente a taxa anual.
    factor = app_module.fixed_income_accrual_factor("PRE", 0.12, [0.0004] * 252)
    assert factor == pytest.approx(1.12)


def test_cdi_plus_is_cdi_times_the_spread(app_module):
    cdi = [0.0004] * 252
    factor = app_module.fixed_income_accrual_factor("CDI_PLUS", 0.02, cdi)
    assert factor == pytest.approx((1.0004 ** 252) * 1.02)


def test_ipca_plus_prorates_the_purchase_month(app_module):
    ipca = [
        (datetime(2026, 4, 1), 0.01),  # comprado no dia 16 de abril: 15 de 30 dias
        (datetime(2026, 5, 1), 0.005),
    ]
    factor = app_module.fixed_income_accrual_factor(
        "IPCA", 0.06, [0.0004] * 252, ipca, datetime(2026, 4, 16)
    )
    expected_ipca = (1.01 ** 0.5) * 1.005
    assert factor == pytest.approx(expected_ipca * 1.06)


def test_ipca_months_before_purchase_are_ignored(app_module):
    ipca = [(datetime(2026, 3, 1), 0.02), (datetime(2026, 4, 1), 0.01)]
    assert app_module.ipca_accrual_factor(ipca, datetime(2026, 4, 1)) == pytest.approx(1.01)


def test_refresh_values_a_prefixed_title(app_module, client, auth, monkeypatch):
    monkeypatch.setattr(
        app_module,
        "fetch_bcb_series",
        lambda code, start, end=None: [(datetime(2026, 1, 1), 0.0004)] * 252,
    )
    response = client.post(
        "/api/investments",
        json=[{
            "asset_class": "FIXED_INCOME",
            "ticker_or_name": "CDB PRE TESTE",
            "quantity": 1,
            "average_price": 1000,
            "current_price": 1000,
            "metadata": {
                "fixed_income_type": "CDB",
                "rate_type": "PRE",
                "annual_rate": 0.12,
                "purchase_date": "2025-01-02",
            },
        }],
        headers=auth,
    )
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    created_id = response.get_json()[0]["id"]

    refresh = client.post("/api/investments/update-prices", json={"investment_id": created_id}, headers=auth)
    assert refresh.status_code == 200, refresh.get_data(as_text=True)
    updated = refresh.get_json()["updated_assets"]
    assert [asset["price"] for asset in updated] == [1120.0]


def create_fixed_income(client, auth, name, metadata, quantity=1, price=1000):
    response = client.post(
        "/api/investments",
        json=[{
            "asset_class": "FIXED_INCOME",
            "ticker_or_name": name,
            "quantity": quantity,
            "average_price": price,
            "current_price": price,
            "metadata": metadata,
        }],
        headers=auth,
    )
    assert response.status_code in (200, 201), response.get_data(as_text=True)
    return response.get_json()[0]["id"]


def test_refresh_fetches_each_series_once_and_slices_per_title(app_module, client, auth, monkeypatch):
    # 10 dias de CDI a 0,1%: os 5 primeiros em janeiro, os 5 ultimos em fevereiro.
    series = [(datetime(2025, 1, day), 0.001) for day in range(1, 6)]
    series += [(datetime(2025, 2, day), 0.001) for day in range(1, 6)]
    calls = []

    def fake_series(code, start, end=None):
        calls.append((code, start))
        return [row for row in series if row[0] >= start]

    monkeypatch.setattr(app_module, "fetch_bcb_series", fake_series)
    early = create_fixed_income(client, auth, "CDB CEDO", {
        "rate_type": "POS", "indexer": "CDI", "cdi_percentage": 1.0, "purchase_date": "2025-01-01",
    })
    late = create_fixed_income(client, auth, "CDB TARDE", {
        "rate_type": "POS", "indexer": "CDI", "cdi_percentage": 1.0, "purchase_date": "2025-02-01",
    })

    refresh = client.post("/api/investments/update-prices", json={}, headers=auth)
    assert refresh.status_code == 200, refresh.get_data(as_text=True)

    # Uma busca so, a partir da compra mais antiga; nada de IPCA sem titulo IPCA+.
    assert calls == [(app_module.BCB_SERIES_CDI, datetime(2025, 1, 1))]
    prices = {asset["investment_id"]: asset["price"] for asset in refresh.get_json()["updated_assets"]}
    assert prices[early] == app_module.rounded_money(1000 * 1.001 ** 10)
    assert prices[late] == app_module.rounded_money(1000 * 1.001 ** 5)


def test_refresh_ignores_redemption_rows(app_module, client, auth, monkeypatch):
    monkeypatch.setattr(
        app_module,
        "fetch_bcb_series",
        lambda code, start, end=None: [(datetime(2026, 1, 1), 0.0004)] * 10,
    )
    title = create_fixed_income(client, auth, "CDB RESGATADO EM PARTE", {
        "rate_type": "POS", "indexer": "CDI", "cdi_percentage": 1.0, "purchase_date": "2025-01-02",
    })
    create_fixed_income(client, auth, "CDB RESGATADO EM PARTE", {
        "is_redemption": True, "affects_position": True, "related_id": title,
        "redemption_date": "2026-01-10",
    }, quantity=-1, price=400)

    refresh = client.post("/api/investments/update-prices", json={}, headers=auth)
    assert refresh.status_code == 200, refresh.get_data(as_text=True)
    body = refresh.get_json()
    assert body["failed_assets"] == []
    assert [asset["investment_id"] for asset in body["updated_assets"]] == [title]


def test_bcb_failure_fails_every_title_without_breaking_the_request(app_module, client, auth, monkeypatch):
    def broken_series(code, start, end=None):
        raise RuntimeError("BCB respondeu 503")

    monkeypatch.setattr(app_module, "fetch_bcb_series", broken_series)
    create_fixed_income(client, auth, "CDB SEM BCB", {
        "rate_type": "PRE", "annual_rate": 0.1, "purchase_date": "2025-01-02",
    })

    refresh = client.post("/api/investments/update-prices", json={}, headers=auth)
    assert refresh.status_code == 200, refresh.get_data(as_text=True)
    body = refresh.get_json()
    assert body["updated_assets"] == []
    assert [asset["error"] for asset in body["failed_assets"]] == ["BCB respondeu 503"]


class FakeBcbResponse:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body.encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_bcb_http_error(code, body):
    import io
    import urllib.error

    return urllib.error.HTTPError("https://api.bcb.gov.br", code, "erro", {}, io.BytesIO(body.encode()))


def test_bcb_not_found_is_an_empty_series(app_module, monkeypatch):
    # Titulo comprado hoje: o SGS responde 404 "Value(s) not found".
    def urlopen(req, timeout=None):
        raise fake_bcb_http_error(404, '{"erro":{"statusCode":404,"detail":"SGSNegocioException: Value(s) not found"}}')

    monkeypatch.setattr(app_module.urllib.request, "urlopen", urlopen)
    assert app_module.fetch_bcb_series(12, datetime(2026, 9, 22), datetime(2026, 9, 22)) == []


def test_bcb_error_object_fails_with_its_message(app_module, monkeypatch):
    # Um objeto em vez de lista era iterado como chaves: "'str' object has no attribute 'get'".
    monkeypatch.setattr(
        app_module.urllib.request,
        "urlopen",
        lambda req, timeout=None: FakeBcbResponse('{"error": "Servico indisponivel"}'),
    )
    with pytest.raises(RuntimeError, match="Servico indisponivel"):
        app_module.fetch_bcb_series(12, datetime(2025, 1, 1), datetime(2025, 2, 1))


def test_bcb_other_http_errors_still_fail(app_module, monkeypatch):
    def urlopen(req, timeout=None):
        raise fake_bcb_http_error(500, "boom")

    monkeypatch.setattr(app_module.urllib.request, "urlopen", urlopen)
    with pytest.raises(RuntimeError, match="500"):
        app_module.fetch_bcb_series(12, datetime(2025, 1, 1), datetime(2025, 2, 1))


def test_bcb_windows_over_ten_years_are_split(app_module, monkeypatch):
    windows = []

    def urlopen(req, timeout=None):
        query = req.full_url.split("?", 1)[1]
        params = dict(part.split("=") for part in query.split("&"))
        windows.append((params["dataInicial"], params["dataFinal"]))
        return FakeBcbResponse(f'[{{"data": "{params["dataInicial"]}", "valor": "0.04"}}]')

    monkeypatch.setattr(app_module.urllib.request, "urlopen", urlopen)
    series = app_module.fetch_bcb_series(12, datetime(2010, 1, 1), datetime(2026, 9, 22))

    assert windows == [
        ("01/01/2010", "29/12/2019"),
        ("30/12/2019", "22/09/2026"),
    ]
    assert [day for day, _ in series] == [datetime(2010, 1, 1), datetime(2019, 12, 30)]
    assert series[0][1] == pytest.approx(0.0004)


def test_refresh_of_a_title_bought_today_keeps_its_cost(app_module, client, auth, monkeypatch):
    def urlopen(req, timeout=None):
        raise fake_bcb_http_error(404, '{"erro":{"statusCode":404,"detail":"Value(s) not found"}}')

    monkeypatch.setattr(app_module.urllib.request, "urlopen", urlopen)
    created_id = create_fixed_income(client, auth, "CDB DE HOJE", {
        "rate_type": "POS", "indexer": "CDI", "cdi_percentage": 1.0,
        "purchase_date": datetime.now().strftime("%Y-%m-%d"),
    })
    refresh = client.post("/api/investments/update-prices", json={"investment_id": created_id}, headers=auth)
    assert refresh.status_code == 200, refresh.get_data(as_text=True)
    body = refresh.get_json()
    assert body["failed_assets"] == []
    assert [asset["price"] for asset in body["updated_assets"]] == [1000.0]


def post_fixed_income(client, auth, metadata, quantity=1):
    return client.post(
        "/api/investments",
        json=[{
            "asset_class": "FIXED_INCOME",
            "ticker_or_name": "CDB VALIDACAO",
            "quantity": quantity,
            "average_price": 1000,
            "current_price": 1000,
            "metadata": {"purchase_date": "2025-01-02", **metadata},
        }],
        headers=auth,
    )


@pytest.mark.parametrize("metadata, message", [
    ({"rate_type": "POS", "indexer": "SELIC", "annual_rate": 0.1}, "Indexador"),
    ({"rate_type": "FLUTUANTE", "annual_rate": 0.1}, "pos-fixada"),
    ({"fixed_income_type": "POUPANCA", "rate_type": "PRE", "annual_rate": 0.1}, "Tipo de titulo"),
    ({"rate_type": "PRE"}, "taxa anual"),
    ({"rate_type": "POS", "indexer": "IPCA", "cdi_percentage": 1.1}, "taxa anual"),
    ({"rate_type": "POS", "indexer": "CDI", "cdi_percentage": 0}, "percentual do CDI"),
    ({"rate_type": "POS", "indexer": "CDI", "cdi_percentage": "abc"}, "percentual do CDI"),
])
def test_buy_with_unreadable_rate_is_refused(client, auth, metadata, message):
    response = post_fixed_income(client, auth, metadata)
    assert response.status_code == 400, response.get_data(as_text=True)
    assert message in response.get_json()["error"]


@pytest.mark.parametrize("metadata", [
    {},  # titulo sem taxa: preco manual, como antes
    {"cdi_percentage": 1.1},  # legado
    {"fixed_income_type": "LCA", "rate_type": "POS", "indexer": "CDI", "cdi_percentage": 0.95},
    {"fixed_income_type": "DEBENTURE", "rate_type": "POS", "indexer": "IPCA", "annual_rate": 0.065},
    {"fixed_income_type": "CDB", "rate_type": "PRE", "annual_rate": 0.12},
])
def test_valid_or_legacy_buys_are_accepted(client, auth, metadata):
    response = post_fixed_income(client, auth, metadata)
    assert response.status_code in (200, 201), response.get_data(as_text=True)


def test_edit_with_unreadable_rate_is_refused(client, auth):
    created_id = create_fixed_income(client, auth, "CDB EDITADO", {
        "rate_type": "POS", "indexer": "CDI", "cdi_percentage": 1.0, "purchase_date": "2025-01-02",
    })
    response = client.patch(
        f"/api/investments/{created_id}",
        json={"metadata": {"rate_type": "POS", "indexer": "CDI_PLUS", "purchase_date": "2025-01-02"}},
        headers=auth,
    )
    assert response.status_code == 400
    assert "taxa anual" in response.get_json()["error"]
