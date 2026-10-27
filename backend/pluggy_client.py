"""Cliente HTTP da Pluggy (https://docs.pluggy.ai), o Open Finance do app.

Modulo sem banco e sem config, como `brapi_client.py`: quem cria o cliente
(services/open_finance.py) passa as credenciais lidas em config.py. Aqui so se
fala com a API:

* `POST /auth` da a API key (vale 2 h). Ela fica guardada ate
  API_KEY_REUSE_SECONDS e e reusada — a Pluggy limita o /auth, e pedir uma
  chave por chamada e o jeito comum de bater no limite. Um 401 descarta a
  chave e tenta uma vez com outra.
* `POST /connect_token` da o token do widget Pluggy Connect (30 min).
* Itens (`GET/DELETE /items/{id}` — nunca PATCH: `call()` recusa), contas
  (`GET /accounts?itemId=`), investimentos (`GET /investments`, 044) e
  transacoes por cursor (`GET /v2/transactions`, seguindo `next` ate null; o
  `/transactions` por pagina foi desligado para apps novos em 2026).

Cada chamada tem timeout e UMA nova tentativa quando a rede falha (nunca
quando a Pluggy respondeu). O log diz metodo, caminho e status — nunca a
chave, o token, o segredo ou a descricao de uma transacao. Cada resultado
real vai para `integrations.record_provider_result("pluggy", ...)`, que o
healthcheck mostra.
"""

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import integrations

logger = logging.getLogger(__name__)

PROVIDER = "pluggy"
DEFAULT_BASE_URL = "https://api.pluggy.ai"
# A chave vale 2 h; trocar 20 min antes nao deixa uma sync longa pegar uma vencida.
API_KEY_REUSE_SECONDS = 100 * 60
# Um pull nunca segue mais que isto de paginas (500 transacoes cada) nem um
# cursor repetido: a defesa contra um `next` que nao anda.
MAX_TRANSACTION_PAGES = 40

urlopen = urllib.request.urlopen


class PluggyError(Exception):
    """A Pluggy respondeu com erro (status >= 400) ou nao respondeu."""

    def __init__(self, message, status=None, code=None):
        super().__init__(message)
        self.status = status
        self.code = code

    @property
    def network(self):
        return self.status is None


def _error_from_body(status, body):
    message, code = None, None
    if isinstance(body, dict):
        message = body.get("message") or body.get("error")
        code = body.get("code") or body.get("codeDescription")
    if not message:
        message = f"A Pluggy respondeu {status}."
    return PluggyError(str(message)[:300], status=status, code=str(code) if code is not None else None)


class PluggyClient:
    def __init__(self, client_id, client_secret, base_url=DEFAULT_BASE_URL, timeout=20.0, clock=time.monotonic):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self._clock = clock
        self._lock = threading.Lock()
        self._api_key = None
        self._api_key_at = None

    @property
    def configured(self):
        return bool(self.client_id and self.client_secret)

    # -- HTTP -------------------------------------------------------------

    def _send(self, method, path, *, body=None, query=None, api_key=None):
        """Uma ida e volta; repete uma vez se a rede falhar. Devolve o JSON."""
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode({key: value for key, value in query.items() if value is not None})
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if api_key:
            headers["X-API-KEY"] = api_key
        last_error = None
        for attempt in (1, 2):
            request = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    raw = response.read()
                    status = getattr(response, "status", 200)
                logger.info("pluggy", extra={"provider": PROVIDER, "method": method, "path": path, "status": status})
                return json.loads(raw) if raw else None
            except urllib.error.HTTPError as exc:
                try:
                    payload = json.loads(exc.read() or b"null")
                except (ValueError, OSError):
                    payload = None
                logger.warning(
                    "pluggy recusou", extra={"provider": PROVIDER, "method": method, "path": path, "status": exc.code},
                )
                raise _error_from_body(exc.code, payload) from None
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "pluggy sem resposta",
                    extra={"provider": PROVIDER, "method": method, "path": path, "attempt": attempt,
                           "error": type(exc).__name__},
                )
        raise PluggyError("A Pluggy nao respondeu. Tente de novo em instantes.") from last_error

    def _api_key_value(self, renew=False):
        with self._lock:
            fresh = (
                self._api_key and self._api_key_at is not None
                and self._clock() - self._api_key_at < API_KEY_REUSE_SECONDS
            )
            if fresh and not renew:
                return self._api_key
            if not self.configured:
                raise PluggyError("Open Finance desligado: faltam PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET.", status=0)
            body = self._send("POST", "/auth", body={"clientId": self.client_id, "clientSecret": self.client_secret})
            key = (body or {}).get("apiKey")
            if not key:
                raise PluggyError("A Pluggy nao devolveu a chave de acesso.", status=0)
            self._api_key, self._api_key_at = key, self._clock()
            return key

    def forget_api_key(self):
        with self._lock:
            self._api_key = None
            self._api_key_at = None

    def call(self, method, path, *, body=None, query=None):
        """Uma chamada autenticada. Registra o resultado para o healthcheck."""
        if method.upper() == "PATCH":
            raise PluggyError("O app nao pede atualizacao ao banco (PATCH): so le o que a Pluggy ja tem.", status=0)
        try:
            try:
                result = self._send(method, path, body=body, query=query, api_key=self._api_key_value())
            except PluggyError as exc:
                if exc.status != 401:
                    raise
                # Chave vencida ou revogada antes da hora: uma nova, uma vez.
                result = self._send(method, path, body=body, query=query, api_key=self._api_key_value(renew=True))
        except PluggyError as exc:
            # 404 de um item ja apagado nao e a Pluggy fora do ar.
            if exc.status not in (404,):
                integrations.record_provider_result(PROVIDER, False, str(exc))
            raise
        integrations.record_provider_result(PROVIDER, True)
        return result

    # -- API --------------------------------------------------------------

    def create_connect_token(self, item_id=None, client_user_id=None):
        body = {}
        if item_id:
            body["itemId"] = item_id
        options = {"avoidDuplicates": True}
        if client_user_id:
            options["clientUserId"] = client_user_id
        body["options"] = options
        result = self.call("POST", "/connect_token", body=body) or {}
        token = result.get("accessToken")
        if not token:
            raise PluggyError("A Pluggy nao devolveu o token de conexao.", status=0)
        return token

    def get_item(self, item_id):
        return self.call("GET", f"/items/{_path_id(item_id)}")

    # Nao ha update_item (PATCH /items/{id}): pedir dados novos ao banco gasta
    # o limite mensal do CPF no plano gratis do MeuPluggy, e esgotado bloqueia
    # a conta ate o mes seguinte (dono, 2026-10-27). A Pluggy atualiza o banco
    # sozinha (6-24 h); o app so le o que ela ja tem, por GET.

    def list_investments(self, item_id):
        """As posicoes de investimento do item (`GET /investments?itemId=`)."""
        return self._pages("/investments", {"itemId": item_id})

    def list_investment_transactions(self, investment_id):
        """As operacoes de uma posicao (`GET /investments/{id}/transactions`)."""
        return self._pages(f"/investments/{_path_id(investment_id)}/transactions", {})

    def _pages(self, path, query):
        """Uma listagem por pagina (`page`, `totalPages`), ate MAX_TRANSACTION_PAGES."""
        results = []
        for number in range(1, MAX_TRANSACTION_PAGES + 1):
            page = self.call("GET", path, query={**query, "page": number, "pageSize": 500}) or {}
            if isinstance(page, list):
                return results + page
            results.extend(page.get("results") or [])
            if number >= int(page.get("totalPages") or 1):
                return results
        logger.warning("pluggy: paginas demais", extra={"provider": PROVIDER, "pages": MAX_TRANSACTION_PAGES})
        return results

    def delete_item(self, item_id):
        try:
            self.call("DELETE", f"/items/{_path_id(item_id)}")
        except PluggyError as exc:
            if exc.status != 404:
                raise
            return False
        return True

    def list_accounts(self, item_id):
        result = self.call("GET", "/accounts", query={"itemId": item_id}) or {}
        return list(result.get("results") or [])

    def list_transactions(self, account_id, date_from, date_to=None):
        """Todas as transacoes da conta de `date_from` (AAAA-MM-DD) em diante,
        seguindo o cursor."""
        query = {"accountId": account_id, "dateFrom": date_from, "dateTo": date_to}
        results = []
        seen = set()
        for _page in range(MAX_TRANSACTION_PAGES):
            page = self.call("GET", "/v2/transactions", query=query) or {}
            results.extend(page.get("results") or [])
            after = next_cursor(page.get("next"))
            if not after or after in seen:
                return results
            seen.add(after)
            query = {"accountId": account_id, "dateFrom": date_from, "dateTo": date_to, "after": after}
        logger.warning("pluggy: paginas demais", extra={"provider": PROVIDER, "pages": MAX_TRANSACTION_PAGES})
        return results


def next_cursor(next_value):
    """O `after` de um `next` da Pluggy ("?accountId=...&after=..."), ou None.
    A doc diz que `next` e uma query string pronta; aceita tambem a URL inteira
    ou so o cursor."""
    if not next_value:
        return None
    text = str(next_value).strip()
    if "after=" not in text:
        return text if "?" not in text and "&" not in text and "=" not in text else None
    query = text.split("?", 1)[1] if "?" in text else text
    values = urllib.parse.parse_qs(query).get("after")
    return values[0] if values and values[0] else None


def _path_id(value):
    text = str(value or "").strip()
    if not text or not all(char.isalnum() or char == "-" for char in text) or len(text) > 64:
        raise PluggyError("Identificador da Pluggy invalido.", status=0)
    return text
