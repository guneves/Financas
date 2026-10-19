"""Precos e taxas do Tesouro Direto, publicados pelo Tesouro Nacional.

A fonte e o conjunto "Taxas dos Titulos Ofertados pelo Tesouro Direto" do
Tesouro Transparente (CKAN): um CSV com todos os titulos desde 2002, uma
linha por titulo e dia util, separado por ";", decimal com virgula e datas
dd/mm/aaaa:

    Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;
    PU Compra Manha;PU Venda Manha;PU Base Manha

O BCB nao publica o preco de mercado do Tesouro Direto (as series do SGS sao
o CDI, a Selic e o IPCA); a marcacao a mercado precisa da taxa do dia, e esta
e a fonte oficial dela. Funcoes puras para ler o arquivo e achar o titulo pelo
nome; o download e o cache (memoria + o arquivo cru em disco,
`TESOURO_PRICES_FILE`) ficam em `get_prices()`.

Os testes nunca chegam a rede: `conftest.py` deixa `TESOURO_PRICES_URL` vazio
(nada a buscar) e os que precisam de precos usam `set_prices()`.
"""

from array import array
from bisect import bisect_left, bisect_right
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
import json
import os
import re
import threading
import time
import unicodedata
import urllib.error

import gov_http
from applog import get_logger
from config import TESOURO_PRICES_FILE, TESOURO_PRICES_URL
from integrations import record_provider_result

logger = get_logger(__name__)

# Se o endereco direto do arquivo mudar, o pacote do CKAN diz o novo.
TESOURO_PACKAGE_URL = (
    "https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show"
    "?id=taxas-dos-titulos-ofertados-pelo-tesouro-direto"
)
DOWNLOAD_TIMEOUT_SECONDS = 60
# O arquivo muda uma vez por dia util: a marcacao a mercado e baixada uma vez
# por dia (dono, 2026-10-19). Antes disso, o cache serve sem perguntar -- nem
# a leitura, nem "Atualizar cotacoes", nem a thread baixam de novo. A copia em
# disco guarda a hora do download, entao um deploy tambem nao rebaixa.
PRICES_FRESH_SECONDS = 24 * 3600
# Mais velho que isso, um preco nao e mais "de mercado": a tela volta a curva.
PRICES_MAX_AGE_SECONDS = 10 * 24 * 3600

# Os tipos como o Tesouro os escreve no arquivo; a chave e o nome normalizado.
SELIC = "TESOURO SELIC"
PREFIXADO = "TESOURO PREFIXADO"
PREFIXADO_JUROS = "TESOURO PREFIXADO COM JUROS SEMESTRAIS"
IPCA = "TESOURO IPCA+"
IPCA_JUROS = "TESOURO IPCA+ COM JUROS SEMESTRAIS"
IGPM_JUROS = "TESOURO IGPM+ COM JUROS SEMESTRAIS"
RENDA_MAIS = "TESOURO RENDA+ APOSENTADORIA EXTRA"
EDUCA_MAIS = "TESOURO EDUCA+"

# Titulos sem cupom: o PU e o valor de face (ou o VNA) descontado pela taxa,
# PU = VNA / (1 + taxa) ^ (du / 252). Os com juros semestrais e os de renda
# mensal (Renda+, Educa+) sao uma soma de fluxos.
ZERO_COUPON_TYPES = {SELIC, PREFIXADO, IPCA}
# O Renda+ e o Educa+ levam no nome o ano da conversao; o vencimento (o ultimo
# pagamento mensal) vem 19 e 4 anos depois: Renda+ 2065 vence em 15/12/2084.
NAMED_BY_CONVERSION = {RENDA_MAIS: 19, EDUCA_MAIS: 4}


def normalize_text(value):
    """Maiusculas sem acento, codigos sem hifen (NTN-B -> NTNB) e "IPCA +" -> "IPCA+"."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.upper().replace("IGP-M", "IGPM").replace("NTN-B", "NTNB").replace("NTN-F", "NTNF")
    text = re.sub(r"\s*\+", "+", text)
    return " ".join(text.split())


def canonical_type(raw_type):
    """Uma das constantes acima a partir do tipo escrito no arquivo, ou None."""
    return title_type_from_name(raw_type)


def title_type_from_name(name):
    """O tipo do Tesouro pelo nome que o dono deu ao titulo, ou None.

    Aceita o nome da corretora ("Tesouro IPCA+ 2045 (NTNB Principal)") e o
    codigo do titulo (LTN, LFT, NTN-B, NTN-B Principal, NTN-F).
    """
    text = normalize_text(name)
    words = set(re.findall(r"[A-Z0-9]+", text))
    has_coupon = "JUROS" in words or "SEMESTRAIS" in words
    if "RENDA+" in text or "APOSENTADORIA" in words:
        return RENDA_MAIS
    if "EDUCA+" in text:
        return EDUCA_MAIS
    if "SELIC" in words or "LFT" in words:
        return SELIC
    if "IGPM" in words or "IGPM+" in text:
        return IGPM_JUROS
    if "IPCA" in words or "NTNB" in words:
        if has_coupon or ("NTNB" in words and "PRINCIPAL" not in words and "PRINC" not in words and "IPCA" not in words):
            return IPCA_JUROS
        return IPCA
    if "NTNF" in words:
        return PREFIXADO_JUROS
    if "PREFIXADO" in words or "LTN" in words or "PRE" in words:
        return PREFIXADO_JUROS if has_coupon else PREFIXADO
    return None


def title_year_from_name(name):
    """O primeiro ano (2000-2099) do nome, ou None."""
    match = re.search(r"(?<!\d)(20\d{2})(?!\d)", str(name or ""))
    return int(match.group(1)) if match else None


def _parse_number(raw):
    value = str(raw or "").strip()
    if not value:
        return None
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


def _parse_date(raw):
    value = str(raw or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _header_index(header):
    """{campo: coluna} pelo nome do cabecalho, sem depender da ordem."""
    names = [normalize_text(column).replace(" ", "_") for column in header]

    def find(*keys):
        for index, name in enumerate(names):
            if all(key in name for key in keys):
                return index
        return None

    index = {
        "type": find("TIPO"),
        "maturity": find("VENCIMENTO"),
        "base": find("DATA_BASE"),
        "buy_rate": find("TAXA_COMPRA"),
        "sell_rate": find("TAXA_VENDA"),
        "buy_pu": find("PU_COMPRA"),
        "sell_pu": find("PU_VENDA"),
        "base_pu": find("PU_BASE"),
    }
    required = ("type", "maturity", "base", "sell_pu")
    if any(index[key] is None for key in required):
        raise ValueError("Arquivo de precos do Tesouro sem as colunas esperadas.")
    return index


class TitleSeries:
    """Historico de um titulo (tipo + vencimento), em ordem de data base.

    Guardado em `array` (o arquivo inteiro tem centenas de milhares de linhas):
    os dias como ordinal e cada coluna como double, NaN quando vazia."""

    FIELDS = ("buy_rate", "sell_rate", "buy_pu", "sell_pu", "base_pu")

    def __init__(self, title_type, maturity):
        self.title_type = title_type
        self.maturity = maturity
        self.days = array("i")
        self.columns = {field: array("d") for field in self.FIELDS}

    def append(self, day, values):
        self.days.append(day.toordinal())
        for field in self.FIELDS:
            value = values.get(field)
            self.columns[field].append(float("nan") if value is None else value)

    def sort(self):
        order = sorted(range(len(self.days)), key=self.days.__getitem__)
        self.days = array("i", (self.days[i] for i in order))
        for field in self.FIELDS:
            column = self.columns[field]
            self.columns[field] = array("d", (column[i] for i in order))

    def _row(self, index):
        row = {"date": date.fromordinal(self.days[index])}
        for field in self.FIELDS:
            value = self.columns[field][index]
            row[field] = None if value != value else value
        return row

    def row_on_or_before(self, day):
        """A linha da data base mais recente <= `day`, ou None."""
        index = bisect_right(self.days, _as_date(day).toordinal())
        return self._row(index - 1) if index else None

    def row_on_or_after(self, day):
        index = bisect_left(self.days, _as_date(day).toordinal())
        return self._row(index) if index < len(self.days) else None

    def latest(self):
        return self._row(len(self.days) - 1) if self.days else None

    def market_pu(self, day):
        """O preco de mercado em `day`: o PU de venda (o que o Tesouro paga na
        recompra), ou o PU base num dia sem venda. None antes da emissao."""
        row = self.row_on_or_before(day)
        if row is None:
            return None
        return row["sell_pu"] or row["base_pu"]

    def purchase_row(self, day):
        """A linha que vale para uma compra em `day`: a do proprio dia, ou a
        anterior (fim de semana, feriado); antes da primeira, a primeira."""
        return self.row_on_or_before(day) or self.row_on_or_after(day)

    def daily_values(self, start, end):
        """[(data, PU de mercado)] das datas base em [start, end)."""
        first = bisect_left(self.days, _as_date(start).toordinal())
        last = bisect_left(self.days, _as_date(end).toordinal())
        result = []
        for index in range(first, last):
            pu = self.columns["sell_pu"][index]
            if pu != pu or pu <= 0:
                pu = self.columns["base_pu"][index]
            if pu == pu and pu > 0:
                result.append((date.fromordinal(self.days[index]), pu))
        return result


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = _parse_date(value)
    if parsed is None:
        raise ValueError(f"Data invalida: {value!r}")
    return parsed


class TreasuryPrices:
    """Todos os titulos do arquivo: {(tipo, vencimento): TitleSeries}."""

    def __init__(self, series, fetched_at=None):
        self.series = series
        self._found = {}
        self.fetched_at = fetched_at if fetched_at is not None else time.time()
        self.latest_date = max(
            (s.latest()["date"] for s in series.values() if s.days),
            default=None,
        )

    def find_title(self, name):
        """O TitleSeries do titulo com esse nome, ou None.

        O tipo e o ano saem do nome; o ano e o do vencimento, ou o da conversao
        no Renda+/Educa+ (que o Tesouro usa no nome comercial)."""
        key = normalize_text(name)
        if key not in self._found:
            self._found[key] = self._find_title(name)
        return self._found[key]

    def _find_title(self, name):
        title_type = title_type_from_name(name)
        year = title_year_from_name(name)
        if title_type is None or year is None:
            return None
        candidates = [s for (kind, maturity), s in self.series.items() if kind == title_type]
        for wanted in (year, year + NAMED_BY_CONVERSION.get(title_type, 0)):
            matches = [s for s in candidates if s.maturity.year == wanted]
            if matches:
                # Dois vencimentos no mesmo ano (raro): o que ainda tem preco.
                return max(matches, key=lambda s: s.days[-1] if s.days else 0)
        return None

    def age_seconds(self, now=None):
        return max((now if now is not None else time.time()) - self.fetched_at, 0.0)


def parse_prices_csv(text, fetched_at=None):
    """O CSV do Tesouro Transparente -> TreasuryPrices. Linhas ilegiveis sao puladas."""
    lines = text.splitlines()
    header_at = next((i for i, line in enumerate(lines) if line.strip()), None)
    if header_at is None:
        raise ValueError("Arquivo de precos do Tesouro vazio.")
    separator = ";" if ";" in lines[header_at] else ","
    index = _header_index(lines[header_at].split(separator))

    series = {}
    for line in lines[header_at + 1:]:
        if not line.strip():
            continue
        cells = line.split(separator)
        try:
            title_type = canonical_type(cells[index["type"]])
            maturity = _parse_date(cells[index["maturity"]])
            base = _parse_date(cells[index["base"]])
        except IndexError:
            continue
        if title_type is None or maturity is None or base is None:
            continue
        values = {}
        for field in TitleSeries.FIELDS:
            column = index.get(field)
            values[field] = _parse_number(cells[column]) if column is not None and column < len(cells) else None
        key = (title_type, maturity)
        if key not in series:
            series[key] = TitleSeries(title_type, maturity)
        series[key].append(base, values)

    if not series:
        raise ValueError("Nenhum titulo lido do arquivo de precos do Tesouro.")
    for title in series.values():
        title.sort()
    return TreasuryPrices(series, fetched_at)


# --- download e cache -------------------------------------------------------

_lock = threading.Lock()
_prices = None
_disk_checked = False
_executor = ThreadPoolExecutor(max_workers=1)
_refresh = None


def reset_cache():
    """Esquece o que foi lido (para os testes)."""
    global _prices, _disk_checked, _refresh
    with _lock:
        _prices = None
        _disk_checked = False
        _refresh = None


def set_prices(prices):
    """Troca os precos em memoria (para os testes)."""
    global _prices, _disk_checked
    with _lock:
        _prices = prices
        _disk_checked = True


def _http_get(url):
    return gov_http.get(url, DOWNLOAD_TIMEOUT_SECONDS)


def _discover_csv_url():
    """O endereco do CSV de precos pelo pacote do CKAN (se o direto mudar)."""
    document = json.loads(_http_get(TESOURO_PACKAGE_URL).decode("utf-8", errors="replace"))
    for resource in (document.get("result") or {}).get("resources") or []:
        url = str(resource.get("url") or "")
        label = normalize_text(f"{resource.get('name')} {url}")
        if url.lower().endswith(".csv") and "PRECO" in label.replace(" ", ""):
            return url
    raise RuntimeError("Arquivo de precos nao encontrado no Tesouro Transparente.")


def download_prices_csv():
    """O texto do CSV de precos e taxas (ISO-8859-1 ou UTF-8)."""
    try:
        raw = _http_get(TESOURO_PRICES_URL)
    except urllib.error.HTTPError as exc:
        if exc.code not in (403, 404, 410):
            raise
        raw = _http_get(_discover_csv_url())
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def _read_disk():
    if not TESOURO_PRICES_FILE:
        return None
    try:
        fetched_at = os.path.getmtime(TESOURO_PRICES_FILE)
        with open(TESOURO_PRICES_FILE, encoding="utf-8") as handle:
            return parse_prices_csv(handle.read(), fetched_at)
    except FileNotFoundError:
        return None
    except Exception as exc:
        logger.warning(f"Copia dos precos do Tesouro ilegivel, ignorada: {exc}")
        return None


def _write_disk(text):
    if not TESOURO_PRICES_FILE:
        return
    temporary = f"{TESOURO_PRICES_FILE}.tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary, TESOURO_PRICES_FILE)
    except OSError as exc:
        logger.warning(f"Nao foi possivel gravar os precos do Tesouro: {exc}")


def refresh_prices():
    """Baixa o arquivo, troca o cache e grava a copia. Uma falha mantem o antigo."""
    global _prices
    try:
        text = download_prices_csv()
        prices = parse_prices_csv(text)
    except Exception as exc:
        record_provider_result("tesouro", False, exc)
        raise
    record_provider_result("tesouro", True)
    with _lock:
        _prices = prices
    _write_disk(text)
    return prices


def _schedule_refresh():
    global _refresh
    with _lock:
        if _refresh is not None and not _refresh.done():
            return _refresh

        def run():
            try:
                refresh_prices()
            except Exception as exc:
                logger.warning(f"Precos do Tesouro nao atualizados: {exc}")

        _refresh = _executor.submit(run)
        return _refresh


def wait_refresh(timeout=None):
    """Espera o download em segundo plano (para os testes)."""
    with _lock:
        future = _refresh
    if future is not None:
        future.result(timeout=timeout)


def get_prices(wait=False):
    """Os precos do Tesouro, ou None.

    Nunca prende a leitura da carteira: sem cache, ou com ele vencido, o
    download vai para segundo plano e quem chama fica com o que houver.
    `wait=True` ("Atualizar cotacoes") baixa na hora quando o cache venceu.
    Precos mais velhos que `PRICES_MAX_AGE_SECONDS` nao saem daqui."""
    global _prices, _disk_checked
    with _lock:
        if not _disk_checked:
            _disk_checked = True
            load_disk = True
        else:
            load_disk = False
    if load_disk:
        from_disk = _read_disk()
        if from_disk is not None:
            with _lock:
                if _prices is None:
                    _prices = from_disk
    with _lock:
        prices = _prices
    if not TESOURO_PRICES_URL:
        return prices
    age = prices.age_seconds() if prices is not None else None
    if age is None or age > PRICES_FRESH_SECONDS:
        if wait:
            try:
                return refresh_prices()
            except Exception:
                pass
        else:
            _schedule_refresh()
    if prices is not None and prices.age_seconds() <= PRICES_MAX_AGE_SECONDS:
        return prices
    return None


# --- atualizacao automatica -------------------------------------------------

# De quanto em quanto tempo a thread confere a idade do cache; ela so baixa
# quando ele passou de PRICES_FRESH_SECONDS.
AUTO_REFRESH_CHECK_SECONDS = 3600
_auto_refresh_started = False


def start_auto_refresh():
    """Mantem os precos em dia sem depender de alguem abrir a carteira.

    Chamado no boot (app.py): baixa se a copia tem mais de um dia, e depois
    confere a cada hora (so a idade; o download e um por dia). Assim
    a marcacao a mercado do dia ja esta pronta quando a Posicao abre, em vez
    de a primeira leitura mostrar a curva enquanto o download corre. Sem URL
    (os testes) nao faz nada."""
    global _auto_refresh_started
    with _lock:
        if _auto_refresh_started or not TESOURO_PRICES_URL:
            return False
        _auto_refresh_started = True

    def loop():
        while True:
            try:
                # O mesmo download em segundo plano das leituras: nunca dois ao mesmo tempo.
                get_prices()
                wait_refresh(timeout=DOWNLOAD_TIMEOUT_SECONDS * 4)
            except Exception as exc:  # a thread nao pode morrer
                logger.warning(f"Atualizacao automatica do Tesouro falhou: {exc}")
            time.sleep(AUTO_REFRESH_CHECK_SECONDS)

    threading.Thread(target=loop, name="tesouro-auto-refresh", daemon=True).start()
    return True
