"""Carteira: posicoes, atualizacao de cotacoes e a evolucao mensal.

`build_portfolio_snapshot()` agrega as movimentacoes em uma posicao por ativo;
`refresh_materialized_positions()` regrava `investment_positions` a partir
dele (tabela derivada), so na leitura de /api/investment-positions: as
gravacoes nao pagam por uma tabela que nenhuma tela le. `refresh_market_prices()` busca cotacao so para os
ativos cotados com posicao aberta (`unique_market_asset_targets()`).
`build_portfolio_evolution()` monta a serie de "Evolucao do Patrimonio".
"""

from datetime import datetime
import math

from asset_classes import is_crypto_asset, is_quoted_asset
from dates import month_end, month_key, month_label, parse_iso_date, subtract_months
from db import encode_metadata, get_db
from money import rounded_money
from services.fixed_income import (
    fixed_income_is_tax_free,
    accrual_factor_until,
    fixed_income_net_value,
    fixed_income_title_closed,
    movement_affects_fixed_income_position,
)
from services import market_listing
import tesouro_client
from services.asset_categories import category_fields
from services.investments import asset_display_name, fetch_investments
from services.prices import (
    get_market_prices_with_status,
    market_price_provider,
    quote_info_from_investment,
    record_price_quote,
    ticker_key,
)
from services.proceeds import paid_proceeds_by_asset
from services.treasury import (
    build_treasury_positions,
    is_treasury_title,
    lot_payload,
)
from validators import safe_float
from applog import get_logger

logger = get_logger(__name__)

def asset_market_kind(asset_class, ticker):
    """ACAO, ETF, BDR ou FII de um ativo cotado, CRIPTO de um criptoativo; None nas demais.

    A classe STOCKS junta acao, ETF e BDR; a tela de posicao separa um do outro.
    E o tipo do IR (`market_listing.tax_kind`), com o ETF de renda fixa
    mostrado junto dos ETFs.
    """
    if is_crypto_asset(asset_class, ticker):
        return "CRIPTO"
    kind = market_listing.tax_kind(ticker, asset_class)
    return "ETF" if kind == "ETF_RF" else kind


def investment_movement_date(investment):
    metadata = investment.get("metadata") or {}
    for key in ("redemption_date", "sale_date", "purchase_date"):
        parsed = parse_iso_date(metadata.get(key))
        if parsed:
            return parsed
    return parse_iso_date(investment.get("created_at")) or datetime.now()


def historical_price_for_month(historical_prices, ticker, target_month_key):
    ticker_prices = historical_prices.get(ticker_key(ticker), {})
    if not isinstance(ticker_prices, dict):
        return None

    price = safe_float(ticker_prices.get(target_month_key), None)
    if price is not None and math.isfinite(price) and price > 0:
        return price

    previous_keys = sorted(
        key for key in ticker_prices
        if isinstance(key, str) and key <= target_month_key
    )
    if not previous_keys:
        return None

    price = safe_float(ticker_prices.get(previous_keys[-1]), None)
    if price is not None and math.isfinite(price) and price > 0:
        return price
    return None


def position_value_today(asset_class, quantity, applied, original_applied, current_price, metadata):
    """Valor bruto de HOJE de uma posicao, pela cotacao gravada.

    E a regra da Posicao (`build_portfolio_snapshot()`) e tambem a do mes
    atual da evolucao e da rentabilidade (`portfolio_month_positions()`): as
    telas mostram o mesmo "Carteira" porque saem daqui.

    Renda fixa: a cotacao e o valor do titulo inteiro (a ultima correcao do
    BCB, ou o preco manual); o fator dela sobre o aplicado original vale para
    o que resta depois dos resgates parciais. O resto: quantidade vezes a cotacao.
    """
    if asset_class == "FIXED_INCOME":
        price = safe_float(current_price, applied)
        if original_applied > 0:
            price = applied * (price / original_applied)
        return max(price, 0)
    return quantity * safe_float(current_price)


def portfolio_evolution_months(months_back):
    current_month = datetime(datetime.now().year, datetime.now().month, 1)
    return [
        subtract_months(current_month, months_back - 1 - index)
        for index in range(months_back)
    ]


def evolution_group_key(investment):
    """Chave da posicao a que a movimentacao pertence na evolucao, ou None se ela
    fica de fora. Renda fixa agrupa pelo titulo (id da compra; o resgate aponta
    para ele em `related_id`), o resto por classe:ticker."""
    metadata = investment.get("metadata") or {}
    asset_class = investment.get("asset_class")
    ticker = ticker_key(investment.get("ticker_or_name"))
    if not asset_class or not ticker:
        return None
    if safe_float(investment.get("quantity")) == 0:
        return None
    if movement_affects_fixed_income_position(investment):
        return str(metadata.get("related_id"))
    if asset_class == "FIXED_INCOME" and metadata.get("is_redemption"):
        return None
    return str(investment.get("id")) if asset_class == "FIXED_INCOME" else f"{asset_class}:{ticker}"


def add_movement_to_positions(positions, investment):
    """Soma a movimentacao a sua posicao em `positions` ({group_key: posicao}).

    E o acumulo da evolucao mensal e da rentabilidade diaria (services/returns.py):
    quantidade, aplicado pelo custo medio e, na renda fixa, o titulo original."""
    group_key = evolution_group_key(investment)
    if group_key is None:
        return None
    metadata = investment.get("metadata") or {}
    asset_class = investment.get("asset_class")
    ticker = ticker_key(investment.get("ticker_or_name"))
    quantity = safe_float(investment.get("quantity"))
    average_price = safe_float(investment.get("average_price"))

    if group_key not in positions:
        positions[group_key] = {
            "ticker": ticker,
            "class": asset_class,
            "quantity": 0,
            "applied": 0,
            "original_applied": 0,
            "current_price": safe_float(investment.get("current_price"), average_price),
            "metadata": metadata,
        }

    position = positions[group_key]
    # Custo medio (apply_average_cost): a venda tira o custo das cotas
    # vendidas, nao o valor da venda — uma venda com lucro nao zera o aplicado.
    position["applied"] += safe_float(investment.get("cost_amount"), quantity * average_price)
    if not movement_affects_fixed_income_position(investment):
        position["quantity"] += quantity
        if asset_class == "FIXED_INCOME" and quantity > 0:
            position["original_applied"] += quantity * average_price
            position["metadata"] = metadata
            position["ticker"] = ticker
            position["purchase_date"] = investment_movement_date(investment)
    if investment.get("current_price") is not None and not movement_affects_fixed_income_position(investment):
        position["current_price"] = safe_float(investment.get("current_price"), average_price)
    return group_key


def position_is_open(position):
    """Posicao com quantidade e aplicado positivos (e titulo de renda fixa nao encerrado)."""
    if position["quantity"] <= 0 or position["applied"] <= 0:
        return False
    return not (position["class"] == "FIXED_INCOME" and fixed_income_title_closed(position["applied"]))


def portfolio_month_positions(
    investments_data, historical_prices, month_start, index_series, current_month_key, movement_dates=None,
    treasury_prices="auto",
):
    """Cada posicao no fim do mes: {group_key: {ticker, class, applied, gross, net}}.

    `gross` e o valor de mercado; `net` desconta o IR estimado da renda fixa.
    So entram as posicoes com quantidade e valor aplicado positivos.
    `movement_dates` e a data de cada movimentacao, na mesma ordem, quando quem
    chama avalia varios meses (`iter_portfolio_months()`) e ja as leu.
    `treasury_prices` sao os precos do Tesouro (`tesouro_client.get_prices()`),
    lidos uma vez por quem avalia varios meses.
    """
    target_key = month_key(month_start)
    target_end = month_end(month_start)
    positions = {}

    if movement_dates is None:
        movement_dates = [investment_movement_date(investment) for investment in investments_data]
    for moved_at, investment in zip(movement_dates, investments_data):
        if moved_at > target_end:
            continue
        add_movement_to_positions(positions, investment)

    valued = {}
    treasury_entries = []
    for group_key, position in positions.items():
        quantity = position["quantity"]
        applied_value = position["applied"]
        if not position_is_open(position):
            continue

        is_current_month = target_key == current_month_key
        if is_current_month:
            # O mes atual vai ate hoje e vale o que a Posicao mostra: a mesma
            # regra e a mesma cotacao gravada (bolsa: a ultima cotacao, nao o
            # fechamento do mes no historico; renda fixa: a ultima correcao do
            # BCB ou o preco manual, nao a serie recalculada aqui).
            market_value = position_value_today(
                position["class"],
                quantity,
                applied_value,
                position["original_applied"],
                position.get("current_price"),
                position["metadata"],
            )
        elif is_quoted_asset(position["class"], position["ticker"]):
            price = historical_price_for_month(
                historical_prices,
                position["ticker"],
                target_key,
            )
            if price is None:
                price = safe_float(position.get("current_price"), applied_value / quantity)
            market_value = quantity * price
        elif position["class"] == "FIXED_INCOME" and index_series and position.get("purchase_date"):
            # Mes passado: corrigido pela serie ate o fim do mes.
            purchase = parse_iso_date(position["purchase_date"])
            factor = accrual_factor_until(position["metadata"], purchase, target_end, index_series) if purchase else None
            market_value = applied_value * factor if factor else applied_value
        else:
            market_value = applied_value

        # Tesouro Direto: marcado a mercado e liquido como na Posicao, abaixo.
        if position["class"] == "FIXED_INCOME" and is_treasury_title(position["class"], position["ticker"], position["metadata"]):
            purchase = parse_iso_date((position["metadata"] or {}).get("purchase_date"))
            treasury_entries.append({
                "id": group_key,
                "asset_id": group_key,
                "ticker": position["ticker"],
                "metadata": position["metadata"],
                "purchase_date": purchase.date() if purchase else None,
                "applied": applied_value,
                "original_applied": position["original_applied"],
                "curve_value": market_value,
            })
            continue

        net_value = fixed_income_net_value(
            position["class"],
            position["metadata"],
            applied_value,
            market_value,
            # Hoje no mes atual, como a Posicao (a faixa do IR pode mudar
            # entre hoje e o fim do mes).
            datetime.now() if is_current_month else target_end,
        )
        valued[group_key] = {
            "ticker": position["ticker"],
            "class": position["class"],
            "applied": applied_value,
            "gross": market_value,
            "net": net_value,
        }

    if treasury_entries:
        valuation_day = datetime.now() if target_key == current_month_key else target_end
        for treasury_position in build_treasury_positions(treasury_entries, valuation_day, treasury_prices):
            for entry, lot in zip(treasury_position["entries"], treasury_position["lots"]):
                valued[entry["id"]] = {
                    "ticker": entry["ticker"],
                    "class": "FIXED_INCOME",
                    "applied": entry["applied"],
                    "gross": lot["gross"],
                    "net": lot["net"],
                }

    return valued


def iter_portfolio_months(investments_data, historical_prices, months_back, index_series=None):
    """(inicio do mes, posicoes no fim do mes) dos ultimos `months_back` meses.

    E o laco da evolucao; a rentabilidade (services/returns.py) le as posicoes
    uma a uma daqui, para as duas sairem da mesma avaliacao."""
    current_month_key = month_key(datetime.now())
    movement_dates = [investment_movement_date(investment) for investment in investments_data]
    treasury_prices = tesouro_client.get_prices()
    for month_start in portfolio_evolution_months(months_back):
        yield month_start, portfolio_month_positions(
            investments_data, historical_prices, month_start, index_series, current_month_key, movement_dates,
            treasury_prices,
        )


def build_portfolio_evolution(investments_data, historical_prices, months_back, index_series=None):
    """Patrimonio mes a mes. `index_series` (CDI/IPCA, de fixed_income.index_history)
    corrige a renda fixa nos meses passados; sem ele, eles ficam no custo.

    Duas bases, lado a lado: `patrimonio` / `ganhoCapital*` sao liquidos do IR
    estimado da renda fixa; `patrimonioBruto` / `ganhoCapitalBruto` sao o valor
    de mercado, a mesma base do "Carteira" (current_balance) da Posicao."""
    evolution = []

    for month_start, positions in iter_portfolio_months(
        investments_data, historical_prices, months_back, index_series,
    ):
        applied_total = 0
        gross_total = 0
        net_total = 0
        for position in positions.values():
            applied_total += position["applied"]
            gross_total += position["gross"]
            net_total += position["net"]

        gain = net_total - applied_total
        gross_gain = gross_total - applied_total
        evolution.append({
            "month": month_label(month_start),
            "month_key": month_key(month_start),
            "patrimonio": rounded_money(max(net_total, 0)),
            "patrimonioBruto": rounded_money(max(gross_total, 0)),
            "valorAplicado": rounded_money(max(applied_total, 0)),
            "ganhoCapital": rounded_money(max(gain, 0)),
            "ganhoCapitalReal": rounded_money(gain),
            "ganhoCapitalBruto": rounded_money(gross_gain),
        })

    return evolution


def open_asset_ids(investments):
    # Vendas entram com quantidade negativa; um ativo zerado nao precisa de cotacao.
    quantities = {}
    for inv in investments:
        asset_id = inv.get("asset_id")
        if asset_id:
            key = str(asset_id)
            quantities[key] = quantities.get(key, 0) + safe_float(inv.get("quantity"))
    return {asset_id for asset_id, quantity in quantities.items() if quantity > 0.000001}


def unique_market_asset_targets(investments, open_ids=None):
    if open_ids is None:
        open_ids = open_asset_ids(investments)
    targets = {}
    for inv in investments:
        asset_id = inv.get("asset_id")
        asset_class = inv.get("asset_class")
        ticker = ticker_key(inv.get("ticker_or_name"))
        if not asset_id or not ticker or not is_quoted_asset(asset_class, ticker):
            continue
        if str(asset_id) not in open_ids:
            continue
        targets[asset_id] = {
            "asset_id": asset_id,
            "asset_class": asset_class,
            "ticker": ticker,
            "name": inv.get("ticker_or_name") or ticker,
            "currency": inv.get("native_currency") or inv.get("asset_currency") or "BRL",
        }
    return list(targets.values())


def update_current_prices_for_assets(current_user_id, target_assets, market_result):
    updated_assets = []
    if not target_assets:
        return updated_assets

    prices = market_result.get("prices", {})
    sources = market_result.get("source_by_ticker", {})

    with get_db() as conn:
        for asset in target_assets:
            ticker = asset["ticker"]
            source = sources.get(ticker)
            if source != "market":
                continue
            price = safe_float(prices.get(ticker), None)
            if price is None or not math.isfinite(price) or price < 0:
                continue

            # Centavos pelo ROUND_HALF_UP (money.py), nunca o round() do Python.
            price = rounded_money(price)
            record_price_quote(
                conn,
                current_user_id,
                asset["asset_id"],
                price,
                asset_class=asset["asset_class"],
                source="market",
                metadata={"ticker": ticker, "provider": market_price_provider(ticker)},
            )
            updated_assets.append({
                **asset,
                "price": price,
                "source": "market",
                "status": "updated",
            })

    return updated_assets


def refresh_market_prices(current_user_id, investment_id=None, *, force=False, asset_id=None, asset_class=None, timeout=None):
    """Busca e grava as cotacoes dos ativos cotados com posicao aberta.

    Se o provedor passa de `timeout`, o que chegar depois e gravado do mesmo jeito
    (`write_late`): a proxima leitura da carteira ja mostra a cotacao nova."""
    all_investments = fetch_investments(current_user_id)
    investments_to_update = (
        fetch_investments(current_user_id, investment_id) if investment_id else all_investments
    )
    if asset_id:
        investments_to_update = [
            inv for inv in investments_to_update
            if str(inv.get("asset_id")) == str(asset_id)
        ]
    if asset_class:
        investments_to_update = [
            inv for inv in investments_to_update
            if inv.get("asset_class") == asset_class
        ]

    # A posicao aberta vem de todos os movimentos, nao so dos filtrados.
    target_assets = unique_market_asset_targets(
        investments_to_update, open_asset_ids(all_investments)
    )
    tickers = sorted({asset["ticker"] for asset in target_assets})

    foreign = {asset["ticker"] for asset in target_assets if asset.get("currency", "BRL") != "BRL"}
    def write_late(prices):
        late_result = {"prices": prices, "source_by_ticker": {ticker: "market" for ticker in prices}}
        update_current_prices_for_assets(current_user_id, target_assets, late_result)

    market_result = get_market_prices_with_status(
        tickers, force=force, foreign=foreign, timeout=timeout, on_late=write_late,
    )
    updated_assets = update_current_prices_for_assets(current_user_id, target_assets, market_result)
    failed_tickers = set(market_result.get("failed_tickers", []))
    source_by_ticker = market_result.get("source_by_ticker", {})
    cached_assets = [
        {
            **asset,
            "price": safe_float(market_result.get("prices", {}).get(asset["ticker"]), None),
            "source": source_by_ticker.get(asset["ticker"]),
            "status": "cache",
        }
        for asset in target_assets
        if source_by_ticker.get(asset["ticker"]) in {"cache", "cache_stale"}
    ]
    failed_assets = [
        {
            **asset,
            "status": "failed",
            "error": market_result.get("errors", {}).get(asset["ticker"], "Cotacao nao encontrada"),
        }
        for asset in target_assets
        if asset["ticker"] in failed_tickers
    ]
    return {
        "updated_count": len(updated_assets),
        "updated_assets": updated_assets,
        "cached_assets": cached_assets,
        "failed_assets": failed_assets,
        "target_assets": target_assets,
        "requested_tickers": len(tickers),
        "priced_tickers": len(market_result.get("prices", {})),
        "failed_tickers": sorted(failed_tickers),
        "late": bool(market_result.get("late")),
    }


def asset_total_return(data, net_value, proceeds_net):
    """Rentabilidade com proventos de uma posicao, em %.

    Decisao do dono (2026-09-26): a base e TODO o dinheiro que ja entrou no
    ativo — o custo atual mais o custo das cotas ja vendidas (= a soma das
    compras). So o custo atual superestimaria o retorno de um ativo que ja
    devolveu a maior parte do capital numa venda.

        custo atual = compras - custo (medio) das cotas vendidas
        numerador   = liquido atual - custo atual + proventos recebidos
                      + lucro liquido realizado (depois do IR do mes)
        base        = custo atual + custo das cotas vendidas

    Com o custo medio, o custo atual e o `total_invested` da posicao.
    `profitability_percent` (so preco, sobre `total_invested`) continua como esta.
    """
    contributed = data.get("contributed", 0)
    sold_cost_basis = data.get("sold_cost_basis", 0)
    if contributed <= 0:
        return 0
    current_cost = contributed - sold_cost_basis
    gain = net_value - current_cost + proceeds_net + data.get("realized_net_profit", 0)
    return gain / contributed * 100


def position_proceeds(data, paid_proceeds, claimed_assets):
    """Proventos pagos da posicao: {'net', 'net_12m'} ou zeros.

    Acoes, FIIs etc. agrupam pelo ativo. A renda fixa agrupa por titulo e so
    recebe o que aponta para o ativo do titulo (amortizacao, na pratica); se
    dois titulos abertos dividem o mesmo ativo, o primeiro fica com tudo — para
    nao contar o mesmo provento duas vezes.
    """
    asset_id = data.get("asset_id")
    if not asset_id or asset_id in claimed_assets:
        return {"net": 0.0, "net_12m": 0.0}
    claimed_assets.add(asset_id)
    return paid_proceeds.get(asset_id) or {"net": 0.0, "net_12m": 0.0}


def treasury_entry(data, curve_value):
    """Uma compra do Tesouro para `build_treasury_positions()`."""
    metadata = data.get("metadata") or {}
    purchase = parse_iso_date(metadata.get("purchase_date"))
    return {
        "id": data["id"],
        "asset_id": data.get("asset_id"),
        "ticker": data["original_ticker"],
        "metadata": metadata,
        "purchase_date": purchase.date() if purchase else None,
        "applied": data["total_invested"],
        "original_applied": data["original_invested"],
        "curve_value": curve_value,
        "quote": data.get("quote") or {},
        "contributed": data.get("contributed", 0),
        "sold_cost_basis": data.get("sold_cost_basis", 0),
        "realized_net_profit": data.get("realized_net_profit", 0),
    }


TREASURY_QUOTE_FRESH_DAYS = 4


def treasury_quote(position, entries):
    """A "cotacao" do titulo: o PU do arquivo do Tesouro, ou a da curva (BCB)."""
    if position["valuation"] != "MARKET" or not position.get("price_date"):
        return entries[0].get("quote") or {}
    price_day = parse_iso_date(position["price_date"])
    age_days = (datetime.now() - price_day).days if price_day else None
    status = "fresh" if age_days is not None and age_days <= TREASURY_QUOTE_FRESH_DAYS else "stale"
    return {
        "id": None,
        "source": "tesouro",
        "quoted_at": f"{position['price_date']}T00:00:00Z",
        "metadata": {"provider": "tesouro_transparente", "market_rate": position.get("market_rate")},
        "age_hours": round(age_days * 24, 2) if age_days is not None else None,
        "stale_after_hours": TREASURY_QUOTE_FRESH_DAYS * 24,
        "status": status,
        "is_stale": status != "fresh",
    }


def treasury_position_payload(position, paid_proceeds, claimed_assets):
    """Uma posicao agrupada do Tesouro, no formato das outras de `assets`."""
    entries = position["entries"]
    first = entries[0]
    asset_ids = []
    for entry in entries:
        if entry.get("asset_id") and entry["asset_id"] not in asset_ids:
            asset_ids.append(entry["asset_id"])
    proceeds = {"net": 0.0, "net_12m": 0.0}
    for asset_id in asset_ids:
        found = position_proceeds({"asset_id": asset_id}, paid_proceeds, claimed_assets)
        proceeds["net"] += found["net"]
        proceeds["net_12m"] += found["net_12m"]
    totals = {
        key: sum(entry.get(key, 0) for entry in entries)
        for key in ("contributed", "sold_cost_basis", "realized_net_profit")
    }
    invested = position["invested"]
    gross = position["gross"]
    net = position["net"]
    units = position["units"]

    # A taxa media entra no lugar da taxa da compra: a descricao da linha a mostra.
    metadata = dict(first["metadata"])
    if position["average_rate"] is not None:
        indexer = metadata.get("indexer") or "CDI"
        if metadata.get("rate_type") != "PRE" and indexer == "CDI":
            metadata["cdi_percentage"] = position["average_rate"]
        else:
            metadata["annual_rate"] = position["average_rate"]
    metadata.pop("treasury_units", None)
    metadata["purchase_date"] = first["metadata"].get("purchase_date")

    lots = [lot_payload(lot) for lot in position["lots"]]
    return {
        "id": f"tesouro:{first['id']}" if len(entries) > 1 else str(first["id"]),
        "asset_id": first.get("asset_id"),
        "asset_ids": asset_ids,
        # A posicao materializada de uma compra so continua com o id dela.
        "source_transaction_id": str(first["id"]) if len(entries) == 1 else None,
        "ticker": first["ticker"],
        "name": asset_display_name("FIXED_INCOME", first["ticker"], first["ticker"]),
        "class": "FIXED_INCOME",
        "market_kind": None,
        **category_fields("FIXED_INCOME", first["ticker"], first["metadata"]),
        "quantity": round(units, 6) if units else 1,
        "average_price": rounded_money(invested / units if units else invested),
        "current_price": rounded_money(position["market_pu"] if position["valuation"] == "MARKET" and position["market_pu"] else gross),
        "total_invested": rounded_money(invested),
        "current_value": rounded_money(gross),
        "net_value": rounded_money(net),
        "taxes": rounded_money(max(rounded_money(gross) - rounded_money(net), 0)),
        "is_tax_free": False,
        "profitability_percent": round((net - invested) / invested * 100, 2) if invested > 0 else 0,
        "proceeds_net": rounded_money(proceeds["net"]),
        "proceeds_12m_net": rounded_money(proceeds["net_12m"]),
        "dividend_yield_12m": round(proceeds["net_12m"] / net * 100, 2) if net > 0 else 0,
        "total_return_percent": round(asset_total_return(totals, net, proceeds["net"]), 2),
        "quote": treasury_quote(position, entries),
        "metadata": metadata,
        "currency": "BRL",
        "native_current_price": None,
        "fx_rate_today": None,
        "lots": lots,
        "treasury": {
            "title_type": position["title_type"],
            "maturity_date": position["maturity_date"],
            "units": round(units, 6) if units is not None else None,
            "average_rate": position["average_rate"],
            "market_pu": rounded_money(position["market_pu"]) if position["market_pu"] else None,
            "market_rate": position["market_rate"],
            "price_date": position["price_date"],
            "valuation": position["valuation"],
            "custody": rounded_money(position["custody"]),
            "iof": rounded_money(position["iof"]),
            "income_tax": rounded_money(position["income_tax"]),
            "lot_count": len(lots),
        },
    }


def build_portfolio_snapshot(current_user_id):
    all_investments = fetch_investments(current_user_id)
    with get_db() as conn:
        paid_proceeds = paid_proceeds_by_asset(conn, current_user_id)

    grouped_assets = {}
    for asset in all_investments:
        metadata = asset.get("metadata") or {}
        asset_id = asset.get("asset_id")
        ticker = asset["ticker_or_name"]
        normalized_ticker = ticker_key(ticker)
        asset_class = asset["asset_class"]
        qty = safe_float(asset.get("quantity"))
        avg_price_buy = safe_float(asset.get("average_price"))
        curr_price = safe_float(asset.get("current_price"), avg_price_buy)
        quote_info = quote_info_from_investment(asset)
        # Custo medio (apply_average_cost): numa venda, - quantidade x custo medio.
        invested_value = safe_float(asset.get("cost_amount"), qty * avg_price_buy)

        if movement_affects_fixed_income_position(asset):
            group_key = str(metadata.get("related_id"))
            source_transaction_id = str(metadata.get("related_id"))
        elif asset_class == "FIXED_INCOME" and metadata.get("is_redemption"):
            continue
        else:
            group_key = str(asset["id"]) if asset_class == "FIXED_INCOME" else str(asset_id or f"{asset_class}:{normalized_ticker}")
            source_transaction_id = str(asset["id"]) if asset_class == "FIXED_INCOME" else None

        if group_key not in grouped_assets:
            grouped_assets[group_key] = {
                "id": group_key,
                "asset_id": asset_id,
                "source_transaction_id": source_transaction_id,
                "original_ticker": normalized_ticker or ticker,
                "class": asset_class,
                "total_quantity": 0,
                "total_invested": 0,
                "original_invested": 0,
                "current_price": curr_price,
                "quote": quote_info,
                "metadata": metadata,
                # Ativo em moeda estrangeira: valores acima ja em reais; a
                # cotacao na moeda dele so para exibir.
                "currency": asset.get("native_currency") or "BRL",
                "native_current_price": asset.get("native_current_price"),
                "fx_rate_today": asset.get("fx_rate_today"),
                # Para a rentabilidade com proventos (asset_total_return).
                "contributed": 0,
                "sold_cost_basis": 0,
                "realized_net_profit": 0,
            }

        grouped_assets[group_key]["total_invested"] += invested_value
        if qty > 0:
            grouped_assets[group_key]["contributed"] += invested_value
        # Venda/resgate: o resultado realizado (custo medio, em reais) vem na linha.
        grouped_assets[group_key]["sold_cost_basis"] += safe_float(asset.get("realized_cost_basis"))
        grouped_assets[group_key]["realized_net_profit"] += safe_float(asset.get("realized_net_profit_after_tax"))

        if not movement_affects_fixed_income_position(asset):
            grouped_assets[group_key]["total_quantity"] += qty
            if asset_class == "FIXED_INCOME" and qty > 0:
                grouped_assets[group_key]["original_invested"] += invested_value
                grouped_assets[group_key]["metadata"] = metadata
                grouped_assets[group_key]["original_ticker"] = normalized_ticker or ticker
                grouped_assets[group_key]["asset_id"] = asset_id
                grouped_assets[group_key]["source_transaction_id"] = str(asset["id"])
                grouped_assets[group_key]["quote"] = quote_info
            if asset.get("current_price") is not None:
                grouped_assets[group_key]["current_price"] = curr_price
                grouped_assets[group_key]["quote"] = quote_info
                grouped_assets[group_key]["native_current_price"] = asset.get("native_current_price")

    processed_assets = []
    total_invested_all = 0
    current_total_value = 0
    current_net_value_all = 0
    distribution = {}
    claimed_proceeds_assets = set()
    treasury_entries = []

    for data in grouped_assets.values():
        if data["total_quantity"] <= 0:
            continue
        # Renda fixa toda resgatada continua com quantidade 1 e aplicado 0: encerrada.
        if data["class"] == "FIXED_INCOME" and fixed_income_title_closed(data["total_invested"]):
            continue

        avg_price_calculated = (
            data["total_invested"] / data["total_quantity"]
            if data["total_quantity"] > 0 else 0
        )

        current_value = position_value_today(
            data["class"],
            data["total_quantity"],
            data["total_invested"],
            data["original_invested"],
            data["current_price"],
            data.get("metadata"),
        )

        # Tesouro Direto: agrupado por titulo e marcado a mercado depois do laco.
        if data["class"] == "FIXED_INCOME" and is_treasury_title(data["class"], data["original_ticker"], data.get("metadata")):
            treasury_entries.append(treasury_entry(data, current_value))
            continue

        net_value = fixed_income_net_value(
            data["class"],
            data.get("metadata") or {},
            data["total_invested"],
            current_value,
            datetime.now(),
        )
        is_tax_free = fixed_income_is_tax_free(data.get("metadata"))
        profitability = (
            ((net_value - data["total_invested"]) / data["total_invested"]) * 100
            if data["total_invested"] > 0 else 0
        )

        total_invested_all += data["total_invested"]
        current_total_value += current_value
        current_net_value_all += net_value
        distribution[data["class"]] = distribution.get(data["class"], 0) + net_value

        display_price = current_value if data["class"] == "FIXED_INCOME" else data["current_price"]
        proceeds = position_proceeds(data, paid_proceeds, claimed_proceeds_assets)
        total_return = asset_total_return(data, net_value, proceeds["net"])

        processed_assets.append({
            "id": data["id"],
            "asset_id": data.get("asset_id"),
            "source_transaction_id": data.get("source_transaction_id"),
            "ticker": data["original_ticker"],
            "name": asset_display_name(data["class"], data["original_ticker"], data["original_ticker"]),
            "class": data["class"],
            "market_kind": asset_market_kind(data["class"], data["original_ticker"]),
            # ETF, Tesouro Direto, indexador da renda fixa (services/asset_categories.py).
            **category_fields(data["class"], data["original_ticker"], data.get("metadata")),
            "quantity": round(data["total_quantity"], 8),
            "average_price": rounded_money(avg_price_calculated),
            "current_price": rounded_money(display_price),
            "total_invested": rounded_money(data["total_invested"]),
            "current_value": rounded_money(current_value),
            "net_value": rounded_money(net_value),
            # Do bruto e do liquido ja arredondados: bruto - IR = liquido no centavo.
            "taxes": rounded_money(max(rounded_money(current_value) - rounded_money(net_value), 0)),
            "is_tax_free": is_tax_free,
            "profitability_percent": round(profitability, 2),
            "proceeds_net": rounded_money(proceeds["net"]),
            "proceeds_12m_net": rounded_money(proceeds["net_12m"]),
            "dividend_yield_12m": round(proceeds["net_12m"] / net_value * 100, 2) if net_value > 0 else 0,
            "total_return_percent": round(total_return, 2),
            "quote": data.get("quote") or {},
            "metadata": data.get("metadata") or {},
            "currency": data.get("currency") or "BRL",
            "native_current_price": (
                rounded_money(data["native_current_price"])
                if data.get("currency", "BRL") != "BRL" and data.get("native_current_price") is not None
                else None
            ),
            "fx_rate_today": data.get("fx_rate_today") if data.get("currency", "BRL") != "BRL" else None,
        })

    for position in build_treasury_positions(treasury_entries):
        asset = treasury_position_payload(position, paid_proceeds, claimed_proceeds_assets)
        total_invested_all += position["invested"]
        current_total_value += position["gross"]
        current_net_value_all += position["net"]
        distribution["FIXED_INCOME"] = distribution.get("FIXED_INCOME", 0) + position["net"]
        processed_assets.append(asset)

    for key, value in distribution.items():
        distribution[key] = round((value / current_net_value_all) * 100, 2) if current_net_value_all > 0 else 0

    return {
        "total_invested": rounded_money(total_invested_all),
        "current_balance": rounded_money(current_total_value),
        "current_net_balance": rounded_money(current_net_value_all),
        "portfolio_profitability": round(
            ((current_net_value_all - total_invested_all) / total_invested_all * 100),
            2,
        ) if total_invested_all > 0 else 0,
        "gross_portfolio_profitability": round(
            ((current_total_value - total_invested_all) / total_invested_all * 100),
            2,
        ) if total_invested_all > 0 else 0,
        "distribution": distribution,
        "assets": processed_assets,
    }


def replace_materialized_positions(current_user_id, assets):
    with get_db() as conn:
        conn.execute("DELETE FROM investment_positions WHERE user_id = ?", (current_user_id,))
        for asset in assets:
            asset_id = asset.get("asset_id")
            if not asset_id:
                continue

            source_transaction_id = asset.get("source_transaction_id") or None
            position_id = f"position:{source_transaction_id or asset_id}"
            conn.execute(
                """
                INSERT INTO investment_positions
                (
                    id, user_id, asset_id, source_transaction_id, quantity,
                    invested_amount, average_price, current_price, current_value,
                    net_value, taxes, profitability_percent, metadata, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                """,
                (
                    position_id,
                    current_user_id,
                    asset_id,
                    source_transaction_id,
                    safe_float(asset.get("quantity")),
                    safe_float(asset.get("total_invested")),
                    safe_float(asset.get("average_price")),
                    safe_float(asset.get("current_price")),
                    safe_float(asset.get("current_value")),
                    safe_float(asset.get("net_value")),
                    safe_float(asset.get("taxes")),
                    safe_float(asset.get("profitability_percent")),
                    encode_metadata(asset.get("metadata") or {}),
                ),
            )


def refresh_materialized_positions(current_user_id):
    try:
        portfolio = build_portfolio_snapshot(current_user_id)
        replace_materialized_positions(current_user_id, portfolio["assets"])
    except Exception as exc:
        logger.warning(f"Nao foi possivel atualizar posicoes materializadas: {exc}")
