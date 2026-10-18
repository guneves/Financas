"""Renda fixa: indexadores, series do BCB, fator de rendimento e a atualizacao.

`fixed_income_rate_terms()` le do metadata o indexador e a taxa (CDI, CDI+,
IPCA+ ou prefixado); `fixed_income_accrual_factor()` aplica a serie do BCB.
A atualizacao e em duas metades: `start_fixed_income_refresh()` dispara os
downloads no `_index_fetch_executor` (separado do yfinance) e
`finish_fixed_income_refresh()` grava as cotacoes.

Os testes trocam `fetch_bcb_series` e `urllib.request.urlopen` aqui.
"""

import calendar
from concurrent.futures import ThreadPoolExecutor
import threading
import time
from datetime import datetime, timedelta
import json
import math
import urllib.error
import urllib.request

from dates import parse_iso_date
from db import get_db
from config import HISTORY_CACHE_TTL_SECONDS
from money import rounded_money
from services.prices import history_fetch_floor, record_price_quote, ticker_key
from validators import ValidationError, safe_float
from applog import get_logger
from integrations import record_provider_result

logger = get_logger(__name__)


# Separado do yfinance: um download travado la nao pode enfileirar o BCB.
_index_fetch_executor = ThreadPoolExecutor(max_workers=2)


def fixed_income_net_value(asset_class, metadata, invested_value, market_value, reference_date):
    if asset_class != "FIXED_INCOME":
        return market_value

    profit = market_value - invested_value
    if profit <= 0 or fixed_income_is_tax_free(metadata):
        return market_value

    purchase_date = parse_iso_date(metadata.get("purchase_date"))
    if not purchase_date:
        return market_value

    days_invested = max((reference_date - purchase_date).days, 0)
    if days_invested <= 180:
        tax_rate = 0.225
    elif days_invested <= 360:
        tax_rate = 0.200
    elif days_invested <= 720:
        tax_rate = 0.175
    else:
        tax_rate = 0.150

    return market_value - (profit * tax_rate)


def movement_affects_fixed_income_position(investment):
    metadata = investment.get("metadata") or {}
    return (
        investment.get("asset_class") == "FIXED_INCOME"
        and safe_float(investment.get("quantity")) < 0
        and metadata.get("is_redemption")
        and metadata.get("affects_position")
        and metadata.get("related_id")
    )


# Meio centavo: a soma dos custos resgatados pode sobrar um resto de ponto flutuante.
CLOSED_TITLE_TOLERANCE = 0.005


def fixed_income_title_closed(remaining_applied):
    """Titulo todo resgatado: o resgate total deixa a quantidade em 1 e o aplicado em 0."""
    return remaining_applied <= CLOSED_TITLE_TOLERANCE


def closed_fixed_income_title_ids(investments):
    """Ids das compras de renda fixa cujos resgates ja levaram todo o valor aplicado."""
    remaining = {}
    for inv in investments:
        if inv.get("asset_class") != "FIXED_INCOME":
            continue
        metadata = inv.get("metadata") or {}
        quantity = safe_float(inv.get("quantity"))
        applied = quantity * safe_float(inv.get("average_price"))
        if movement_affects_fixed_income_position(inv):
            key = str(metadata.get("related_id"))
        elif quantity > 0 and not metadata.get("is_redemption"):
            key = str(inv.get("id"))
        else:
            continue
        remaining[key] = remaining.get(key, 0) + applied
    return {key for key, value in remaining.items() if fixed_income_title_closed(value)}


FIXED_INCOME_INDEXERS = {"CDI", "CDI_PLUS", "IPCA"}
BUSINESS_DAYS_PER_YEAR = 252
BCB_SERIES_CDI = 12
BCB_SERIES_IPCA = 433


def fixed_income_rate_terms(metadata):
    """Le a forma de remuneracao do titulo a partir do metadata.

    Devolve (indexador, taxa) onde indexador e "PRE", "CDI", "CDI_PLUS" ou
    "IPCA". Para CDI a taxa e o percentual do CDI (1.10 = 110%); para os
    demais e a taxa anual (0.065 = 6,5% a.a.). Lancamentos anteriores a
    escolha do indexador so tem `cdi_percentage` e seguem como % do CDI.
    Devolve (None, None) se faltar a taxa.
    """
    metadata = metadata or {}
    if metadata.get("rate_type") == "PRE":
        indexer = "PRE"
    else:
        indexer = metadata.get("indexer") or "CDI"
        if indexer not in FIXED_INCOME_INDEXERS:
            return None, None

    if indexer == "CDI":
        rate = safe_float(metadata.get("cdi_percentage"), None)
    else:
        rate = safe_float(metadata.get("annual_rate"), None)

    if rate is None or not math.isfinite(rate) or rate < 0 or (indexer == "CDI" and rate == 0):
        return None, None
    return indexer, rate


FIXED_INCOME_TYPES = {
    "CDB", "LCI", "LCA", "LIG", "LC", "LF", "RDB", "DEBENTURE", "DEBENTURE_INCENTIVADA",
    "CRI", "CRA", "CCB",
}
# Isentos de IR para pessoa fisica pela propria especie do titulo.
TAX_FREE_FIXED_INCOME_TYPES = {"LCI", "LCA", "LIG", "CRI", "CRA", "DEBENTURE_INCENTIVADA"}


def fixed_income_is_tax_free(metadata):
    """Isencao de IR do titulo: vem do tipo; `is_tax_free` gravado ainda vale (legado)."""
    metadata = metadata or {}
    return bool(metadata.get("is_tax_free")) or metadata.get("fixed_income_type") in TAX_FREE_FIXED_INCOME_TYPES
FIXED_INCOME_RATE_KEYS = ("fixed_income_type", "rate_type", "indexer", "cdi_percentage", "annual_rate")


def validate_fixed_income_metadata(asset_class, quantity, metadata):
    """Recusa na gravacao a remuneracao que a atualizacao nao saberia ler.

    So vale para compras de renda fixa que tragam alguma das chaves de
    remuneracao: titulo sem taxa (preco manual) e resgates seguem livres.
    Sem isso, um indexador errado so aparecia como falha em "Atualizar cotacoes".
    """
    metadata = metadata or {}
    if asset_class != "FIXED_INCOME" or quantity <= 0 or metadata.get("is_redemption"):
        return
    if not any(metadata.get(key) not in (None, "") for key in FIXED_INCOME_RATE_KEYS):
        return

    fixed_income_type = metadata.get("fixed_income_type")
    if fixed_income_type not in (None, "") and fixed_income_type not in FIXED_INCOME_TYPES:
        raise ValidationError("Tipo de titulo de renda fixa invalido.")
    rate_type = metadata.get("rate_type")
    if rate_type not in (None, "", "POS", "PRE"):
        raise ValidationError("Remuneracao deve ser pos-fixada ou pre-fixada.")
    if rate_type != "PRE":
        indexer = metadata.get("indexer") or "CDI"
        if indexer not in FIXED_INCOME_INDEXERS:
            raise ValidationError("Indexador deve ser CDI, CDI+ ou IPCA+.")
    indexer, _ = fixed_income_rate_terms(metadata)
    if indexer is None:
        if rate_type == "PRE" or (metadata.get("indexer") or "CDI") != "CDI":
            raise ValidationError("Informe a taxa anual do titulo.")
        raise ValidationError("Informe o percentual do CDI do titulo.")


def ipca_accrual_factor(ipca_monthly, purchase_date):
    """Fator do IPCA desde a compra, com o primeiro mes pro rata por dias corridos.

    `ipca_monthly` e uma lista de (data do mes, variacao decimal) como a serie
    433 do BCB. Meses ainda nao divulgados nao entram: o valor e uma estimativa
    que se completa quando o IPCA sai.
    """
    factor = 1.0
    for month_date, variation in ipca_monthly:
        if (month_date.year, month_date.month) < (purchase_date.year, purchase_date.month):
            continue
        weight = 1.0
        if (month_date.year, month_date.month) == (purchase_date.year, purchase_date.month):
            days_in_month = calendar.monthrange(purchase_date.year, purchase_date.month)[1]
            weight = (days_in_month - purchase_date.day + 1) / days_in_month
        factor *= (1 + variation) ** weight
    return factor


def fixed_income_accrual_factor(indexer, rate, cdi_daily, ipca_monthly=None, purchase_date=None):
    """Fator de correcao acumulado do titulo.

    `cdi_daily` e a serie diaria do CDI (decimal ao dia) desde a compra; alem
    de corrigir os pos-fixados em CDI, seu tamanho e a contagem de dias uteis
    usada para a parte prefixada (base 252).
    """
    business_days = len(cdi_daily)
    if indexer == "CDI":
        factor = 1.0
        for daily_rate in cdi_daily:
            factor *= 1 + (daily_rate * rate)
        return factor

    fixed_part = (1 + rate) ** (business_days / BUSINESS_DAYS_PER_YEAR)
    if indexer == "PRE":
        return fixed_part
    if indexer == "CDI_PLUS":
        factor = 1.0
        for daily_rate in cdi_daily:
            factor *= 1 + daily_rate
        return factor * fixed_part
    if indexer == "IPCA":
        return ipca_accrual_factor(ipca_monthly or [], purchase_date) * fixed_part
    raise ValueError(f"Indexador desconhecido: {indexer}")


# O SGS recusa (HTTP 406) consultas de serie diaria com janela acima de 10 anos.
BCB_MAX_WINDOW_DAYS = 3650


def fetch_bcb_window(series_code, start_date, end_date):
    """Uma consulta ao SGS; devolve a lista crua de {"data", "valor"}.

    Sem valores no periodo (compra de hoje, CDI do dia ainda nao publicado) o
    BCB responde 404 com {"erro": ...}: isso e uma serie vazia, nao uma falha.
    Qualquer outra resposta que nao seja uma lista vira erro legivel -- iterar
    o objeto de erro era o "'str' object has no attribute 'get'".
    """
    url = (
        f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series_code}/dados"
        f"?formato=json&dataInicial={start_date.strftime('%d/%m/%Y')}"
        f"&dataFinal={end_date.strftime('%d/%m/%Y')}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as response_bcb:
            body = response_bcb.read().decode()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace") if exc.fp else ""
        if exc.code == 404 and "not found" in detail.lower():
            return []
        raise RuntimeError(f"BCB respondeu {exc.code}") from exc

    rows = json.loads(body) if body.strip() else []
    if not isinstance(rows, list):
        message = rows.get("error") or rows.get("erro") if isinstance(rows, dict) else None
        if isinstance(message, dict):
            message = message.get("detail")
        raise RuntimeError(f"Resposta inesperada do BCB: {message or 'formato desconhecido'}")
    return rows


def fetch_bcb_series(series_code, start_date, end_date=None):
    """Busca uma serie do SGS do BCB; devolve [(data, valor decimal)].

    Periodos acima de 10 anos sao buscados em janelas consecutivas.
    """
    end_date = end_date or datetime.now()
    series = []
    window_start = start_date
    try:
        while window_start <= end_date:
            window_end = min(window_start + timedelta(days=BCB_MAX_WINDOW_DAYS - 1), end_date)
            for row in fetch_bcb_window(series_code, window_start, window_end):
                series.append((datetime.strptime(row["data"], "%d/%m/%Y"), safe_float(row.get("valor")) / 100))
            window_start = window_end + timedelta(days=1)
    except Exception as exc:
        record_provider_result("bcb", False, exc)
        raise
    record_provider_result("bcb", True)
    return series


def fixed_income_asset_result(inv, **fields):
    return {
        "asset_id": inv.get("asset_id"),
        "investment_id": inv.get("id"),
        "asset_class": inv.get("asset_class"),
        "ticker": ticker_key(inv.get("ticker_or_name")),
        "name": inv.get("ticker_or_name"),
        **fields,
    }


def start_fixed_income_refresh(investments_to_update):
    """Separa os titulos a corrigir e dispara a busca no BCB em segundo plano.

    Cada serie (CDI e, se algum titulo for IPCA+, o IPCA) e buscada uma unica
    vez, a partir da compra mais antiga; cada titulo usa o trecho desde a sua
    compra. Resgates tem quantidade negativa e nao sao titulos: corrigi-los
    so gerava uma falha "Taxa do titulo nao informada". Titulo ja todo
    resgatado tambem fica de fora: nao vale mais nada a corrigir.
    """
    titles = []
    failed_assets = []
    closed_ids = closed_fixed_income_title_ids(investments_to_update)
    for inv in investments_to_update:
        if inv.get("asset_class") != "FIXED_INCOME" or safe_float(inv.get("quantity")) <= 0:
            continue
        meta = inv.get("metadata") or {}
        if meta.get("is_redemption") or str(inv.get("id")) in closed_ids:
            continue

        indexer, rate = fixed_income_rate_terms(meta)
        if indexer is None:
            failed_assets.append(fixed_income_asset_result(
                inv, status="failed", error="Taxa do titulo nao informada"
            ))
            continue

        try:
            date_str = meta.get("purchase_date") or (inv.get("created_at") or "")[:10]
            purchase_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            logger.warning(f"Data invalida para {inv['ticker_or_name']}; pulando correcao.")
            failed_assets.append(fixed_income_asset_result(
                inv, status="failed", error="Data invalida para calculo da rentabilidade"
            ))
            continue

        titles.append((inv, indexer, rate, purchase_date))

    plan = {"titles": titles, "failed_assets": failed_assets, "cdi": None, "ipca": None}
    if titles:
        start_date = min(purchase_date for _, _, _, purchase_date in titles)
        plan["cdi"] = _index_fetch_executor.submit(fetch_bcb_series, BCB_SERIES_CDI, start_date)
        if any(indexer == "IPCA" for _, indexer, _, _ in titles):
            plan["ipca"] = _index_fetch_executor.submit(
                fetch_bcb_series, BCB_SERIES_IPCA, start_date.replace(day=1)
            )
    return plan


def finish_fixed_income_refresh(current_user_id, plan):
    updated_assets = []
    failed_assets = list(plan["failed_assets"])

    def series_result(future):
        # fetch_bcb_series tem timeout proprio; o result() nao fica preso.
        if future is None:
            return None, None
        try:
            return future.result(), None
        except Exception as exc:
            logger.exception(f"Erro ao buscar indices no BCB: {exc}")
            return None, str(exc) or "Erro ao buscar indices no BCB"

    cdi_series, cdi_error = series_result(plan["cdi"])
    ipca_series, ipca_error = series_result(plan["ipca"])

    with get_db() as conn:
        for inv, indexer, rate, purchase_date in plan["titles"]:
            error = cdi_error or (ipca_error if indexer == "IPCA" else None)
            if error:
                failed_assets.append(fixed_income_asset_result(inv, status="failed", error=error))
                continue

            try:
                cdi_daily = [value for day, value in cdi_series if day >= purchase_date]
                accumulated = fixed_income_accrual_factor(
                    indexer, rate, cdi_daily, ipca_series, purchase_date
                )
                new_price = rounded_money(safe_float(inv.get("average_price")) * accumulated)
                quote_metadata = {"provider": "bcb", "indexer": indexer}
                if indexer == "CDI":
                    quote_metadata["cdi_percentage"] = rate
                else:
                    quote_metadata["annual_rate"] = rate
                record_price_quote(
                    conn,
                    current_user_id,
                    inv["asset_id"],
                    new_price,
                    asset_class=inv["asset_class"],
                    transaction_id=inv["id"],
                    source="cdi",
                    metadata=quote_metadata,
                )
            except Exception as exc:
                logger.exception(f"Erro ao corrigir {inv['ticker_or_name']} pelo BCB: {exc}")
                failed_assets.append(fixed_income_asset_result(
                    inv, status="failed", error=str(exc) or "Erro ao corrigir o titulo"
                ))
                continue

            updated_assets.append(fixed_income_asset_result(
                inv, price=new_price, source="cdi", status="updated"
            ))

    return {
        "updated_count": len(updated_assets),
        "updated_assets": updated_assets,
        "failed_assets": failed_assets,
    }


def refresh_fixed_income_prices(current_user_id, investments_to_update):
    return finish_fixed_income_refresh(
        current_user_id, start_fixed_income_refresh(investments_to_update)
    )


# Serie historica para a Evolucao do Patrimonio: cada mes passado corrige a
# renda fixa ate o fim daquele mes. Guardada em memoria pelo mesmo tempo do
# historico de precos, para o grafico nao buscar o BCB a cada abertura.
# {"cdi" | "ipca": (instante, desde, serie)}: cada serie desde `desde`, que
# serve qualquer pedido que comece depois (a rentabilidade pede o CDI desde o
# inicio da janela, a renda fixa desde a compra mais antiga, os indices o IPCA).
_index_history_cache = {}
_index_history_lock = threading.Lock()


def _bcb_series_since(name, series_code, start):
    """A serie `series_code` desde `start` (meia-noite), pelo cache acima.

    Sem cobertura, busca desde o mais cedo entre `start` e o piso do historico
    (`history_fetch_floor()`): a proxima janela, menor ou maior ate la, le o cache."""
    now = time.monotonic()
    with _index_history_lock:
        cached = _index_history_cache.get(name)
        if cached and now - cached[0] < HISTORY_CACHE_TTL_SECONDS and cached[1] <= start:
            return [item for item in cached[2] if item[0] >= start]
    floor = history_fetch_floor()
    fetch_from = min(start, datetime(floor.year, floor.month, floor.day))
    series = fetch_bcb_series(series_code, fetch_from)
    with _index_history_lock:
        # Duas buscas ao mesmo tempo (o CDI da janela e o da renda fixa): a
        # que cobre menos nao apaga a que cobre mais.
        current = _index_history_cache.get(name)
        if not current or fetch_from <= current[1] or now - current[0] >= HISTORY_CACHE_TTL_SECONDS:
            _index_history_cache[name] = (now, fetch_from, series)
    return [item for item in series if item[0] >= start]


def cdi_since(start_date):
    """[(data, taxa diaria)] do CDI desde `start_date`."""
    return _bcb_series_since("cdi", BCB_SERIES_CDI, datetime(start_date.year, start_date.month, start_date.day))


def ipca_since(start_date):
    """[(mes, variacao)] do IPCA desde o mes de `start_date`."""
    return _bcb_series_since("ipca", BCB_SERIES_IPCA, datetime(start_date.year, start_date.month, 1))


def index_history(start_date, need_ipca):
    """{"cdi": [(data, taxa diaria)], "ipca": [(mes, variacao)] ou None}, desde start_date."""
    return {
        "cdi": cdi_since(start_date),
        "ipca": ipca_since(start_date) if need_ipca else None,
    }


def accrual_factor_until(metadata, purchase_date, until, series):
    """Fator do titulo da compra ate `until`, com as series ja buscadas.

    None quando o titulo nao tem taxa (preco manual) ou a serie falta: quem
    chama fica com o custo.
    """
    indexer, rate = fixed_income_rate_terms(metadata)
    if indexer is None or not series or series.get("cdi") is None:
        return None
    if indexer == "IPCA" and series.get("ipca") is None:
        return None
    cdi_daily = [value for day, value in series["cdi"] if purchase_date <= day <= until]
    ipca = [(month, value) for month, value in (series.get("ipca") or []) if month <= until]
    return fixed_income_accrual_factor(indexer, rate, cdi_daily, ipca, purchase_date)
