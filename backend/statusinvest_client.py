"""Historico de proventos por ticker na StatusInvest (funcoes puras, sem banco).

`GET https://statusinvest.com.br/<acao|fii>/companytickerprovents?ticker=X&chartProventsType=2`
e publico (sem token) e devolve `assetEarningsModels`: data com (`ed`), data de
pagamento (`pd`), tipo (`et`) e valor por cota (`v`), em reais.

Base dos valores, conferida contra a carteira do Investidor10 (2026-10-16):

- desdobramento/grupamento: os valores anteriores vem ajustados (`adj` true) para
  a base de hoje — a mesma base em que o app guarda as quantidades depois de um
  evento corporativo (017). Quantidade gravada x valor = bruto certo;
- bonificacao: os valores nao sao ajustados, e no app a bonificacao e uma compra
  na data ex — quantidade na data com x valor tambem fecha.

Os tipos viram os do app em `EVENT_TYPES`; tipo desconhecido e ignorado.
Um cache em memoria (`CACHE_SECONDS`) evita pedir o mesmo ticker de novo a cada
sincronizacao — recalcular a posicao depois de uma operacao nao vai a rede.
"""

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime

BASE_URL = "https://statusinvest.com.br"
REQUEST_TIMEOUT_SECONDS = 15
CACHE_SECONDS = 6 * 60 * 60
# A StatusInvest corta rajadas (30 tickers seguidos deram 429/403 na 2026-10-16):
# um intervalo entre pedidos e uma segunda tentativa depois de uma pausa.
MIN_REQUEST_INTERVAL_SECONDS = 0.6
THROTTLED_RETRY_PAUSE_SECONDS = 4
THROTTLED_STATUSES = {403, 429}
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

# Ticker que mudou de codigo: a StatusInvest so conhece o novo, com o
# historico inteiro (conferido valor a valor contra o Investidor10).
TICKER_ALIASES = {
    "MALL11": "PMLL11",  # Malls Brasil Plural, renomeado em 2025
}

# tipo na StatusInvest -> (proceeds_type do app, natureza)
# A natureza decide o imposto: JCP na fonte, rendimento tributavel na tabela
# regressiva, dividendo/rendimento de FII isentos.
EVENT_TYPES = {
    "dividendo": ("DIVIDEND", "DIVIDEND"),
    "rendimento": ("DIVIDEND", "DIVIDEND"),
    "jcp": ("JCP", "JCP"),
    "juros sobre capital proprio": ("JCP", "JCP"),
    "rend. tributado": ("JCP", "TAXABLE_INCOME"),
    "rendimento tributado": ("JCP", "TAXABLE_INCOME"),
    "rend. tributavel": ("JCP", "TAXABLE_INCOME"),
    "amortizacao": ("AMORTIZATION", "AMORTIZATION"),
}


class StatusInvestError(Exception):
    pass


@dataclass(frozen=True)
class ProceedEvent:
    ticker: str
    proceeds_type: str
    kind: str
    record_date: str
    payment_date: str
    amount_per_unit: float
    source_label: str


_cache = {}
_lock = threading.Lock()
_request_lock = threading.Lock()
_last_request_at = 0.0


def clear_cache():
    with _lock:
        _cache.clear()


def _strip_accents(text):
    replacements = str.maketrans("áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ", "aaaaeeioooucAAAAEEIOOOUC")
    return text.translate(replacements)


def _parse_br_date(value):
    try:
        return datetime.strptime(str(value or "").strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def map_event_type(label):
    key = _strip_accents(str(label or "")).strip().lower()
    return EVENT_TYPES.get(key)


def parse_events(ticker, payload):
    """Os eventos com data com, pagamento e valor > 0; o resto e descartado."""
    models = (payload or {}).get("assetEarningsModels") if isinstance(payload, dict) else None
    events = []
    for item in models or []:
        if not isinstance(item, dict):
            continue
        mapped = map_event_type(item.get("et")) or map_event_type(item.get("etd"))
        record_date = _parse_br_date(item.get("ed"))
        payment_date = _parse_br_date(item.get("pd"))
        try:
            value = float(item.get("v"))
        except (TypeError, ValueError):
            value = 0.0
        if not mapped or not record_date or not payment_date or value <= 0:
            continue
        # Pagamento antes da data com e erro de digitacao na fonte (visto no
        # ITSA4: data com 30/05/2025, pagamento 01/07/2024).
        if payment_date < record_date:
            continue
        events.append(ProceedEvent(
            ticker=ticker,
            proceeds_type=mapped[0],
            kind=mapped[1],
            record_date=record_date,
            payment_date=payment_date,
            amount_per_unit=value,
            source_label=str(item.get("et") or ""),
        ))
    return events


def _paced_open(req, timeout):
    global _last_request_at
    with _request_lock:
        wait = MIN_REQUEST_INTERVAL_SECONDS - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read().decode("utf-8", errors="replace")
        finally:
            _last_request_at = time.monotonic()


def _request(path, ticker, timeout):
    query = urllib.parse.urlencode({"ticker": ticker, "chartProventsType": 2})
    req = urllib.request.Request(
        f"{BASE_URL}/{path}/companytickerprovents?{query}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        try:
            body = _paced_open(req, timeout)
        except urllib.error.HTTPError as exc:
            if exc.code not in THROTTLED_STATUSES:
                raise
            time.sleep(THROTTLED_RETRY_PAUSE_SECONDS)
            body = _paced_open(req, timeout)
    except urllib.error.HTTPError as exc:
        raise StatusInvestError(f"StatusInvest respondeu {exc.code} para {ticker}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise StatusInvestError(f"Falha de rede ao consultar a StatusInvest: {exc}") from exc
    try:
        return json.loads(body) if body.strip() else {}
    except ValueError as exc:
        raise StatusInvestError(f"Resposta da StatusInvest nao e JSON para {ticker}") from exc


def get_proceed_events(ticker, asset_class, *, force=False, timeout=None, now=None):
    """Eventos do ticker; FII consulta /fii primeiro, o resto /acao.

    Ticker que a StatusInvest nao conhece devolve lista vazia (e fica no cache);
    so falha de rede ou HTTP levanta StatusInvestError.
    """
    ticker = str(ticker or "").strip().upper()
    now = now if now is not None else time.monotonic()
    with _lock:
        cached = _cache.get(ticker)
        if cached and not force and now - cached[0] < CACHE_SECONDS:
            return list(cached[1])

    paths = ["fii", "acao"] if asset_class == "REIT" else ["acao", "fii"]
    source_ticker = TICKER_ALIASES.get(ticker, ticker)
    events = []
    for path in paths:
        payload = _request(path, source_ticker, timeout or REQUEST_TIMEOUT_SECONDS)
        events = parse_events(ticker, payload)
        if events:
            break

    with _lock:
        _cache[ticker] = (now, list(events))
    return events
