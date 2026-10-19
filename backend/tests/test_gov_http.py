"""gov_http: o GET do SGS (BCB) e do Tesouro Transparente.

O BCB e o Tesouro falhavam no servidor (Python 3.14) com a cadeia de
certificados dos sites gov.br, que o modo estrito do Python 3.13+ recusa.
Nenhum teste vai a rede: `urllib.request.urlopen` e substituido.
"""

import io
import socket
import ssl
import urllib.error
import urllib.request
from datetime import datetime

import pytest

import gov_http


class FakeResponse:
    def __init__(self, body):
        self.body = body.encode() if isinstance(body, str) else body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(gov_http, "RETRY_DELAYS_SECONDS", (0,))


def http_error(code, body=""):
    return urllib.error.HTTPError("https://api.bcb.gov.br", code, "erro", {}, io.BytesIO(body.encode()))


def cert_error():
    error = ssl.SSLCertVerificationError(1, "certificate verify failed")
    error.verify_message = "Missing Authority Key Identifier"
    return urllib.error.URLError(error)


def test_context_verifies_the_chain_without_strict_mode():
    context = gov_http.ssl_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    strict = getattr(ssl, "VERIFY_X509_STRICT", 0)
    assert not context.verify_flags & strict


def test_get_sends_the_context_and_headers(monkeypatch):
    seen = {}

    def urlopen(request, timeout=None, context=None):
        seen.update(timeout=timeout, context=context, accept=request.get_header("Accept"))
        return FakeResponse("[]")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert gov_http.get("https://api.bcb.gov.br/x", 30, accept="application/json") == b"[]"
    assert seen["timeout"] == 30
    assert isinstance(seen["context"], ssl.SSLContext)
    assert seen["accept"] == "application/json"


def test_a_passing_failure_is_tried_again(monkeypatch):
    calls = []

    def urlopen(request, timeout=None, context=None):
        calls.append(1)
        if len(calls) == 1:
            raise http_error(503)
        return FakeResponse("ok")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert gov_http.get("https://api.bcb.gov.br/x", 5) == b"ok"
    assert len(calls) == 2


def test_a_refused_certificate_is_not_retried_and_says_why(monkeypatch):
    calls = []

    def urlopen(request, timeout=None, context=None):
        calls.append(1)
        raise cert_error()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(RuntimeError, match="certificado recusado.*Authority Key Identifier"):
        gov_http.get("https://api.bcb.gov.br/x", 5)
    assert len(calls) == 1


def test_a_timeout_is_retried_once_then_named(monkeypatch):
    calls = []

    def urlopen(request, timeout=None, context=None):
        calls.append(1)
        raise urllib.error.URLError(socket.timeout("timed out"))

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(RuntimeError, match="sem resposta em 15 s"):
        gov_http.get("https://api.bcb.gov.br/x", 15)
    assert len(calls) == 2


def test_other_http_errors_go_up_untouched(monkeypatch):
    def urlopen(request, timeout=None, context=None):
        raise http_error(404, "not found")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(urllib.error.HTTPError):
        gov_http.get("https://api.bcb.gov.br/x", 5)


def test_bcb_failure_names_the_cause(fixed_income_module, monkeypatch):
    def urlopen(request, timeout=None, context=None):
        raise cert_error()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(RuntimeError, match="BCB: certificado recusado"):
        fixed_income_module.fetch_bcb_series(12, datetime(2026, 10, 1), datetime(2026, 10, 15))


def test_bcb_series_reads_through_the_context(fixed_income_module, monkeypatch):
    def urlopen(request, timeout=None, context=None):
        assert context is not None
        assert timeout == fixed_income_module.BCB_TIMEOUT_SECONDS
        return FakeResponse('[{"data": "01/10/2026", "valor": "0.055131"}]')

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    series = fixed_income_module.fetch_bcb_series(12, datetime(2026, 10, 1), datetime(2026, 10, 1))
    assert series[0][0] == datetime(2026, 10, 1)
    assert series[0][1] == pytest.approx(0.00055131)


def test_health_waits_for_the_bcb_longer_than_for_quotes(app_module, monkeypatch):
    import importlib

    health = importlib.import_module("services.health")
    seen = {}

    def timed(fn, timeout=None):
        seen["timeout"] = timeout
        return [(datetime.now(), 0.0005)], None, 10

    monkeypatch.setattr(health, "_timed", timed)
    assert health.check_bcb()["status"] == "ok"
    assert seen["timeout"] > health.PRICE_FETCH_TIMEOUT_SECONDS


def test_tesouro_auto_refresh_stays_off_without_url(app_module):
    import tesouro_client

    assert tesouro_client.TESOURO_PRICES_URL == ""
    assert tesouro_client.start_auto_refresh() is False
