"""O cliente da Pluggy (pluggy_client.py): leitura das respostas e o HTTP, sem rede.

O formato veio do SDK oficial (`pluggy-sdk`, gerado do OpenAPI da Pluggy). O
que estes testes fixam:

- o valor sai positivo, em centavos, e a direcao vem de `type`; sem `type`, o
  sinal decide, invertido no cartao;
- compra no exterior usa o valor ja convertido (`amountInAccountCurrency`);
- parcela so quando ha mais de uma (installmentNumber/totalInstallments);
- sem credenciais nada vai a rede; a apiKey fica em cache e e pedida de novo
  num 401; a lista de transacoes vem pagina por pagina, inteira ou erro.
"""

import json
import urllib.parse

import pytest

import pluggy_client


def raw(**overrides):
    item = {
        "id": "tx-1",
        "accountId": "acc-1",
        "description": "PADARIA PAO QUENTE",
        "currencyCode": "BRL",
        "amount": -12.5,
        "date": "2026-10-15T03:00:00.000Z",
        "type": "DEBIT",
        "status": "POSTED",
        "updatedAt": "2026-10-15T10:00:00.000Z",
    }
    item.update(overrides)
    return item


class TestParseTransaction:
    def test_a_bank_debit(self):
        tx = pluggy_client.parse_transaction(raw())
        assert tx.id == "tx-1"
        assert tx.account_id == "acc-1"
        assert tx.date == "2026-10-15"
        assert tx.amount_cents == 1250
        assert tx.direction == "DEBIT"
        assert tx.status == "POSTED"
        assert tx.description == "PADARIA PAO QUENTE"
        assert (tx.installment_number, tx.total_installments) == (0, 0)

    def test_the_type_wins_over_the_sign(self):
        tx = pluggy_client.parse_transaction(raw(amount=80, type="CREDIT"))
        assert (tx.direction, tx.amount_cents) == ("CREDIT", 8000)

    def test_without_type_the_sign_decides_and_the_card_inverts_it(self):
        assert pluggy_client.parse_transaction(raw(type=None, amount=-5)).direction == "DEBIT"
        assert pluggy_client.parse_transaction(raw(type=None, amount=5)).direction == "CREDIT"
        assert pluggy_client.parse_transaction(raw(type=None, amount=5), "CREDIT").direction == "DEBIT"
        assert pluggy_client.parse_transaction(raw(type=None, amount=-5), "CREDIT").direction == "CREDIT"

    def test_a_foreign_purchase_uses_the_converted_amount(self):
        tx = pluggy_client.parse_transaction(raw(amount=-3, currencyCode="USD", amountInAccountCurrency=-16.47))
        assert tx.amount_cents == 1647

    def test_cents_round_half_up(self):
        assert pluggy_client.parse_transaction(raw(amount=-0.125)).amount_cents == 13

    def test_installments(self):
        tx = pluggy_client.parse_transaction(raw(creditCardMetadata={
            "installmentNumber": 2, "totalInstallments": 10, "purchaseDate": "2026-08-20T00:00:00.000Z",
        }), "CREDIT")
        assert (tx.installment_number, tx.total_installments) == (2, 10)
        assert tx.purchase_date == "2026-08-20"

    def test_a_single_installment_is_no_installment(self):
        tx = pluggy_client.parse_transaction(raw(creditCardMetadata={
            "installmentNumber": 1, "totalInstallments": 1,
        }), "CREDIT")
        assert (tx.installment_number, tx.total_installments) == (0, 0)

    def test_pending(self):
        assert pluggy_client.parse_transaction(raw(status="PENDING")).status == "PENDING"

    @pytest.mark.parametrize("broken", [
        {"id": None}, {"amount": None}, {"amount": 0}, {"date": "ontem"}, {"amount": "abc"},
    ])
    def test_without_the_essentials_it_is_dropped(self, broken):
        assert pluggy_client.parse_transaction(raw(**broken)) is None

    def test_account_and_item(self):
        account = pluggy_client.parse_account({
            "id": "acc-1", "itemId": "item-1", "type": "credit", "subtype": "CREDIT_CARD",
            "number": "1234", "name": "Cartao", "marketingName": "Itau Visa Platinum",
            "currencyCode": "BRL",
        })
        assert (account.type, account.name, account.number) == ("CREDIT", "Itau Visa Platinum", "1234")
        item = pluggy_client.parse_item({
            "id": "item-1", "status": "UPDATED", "executionStatus": "SUCCESS",
            "connector": {"name": "Itaú"},
        })
        assert (item.connector_name, item.status) == ("Itaú", "UPDATED")


class FakeHttp:
    """Responde por caminho; guarda cada pedido."""

    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def __call__(self, req, timeout):
        self.requests.append(req)
        parsed = urllib.parse.urlparse(req.full_url)
        handler = self.routes[parsed.path]
        result = handler(req, urllib.parse.parse_qs(parsed.query)) if callable(handler) else handler
        if isinstance(result, Exception):
            raise result
        return json.dumps(result)


@pytest.fixture()
def configured(monkeypatch):
    monkeypatch.setenv("PLUGGY_CLIENT_ID", "11111111-2222-3333-4444-555555555555")
    monkeypatch.setenv("PLUGGY_CLIENT_SECRET", "segredo")
    pluggy_client.reset_api_key()
    yield
    pluggy_client.reset_api_key()


class TestSetup:
    """Por que a Pluggy nao esta configurada: so nomes, nunca valores."""

    def test_a_key_the_container_never_got_is_missing(self, monkeypatch):
        monkeypatch.delenv("PLUGGY_CLIENT_ID", raising=False)
        monkeypatch.setenv("PLUGGY_CLIENT_SECRET", "")
        report = pluggy_client.setup_report()
        assert report["missing"] == ["PLUGGY_CLIENT_ID"]
        assert report["empty"] == ["PLUGGY_CLIENT_SECRET"]
        message = pluggy_client.not_configured_message()
        assert "PLUGGY_CLIENT_ID não chegou ao app" in message
        assert "PLUGGY_CLIENT_SECRET está vazio" in message
        assert "--force-recreate" in message

    def test_a_misspelled_name_is_named_and_its_value_never_shown(self, monkeypatch):
        monkeypatch.delenv("PLUGGY_CLIENT_ID", raising=False)
        monkeypatch.setenv("PLUGGY_CLIENT_SECRET", "segredo-que-nao-aparece")
        monkeypatch.setenv("PLUGGY_CLIENTID", "id-que-nao-aparece")
        report = pluggy_client.setup_report()
        assert report["unknown_names"] == ["PLUGGY_CLIENTID"]
        message = pluggy_client.not_configured_message()
        assert "PLUGGY_CLIENTID" in message
        assert "nao-aparece" not in message and "nao-aparece" not in json.dumps(report)

    def test_the_settings_the_app_reads_are_not_unknown(self, monkeypatch):
        monkeypatch.setenv("PLUGGY_MATCH_DAYS", "3")
        monkeypatch.setenv("PLUGGY_BASE_URL", "http://127.0.0.1:9")
        assert pluggy_client.setup_report()["unknown_names"] == []

    def test_quotes_around_a_value_are_not_part_of_it(self, monkeypatch):
        monkeypatch.setenv("PLUGGY_CLIENT_ID", '"11111111-2222"')
        monkeypatch.setenv("PLUGGY_CLIENT_SECRET", "'segredo'")
        assert pluggy_client.credentials() == ("11111111-2222", "segredo")
        monkeypatch.setenv("PLUGGY_CLIENT_SECRET", '""')
        assert pluggy_client.is_configured() is False
        assert pluggy_client.setup_report()["empty"] == ["PLUGGY_CLIENT_SECRET"]


class TestHttp:
    def test_blank_credentials_never_reach_the_network(self, monkeypatch):
        monkeypatch.setenv("PLUGGY_CLIENT_ID", "")
        monkeypatch.setenv("PLUGGY_CLIENT_SECRET", "")
        pluggy_client.reset_api_key()
        monkeypatch.setattr(pluggy_client, "_open", lambda *a, **k: pytest.fail("foi a rede"))
        assert pluggy_client.is_configured() is False
        with pytest.raises(pluggy_client.PluggyNotConfiguredError):
            pluggy_client.list_transactions("acc-1", "2026-10-01")

    def test_the_api_key_is_asked_once_and_sent_on_every_call(self, configured, monkeypatch):
        http = FakeHttp({
            "/auth": {"apiKey": "chave-1"},
            "/items/item-1": {"id": "item-1", "status": "UPDATED", "executionStatus": "SUCCESS"},
        })
        monkeypatch.setattr(pluggy_client, "_open", http)
        pluggy_client.get_item("item-1")
        pluggy_client.get_item("item-1")
        paths = [urllib.parse.urlparse(req.full_url).path for req in http.requests]
        assert paths == ["/auth", "/items/item-1", "/items/item-1"]
        auth = http.requests[0]
        assert auth.get_method() == "POST"
        assert json.loads(auth.data) == {
            "clientId": "11111111-2222-3333-4444-555555555555", "clientSecret": "segredo",
        }
        assert http.requests[1].get_header("X-api-key") == "chave-1"

    def test_a_401_asks_for_a_new_key_once(self, configured, monkeypatch):
        keys = iter(["velha", "nova"])
        seen = []

        def item(req, _query):
            seen.append(req.get_header("X-api-key"))
            if req.get_header("X-api-key") == "velha":
                return pluggy_client.PluggyHTTPError(401, "expirou")
            return {"id": "item-1", "status": "UPDATED", "executionStatus": "SUCCESS"}

        http = FakeHttp({"/auth": lambda _req, _q: {"apiKey": next(keys)}, "/items/item-1": item})
        monkeypatch.setattr(pluggy_client, "_open", http)
        assert pluggy_client.get_item("item-1").id == "item-1"
        assert seen == ["velha", "nova"]

    def test_transactions_come_page_by_page(self, configured, monkeypatch):
        def transactions(_req, query):
            page = int(query["page"][0])
            assert query["accountId"] == ["acc-1"]
            assert query["from"] == ["2026-09-30"]
            assert query["pageSize"] == ["500"]
            return {
                "results": [raw(id=f"tx-{page}")],
                "page": page, "total": 2, "totalPages": 2,
            }

        http = FakeHttp({"/auth": {"apiKey": "chave"}, "/transactions": transactions})
        monkeypatch.setattr(pluggy_client, "_open", http)
        result = pluggy_client.list_transactions("acc-1", "2026-09-30")
        assert [tx.id for tx in result] == ["tx-1", "tx-2"]

    def test_a_broken_page_raises_instead_of_returning_half(self, configured, monkeypatch):
        def transactions(_req, query):
            if query["page"] == ["2"]:
                return pluggy_client.PluggyUnavailableError("caiu")
            return {"results": [raw()], "page": 1, "total": 2, "totalPages": 2}

        http = FakeHttp({"/auth": {"apiKey": "chave"}, "/transactions": transactions})
        monkeypatch.setattr(pluggy_client, "_open", http)
        with pytest.raises(pluggy_client.PluggyUnavailableError):
            pluggy_client.list_transactions("acc-1", "2026-09-30")

    def test_a_body_without_results_is_an_error(self, configured, monkeypatch):
        http = FakeHttp({"/auth": {"apiKey": "chave"}, "/accounts": {"oops": True}})
        monkeypatch.setattr(pluggy_client, "_open", http)
        with pytest.raises(pluggy_client.PluggyResponseError):
            pluggy_client.list_accounts("item-1")
