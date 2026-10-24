"""Tesouro Direto: o titulo marcado a mercado, agrupado e liquido de taxas.

Cada compra do Tesouro e gravada como os outros titulos de renda fixa
(quantidade 1, preco = valor aplicado, taxa contratada no metadata). Aqui:

- **Quantos titulos a compra comprou** (`lot_units()`): o informado pelo
  dono (`metadata.treasury_units`) ou valor aplicado / PU da compra. O PU da
  compra e o do arquivo do Tesouro na data; num titulo sem cupom, ajustado da
  taxa do arquivo para a taxa contratada (PU = VNA / (1 + taxa) ^ (du/252)),
  porque o preco muda ao longo do dia e a taxa contratada e a que o dono viu.
- **Valor bruto** = titulos x PU de mercado do dia (PU de venda: o que o
  Tesouro paga na recompra) -- a marcacao a mercado, nao a curva.
- **Liquido** = bruto - custodia da B3 - IOF - IR, lote a lote:
  custodia de 0,20% a.a. pro rata die sobre o valor de mercado de cada dia,
  provisionada desde a liquidacao (D+1) e no maximo desde 01/01/2025, quando
  a B3 passou a cobrar no evento em vez de semestralmente (OC B3 014/2024-VPC);
  o Tesouro Selic e isento ate R$ 10 mil por CPF. IOF regressivo nos 30
  primeiros dias (Decreto 6.306/2007, anexo) e IR pela tabela regressiva
  (Lei 11.033/2004, art. 1o) sobre o rendimento, que a custodia e o IOF
  reduzem.
- **Agrupado**: as compras do mesmo titulo (tipo + vencimento) viram uma
  posicao, com a **taxa media** que, aplicada a todas as compras, da o mesmo
  valor no vencimento: sum(C_i (1 + t)^T_i) = sum(C_i (1 + t_i)^T_i), C_i o
  custo ainda aplicado e T_i os anos (du/252) da compra ao vencimento -- a
  taxa que a posicao inteira rende se levada ao vencimento. Fica perto da
  media ponderada pelo custo, um pouco acima (convexidade) e puxada para as
  compras mais longas; sem vencimento conhecido, e a media ponderada.

Sem o arquivo do Tesouro (ou um titulo que ele nao tem), o valor bruto e a
curva de sempre (a cotacao gravada pela atualizacao do BCB): `valuation`
"CURVE" na resposta.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import tesouro_client
from applog import get_logger
from dates import parse_iso_date
from db import get_db
from money import rounded_money
from services.asset_categories import asset_category
from services.fixed_income import (
    closed_fixed_income_title_ids,
    fixed_income_asset_result,
    fixed_income_rate_terms,
    regressive_ir_rate,
)
from services.prices import record_price_quote
from validators import ValidationError, safe_float

logger = get_logger(__name__)

CUSTODY_ANNUAL_RATE = 0.002
CUSTODY_PROVISION_START = date(2025, 1, 1)
SELIC_CUSTODY_EXEMPT = 10000.0
# Uma taxa contratada mais longe que isso da do arquivo e outro titulo, ou um
# erro de digitacao: o PU do arquivo fica como esta.
MAX_RATE_ADJUSTMENT = 0.015
# IOF sobre o rendimento por dia corrido desde a aplicacao (1 a 29), em %.
IOF_TABLE = (
    100, 96, 93, 90, 86, 83, 80, 76, 73, 70, 66, 63, 60, 56, 53, 50,
    46, 43, 40, 36, 33, 30, 26, 23, 20, 16, 13, 10, 6, 3,
)


def is_treasury_title(asset_class, ticker, metadata):
    metadata = metadata or {}
    return asset_category(asset_class, ticker, metadata.get("fixed_income_type") or None) == "TESOURO"


def iof_rate(days):
    if days >= 30:
        return 0.0
    return IOF_TABLE[max(days, 0)] / 100


def business_years(start, end):
    """(du / 252) entre duas datas: dias uteis contados como dias de semana,
    descontados os ~9 feriados nacionais de um ano (252 de 261)."""
    start, end = _as_date(start), _as_date(end)
    if end <= start:
        return 0.0
    days = (end - start).days
    weeks, rest = divmod(days, 7)
    weekdays = weeks * 5
    weekday = start.weekday()
    for offset in range(rest):
        if (weekday + offset) % 7 < 5:
            weekdays += 1
    return weekdays / 261


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = parse_iso_date(value)
    return parsed.date() if parsed else None


def title_key(name, prices=None):
    """Chave do titulo para agrupar: (tipo, vencimento) do arquivo, ou (tipo, ano) pelo nome."""
    series = prices.find_title(name) if prices is not None else None
    if series is not None:
        return (series.title_type, series.maturity.isoformat())
    title_type = tesouro_client.title_type_from_name(name)
    year = tesouro_client.title_year_from_name(name)
    if title_type and year:
        return (title_type, str(year))
    return None


def contracted_rate(metadata):
    """A taxa contratada como fracao ao ano (IPCA+, prefixado), ou None."""
    indexer, rate = fixed_income_rate_terms(metadata)
    if indexer in ("IPCA", "PRE"):
        return rate
    return None


def purchase_pu(series, purchase_date, metadata):
    """PU pago na compra: o do arquivo na data, na taxa contratada quando da."""
    row = series.purchase_row(purchase_date)
    if row is None:
        return None
    pu = row["buy_pu"] or row["base_pu"] or row["sell_pu"]
    if not pu or pu <= 0:
        return None
    rate = contracted_rate(metadata)
    market_rate = row["buy_rate"]
    if (
        series.title_type in tesouro_client.ZERO_COUPON_TYPES
        and series.title_type != tesouro_client.SELIC
        and rate is not None
        and market_rate is not None
        and abs(rate - market_rate / 100) <= MAX_RATE_ADJUSTMENT
    ):
        years = business_years(row["date"], series.maturity)
        pu *= ((1 + market_rate / 100) / (1 + rate)) ** years
    return pu


def lot_units(series, lot):
    """Quantos titulos a compra comprou (antes dos resgates), ou None."""
    typed = safe_float((lot["metadata"] or {}).get("treasury_units"), None)
    if typed is not None and typed > 0:
        return typed
    if series is None or lot["purchase_date"] is None:
        return None
    pu = purchase_pu(series, lot["purchase_date"], lot["metadata"])
    if not pu:
        return None
    paid = lot["original_applied"] - safe_float((lot["metadata"] or {}).get("other_costs"))
    return max(paid, 0) / pu if paid > 0 else None


def market_value(series, units, on_day):
    pu = series.market_pu(on_day) if series is not None else None
    if pu is None or units is None:
        return None
    return units * pu


def market_value_on(asset_class, ticker, metadata, applied, original_applied, on_day, prices="auto"):
    """Valor bruto de mercado de um titulo do Tesouro em `on_day`, ou None.

    E a mesma conta da Posicao para a evolucao e a rentabilidade (os meses
    passados pelo PU daquele dia). None fora do Tesouro, sem precos, sem o
    titulo no arquivo ou antes da compra: quem chama fica com a curva."""
    if asset_class != "FIXED_INCOME" or not is_treasury_title(asset_class, ticker, metadata):
        return None
    if prices == "auto":
        prices = tesouro_client.get_prices()
    if prices is None or original_applied <= 0:
        return None
    purchase_date = _as_date((metadata or {}).get("purchase_date"))
    on_day = _as_date(on_day)
    if purchase_date is None or on_day is None or on_day < purchase_date:
        return None
    series = prices.find_title(ticker)
    lot = {"metadata": metadata, "purchase_date": purchase_date, "original_applied": original_applied}
    units = lot_units(series, lot)
    value = market_value(series, units, on_day)
    if value is None:
        return None
    return value * (applied / original_applied)


def custody_fee(series, units, purchase_date, today, gross_today, cost):
    """Custodia provisionada da B3 ate hoje (sem a isencao do Selic)."""
    start = max(purchase_date + timedelta(days=1), CUSTODY_PROVISION_START)
    if today <= start:
        return 0.0
    if series is not None and units:
        points = []
        first_pu = series.market_pu(start)
        if first_pu:
            points.append((start, first_pu))
        points.extend(series.daily_values(start + timedelta(days=1), today))
        if points:
            total = 0.0
            for index, (day, pu) in enumerate(points):
                until = points[index + 1][0] if index + 1 < len(points) else today
                total += units * pu * (until - day).days
            return CUSTODY_ANNUAL_RATE * total / 365
    # Sem o historico de precos: o valor medio entre o custo e o de hoje.
    average = (cost + gross_today) / 2
    return CUSTODY_ANNUAL_RATE * average * (today - start).days / 365


def taxes_on_sale(gross, cost, custody, days):
    """(IOF, IR) de vender hoje: o rendimento ja sem a custodia."""
    income = gross - custody - cost
    if income <= 0:
        return 0.0, 0.0
    iof = income * iof_rate(days)
    income_tax = (income - iof) * regressive_ir_rate(days)
    return iof, income_tax


def average_rate(lots, maturity):
    """Taxa media das compras (ver o docstring do modulo), ou None."""
    weighted = [(lot["cost"], lot["rate"], lot["purchase_date"]) for lot in lots if lot["rate"] is not None and lot["cost"] > 0]
    if not weighted:
        return None
    total_cost = sum(cost for cost, _, _ in weighted)
    simple = sum(cost * rate for cost, rate, _ in weighted) / total_cost
    if maturity is None or len(weighted) == 1:
        return simple if len(weighted) > 1 else weighted[0][1]
    terms = [(cost, rate, business_years(purchase, maturity)) for cost, rate, purchase in weighted]
    if any(years <= 0 for _, _, years in terms):
        return simple
    target = sum(cost * (1 + rate) ** years for cost, rate, years in terms)

    def value(rate_guess):
        return sum(cost * (1 + rate_guess) ** years for cost, _, years in terms)

    low = min(rate for _, rate, _ in terms)
    high = max(rate for _, rate, _ in terms)
    if high - low < 1e-12:
        return low
    for _ in range(100):
        middle = (low + high) / 2
        if value(middle) < target:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def value_lot(lot, series, today):
    """Bruto, custodia, IOF, IR e liquido de uma compra, hoje."""
    units_bought = lot_units(series, lot)
    fraction = lot["applied"] / lot["original_applied"] if lot["original_applied"] > 0 else 0
    units = units_bought * fraction if units_bought is not None else None
    gross = market_value(series, units, today)
    valuation = "MARKET"
    if gross is None:
        gross = lot["curve_value"]
        valuation = "CURVE"
    purchase_date = lot["purchase_date"] or today
    custody = custody_fee(series if valuation == "MARKET" else None, units, purchase_date, today, gross, lot["applied"])
    days = (today - purchase_date).days
    return {
        "id": lot["id"],
        "purchase_date": purchase_date.isoformat(),
        "invested": lot["applied"],
        "rate": lot["rate"],
        "units": units,
        "purchase_pu": (lot["original_applied"] / units_bought) if units_bought else None,
        "gross": gross,
        "custody": custody,
        "days": days,
        "valuation": valuation,
        "title_type": series.title_type if series is not None else None,
    }


def finish_lots(lots, today):
    """Aplica a isencao do Selic e calcula IOF, IR e liquido de cada compra."""
    selic_gross = sum(lot["gross"] for lot in lots if lot["title_type"] == tesouro_client.SELIC)
    if selic_gross > 0:
        exempt_share = min(SELIC_CUSTODY_EXEMPT / selic_gross, 1.0)
        for lot in lots:
            if lot["title_type"] == tesouro_client.SELIC:
                lot["custody"] *= 1 - exempt_share
    for lot in lots:
        iof, income_tax = taxes_on_sale(lot["gross"], lot["invested"], lot["custody"], lot["days"])
        lot["iof"] = iof
        lot["income_tax"] = income_tax
        lot["net"] = lot["gross"] - lot["custody"] - iof - income_tax
    return lots


def build_treasury_positions(lot_entries, today=None, prices="auto"):
    """As compras do Tesouro agrupadas por titulo.

    `lot_entries`: uma por compra aberta, com id, asset_id, ticker, metadata,
    applied (custo que resta), original_applied, curve_value (bruto pela
    curva) e os campos da rentabilidade com proventos (contributed,
    sold_cost_basis, realized_net_profit). Devolve [{key, lots, ...}] na ordem
    da primeira compra de cada titulo."""
    today = _as_date(today or datetime.now())
    if prices == "auto":
        prices = tesouro_client.get_prices()

    groups = {}
    for entry in lot_entries:
        key = title_key(entry["ticker"], prices) or ("ASSET", str(entry["asset_id"]))
        groups.setdefault(key, []).append(entry)

    selic_lots = []
    positions = []
    for key, entries in groups.items():
        entries.sort(key=lambda entry: (entry["purchase_date"] or today, str(entry["id"])))
        series = prices.find_title(entries[0]["ticker"]) if prices is not None else None
        lots = []
        for entry in entries:
            lot = value_lot({
                **entry,
                "rate": rate_of(entry["metadata"]),
            }, series, today)
            lots.append(lot)
        if lots and lots[0]["title_type"] == tesouro_client.SELIC:
            selic_lots.extend(lots)
        positions.append({"key": key, "series": series, "entries": entries, "lots": lots})

    # A isencao do Selic e por CPF: vale sobre todos os titulos Selic juntos.
    finish_lots(selic_lots, today)
    for position in positions:
        if position["lots"] and position["lots"][0]["title_type"] != tesouro_client.SELIC:
            finish_lots(position["lots"], today)
        summarize_position(position, prices, today)
    return positions


def rate_of(metadata):
    indexer, rate = fixed_income_rate_terms(metadata)
    return rate if indexer is not None else None


def summarize_position(position, prices, today):
    series = position["series"]
    lots = position["lots"]
    entries = position["entries"]
    maturity = series.maturity if series is not None else None
    units_known = all(lot["units"] is not None for lot in lots)
    units = sum(lot["units"] for lot in lots) if units_known else None
    latest = series.row_on_or_before(today) if series is not None else None
    rate_lots = [
        {"cost": lot["invested"], "rate": lot["rate"], "purchase_date": _as_date(lot["purchase_date"])}
        for lot in lots
    ]
    valuation = "MARKET" if all(lot["valuation"] == "MARKET" for lot in lots) else "CURVE"
    position.update({
        "invested": sum(lot["invested"] for lot in lots),
        "gross": sum(lot["gross"] for lot in lots),
        "custody": sum(lot["custody"] for lot in lots),
        "iof": sum(lot["iof"] for lot in lots),
        "income_tax": sum(lot["income_tax"] for lot in lots),
        "net": sum(lot["net"] for lot in lots),
        "units": units,
        "average_rate": average_rate(rate_lots, maturity),
        "maturity_date": maturity.isoformat() if maturity else None,
        "title_type": series.title_type if series is not None else tesouro_client.title_type_from_name(entries[0]["ticker"]),
        "market_pu": latest["sell_pu"] or latest["base_pu"] if latest else None,
        "market_rate": latest["sell_rate"] / 100 if latest and latest["sell_rate"] is not None else None,
        "price_date": latest["date"].isoformat() if latest else None,
        "valuation": valuation,
        "prices_fetched_at": prices.fetched_at if prices is not None else None,
    })
    return position


def lot_payload(lot):
    """Uma compra na resposta da API (para o resgate e o detalhe da posicao)."""
    return {
        "id": lot["id"],
        "purchase_date": lot["purchase_date"],
        "invested": rounded_money(lot["invested"]),
        "rate": lot["rate"],
        "units": round(lot["units"], 6) if lot["units"] is not None else None,
        "purchase_pu": rounded_money(lot["purchase_pu"]) if lot["purchase_pu"] else None,
        "gross": rounded_money(lot["gross"]),
        "custody": rounded_money(lot["custody"]),
        "iof": rounded_money(lot["iof"]),
        "income_tax": rounded_money(lot["income_tax"]),
        "net": rounded_money(lot["net"]),
        "valuation": lot["valuation"],
    }


# --- Resgate ------------------------------------------------------------------

def allocate_treasury_redemption(lots, amount):
    """Resgate de um titulo agrupado: o Tesouro vende primeiro os titulos
    comprados antes (PEPS). Cada parte vira um resgate da compra dela
    (`related_id`), com o custo proporcional ao valor bruto tirado daquela
    compra -- a mesma regra do resgate parcial de um titulo so. Valor acima do
    bruto da posicao: erro.

    `lots` no formato de `lot_payload()` (id, purchase_date, invested, gross).
    Devolve [{lot_id, amount, cost}]; o custo nao e arredondado (e o preco
    medio da operacao, como era no cliente)."""
    ordered = sorted(lots or [], key=lambda lot: (str(lot.get("purchase_date")), str(lot.get("id"))))
    rest = rounded_money(amount or 0)
    if not rest > 0:
        raise ValidationError("Informe um valor de resgate.")
    parts = []
    for lot in ordered:
        if rest <= 0:
            break
        gross = safe_float(lot.get("gross"))
        if gross <= 0:
            continue
        take = min(rest, rounded_money(gross))
        parts.append({
            "lot_id": lot["id"],
            "amount": rounded_money(take),
            "cost": safe_float(lot.get("invested")) * (take / gross),
        })
        rest = rounded_money(rest - take)
    if rest > 0:
        raise ValidationError("O valor passa do saldo bruto do título.")
    return parts


def redemption_parts(position, amount):
    """As partes do resgate de uma posicao de renda fixa da carteira
    (`build_portfolio_snapshot()`): PEPS pelas compras quando ela traz `lots`
    (Tesouro), senao uma parte so, com custo = preco medio x bruto resgatado /
    valor bruto atual."""
    if position.get("lots"):
        return allocate_treasury_redemption(position["lots"], amount)
    amount = rounded_money(amount or 0)
    if not amount > 0:
        raise ValidationError("Informe um valor de resgate.")
    current_value = safe_float(position.get("current_value"))
    if current_value <= 0:
        raise ValidationError("O titulo nao tem saldo para resgatar.")
    return [{
        "lot_id": position["id"],
        "amount": amount,
        "cost": safe_float(position.get("average_price")) * (amount / current_value),
    }]


# --- "Atualizar cotacoes" ---------------------------------------------------

_refresh_executor = ThreadPoolExecutor(max_workers=1)


def treasury_buys(investments):
    """As compras do Tesouro ainda abertas (o mesmo filtro da correcao pelo BCB)."""
    closed_ids = closed_fixed_income_title_ids(investments)
    buys = []
    for inv in investments:
        metadata = inv.get("metadata") or {}
        if inv.get("asset_class") != "FIXED_INCOME" or safe_float(inv.get("quantity")) <= 0:
            continue
        if metadata.get("is_redemption") or str(inv.get("id")) in closed_ids:
            continue
        if is_treasury_title(inv.get("asset_class"), inv.get("ticker_or_name"), metadata):
            buys.append(inv)
    return buys


def start_treasury_refresh(investments):
    """Busca o arquivo do Tesouro em segundo plano, se ha titulo do Tesouro a avaliar."""
    if not treasury_buys(investments):
        return None
    return _refresh_executor.submit(tesouro_client.get_prices, True)


def finish_treasury_refresh(current_user_id, investments, pending, fixed_income_plan):
    """Grava o valor de mercado de cada compra do Tesouro como a cotacao dela.

    O titulo avaliado sai do plano do BCB (`start_fixed_income_refresh()`):
    a curva nao grava uma cotacao por cima, e um titulo sem taxa informada nao
    e mais uma falha -- o mercado nao precisa da taxa."""
    result = {"updated_assets": [], "failed_assets": []}
    if pending is None:
        return result
    try:
        prices = pending.result()
    except Exception as exc:
        logger.warning(f"Precos do Tesouro indisponiveis: {exc}")
        prices = None
    if prices is None:
        return result

    today = datetime.now()
    valued_ids = set()
    with get_db() as conn:
        for inv in treasury_buys(investments):
            metadata = inv.get("metadata") or {}
            applied = safe_float(inv.get("quantity")) * safe_float(inv.get("average_price"))
            value = market_value_on(
                "FIXED_INCOME", inv.get("ticker_or_name"), metadata, applied, applied, today, prices,
            )
            if value is None:
                continue
            series = prices.find_title(inv.get("ticker_or_name"))
            row = series.row_on_or_before(today)
            record_price_quote(
                conn,
                current_user_id,
                inv["asset_id"],
                rounded_money(value),
                asset_class="FIXED_INCOME",
                transaction_id=inv["id"],
                source="tesouro",
                metadata={
                    "provider": "tesouro_transparente",
                    "price_date": row["date"].isoformat() if row else None,
                    "market_pu": row["sell_pu"] if row else None,
                    "market_rate": row["sell_rate"] if row else None,
                },
            )
            valued_ids.add(str(inv["id"]))
            result["updated_assets"].append(fixed_income_asset_result(
                inv, price=rounded_money(value), source="tesouro", status="updated"
            ))

    fixed_income_plan["titles"] = [
        title for title in fixed_income_plan["titles"] if str(title[0].get("id")) not in valued_ids
    ]
    fixed_income_plan["failed_assets"] = [
        failure for failure in fixed_income_plan["failed_assets"]
        if str(failure.get("investment_id")) not in valued_ids
    ]
    return result
