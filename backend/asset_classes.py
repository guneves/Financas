"""Classes de ativo da carteira e o filtro por classe.

`QUOTED_ASSET_CLASSES` sao as que tem cotacao de mercado (yfinance/brapi).
Criptoativos (`CRYPTO_ASSETS`, hoje so o Bitcoin) ficam na classe "Outros" --
o CHECK das migrations nao aceita uma classe nova sem reconstruir `assets` --,
mas tem cotacao automatica em reais: `is_quoted_asset()` e a regra.
`CATTLE` (gado) foi removida em 2026-09-27: o banco ainda aceita o valor (CHECK
das migrations), mas a API recusa — ver docs/done-tasks.md.
"""


ALLOWED_ASSET_CLASSES = {"STOCKS", "FIXED_INCOME", "REIT", "OTHER"}

QUOTED_ASSET_CLASSES = {"STOCKS", "REIT"}
ASSET_CLASS_LABELS = {
    "STOCKS": "Acoes",
    "REIT": "Fundos Imobiliarios",
    "FIXED_INCOME": "Renda Fixa",
    "OTHER": "Outros",
}


# Ticker canonico -> nome e simbolo no Yahoo (cotado direto em reais).
CRYPTO_ASSETS = {
    "BTC": {"name": "Bitcoin", "yahoo_symbol": "BTC-BRL"},
}
CRYPTO_ALIASES = {"BITCOIN": "BTC", "BTC-BRL": "BTC", "XBT": "BTC"}


def crypto_ticker(ticker_or_name):
    """'bitcoin', 'BTC', 'BTC-BRL' -> 'BTC'; None se nao for criptoativo conhecido."""
    symbol = str(ticker_or_name or "").strip().upper()
    symbol = CRYPTO_ALIASES.get(symbol, symbol)
    return symbol if symbol in CRYPTO_ASSETS else None


def is_crypto_asset(asset_class, ticker_or_name):
    return asset_class == "OTHER" and crypto_ticker(ticker_or_name) is not None


def is_quoted_asset(asset_class, ticker_or_name):
    """Tem cotacao de mercado: acao/FII, ou criptoativo conhecido em "Outros"."""
    return asset_class in QUOTED_ASSET_CLASSES or is_crypto_asset(asset_class, ticker_or_name)


def parse_asset_class_filter(value):
    normalized = str(value or "").strip().upper()
    if normalized in {"", "TODOS", "ALL"}:
        return None
    return normalized if normalized in ALLOWED_ASSET_CLASSES else None
