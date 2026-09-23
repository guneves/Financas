"""Classes de ativo da carteira e o filtro por classe.

`QUOTED_ASSET_CLASSES` sao as que tem cotacao de mercado (yfinance/brapi);
`CATTLE` e uma classe viva — ver docs/done-tasks.md antes de mexer nela.
"""


ALLOWED_ASSET_CLASSES = {"STOCKS", "FIXED_INCOME", "REIT", "CATTLE", "OTHER"}

QUOTED_ASSET_CLASSES = {"STOCKS", "REIT"}
ASSET_CLASS_LABELS = {
    "STOCKS": "Acoes",
    "REIT": "Fundos Imobiliarios",
    "FIXED_INCOME": "Renda Fixa",
    "CATTLE": "Gado",
    "OTHER": "Outros",
}


def parse_asset_class_filter(value):
    normalized = str(value or "").strip().upper()
    if normalized in {"", "TODOS", "ALL"}:
        return None
    return normalized if normalized in ALLOWED_ASSET_CLASSES else None
