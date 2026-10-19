"""Correcao da renda fixa por indexador: % do CDI, CDI+, IPCA+ e prefixado.

As funcoes sao puras -- recebem as series do BCB ja buscadas -- para que as
regras sejam testadas sem rede.
"""

from datetime import datetime, timedelta
import importlib

import pytest


def test_legacy_metadata_is_read_as_percent_of_cdi(fixed_income_module):
    assert fixed_income_module.fixed_income_rate_terms({"cdi_percentage": 1.1}) == ("CDI", 1.1)


def test_rate_terms_by_indexer(fixed_income_module):
    terms = fixed_income_module.fixed_income_rate_terms
    assert terms({"rate_type": "POS", "indexer": "CDI_PLUS", "annual_rate": 0.015}) == ("CDI_PLUS", 0.015)
    assert terms({"rate_type": "POS", "indexer": "IPCA", "annual_rate": 0.065}) == ("IPCA", 0.065)
    # Prefixado ignora um indexador que tenha sobrado no metadata.
    assert terms({"rate_type": "PRE", "indexer": "CDI", "annual_rate": 0.125}) == ("PRE", 0.125)


def test_missing_or_invalid_rate_is_rejected(fixed_income_module):
    terms = fixed_income_module.fixed_income_rate_terms
    assert terms({}) == (None, None)
    assert terms({"rate_type": "PRE"}) == (None, None)
    assert terms({"rate_type": "POS", "indexer": "CDI", "cdi_percentage": 0}) == (None, None)
    assert terms({"rate_type": "POS", "indexer": "SELIC", "annual_rate": 0.1}) == (None, None)


def test_percent_of_cdi_compounds_each_day(fixed_income_module):
    factor = fixed_income_module.fixed_income_accrual_factor("CDI", 1.1, [0.0005, 0.0005])
    assert factor == pytest.approx((1 + 0.0005 * 1.1) ** 2)


def test_prefixed_uses_252_business_days(fixed_income_module):
    # 252 dias uteis = um ano: o fator e exatamente a taxa anual.
    factor = fixed_income_module.fixed_income_accrual_factor("PRE", 0.12, [0.0004] * 252)
    assert factor == pytest.approx(1.12)


def test_cdi_plus_is_cdi_times_the_spread(fixed_income_module):
    cdi = [0.0004] * 252
    factor = fixed_income_module.fixed_income_accrual_factor("CDI_PLUS", 0.02, cdi)
    assert factor == pytest.approx((1.0004 ** 252) * 1.02)


def test_ipca_plus_prorates_the_purchase_month(fixed_income_module):
    ipca = [
        (datetime(2026, 4, 1), 0.01),  # comprado no dia 16 de abril: 15 de 30 dias
        (datetime(2026, 5, 1), 0.005),
    ]
    factor = fixed_income_module.fixed_income_accrual_factor(
        "IPCA", 0.06, [0.0004] * 252, ipca, datetime(2026, 4, 16)
    )
    expected_ipca = (1.01 ** 0.5) * 1.005
    assert factor == pytest.approx(expected_ipca * 1.06)


def test_ipca_months_before_purchase_are_ignored(fixed_income_module):
    ipca = [(datetime(2026, 3, 1), 0.02), (datetime(2026, 4, 1), 0.01)]
    assert fixed_income_module.ipca_accrual_factor(ipca, datetime(2026, 4, 1)) == pytest.approx(1.01)


def test_refresh_values_a_prefixed_title(fixed_income_module, client, auth, monkeypatch):
    monkeypatch.setattr(
        fixed_income_module,
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


def test_refresh_fetches_each_series_once_and_slices_per_title(fixed_income_module, client, auth, monkeypatch):
    # 10 dias de CDI a 0,1%: os 5 primeiros em janeiro, os 5 ultimos em fevereiro.
    series = [(datetime(2025, 1, day), 0.001) for day in range(1, 6)]
    series += [(datetime(2025, 2, day), 0.001) for day in range(1, 6)]
    calls = []

    def fake_series(code, start, end=None):
        calls.append((code, start))
        return [row for row in series if row[0] >= start]

    monkeypatch.setattr(fixed_income_module, "fetch_bcb_series", fake_series)
    early = create_fixed_income(client, auth, "CDB CEDO", {
        "rate_type": "POS", "indexer": "CDI", "cdi_percentage": 1.0, "purchase_date": "2025-01-01",
    })
    late = create_fixed_income(client, auth, "CDB TARDE", {
        "rate_type": "POS", "indexer": "CDI", "cdi_percentage": 1.0, "purchase_date": "2025-02-01",
    })

    refresh = client.post("/api/investments/update-prices", json={}, headers=auth)
    assert refresh.status_code == 200, refresh.get_data(as_text=True)

    # Uma busca so, a partir da compra mais antiga; nada de IPCA sem titulo IPCA+.
    assert calls == [(fixed_income_module.BCB_SERIES_CDI, datetime(2025, 1, 1))]
    prices = {asset["investment_id"]: asset["price"] for asset in refresh.get_json()["updated_assets"]}
    assert prices[early] == fixed_income_module.rounded_money(1000 * 1.001 ** 10)
    assert prices[late] == fixed_income_module.rounded_money(1000 * 1.001 ** 5)


def test_refresh_ignores_redemption_rows(fixed_income_module, client, auth, monkeypatch):
    monkeypatch.setattr(
        fixed_income_module,
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


def redeem_fixed_income(client, auth, name, title, cost, date):
    create_fixed_income(client, auth, name, {
        "is_redemption": True, "affects_position": True, "related_id": title,
        "redemption_date": date,
    }, quantity=-1, price=cost)


def test_fully_redeemed_title_is_closed(fixed_income_module, client, auth, monkeypatch):
    # O resgate total deixa a quantidade em 1 e o aplicado em 0: o titulo saiu
    # da carteira -- nada de corrigir pelo BCB nem de linha de R$ 0 na Posicao.
    monkeypatch.setattr(
        fixed_income_module,
        "fetch_bcb_series",
        lambda code, start, end=None: [(datetime(2026, 1, 1), 0.0004)] * 10,
    )
    rate = {"rate_type": "POS", "indexer": "CDI", "cdi_percentage": 1.0, "purchase_date": "2025-01-02"}
    closed = create_fixed_income(client, auth, "LCI TODA RESGATADA", rate, price=1000)
    # Dois resgates cujos custos somam o aplicado (com o resto de ponto flutuante).
    redeem_fixed_income(client, auth, "LCI TODA RESGATADA", closed, 700.1, "2025-06-01")
    redeem_fixed_income(client, auth, "LCI TODA RESGATADA", closed, 299.9, "2025-07-01")
    open_title = create_fixed_income(client, auth, "LCI EM PARTE", rate, price=1000)
    redeem_fixed_income(client, auth, "LCI EM PARTE", open_title, 999.99, "2025-07-01")

    refresh = client.post("/api/investments/update-prices", json={}, headers=auth)
    assert refresh.status_code == 200, refresh.get_data(as_text=True)
    body = refresh.get_json()
    assert body["failed_assets"] == []
    assert [asset["investment_id"] for asset in body["updated_assets"]] == [open_title]
    assert [asset["name"] for asset in body["stale_assets"]] == []

    portfolio = client.get("/api/investments/portfolio", headers=auth).get_json()
    assert [asset["source_transaction_id"] for asset in portfolio["assets"]] == [open_title]


def test_closed_title_ids_need_the_whole_cost_redeemed(fixed_income_module):
    def movement(movement_id, quantity, price, **metadata):
        return {"id": movement_id, "asset_class": "FIXED_INCOME", "quantity": quantity,
                "average_price": price, "metadata": metadata}

    redemption = {"is_redemption": True, "affects_position": True}
    investments = [
        movement("a", 1, 1000),
        movement("r1", -1, 1000, related_id="a", **redemption),
        movement("b", 1, 500),
        movement("r2", -1, 499.99, related_id="b", **redemption),
        movement("c", 1, 300),
    ]
    assert fixed_income_module.closed_fixed_income_title_ids(investments) == {"a"}


def test_bcb_failure_fails_every_title_without_breaking_the_request(fixed_income_module, client, auth, monkeypatch):
    def broken_series(code, start, end=None):
        raise RuntimeError("BCB respondeu 503")

    monkeypatch.setattr(fixed_income_module, "fetch_bcb_series", broken_series)
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


def test_bcb_not_found_is_an_empty_series(fixed_income_module, monkeypatch):
    # Titulo comprado hoje: o SGS responde 404 "Value(s) not found".
    def urlopen(req, timeout=None):
        raise fake_bcb_http_error(404, '{"erro":{"statusCode":404,"detail":"SGSNegocioException: Value(s) not found"}}')

    monkeypatch.setattr(fixed_income_module.urllib.request, "urlopen", urlopen)
    assert fixed_income_module.fetch_bcb_series(12, datetime(2026, 9, 22), datetime(2026, 9, 22)) == []


def test_bcb_error_object_fails_with_its_message(fixed_income_module, monkeypatch):
    # Um objeto em vez de lista era iterado como chaves: "'str' object has no attribute 'get'".
    monkeypatch.setattr(
        fixed_income_module.urllib.request,
        "urlopen",
        lambda req, timeout=None: FakeBcbResponse('{"error": "Servico indisponivel"}'),
    )
    with pytest.raises(RuntimeError, match="Servico indisponivel"):
        fixed_income_module.fetch_bcb_series(12, datetime(2025, 1, 1), datetime(2025, 2, 1))


def test_bcb_other_http_errors_still_fail(fixed_income_module, monkeypatch):
    def urlopen(req, timeout=None):
        raise fake_bcb_http_error(500, "boom")

    monkeypatch.setattr(fixed_income_module.urllib.request, "urlopen", urlopen)
    with pytest.raises(RuntimeError, match="500"):
        fixed_income_module.fetch_bcb_series(12, datetime(2025, 1, 1), datetime(2025, 2, 1))


def test_bcb_windows_over_ten_years_are_split(fixed_income_module, monkeypatch):
    windows = []

    def urlopen(req, timeout=None):
        query = req.full_url.split("?", 1)[1]
        params = dict(part.split("=") for part in query.split("&"))
        windows.append((params["dataInicial"], params["dataFinal"]))
        return FakeBcbResponse(f'[{{"data": "{params["dataInicial"]}", "valor": "0.04"}}]')

    monkeypatch.setattr(fixed_income_module.urllib.request, "urlopen", urlopen)
    series = fixed_income_module.fetch_bcb_series(12, datetime(2010, 1, 1), datetime(2026, 9, 22))

    assert windows == [
        ("01/01/2010", "29/12/2019"),
        ("30/12/2019", "22/09/2026"),
    ]
    assert [day for day, _ in series] == [datetime(2010, 1, 1), datetime(2019, 12, 30)]
    assert series[0][1] == pytest.approx(0.0004)


def test_refresh_of_a_title_bought_today_keeps_its_cost(fixed_income_module, client, auth, monkeypatch):
    def urlopen(req, timeout=None):
        raise fake_bcb_http_error(404, '{"erro":{"statusCode":404,"detail":"Value(s) not found"}}')

    monkeypatch.setattr(fixed_income_module.urllib.request, "urlopen", urlopen)
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


@pytest.mark.parametrize("fixed_income_type, exempt", [
    ("LCI", True), ("LCA", True), ("LIG", True), ("CRI", True), ("CRA", True),
    ("DEBENTURE_INCENTIVADA", True), ("CDB", False), ("DEBENTURE", False), (None, False),
])
def test_tax_exemption_follows_the_title_type(fixed_income_module, fixed_income_type, exempt):
    assert fixed_income_module.fixed_income_is_tax_free({"fixed_income_type": fixed_income_type}) is exempt


def test_legacy_tax_free_flag_is_still_honoured(fixed_income_module):
    assert fixed_income_module.fixed_income_is_tax_free({"fixed_income_type": "CDB", "is_tax_free": True})
    assert not fixed_income_module.fixed_income_is_tax_free(None)


def test_net_value_of_a_tax_free_type_keeps_the_whole_profit(fixed_income_module):
    net_value = fixed_income_module.fixed_income_net_value(
        "FIXED_INCOME", {"fixed_income_type": "LCA", "purchase_date": "2025-01-02"},
        1000, 1100, datetime(2025, 3, 1),
    )
    assert net_value == 1100
    taxed = fixed_income_module.fixed_income_net_value(
        "FIXED_INCOME", {"fixed_income_type": "CDB", "purchase_date": "2025-01-02"},
        1000, 1100, datetime(2025, 3, 1),
    )
    assert taxed < 1100


@pytest.mark.parametrize("fixed_income_type", ["LIG", "DEBENTURE_INCENTIVADA"])
def test_new_title_types_are_accepted(client, auth, fixed_income_type):
    response = post_fixed_income(client, auth, {
        "fixed_income_type": fixed_income_type, "rate_type": "POS", "indexer": "IPCA", "annual_rate": 0.06,
    })
    assert response.status_code in (200, 201), response.get_data(as_text=True)


def test_ir_report_puts_a_tax_free_type_in_the_exempt_code(app_module):
    tax_report = importlib.import_module("services.tax_report")
    assert tax_report.bens_code("FIXED_INCOME", "BRL", {"fixed_income_type": "LIG"})[:2] == ("04", "03")
    assert tax_report.bens_code("FIXED_INCOME", "BRL", {"fixed_income_type": "CDB"})[:2] == ("04", "02")


def test_accrual_until_matches_the_day_by_day_product(fixed_income_module):
    # accrual_factor_until usa produtos acumulados (cdi_products); o fator tem
    # de ser o mesmo da conta dia a dia sobre o trecho.
    start = datetime(2024, 1, 1)
    cdi = [(start + timedelta(days=n), 0.0004 + (n % 5) * 0.00001) for n in range(700) if (start + timedelta(days=n)).weekday() < 5]
    ipca = [(datetime(2024, month, 1), 0.004) for month in range(1, 13)] + [(datetime(2025, month, 1), 0.003) for month in range(1, 12)]
    series = {"cdi": cdi, "ipca": ipca}
    purchase, until = datetime(2024, 3, 15), datetime(2025, 6, 30, 23, 59, 59)
    titles = [
        {"rate_type": "POS", "indexer": "CDI", "cdi_percentage": 1.1},
        {"rate_type": "POS", "indexer": "CDI_PLUS", "annual_rate": 0.02},
        {"rate_type": "PRE", "indexer": "PRE", "annual_rate": 0.12},
        {"rate_type": "POS", "indexer": "IPCA", "annual_rate": 0.06},
    ]
    for metadata in titles:
        indexer, rate = fixed_income_module.fixed_income_rate_terms(metadata)
        expected = fixed_income_module.fixed_income_accrual_factor(
            indexer, rate,
            [value for day, value in cdi if purchase <= day <= until],
            [(month, value) for month, value in ipca if month <= until],
            purchase,
        )
        assert fixed_income_module.accrual_factor_until(metadata, purchase, until, series) == pytest.approx(expected, rel=1e-12)
    # Uma serie fora de ordem cai na conta dia a dia.
    shuffled = {"cdi": list(reversed(cdi)), "ipca": ipca}
    metadata = titles[0]
    assert fixed_income_module.accrual_factor_until(metadata, purchase, until, shuffled) == pytest.approx(
        fixed_income_module.accrual_factor_until(metadata, purchase, until, series), rel=1e-12,
    )
    # Compra depois do fim do trecho: nenhum dia, fator 1 no CDI.
    assert fixed_income_module.accrual_factor_until(metadata, datetime(2026, 1, 1), until, series) == 1.0
