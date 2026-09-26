"""Relatorio anual de IR (Fase 6): o que a carteira diz para a declaracao.

Ferramenta de apoio, nao fonte da verdade (decisao 5, 2026-09-23): tudo sai
do que foi lancado no app, com as regras simplificadas abaixo, e precisa ser
conferido com as notas de corretagem e os informes de rendimentos.

Secoes:

- bens_e_direitos: posicao a custo em 31/12 do ano e do ano anterior (FIFO
  sobre o fluxo em reais de fetch_investments), com grupo/codigo sugeridos;
- renda_variavel: mes a mes, acoes (isencao de vendas ate R$ 20 mil no mes,
  15%) e FII (20%, sem isencao), cada um com o proprio saldo de prejuizo,
  carregado dos anos anteriores; DARF abaixo de R$ 10 acumula para o mes
  seguinte. Day trade nao e separado (o app nao guarda hora da operacao);
- exterior: ativos em moeda estrangeira, apuracao anual a 15% (Lei
  14.754/2023), prejuizo carregado para o ano seguinte;
- rendimentos_isentos e tributacao_exclusiva: proventos e resgates de renda
  fixa do ano;
- ganho_de_capital: venda de gado e "outros" em reais, para o GCAP.
"""

from collections import defaultdict
from datetime import datetime

from db import get_db
from money import rounded_money
from services.fx import BASE_CURRENCY, normalize_currency
from services.realized_results import refresh_realized_results
from services.investments import (
    fetch_investments,
    investment_movement_type,
    investment_operation_date,
    movement_sort_key,
)
from validators import safe_float

STOCK_EXEMPTION_LIMIT = 20000.0
STOCK_RATE = 0.15
REIT_RATE = 0.20
FOREIGN_RATE = 0.15
DARF_MINIMUM = 10.0
TAX_FREE_FIXED_INCOME = {"LCI", "LCA", "CRI", "CRA"}

DISCLAIMER = (
    "Apoio para a declaração, calculado só com o que foi lançado no app. Confira com as notas de "
    "corretagem e os informes de rendimentos antes de declarar. Day trade não é separado."
)


def br_money(value):
    """1234.5 -> "1.234,50" (texto da discriminacao, que vai colado no programa)."""
    return f"{rounded_money(value):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def bens_code(asset_class, currency, metadata):
    """(grupo, codigo, rotulo) sugeridos para Bens e Direitos."""
    if asset_class == "STOCKS":
        suffix = " (exterior)" if currency != BASE_CURRENCY else ""
        return "03", "01", f"Ações{suffix}"
    if asset_class == "REIT":
        return "07", "03", "Fundos imobiliários (FII)"
    if asset_class == "FIXED_INCOME":
        if (metadata or {}).get("is_tax_free") or (metadata or {}).get("fixed_income_type") in TAX_FREE_FIXED_INCOME:
            return "04", "03", "Títulos isentos (LCI, LCA, CRI, CRA)"
        return "04", "02", "Títulos sujeitos à tributação (CDB, Tesouro, debêntures...)"
    return "99", "99", "Outros bens e direitos"


def holdings_at(investments, cutoff):
    """Posicao a custo em `cutoff` (AAAA-MM-DD), por ativo (renda fixa: por titulo)."""
    lots = defaultdict(list)
    fixed = {}
    info = {}
    for inv in sorted(investments, key=movement_sort_key):
        if investment_operation_date(inv) > cutoff:
            continue
        metadata = inv.get("metadata") or {}
        asset_class = inv.get("asset_class")
        quantity = safe_float(inv.get("quantity"))
        unit_cost = safe_float(inv.get("average_price"))
        movement_type = investment_movement_type(quantity, metadata)

        if asset_class == "FIXED_INCOME":
            if movement_type == "REDEMPTION" or quantity < 0:
                key = str(metadata.get("related_id") or inv.get("id"))
                if key in fixed:
                    fixed[key]["cost"] -= abs(quantity * unit_cost)
                continue
            key = str(inv.get("id"))
            fixed[key] = {"cost": quantity * unit_cost, "quantity": quantity}
            info[key] = inv
            continue

        key = str(inv.get("asset_id"))
        info.setdefault(key, inv)
        if quantity > 0:
            lots[key].append([quantity, unit_cost])
            continue
        remaining = abs(quantity)
        queue = lots[key]
        while remaining > 0.000001 and queue:
            take = min(remaining, queue[0][0])
            queue[0][0] -= take
            remaining -= take
            if queue[0][0] <= 0.000001:
                queue.pop(0)

    result = {}
    for key, queue in lots.items():
        quantity = sum(lot[0] for lot in queue)
        if quantity > 0.000001:
            result[key] = {"quantity": quantity, "cost": sum(lot[0] * lot[1] for lot in queue), "inv": info[key]}
    for key, position in fixed.items():
        if position["cost"] > 0.005:
            result[key] = {"quantity": position["quantity"], "cost": position["cost"], "inv": info[key]}
    return result


def bens_e_direitos(investments, year):
    current = holdings_at(investments, f"{year}-12-31")
    previous = holdings_at(investments, f"{year - 1}-12-31")
    items = []
    for key in sorted(set(current) | set(previous)):
        inv = (current.get(key) or previous.get(key))["inv"]
        metadata = inv.get("metadata") or {}
        currency = normalize_currency(inv.get("native_currency") or inv.get("asset_currency"))
        group, code, label = bens_code(inv.get("asset_class"), currency, metadata)
        now = current.get(key)
        before = previous.get(key)
        ticker = inv.get("ticker_or_name")
        quantity_text = "" if inv.get("asset_class") == "FIXED_INCOME" else f"{now['quantity'] if now else 0:g} de "
        where = f" Custodiado no exterior, em {currency}." if currency != BASE_CURRENCY else ""
        items.append({
            "key": key,
            "ticker": ticker,
            "asset_class": inv.get("asset_class"),
            "currency": currency,
            "group": group,
            "code": code,
            "code_label": label,
            "quantity_previous": round(before["quantity"], 6) if before else 0,
            "cost_previous": rounded_money(before["cost"]) if before else 0.0,
            "quantity": round(now["quantity"], 6) if now else 0,
            "cost": rounded_money(now["cost"]) if now else 0.0,
            "description": (
                f"{quantity_text}{ticker}. Custo de aquisição em 31/12/{year}: "
                f"R$ {br_money(now['cost'] if now else 0)}.{where}"
            ),
        })
    items.sort(key=lambda item: (item["group"], item["code"], str(item["ticker"])))
    return items


def realized_rows(conn, current_user_id):
    return conn.execute(
        """
        SELECT rr.*, a.asset_class, a.ticker, a.currency
        FROM investment_realized_results rr
        JOIN assets a ON a.id = rr.asset_id AND a.user_id = rr.user_id
        WHERE rr.user_id = ?
        ORDER BY rr.operation_date, rr.created_at
        """,
        (current_user_id,),
    ).fetchall()


def apply_losses(result, pool):
    """(tributavel, prejuizo compensado, pool novo) de um resultado do mes."""
    if result < 0:
        return 0.0, 0.0, pool + abs(result)
    used = min(result, pool)
    return result - used, used, pool - used


def renda_variavel(rows, year):
    """Meses do ano, com os saldos de prejuizo vindos de antes."""
    by_month = defaultdict(lambda: {"STOCKS": {"sales": 0.0, "result": 0.0}, "REIT": {"sales": 0.0, "result": 0.0}})
    for row in rows:
        if row["movement_type"] != "SELL" or normalize_currency(row["currency"]) != BASE_CURRENCY:
            continue
        if row["asset_class"] not in ("STOCKS", "REIT"):
            continue
        month = str(row["operation_date"])[:7]
        bucket = by_month[month][row["asset_class"]]
        bucket["sales"] += safe_float(row["gross_proceeds"])
        bucket["result"] += safe_float(row["realized_profit"])

    pools = {"STOCKS": 0.0, "REIT": 0.0}
    pending_darf = 0.0
    months = []
    for month in sorted(by_month):
        if month > f"{year}-12":
            break
        entry = {"month": month}
        tax_total = 0.0
        stocks = by_month[month]["STOCKS"]
        exempt = stocks["sales"] <= STOCK_EXEMPTION_LIMIT
        if exempt and stocks["result"] >= 0:
            # Ganho isento nao consome prejuizo.
            taxable, used = 0.0, 0.0
        else:
            taxable, used, pools["STOCKS"] = apply_losses(stocks["result"], pools["STOCKS"])
        stock_tax = taxable * STOCK_RATE
        entry["stocks"] = {
            "sales": rounded_money(stocks["sales"]),
            "result": rounded_money(stocks["result"]),
            "exempt": exempt and stocks["result"] >= 0,
            "exempt_gain": rounded_money(stocks["result"]) if exempt and stocks["result"] > 0 else 0.0,
            "loss_used": rounded_money(used),
            "taxable": rounded_money(taxable),
            "tax": rounded_money(stock_tax),
            "loss_balance": rounded_money(pools["STOCKS"]),
        }
        reits = by_month[month]["REIT"]
        taxable, used, pools["REIT"] = apply_losses(reits["result"], pools["REIT"])
        reit_tax = taxable * REIT_RATE
        entry["reits"] = {
            "sales": rounded_money(reits["sales"]),
            "result": rounded_money(reits["result"]),
            "loss_used": rounded_money(used),
            "taxable": rounded_money(taxable),
            "tax": rounded_money(reit_tax),
            "loss_balance": rounded_money(pools["REIT"]),
        }
        tax_total = stock_tax + reit_tax + pending_darf
        if tax_total >= DARF_MINIMUM:
            entry["darf"] = rounded_money(tax_total)
            entry["darf_carried"] = 0.0
            pending_darf = 0.0
        else:
            entry["darf"] = 0.0
            entry["darf_carried"] = rounded_money(tax_total)
            pending_darf = tax_total
        if month.startswith(f"{year}-"):
            months.append(entry)

    return {
        "months": months,
        "totals": {
            "stock_exempt_gain": rounded_money(sum(m["stocks"]["exempt_gain"] for m in months)),
            "tax_due": rounded_money(sum(m["darf"] for m in months)),
            "stock_loss_balance": rounded_money(pools["STOCKS"]),
            "reit_loss_balance": rounded_money(pools["REIT"]),
        },
    }


def exterior(rows, year):
    """Apuracao anual dos ativos em moeda estrangeira, com prejuizo carregado."""
    by_year = defaultdict(float)
    for row in rows:
        if normalize_currency(row["currency"]) == BASE_CURRENCY or row["movement_type"] != "SELL":
            continue
        by_year[str(row["operation_date"])[:4]] += safe_float(row["realized_profit"])
    pool = 0.0
    result = {"result": 0.0, "loss_used": 0.0, "taxable": 0.0, "tax": 0.0, "loss_balance": 0.0}
    for key in sorted(by_year):
        if key > str(year):
            break
        taxable, used, pool = apply_losses(by_year[key], pool)
        if key == str(year):
            result = {
                "result": rounded_money(by_year[key]),
                "loss_used": rounded_money(used),
                "taxable": rounded_money(taxable),
                "tax": rounded_money(taxable * FOREIGN_RATE),
                "loss_balance": rounded_money(pool),
            }
    result["loss_balance"] = rounded_money(pool)
    return result


def proceeds_rows(conn, current_user_id, year):
    return conn.execute(
        """
        SELECT p.*, a.asset_class, a.ticker
        FROM investment_proceeds p
        JOIN assets a ON a.id = p.asset_id AND a.user_id = p.user_id
        WHERE p.user_id = ? AND substr(p.payment_date, 1, 4) = ? AND p.payment_date <= ?
        ORDER BY p.payment_date
        """,
        (current_user_id, str(year), datetime.now().strftime("%Y-%m-%d")),
    ).fetchall()


def income_sections(proceeds, rows, year):
    isentos = defaultdict(float)
    exclusiva = defaultdict(lambda: {"gross": 0.0, "withheld": 0.0})
    details = []
    for item in proceeds:
        kind = item["proceeds_type"]
        gross = safe_float(item["gross_amount"])
        tax = safe_float(item["tax_amount"])
        if kind == "DIVIDEND":
            line = "99 - Rendimentos de FII" if item["asset_class"] == "REIT" else "09 - Lucros e dividendos recebidos"
            isentos[line] += safe_float(item["net_amount"])
        elif kind == "JCP":
            exclusiva["10 - Juros sobre capital próprio"]["gross"] += gross
            exclusiva["10 - Juros sobre capital próprio"]["withheld"] += tax
        else:
            continue
        details.append({"date": item["payment_date"], "ticker": item["ticker"], "type": kind, "gross": rounded_money(gross), "tax": rounded_money(tax)})

    for row in rows:
        if row["movement_type"] != "REDEMPTION" or str(row["operation_date"])[:4] != str(year):
            continue
        profit = safe_float(row["realized_profit"])
        if profit <= 0:
            continue
        if safe_float(row["tax_rate"]) == 0 and safe_float(row["tax_amount"]) == 0:
            isentos["12 - Rendimentos de LCI, LCA, CRI e CRA"] += profit
        else:
            exclusiva["06 - Rendimentos de aplicações financeiras"]["gross"] += profit
            exclusiva["06 - Rendimentos de aplicações financeiras"]["withheld"] += safe_float(row["tax_amount"])

    return (
        [{"line": line, "amount": rounded_money(value)} for line, value in sorted(isentos.items())],
        [
            {"line": line, "gross": rounded_money(value["gross"]), "withheld": rounded_money(value["withheld"])}
            for line, value in sorted(exclusiva.items())
        ],
        details,
    )


def capital_gains(rows, year):
    items = []
    for row in rows:
        if row["movement_type"] != "SELL" or str(row["operation_date"])[:4] != str(year):
            continue
        if row["asset_class"] not in ("CATTLE", "OTHER") or normalize_currency(row["currency"]) != BASE_CURRENCY:
            continue
        items.append({
            "date": row["operation_date"],
            "ticker": row["ticker"],
            "proceeds": rounded_money(row["net_proceeds"]),
            "cost": rounded_money(row["cost_basis"]),
            "result": rounded_money(row["realized_profit"]),
            "tax_estimate": rounded_money(max(safe_float(row["realized_profit"]), 0) * STOCK_RATE),
        })
    return items


def available_years(investments, rows):
    years = {int(investment_operation_date(inv)[:4]) for inv in investments if investment_operation_date(inv)}
    years |= {int(str(row["operation_date"])[:4]) for row in rows}
    return sorted(years, reverse=True)


def build_tax_report(current_user_id, year):
    refresh_realized_results(current_user_id)
    investments = fetch_investments(current_user_id)
    with get_db() as conn:
        rows = realized_rows(conn, current_user_id)
        proceeds = proceeds_rows(conn, current_user_id, year)
    isentos, exclusiva, income_details = income_sections(proceeds, rows, year)
    variable = renda_variavel(rows, year)
    if variable["totals"]["stock_exempt_gain"]:
        isentos.append({
            "line": "20 - Ganhos líquidos em ações (vendas até R$ 20 mil no mês)",
            "amount": variable["totals"]["stock_exempt_gain"],
        })
        isentos.sort(key=lambda item: item["line"])
    return {
        "year": year,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "disclaimer": DISCLAIMER,
        "available_years": available_years(investments, rows),
        "bens_e_direitos": bens_e_direitos(investments, year),
        "renda_variavel": variable,
        "exterior": exterior(rows, year),
        "rendimentos_isentos": isentos,
        "tributacao_exclusiva": exclusiva,
        "proventos": income_details,
        "ganho_de_capital": capital_gains(rows, year),
    }


def exemption_meter(current_user_id, month, planned_sale=0.0):
    """Isentometro: vendas de acoes no mes contra o limite de R$ 20 mil.

    Le a mesma apuracao do relatorio (renda_variavel), entao o numero do mes
    corrente e o que o relatorio anual vai mostrar. `planned_sale` simula uma
    venda ainda nao lancada: diz se ela faria o mes passar do limite — o
    aviso que importa e o de antes de vender. So acoes em reais: FII nao tem
    isencao e ativo no exterior e apurado no ano.
    """
    refresh_realized_results(current_user_id)
    with get_db() as conn:
        rows = realized_rows(conn, current_user_id)
    # So ate o mes pedido: o saldo de prejuizo sai certo mesmo num mes sem venda.
    rows = [row for row in rows if str(row["operation_date"])[:7] <= month]
    variable = renda_variavel(rows, int(month[:4]))
    entry = next((m for m in variable["months"] if m["month"] == month), None)
    stocks = (entry or {}).get("stocks") or {}
    reits = (entry or {}).get("reits") or {}
    sales = safe_float(stocks.get("sales"))
    planned = rounded_money(max(safe_float(planned_sale), 0.0))
    sales_after = rounded_money(sales + planned)
    return {
        "month": month,
        "limit": STOCK_EXEMPTION_LIMIT,
        "stock_sales": rounded_money(sales),
        "remaining": rounded_money(max(STOCK_EXEMPTION_LIMIT - sales, 0.0)),
        "percent": rounded_money(sales / STOCK_EXEMPTION_LIMIT * 100),
        "exempt": sales <= STOCK_EXEMPTION_LIMIT,
        "stock_result": rounded_money(safe_float(stocks.get("result"))),
        "stock_tax": rounded_money(safe_float(stocks.get("tax"))),
        "stock_loss_balance": variable["totals"]["stock_loss_balance"],
        "reit_sales": rounded_money(safe_float(reits.get("sales"))),
        "reit_tax": rounded_money(safe_float(reits.get("tax"))),
        "darf": rounded_money(safe_float((entry or {}).get("darf"))),
        "planned_sale": planned,
        "sales_after": sales_after,
        "would_exceed": planned > 0 and sales <= STOCK_EXEMPTION_LIMIT < sales_after,
    }
