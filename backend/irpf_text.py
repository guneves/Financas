"""Texto para colar no programa do IRPF, secao por secao.

Funcoes puras, sem banco e sem Flask: recebem o relatorio ja montado por
services/tax_report.py e so o reescrevem no formato das fichas do programa da
Receita. Nenhuma regra de apuracao mora aqui — isencao, prejuizo, DARF e a
classificacao dos rendimentos sao os numeros do relatorio (a unica copia).

Codigos: a tabela do IRPF reestruturada em 2024 (vale para o IRPF 2024 e o
IRPF 2025). Onde o app nao guarda o dado (CNPJ da fonte, corretora, pais de
ativo no exterior) o texto sai com "(preencher)": nunca inventamos CNPJ.
"""

from money import rounded_money

CODE_TABLE = "Tabela de códigos do IRPF 2024/2025 (reestruturada em 2024) — confira no programa do ano."
FILL = "(preencher)"

MONTH_NAMES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

BENS_GROUPS = {
    "03": "Participações Societárias",
    "04": "Aplicações e Investimentos",
    "07": "Fundos",
    "99": "Outros Bens e Direitos",
}

BENS_CODES = {
    ("03", "01"): "Ações (inclusive as listadas em bolsa)",
    ("04", "02"): "Títulos públicos e privados sujeitos à tributação (Tesouro Direto, CDB, RDB e outros)",
    ("04", "03"): "Títulos isentos de tributação (LCI, LCA, CRI, CRA e outros)",
    ("07", "03"): "Fundos de Investimento Imobiliário (FII)",
    ("99", "99"): "Outros bens e direitos",
}

INCOME_CODES = {
    "06": "Rendimentos de aplicações financeiras",
    "09": "Lucros e dividendos recebidos",
    "10": "Juros sobre capital próprio",
    "12": "Rendimentos de cadernetas de poupança, letras hipotecárias, LCI, LCA, CRI e CRA",
    "20": (
        "Ganhos líquidos em operações no mercado à vista de ações negociadas em bolsas de valores "
        "nas alienações realizadas até R$ 20.000,00 em cada mês, para o conjunto de ações"
    ),
    "99": "Outros",
}

DARF_CODE = "6015"


def br_money(value):
    """1234.5 -> "1.234,50"; -0,00 sai como 0,00."""
    amount = rounded_money(value) or 0.0
    return f"{amount:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def br_quantity(value):
    """1000 -> "1.000"; 12.5 -> "12,5" (cotas fracionadas: ate 6 casas)."""
    text = f"{float(value or 0):,.6f}".rstrip("0").rstrip(".")
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def month_label(key):
    year, month = str(key).split("-")[:2]
    return f"{MONTH_NAMES[int(month) - 1]}/{year}"


def line_code(line):
    return str(line).split(" - ", 1)[0].strip()


def code_text(code, fallback_line=""):
    label = INCOME_CODES.get(code) or (str(fallback_line).split(" - ", 1)[-1])
    return f"{code} - {label}"


def source_name(ticker, name):
    return f"{ticker} - {name}" if name and name != ticker else str(ticker)


def section(key, title, hint, blocks, empty):
    text = "\n\n".join(block["text"] for block in blocks)
    return {"key": key, "title": title, "hint": hint, "blocks": blocks, "text": text, "empty": empty}


# --- Bens e Direitos ---


def bens_block(item, year):
    group, code = item["group"], item["code"]
    ticker = item["ticker"]
    name = item.get("name") or ticker
    currency = item.get("currency") or "BRL"
    foreign = currency != "BRL"
    asset_class = item.get("asset_class")
    listed = asset_class in ("STOCKS", "REIT") and not foreign

    lines = [
        f"Grupo: {group} - {BENS_GROUPS.get(group, 'Outros Bens e Direitos')}",
        f"Código: {code} - {BENS_CODES.get((group, code), item.get('code_label') or '')}",
        f"Localização (País): {FILL + ' (ativo em ' + currency + ')' if foreign else '105 - Brasil'}",
    ]
    if asset_class == "REIT":
        lines.append(f"CNPJ do fundo: {FILL}")
    elif asset_class == "STOCKS" and not foreign:
        lines.append(f"CNPJ da empresa: {FILL}")
    elif asset_class == "FIXED_INCOME":
        lines.append(f"CNPJ da instituição emissora: {FILL}")
    if listed:
        lines.append(f"Negociado em bolsa: Sim · Código de negociação: {ticker}")

    quantity = float(item.get("quantity") or 0)
    cost = float(item.get("cost") or 0)
    label = source_name(ticker, name)
    if asset_class in ("STOCKS", "REIT"):
        unit, single = ("cotas", "cota") if asset_class == "REIT" else ("ações", "ação")
        if quantity > 0:
            description = (
                f"{br_quantity(quantity)} {unit} {label}, custo médio de R$ {br_money(cost / quantity)} por {single}."
            )
        else:
            description = f"{label}: posição zerada em 31/12/{year} (vendida no ano)."
    else:
        description = f"{label}." if cost > 0 else f"{label}: posição zerada em 31/12/{year} (resgatada no ano)."
    if foreign:
        description += f" Custodiado no exterior, em {currency}; custo em reais pelo câmbio de cada compra."
    else:
        description += f" Corretora/custodiante: {FILL}."
    lines.append(f"Discriminação: {description}")
    lines.append(f"Situação em 31/12/{year - 1} (R$): {br_money(item.get('cost_previous'))}")
    lines.append(f"Situação em 31/12/{year} (R$): {br_money(cost)}")
    return {"title": f"{ticker} · {group}/{code}", "text": "\n".join(lines)}


def bens_section(report):
    year = report["year"]
    blocks = [bens_block(item, year) for item in report["bens_e_direitos"]]
    return section(
        "bens",
        "Bens e Direitos",
        "Um bem por ativo, a custo de aquisição (nunca a valor de mercado).",
        blocks,
        f"Nenhuma posição em 31/12/{year - 1} nem em 31/12/{year}.",
    )


# --- Rendimentos ---


def income_block(item):
    code = line_code(item["line"])
    name = source_name(item["ticker"], item.get("name"))
    lines = [
        f"Código: {code_text(code, item['line'])}",
        "Tipo de beneficiário: Titular",
        f"CNPJ da fonte pagadora: {FILL}",
        f"Nome da fonte pagadora: {name}",
    ]
    if code == "99":
        lines.append(f"Descrição: {item['line'].split(' - ', 1)[-1]} — {item['ticker']}")
    if item["section"] == "exclusiva":
        net = rounded_money(item["gross"] - item["withheld"])
        lines.append(f"Valor (R$): {br_money(net)}")
        lines.append(
            f"(Bruto R$ {br_money(item['gross'])} − IR retido R$ {br_money(item['withheld'])}; "
            "confira com o informe de rendimentos da fonte.)"
        )
    else:
        lines.append(f"Valor (R$): {br_money(item['amount'])}")
    return {"title": f"{code} · {item['ticker']}", "text": "\n".join(lines)}


def exempt_sales_block(report):
    line = next((item for item in report["rendimentos_isentos"] if line_code(item["line"]) == "20"), None)
    if not line or not line["amount"]:
        return None
    months = [
        f"{month_label(month['month'])}: {br_money(month['stocks']['exempt_gain'])}"
        for month in report["renda_variavel"]["months"]
        if month["stocks"]["exempt_gain"]
    ]
    lines = [
        f"Código: {code_text('20')}",
        "Tipo de beneficiário: Titular",
        f"Valor (R$): {br_money(line['amount'])}",
    ]
    if months:
        lines.append(f"(Meses: {'; '.join(months)}.)")
    return {"title": "20 · vendas isentas", "text": "\n".join(lines)}


def isentos_section(report):
    blocks = [income_block(item) for item in report.get("rendimentos_por_fonte", []) if item["section"] == "isentos"]
    exempt = exempt_sales_block(report)
    if exempt:
        blocks.append(exempt)
    blocks.sort(key=lambda block: block["title"])
    return section(
        "isentos",
        "Rendimentos isentos e não tributáveis",
        "Uma linha por fonte pagadora em cada código; o código 20 é um total só.",
        blocks,
        "Nenhum rendimento isento no ano.",
    )


def exclusiva_section(report):
    blocks = [income_block(item) for item in report.get("rendimentos_por_fonte", []) if item["section"] == "exclusiva"]
    return section(
        "exclusiva",
        "Rendimentos sujeitos à tributação exclusiva/definitiva",
        "Valor líquido recebido (bruto menos o IR retido na fonte), uma linha por fonte pagadora.",
        blocks,
        "Nenhum rendimento de tributação exclusiva no ano.",
    )


# --- Renda variavel ---


def month_block(month):
    stocks, reits = month["stocks"], month["reits"]
    lines = [month_label(month["month"]).capitalize()]
    if stocks["sales"]:
        if stocks["exempt"]:
            lines.append("Operações comuns · Mercado à vista - ações (R$): 0,00")
            lines.append(
                f"(Vendas de R$ {br_money(stocks['sales'])} no mês, até R$ 20 mil: o ganho de "
                f"R$ {br_money(stocks['exempt_gain'])} é isento e vai em Rendimentos isentos, código 20.)"
            )
        else:
            lines.append(f"Operações comuns · Mercado à vista - ações (R$): {br_money(stocks['result'])}")
            lines.append(
                f"(Conferência ações: vendas {br_money(stocks['sales'])} · prejuízo compensado "
                f"{br_money(stocks['loss_used'])} · base de cálculo {br_money(stocks['taxable'])} · imposto devido "
                f"{br_money(stocks['tax'])} · prejuízo a compensar {br_money(stocks['loss_balance'])})"
            )
    if reits["sales"]:
        lines.append(f"Fundos de Investimento Imobiliário · Resultado líquido do mês (R$): {br_money(reits['result'])}")
        lines.append(
            f"(Conferência FII: prejuízo compensado {br_money(reits['loss_used'])} · base de cálculo "
            f"{br_money(reits['taxable'])} · imposto devido {br_money(reits['tax'])} · prejuízo a compensar "
            f"{br_money(reits['loss_balance'])})"
        )
    if month["darf"]:
        lines.append(f"Imposto pago (R$): {br_money(month['darf'])} — DARF {DARF_CODE}; informe só se foi pago.")
    elif month["darf_carried"]:
        lines.append(f"Imposto pago (R$): 0,00 — R$ {br_money(month['darf_carried'])} abaixo do mínimo do DARF, acumula.")
    return {"title": month["month"], "text": "\n".join(lines)}


def renda_variavel_section(report):
    variable = report["renda_variavel"]
    year = report["year"]
    blocks = []
    opening = variable.get("opening_loss_balance") or {}
    if opening.get("stocks") or opening.get("reits"):
        blocks.append({
            "title": "saldo anterior",
            "text": "\n".join([
                f"Prejuízo a compensar de 31/12/{year - 1} (informe em janeiro se o programa não trouxer da declaração anterior)",
                f"Operações comuns · Resultado negativo até o mês anterior (R$): {br_money(opening.get('stocks'))}",
                f"Fundos de Investimento Imobiliário · Resultado negativo até o mês anterior (R$): {br_money(opening.get('reits'))}",
            ]),
        })
    blocks.extend(month_block(month) for month in variable["months"])
    return section(
        "renda_variavel",
        "Renda variável",
        "Ficha Renda Variável: operações comuns e FII, mês a mês. Meses sem venda ficam em branco. Day trade não é separado.",
        blocks,
        "Nenhuma venda de ações ou FII no ano.",
    )


def build_irpf_text(report):
    """Secoes com blocos de texto prontos para colar, na ordem das fichas."""
    return {
        "code_table": CODE_TABLE,
        "sections": [
            bens_section(report),
            isentos_section(report),
            exclusiva_section(report),
            renda_variavel_section(report),
        ],
    }
