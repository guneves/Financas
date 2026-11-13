"""Renda fixa, Tesouro e cupom da corretora pela Pluggy, so com dados exatos (Fase 3).

A operacao da Pluggy (`/investments/{id}/transactions`) nao diz o indexador, a
taxa nem o tipo do titulo; a *posicao* (`/investments`) diz, quando o MeuPluggy
preenche: `subtype`, `rateType`, `rate`, `fixedAnnualRate`, `dueDate`. A
posicao inteira fica em `open_finance_positions.raw` (056) e este modulo grava
a operacao quando ela mapeia **exatamente** para o metadata do app
(`validate_fixed_income_metadata()`); senao a operacao espera (HELD) com o
motivo `missing:<campo>` (falta) ou `unmapped:<campo>` (veio, mas nao tem um
significado so). **Nunca chuta uma taxa**: uma taxa errada marca a carteira
errada sem aviso nenhum.

- **Remuneracao** (`title_terms()`), na unidade da doc da Pluggy, percentual:
  CDI com `rate` = "% do CDI" (110 -> 1.10); IPCA com `fixedAnnualRate` =
  "IPCA+ x%"; pre-fixado com `fixedAnnualRate` = "PRE x%". SELIC, IGPM, CDI
  com taxa fixa (CDI+? ou outra coisa?) e qualquer outro esperam. Uma taxa fora
  da faixa plausivel (`CDI_PERCENT_RANGE`, `ANNUAL_PERCENT_RANGE`) espera: ali
  ate a unidade seria um palpite (0,065 e 6,5% ou 0,065%?).
- **Tipo do titulo** (`TITLE_TYPES`): decide o IR e a categoria (LCI, LCA,
  CRI e CRA isentos, services/fixed_income.py; TESOURO e a categoria Tesouro
  Direto, services/asset_categories.py).
- **Tesouro**: o nome tem que achar o titulo no arquivo de precos do Tesouro
  (`tesouro_client.TreasuryPrices.find_title()`), o tipo do nome tem que
  concordar com a remuneracao e, com `dueDate`, o vencimento com o do arquivo;
  os titulos comprados (`treasury_units`) sao a quantidade da Pluggy.
- **Sem caixa**: o dinheiro da renda fixa ja e uma linha BROKER_STATEMENT do
  extrato da corretora (services/broker_statement.py); um lancamento ligado
  contaria duas vezes. A compra, o resgate e o cupom gravados daqui nao tem
  `cash_account_id`.
- **Resgate**: baixa as compras do mesmo investimento da Pluggy, a mais antiga
  primeiro (PEPS, a regra de lib/treasury.js), pela quantidade de cotas da
  Pluggy: custo e bruto proporcionais as cotas, exatos. Sem compra no app, ou
  cotas que nao fecham, espera.
- **Cupom** (INTEREST): um provento INTEREST (040) no ativo da compra do
  titulo, com o IR pela primeira compra (`interest_tax_rate()`). A linha do
  extrato que ja pagou o cupom passa a ser o lancamento do provento
  (`broker_statement.adopt_proceed_line()`), nunca um segundo.
- **Ligado, nunca duplicado**: a compra, o resgate ou o cupom que o dono ja
  lancou (mesmo valor ao centavo, ate LINK_DAYS dias) e ligado.
"""

import json
import math
from datetime import timedelta

import tesouro_client
from dates import parse_iso_date
from db import encode_metadata, new_id, parse_metadata_value
from money import cents_or_zero, rounded_money
from services import broker_statement
from services.corporate_actions import ensure_outside_corporate_actions
from services.fixed_income import TAX_FREE_FIXED_INCOME_TYPES, validate_fixed_income_metadata
from services.investments import (
    get_or_create_asset,
    investment_fee_amount,
    investment_gross_amount,
    investment_movement_type,
    validate_asset_transaction_backing,
    validate_movement_metadata,
)
from services.prices import quote_timestamp, record_price_quote
from services.proceeds import INTEREST_TYPE, interest_tax_rate, investment_position_at_date
from validators import ValidationError, safe_float

LINK_DAYS = 2
PLUGGY_FIXED_INCOME = "FIXED_INCOME"
# subtype da Pluggy -> fixed_income_type do app. So o que tem um significado so.
TITLE_TYPES = {
    "CDB": "CDB",
    "LCI": "LCI",
    "LCA": "LCA",
    "LC": "LC",
    "CRI": "CRI",
    "CRA": "CRA",
    "DEBENTURE": "DEBENTURE",
    "DEBENTURES": "DEBENTURE",
    "TREASURY": "TESOURO",
}
TREASURY_SUBTYPE = "TREASURY"
# rateType da Pluggy (sem hifen, espaco ou sublinhado) -> forma do app.
RATE_KINDS = {"CDI": "CDI", "IPCA": "IPCA", "PRE": "PRE", "PREFIXADO": "PRE"}
CDI_PERCENT_RANGE = (10.0, 300.0)
ANNUAL_PERCENT_RANGE = (0.5, 50.0)
TREASURY_KINDS = {
    tesouro_client.IPCA: "IPCA",
    tesouro_client.IPCA_JUROS: "IPCA",
    tesouro_client.RENDA_MAIS: "IPCA",
    tesouro_client.EDUCA_MAIS: "IPCA",
    tesouro_client.PREFIXADO: "PRE",
    tesouro_client.PREFIXADO_JUROS: "PRE",
}
UNITS_KEY = "open_finance_units"
OPERATION_KEY = "open_finance_operation"
UNITS_TOLERANCE = 0.000001


class Held(Exception):
    """A operacao espera o dono: `reason` e `missing:<campo>` ou `unmapped:<campo>`."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


# ---------------------------------------------------------------------------
# Puro: a posicao da Pluggy -> o metadata do titulo
# ---------------------------------------------------------------------------

def _present(raw, key):
    value = raw.get(key)
    return value not in (None, "")


def _number(raw, key):
    value = raw.get(key)
    if isinstance(value, bool):
        return None
    number = safe_float(value, None)
    return number if number is not None and math.isfinite(number) else None


def _rate_kind(value):
    text = "".join(char for char in str(value or "").upper() if char.isalnum())
    return RATE_KINDS.get(text)


def _percent(raw, key, bounds):
    """A taxa em fracao (110 -> 1.10), ou Held."""
    if not _present(raw, key):
        raise Held(f"missing:{key}")
    number = _number(raw, key)
    if number is None or not bounds[0] <= number <= bounds[1]:
        raise Held(f"unmapped:{key}")
    return round(number / 100, 8)


def _no_fixed_rate(raw):
    number = _number(raw, "fixedAnnualRate")
    return not _present(raw, "fixedAnnualRate") or number == 0


def is_fixed_income_position(raw):
    return isinstance(raw, dict) and str(raw.get("type") or "").upper() == PLUGGY_FIXED_INCOME


def title_terms(raw, prices=None):
    """{ticker, metadata} do titulo da posicao, ou Held com o primeiro campo que
    falta ou nao mapeia. `prices`: o arquivo do Tesouro (TreasuryPrices) ou None."""
    if not isinstance(raw, dict):
        raise Held("missing:position")
    if not is_fixed_income_position(raw):
        raise Held("unmapped:type")
    subtype = str(raw.get("subtype") or "").upper()
    if not subtype:
        raise Held("missing:subtype")
    title_type = TITLE_TYPES.get(subtype)
    if not title_type:
        raise Held("unmapped:subtype")
    name = " ".join(str(raw.get("name") or "").split())
    if not name:
        raise Held("missing:name")
    if not _present(raw, "rateType"):
        raise Held("missing:rateType")
    kind = _rate_kind(raw.get("rateType"))
    if kind is None:
        # SELIC, IGPM ou outro: o app nao le (Selic acompanharia o CDI: chute).
        raise Held("unmapped:rateType")

    metadata = {"fixed_income_type": title_type}
    if kind == "CDI":
        if not _no_fixed_rate(raw):
            # CDI com taxa fixa: CDI+ x% ou % do CDI mais spread? Nao se sabe.
            raise Held("unmapped:fixedAnnualRate")
        metadata.update({"rate_type": "POS", "indexer": "CDI", "cdi_percentage": _percent(raw, "rate", CDI_PERCENT_RANGE)})
    elif kind == "IPCA":
        metadata.update({
            "rate_type": "POS", "indexer": "IPCA",
            "annual_rate": _percent(raw, "fixedAnnualRate", ANNUAL_PERCENT_RANGE),
        })
    else:
        metadata.update({"rate_type": "PRE", "annual_rate": _percent(raw, "fixedAnnualRate", ANNUAL_PERCENT_RANGE)})
    metadata["is_tax_free"] = title_type in TAX_FREE_FIXED_INCOME_TYPES

    if title_type == "TESOURO":
        if prices is None:
            raise Held("missing:tesouro_prices")
        series = prices.find_title(name)
        if series is None:
            raise Held("unmapped:name")
        if TREASURY_KINDS.get(series.title_type) != kind:
            raise Held("unmapped:rateType")
        due = parse_iso_date(str(raw.get("dueDate") or "")[:10]) if _present(raw, "dueDate") else None
        if _present(raw, "dueDate") and (due is None or due.date() != series.maturity):
            raise Held("unmapped:dueDate")
    validate_fixed_income_metadata("FIXED_INCOME", 1, metadata)
    return {"ticker": name, "metadata": metadata}


def partial_terms(raw, prices=None):
    """O que da para preencher do titulo para o dono terminar (o "Lancar")."""
    try:
        return title_terms(raw, prices)
    except (Held, ValidationError):
        pass
    raw = raw if isinstance(raw, dict) else {}
    metadata = {}
    title_type = TITLE_TYPES.get(str(raw.get("subtype") or "").upper())
    if title_type:
        metadata["fixed_income_type"] = title_type
    return {"ticker": " ".join(str(raw.get("name") or "").split()) or None, "metadata": metadata}


def raw_position(conn, current_user_id, pluggy_investment_id):
    row = conn.execute(
        "SELECT raw FROM open_finance_positions WHERE user_id = ? AND pluggy_investment_id = ?",
        (current_user_id, str(pluggy_investment_id)),
    ).fetchone()
    if not row or not row["raw"]:
        return None
    try:
        value = json.loads(row["raw"])
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def treasury_prices():
    """O arquivo do Tesouro sem esperar (a leitura nunca espera o download)."""
    try:
        return tesouro_client.get_prices(wait=False)
    except Exception:  # noqa: BLE001 - sem arquivo, o Tesouro espera
        return None


# ---------------------------------------------------------------------------
# Gravar
# ---------------------------------------------------------------------------

def _shifted(day, days):
    return (parse_iso_date(day).date() + timedelta(days=days)).isoformat()


def _linked_ids(conn, current_user_id):
    return {
        row["investment_id"] for row in conn.execute(
            "SELECT investment_id FROM open_finance_investment_operations WHERE user_id = ? AND investment_id IS NOT NULL",
            (current_user_id,),
        ).fetchall()
    }


def _fixed_income_rows(conn, current_user_id, date_from, date_to):
    rows = conn.execute(
        """
        SELECT it.id, it.asset_id, it.quantity, it.unit_price, it.transaction_date, it.metadata
        FROM investment_transactions it
        JOIN assets a ON a.id = it.asset_id AND a.user_id = it.user_id
        WHERE it.user_id = ? AND a.asset_class = 'FIXED_INCOME' AND it.transaction_date BETWEEN ? AND ?
        ORDER BY it.transaction_date, it.id
        """,
        (current_user_id, date_from, date_to),
    ).fetchall()
    return [dict(row, metadata=parse_metadata_value(row["metadata"]) or {}) for row in rows]


def _typed_buy(conn, current_user_id, op):
    """A compra de renda fixa ja lancada com o mesmo valor (ate LINK_DAYS dias)."""
    linked = _linked_ids(conn, current_user_id)
    wanted = {cents_or_zero(op["amount"]), cents_or_zero(op["amount"] + op["expenses"])}
    for row in _fixed_income_rows(
        conn, current_user_id, _shifted(op["trade_date"], -LINK_DAYS), _shifted(op["trade_date"], LINK_DAYS),
    ):
        if row["id"] in linked or safe_float(row["quantity"]) <= 0 or row["metadata"].get("is_redemption"):
            continue
        if cents_or_zero(investment_gross_amount(row["quantity"], row["unit_price"])) in wanted:
            return row["id"]
    return None


def _insert(conn, current_user_id, ticker, quantity, unit_price, metadata, quote=None):
    validate_movement_metadata(metadata)
    validate_fixed_income_metadata("FIXED_INCOME", quantity, metadata)
    asset_id = get_or_create_asset(conn, current_user_id, "FIXED_INCOME", ticker)
    day = next(metadata[key] for key in ("redemption_date", "purchase_date") if metadata.get(key))
    ensure_outside_corporate_actions(conn, current_user_id, asset_id, day)
    movement_id = new_id()
    conn.execute(
        """
        INSERT INTO investment_transactions
        (id, user_id, asset_id, movement_type, quantity, unit_price, gross_amount, fee_amount,
         transaction_date, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            movement_id, current_user_id, asset_id, investment_movement_type(quantity, metadata), quantity,
            unit_price, investment_gross_amount(quantity, unit_price), investment_fee_amount(metadata), day,
            encode_metadata(metadata),
        ),
    )
    if quote is not None:
        record_price_quote(
            conn, current_user_id, asset_id, quote, asset_class="FIXED_INCOME", transaction_id=movement_id,
            quoted_at=quote_timestamp(day), source="open_finance",
        )
    validate_asset_transaction_backing(conn, current_user_id, asset_id)
    return movement_id


def record_buy(conn, current_user_id, op, terms):
    """(state, investment_id) da compra do titulo."""
    if not op["trade_date"]:
        raise Held("missing:tradeDate")
    if op["amount"] <= 0:
        raise Held("missing:amount")
    twin = _typed_buy(conn, current_user_id, op)
    if twin:
        return "LINKED", twin
    metadata = {
        **terms["metadata"],
        "purchase_date": op["trade_date"],
        "other_costs": op["expenses"],
        "source": "open_finance",
        OPERATION_KEY: op["op_key"],
    }
    if op["quantity"] > 0:
        metadata[UNITS_KEY] = op["quantity"]
        if terms["metadata"].get("fixed_income_type") == "TESOURO":
            metadata["treasury_units"] = op["quantity"]
    return "RECORDED", _insert(conn, current_user_id, terms["ticker"], 1, op["amount"] + op["expenses"], metadata)


def title_lots(conn, current_user_id, pluggy_investment_id):
    """As compras do investimento da Pluggy no app, a mais antiga primeiro, com
    as cotas e o custo que ainda restam."""
    lots = []
    for row in conn.execute(
        """
        SELECT o.quantity AS units, it.id, it.asset_id, it.quantity, it.unit_price, it.transaction_date
        FROM open_finance_investment_operations o
        JOIN investment_transactions it ON it.id = o.investment_id AND it.user_id = o.user_id
        WHERE o.user_id = ? AND o.pluggy_investment_id = ? AND o.op_type = 'BUY'
          AND o.state IN ('RECORDED', 'LINKED') AND instr(o.op_key, '#') = 0
        ORDER BY it.transaction_date, it.id
        """,
        (current_user_id, str(pluggy_investment_id)),
    ).fetchall():
        lots.append({
            "id": row["id"], "asset_id": row["asset_id"], "date": row["transaction_date"],
            "units": safe_float(row["units"]), "cost": abs(safe_float(row["quantity"]) * safe_float(row["unit_price"])),
            "taken_units": 0.0, "taken_cost": 0.0, "unknown": False,
        })
    if not lots:
        return lots
    by_id = {lot["id"]: lot for lot in lots}
    for row in conn.execute(
        """
        SELECT it.unit_price, it.quantity, it.metadata FROM investment_transactions it
        WHERE it.user_id = ? AND it.metadata LIKE '%related_id%'
        """,
        (current_user_id,),
    ).fetchall():
        metadata = parse_metadata_value(row["metadata"]) or {}
        lot = by_id.get(str(metadata.get("related_id") or ""))
        if not lot or not metadata.get("is_redemption"):
            continue
        units = safe_float(metadata.get(UNITS_KEY), None)
        if units is None:
            lot["unknown"] = True
            continue
        lot["taken_units"] += units
        lot["taken_cost"] += abs(safe_float(row["quantity"]) * safe_float(row["unit_price"]))
    return lots


def _typed_redemption(conn, current_user_id, op, lot_ids):
    linked = _linked_ids(conn, current_user_id)
    for row in _fixed_income_rows(
        conn, current_user_id, _shifted(op["trade_date"], -LINK_DAYS), _shifted(op["trade_date"], LINK_DAYS),
    ):
        if row["id"] in linked or not row["metadata"].get("is_redemption"):
            continue
        if str(row["metadata"].get("related_id") or "") in lot_ids:
            return row["id"]
    return None


def redemption_plan(lots, units, amount):
    """Puro: [{lot_id, units, cost, amount}] baixando `units` cotas das compras
    na ordem (PEPS), ou Held."""
    if units <= 0:
        raise Held("missing:quantity")
    if any(lot["units"] <= 0 or lot["unknown"] for lot in lots):
        raise Held("unmapped:lot")
    rest = units
    parts = []
    for lot in lots:
        free = lot["units"] - lot["taken_units"]
        if rest <= UNITS_TOLERANCE:
            break
        if free <= UNITS_TOLERANCE:
            continue
        take = min(free, rest)
        closes = abs(free - take) <= UNITS_TOLERANCE
        cost = lot["cost"] - lot["taken_cost"] if closes else lot["cost"] * take / lot["units"]
        parts.append({"lot_id": lot["id"], "units": take, "cost": max(cost, 0.0), "amount": amount * take / units})
        rest -= take
    if rest > UNITS_TOLERANCE:
        raise Held("unmapped:quantity")
    # O bruto em centavos: a ultima parte leva o arredondamento.
    rounded = [rounded_money(part["amount"]) for part in parts]
    rounded[-1] = rounded_money(amount - sum(rounded[:-1]))
    for part, value in zip(parts, rounded):
        part["amount"] = value
    return parts


def record_redemption(conn, current_user_id, op, terms):
    """(state, investment_id) do resgate: o da primeira parte."""
    if not op["trade_date"]:
        raise Held("missing:tradeDate")
    if op["amount"] <= 0:
        raise Held("missing:amount")
    lots = title_lots(conn, current_user_id, op["pluggy_investment_id"])
    if not lots:
        raise Held("missing:buy")
    twin = _typed_redemption(conn, current_user_id, op, {lot["id"] for lot in lots})
    if twin:
        return "LINKED", twin
    parts = redemption_plan(lots, op["quantity"], op["amount"])
    first = None
    for part in parts:
        metadata = {
            "is_redemption": True,
            "affects_position": True,
            "related_id": part["lot_id"],
            "redemption_date": op["trade_date"],
            "source": "open_finance",
            OPERATION_KEY: op["op_key"],
            UNITS_KEY: part["units"],
        }
        movement_id = _insert(conn, current_user_id, terms["ticker"], -1, part["cost"], metadata, quote=part["amount"])
        first = first or movement_id
    return "RECORDED", first


def _typed_interest(conn, current_user_id, asset_id, op):
    for row in conn.execute(
        """
        SELECT p.id, p.gross_amount, p.net_amount FROM investment_proceeds p
        WHERE p.user_id = ? AND p.asset_id = ? AND p.proceeds_type = ? AND substr(p.payment_date, 1, 10) BETWEEN ? AND ?
          AND NOT EXISTS (
              SELECT 1 FROM open_finance_investment_operations o WHERE o.user_id = p.user_id AND o.proceed_id = p.id
          )
        ORDER BY p.payment_date, p.id
        """,
        (
            current_user_id, asset_id, INTEREST_TYPE,
            _shifted(op["trade_date"], -LINK_DAYS), _shifted(op["trade_date"], LINK_DAYS),
        ),
    ).fetchall():
        if cents_or_zero(op["amount"]) in (cents_or_zero(row["gross_amount"]), cents_or_zero(row["net_amount"])):
            return row["id"]
    return None


def record_interest(conn, current_user_id, op):
    """(state, proceed_id) do cupom: provento INTEREST no ativo da compra."""
    if not op["trade_date"]:
        raise Held("missing:tradeDate")
    if op["amount"] <= 0:
        raise Held("missing:amount")
    lots = title_lots(conn, current_user_id, op["pluggy_investment_id"])
    if not lots:
        raise Held("missing:buy")
    asset_id = lots[0]["asset_id"]
    twin = _typed_interest(conn, current_user_id, asset_id, op)
    if twin:
        return "LINKED", twin
    day = op["trade_date"]
    gross = rounded_money(op["amount"])
    tax = rounded_money(gross * interest_tax_rate(conn, current_user_id, asset_id, day))
    eligible = safe_float(investment_position_at_date(conn, current_user_id, asset_id, day)["quantity"])
    proceed_id = new_id()
    conn.execute(
        """
        INSERT INTO investment_proceeds
        (id, user_id, asset_id, proceeds_type, record_date, payment_date, amount_per_unit, eligible_quantity,
         gross_amount, tax_amount, net_amount, source, notes, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open_finance', '', ?)
        """,
        (
            proceed_id, current_user_id, asset_id, INTEREST_TYPE, day, day,
            round(gross / eligible, 8) if eligible > 0 else None, round(eligible, 6), gross, tax,
            rounded_money(gross - tax), encode_metadata({OPERATION_KEY: op["op_key"]}),
        ),
    )
    broker_statement.adopt_proceed_line(conn, current_user_id, proceed_id)
    return "RECORDED", proceed_id


def _record(conn, current_user_id, op, prices):
    if op["op_type"] == "INTEREST":
        state, proceed_id = record_interest(conn, current_user_id, op)
        return state, None, proceed_id
    if op["op_type"] not in ("BUY", "SELL"):
        raise Held("unmapped:type")
    raw = raw_position(conn, current_user_id, op["pluggy_investment_id"])
    terms = title_terms(raw, treasury_prices() if prices == "auto" else prices)
    if op["op_type"] == "BUY":
        state, movement_id = record_buy(conn, current_user_id, op, terms)
    else:
        state, movement_id = record_redemption(conn, current_user_id, op, terms)
    return state, movement_id, None


def decide(conn, current_user_id, op, prices="auto"):
    """(state, held_reason, investment_id, proceed_id) de uma operacao de renda
    fixa. Nada fica gravado de uma operacao que espera."""
    conn.execute("SAVEPOINT open_finance_fixed_income")
    try:
        state, movement_id, proceed_id = _record(conn, current_user_id, op, prices)
    except (Held, ValidationError) as exc:
        conn.execute("ROLLBACK TO SAVEPOINT open_finance_fixed_income")
        conn.execute("RELEASE SAVEPOINT open_finance_fixed_income")
        if isinstance(exc, Held):
            return "HELD", exc.reason, None, None
        return "HELD", f"refused: {str(exc)[:200]}", None, None
    conn.execute("RELEASE SAVEPOINT open_finance_fixed_income")
    return state, None, movement_id, proceed_id
