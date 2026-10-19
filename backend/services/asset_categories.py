"""Categoria de cada ativo: a classe da carteira refinada para a tela.

A classe (`asset_class`) e o que o banco guarda e o que o IR, as metas e os
alvos de alocacao leem; o CHECK das migrations nao aceita uma classe nova sem
reconstruir `assets` (e as sete tabelas que caem em cascata com ela). A
categoria e calculada na leitura, nunca gravada:

- Acoes (STOCKS) se separa em ACAO, ETF e BDR pelo tipo do papel na B3
  (`market_listing.tax_kind`; o ETF de renda fixa e um ETF);
- Renda fixa (FIXED_INCOME) se separa em RENDA_FIXA e TESOURO (Tesouro
  Direto): o tipo do titulo `TESOURO` no metadata da aplicacao, ou, num titulo
  sem tipo, o nome comecando por "Tesouro";
- FII (REIT) e FII; Outros e CRIPTO (Bitcoin) ou OTHER.

A renda fixa ainda tem o indexador (`rate_kind`): PRE, POS (CDI, CDI+, Selic)
ou IPCA, que a alocacao por setor usa no lugar de "Sem setor".
"""

from asset_classes import is_crypto_asset
from db import parse_metadata_value
from services import market_listing

CATEGORY_LABELS = {
    "ACAO": "Ações",
    "ETF": "ETFs",
    "BDR": "BDRs",
    "FII": "FIIs",
    "RENDA_FIXA": "Renda fixa",
    "TESOURO": "Tesouro Direto",
    "CRIPTO": "Cripto",
    "OTHER": "Outros",
}

TREASURY_TYPE = "TESOURO"

RATE_KIND_LABELS = {
    "PRE": "Pré-fixado",
    "POS": "Pós-fixado",
    "IPCA": "IPCA+",
}

FIXED_INCOME_TYPE_LABELS = {
    "DEBENTURE": "Debênture",
    "DEBENTURE_INCENTIVADA": "Debênture incentivada",
    TREASURY_TYPE: "Tesouro Direto",
}


def normalized_name(value):
    return " ".join(str(value or "").upper().split())


def is_treasury_name(name):
    return normalized_name(name).startswith("TESOURO")


def asset_category(asset_class, ticker, fixed_income_type=None):
    """ACAO, ETF, BDR, FII, RENDA_FIXA, TESOURO, CRIPTO ou OTHER."""
    if asset_class == "REIT":
        return "FII"
    if asset_class == "STOCKS":
        kind = market_listing.tax_kind(ticker, asset_class)
        if kind in ("ETF", "ETF_RF"):
            return "ETF"
        return "BDR" if kind == "BDR" else "ACAO"
    if asset_class == "FIXED_INCOME":
        if fixed_income_type == TREASURY_TYPE:
            return "TESOURO"
        if not fixed_income_type and is_treasury_name(ticker):
            return "TESOURO"
        return "RENDA_FIXA"
    if is_crypto_asset(asset_class, ticker):
        return "CRIPTO"
    return "OTHER"


def treasury_rate_kind(name):
    """Indexador pelo nome do titulo do Tesouro, ou None."""
    text = normalized_name(name)
    if "SELIC" in text:
        return "POS"
    if "IPCA" in text or "RENDA+" in text or "EDUCA+" in text:
        return "IPCA"
    if "PREFIXADO" in text or "PRÉ-FIXADO" in text or "PRE-FIXADO" in text:
        return "PRE"
    return None


def rate_kind(metadata, name=None):
    """PRE, POS ou IPCA de um titulo de renda fixa, pelo metadata da aplicacao.

    Le as mesmas chaves de `fixed_income_rate_terms()`, mas nao exige a taxa: um
    titulo de preco manual com a remuneracao escolhida ainda tem indexador. Sem
    nada no metadata, um titulo do Tesouro se le pelo nome.
    """
    metadata = metadata or {}
    if metadata.get("rate_type") == "PRE":
        return "PRE"
    indexer = metadata.get("indexer")
    if indexer == "IPCA":
        return "IPCA"
    if indexer in ("CDI", "CDI_PLUS") or metadata.get("rate_type") == "POS" or metadata.get("cdi_percentage") not in (None, ""):
        return "POS"
    return treasury_rate_kind(name)


def fixed_income_type_label(value):
    if not value:
        return None
    return FIXED_INCOME_TYPE_LABELS.get(value, value)


def category_fields(asset_class, ticker, metadata=None):
    """Os campos de categoria de um ativo (ou posicao) para as respostas da API."""
    metadata = metadata or {}
    fixed_income_type = metadata.get("fixed_income_type") or None
    category = asset_category(asset_class, ticker, fixed_income_type)
    fields = {
        "category": category,
        "category_label": CATEGORY_LABELS[category],
    }
    if asset_class == "FIXED_INCOME":
        kind = rate_kind(metadata, ticker)
        fields["fixed_income_type"] = fixed_income_type
        fields["rate_kind"] = kind
        fields["rate_kind_label"] = RATE_KIND_LABELS.get(kind)
    return fields


def fixed_income_terms_by_asset(conn, current_user_id):
    """{asset_id: metadata da primeira aplicacao com tipo ou remuneracao}.

    O tipo e o indexador ficam no metadata de cada compra de renda fixa; o
    ativo le o da primeira que tenha algum deles (um resgate nao tem).
    """
    rows = conn.execute(
        """
        SELECT it.asset_id, it.metadata
        FROM investment_transactions it
        JOIN assets a ON a.id = it.asset_id AND a.user_id = it.user_id
        WHERE it.user_id = ? AND a.asset_class = 'FIXED_INCOME' AND it.quantity > 0
        ORDER BY it.transaction_date ASC, it.created_at ASC
        """,
        (current_user_id,),
    ).fetchall()
    terms = {}
    for row in rows:
        if row["asset_id"] in terms:
            continue
        metadata = parse_metadata_value(row["metadata"]) or {}
        if any(metadata.get(key) not in (None, "") for key in ("fixed_income_type", "rate_type", "indexer", "cdi_percentage")):
            terms[row["asset_id"]] = metadata
    return terms


def categories_by_asset(conn, current_user_id):
    """{asset_id: category_fields(...)} de todos os ativos do usuario."""
    rows = conn.execute(
        "SELECT id, asset_class, ticker FROM assets WHERE user_id = ?",
        (current_user_id,),
    ).fetchall()
    terms = fixed_income_terms_by_asset(conn, current_user_id)
    return {
        row["id"]: category_fields(row["asset_class"], row["ticker"], terms.get(row["id"]))
        for row in rows
    }
