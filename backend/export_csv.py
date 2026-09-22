"""Geracao dos CSV de exportacao (extrato e carteira).

Funcoes puras, sem banco e sem Flask — a mesma forma de statement_import.py:
o modulo monta o texto, a rota busca os dados e devolve a resposta.

O arquivo sai no formato que o Excel em pt-BR abre com um duplo clique:
BOM UTF-8, ponto e virgula como separador e numero com virgula decimal.
"""

import io
import csv


CSV_DELIMITER = ";"
BOM = "﻿"

TRANSACTION_TYPE_LABELS = {
    "INCOME": "Receita",
    "EXPENSE": "Despesa",
    "TRANSFER": "Transferencia",
}

SOURCE_LABELS = {
    "INVESTMENT_TRANSACTION": "Carteira",
    "CC_INVOICE_PAYMENT": "Fatura do cartao",
    "CC_AUTOPAY": "Debito automatico",
    "RECURRING_TRANSACTION": "Recorrencia",
    "STATEMENT_IMPORT": "Importacao de extrato",
}

ASSET_CLASS_LABELS = {
    "STOCKS": "Acoes",
    "FIXED_INCOME": "Renda Fixa",
    "REIT": "Fundos Imobiliarios",
    "CATTLE": "Gado",
    "OTHER": "Outros",
}

TRANSACTIONS_HEADER = [
    "Data",
    "Tipo",
    "Descricao",
    "Categoria",
    "Conta",
    "Conta destino",
    "Valor",
    "Valor com sinal",
    "Origem",
]

PORTFOLIO_HEADER = [
    "Ativo",
    "Classe",
    "Quantidade",
    "Preco medio",
    "Preco atual",
    "Valor investido",
    "Valor bruto",
    "IR estimado",
    "Valor liquido",
    "Rentabilidade (%)",
    "Isento de IR",
    "Cotacao de",
]


def format_decimal(value, places=2):
    """Numero no formato pt-BR (1234.5 -> "1234,50"), sem separador de milhar.

    Sem separador de milhar de proposito: o Excel le a celula como numero em
    qualquer configuracao de milhar, e quem abre no Google Sheets tambem.
    """
    if value is None or value == "":
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{number:.{places}f}".replace(".", ",")


def signed_amount(amount, transaction_type):
    """Valor com sinal de efeito no caixa.

    TRANSFER fica vazio: a transferencia sai de uma conta e entra em outra na
    mesma linha, entao somar a coluna daria uma despesa que nao existe. E a
    mesma regra que o saldo consolidado usa.
    """
    if transaction_type == "TRANSFER":
        return ""
    try:
        number = float(amount or 0)
    except (TypeError, ValueError):
        return ""
    return format_decimal(-number if transaction_type == "EXPENSE" else number)


def build_csv(header, rows):
    """Monta o texto do CSV com BOM, ";" e quebra de linha \r\n."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=CSV_DELIMITER, lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(["" if cell is None else cell for cell in row])
    return BOM + buffer.getvalue()


def source_label(source_type):
    """Quem criou o lancamento. Sem source_type e digitacao manual."""
    if not source_type:
        return "Manual"
    return SOURCE_LABELS.get(source_type, source_type)


def transaction_row(transaction, account_names=None):
    account_names = account_names or {}
    transaction_type = transaction.get("type")
    return [
        transaction.get("date") or "",
        TRANSACTION_TYPE_LABELS.get(transaction_type, transaction_type or ""),
        transaction.get("description") or "",
        transaction.get("category") or "",
        account_names.get(transaction.get("account_id"), ""),
        account_names.get(transaction.get("transfer_account_id"), ""),
        format_decimal(transaction.get("amount")),
        signed_amount(transaction.get("amount"), transaction_type),
        source_label(transaction.get("source_type")),
    ]


def transactions_csv(transactions, account_names=None):
    rows = [transaction_row(item, account_names) for item in transactions]
    return build_csv(TRANSACTIONS_HEADER, rows)


def portfolio_row(asset):
    quantity = asset.get("quantity")
    average_price = asset.get("average_price")
    try:
        invested = float(quantity or 0) * float(average_price or 0)
    except (TypeError, ValueError):
        invested = 0
    quote = asset.get("quote") or {}
    asset_class = asset.get("class")
    return [
        asset.get("ticker") or "",
        ASSET_CLASS_LABELS.get(asset_class, asset_class or ""),
        format_decimal(quantity, 6),
        format_decimal(average_price),
        format_decimal(asset.get("current_price")),
        format_decimal(invested),
        format_decimal(asset.get("current_value")),
        format_decimal(asset.get("taxes")),
        format_decimal(asset.get("net_value")),
        format_decimal(asset.get("profitability_percent")),
        "Sim" if asset.get("is_tax_free") else "Nao",
        (quote.get("quoted_at") or "")[:10],
    ]


def portfolio_csv(assets):
    rows = [portfolio_row(asset) for asset in assets or []]
    return build_csv(PORTFOLIO_HEADER, rows)
