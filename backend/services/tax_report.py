"""Relatorio anual de IR (Fase 6): o que a carteira diz para a declaracao.

Ferramenta de apoio, nao fonte da verdade (decisao 5, 2026-09-23): tudo sai
do que foi lancado no app, com as regras simplificadas abaixo, e precisa ser
conferido com as notas de corretagem e os informes de rendimentos.

Secoes:

- bens_e_direitos: posicao a custo em 31/12 do ano e do ano anterior (custo
  medio ponderado sobre o fluxo em reais de fetch_investments), com
  grupo/codigo sugeridos;
- renda_variavel: mes a mes, acoes (isencao de vendas ate R$ 20 mil no mes,
  15%), ETFs e BDRs (15%, sem isencao, no mesmo saldo de prejuizo das acoes)
  e FII (20%, sem isencao, saldo proprio), carregado dos anos anteriores;
  DARF abaixo de R$ 10 acumula para o mes seguinte. A regra mora em
  services/variable_income_tax.py. Day trade nao e separado (o app nao guarda
  hora da operacao); ETF de renda fixa fica fora (IR retido na fonte);
- exterior: ativos em moeda estrangeira, apuracao anual a 15% (Lei
  14.754/2023), prejuizo carregado para o ano seguinte;
- rendimentos_isentos e tributacao_exclusiva: proventos e resgates de renda
  fixa do ano;
- ganho_de_capital: venda de "outros" em reais, para o GCAP; criptoativo com
  a isencao do mes de vendas ate R$ 35 mil (services/crypto_tax.py).
"""

from collections import defaultdict
from datetime import datetime

from asset_classes import is_crypto_asset
from db import get_db
from irpf_text import br_money, build_irpf_text
from money import rounded_money
from services.crypto_tax import capital_gain_tax, monthly_crypto_tax
from services.fixed_income import fixed_income_is_tax_free
import market_catalog
from services import market_listing
from services.fx import BASE_CURRENCY, normalize_currency
from services.proceeds import paid_proceeds_in_year
from services.realized_results import refresh_realized_results
from services.investments import (
    fetch_investments,
    investment_movement_type,
    investment_operation_date,
    movement_sort_key,
)
from services.variable_income_tax import (
    BUCKET_BY_TAX_KIND,
    STOCK_EXEMPTION_LIMIT,
    apply_losses,
    monthly_apuration,
)
from validators import safe_float

FOREIGN_RATE = 0.15

DISCLAIMER = (
    "Apoio para a declaração, calculado só com o que foi lançado no app. Confira com as notas de "
    "corretagem e os informes de rendimentos antes de declarar. Day trade não é separado."
)


def bens_code(asset_class, currency, metadata, tax_kind=None, ticker=None):
    """(grupo, codigo, rotulo) sugeridos para Bens e Direitos."""
    if is_crypto_asset(asset_class, ticker):
        return "08", "01", "Criptoativo Bitcoin (BTC)"
    if asset_class == "STOCKS" and currency == BASE_CURRENCY:
        if tax_kind == market_catalog.TAX_BDR:
            return "04", "04", "Ativos negociados em bolsa no Brasil (BDR)"
        if tax_kind in (market_catalog.TAX_ETF, market_catalog.TAX_ETF_RF):
            return "07", "09", "Fundos de índice (ETF)"
    if asset_class == "STOCKS":
        suffix = " (exterior)" if currency != BASE_CURRENCY else ""
        return "03", "01", f"Ações{suffix}"
    if asset_class == "REIT":
        return "07", "03", "Fundos imobiliários (FII)"
    if asset_class == "FIXED_INCOME":
        if fixed_income_is_tax_free(metadata):
            return "04", "03", "Títulos isentos (LCI, LCA, LIG, CRI, CRA, debêntures incentivadas)"
        return "04", "02", "Títulos sujeitos à tributação (CDB, Tesouro, debêntures...)"
    return "99", "99", "Outros bens e direitos"


def holdings_at(investments, cutoff):
    """Posicao a custo em `cutoff` (AAAA-MM-DD), por ativo (renda fixa: por titulo).

    Custo medio: soma o `cost_amount` de cada operacao (apply_average_cost), o
    mesmo custo da Posicao e do resultado realizado.
    """
    held = defaultdict(lambda: {"quantity": 0.0, "cost": 0.0})
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
        position = held[key]
        position["quantity"] += quantity
        position["cost"] += safe_float(inv.get("cost_amount"), quantity * unit_cost)
        if position["quantity"] <= 0.000001:
            position["quantity"] = 0.0
            position["cost"] = 0.0

    result = {}
    for key, position in held.items():
        if position["quantity"] > 0.000001:
            result[key] = {"quantity": position["quantity"], "cost": position["cost"], "inv": info[key]}
    for key, position in fixed.items():
        if position["cost"] > 0.005:
            result[key] = {"quantity": position["quantity"], "cost": position["cost"], "inv": info[key]}
    return result


def bens_e_direitos(investments, year, asset_names=None):
    asset_names = asset_names or {}
    current = holdings_at(investments, f"{year}-12-31")
    previous = holdings_at(investments, f"{year - 1}-12-31")
    items = []
    for key in sorted(set(current) | set(previous)):
        inv = (current.get(key) or previous.get(key))["inv"]
        metadata = inv.get("metadata") or {}
        currency = normalize_currency(inv.get("native_currency") or inv.get("asset_currency"))
        kind = market_listing.tax_kind(inv.get("ticker_or_name"), inv.get("asset_class"))
        group, code, label = bens_code(inv.get("asset_class"), currency, metadata, kind, inv.get("ticker_or_name"))
        now = current.get(key)
        before = previous.get(key)
        ticker = inv.get("ticker_or_name")
        quantity_text = "" if inv.get("asset_class") == "FIXED_INCOME" else f"{now['quantity'] if now else 0:g} de "
        where = f" Custodiado no exterior, em {currency}." if currency != BASE_CURRENCY else ""
        items.append({
            "key": key,
            "ticker": ticker,
            "name": asset_names.get(inv.get("asset_id")) or ticker,
            "asset_class": inv.get("asset_class"),
            "currency": currency,
            "group": group,
            "code": code,
            "code_label": label,
            "quantity_previous": round(before["quantity"], 8) if before else 0,
            "cost_previous": rounded_money(before["cost"]) if before else 0.0,
            "quantity": round(now["quantity"], 8) if now else 0,
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


def sale_tax_kind(row):
    """O tipo do papel para o IR de uma linha de resultado realizado."""
    return market_listing.tax_kind(row["ticker"], row["asset_class"])


def variable_income_sales(rows):
    """As vendas em reais de acoes, ETFs, BDRs e FIIs, no formato da apuracao mensal.

    ETF de renda fixa sai daqui (IR retido na fonte); ativo no exterior tem a
    apuracao anual propria (`exterior`)."""
    sales = []
    for row in rows:
        if row["movement_type"] != "SELL" or normalize_currency(row["currency"]) != BASE_CURRENCY:
            continue
        bucket = BUCKET_BY_TAX_KIND.get(sale_tax_kind(row))
        if not bucket:
            continue
        sales.append({
            "id": row["source_transaction_id"],
            "month": str(row["operation_date"])[:7],
            "bucket": bucket,
            "gross": safe_float(row["gross_proceeds"]),
            "result": safe_float(row["realized_profit"]),
        })
    return sales


def fixed_income_etf_sales(rows, year):
    """Vendas de ETF de renda fixa no ano: o IR ja vem retido pelo administrador."""
    items = []
    for row in rows:
        if row["movement_type"] != "SELL" or str(row["operation_date"])[:4] != str(year):
            continue
        if normalize_currency(row["currency"]) != BASE_CURRENCY:
            continue
        if sale_tax_kind(row) != market_catalog.TAX_ETF_RF:
            continue
        items.append({
            "date": row["operation_date"],
            "ticker": row["ticker"],
            "proceeds": rounded_money(row["net_proceeds"]),
            "result": rounded_money(row["realized_profit"]),
        })
    return items


def renda_variavel(rows, year):
    """Meses do ano, com os saldos de prejuizo vindos de antes."""
    apuration = monthly_apuration(variable_income_sales(rows))
    months = []
    opening = None
    closing = {"common": 0.0, "reit": 0.0}
    for entry in apuration["months"]:
        if entry["month"] > f"{year}-12":
            break
        if opening is None and entry["month"] >= f"{year}-01":
            opening = dict(closing)
        closing = {"common": entry["stocks"]["loss_balance"], "reit": entry["reits"]["loss_balance"]}
        if entry["month"].startswith(f"{year}-"):
            months.append(entry)

    if opening is None:
        opening = dict(closing)
    return {
        "months": months,
        # Prejuizo a compensar vindo de dezembro do ano anterior (o que o
        # programa pede em janeiro quando nao importa a declaracao anterior).
        "opening_loss_balance": {
            "stocks": rounded_money(opening["common"]),
            "reits": rounded_money(opening["reit"]),
        },
        "totals": {
            "stock_exempt_gain": rounded_money(sum(m["stocks"]["exempt_gain"] for m in months)),
            "tax_due": rounded_money(sum(m["darf"] for m in months)),
            "stock_loss_balance": rounded_money(closing["common"]),
            "reit_loss_balance": rounded_money(closing["reit"]),
        },
        "fixed_income_etfs": fixed_income_etf_sales(rows, year),
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
    # Valores como gravados (em reais, mesmo de ativo no exterior): ver services/proceeds.py.
    return paid_proceeds_in_year(conn, current_user_id, year)


def income_sections(proceeds, rows, year):
    isentos = defaultdict(float)
    exclusiva = defaultdict(lambda: {"gross": 0.0, "withheld": 0.0})
    details = []
    # Mesma classificacao, aberta por fonte pagadora (o ativo): o programa pede
    # uma linha por fonte em cada codigo.
    sources = defaultdict(lambda: {"amount": 0.0, "gross": 0.0, "withheld": 0.0})

    def add_source(section, line, ticker, name, amount=0.0, gross=0.0, withheld=0.0):
        entry = sources[(section, line, ticker)]
        entry["name"] = name or ticker
        entry["amount"] += amount
        entry["gross"] += gross
        entry["withheld"] += withheld
    for item in proceeds:
        kind = item["proceeds_type"]
        gross = safe_float(item["gross_amount"])
        tax = safe_float(item["tax_amount"])
        if kind == "DIVIDEND":
            line = "99 - Rendimentos de FII" if item["asset_class"] == "REIT" else "09 - Lucros e dividendos recebidos"
            isentos[line] += safe_float(item["net_amount"])
            add_source("isentos", line, item["ticker"], item["asset_name"], amount=safe_float(item["net_amount"]))
        elif kind == "JCP":
            exclusiva["10 - Juros sobre capital próprio"]["gross"] += gross
            exclusiva["10 - Juros sobre capital próprio"]["withheld"] += tax
            add_source("exclusiva", "10 - Juros sobre capital próprio", item["ticker"], item["asset_name"], gross=gross, withheld=tax)
        elif kind == "INTEREST":
            # Cupom de renda fixa (040): a mesma regra do resgate abaixo — sem
            # IR, isento (LCI, LCA, CRI, CRA); com IR, tributacao exclusiva.
            # A amortizacao devolve capital e nao e rendimento: fica de fora.
            if tax == 0:
                line = "12 - Rendimentos de LCI, LCA, CRI e CRA"
                isentos[line] += gross
                add_source("isentos", line, item["ticker"], item["asset_name"], amount=gross)
            else:
                line = "06 - Rendimentos de aplicações financeiras"
                exclusiva[line]["gross"] += gross
                exclusiva[line]["withheld"] += tax
                add_source("exclusiva", line, item["ticker"], item["asset_name"], gross=gross, withheld=tax)
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
            add_source("isentos", "12 - Rendimentos de LCI, LCA, CRI e CRA", row["ticker"], row["ticker"], amount=profit)
        else:
            exclusiva["06 - Rendimentos de aplicações financeiras"]["gross"] += profit
            exclusiva["06 - Rendimentos de aplicações financeiras"]["withheld"] += safe_float(row["tax_amount"])
            add_source(
                "exclusiva", "06 - Rendimentos de aplicações financeiras", row["ticker"], row["ticker"],
                gross=profit, withheld=safe_float(row["tax_amount"]),
            )

    return (
        [{"line": line, "amount": rounded_money(value)} for line, value in sorted(isentos.items())],
        [
            {
                "line": line,
                "gross": rounded_money(value["gross"]),
                "withheld": rounded_money(value["withheld"]),
                # Declarado liquido (o que a exportacao e o texto do IRPF mostram).
                "net": rounded_money(rounded_money(value["gross"]) - rounded_money(value["withheld"])),
            }
            for line, value in sorted(exclusiva.items())
        ],
        details,
        [
            {
                "section": section,
                "line": line,
                "ticker": ticker,
                "name": value["name"],
                "amount": rounded_money(value["amount"]),
                "gross": rounded_money(value["gross"]),
                "withheld": rounded_money(value["withheld"]),
            }
            for (section, line, ticker), value in sorted(sources.items())
        ],
    )


def capital_gains(rows, year):
    """Vendas de "outros" em reais para o GCAP. Criptoativo: isento no mes em que
    o total vendido de cripto fica em ate R$ 35 mil; o resto, a aliquota
    progressiva do ganho de capital (services/crypto_tax.py)."""
    selected = [
        row for row in rows
        if row["movement_type"] == "SELL"
        and str(row["operation_date"])[:4] == str(year)
        and row["asset_class"] == "OTHER"
        and normalize_currency(row["currency"]) == BASE_CURRENCY
    ]
    crypto_months = monthly_crypto_tax([
        {
            "id": row["source_transaction_id"],
            "month": str(row["operation_date"])[:7],
            "gross": safe_float(row["gross_proceeds"]),
            "result": safe_float(row["realized_profit"]),
        }
        for row in selected if is_crypto_asset(row["asset_class"], row["ticker"])
    ])
    items = []
    for row in selected:
        profit = safe_float(row["realized_profit"])
        crypto = is_crypto_asset(row["asset_class"], row["ticker"])
        month = crypto_months["months"].get(str(row["operation_date"])[:7]) if crypto else None
        items.append({
            "date": row["operation_date"],
            "ticker": row["ticker"],
            "crypto": crypto,
            "exempt": bool(month and month["exempt"]),
            "month_crypto_sales": month["gross"] if month else None,
            "proceeds": rounded_money(row["net_proceeds"]),
            "cost": rounded_money(row["cost_basis"]),
            "result": rounded_money(profit),
            "tax_estimate": (
                rounded_money(crypto_months["tax_by_sale"].get(row["source_transaction_id"], 0))
                if crypto else capital_gain_tax(profit)
            ),
        })
    return items


def exempt_crypto_gain(gains):
    """Ganho isento das vendas de cripto em meses de ate R$ 35 mil vendidos."""
    return rounded_money(sum(max(item["result"], 0) for item in gains if item["crypto"] and item["exempt"]))


def available_years(investments, rows):
    years = {int(investment_operation_date(inv)[:4]) for inv in investments if investment_operation_date(inv)}
    years |= {int(str(row["operation_date"])[:4]) for row in rows}
    return sorted(years, reverse=True)


def asset_names(conn, current_user_id):
    rows = conn.execute("SELECT id, name FROM assets WHERE user_id = ?", (current_user_id,)).fetchall()
    return {row["id"]: row["name"] for row in rows}


def build_tax_report(current_user_id, year):
    refresh_realized_results(current_user_id)
    investments = fetch_investments(current_user_id)
    with get_db() as conn:
        rows = realized_rows(conn, current_user_id)
        proceeds = proceeds_rows(conn, current_user_id, year)
        names = asset_names(conn, current_user_id)
    isentos, exclusiva, income_details, income_sources = income_sections(proceeds, rows, year)
    variable = renda_variavel(rows, year)
    gains = capital_gains(rows, year)
    if variable["totals"]["stock_exempt_gain"]:
        isentos.append({
            "line": "20 - Ganhos líquidos em ações (vendas até R$ 20 mil no mês)",
            "amount": variable["totals"]["stock_exempt_gain"],
        })
    if exempt_crypto_gain(gains):
        isentos.append({
            "line": "05 - Ganho de capital na alienação de bens de pequeno valor (criptoativos até R$ 35 mil no mês)",
            "amount": exempt_crypto_gain(gains),
        })
    isentos.sort(key=lambda item: item["line"])
    report = {
        "year": year,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "disclaimer": DISCLAIMER,
        "available_years": available_years(investments, rows),
        "bens_e_direitos": bens_e_direitos(investments, year, names),
        "renda_variavel": variable,
        "exterior": exterior(rows, year),
        "rendimentos_isentos": isentos,
        "tributacao_exclusiva": exclusiva,
        "rendimentos_por_fonte": income_sources,
        "proventos": income_details,
        "ganho_de_capital": gains,
    }
    # Texto para colar no programa da Receita: so formata o que esta acima.
    report["irpf_text"] = build_irpf_text(report)
    return report


def exemption_meter(current_user_id, month, planned_sale=0.0, ticker=None):
    """Isentometro: vendas de acoes no mes contra o limite de R$ 20 mil.

    Le a mesma apuracao do relatorio (renda_variavel), entao o numero do mes
    corrente e o que o relatorio anual vai mostrar. `planned_sale` simula uma
    venda ainda nao lancada: diz se ela faria o mes passar do limite — o
    aviso que importa e o de antes de vender. So acoes em reais: FII, ETF e
    BDR nao tem isencao, e ativo no exterior e apurado no ano. Com `ticker`, a
    venda simulada de um ETF ou BDR nao conta no limite (`eligible` False).
    """
    kind = market_listing.tax_kind(ticker, "STOCKS") if ticker else market_catalog.TAX_ACAO
    eligible = kind == market_catalog.TAX_ACAO
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
    planned = rounded_money(max(safe_float(planned_sale), 0.0)) if eligible else 0.0
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
        "eligible": eligible,
        "kind": kind,
    }
