"""Carteira: posicoes, atualizacao de cotacoes e a evolucao mensal.

`build_portfolio_snapshot()` agrega as movimentacoes em uma posicao por ativo;
`refresh_materialized_positions()` regrava `investment_positions` a partir
dele (tabela derivada). `refresh_market_prices()` busca cotacao so para os
ativos cotados com posicao aberta (`unique_market_asset_targets()`).
`build_portfolio_evolution()` monta a serie de "Evolucao do Patrimonio".
"""

from datetime import datetime
import math

from asset_classes import QUOTED_ASSET_CLASSES
from dates import month_end, month_key, month_label, parse_iso_date, subtract_months
from db import encode_metadata, get_db
from money import rounded_money
from services.fixed_income import (
    accrual_factor_until,
    fixed_income_net_value,
    movement_affects_fixed_income_position,
)
from services.investments import fetch_investments
from services.prices import (
    get_market_prices_with_status,
    market_price_provider,
    quote_info_from_investment,
    record_price_quote,
    ticker_key,
)
from validators import safe_float
from applog import get_logger

logger = get_logger(__name__)


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


def current_price_from_position(data, default=0):
    price = safe_float(data.get("current_price"), default)
    if data.get("class") == "FIXED_INCOME" and data.get("original_invested", 0) > 0:
        factor = price / data["original_invested"]
        price = data["total_invested"] * factor
    return max(price, 0)


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


def portfolio_month_positions(investments_data, historical_prices, month_start, index_series, current_month_key):
    """Cada posicao no fim do mes: {group_key: {ticker, class, applied, gross, net}}.

    `gross` e o valor de mercado; `net` desconta o IR estimado da renda fixa.
    So entram as posicoes com quantidade e valor aplicado positivos.
    """
    target_key = month_key(month_start)
    target_end = month_end(month_start)
    positions = {}

    for investment in investments_data:
        metadata = investment.get("metadata") or {}
        if investment_movement_date(investment) > target_end:
            continue

        group_key = evolution_group_key(investment)
        if group_key is None:
            continue
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
        position["applied"] += quantity * average_price
        if not movement_affects_fixed_income_position(investment):
            position["quantity"] += quantity
            if asset_class == "FIXED_INCOME" and quantity > 0:
                position["original_applied"] += quantity * average_price
                position["metadata"] = metadata
                position["ticker"] = ticker
                position["purchase_date"] = investment_movement_date(investment)
                position["quote_source"] = investment.get("current_quote_source")
        if investment.get("current_price") is not None and not movement_affects_fixed_income_position(investment):
            position["current_price"] = safe_float(investment.get("current_price"), average_price)

    valued = {}
    for group_key, position in positions.items():
        quantity = position["quantity"]
        applied_value = position["applied"]
        if quantity <= 0 or applied_value <= 0:
            continue

        adjusted_quantity = quantity
        if position["class"] == "CATTLE":
            mortality_rate = safe_float(position["metadata"].get("mortality_rate"))
            adjusted_quantity = quantity * (1 - mortality_rate)

        if position["class"] in QUOTED_ASSET_CLASSES:
            price = historical_price_for_month(
                historical_prices,
                position["ticker"],
                target_key,
            )
            if price is None:
                price = safe_float(position.get("current_price"), applied_value / quantity)
            market_value = adjusted_quantity * price
        elif (
            position["class"] == "FIXED_INCOME" and target_key == current_month_key
            and (position.get("quote_source") == "cdi" or not index_series)
        ):
            original_applied = position.get("original_applied", applied_value)
            if original_applied > 0:
                factor = safe_float(position.get("current_price"), original_applied) / original_applied
                market_value = applied_value * factor
            else:
                market_value = applied_value
        elif position["class"] == "FIXED_INCOME" and index_series and position.get("purchase_date"):
            # Mes passado (ou o atual, se o titulo ainda nao tem cotacao do
            # BCB): corrigido pela serie ate o fim do mes, ou ate hoje.
            purchase = parse_iso_date(position["purchase_date"])
            until = min(target_end, datetime.now())
            factor = accrual_factor_until(position["metadata"], purchase, until, index_series) if purchase else None
            market_value = applied_value * factor if factor else applied_value
        elif target_key == current_month_key:
            market_value = adjusted_quantity * safe_float(
                position.get("current_price"),
                applied_value / quantity,
            )
        else:
            market_value = applied_value

        net_value = fixed_income_net_value(
            position["class"],
            position["metadata"],
            applied_value,
            market_value,
            target_end,
        )
        valued[group_key] = {
            "ticker": position["ticker"],
            "class": position["class"],
            "applied": applied_value,
            "gross": market_value,
            "net": net_value,
        }

    return valued


def iter_portfolio_months(investments_data, historical_prices, months_back, index_series=None):
    """(inicio do mes, posicoes no fim do mes) dos ultimos `months_back` meses.

    E o laco da evolucao; a rentabilidade (services/returns.py) le as posicoes
    uma a uma daqui, para as duas sairem da mesma avaliacao."""
    current_month_key = month_key(datetime.now())
    for month_start in portfolio_evolution_months(months_back):
        yield month_start, portfolio_month_positions(
            investments_data, historical_prices, month_start, index_series, current_month_key,
        )


def build_portfolio_evolution(investments_data, historical_prices, months_back, index_series=None):
    """Patrimonio mes a mes. `index_series` (CDI/IPCA, de fixed_income.index_history)
    corrige a renda fixa nos meses passados; sem ele, eles ficam no custo."""
    evolution = []

    for month_start, positions in iter_portfolio_months(
        investments_data, historical_prices, months_back, index_series,
    ):
        applied_total = 0
        net_total = 0
        for position in positions.values():
            applied_total += position["applied"]
            net_total += position["net"]

        gain = net_total - applied_total
        evolution.append({
            "month": month_label(month_start),
            "month_key": month_key(month_start),
            "patrimonio": rounded_money(max(net_total, 0)),
            "valorAplicado": rounded_money(max(applied_total, 0)),
            "ganhoCapital": rounded_money(max(gain, 0)),
            "ganhoCapitalReal": rounded_money(gain),
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
        if not asset_id or asset_class not in QUOTED_ASSET_CLASSES or not ticker:
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

            record_price_quote(
                conn,
                current_user_id,
                asset["asset_id"],
                round(price, 2),
                asset_class=asset["asset_class"],
                source="market",
                metadata={"ticker": ticker, "provider": market_price_provider(ticker)},
            )
            updated_assets.append({
                **asset,
                "price": round(price, 2),
                "source": "market",
                "status": "updated",
            })

    return updated_assets


def refresh_market_prices(current_user_id, investment_id=None, *, force=False, asset_id=None, asset_class=None):
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
    market_result = get_market_prices_with_status(tickers, force=force, foreign=foreign)
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
    }


def build_portfolio_snapshot(current_user_id):
    all_investments = fetch_investments(current_user_id)

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
        invested_value = qty * avg_price_buy

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
            }

        grouped_assets[group_key]["total_invested"] += invested_value

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

    for data in grouped_assets.values():
        if data["total_quantity"] <= 0:
            continue

        avg_price_calculated = (
            data["total_invested"] / data["total_quantity"]
            if data["total_quantity"] > 0 else 0
        )

        adjusted_quantity = data["total_quantity"]
        if data["class"] == "CATTLE" and data.get("metadata"):
            mortality_rate = safe_float(data["metadata"].get("mortality_rate"))
            adjusted_quantity = data["total_quantity"] * (1 - mortality_rate)

        if data["class"] == "FIXED_INCOME":
            current_value = current_price_from_position(data, data["total_invested"])
        else:
            current_value = adjusted_quantity * data["current_price"]

        net_value = fixed_income_net_value(
            data["class"],
            data.get("metadata") or {},
            data["total_invested"],
            current_value,
            datetime.now(),
        )
        taxes = max(current_value - net_value, 0)
        is_tax_free = bool((data.get("metadata") or {}).get("is_tax_free", False))
        profitability = (
            ((net_value - data["total_invested"]) / data["total_invested"]) * 100
            if data["total_invested"] > 0 else 0
        )

        total_invested_all += data["total_invested"]
        current_total_value += current_value
        current_net_value_all += net_value
        distribution[data["class"]] = distribution.get(data["class"], 0) + net_value

        display_price = current_value if data["class"] == "FIXED_INCOME" else data["current_price"]

        processed_assets.append({
            "id": data["id"],
            "asset_id": data.get("asset_id"),
            "source_transaction_id": data.get("source_transaction_id"),
            "ticker": data["original_ticker"],
            "name": data["original_ticker"],
            "class": data["class"],
            "quantity": round(data["total_quantity"], 4),
            "average_price": rounded_money(avg_price_calculated),
            "current_price": rounded_money(display_price),
            "total_invested": rounded_money(data["total_invested"]),
            "current_value": rounded_money(current_value),
            "net_value": rounded_money(net_value),
            # Do bruto e do liquido ja arredondados: bruto - IR = liquido no centavo.
            "taxes": rounded_money(max(rounded_money(current_value) - rounded_money(net_value), 0)),
            "is_tax_free": is_tax_free,
            "profitability_percent": round(profitability, 2),
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
