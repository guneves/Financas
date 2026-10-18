"""IR do ganho de capital na venda de criptoativos em reais (funcoes puras).

Regra da Receita para pessoa fisica (Perguntas e Respostas IRPF, capitulo
Ganho de Capital, criptoativos; IN RFB 1.888/2019 para as informacoes):

- isento o ganho do mes em que o total das alienacoes de criptoativos fica em
  ate R$ 35 mil (bens de pequeno valor: Lei 9.250/1995, art. 22, II, com a
  redacao da Lei 11.196/2005) -- o limite olha o total VENDIDO no mes, nao o
  lucro;
- acima dele, cada ganho paga as aliquotas progressivas do ganho de capital
  (Lei 8.981/1995, art. 21, com a redacao da Lei 13.259/2016): 15% ate R$ 5
  milhoes, 17,5% de 5 a 10, 20% de 10 a 30 e 22,5% acima, cada faixa sobre a
  sua parcela;
- prejuizo nao compensa ganho (ganho de capital, nao renda variavel): uma
  venda com perda paga 0 e nao reduz o imposto das outras;
- apurado no GCAP, DARF codigo 4600 ate o ultimo dia util do mes seguinte.

Criptoativo em exchange/custodia no exterior cai na Lei 14.754/2023 (15% ao
ano, com os demais ativos no exterior) -- aqui so as operacoes em reais.
"""

from collections import defaultdict

from money import rounded_money

CRYPTO_EXEMPTION_LIMIT = 35000.0

# (teto da faixa, aliquota); a ultima faixa nao tem teto.
CAPITAL_GAIN_BRACKETS = (
    (5_000_000.0, 0.15),
    (10_000_000.0, 0.175),
    (30_000_000.0, 0.20),
    (None, 0.225),
)


def capital_gain_tax(gain):
    """Imposto progressivo sobre um ganho (cada faixa na sua parcela)."""
    remaining = max(float(gain or 0), 0.0)
    tax = 0.0
    floor = 0.0
    for ceiling, rate in CAPITAL_GAIN_BRACKETS:
        if remaining <= 0:
            break
        width = remaining if ceiling is None else min(remaining, ceiling - floor)
        tax += width * rate
        remaining -= width
        floor = ceiling or floor
    return rounded_money(tax)


def monthly_crypto_tax(sales):
    """`sales`: [{"id", "month": "AAAA-MM", "gross", "result"}].

    Devolve {"months": {mes: {"gross", "gain", "exempt", "tax"}},
    "tax_by_sale": {id: imposto}}."""
    by_month = defaultdict(list)
    for sale in sales:
        by_month[sale["month"]].append(sale)

    months = {}
    tax_by_sale = {}
    for month, month_sales in sorted(by_month.items()):
        gross = sum(float(sale.get("gross") or 0) for sale in month_sales)
        exempt = gross <= CRYPTO_EXEMPTION_LIMIT
        tax = 0.0
        for sale in month_sales:
            sale_tax = 0.0 if exempt else capital_gain_tax(sale.get("result"))
            tax_by_sale[sale["id"]] = sale_tax
            tax += sale_tax
        months[month] = {
            "gross": rounded_money(gross),
            "gain": rounded_money(sum(max(float(sale.get("result") or 0), 0) for sale in month_sales)),
            "exempt": exempt,
            "tax": rounded_money(tax),
        }
    return {"months": months, "tax_by_sale": tax_by_sale}
