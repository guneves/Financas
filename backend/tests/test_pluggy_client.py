"""pluggy_client.py: a conversa com a API da Pluggy, sem rede (urlopen falso).

- a API key e pedida uma vez e reusada (o /auth tem limite); um 401 pede outra, uma vez;
- a rede que falha tenta de novo UMA vez; um erro da Pluggy nao repete;
- as transacoes seguem o cursor `next` ate null, e param num cursor repetido;
- nada de segredo, chave ou descricao no log;
- cada resultado vai para o healthcheck (integrations).
"""

import io
import json
import logging
import urllib.error

import pytest

import integrations
import pluggy_client

SECRET = "segredo-que-nao-pode-vazar"


class FakeResponse:
    def __init__(self, body, status=200):
        self._raw = json.dumps(body).encode() if body is not None else b""
        self.status = status

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeHttp:
    """Responde por (metodo, caminho sem query); guarda cada pedido."""

    def __init__(self):
        self.routes = {}
        self.requests = []

    def on(self, method, path, *responses):
        self.routes.setdefault((method, path), []).extend(responses)

    def __call__(self, request, timeout=None):
        assert timeout, "toda chamada tem timeout"
        path = request.full_url.split("api.test", 1)[1].split("?", 1)[0]
        self.requests.append((request.get_method(), request.full_url, dict(request.header_items()), request.data))
        queue = self.routes.get((request.get_method(), path))
        assert queue, f"sem resposta para {request.get_method()} {path}"
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, tuple):
            status, body = answer
            raise urllib.error.HTTPError(request.full_url, status, "erro", {}, io.BytesIO(json.dumps(body).encode()))
        return FakeResponse(answer)


@pytest.fixture()
def http(monkeypatch):
    fake = FakeHttp()
    monkeypatch.setattr(pluggy_client, "urlopen", fake)
    integrations.reset_provider_status()
    yield fake
    integrations.reset_provider_status()


def make_client(clock=None):
    times = clock or [0.0]
    return pluggy_client.PluggyClient("client-id", SECRET, "https://api.test", timeout=5, clock=lambda: times[0])


class TestApiKey:
    def test_the_key_is_asked_once_and_reused(self, http):
        http.on("POST", "/auth", {"apiKey": "chave-1"})
        http.on("GET", "/items/abc-123", {"id": "abc-123", "status": "UPDATED"})
        client = make_client()
        client.get_item("abc-123")
        client.get_item("abc-123")
        auths = [req for req in http.requests if req[1].endswith("/auth")]
        assert len(auths) == 1
        item_calls = [req for req in http.requests if "/items/" in req[1]]
        assert all(req[2].get("X-api-key") == "chave-1" for req in item_calls)

    def test_an_old_key_is_renewed(self, http):
        clock = [0.0]
        http.on("POST", "/auth", {"apiKey": "chave-1"}, {"apiKey": "chave-2"})
        http.on("GET", "/items/abc-123", {"id": "abc-123"})
        client = make_client(clock)
        client.get_item("abc-123")
        clock[0] = pluggy_client.API_KEY_REUSE_SECONDS + 1
        client.get_item("abc-123")
        assert len([req for req in http.requests if req[1].endswith("/auth")]) == 2
        assert http.requests[-1][2]["X-api-key"] == "chave-2"

    def test_a_401_asks_a_new_key_once(self, http):
        http.on("POST", "/auth", {"apiKey": "vencida"}, {"apiKey": "nova"})
        http.on("GET", "/items/abc-123", (401, {"message": "Unauthorized"}), {"id": "abc-123"})
        assert make_client().get_item("abc-123") == {"id": "abc-123"}
        assert http.requests[-1][2]["X-api-key"] == "nova"

    def test_the_secret_goes_only_in_the_auth_body(self, http):
        http.on("POST", "/auth", {"apiKey": "chave-1"})
        http.on("GET", "/items/abc-123", {"id": "abc-123"})
        make_client().get_item("abc-123")
        auth = next(req for req in http.requests if req[1].endswith("/auth"))
        assert json.loads(auth[3]) == {"clientId": "client-id", "clientSecret": SECRET}
        for method, url, headers, _data in http.requests:
            assert SECRET not in url and SECRET not in json.dumps(headers)

    def test_without_credentials_nothing_is_called(self, http):
        client = pluggy_client.PluggyClient("", "", "https://api.test")
        assert not client.configured
        with pytest.raises(pluggy_client.PluggyError):
            client.get_item("abc-123")
        assert http.requests == []


class TestRetries:
    def test_a_network_failure_is_retried_once(self, http):
        http.on("POST", "/auth", {"apiKey": "chave-1"})
        http.on("GET", "/items/abc-123", urllib.error.URLError("caiu"), {"id": "abc-123"})
        assert make_client().get_item("abc-123") == {"id": "abc-123"}
        assert len([req for req in http.requests if "/items/" in req[1]]) == 2

    def test_two_network_failures_give_up(self, http):
        http.on("POST", "/auth", {"apiKey": "chave-1"})
        http.on("GET", "/items/abc-123", TimeoutError("lento"), TimeoutError("lento"), {"id": "nunca"})
        with pytest.raises(pluggy_client.PluggyError) as error:
            make_client().get_item("abc-123")
        assert error.value.network
        assert len([req for req in http.requests if "/items/" in req[1]]) == 2

    def test_a_refusal_is_not_retried_and_keeps_pluggys_message(self, http):
        http.on("POST", "/auth", {"apiKey": "chave-1"})
        http.on("POST", "/connect_token", (403, {"message": "Limite de CPFs do plano atingido", "code": 403}))
        with pytest.raises(pluggy_client.PluggyError) as error:
            make_client().create_connect_token()
        assert error.value.status == 403
        assert "Limite de CPFs" in str(error.value)
        assert len([req for req in http.requests if "connect_token" in req[1]]) == 1


class TestTransactions:
    def test_the_cursor_is_followed_until_next_is_null(self, http):
        http.on("POST", "/auth", {"apiKey": "chave-1"})
        http.on(
            "GET", "/v2/transactions",
            {"results": [{"id": "t1"}, {"id": "t2"}], "next": "?accountId=acc-1&after=Q1VSU09SMQ%3D%3D"},
            {"results": [{"id": "t3"}], "next": None},
        )
        results = make_client().list_transactions("acc-1", "2026-09-27")
        assert [tx["id"] for tx in results] == ["t1", "t2", "t3"]
        pages = [req[1] for req in http.requests if "/v2/transactions" in req[1]]
        assert "dateFrom=2026-09-27" in pages[0] and "after=" not in pages[0]
        # O after vai decodificado uma vez e codificado de novo pela query.
        assert "after=Q1VSU09SMQ%3D%3D" in pages[1] and "dateFrom=2026-09-27" in pages[1]
        assert "pageSize" not in "".join(pages)

    def test_a_repeated_cursor_stops(self, http):
        http.on("POST", "/auth", {"apiKey": "chave-1"})
        http.on("GET", "/v2/transactions", {"results": [{"id": "t1"}], "next": "?after=MESMO"})
        results = make_client().list_transactions("acc-1", "2026-09-27")
        assert len(results) == 2
        assert len([req for req in http.requests if "/v2/transactions" in req[1]]) == 2

    @pytest.mark.parametrize("value, expected", [
        ("?accountId=a&after=abc", "abc"),
        ("https://api.pluggy.ai/v2/transactions?accountId=a&after=abc%3D", "abc="),
        ("abc", "abc"),
        (None, None),
        ("", None),
        ("?accountId=a", None),
    ])
    def test_next_cursor_shapes(self, value, expected):
        assert pluggy_client.next_cursor(value) == expected


class TestLogsAndHealth:
    def test_logs_carry_no_key_no_secret_no_description(self, http, caplog):
        http.on("POST", "/auth", {"apiKey": "chave-secreta-1"})
        http.on("GET", "/v2/transactions", {"results": [{"id": "t1", "description": "FARMACIA DO ZE"}], "next": None})
        with caplog.at_level(logging.DEBUG):
            make_client().list_transactions("acc-1", "2026-09-27")
        text = " ".join(f"{record.getMessage()} {vars(record)}" for record in caplog.records)
        assert caplog.records
        for forbidden in ("chave-secreta-1", SECRET, "FARMACIA"):
            assert forbidden not in text

    def test_results_feed_the_healthcheck(self, http):
        http.on("POST", "/auth", {"apiKey": "chave-1"})
        http.on("GET", "/items/abc-123", {"id": "abc-123"})
        http.on("GET", "/items/abc-999", (500, {"message": "Erro interno"}))
        client = make_client()
        client.get_item("abc-123")
        assert integrations.provider_snapshot("pluggy")["consecutive_failures"] == 0
        with pytest.raises(pluggy_client.PluggyError):
            client.get_item("abc-999")
        snapshot = integrations.provider_snapshot("pluggy")
        assert snapshot["consecutive_failures"] == 1 and "Erro interno" in snapshot["last_error"]

    def test_a_bad_id_never_reaches_the_url(self, http):
        with pytest.raises(pluggy_client.PluggyError):
            make_client().get_item("../accounts")
        assert http.requests == []

    def test_deleting_a_gone_item_is_fine(self, http):
        http.on("POST", "/auth", {"apiKey": "chave-1"})
        http.on("DELETE", "/items/abc-123", (404, {"message": "Item not found"}))
        assert make_client().delete_item("abc-123") is False
        assert integrations.provider_snapshot("pluggy").get("consecutive_failures", 0) == 0
