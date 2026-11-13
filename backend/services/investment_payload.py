"""Operacoes de investimento: os auxiliares das rotas que nao dependem do Flask.

Saiu de routes/investments.py (2026-11-13): nada aqui usa o Flask. A rota continua importando
todos estes nomes.
"""

import time
from concurrent.futures import ThreadPoolExecutor

from asset_classes import is_crypto_asset
from config import PRICE_FETCH_TIMEOUT_SECONDS
from dates import local_now, parse_iso_date
from db import get_db
from money import rounded_money
from services.corporate_actions import (
    action_factor,
    list_corporate_actions,
)
from services.fixed_income import (
    index_history,
)
from services.fx import (
    BASE_CURRENCY,
    SUPPORTED_CURRENCIES,
    normalize_currency,
)
from services.investments import (
    fetch_investment_rows,
    investment_fee_amount,
    investment_gross_amount,
    investment_movement_type,
    investment_transaction_date,
)
from services.prices import (
    ticker_key,
)
from validators import (
    ValidationError,
    optional_client_id,
)

# CDI/IPCA da evolucao e da rentabilidade: fora do executor do yfinance, que o
# historico ja ocupa. Dois: a rentabilidade busca o CDI da janela e o da renda
# fixa ao mesmo tempo.
_index_history_executor = ThreadPoolExecutor(max_workers=2)


# Moeda estrangeira: acoes/ETFs de fora e "outros" (cripto, conta no
# exterior). Renda fixa e FII sao em reais.
FOREIGN_CURRENCY_CLASSES = {"STOCKS", "OTHER"}


def read_movement_currency(item, asset_class):
    currency = normalize_currency(item.get("currency"))
    if currency not in SUPPORTED_CURRENCIES:
        raise ValidationError(f"Moeda nao suportada: {currency}. Use BRL, USD, EUR ou GBP.")
    if currency != BASE_CURRENCY and asset_class not in FOREIGN_CURRENCY_CLASSES:
        raise ValidationError("So acoes do exterior e 'outros' podem ser em moeda estrangeira.")
    if currency != BASE_CURRENCY and is_crypto_asset(asset_class, item.get("ticker_or_name")):
        # A cotacao (BTC-BRL) e o IR sao em reais: lance a operacao em reais.
        raise ValidationError("Bitcoin e lancado em reais.")
    return currency


def movement_export_item(investment):
    """Uma operacao como a tela Operacoes mostra: preco de venda/resgate na
    venda, bruto = quantidade x preco, custos, e o resultado realizado (custo medio)."""
    metadata = investment.get("metadata") or {}
    movement_type = investment_movement_type(investment.get("quantity"), metadata)
    quantity = abs(float(investment.get("quantity") or 0))
    if metadata.get("is_redemption"):
        unit_price = float(investment.get("current_price") or 0)
    elif movement_type == "SELL" and metadata.get("sale_price"):
        unit_price = float(metadata.get("sale_price") or 0)
    else:
        unit_price = float(investment.get("average_price") or 0)
    realized_fee = investment.get("realized_fee_amount")
    return {
        "date": investment_transaction_date(metadata, investment.get("created_at")),
        "movement_type": movement_type,
        "ticker": investment.get("ticker_or_name"),
        "asset_class": investment.get("asset_class"),
        "quantity": quantity,
        "unit_price": unit_price,
        "gross_amount": rounded_money(investment_gross_amount(quantity, unit_price)),
        "fees": realized_fee if realized_fee is not None else investment_fee_amount(metadata),
        "realized_cost_basis": investment.get("realized_cost_basis"),
        "realized_profit": investment.get("realized_profit"),
        "realized_tax_amount": investment.get("realized_tax_amount"),
        "realized_net_profit_after_tax": investment.get("realized_net_profit_after_tax"),
    }


def request_client_id(items):
    """O client_id do envio (042): uma lista e um envio so, entao todas as
    operacoes levam o mesmo id (ou nenhuma leva)."""
    ids = {optional_client_id(item) if isinstance(item, dict) else None for item in items}
    if len(ids) > 1:
        raise ValidationError("Todas as operacoes de um envio levam o mesmo client_id.")
    return ids.pop()


def movements_by_client_id(conn, current_user_id, client_id):
    """As operacoes que um envio com este client_id ja criou (042), na ordem do envio."""
    if not client_id:
        return []
    ids = conn.execute(
        """
        SELECT id FROM investment_transactions
        WHERE user_id = ? AND client_id = ?
        ORDER BY client_part
        """,
        (current_user_id, client_id),
    ).fetchall()
    return [fetch_investment_rows(conn, current_user_id, investment_id=row["id"])[0] for row in ids]


class AssetDeleteRefused(Exception):
    """Recusa no meio da exclusao: sai do `with` (rollback) levando a resposta."""

    def __init__(self, response):
        super().__init__("refused")
        self.response = response


def read_months_arg(args, default=12):
    """`?months=` do historico e da rentabilidade: de 1 a 60."""
    try:
        months_back = int(args.get("months", default))
    except (TypeError, ValueError):
        months_back = default
    return max(1, min(months_back, 60))


def months_since_first_movement(current_user_id, asset_class_filter=None, default=12):
    """Meses do mes da primeira operacao ate o atual (os dois inclusive), de 1 a 60."""
    query = """
        SELECT MIN(it.transaction_date) AS first_date
        FROM investment_transactions it
        JOIN assets a ON a.id = it.asset_id AND a.user_id = it.user_id
        WHERE it.user_id = ?
    """
    params = [current_user_id]
    if asset_class_filter:
        query += " AND a.asset_class = ?"
        params.append(asset_class_filter)
    with get_db() as conn:
        row = conn.execute(query, params).fetchone()
    first = parse_iso_date(row["first_date"]) if row else None
    if first is None:
        return default
    now = local_now()
    months = (now.year - first.year) * 12 + now.month - first.month + 1
    return max(1, min(months, 60))


def registered_split_events(current_user_id):
    """{ticker: [(data ex, fator)]} dos desdobramentos e grupamentos registrados."""
    with get_db() as conn:
        actions = list_corporate_actions(conn, current_user_id)
    events = {}
    for action in actions:
        if action.get("action_type") in ("SPLIT", "REVERSE_SPLIT"):
            events.setdefault(ticker_key(action.get("ticker")), []).append(
                (action.get("ex_date"), action_factor(action)),
            )
    return events


def start_index_history(start_date, need_ipca):
    """Comeca a buscar CDI (e IPCA) do BCB; `wait_index_history()` colhe.

    O prazo conta daqui: quem espera depois de outra busca nao ganha outro."""
    future = _index_history_executor.submit(index_history, start_date, need_ipca)
    return future, time.monotonic() + PRICE_FETCH_TIMEOUT_SECONDS


def read_report_year(args):
    try:
        year = int(args.get("year") or local_now().year - 1)
    except (TypeError, ValueError):
        raise ValidationError("Ano invalido.")
    if year < 2000 or year > local_now().year:
        raise ValidationError("Ano fora do intervalo.")
    return year
