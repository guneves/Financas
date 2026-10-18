"""Cliente da Pluggy (https://pluggy.ai), o agregador de Open Finance (funcoes puras, sem banco).

Quem grava no banco e `services/pluggy_sync.py`; aqui so ha HTTP, um cache da
chave de acesso e a leitura das respostas. As credenciais (`PLUGGY_CLIENT_ID`,
`PLUGGY_CLIENT_SECRET`) vem do ambiente (`backend/.env`, gitignored, e o `.env`
do servidor) a cada chamada, como o token da brapi, e nunca saem do backend.

O formato de cada chamada foi conferido contra o SDK Python oficial
(`pluggy-sdk` 1.0.0.post73, gerado do OpenAPI da Pluggy) em 2026-10-17, porque
docs.pluggy.ai nao abre da sessao na nuvem:

- `POST /auth` {clientId, clientSecret} -> {apiKey}; toda outra chamada leva o
  cabecalho `X-API-KEY`.
- `GET /items/{id}`: a conexao com um banco (status, executionStatus,
  connector.name, lastUpdatedAt).
- `GET /accounts?itemId=` -> {results}: id, type (BANK | CREDIT), subtype,
  number, name, marketingName, currencyCode.
- `GET /transactions?accountId=&from=&to=&pageSize=&page=` -> {results, page,
  total, totalPages}; pageSize de 1 a 500.

Uma transacao: id, description, amount, amountInAccountCurrency, currencyCode,
date, type (DEBIT | CREDIT — a Pluggy ja normaliza o sinal: compra no cartao e
sempre DEBIT, pagamento da fatura CREDIT), status (POSTED | PENDING; no cartao,
PENDING e a compra da fatura ainda aberta), creditCardMetadata
(installmentNumber, totalInstallments, totalAmount, purchaseDate, cardNumber,
billId), operationType (no cartao, 'PAGAMENTO_FATURA', 'ESTORNO'...), updatedAt.

Nao conferido (o SDK nao diz): quanto tempo a apiKey vale. Ela fica em cache
por `API_KEY_TTL_SECONDS` e, num 401/403, e pedida de novo uma vez.
"""

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

DEFAULT_BASE_URL = "https://api.pluggy.ai"
REQUEST_TIMEOUT_SECONDS = 20
API_KEY_TTL_SECONDS = 60 * 60
PAGE_SIZE = 500
# Um extrato de um ano de uma conta movimentada cabe em poucas paginas; acima
# disso algo esta errado e a sincronizacao para em vez de girar sem fim.
MAX_PAGES = 40

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}")


class PluggyError(RuntimeError):
    """Base de todos os erros do cliente."""


class PluggyNotConfiguredError(PluggyError):
    """PLUGGY_CLIENT_ID ou PLUGGY_CLIENT_SECRET vazio."""


class PluggyHTTPError(PluggyError):
    def __init__(self, status, detail=""):
        self.status = int(status)
        self.detail = str(detail or "")[:300]
        super().__init__(f"Pluggy respondeu {self.status}: {self.detail or 'sem detalhe'}")


class PluggyUnavailableError(PluggyError):
    """Tempo esgotado ou falha de rede."""


class PluggyResponseError(PluggyError):
    """Resposta 2xx fora do formato esperado."""


CREDENTIAL_NAMES = ("PLUGGY_CLIENT_ID", "PLUGGY_CLIENT_SECRET")
# Os outros PLUGGY_* que o app le (config.py e base_url). Um nome fora desta
# lista no ambiente e, quase sempre, uma das credenciais escrita errado.
KNOWN_SETTING_NAMES = CREDENTIAL_NAMES + (
    "PLUGGY_BASE_URL",
    "PLUGGY_IMPORT_PENDING",
    "PLUGGY_SYNC_MIN_INTERVAL_SECONDS",
    "PLUGGY_LOOKBACK_DAYS",
    "PLUGGY_MATCH_DAYS",
)
# Onde mexer, para a mensagem: o servidor so tem compose.yaml e .env (DEPLOY.md).
NOT_CONFIGURED_HINT = (
    "No servidor, edite /srv/apps/financas/.env e rode "
    "`sudo docker compose up -d --force-recreate`: um `docker compose restart` "
    "mantém o ambiente antigo e não lê o .env de novo."
)


def _setting(name):
    value = str(os.getenv(name, "") or "").strip()
    # "abc" ou 'abc' no .env: o docker compose antigo (v1) passa as aspas junto.
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1].strip()
    return value


def credentials():
    return tuple(_setting(name) for name in CREDENTIAL_NAMES)


def is_configured():
    client_id, client_secret = credentials()
    return bool(client_id and client_secret)


def setup_report():
    """Por que a Pluggy nao esta configurada, sem nunca mostrar um valor.

    `missing`: credenciais que nem existem no ambiente do processo (o container
    nao foi recriado, ou o .env e outro); `empty`: existem, mas vazias;
    `unknown_names`: PLUGGY_* que o app nao le (um nome errado aparece aqui).
    So nomes saem daqui.
    """
    missing = [name for name in CREDENTIAL_NAMES if name not in os.environ]
    empty = [name for name in CREDENTIAL_NAMES if name in os.environ and not _setting(name)]
    unknown = sorted(
        name for name in os.environ
        if name.upper().startswith("PLUGGY") and name not in KNOWN_SETTING_NAMES
    )
    return {"missing": missing, "empty": empty, "unknown_names": unknown}


def not_configured_message():
    """A frase do erro: o que falta e onde mexer."""
    report = setup_report()
    parts = []
    if report["missing"]:
        verb = "não chegaram" if len(report["missing"]) > 1 else "não chegou"
        parts.append(f"{' e '.join(report['missing'])} {verb} ao app")
    if report["empty"]:
        verb = "estão vazios" if len(report["empty"]) > 1 else "está vazio"
        parts.append(f"{' e '.join(report['empty'])} {verb}")
    if report["unknown_names"]:
        parts.append(f"há {', '.join(report['unknown_names'])} no ambiente (nome errado?)")
    summary = "; ".join(parts) or "credenciais da Pluggy vazias"
    return f"A Pluggy não está configurada: {summary}. {NOT_CONFIGURED_HINT}"


def base_url():
    return str(os.getenv("PLUGGY_BASE_URL", DEFAULT_BASE_URL) or DEFAULT_BASE_URL).rstrip("/")


_key_lock = threading.Lock()
_api_key = {"value": None, "expires_at": 0.0, "client_id": None}


def reset_api_key():
    """Para os testes, e quando as credenciais mudam."""
    with _key_lock:
        _api_key.update({"value": None, "expires_at": 0.0, "client_id": None})


def _open(req, timeout):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        except Exception:  # noqa: BLE001 - o status basta
            detail = ""
        raise PluggyHTTPError(exc.code, _error_message(detail)) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise PluggyUnavailableError(f"Falha de rede ao falar com a Pluggy: {reason}") from exc


def _error_message(body):
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return body
    if isinstance(payload, dict):
        return str(payload.get("message") or payload.get("error") or body)
    return body


def _decode(body):
    try:
        return json.loads(body)
    except (TypeError, ValueError) as exc:
        raise PluggyResponseError("A Pluggy respondeu algo que nao e JSON.") from exc


def get_api_key(force=False):
    """A apiKey de `POST /auth`, guardada por API_KEY_TTL_SECONDS."""
    client_id, client_secret = credentials()
    if not (client_id and client_secret):
        raise PluggyNotConfiguredError(not_configured_message())
    with _key_lock:
        if (
            not force
            and _api_key["value"]
            and _api_key["client_id"] == client_id
            and time.monotonic() < _api_key["expires_at"]
        ):
            return _api_key["value"]
    req = urllib.request.Request(
        base_url() + "/auth",
        data=json.dumps({"clientId": client_id, "clientSecret": client_secret}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    payload = _decode(_open(req, REQUEST_TIMEOUT_SECONDS))
    key = payload.get("apiKey") if isinstance(payload, dict) else None
    if not key:
        raise PluggyResponseError("A Pluggy nao devolveu apiKey em /auth.")
    with _key_lock:
        _api_key.update({
            "value": key,
            "expires_at": time.monotonic() + API_KEY_TTL_SECONDS,
            "client_id": client_id,
        })
    return key


def _get(path, params=None):
    """GET autenticado; num 401/403 pede outra apiKey e tenta uma vez mais."""
    query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
    return _request("GET", path + (f"?{query}" if query else ""))


def _post(path, body):
    return _request("POST", path, body)


def _request(method, path, body=None):
    url = base_url() + path
    data = None if body is None else json.dumps(body).encode("utf-8")
    for attempt in (0, 1):
        key = get_api_key(force=attempt == 1)
        headers = {"X-API-KEY": key, "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            return _decode(_open(req, REQUEST_TIMEOUT_SECONDS))
        except PluggyHTTPError as exc:
            if exc.status in (401, 403) and attempt == 0:
                continue
            raise
    raise PluggyError("Nao foi possivel autenticar na Pluggy.")


# ---------------------------------------------------------------------------
# Leitura das respostas
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PluggyItem:
    id: str
    status: str
    execution_status: str
    connector_name: str
    last_updated_at: str


@dataclass(frozen=True)
class PluggyAccount:
    id: str
    item_id: str
    type: str
    subtype: str
    number: str
    name: str
    currency: str


@dataclass(frozen=True)
class PluggyTransaction:
    id: str
    account_id: str
    date: str
    description: str
    amount_cents: int
    direction: str
    status: str
    installment_number: int
    total_installments: int
    purchase_date: str
    operation_type: str
    updated_at: str
    # A data como veio, com hora e fuso se vierem (`date` e so o AAAA-MM-DD).
    date_raw: str = ""


def _text(value):
    return str(value).strip() if value is not None else ""


def _iso_date(value):
    """A data como a Pluggy manda (AAAA-MM-DD do inicio do texto); vazio se nao for data."""
    text = _text(value)
    return text[:10] if DATE_PATTERN.match(text) else ""


def _cents(value):
    try:
        return int(Decimal(str(value)).scaleb(2).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _positive_int(value):
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def parse_item(raw):
    if not isinstance(raw, dict) or not raw.get("id"):
        raise PluggyResponseError("Item da Pluggy sem id.")
    connector = raw.get("connector") if isinstance(raw.get("connector"), dict) else {}
    return PluggyItem(
        id=_text(raw.get("id")),
        status=_text(raw.get("status")),
        execution_status=_text(raw.get("executionStatus")),
        connector_name=_text(connector.get("name")),
        last_updated_at=_text(raw.get("lastUpdatedAt")),
    )


def parse_account(raw):
    if not isinstance(raw, dict) or not raw.get("id"):
        raise PluggyResponseError("Conta da Pluggy sem id.")
    return PluggyAccount(
        id=_text(raw.get("id")),
        item_id=_text(raw.get("itemId")),
        type=_text(raw.get("type")).upper(),
        subtype=_text(raw.get("subtype")).upper(),
        number=_text(raw.get("number")),
        name=_text(raw.get("marketingName")) or _text(raw.get("name")),
        currency=_text(raw.get("currencyCode")).upper() or "BRL",
    )


def parse_transaction(raw, account_type="BANK"):
    """Uma transacao da Pluggy no formato do app; None quando falta o essencial.

    O valor sai sempre positivo, em centavos, e a direcao vem de `type`. Sem
    `type`, o sinal decide: na conta, negativo e saida; no cartao, onde o banco
    inverte, positivo e compra. Compra no exterior usa o valor ja convertido
    para a moeda da conta (`amountInAccountCurrency`), quando vem.
    """
    if not isinstance(raw, dict) or not raw.get("id"):
        return None
    date = _iso_date(raw.get("date"))
    value = raw.get("amountInAccountCurrency")
    if value is None:
        value = raw.get("amount")
    cents = _cents(value)
    if not date or cents is None or cents == 0:
        return None

    direction = _text(raw.get("type")).upper()
    if direction not in ("DEBIT", "CREDIT"):
        if str(account_type).upper() == "CREDIT":
            direction = "DEBIT" if cents > 0 else "CREDIT"
        else:
            direction = "DEBIT" if cents < 0 else "CREDIT"

    card = raw.get("creditCardMetadata") if isinstance(raw.get("creditCardMetadata"), dict) else {}
    total = _positive_int(card.get("totalInstallments"))
    number = _positive_int(card.get("installmentNumber"))
    if total <= 1 or not number or number > total:
        total, number = 0, 0
    status = _text(raw.get("status")).upper() or "POSTED"

    return PluggyTransaction(
        id=_text(raw.get("id")),
        account_id=_text(raw.get("accountId")),
        date=date,
        description=_text(raw.get("description")) or _text(raw.get("descriptionRaw")),
        amount_cents=abs(cents),
        direction=direction,
        status=status if status in ("POSTED", "PENDING") else "POSTED",
        installment_number=number,
        total_installments=total,
        purchase_date=_iso_date(card.get("purchaseDate")),
        operation_type=_text(raw.get("operationType")).upper(),
        updated_at=_text(raw.get("updatedAt")),
        date_raw=_text(raw.get("date"))[:40],
    )


# ---------------------------------------------------------------------------
# Chamadas
# ---------------------------------------------------------------------------

def create_connect_token(item_id=None):
    """O token de curta duracao do Pluggy Connect (`POST /connect_token`).

    E o que a tela entrega ao widget da Pluggy, onde o dono escolhe o banco e
    da o consentimento do Open Finance; a apiKey nunca sai do backend. Com
    `item_id`, o widget abre no modo de atualizacao daquela conexao
    (consentimento vencido, senha trocada).
    """
    payload = _post("/connect_token", {"itemId": item_id} if item_id else {})
    token = payload.get("accessToken") if isinstance(payload, dict) else None
    if not token:
        raise PluggyResponseError("A Pluggy nao devolveu o token do Connect.")
    return token


def get_item(item_id):
    return parse_item(_get(f"/items/{urllib.parse.quote(str(item_id), safe='')}"))


def list_accounts(item_id):
    payload = _get("/accounts", {"itemId": item_id})
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise PluggyResponseError("A Pluggy nao devolveu a lista de contas.")
    return [parse_account(raw) for raw in results]


def list_transactions(account_id, date_from, date_to=None, account_type="BANK"):
    """Todas as transacoes da conta a partir de `date_from` (AAAA-MM-DD), pagina por pagina.

    Devolve a lista inteira ou levanta erro: uma lista pela metade nao pode
    chegar a quem compara com o que ja foi gravado (o que falta seria lido
    como apagado na Pluggy).
    """
    transactions = []
    page = 1
    while True:
        payload = _get("/transactions", {
            "accountId": account_id,
            "from": date_from,
            "to": date_to,
            "pageSize": PAGE_SIZE,
            "page": page,
        })
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            raise PluggyResponseError("A Pluggy nao devolveu a lista de transacoes.")
        for raw in results:
            parsed = parse_transaction(raw, account_type)
            if parsed:
                transactions.append(parsed)
        try:
            total_pages = int(payload.get("totalPages") or 1)
        except (TypeError, ValueError):
            total_pages = 1
        if page >= total_pages:
            return transactions
        page += 1
        if page > MAX_PAGES:
            raise PluggyResponseError(f"Mais de {MAX_PAGES} paginas de transacoes; sincronizacao interrompida.")
