"""Healthcheck das integracoes (secao Operations) e log estruturado.

O que estes testes fixam:

- cada provedor sai como ok / error / not_configured / stale, com o detalhe;
- sem nenhum provedor de cotacao funcionando o status geral e "down";
- o resultado fica em cache e ?refresh=1 refaz;
- uma busca real que falha fica registrada (last_failure, last_error);
- o log sai em JSON, com os campos de `extra=`.
"""

import importlib
import json
import logging
from datetime import datetime, timedelta

import pytest


@pytest.fixture()
def health(app_module, monkeypatch):
    module = importlib.import_module("services.health")
    prices = importlib.import_module("services.prices")
    fixed_income = importlib.import_module("services.fixed_income")
    importlib.import_module("integrations").reset_provider_status()
    module._cache.update({"at": 0.0, "result": None})
    # Padrao: tudo saudavel e sem rede.
    monkeypatch.setattr(prices, "yf", object())
    monkeypatch.setattr(prices, "download_close_prices", lambda symbols, **kw: {symbols[0]: 38.5})
    monkeypatch.setattr(
        fixed_income, "fetch_bcb_series",
        lambda code, start, end=None: [(datetime.now() - timedelta(days=1), 0.0004)],
    )
    monkeypatch.setattr(importlib.import_module("brapi_client"), "is_configured", lambda: False)
    return module


def by_key(result):
    return {item["key"]: item for item in result["items"]}


def test_all_healthy_without_brapi_token(health):
    result = health.check_integrations(force=True)
    items = by_key(result)
    assert result["status"] == "ok"
    assert items["yfinance"]["status"] == "ok"
    assert "38,50" in items["yfinance"]["detail"]
    assert items["brapi"]["status"] == "not_configured"
    assert items["bcb"]["status"] == "ok"


def test_yfinance_down_without_brapi_is_down(health, monkeypatch):
    prices = importlib.import_module("services.prices")
    monkeypatch.setattr(prices, "download_close_prices", lambda symbols, **kw: {})
    result = health.check_integrations(force=True)
    assert by_key(result)["yfinance"]["status"] == "error"
    assert result["status"] == "down"


def test_bcb_failure_is_degraded(health, monkeypatch):
    fixed_income = importlib.import_module("services.fixed_income")

    def boom(*args, **kwargs):
        raise RuntimeError("BCB fora do ar")

    monkeypatch.setattr(fixed_income, "fetch_bcb_series", boom)
    result = health.check_integrations(force=True)
    assert by_key(result)["bcb"] == {**by_key(result)["bcb"], "status": "error", "detail": "BCB fora do ar"}
    assert result["status"] == "degraded"


def test_old_cdi_is_stale(health, monkeypatch):
    fixed_income = importlib.import_module("services.fixed_income")
    monkeypatch.setattr(
        fixed_income, "fetch_bcb_series",
        lambda code, start, end=None: [(datetime.now() - timedelta(days=12), 0.0004)],
    )
    assert by_key(health.check_integrations(force=True))["bcb"]["status"] == "stale"


def test_result_is_cached_until_refresh(health, client, auth, monkeypatch):
    calls = []
    prices = importlib.import_module("services.prices")
    monkeypatch.setattr(prices, "download_close_prices", lambda symbols, **kw: calls.append(1) or {symbols[0]: 10})
    first = client.get("/api/health/integrations", headers=auth).get_json()
    second = client.get("/api/health/integrations", headers=auth).get_json()
    third = client.get("/api/health/integrations?refresh=1", headers=auth).get_json()
    assert (first["cached"], second["cached"], third["cached"]) == (False, True, False)
    assert len(calls) == 2


def test_a_failed_real_download_is_recorded(app_module, monkeypatch):
    prices = importlib.import_module("services.prices")
    integrations = importlib.import_module("integrations")
    integrations.reset_provider_status()

    class BrokenYf:
        @staticmethod
        def download(**kwargs):
            raise ConnectionError("Yahoo recusou")

    monkeypatch.setattr(prices, "yf", BrokenYf)
    assert prices.download_close_prices(["PETR4.SA"], period="1d", interval="1m") == {}
    snapshot = integrations.provider_snapshot("yfinance")
    assert snapshot["consecutive_failures"] == 1
    assert "Yahoo recusou" in snapshot["last_error"]


def test_log_lines_are_json_with_extras(app_module):
    applog = importlib.import_module("applog")
    record = logging.LogRecord("services.prices", logging.WARNING, __file__, 1, "Falhou %s", ("yfinance",), None)
    record.provider = "yfinance"
    line = json.loads(applog.JsonFormatter().format(record))
    assert line["level"] == "WARNING"
    assert line["msg"] == "Falhou yfinance"
    assert line["provider"] == "yfinance"
    assert line["logger"] == "services.prices"
