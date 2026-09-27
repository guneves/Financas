"""Resultado realizado: custo FIFO, aliquotas e o imposto estimado.

`build_realized_results()` reconstroi, a partir das movimentacoes, o resultado
de cada venda (lotes FIFO, `build_variable_realized_result()`) e de cada
resgate de renda fixa (tabela regressiva pelos dias aplicados,
`build_fixed_income_realized_result()`). `refresh_realized_results()` regrava
a tabela `investment_realized_results` inteira do usuario — ela e derivada,
nunca editada a mao.
"""

import math

from dates import parse_iso_date
from db import encode_metadata, get_db, row_to_dict
from money import rounded_money
from services.fixed_income import fixed_income_is_tax_free
from services.investments import (
    fetch_investments,
    investment_fee_amount,
    investment_gross_proceeds,
    investment_movement_type,
    investment_operation_date,
    movement_sort_key,
)
from validators import safe_float


DEFAULT_REALIZED_TAX_RATES = {
    "STOCKS": 0.15,
    "REIT": 0.20,
    "OTHER": 0.15,
    "FIXED_INCOME": 0.15,
}


def normalized_tax_rate(value):
    rate = safe_float(value, None)
    if rate is None or not math.isfinite(rate) or rate < 0:
        return None
    if rate > 1:
        return rate / 100
    return rate


def fixed_income_tax_rate_for_days(days_invested):
    days = max(int(days_invested or 0), 0)
    if days <= 180:
        return 0.225
    if days <= 360:
        return 0.200
    if days <= 720:
        return 0.175
    return 0.150


def realized_tax_rate(asset_class, metadata=None, holding_days=None):
    metadata = metadata or {}
    explicit_rate = normalized_tax_rate(
        metadata.get("tax_rate", metadata.get("tax_rate_percent"))
    )
    if explicit_rate is not None:
        return explicit_rate

    if asset_class == "FIXED_INCOME":
        if fixed_income_is_tax_free(metadata):
            return 0
        if holding_days is not None:
            return fixed_income_tax_rate_for_days(holding_days)

    return DEFAULT_REALIZED_TAX_RATES.get(asset_class, 0)


def days_between_dates(start_date, end_date):
    start = parse_iso_date(start_date)
    end = parse_iso_date(end_date)
    if not start or not end:
        return None
    return max((end - start).days, 0)


def realized_result_record(investment, *, quantity, gross_proceeds, fees, cost_basis, tax_amount, tax_rate, metadata):
    quantity = abs(safe_float(quantity))
    gross_proceeds = max(safe_float(gross_proceeds), 0)
    fees = max(safe_float(fees), 0)
    net_proceeds = max(gross_proceeds - fees, 0)
    cost_basis = max(safe_float(cost_basis), 0)
    realized_profit = net_proceeds - cost_basis
    average_cost = cost_basis / quantity if quantity > 0 else 0
    net_unit_price = net_proceeds / quantity if quantity > 0 else 0
    profitability = (realized_profit / cost_basis * 100) if cost_basis > 0 else 0
    tax_amount = max(safe_float(tax_amount), 0)

    return {
        "id": f"realized:{investment['id']}",
        "user_id": investment["user_id"],
        "asset_id": investment["asset_id"],
        "source_transaction_id": investment["id"],
        "movement_type": investment.get("movement_type") or investment_movement_type(
            investment.get("quantity"),
            investment.get("metadata") or {},
        ),
        "quantity": round(quantity, 6),
        "average_cost": rounded_money(average_cost),
        "gross_proceeds": rounded_money(gross_proceeds),
        "fee_amount": rounded_money(fees),
        "net_proceeds": rounded_money(net_proceeds),
        "net_unit_price": rounded_money(net_unit_price),
        "cost_basis": rounded_money(cost_basis),
        "realized_profit": rounded_money(realized_profit),
        "profitability_percent": round(profitability, 2),
        "tax_rate": round(safe_float(tax_rate), 6),
        "tax_amount": rounded_money(tax_amount),
        "net_profit_after_tax": rounded_money(realized_profit - tax_amount),
        "operation_date": investment_operation_date(investment),
        "metadata": metadata,
    }


def allocation_tax_amount(asset_class, movement_metadata, allocation, profit):
    rate = realized_tax_rate(
        asset_class,
        movement_metadata,
        allocation.get("holding_days"),
    )
    return max(profit, 0) * rate, rate


def build_variable_realized_result(investment, lots):
    metadata = investment.get("metadata") or {}
    asset_class = investment.get("asset_class")
    operation_date = investment_operation_date(investment)
    sold_quantity = abs(safe_float(investment.get("quantity")))
    fees = max(safe_float(investment.get("fee_amount"), investment_fee_amount(metadata)), 0)
    gross_proceeds = investment_gross_proceeds(investment, metadata)
    gross_unit_price = gross_proceeds / sold_quantity if sold_quantity > 0 else 0

    remaining = sold_quantity
    allocations = []
    cost_basis = 0
    index = 0

    while remaining > 0.000001 and index < len(lots):
        lot = lots[index]
        lot_quantity = safe_float(lot.get("remaining_quantity"))
        if lot_quantity <= 0.000001:
            lots.pop(index)
            continue

        consumed_quantity = min(remaining, lot_quantity)
        allocation_cost = consumed_quantity * safe_float(lot.get("unit_cost"))
        holding_days = days_between_dates(lot.get("purchase_date"), operation_date)
        allocations.append({
            "buy_transaction_id": lot.get("transaction_id"),
            "purchase_date": lot.get("purchase_date"),
            "quantity": round(consumed_quantity, 6),
            "unit_cost": rounded_money(lot.get("unit_cost")),
            "cost_basis": rounded_money(allocation_cost),
            "holding_days": holding_days,
        })
        cost_basis += allocation_cost
        lot["remaining_quantity"] = lot_quantity - consumed_quantity
        remaining -= consumed_quantity

        if lot["remaining_quantity"] <= 0.000001:
            lots.pop(index)
        else:
            index += 1

    if remaining > 0.000001:
        fallback_unit_cost = safe_float(investment.get("average_price"))
        fallback_cost = remaining * fallback_unit_cost
        allocations.append({
            "buy_transaction_id": None,
            "purchase_date": None,
            "quantity": round(remaining, 6),
            "unit_cost": rounded_money(fallback_unit_cost),
            "cost_basis": rounded_money(fallback_cost),
            "holding_days": None,
            "unmatched": True,
        })
        cost_basis += fallback_cost

    tax_amount = 0
    taxable_profit = 0
    for allocation in allocations:
        allocation_quantity = safe_float(allocation.get("quantity"))
        fee_share = fees * (allocation_quantity / sold_quantity) if sold_quantity > 0 else 0
        allocation_gross = allocation_quantity * gross_unit_price
        allocation_net = max(allocation_gross - fee_share, 0)
        allocation_profit = allocation_net - safe_float(allocation.get("cost_basis"))
        allocation_tax, allocation_rate = allocation_tax_amount(
            asset_class,
            metadata,
            allocation,
            allocation_profit,
        )
        tax_amount += allocation_tax
        taxable_profit += max(allocation_profit, 0)
        allocation["gross_proceeds"] = rounded_money(allocation_gross)
        allocation["fee_amount"] = rounded_money(fee_share)
        allocation["net_proceeds"] = rounded_money(allocation_net)
        allocation["realized_profit"] = rounded_money(allocation_profit)
        allocation["tax_rate"] = round(allocation_rate, 6)
        allocation["tax_amount"] = rounded_money(allocation_tax)

    effective_tax_rate = tax_amount / taxable_profit if taxable_profit > 0 else realized_tax_rate(asset_class, metadata)
    return realized_result_record(
        investment,
        quantity=sold_quantity,
        gross_proceeds=gross_proceeds,
        fees=fees,
        cost_basis=cost_basis,
        tax_amount=tax_amount,
        tax_rate=effective_tax_rate,
        metadata={
            "cost_method": "FIFO",
            "tax_method": "estimativa_simples",
            "tax_note": "Estimativa operacional. Valide regras fiscais e isencoes antes da declaracao oficial.",
            "gross_unit_price": rounded_money(gross_unit_price),
            "unmatched_quantity": round(max(remaining, 0), 6),
            "allocations": allocations,
        },
    )


def build_fixed_income_realized_result(investment, investments_by_id):
    metadata = investment.get("metadata") or {}
    operation_date = investment_operation_date(investment)
    quantity = abs(safe_float(investment.get("quantity"), 1)) or 1
    fees = max(safe_float(investment.get("fee_amount"), investment_fee_amount(metadata)), 0)
    gross_proceeds = investment_gross_proceeds(investment, metadata)
    cost_basis = abs(safe_float(investment.get("quantity")) * safe_float(investment.get("average_price")))
    related_id = metadata.get("related_id")
    related_purchase = investments_by_id.get(str(related_id)) if related_id else None
    purchase_metadata = (related_purchase or {}).get("metadata") or {}
    purchase_date = investment_operation_date(related_purchase) if related_purchase else None
    holding_days = days_between_dates(purchase_date, operation_date)
    tax_metadata = {**purchase_metadata, **metadata}
    profit = max(gross_proceeds - fees, 0) - cost_basis
    tax_rate = realized_tax_rate("FIXED_INCOME", tax_metadata, holding_days)
    tax_amount = max(profit, 0) * tax_rate

    allocation = {
        "buy_transaction_id": related_id,
        "purchase_date": purchase_date,
        "quantity": round(quantity, 6),
        "unit_cost": rounded_money(cost_basis / quantity if quantity > 0 else cost_basis),
        "cost_basis": rounded_money(cost_basis),
        "holding_days": holding_days,
        "gross_proceeds": rounded_money(gross_proceeds),
        "fee_amount": rounded_money(fees),
        "net_proceeds": rounded_money(max(gross_proceeds - fees, 0)),
        "realized_profit": rounded_money(profit),
        "tax_rate": round(tax_rate, 6),
        "tax_amount": rounded_money(tax_amount),
    }

    return realized_result_record(
        investment,
        quantity=quantity,
        gross_proceeds=gross_proceeds,
        fees=fees,
        cost_basis=cost_basis,
        tax_amount=tax_amount,
        tax_rate=tax_rate,
        metadata={
            "cost_method": "LOT_REDEMPTION",
            "tax_method": "estimativa_simples",
            "tax_note": "Estimativa operacional. Valide regras fiscais e isencoes antes da declaracao oficial.",
            "gross_unit_price": rounded_money(gross_proceeds / quantity if quantity > 0 else gross_proceeds),
            "allocations": [allocation],
        },
    )


def build_realized_results(current_user_id):
    investments = sorted(fetch_investments(current_user_id), key=movement_sort_key)
    investments_by_id = {str(item.get("id")): item for item in investments}
    lots_by_asset = {}
    results = []

    for investment in investments:
        asset_id = investment.get("asset_id")
        if not asset_id:
            continue

        metadata = investment.get("metadata") or {}
        movement_type = investment.get("movement_type") or investment_movement_type(
            investment.get("quantity"),
            metadata,
        )
        quantity = safe_float(investment.get("quantity"))
        asset_lots = lots_by_asset.setdefault(asset_id, [])

        if movement_type == "BUY" and quantity > 0:
            asset_lots.append({
                "transaction_id": investment.get("id"),
                "purchase_date": investment_operation_date(investment),
                "remaining_quantity": quantity,
                "unit_cost": safe_float(investment.get("average_price")),
                "metadata": metadata,
            })
            continue

        if movement_type == "SELL" and quantity < 0:
            results.append(build_variable_realized_result(investment, asset_lots))
            continue

        if movement_type == "REDEMPTION":
            results.append(build_fixed_income_realized_result(investment, investments_by_id))

    return results


def replace_realized_results(current_user_id, results):
    with get_db() as conn:
        conn.execute("DELETE FROM investment_realized_results WHERE user_id = ?", (current_user_id,))
        for item in results:
            conn.execute(
                """
                INSERT INTO investment_realized_results
                (
                    id, user_id, asset_id, source_transaction_id, movement_type,
                    quantity, average_cost, gross_proceeds, fee_amount,
                    net_proceeds, net_unit_price, cost_basis, realized_profit,
                    profitability_percent, tax_rate, tax_amount, net_profit_after_tax,
                    operation_date, metadata, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                """,
                (
                    item["id"],
                    item["user_id"],
                    item["asset_id"],
                    item["source_transaction_id"],
                    item["movement_type"],
                    item["quantity"],
                    item["average_cost"],
                    item["gross_proceeds"],
                    item["fee_amount"],
                    item["net_proceeds"],
                    item["net_unit_price"],
                    item["cost_basis"],
                    item["realized_profit"],
                    item["profitability_percent"],
                    item["tax_rate"],
                    item["tax_amount"],
                    item["net_profit_after_tax"],
                    item["operation_date"],
                    encode_metadata(item.get("metadata")),
                ),
            )


def refresh_realized_results(current_user_id):
    results = build_realized_results(current_user_id)
    replace_realized_results(current_user_id, results)
    return results


def realized_results_summary(current_user_id):
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS operation_count,
                COALESCE(SUM(gross_proceeds), 0) AS gross_proceeds,
                COALESCE(SUM(fee_amount), 0) AS fee_amount,
                COALESCE(SUM(net_proceeds), 0) AS net_proceeds,
                COALESCE(SUM(cost_basis), 0) AS cost_basis,
                COALESCE(SUM(realized_profit), 0) AS realized_profit,
                COALESCE(SUM(tax_amount), 0) AS tax_amount,
                COALESCE(SUM(net_profit_after_tax), 0) AS net_profit_after_tax
            FROM investment_realized_results
            WHERE user_id = ?
            """,
            (current_user_id,),
        ).fetchone()

    summary = row_to_dict(row) or {}
    return {
        "operation_count": int(summary.get("operation_count") or 0),
        "gross_proceeds": rounded_money(summary.get("gross_proceeds")),
        "fee_amount": rounded_money(summary.get("fee_amount")),
        "net_proceeds": rounded_money(summary.get("net_proceeds")),
        "cost_basis": rounded_money(summary.get("cost_basis")),
        "realized_profit": rounded_money(summary.get("realized_profit")),
        "tax_amount": rounded_money(summary.get("tax_amount")),
        "net_profit_after_tax": rounded_money(summary.get("net_profit_after_tax")),
    }
