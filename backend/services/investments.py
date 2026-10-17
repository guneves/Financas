"""Movimentacoes de investimento: ativos, leitura, validacao e o caixa ligado.

Uma movimentacao (compra, venda, resgate) e uma linha de
`investment_transactions`: quantidade negativa e venda, e o resgate de renda
fixa vem marcado no metadata (`is_redemption`). Ela so chega ao extrato quando
o dono pede, operacao por operacao: `metadata.cash_account_id` e a conta, e
entao existe exatamente um lancamento em `transactions` com
`source_type = INVESTMENT_CASH_SOURCE_TYPE` nessa conta
(`sync_investment_cash_transaction()`). Sem a chave nada e gravado: a carteira
nao mexe no saldo. `investment_cash_account_id()` e a regra e
`resolve_investment_cash_account()` valida a conta antes de gravar.
`validate_asset_transaction_backing()` recusa a mudanca que deixaria uma venda
ou resgate sem compra que a cubra.

Moeda (018): um ativo em moeda estrangeira guarda quantidade, precos e
cotacoes na moeda dele, e cada operacao o cambio da data em
`metadata.fx_rate`. `fetch_investments()` — o fluxo que o resultado realizado,
a carteira e a evolucao leem — entrega tudo convertido para reais (e com o
custo medio de cada venda, `apply_average_cost()`): custo pelo cambio de cada
compra, valor atual pelo cambio de hoje (a regra do IR para ativo no
exterior). O caixa ligado tambem sai em reais. As telas de operacao leem
`fetch_investment_rows()`, na moeda original.
"""

from datetime import datetime
import math

from asset_classes import ASSET_CLASS_LABELS, QUOTED_ASSET_CLASSES
from dates import parse_iso_date
from db import encode_metadata, get_db, new_id, parse_metadata_value, row_to_dict
import market_catalog
from money import rounded_money
from services.accounts import fetch_account
from services import market_listing
from services.fx import BASE_CURRENCY, FxUnavailable, normalize_currency, rate_on
from services.prices import ticker_key
from source_types import INVESTMENT_CASH_SOURCE_TYPE
from validators import ValidationError, safe_float


INVESTMENT_CASH_CATEGORY = "Investimento"
# Chave do metadata da movimentacao: a conta do lancamento ligado.
CASH_ACCOUNT_KEY = "cash_account_id"


def ensure_asset_owner(conn, current_user_id, asset_id):
    asset = conn.execute(
        """
        SELECT id, user_id, asset_class, ticker, name
        FROM assets
        WHERE id = ? AND user_id = ?
        """,
        (asset_id, current_user_id),
    ).fetchone()
    if not asset:
        raise ValidationError("Ativo nao encontrado.")
    return asset


def serialize_investment(row):
    item = row_to_dict(row)
    if item:
        item["metadata"] = parse_metadata_value(item.get("metadata"))
        if "current_quote_metadata" in item:
            item["current_quote_metadata"] = parse_metadata_value(item.get("current_quote_metadata"))
        if "realized_metadata" in item:
            item["realized_metadata"] = parse_metadata_value(item.get("realized_metadata"))
    return item


def investment_metadata_dict(value):
    return parse_metadata_value(value)


def investment_transaction_date(metadata, created_at=None):
    metadata = metadata or {}
    for key in ("redemption_date", "sale_date", "purchase_date"):
        parsed = parse_iso_date(metadata.get(key))
        if parsed:
            return parsed.strftime("%Y-%m-%d")

    parsed_created_at = parse_iso_date(created_at)
    if parsed_created_at:
        return parsed_created_at.strftime("%Y-%m-%d")
    return datetime.now().strftime("%Y-%m-%d")


def investment_movement_type(quantity, metadata):
    metadata = metadata or {}
    if metadata.get("is_redemption"):
        return "REDEMPTION"
    if safe_float(quantity) < 0:
        return "SELL"
    return "BUY"


def investment_fee_amount(metadata):
    return max(safe_float((metadata or {}).get("other_costs")), 0)


def investment_gross_amount(quantity, unit_price):
    return abs(safe_float(quantity) * safe_float(unit_price))


def investment_sale_price(investment, metadata):
    sale_price = safe_float((metadata or {}).get("sale_price"), None)
    if sale_price is not None and math.isfinite(sale_price) and sale_price > 0:
        return sale_price

    current_price = safe_float(investment.get("current_price"), None)
    if current_price is not None and math.isfinite(current_price) and current_price > 0:
        return current_price

    return safe_float(investment.get("average_price"))


def investment_cash_amount(investment):
    metadata = investment.get("metadata") or {}
    movement_type = investment.get("movement_type") or investment_movement_type(
        investment.get("quantity"),
        metadata,
    )
    quantity = safe_float(investment.get("quantity"))
    unit_price = safe_float(investment.get("average_price"))
    fees = investment_fee_amount(metadata)

    if movement_type == "BUY":
        amount = abs(quantity * unit_price)
    elif movement_type == "SELL":
        amount = (abs(quantity) * investment_sale_price(investment, metadata)) - fees
    elif movement_type == "REDEMPTION":
        amount = safe_float(investment.get("current_price"), abs(quantity * unit_price)) - fees
    else:
        return None

    if not math.isfinite(amount) or amount <= 0:
        return None
    return rounded_money(amount)


def investment_cash_type(investment):
    movement_type = investment.get("movement_type") or investment_movement_type(
        investment.get("quantity"),
        investment.get("metadata") or {},
    )
    if movement_type == "BUY":
        return "EXPENSE"
    if movement_type in {"SELL", "REDEMPTION"}:
        return "INCOME"
    return None


def investment_cash_description(investment):
    movement_type = investment.get("movement_type") or investment_movement_type(
        investment.get("quantity"),
        investment.get("metadata") or {},
    )
    ticker = ticker_key(investment.get("ticker_or_name"))
    labels = {
        "BUY": "Compra de investimento",
        "SELL": "Venda de investimento",
        "REDEMPTION": "Resgate de investimento",
    }
    return f"{labels.get(movement_type, 'Movimento de investimento')}: {ticker}"


def investment_cash_metadata(investment):
    return {
        "asset_id": investment.get("asset_id"),
        "asset_class": investment.get("asset_class"),
        "ticker": ticker_key(investment.get("ticker_or_name")),
        "movement_type": investment.get("movement_type"),
    }


def investment_cash_account_id(metadata):
    """A conta do lancamento ligado, ou None quando a operacao fica fora do extrato."""
    value = (metadata or {}).get(CASH_ACCOUNT_KEY)
    if not isinstance(value, str):
        return None
    return value.strip() or None


def resolve_investment_cash_account(conn, current_user_id, metadata, previous_account_id=None):
    """Valida `metadata.cash_account_id` e devolve o id (None = fora do extrato).

    A conta tem que ser do usuario, em reais (o lancamento ligado e sempre em
    reais) e ativa — a nao ser que ja fosse a conta da operacao
    (`previous_account_id`): arquivar a conta depois nao trava a edicao.
    """
    value = (metadata or {}).get(CASH_ACCOUNT_KEY)
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise ValidationError("Conta do extrato invalida.")
    account_id = value.strip()
    account = fetch_account(conn, current_user_id, account_id)
    if not account:
        raise ValidationError("Conta do extrato nao encontrada.")
    if account["archived_at"] and account_id != previous_account_id:
        raise ValidationError("Conta do extrato esta arquivada.")
    if normalize_currency(account["currency"]) != BASE_CURRENCY:
        raise ValidationError("O lancamento no extrato e em reais: escolha uma conta em reais.")
    return account_id


def with_investment_cash_account(metadata, account_id):
    """O metadata com a conta ja validada, ou sem a chave quando nao ha conta."""
    cleaned = {key: value for key, value in (metadata or {}).items() if key != CASH_ACCOUNT_KEY}
    if account_id:
        cleaned[CASH_ACCOUNT_KEY] = account_id
    return cleaned


def investment_cash_receipt_count(conn, current_user_id, investment_id):
    """Comprovantes presos ao lancamento ligado: tirar a operacao do extrato os apagaria."""
    row = conn.execute(
        """
        SELECT COUNT(*) AS total
        FROM transaction_attachments ta
        JOIN transactions t
          ON t.id = ta.transaction_id
         AND t.user_id = ta.user_id
        WHERE ta.user_id = ?
          AND t.source_type = ?
          AND t.source_id = ?
        """,
        (current_user_id, INVESTMENT_CASH_SOURCE_TYPE, investment_id),
    ).fetchone()
    return row["total"] if row else 0


def sync_investment_cash_transaction(conn, current_user_id, investment):
    """Deixa o lancamento ligado igual a movimentacao.

    Devolve True quando a operacao ficou com lancamento no extrato. Quem grava
    recusa a operacao que pede o extrato e nao tem valor a lancar (False com a
    conta no metadata), para a chave nunca dizer "no extrato" sem linha la.
    """
    # Fora do extrato: sem lancamento (e sem buscar cambio para ele).
    account_id = investment_cash_account_id(investment.get("metadata"))
    if not account_id:
        if investment.get("id"):
            delete_investment_cash_transaction(conn, current_user_id, investment["id"])
        return False
    # O caixa e em reais: operacao em moeda estrangeira converte pelo cambio dela.
    if normalize_currency(investment.get("asset_currency")) != BASE_CURRENCY:
        rate = movement_fx_rate(conn, current_user_id, investment)
        investment = convert_movement_to_brl(investment, rate, rate)
    amount = investment_cash_amount(investment)
    cash_type = investment_cash_type(investment)
    investment_id = investment.get("id")
    if not investment_id:
        return False

    if amount is None or cash_type is None:
        conn.execute(
            """
            DELETE FROM transactions
            WHERE user_id = ? AND source_type = ? AND source_id = ?
            """,
            (current_user_id, INVESTMENT_CASH_SOURCE_TYPE, investment_id),
        )
        return False

    transaction_date = investment.get("transaction_date") or investment_transaction_date(
        investment.get("metadata") or {},
        investment.get("created_at"),
    )
    description = investment_cash_description(investment)
    metadata = investment_cash_metadata(investment)

    existing = conn.execute(
        """
        SELECT id FROM transactions
        WHERE user_id = ? AND source_type = ? AND source_id = ?
        """,
        (current_user_id, INVESTMENT_CASH_SOURCE_TYPE, investment_id),
    ).fetchone()

    if existing:
        # A conta tambem: trocar a conta move o mesmo lancamento.
        conn.execute(
            """
            UPDATE transactions
            SET account_id = ?,
                amount = ?,
                date = ?,
                category = ?,
                description = ?,
                type = ?,
                metadata = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                account_id,
                amount,
                transaction_date,
                INVESTMENT_CASH_CATEGORY,
                description,
                cash_type,
                encode_metadata(metadata),
                existing["id"],
                current_user_id,
            ),
        )
        return True

    conn.execute(
        """
        INSERT INTO transactions
        (id, user_id, account_id, amount, date, category, description, type, source_type, source_id, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"cash:{investment_id}",
            current_user_id,
            account_id,
            amount,
            transaction_date,
            INVESTMENT_CASH_CATEGORY,
            description,
            cash_type,
            INVESTMENT_CASH_SOURCE_TYPE,
            investment_id,
            encode_metadata(metadata),
        ),
    )
    return True


def delete_investment_cash_transaction(conn, current_user_id, investment_id):
    conn.execute(
        """
        DELETE FROM transactions
        WHERE user_id = ? AND source_type = ? AND source_id = ?
        """,
        (current_user_id, INVESTMENT_CASH_SOURCE_TYPE, investment_id),
    )


def investment_gross_proceeds(investment, metadata):
    movement_type = investment.get("movement_type") or investment_movement_type(
        investment.get("quantity"),
        metadata,
    )
    quantity = abs(safe_float(investment.get("quantity")))
    if movement_type == "SELL":
        return quantity * investment_sale_price(investment, metadata)
    if movement_type == "REDEMPTION":
        return safe_float(
            investment.get("current_price"),
            abs(quantity * safe_float(investment.get("average_price"))),
        )
    return 0


def investment_operation_date(investment):
    return investment_transaction_date(
        investment.get("metadata") or {},
        investment.get("transaction_date") or investment.get("created_at"),
    )


def get_or_create_asset(conn, current_user_id, asset_class, ticker_or_name, currency=BASE_CURRENCY):
    ticker = ticker_key(ticker_or_name)
    currency = normalize_currency(currency)
    row = conn.execute(
        """
        SELECT id, currency FROM assets
        WHERE user_id = ? AND asset_class = ? AND ticker = ?
        """,
        (current_user_id, asset_class, ticker),
    ).fetchone()
    if row:
        if normalize_currency(row["currency"]) != currency:
            raise ValidationError(
                f"{ticker} ja esta na carteira em {normalize_currency(row['currency'])}; "
                "lance a operacao na mesma moeda."
            )
        return row["id"]

    asset_id = new_id()
    conn.execute(
        """
        INSERT INTO assets
        (id, user_id, asset_class, ticker, name, currency)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (asset_id, current_user_id, asset_class, ticker, ticker or ticker_or_name, currency),
    )
    return asset_id


def movement_fx_rate(conn, current_user_id, investment, fallback=None):
    """Cambio da operacao: o informado (metadata.fx_rate) ou a PTAX da data."""
    currency = normalize_currency(investment.get("asset_currency"))
    if currency == BASE_CURRENCY:
        return 1.0
    stored = safe_float((investment.get("metadata") or {}).get("fx_rate"), None)
    if stored and stored > 0:
        return stored
    try:
        return rate_on(conn, current_user_id, currency, investment_operation_date(investment))
    except FxUnavailable:
        if fallback:
            return fallback
        raise


def convert_movement_to_brl(investment, movement_rate, today_rate):
    """A mesma operacao em reais. Os valores originais ficam em native_*."""
    item = dict(investment)
    metadata = dict(item.get("metadata") or {})
    item["native_currency"] = normalize_currency(item.get("asset_currency"))
    item["native_average_price"] = item.get("average_price")
    item["native_current_price"] = item.get("current_price")
    item["fx_rate"] = movement_rate
    item["fx_rate_today"] = today_rate
    item["average_price"] = safe_float(item.get("average_price")) * movement_rate
    if item.get("current_price") is not None:
        # No resgate o "preco atual" e o valor resgatado: cambio da data dele.
        rate = movement_rate if metadata.get("is_redemption") else today_rate
        item["current_price"] = safe_float(item.get("current_price")) * rate
    for key in ("gross_amount", "fee_amount"):
        if item.get(key) is not None:
            item[key] = safe_float(item.get(key)) * movement_rate
    for key in ("sale_price", "other_costs", "fee_amount"):
        if metadata.get(key) not in (None, ""):
            metadata[key] = safe_float(metadata.get(key)) * movement_rate
    item["metadata"] = metadata
    return item


def investments_in_brl(conn, current_user_id, investments):
    """Converte a lista inteira; um cambio de hoje por moeda."""
    today_rates = {}
    converted = []
    for investment in investments:
        currency = normalize_currency(investment.get("asset_currency"))
        if currency == BASE_CURRENCY:
            converted.append(investment)
            continue
        if currency not in today_rates:
            try:
                today_rates[currency] = rate_on(conn, current_user_id, currency)
            except FxUnavailable:
                today_rates[currency] = None
        movement_rate = movement_fx_rate(conn, current_user_id, investment, fallback=today_rates[currency])
        today_rate = today_rates[currency] or movement_rate
        converted.append(convert_movement_to_brl(investment, movement_rate, today_rate))
    return converted


def apply_average_cost(investments):
    """Custo medio ponderado, a regra da Receita para acoes, FIIs, ETFs e BDRs
    (Lei 8.981/1995, art. 72, par. 2o; IN RFB 1.585/2015, art. 58).

    Anota cada operacao (a lista e alterada e devolvida, na mesma ordem):

    - `cost_amount`: quanto o custo da posicao muda. Compra: + quantidade x
      preco (o preco da compra ja traz os custos dela). Venda: - quantidade x o
      custo medio daquele momento — vender nao muda o custo medio do que fica;
    - `average_cost`: na venda, esse custo medio por cota.

    O preco gravado na linha da venda (o que a tela ou a API mandou: o preco
    medio da hora ou o proprio preco de venda) nao entra na conta. Assim a
    Posicao, a evolucao, o resultado realizado e Bens e Direitos partem do mesmo
    custo, e editar uma compra antiga corrige as vendas seguintes.

    Renda fixa segue por titulo: `cost_amount` e quantidade x preco, como gravado.
    """
    state = {}
    for investment in sorted(investments, key=movement_sort_key):
        quantity = safe_float(investment.get("quantity"))
        unit_price = safe_float(investment.get("average_price"))
        if investment.get("asset_class") == "FIXED_INCOME" or not investment.get("asset_id"):
            investment["cost_amount"] = quantity * unit_price
            continue
        position = state.setdefault(str(investment["asset_id"]), {"quantity": 0.0, "cost": 0.0})
        if quantity > 0:
            position["quantity"] += quantity
            position["cost"] += quantity * unit_price
            investment["cost_amount"] = quantity * unit_price
            continue
        sold = abs(quantity)
        held = position["quantity"]
        # Venda sem compra antes (nao deveria existir: a validacao recusa) fica
        # com o preco gravado na propria linha.
        average = position["cost"] / held if held > 0.000001 else unit_price
        investment["average_cost"] = average
        investment["cost_amount"] = -sold * average
        position["quantity"] = held - sold
        position["cost"] -= sold * average
        if position["quantity"] <= 0.000001:
            position["quantity"] = 0.0
            position["cost"] = 0.0
    return investments


def fetch_investment_rows(conn, current_user_id, *, investment_id=None, order_by="it.created_at", direction="ASC"):
    query = """
        SELECT
            it.id,
            it.user_id,
            it.asset_id,
            a.asset_class,
            a.ticker AS ticker_or_name,
            a.currency AS asset_currency,
            it.quantity,
            it.unit_price AS average_price,
            COALESCE(
                (
                    SELECT pq.price
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id = it.id
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                ),
                (
                    SELECT pq.price
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id IS NULL
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                ),
                it.unit_price
            ) AS current_price,
            COALESCE(
                (
                    SELECT pq.id
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id = it.id
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                ),
                (
                    SELECT pq.id
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id IS NULL
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                )
            ) AS current_quote_id,
            COALESCE(
                (
                    SELECT pq.quoted_at
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id = it.id
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                ),
                (
                    SELECT pq.quoted_at
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id IS NULL
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                )
            ) AS current_quote_quoted_at,
            COALESCE(
                (
                    SELECT pq.source
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id = it.id
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                ),
                (
                    SELECT pq.source
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id IS NULL
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                )
            ) AS current_quote_source,
            COALESCE(
                (
                    SELECT pq.metadata
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id = it.id
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                ),
                (
                    SELECT pq.metadata
                    FROM price_quotes pq
                    WHERE pq.user_id = it.user_id
                      AND pq.asset_id = it.asset_id
                      AND pq.transaction_id IS NULL
                    ORDER BY pq.quoted_at DESC, pq.created_at DESC
                    LIMIT 1
                )
            ) AS current_quote_metadata,
            it.metadata,
            it.movement_type,
            it.gross_amount,
            it.fee_amount,
            it.transaction_date,
            it.created_at,
            it.updated_at,
            rr.quantity AS realized_quantity,
            rr.average_cost AS realized_average_cost,
            rr.gross_proceeds AS realized_gross_proceeds,
            rr.fee_amount AS realized_fee_amount,
            rr.net_proceeds AS realized_net_proceeds,
            rr.net_unit_price AS realized_net_unit_price,
            rr.cost_basis AS realized_cost_basis,
            rr.realized_profit,
            rr.profitability_percent AS realized_profitability_percent,
            rr.tax_rate AS realized_tax_rate,
            rr.tax_amount AS realized_tax_amount,
            rr.net_profit_after_tax AS realized_net_profit_after_tax,
            rr.operation_date AS realized_operation_date,
            rr.metadata AS realized_metadata
        FROM investment_transactions it
        JOIN assets a ON a.id = it.asset_id
        LEFT JOIN investment_realized_results rr
          ON rr.user_id = it.user_id
         AND rr.source_transaction_id = it.id
        WHERE it.user_id = ?
    """
    params = [current_user_id]
    if investment_id:
        query += " AND it.id = ?"
        params.append(investment_id)
    query += f" ORDER BY {order_by} {direction}"
    return conn.execute(query, params).fetchall()


def fetch_investments(current_user_id, investment_id=None):
    """As operacoes em reais (ver o topo do modulo), com o custo medio de cada
    venda (`apply_average_cost`): o que os calculos leem. O custo depende de
    todas as operacoes do ativo, entao uma so (`investment_id`) sai da lista inteira."""
    with get_db() as conn:
        rows = fetch_investment_rows(
            conn,
            current_user_id,
            order_by="it.created_at",
            direction="ASC",
        )
        investments = apply_average_cost(
            investments_in_brl(conn, current_user_id, [serialize_investment(row) for row in rows])
        )
    if investment_id:
        return [item for item in investments if str(item.get("id")) == str(investment_id)]
    return investments


def fetch_position_quantity(conn, current_user_id, asset_class, ticker, exclude_id=None):
    query = """
        SELECT COALESCE(SUM(quantity), 0) AS quantity
        FROM investment_transactions it
        JOIN assets a ON a.id = it.asset_id
        WHERE it.user_id = ?
          AND a.asset_class = ?
          AND a.ticker = ?
    """
    params = [current_user_id, asset_class, ticker_key(ticker)]
    if exclude_id:
        query += " AND it.id <> ?"
        params.append(exclude_id)
    row = conn.execute(query, params).fetchone()
    return safe_float(row["quantity"] if row else 0)


def resolve_catalog_ticker(conn, current_user_id, asset_class, ticker_or_name, quantity):
    """Garante que uma compra de renda variavel use um papel conhecido.

    Devolve sempre o ticker canonico das classes com cotacao (maiusculas, sem o
    sufixo .SA), inclusive nas vendas -- e a normalizacao das duas pontas que
    faz a venda encontrar a posicao criada pela compra. Vendas e resgates nao
    consultam o catalogo (eles se apoiam numa posicao que ja existe) e classes
    sem cotacao (renda fixa, outros) continuam com texto livre, porque ali
    o "ticker" e so o nome que o dono deu ao ativo.

    Posicoes antigas, anteriores ao catalogo, continuam aceitas: se o ativo ja
    existe na carteira do usuario, o lancamento passa mesmo fora da lista.
    """
    ticker = market_catalog.normalize_ticker(ticker_or_name)
    if asset_class not in QUOTED_ASSET_CLASSES:
        # Renda fixa e outros: o "ticker" e so o nome do ativo, texto livre.
        return ticker_key(ticker_or_name)
    if quantity <= 0:
        # Venda/resgate nao consulta o catalogo, mas usa a mesma normalizacao da
        # compra -- senao "PETR4.SA" nao acha a posicao gravada como "PETR4".
        return ticker

    if not ticker:
        raise ValidationError("Informe o ativo do lancamento.")

    entry = market_listing.lookup(ticker)
    if entry is None:
        # O ticker gravado pode ser o normalizado ou, num ativo antigo, o texto
        # original com sufixo.
        existing = conn.execute(
            """
            SELECT ticker FROM assets
            WHERE user_id = ? AND asset_class = ? AND ticker IN (?, ?)
            """,
            (current_user_id, asset_class, ticker, ticker_key(ticker_or_name)),
        ).fetchone()
        if existing:
            return existing["ticker"]
        raise ValidationError(
            f"Ativo {ticker} nao encontrado na lista da B3. Selecione um papel pela busca."
        )

    if entry["asset_class"] != asset_class:
        expected = ASSET_CLASS_LABELS.get(entry["asset_class"], entry["asset_class"])
        raise ValidationError(
            f"{ticker} e um ativo do tipo {entry['kind_label']}. Selecione o tipo {expected}."
        )

    return entry["ticker"]


def validate_investment_movement(conn, current_user_id, asset_class, ticker_or_name, quantity):
    if quantity >= 0 or asset_class == "FIXED_INCOME":
        return

    available_quantity = fetch_position_quantity(
        conn,
        current_user_id,
        asset_class,
        ticker_or_name,
    )
    if abs(quantity) - available_quantity > 0.000001:
        raise ValidationError("Venda maior que a quantidade disponivel na carteira.")


def movement_sort_key(investment):
    return (
        investment_operation_date(investment),
        str(investment.get("created_at") or ""),
        str(investment.get("id") or ""),
    )


def fetch_asset_transactions_for_backing(conn, current_user_id, asset_id):
    rows = conn.execute(
        """
        SELECT
            it.id,
            it.user_id,
            it.asset_id,
            asset.asset_class,
            asset.ticker AS ticker_or_name,
            it.quantity,
            it.unit_price AS average_price,
            it.gross_amount,
            it.fee_amount,
            it.movement_type,
            it.transaction_date,
            it.metadata,
            it.created_at,
            it.updated_at
        FROM investment_transactions it
        JOIN assets asset ON asset.id = it.asset_id
        WHERE it.user_id = ?
          AND it.asset_id = ?
        """,
        (current_user_id, asset_id),
    ).fetchall()
    return [serialize_investment(row) for row in rows]


def validate_asset_transaction_backing(
    conn,
    current_user_id,
    asset_id,
    *,
    exclude_ids=None,
    replacements=None,
):
    excluded = {str(item_id) for item_id in (exclude_ids or set())}
    transactions = [
        item
        for item in fetch_asset_transactions_for_backing(conn, current_user_id, asset_id)
        if str(item.get("id")) not in excluded
    ]
    transactions.extend(replacements or [])
    transactions = sorted(transactions, key=movement_sort_key)
    remaining_ids = {str(item.get("id")) for item in transactions if item.get("id")}

    for item in transactions:
        metadata = item.get("metadata") or {}
        related_id = metadata.get("related_id")
        if metadata.get("is_redemption") and related_id and str(related_id) not in remaining_ids:
            raise ValidationError(
                "Nao e possivel alterar ou excluir essa compra: ela possui resgate vinculado."
            )

    balance_by_asset = {}
    for item in transactions:
        asset_class = item.get("asset_class")
        if asset_class == "FIXED_INCOME":
            continue

        quantity = safe_float(item.get("quantity"))
        if quantity == 0:
            continue

        key = item.get("asset_id") or asset_id
        next_balance = balance_by_asset.get(key, 0) + quantity
        if next_balance < -0.000001:
            ticker = ticker_key(item.get("ticker_or_name"))
            raise ValidationError(
                f"Nao e possivel alterar ou excluir essa movimentacao: {ticker} ficaria com venda sem lastro de compra anterior."
            )
        balance_by_asset[key] = next_balance
