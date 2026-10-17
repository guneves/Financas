"""Apuracao mensal da renda variavel: o IR das vendas de acoes, ETFs, BDRs e FIIs.

Pura (sem banco): recebe as vendas, cada uma com o resultado realizado, e
devolve o mes a mes e a parte de cada venda no imposto do mes. O relatorio de
IR (services/tax_report.py) mostra o mes a mes; o resultado realizado
(services/realized_results.py) grava em cada venda a parte dela, para a lista
de Operacoes dizer o mesmo que a aba IR — uma regra so.

Regras (simplificadas; day trade nao e separado, o app nao guarda a hora):

- acoes no mercado a vista: o ganho e isento no mes em que as vendas de acoes
  somam ate R$ 20 mil (Lei 11.033/2004, art. 3o, I); acima disso, 15%;
- ETF de renda variavel e BDR: 15% sobre todo ganho, sem isencao, e as vendas
  deles nao contam para o limite das acoes. Sao operacoes comuns como as acoes:
  o prejuizo de um compensa o ganho do outro, no mesmo saldo;
- FII: 20%, sem isencao, com saldo de prejuizo proprio (Lei 8.668/1993, art. 18);
- ETF de renda fixa: IR retido na fonte pelo administrador (Lei 13.043/2014),
  fora do DARF — nao entra aqui (quem chama nao manda).

Ganho isento nao consome prejuizo. Prejuizo de acoes num mes isento entra no
saldo (e compensa, no proprio mes, o ganho de um ETF ou BDR). O DARF abaixo de
R$ 10 acumula para o mes seguinte.
"""

from collections import defaultdict

from money import rounded_money
from validators import safe_float

STOCK_EXEMPTION_LIMIT = 20000.0
STOCK_RATE = 0.15
REIT_RATE = 0.20
DARF_MINIMUM = 10.0

# O balde de cada venda (o tipo do papel para o IR, market_catalog.tax_kind).
BUCKET_STOCK = "ACAO"
BUCKET_COMMON = "COMMON"  # ETF de renda variavel e BDR
BUCKET_REIT = "FII"

BUCKET_BY_TAX_KIND = {
    "ACAO": BUCKET_STOCK,
    "ETF": BUCKET_COMMON,
    "BDR": BUCKET_COMMON,
    "FII": BUCKET_REIT,
}


def apply_losses(result, pool):
    """(tributavel, prejuizo compensado, saldo novo) de um resultado do mes."""
    if result < 0:
        return 0.0, 0.0, pool + abs(result)
    used = min(result, pool)
    return result - used, used, pool - used


def split_tax(tax, sales):
    """Reparte `tax` entre as vendas com lucro, na proporcao do lucro de cada uma.

    {id: imposto}; o centavo que sobra do arredondamento vai para o maior lucro,
    para a soma bater com o imposto do mes.
    """
    winners = [sale for sale in sales if sale["result"] > 0]
    total = sum(sale["result"] for sale in winners)
    shares = {sale["id"]: 0.0 for sale in sales}
    if tax <= 0 or total <= 0:
        return shares
    for sale in winners:
        shares[sale["id"]] = rounded_money(tax * sale["result"] / total)
    residual = rounded_money(rounded_money(tax) - sum(shares[sale["id"]] for sale in winners))
    if residual:
        largest = max(winners, key=lambda sale: sale["result"])["id"]
        shares[largest] = rounded_money(shares[largest] + residual)
    return shares


def monthly_apuration(sales):
    """O mes a mes de todas as vendas e o imposto de cada uma.

    `sales`: [{"id", "month" (AAAA-MM), "bucket" (ACAO, COMMON, FII), "gross"
    (valor de venda), "result" (resultado realizado)}]. Devolve
    {"months": [entrada por mes, em ordem], "tax_by_sale": {id: imposto}}, com a
    entrada no formato do relatorio de IR (stocks, etfs, reits, darf).
    """
    by_month = defaultdict(lambda: defaultdict(list))
    for sale in sales:
        if sale["bucket"] in (BUCKET_STOCK, BUCKET_COMMON, BUCKET_REIT):
            by_month[sale["month"]][sale["bucket"]].append(sale)

    pools = {"common": 0.0, "reit": 0.0}
    pending_darf = 0.0
    months = []
    tax_by_sale = {}
    for month in sorted(by_month):
        groups = by_month[month]
        stocks = groups[BUCKET_STOCK]
        common = groups[BUCKET_COMMON]
        reits = groups[BUCKET_REIT]
        stock_sales = sum(safe_float(sale["gross"]) for sale in stocks)
        stock_result = sum(safe_float(sale["result"]) for sale in stocks)
        common_sales = sum(safe_float(sale["gross"]) for sale in common)
        common_only_result = sum(safe_float(sale["result"]) for sale in common)
        reit_sales = sum(safe_float(sale["gross"]) for sale in reits)
        reit_result = sum(safe_float(sale["result"]) for sale in reits)

        exempt = stock_sales <= STOCK_EXEMPTION_LIMIT
        exempt_gain = max(stock_result, 0.0) if exempt else 0.0
        # Acoes isentas: o ganho fica de fora; o prejuizo entra no resultado comum.
        stock_part = min(stock_result, 0.0) if exempt else stock_result
        common_result = stock_part + common_only_result
        if exempt and stock_result >= 0 and not common:
            taxable, used = 0.0, 0.0
        else:
            taxable, used, pools["common"] = apply_losses(common_result, pools["common"])
        common_tax = taxable * STOCK_RATE
        taxed_sales = common + ([] if exempt else stocks)
        tax_by_sale.update({sale["id"]: 0.0 for sale in stocks})
        tax_by_sale.update(split_tax(common_tax, taxed_sales))

        reit_taxable, reit_used, pools["reit"] = apply_losses(reit_result, pools["reit"])
        reit_tax = reit_taxable * REIT_RATE
        tax_by_sale.update(split_tax(reit_tax, reits))

        entry = {
            "month": month,
            "stocks": {
                "sales": rounded_money(stock_sales),
                "result": rounded_money(stock_result),
                "exempt": exempt and stock_result >= 0,
                "exempt_gain": rounded_money(exempt_gain) if stock_sales else 0.0,
                # O que vai na linha "Mercado a vista - acoes" das operacoes comuns:
                # acoes (o prejuizo, se o mes e isento) mais ETFs e BDRs.
                "common_result": rounded_money(common_result),
                "loss_used": rounded_money(used),
                "taxable": rounded_money(taxable),
                "tax": rounded_money(common_tax),
                "loss_balance": rounded_money(pools["common"]),
            },
            "etfs": {
                "sales": rounded_money(common_sales),
                "result": rounded_money(common_only_result),
            },
            "reits": {
                "sales": rounded_money(reit_sales),
                "result": rounded_money(reit_result),
                "loss_used": rounded_money(reit_used),
                "taxable": rounded_money(reit_taxable),
                "tax": rounded_money(reit_tax),
                "loss_balance": rounded_money(pools["reit"]),
            },
        }
        month_tax = common_tax + reit_tax + pending_darf
        if month_tax >= DARF_MINIMUM:
            entry["darf"] = rounded_money(month_tax)
            entry["darf_carried"] = 0.0
            pending_darf = 0.0
        else:
            entry["darf"] = 0.0
            entry["darf_carried"] = rounded_money(month_tax)
            pending_darf = month_tax
        months.append(entry)
    return {"months": months, "tax_by_sale": tax_by_sale}
