"""Tabelas de exportacao (extrato, carteira, operacoes, proventos) em CSV.

Funcoes puras, sem banco e sem Flask — a mesma forma de statement_import.py:
o modulo monta o texto, a rota busca os dados e devolve a resposta.

Cada exportacao e uma lista de colunas tipadas (`Column`): a chave que o
cliente usa para escolher colunas (`?columns=data,valor`), o cabecalho e o
tipo do valor. A mesma tabela vira CSV aqui ou planilha em export_xlsx.py; so
a formatacao muda.

O CSV sai no formato que o Excel em pt-BR abre com um duplo clique: BOM UTF-8,
ponto e virgula como separador e numero com virgula decimal.
"""

import io
import csv
from collections import namedtuple


CSV_DELIMITER = ";"
BOM = "﻿"

# kind: "text", "date" (AAAA-MM-DD), "money" (2 casas), "quantity" (ate 6
# casas: cotas fracionadas) ou "percent" (12.5 quer dizer 12,5%).
Column = namedtuple("Column", ["key", "header", "kind", "value"])

TRANSACTION_TYPE_LABELS = {
    "INCOME": "Receita",
    "EXPENSE": "Despesa",
    "TRANSFER": "Transferência",
}

SOURCE_LABELS = {
    "INVESTMENT_TRANSACTION": "Carteira",
    "CC_INVOICE_PAYMENT": "Fatura do cartão",
    "CC_AUTOPAY": "Débito automático",
    "RECURRING_TRANSACTION": "Recorrência",
    "STATEMENT_IMPORT": "Importação de extrato",
    "PLUGGY": "Banco (Pluggy)",
}

ASSET_CLASS_LABELS = {
    "STOCKS": "Ações",
    "FIXED_INCOME": "Renda Fixa",
    "REIT": "Fundos Imobiliários",
    "OTHER": "Outros",
}

MOVEMENT_TYPE_LABELS = {
    "BUY": "Compra",
    "SELL": "Venda",
    "REDEMPTION": "Resgate",
}

def movement_label(movement_type, asset_class):
    """Como a tela Operacoes chama: renda fixa tem aporte e resgate."""
    is_sale = movement_type in ("SELL", "REDEMPTION")
    if asset_class == "FIXED_INCOME":
        return "Resgate" if is_sale else "Aporte"
    return MOVEMENT_TYPE_LABELS.get(movement_type, movement_type or "")


PROCEEDS_TYPE_LABELS = {
    "DIVIDEND": "Dividendos",
    "JCP": "JCP",
    "AMORTIZATION": "Amortização",
}

PROCEEDS_STATUS_LABELS = {
    "PAID": "Pago",
    "SCHEDULED": "Agendado",
}


class ColumnError(ValueError):
    """Coluna pedida que a exportacao nao tem."""


def to_number(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_decimal(value, places=2):
    """Numero no formato pt-BR (1234.5 -> "1234,50"), sem separador de milhar.

    Sem separador de milhar de proposito: o Excel le a celula como numero em
    qualquer configuracao de milhar, e quem abre no Google Sheets tambem.
    """
    number = to_number(value)
    if number is None:
        return ""
    return f"{number:.{places}f}".replace(".", ",")


def signed_value(amount, transaction_type):
    """Valor com sinal de efeito no caixa, como numero (None para TRANSFER).

    TRANSFER fica vazio: a transferencia sai de uma conta e entra em outra na
    mesma linha, entao somar a coluna daria uma despesa que nao existe. E a
    mesma regra que o saldo consolidado usa.
    """
    if transaction_type == "TRANSFER":
        return None
    number = to_number(amount) or 0
    return -number if transaction_type == "EXPENSE" else number


def signed_amount(amount, transaction_type):
    return format_decimal(signed_value(amount, transaction_type))


def source_label(source_type):
    """Quem criou o lancamento. Sem source_type e digitacao manual."""
    if not source_type:
        return "Manual"
    return SOURCE_LABELS.get(source_type, source_type)


def label(mapping, value):
    return mapping.get(value, value or "")


# --- colunas de cada exportacao ---------------------------------------------
# `value(item, context)`: o item e o dict que a rota monta; o contexto leva o
# que nao esta no item (nomes das contas, no extrato).

TRANSACTION_COLUMNS = [
    Column("data", "Data", "date", lambda t, c: t.get("date")),
    Column("tipo", "Tipo", "text", lambda t, c: label(TRANSACTION_TYPE_LABELS, t.get("type"))),
    Column("descricao", "Descrição", "text", lambda t, c: t.get("description")),
    Column("categoria", "Categoria", "text", lambda t, c: t.get("category")),
    Column("conta", "Conta", "text", lambda t, c: c.get("account_names", {}).get(t.get("account_id"), "")),
    Column("conta_destino", "Conta destino", "text",
           lambda t, c: c.get("account_names", {}).get(t.get("transfer_account_id"), "")),
    Column("valor", "Valor", "money", lambda t, c: t.get("amount")),
    Column("valor_com_sinal", "Valor com sinal", "money", lambda t, c: signed_value(t.get("amount"), t.get("type"))),
    Column("origem", "Origem", "text", lambda t, c: source_label(t.get("source_type"))),
]


def portfolio_invested(asset):
    # O custo do ativo como a carteira o soma; quantidade x preco medio (ja
    # arredondado) so para payload antigo, e pode errar por centavos.
    if asset.get("total_invested") is not None:
        return asset.get("total_invested")
    quantity = to_number(asset.get("quantity")) or 0
    average_price = to_number(asset.get("average_price")) or 0
    return quantity * average_price


PORTFOLIO_COLUMNS = [
    Column("ativo", "Ativo", "text", lambda a, c: a.get("ticker")),
    Column("classe", "Classe", "text", lambda a, c: label(ASSET_CLASS_LABELS, a.get("class"))),
    Column("quantidade", "Quantidade", "quantity", lambda a, c: a.get("quantity")),
    Column("preco_medio", "Preço médio", "money", lambda a, c: a.get("average_price")),
    Column("preco_atual", "Preço atual", "money", lambda a, c: a.get("current_price")),
    Column("valor_investido", "Valor investido", "money", lambda a, c: portfolio_invested(a)),
    Column("valor_bruto", "Valor bruto", "money", lambda a, c: a.get("current_value")),
    Column("ir_estimado", "IR estimado", "money", lambda a, c: a.get("taxes")),
    Column("valor_liquido", "Valor líquido", "money", lambda a, c: a.get("net_value")),
    Column("rentabilidade", "Rentabilidade (%)", "percent", lambda a, c: a.get("profitability_percent")),
    # Proventos pagos (liquidos) e a rentabilidade com eles, como a tela Posicao.
    Column("proventos", "Proventos", "money", lambda a, c: a.get("proceeds_net")),
    Column("proventos_12m", "Proventos 12m", "money", lambda a, c: a.get("proceeds_12m_net")),
    Column("dy_12m", "DY 12m (%)", "percent", lambda a, c: a.get("dividend_yield_12m")),
    Column("rentabilidade_com_proventos", "Rentab. c/ proventos (%)", "percent",
           lambda a, c: a.get("total_return_percent")),
    Column("isento_ir", "Isento de IR", "text", lambda a, c: "Sim" if a.get("is_tax_free") else "Não"),
    Column("cotacao_de", "Cotação de", "date", lambda a, c: ((a.get("quote") or {}).get("quoted_at") or "")[:10]),
]

# Operacoes: a rota entrega cada movimentacao ja resolvida (tipo, data, bruto,
# custos, resultado realizado), com as regras de services/investments.py.
MOVEMENT_COLUMNS = [
    Column("data", "Data", "date", lambda m, c: m.get("date")),
    Column("tipo", "Tipo", "text", lambda m, c: movement_label(m.get("movement_type"), m.get("asset_class"))),
    Column("ativo", "Ativo", "text", lambda m, c: m.get("ticker")),
    Column("classe", "Classe", "text", lambda m, c: label(ASSET_CLASS_LABELS, m.get("asset_class"))),
    Column("quantidade", "Quantidade", "quantity", lambda m, c: m.get("quantity")),
    Column("preco", "Preço", "money", lambda m, c: m.get("unit_price")),
    Column("valor_bruto", "Valor bruto", "money", lambda m, c: m.get("gross_amount")),
    Column("custos", "Custos", "money", lambda m, c: m.get("fees")),
    Column("custo_vendido", "Custo do vendido", "money", lambda m, c: m.get("realized_cost_basis")),
    Column("resultado", "Resultado", "money", lambda m, c: m.get("realized_profit")),
    Column("ir", "IR estimado", "money", lambda m, c: m.get("realized_tax_amount")),
    Column("resultado_pos_ir", "Resultado pós-IR", "money", lambda m, c: m.get("realized_net_profit_after_tax")),
]

PROCEEDS_COLUMNS = [
    Column("pagamento", "Pagamento", "date", lambda p, c: p.get("payment_date")),
    Column("ativo", "Ativo", "text", lambda p, c: (p.get("asset") or {}).get("ticker")),
    Column("classe", "Classe", "text", lambda p, c: label(ASSET_CLASS_LABELS, (p.get("asset") or {}).get("asset_class"))),
    Column("tipo", "Tipo", "text", lambda p, c: label(PROCEEDS_TYPE_LABELS, p.get("proceeds_type"))),
    Column("status", "Situação", "text", lambda p, c: label(PROCEEDS_STATUS_LABELS, p.get("status"))),
    Column("data_com", "Data com", "date", lambda p, c: p.get("record_date")),
    Column("data_ex", "Data ex", "date", lambda p, c: p.get("ex_date")),
    Column("valor_por_cota", "Valor por cota", "quantity", lambda p, c: p.get("amount_per_unit")),
    Column("quantidade", "Quantidade", "quantity", lambda p, c: p.get("eligible_quantity")),
    Column("bruto", "Bruto", "money", lambda p, c: p.get("gross_amount")),
    Column("imposto", "Imposto", "money", lambda p, c: p.get("tax_amount")),
    Column("liquido", "Líquido", "money", lambda p, c: p.get("net_amount")),
    Column("yield_on_cost", "Yield on cost (%)", "percent", lambda p, c: p.get("yield_on_cost_percent")),
    Column("observacoes", "Observações", "text", lambda p, c: p.get("notes")),
]

EXPORTS = {
    "transactions": TRANSACTION_COLUMNS,
    "portfolio": PORTFOLIO_COLUMNS,
    "movements": MOVEMENT_COLUMNS,
    "proceeds": PROCEEDS_COLUMNS,
}

TRANSACTIONS_HEADER = [column.header for column in TRANSACTION_COLUMNS]
PORTFOLIO_HEADER = [column.header for column in PORTFOLIO_COLUMNS]


def column_catalog():
    """O que o seletor de colunas do cliente mostra, por exportacao."""
    return {
        name: [{"key": column.key, "label": column.header} for column in columns]
        for name, columns in EXPORTS.items()
    }


def select_columns(columns, raw_keys):
    """Colunas pedidas, na ordem pedida. Vazio ou ausente = todas.

    `raw_keys` e o texto de `?columns=` ("data,valor") ou uma lista.
    """
    if raw_keys in (None, "", []):
        return list(columns)
    keys = raw_keys.split(",") if isinstance(raw_keys, str) else list(raw_keys)
    keys = [str(key).strip() for key in keys if str(key).strip()]
    by_key = {column.key: column for column in columns}
    unknown = [key for key in keys if key not in by_key]
    if unknown:
        raise ColumnError(f"Coluna desconhecida: {', '.join(unknown)}.")
    selected = []
    for key in keys:
        if by_key[key] not in selected:
            selected.append(by_key[key])
    if not selected:
        raise ColumnError("Escolha ao menos uma coluna.")
    return selected


def table_values(columns, items, context=None):
    """Linhas de valores crus (numero como numero), na ordem das colunas."""
    context = context or {}
    return [[column.value(item, context) for column in columns] for item in items or []]


def format_cell(value, kind):
    if value is None:
        return ""
    if kind == "money":
        return format_decimal(value)
    if kind == "percent":
        return format_decimal(value)
    if kind == "quantity":
        number = to_number(value)
        if number is None:
            return ""
        # Ate 6 casas, sem zeros a direita: 100 cotas saem "100", nao "100,000000".
        text = f"{number:.6f}".rstrip("0").rstrip(".")
        return text.replace(".", ",")
    return str(value)


def build_csv(header, rows):
    """Monta o texto do CSV com BOM, ";" e quebra de linha CRLF."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=CSV_DELIMITER, lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(["" if cell is None else cell for cell in row])
    return BOM + buffer.getvalue()


def table_csv(columns, items, context=None):
    rows = [
        [format_cell(value, column.kind) for value, column in zip(values, columns)]
        for values in table_values(columns, items, context)
    ]
    return build_csv([column.header for column in columns], rows)


def transaction_row(transaction, account_names=None):
    context = {"account_names": account_names or {}}
    return [format_cell(column.value(transaction, context), column.kind) for column in TRANSACTION_COLUMNS]


def transactions_csv(transactions, account_names=None):
    return table_csv(TRANSACTION_COLUMNS, transactions, {"account_names": account_names or {}})


def portfolio_row(asset):
    return [format_cell(column.value(asset, {}), column.kind) for column in PORTFOLIO_COLUMNS]


def portfolio_csv(assets):
    return table_csv(PORTFOLIO_COLUMNS, assets or [])


# --- relatorio anual de IR (services/tax_report.py) -----------------------------
# Um .xlsx com uma aba por secao; os itens chegam achatados pela rota.

TAX_BENS_COLUMNS = [
    Column("grupo", "Grupo", "text", lambda b, c: b.get("group")),
    Column("codigo", "Código", "text", lambda b, c: b.get("code")),
    Column("tipo", "Tipo", "text", lambda b, c: b.get("code_label")),
    Column("ativo", "Ativo", "text", lambda b, c: b.get("ticker")),
    Column("quantidade_anterior", "Quantidade 31/12 anterior", "quantity", lambda b, c: b.get("quantity_previous")),
    Column("custo_anterior", "Situação 31/12 anterior (R$)", "money", lambda b, c: b.get("cost_previous")),
    Column("quantidade", "Quantidade 31/12", "quantity", lambda b, c: b.get("quantity")),
    Column("custo", "Situação 31/12 (R$)", "money", lambda b, c: b.get("cost")),
    Column("discriminacao", "Discriminação", "text", lambda b, c: b.get("description")),
]

TAX_MONTH_COLUMNS = [
    Column("mes", "Mês", "text", lambda m, c: m.get("month")),
    Column("vendas_acoes", "Vendas de ações", "money", lambda m, c: m["stocks"]["sales"]),
    Column("resultado_acoes", "Resultado ações", "money", lambda m, c: m["stocks"]["result"]),
    Column("isento", "Isento (até R$ 20 mil)", "text", lambda m, c: "Sim" if m["stocks"]["exempt"] else "Não"),
    # ETF e BDR: 15% sem isencao, no mesmo saldo de prejuizo das acoes.
    Column("vendas_etfs", "Vendas de ETFs e BDRs", "money", lambda m, c: (m.get("etfs") or {}).get("sales")),
    Column("resultado_etfs", "Resultado ETFs e BDRs", "money", lambda m, c: (m.get("etfs") or {}).get("result")),
    Column("prejuizo_acoes", "Prejuízo compensado (ações, ETFs e BDRs)", "money", lambda m, c: m["stocks"]["loss_used"]),
    Column("ir_acoes", "IR ações, ETFs e BDRs (15%)", "money", lambda m, c: m["stocks"]["tax"]),
    Column("vendas_fii", "Vendas de FII", "money", lambda m, c: m["reits"]["sales"]),
    Column("resultado_fii", "Resultado FII", "money", lambda m, c: m["reits"]["result"]),
    Column("prejuizo_fii", "Prejuízo compensado (FII)", "money", lambda m, c: m["reits"]["loss_used"]),
    Column("ir_fii", "IR FII (20%)", "money", lambda m, c: m["reits"]["tax"]),
    Column("darf", "DARF do mês", "money", lambda m, c: m.get("darf")),
    Column("darf_acumulado", "Abaixo de R$ 10 (acumula)", "money", lambda m, c: m.get("darf_carried")),
]

TAX_INCOME_COLUMNS = [
    Column("ficha", "Ficha", "text", lambda i, c: i.get("section")),
    Column("linha", "Linha", "text", lambda i, c: i.get("line")),
    Column("valor", "Valor (R$)", "money", lambda i, c: i.get("amount")),
    # Tributacao exclusiva: o valor e o liquido (o que se declara); bruto e IR so conferem.
    Column("bruto", "Bruto (R$)", "money", lambda i, c: i.get("gross")),
    Column("ir_retido", "IR retido (R$)", "money", lambda i, c: i.get("withheld")),
]
