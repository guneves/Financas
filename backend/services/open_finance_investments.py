"""BTG Investimentos na carteira, pelo Open Finance (044, dono 2026-10-27).

No mesmo pull das contas (so GET): `GET /investments?itemId=` da as posicoes
da corretora e `GET /investments/{id}/transactions` as operacoes de cada uma.

- **Operacoes, nunca posicoes**: o custo medio, o resultado realizado e o DARF
  saem das operacoes (CLAUDE.md › Investments); a posicao da Pluggy so confere.
- Grava sozinho a COMPRA e a VENDA de renda variavel (`EQUITY`: acoes, ETFs,
  FIIs), na data do pregao (`tradeDate`), com o preco unitario e os custos
  (`expenses`), o caixa pela Corretora (`metadata.cash_account_id`) — o
  mesmo caminho de uma operacao digitada. A classe e a do ativo que o dono ja
  tem com esse ticker, senao a do catalogo da B3; sem nenhuma, a operacao
  espera (HELD `unknown_asset`).
- **Idempotente** pela chave da operacao (`id` da Pluggy, ou investimento +
  pregao + tipo + quantidade + valor), unica por usuario.
- **Nunca duplica o digitado**: a mesma operacao ja lancada (mesmo ativo,
  mesma quantidade com sinal, pregao a ate LINK_DAYS dias) e LIGADA. A corretora
  soma as ordens do dia (AUPO11 -12) onde o dono digitou cada uma (-3 e -9): as
  digitadas que somam a operacao tambem sao ligadas (`_summed_twins()`), a
  primeira na linha da operacao e cada outra numa linha `<op_key>#part:<id>` de
  quantidade 0, que so a tira de um proximo vinculo.
- **Evento corporativo (017)**: uma operacao antes do ultimo evento do ativo
  nao entra (HELD `corporate_action`); nem uma venda maior que a posicao.
- Renda fixa, Tesouro, fundos, TRANSFER (custodia) e INTEREST (cupom) esperam
  (HELD `type`): aparecem na conferencia para o dono lancar. Gravar um titulo
  pede o que a operacao nao traz: indexador e taxa contratada
  (`validate_fixed_income_metadata()`; um palpite errado marca a carteira errada
  sem aviso), o tipo do titulo (define IR e categoria) e, no resgate, a compra
  exata que ele baixa (`related_id`, o IR de cada lote). O cupom e um provento
  tributado desde a primeira compra do titulo, que nao esta aqui. Os proventos de
  acoes/FIIs ja sao calculados (026); o dinheiro deles na conta da corretora e
  COVERED (services/open_finance_inbox.py), nunca um segundo provento.
- **Desfazer**: apagar a operacao no Extrato. A linha daqui fica DISMISSED e
  nunca volta.
- **Liquidacao** (049): o lancamento de cada operacao fica na data da
  liquidacao (`services/settlement.py`), com o valor liquidado da Pluggy
  (`netAmount`); o caixa se compara so com o que liquidou ate o dia do saldo
  da Pluggy (`cash_check()`), o resto esta em transito (`broker_cash.py`).
"""

from datetime import timedelta
from itertools import combinations

import market_catalog
import pluggy_client
from asset_classes import QUOTED_ASSET_CLASSES
from dates import parse_iso_date
from db import encode_metadata, new_id, utc_timestamp
from money import rounded_money
from services import invoices
from services.broker_cash import broker_settlement
from services.corporate_actions import ensure_outside_corporate_actions
from services.investments import (
    CASH_ACCOUNT_KEY,
    fetch_investment_rows,
    get_or_create_asset,
    investment_fee_amount,
    investment_gross_amount,
    investment_movement_type,
    portfolio_cash_account_id,
    serialize_investment,
    sync_investment_cash_transaction,
    validate_asset_transaction_backing,
    validate_investment_movement,
)
from services.prices import ticker_key
from services.settlement import SETTLEMENT_AMOUNT_KEY
from validators import ValidationError, safe_float

OP_KEY_PREFIX = "pluggy-inv:"
LINK_DAYS = 2
RECORDED_TYPES = {"BUY", "SELL"}
EQUITY_TYPES = {"EQUITY", "ETF"}
QUANTITY_TOLERANCE = 0.000001
# Ordens do mesmo ativo em LINK_DAYS dias que entram na busca por uma soma.
MAX_SUMMED_ROWS = 14
PART_KEY = "#part:"


# ---------------------------------------------------------------------------
# Ler a Pluggy (fora da transacao do banco)
# ---------------------------------------------------------------------------

def fetch(api, pluggy_item_id, logger):
    """{positions, operations: [(posicao, operacao)]} do item, ou None se a
    Pluggy recusou (o resto do pull segue; nada da carteira muda)."""
    if not hasattr(api, "list_investments"):
        return None
    try:
        positions = list(api.list_investments(pluggy_item_id) or [])
        operations = []
        for position in positions:
            if not isinstance(position, dict) or not position.get("id"):
                continue
            for raw in api.list_investment_transactions(position["id"]) or []:
                if isinstance(raw, dict):
                    operations.append((position, raw))
    except pluggy_client.PluggyError as exc:
        logger.warning(
            "Open Finance: investimentos recusados", extra={"status": exc.status, "error": str(exc)[:300]},
        )
        return None
    return {"positions": positions, "operations": operations}


# ---------------------------------------------------------------------------
# Puro: uma operacao da Pluggy
# ---------------------------------------------------------------------------

def _day(value):
    text = str(value or "")[:10]
    return text if parse_iso_date(text) else None


def expenses_total(value):
    """`expenses` e um numero ou um objeto de taxas (corretagem, emolumentos,
    IR na fonte...): a soma, nunca negativa."""
    if isinstance(value, dict):
        total = sum(safe_float(item) for item in value.values() if isinstance(item, (int, float)))
    else:
        total = safe_float(value)
    return rounded_money(max(total, 0))


def op_key(position, raw):
    if raw.get("id"):
        return OP_KEY_PREFIX + str(raw["id"])
    parts = [
        position.get("id"), _day(raw.get("tradeDate") or raw.get("date")), str(raw.get("type") or "").upper(),
        safe_float(raw.get("quantity")), safe_float(raw.get("amount")),
    ]
    return OP_KEY_PREFIX + ":".join(str(part) for part in parts)


def normalize_operation(position, raw):
    """Os campos de uma operacao, sem decidir nada."""
    quantity = abs(safe_float(raw.get("quantity")))
    amount = abs(safe_float(raw.get("amount")))
    price = abs(safe_float(raw.get("value")))
    if not price and quantity:
        price = amount / quantity
    return {
        "op_key": op_key(position, raw),
        "pluggy_investment_id": str(position.get("id")),
        "code": ticker_key(position.get("code") or "") or None,
        "name": (position.get("name") or "")[:120] or None,
        "pluggy_type": str(position.get("type") or "").upper() or None,
        "op_type": str(raw.get("type") or "").upper() or "UNKNOWN",
        "trade_date": _day(raw.get("tradeDate")) or _day(raw.get("date")),
        "quantity": quantity,
        "unit_price": price,
        "amount": amount,
        "net_amount": abs(safe_float(raw.get("netAmount"))) or None,
        "expenses": expenses_total(raw.get("expenses")),
    }


# ---------------------------------------------------------------------------
# Gravar
# ---------------------------------------------------------------------------

def equity_class(conn, current_user_id, ticker):
    """A classe do ativo que o dono ja tem com este ticker; senao a do catalogo."""
    row = conn.execute(
        f"""
        SELECT asset_class FROM assets
        WHERE user_id = ? AND ticker = ? AND asset_class IN ({', '.join('?' for _ in QUOTED_ASSET_CLASSES)})
        ORDER BY created_at, id LIMIT 1
        """,
        (current_user_id, ticker, *sorted(QUOTED_ASSET_CLASSES)),
    ).fetchone()
    if row:
        return row["asset_class"]
    entry = market_catalog.lookup(ticker)
    return entry["asset_class"] if entry else None


def _free_typed_rows(conn, current_user_id, asset_class, ticker, trade_date):
    """As operacoes do ativo a ate LINK_DAYS dias, nao ligadas a outra da Pluggy."""
    day = parse_iso_date(trade_date).date()
    return conn.execute(
        """
        SELECT it.id, it.transaction_date, it.quantity FROM investment_transactions it
        JOIN assets a ON a.id = it.asset_id AND a.user_id = it.user_id
        WHERE it.user_id = ? AND a.asset_class = ? AND a.ticker = ? AND it.transaction_date BETWEEN ? AND ?
          AND NOT EXISTS (
              SELECT 1 FROM open_finance_investment_operations o
              WHERE o.user_id = it.user_id AND o.investment_id = it.id
          )
        ORDER BY it.transaction_date, it.id
        """,
        (
            current_user_id, asset_class, ticker,
            (day - timedelta(days=LINK_DAYS)).isoformat(), (day + timedelta(days=LINK_DAYS)).isoformat(),
        ),
    ).fetchall()


def _typed_twin(conn, current_user_id, asset_class, ticker, signed_quantity, trade_date):
    """A mesma operacao ja lancada pelo dono (e nao ligada a outra da Pluggy)."""
    day = parse_iso_date(trade_date).date()
    rows = _free_typed_rows(conn, current_user_id, asset_class, ticker, trade_date)
    found = [row for row in rows if abs(safe_float(row["quantity"]) - signed_quantity) < QUANTITY_TOLERANCE]
    found.sort(key=lambda row: abs((parse_iso_date(row["transaction_date"]).date() - day).days))
    return found[0]["id"] if found else None


def _summed_twins(conn, current_user_id, asset_class, ticker, signed_quantity, trade_date):
    """As digitadas de mesmo sinal cujas quantidades somam a operacao (a menor
    combinacao, as de data mais perto primeiro), ou []."""
    day = parse_iso_date(trade_date).date()
    rows = [
        row for row in _free_typed_rows(conn, current_user_id, asset_class, ticker, trade_date)
        if (safe_float(row["quantity"]) > 0) == (signed_quantity > 0)
    ]
    rows.sort(key=lambda row: (abs((parse_iso_date(row["transaction_date"]).date() - day).days), row["id"]))
    rows = rows[:MAX_SUMMED_ROWS]
    for size in range(2, len(rows) + 1):
        for group in combinations(rows, size):
            if abs(sum(safe_float(row["quantity"]) for row in group) - signed_quantity) < QUANTITY_TOLERANCE:
                return [row["id"] for row in group]
    return []


def _insert_movement(conn, current_user_id, asset_class, op):
    """A operacao como POST /api/investments a gravaria (renda variavel, BRL)."""
    signed = op["quantity"] if op["op_type"] == "BUY" else -op["quantity"]
    validate_investment_movement(conn, current_user_id, asset_class, op["code"], signed)
    asset_id = get_or_create_asset(conn, current_user_id, asset_class, op["code"])
    ensure_outside_corporate_actions(conn, current_user_id, asset_id, op["trade_date"])
    metadata = {
        ("purchase_date" if signed > 0 else "sale_date"): op["trade_date"],
        "other_costs": op["expenses"],
        "source": "open_finance",
        "open_finance_operation": op["op_key"],
    }
    if signed < 0:
        metadata["sale_price"] = op["unit_price"]
    if op.get("net_amount"):
        # O que a corretora liquidou de fato (com taxas): o caixa usa este (049).
        metadata[SETTLEMENT_AMOUNT_KEY] = op["net_amount"]
    cash_account = portfolio_cash_account_id(conn, current_user_id)
    if cash_account:
        metadata[CASH_ACCOUNT_KEY] = cash_account
    movement_id = new_id()
    conn.execute(
        """
        INSERT INTO investment_transactions
        (id, user_id, asset_id, movement_type, quantity, unit_price, gross_amount, fee_amount,
         transaction_date, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            movement_id, current_user_id, asset_id, investment_movement_type(signed, metadata), signed,
            op["unit_price"], investment_gross_amount(signed, op["unit_price"]), investment_fee_amount(metadata),
            op["trade_date"], encode_metadata(metadata),
        ),
    )
    validate_asset_transaction_backing(conn, current_user_id, asset_id)
    if cash_account:
        movement = serialize_investment(fetch_investment_rows(conn, current_user_id, investment_id=movement_id)[0])
        sync_investment_cash_transaction(conn, current_user_id, movement)
    return movement_id


def decide(conn, current_user_id, op):
    """(state, held_reason, investment_id) de uma operacao nova (ou segurada).
    Na soma de digitadas, as outras ficam em op["other_links"]."""
    if op["op_type"] not in RECORDED_TYPES or op["pluggy_type"] not in EQUITY_TYPES:
        return "HELD", "type", None
    if not op["code"] or not op["trade_date"] or op["quantity"] <= 0 or op["unit_price"] <= 0:
        return "HELD", "incomplete", None
    asset_class = equity_class(conn, current_user_id, op["code"])
    if not asset_class:
        return "HELD", "unknown_asset", None
    signed = op["quantity"] if op["op_type"] == "BUY" else -op["quantity"]
    twin = _typed_twin(conn, current_user_id, asset_class, op["code"], signed, op["trade_date"])
    if twin:
        return "LINKED", None, twin
    summed = _summed_twins(conn, current_user_id, asset_class, op["code"], signed, op["trade_date"])
    if summed:
        op["other_links"] = summed[1:]
        return "LINKED", None, summed[0]
    conn.execute("SAVEPOINT open_finance_operation")
    try:
        movement_id = _insert_movement(conn, current_user_id, asset_class, op)
    except ValidationError as exc:
        conn.execute("ROLLBACK TO SAVEPOINT open_finance_operation")
        conn.execute("RELEASE SAVEPOINT open_finance_operation")
        reason = "corporate_action" if "evento" in str(exc) else "refused"
        return "HELD", f"{reason}: {str(exc)[:200]}", None
    conn.execute("RELEASE SAVEPOINT open_finance_operation")
    return "RECORDED", None, movement_id


def _save_positions(conn, current_user_id, of_item_id, positions):
    stamp = utc_timestamp()
    for raw in positions:
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        values = {
            "of_item_id": of_item_id,
            "code": ticker_key(raw.get("code") or "") or None,
            "name": (raw.get("name") or "")[:120] or None,
            "pluggy_type": str(raw.get("type") or "").upper() or None,
            "subtype": str(raw.get("subtype") or "").upper() or None,
            "quantity": safe_float(raw.get("quantity"), None),
            "unit_value": safe_float(raw.get("value"), None),
            "balance": safe_float(raw.get("balance"), None),
            "status": raw.get("status"),
            "position_date": _day(raw.get("date")),
            "updated_at": stamp,
        }
        existing = conn.execute(
            "SELECT id FROM open_finance_positions WHERE user_id = ? AND pluggy_investment_id = ?",
            (current_user_id, str(raw["id"])),
        ).fetchone()
        if existing:
            conn.execute(
                f"UPDATE open_finance_positions SET {', '.join(f'{key} = ?' for key in values)} WHERE id = ? AND user_id = ?",
                (*values.values(), existing["id"], current_user_id),
            )
        else:
            values.update({"id": new_id(), "user_id": current_user_id, "pluggy_investment_id": str(raw["id"])})
            conn.execute(
                f"INSERT INTO open_finance_positions ({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})",
                tuple(values.values()),
            )


def apply(conn, current_user_id, of_item_id, data, today):
    """Grava as posicoes e decide cada operacao nova (na ordem do pregao).
    Devolve {recorded, linked, held, dismissed}."""
    counts = {"recorded": 0, "linked": 0, "held": 0, "dismissed": 0}
    _save_positions(conn, current_user_id, of_item_id, data.get("positions") or [])
    operations = [normalize_operation(position, raw) for position, raw in data.get("operations") or []]
    operations.sort(key=lambda op: (op["trade_date"] or "", 0 if op["op_type"] == "BUY" else 1, op["op_key"]))
    for op in operations:
        existing = conn.execute(
            "SELECT * FROM open_finance_investment_operations WHERE user_id = ? AND op_key = ?",
            (current_user_id, op["op_key"]),
        ).fetchone()
        if existing and existing["state"] in ("RECORDED", "LINKED"):
            if existing["investment_id"] is None:
                # O dono apagou a operacao no Extrato: desfeita para sempre.
                conn.execute(
                    "UPDATE open_finance_investment_operations SET state = 'DISMISSED', updated_at = ? WHERE id = ? AND user_id = ?",
                    (utc_timestamp(), existing["id"], current_user_id),
                )
                counts["dismissed"] += 1
            continue
        if existing and existing["state"] == "DISMISSED":
            continue
        state, reason, investment_id = decide(conn, current_user_id, op)
        counts[state.lower()] += 1
        values = {key: op[key] for key in (
            "pluggy_investment_id", "code", "name", "pluggy_type", "op_type", "trade_date", "quantity",
            "unit_price", "amount", "net_amount", "expenses",
        )}
        values["trade_date"] = values["trade_date"] or today.isoformat()
        values.update({"state": state, "held_reason": reason, "investment_id": investment_id,
                       "updated_at": utc_timestamp()})
        if existing:
            conn.execute(
                f"UPDATE open_finance_investment_operations SET {', '.join(f'{key} = ?' for key in values)} WHERE id = ? AND user_id = ?",
                (*values.values(), existing["id"], current_user_id),
            )
        else:
            values.update({"id": new_id(), "user_id": current_user_id, "of_item_id": of_item_id,
                           "op_key": op["op_key"]})
            conn.execute(
                f"INSERT INTO open_finance_investment_operations ({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})",
                tuple(values.values()),
            )
        _link_parts(conn, current_user_id, of_item_id, op, today)
    return counts


def _link_parts(conn, current_user_id, of_item_id, op, today):
    """As outras digitadas de uma soma: linhas so para tira-las de outro vinculo."""
    for investment_id in op.get("other_links") or []:
        conn.execute(
            """
            INSERT OR IGNORE INTO open_finance_investment_operations
            (id, user_id, of_item_id, op_key, pluggy_investment_id, code, name, pluggy_type, op_type, trade_date,
             quantity, state, investment_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'LINKED', ?)
            """,
            (
                new_id(), current_user_id, of_item_id, f"{op['op_key']}{PART_KEY}{investment_id}",
                op["pluggy_investment_id"], op["code"], op["name"], op["pluggy_type"], op["op_type"],
                op["trade_date"] or today.isoformat(), investment_id,
            ),
        )


# ---------------------------------------------------------------------------
# Conferir
# ---------------------------------------------------------------------------

def _app_quantity(conn, current_user_id, ticker):
    row = conn.execute(
        f"""
        SELECT COALESCE(SUM(it.quantity), 0) AS quantity FROM investment_transactions it
        JOIN assets a ON a.id = it.asset_id AND a.user_id = it.user_id
        WHERE it.user_id = ? AND a.ticker = ? AND a.asset_class IN ({', '.join('?' for _ in QUOTED_ASSET_CLASSES)})
        """,
        (current_user_id, ticker, *sorted(QUOTED_ASSET_CLASSES)),
    ).fetchone()
    return safe_float(row["quantity"])


def _later_operations(conn, current_user_id, code, after_day):
    """Quantidade com sinal das operacoes gravadas/ligadas depois do dia da posicao."""
    total = 0.0
    for row in conn.execute(
        """
        SELECT op_type, quantity FROM open_finance_investment_operations
        WHERE user_id = ? AND code = ? AND state IN ('RECORDED', 'LINKED') AND trade_date > ?
        """,
        (current_user_id, code, after_day or "0000-00-00"),
    ).fetchall():
        quantity = safe_float(row["quantity"])
        total += quantity if row["op_type"] == "BUY" else -quantity
    return total


def portfolio_check(conn, current_user_id, today=None):
    """A carteira da corretora contra a do app, ou None sem dados da Pluggy.

    - `positions`: cada ativo de renda variavel, quantidade da Pluggy (do dia
      da posicao, D-1) mais as operacoes depois dela, contra a do app;
      renda fixa e Tesouro so com o valor (nunca marcados por ele).
    - `cash`: o saldo da conta da corretora na Pluggy contra o da Corretora no
      app ate o dia do saldo da Pluggy; `unsettled` e o que esta em transito.
    - `held`: operacoes que esperam o dono, com o motivo.
    """
    positions = conn.execute(
        """
        SELECT p.* FROM open_finance_positions p
        JOIN open_finance_items i ON i.id = p.of_item_id AND i.user_id = p.user_id
        WHERE p.user_id = ? AND i.archived_at IS NULL
        ORDER BY p.pluggy_type, p.code, p.name
        """,
        (current_user_id,),
    ).fetchall()
    if not positions:
        return None
    today = today or invoices.local_today()
    listed = []
    for row in positions:
        entry = {
            "code": row["code"], "name": row["name"], "type": row["pluggy_type"], "status": row["status"],
            "pluggy_quantity": row["quantity"], "balance": row["balance"], "position_date": row["position_date"],
        }
        if row["pluggy_type"] in EQUITY_TYPES and row["code"]:
            expected = safe_float(row["quantity"]) + _later_operations(
                conn, current_user_id, row["code"], row["position_date"],
            )
            app_quantity = _app_quantity(conn, current_user_id, row["code"])
            entry["app_quantity"] = app_quantity
            entry["expected_quantity"] = expected
            entry["matches"] = abs(app_quantity - expected) < QUANTITY_TOLERANCE
        listed.append(entry)
    held = [
        {"code": row["code"], "name": row["name"], "type": row["op_type"], "trade_date": row["trade_date"],
         "quantity": row["quantity"], "amount": row["amount"], "reason": row["held_reason"]}
        for row in conn.execute(
            """
            SELECT * FROM open_finance_investment_operations
            WHERE user_id = ? AND state = 'HELD' ORDER BY trade_date DESC, code LIMIT 100
            """,
            (current_user_id,),
        ).fetchall()
    ]
    return {
        "positions": listed,
        "mismatched_count": sum(1 for entry in listed if entry.get("matches") is False),
        "held": held,
        "cash": cash_check(conn, current_user_id, today),
    }


def cash_check(conn, current_user_id, today):
    """O caixa da corretora na Pluggy contra o da Corretora no app (049).

    O lancamento de cada operacao fica na data da liquidacao, entao o app se
    compara so com o que esta datado ate o dia do saldo da Pluggy; `unsettled`
    e o que ainda esta em transito (operacoes e proventos depois de hoje).
    """
    view = broker_settlement(conn, current_user_id, today)
    if not view or not view["pluggy"] or view["pluggy"]["app_balance"] is None:
        return None
    pluggy = view["pluggy"]
    return {
        "pluggy_balance": pluggy["balance"],
        "app_balance": pluggy["app_balance"],
        "as_of": pluggy["as_of"],
        "difference": pluggy["difference"],
        "unsettled": view["in_transit_total"],
        "unexplained": pluggy["difference"],
    }


def recorded_any(result):
    return bool(result) and bool(result.get("recorded"))
