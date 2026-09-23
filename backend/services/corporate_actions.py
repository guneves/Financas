"""Eventos corporativos: desdobramento, grupamento e bonificacao (017).

Ajuste na gravacao (ver a migration 017): registrar um evento reescala as
operacoes e cotacoes anteriores a data ex, ou cria a operacao da bonificacao;
excluir desfaz exatamente o que foi feito, pelos ids guardados no evento.

Invariante que as guardas protegem: tudo que esta gravado para um ativo esta
na base do ultimo evento. Por isso nao se lanca operacao antes da data ex do
ultimo evento (ela chegaria na base antiga), e so o ultimo evento de um ativo,
sem operacao depois dele, pode ser excluido.
"""

import json

from db import encode_metadata, new_id, parse_metadata_value, row_to_dict
from money import rounded_money
from validators import ValidationError, parse_number, require_choice, require_date, safe_float

ACTION_TYPES = {"SPLIT", "REVERSE_SPLIT", "BONUS"}
ACTION_LABELS = {"SPLIT": "desdobramento", "REVERSE_SPLIT": "grupamento", "BONUS": "bonificação"}
# Renda fixa e gado nao tem evento corporativo.
ELIGIBLE_ASSET_CLASSES = {"STOCKS", "REIT"}
QUANTITY_PLACES = 6
# Preco por cota, nao valor em dinheiro: fica com 6 casas para que
# quantidade x preco continue dando o mesmo total depois de um 1:3.
UNIT_PRICE_PLACES = 6


def action_factor(action):
    """Quantas cotas novas por cota antiga (so desdobramento e grupamento)."""
    return safe_float(action["ratio_to"]) / safe_float(action["ratio_from"])


def serialize_corporate_action(row):
    item = row_to_dict(row)
    item["adjusted_ids"] = parse_metadata_value(item.get("adjusted_ids")) or {}
    item["label"] = ACTION_LABELS.get(item.get("action_type"), item.get("action_type"))
    return item


def fetch_corporate_action(conn, current_user_id, action_id):
    return conn.execute(
        "SELECT * FROM corporate_actions WHERE id = ? AND user_id = ?",
        (action_id, current_user_id),
    ).fetchone()


def list_corporate_actions(conn, current_user_id, asset_id=None):
    sql = """
        SELECT ca.*, a.ticker, a.asset_class
        FROM corporate_actions ca
        JOIN assets a ON a.id = ca.asset_id AND a.user_id = ca.user_id
        WHERE ca.user_id = ?
    """
    params = [current_user_id]
    if asset_id:
        sql += " AND ca.asset_id = ?"
        params.append(asset_id)
    sql += " ORDER BY ca.ex_date DESC, ca.created_at DESC"
    return [serialize_corporate_action(row) for row in conn.execute(sql, params).fetchall()]


def latest_action(conn, current_user_id, asset_id):
    return conn.execute(
        """
        SELECT * FROM corporate_actions
        WHERE user_id = ? AND asset_id = ?
        ORDER BY ex_date DESC, created_at DESC
        LIMIT 1
        """,
        (current_user_id, asset_id),
    ).fetchone()


def ensure_outside_corporate_actions(conn, current_user_id, asset_id, transaction_date, previous_date=None):
    """Recusa uma operacao (nova, ou com a data mudada) antes do ultimo evento.

    Ela entraria gravada na base antiga (antes do desdobramento), e nada a
    reescalaria. Editar uma operacao antiga sem mudar a data continua valendo:
    os valores dela ja estao na base nova.
    """
    action = latest_action(conn, current_user_id, asset_id)
    if not action or not transaction_date:
        return
    ex_date = action["ex_date"]
    new_before = str(transaction_date)[:10] < ex_date
    if previous_date is None:
        crosses = new_before
    else:
        crosses = new_before != (str(previous_date)[:10] < ex_date)
    if crosses:
        label = ACTION_LABELS.get(action["action_type"], "evento")
        raise ValidationError(
            f"Ha um {label} em {ex_date} neste ativo, e as operacoes anteriores ja estao ajustadas a ele. "
            "Exclua o evento, lance a operacao e registre o evento de novo."
        )


def asset_rows(conn, current_user_id, asset_id, before_date=None):
    sql = "SELECT * FROM investment_transactions WHERE user_id = ? AND asset_id = ?"
    params = [current_user_id, asset_id]
    if before_date:
        sql += " AND transaction_date < ?"
        params.append(before_date)
    return conn.execute(sql + " ORDER BY transaction_date, created_at", params).fetchall()


def read_action_payload(conn, current_user_id, payload):
    asset_id = str(payload.get("asset_id") or "").strip()
    asset = conn.execute(
        "SELECT id, asset_class, ticker FROM assets WHERE id = ? AND user_id = ?",
        (asset_id, current_user_id),
    ).fetchone()
    if not asset:
        raise ValidationError("Ativo nao encontrado.")
    if asset["asset_class"] not in ELIGIBLE_ASSET_CLASSES:
        raise ValidationError("Evento corporativo so vale para acoes e fundos imobiliarios.")

    action_type = require_choice(payload, "action_type", "Tipo de evento", ACTION_TYPES)
    ex_date = require_date(payload, "ex_date", "Data ex")
    ratio_from = parse_number(payload, "ratio_from", "Proporcao (de)", minimum=0, allow_zero=False)
    ratio_to = parse_number(payload, "ratio_to", "Proporcao (para)", minimum=0, allow_zero=False)
    if action_type == "SPLIT" and ratio_to <= ratio_from:
        raise ValidationError("No desdobramento cada cota vira mais de uma: use, por exemplo, 1 para 2.")
    if action_type == "REVERSE_SPLIT" and ratio_to >= ratio_from:
        raise ValidationError("No grupamento varias cotas viram uma: use, por exemplo, 10 para 1.")
    bonus_unit_cost = None
    if action_type == "BONUS":
        bonus_unit_cost = 0.0
        if payload.get("bonus_unit_cost") not in (None, ""):
            bonus_unit_cost = parse_number(payload, "bonus_unit_cost", "Custo atribuido", minimum=0)
    notes = str(payload.get("notes") or "").strip()[:500] or None
    return asset, {
        "action_type": action_type,
        "ex_date": ex_date,
        "ratio_from": ratio_from,
        "ratio_to": ratio_to,
        "bonus_unit_cost": bonus_unit_cost,
        "notes": notes,
    }


def create_corporate_action(conn, current_user_id, payload):
    asset, fields = read_action_payload(conn, current_user_id, payload)
    asset_id = asset["id"]
    ex_date = fields["ex_date"]

    previous = latest_action(conn, current_user_id, asset_id)
    if previous and ex_date < previous["ex_date"]:
        raise ValidationError(
            f"Ja existe um evento em {previous['ex_date']}; registre os eventos em ordem de data."
        )

    rows = asset_rows(conn, current_user_id, asset_id, before_date=ex_date)
    held = sum(safe_float(row["quantity"]) for row in rows)
    if held <= 0.000001:
        raise ValidationError(f"Nenhuma posicao em {asset['ticker']} antes de {ex_date}.")

    action_id = new_id()
    adjusted = {"transactions": [], "quotes": []}
    bonus_transaction_id = None

    if fields["action_type"] in ("SPLIT", "REVERSE_SPLIT"):
        factor = fields["ratio_to"] / fields["ratio_from"]
        for row in rows:
            rescale_transaction(conn, current_user_id, row, factor, action_id)
            adjusted["transactions"].append(row["id"])
        # Cotacoes do ativo anteriores a data ex (manuais ou do mercado) vao
        # para a base nova; a cotacao seguinte do mercado ja vem nela.
        for quote in conn.execute(
            """
            SELECT id, price FROM price_quotes
            WHERE user_id = ? AND asset_id = ? AND substr(quoted_at, 1, 10) < ?
            """,
            (current_user_id, asset_id, ex_date),
        ).fetchall():
            conn.execute(
                "UPDATE price_quotes SET price = ? WHERE id = ? AND user_id = ?",
                (round(safe_float(quote["price"]) / factor, UNIT_PRICE_PLACES), quote["id"], current_user_id),
            )
            adjusted["quotes"].append(quote["id"])
    else:
        quantity = round(held * fields["ratio_to"] / fields["ratio_from"], QUANTITY_PLACES)
        if quantity <= 0:
            raise ValidationError("A bonificacao nao gera nenhuma cota nova com essa posicao.")
        unit_cost = fields["bonus_unit_cost"] or 0.0
        bonus_transaction_id = new_id()
        conn.execute(
            """
            INSERT INTO investment_transactions
            (id, user_id, asset_id, movement_type, quantity, unit_price, gross_amount,
             fee_amount, transaction_date, metadata)
            VALUES (?, ?, ?, 'BUY', ?, ?, ?, 0, ?, ?)
            """,
            (
                bonus_transaction_id,
                current_user_id,
                asset_id,
                quantity,
                unit_cost,
                rounded_money(quantity * unit_cost),
                ex_date,
                encode_metadata({
                    "purchase_date": ex_date,
                    "corporate_action_id": action_id,
                    "is_bonus": True,
                    "other_costs": 0,
                }),
            ),
        )

    conn.execute(
        """
        INSERT INTO corporate_actions
        (id, user_id, asset_id, action_type, ex_date, ratio_from, ratio_to,
         bonus_unit_cost, bonus_transaction_id, adjusted_ids, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            action_id,
            current_user_id,
            asset_id,
            fields["action_type"],
            ex_date,
            fields["ratio_from"],
            fields["ratio_to"],
            fields["bonus_unit_cost"],
            bonus_transaction_id,
            json.dumps(adjusted),
            fields["notes"],
        ),
    )
    return serialize_corporate_action(fetch_corporate_action(conn, current_user_id, action_id))


def rescale_transaction(conn, current_user_id, row, factor, action_id):
    """Quantidade x fator, precos / fator; o original fica no metadata."""
    metadata = parse_metadata_value(row["metadata"]) or {}
    adjustments = list(metadata.get("corporate_adjustments") or [])
    adjustments.append({
        "action_id": action_id,
        "factor": factor,
        "quantity_before": safe_float(row["quantity"]),
        "unit_price_before": safe_float(row["unit_price"]),
    })
    metadata["corporate_adjustments"] = adjustments
    if metadata.get("sale_price") not in (None, ""):
        metadata["sale_price"] = round(safe_float(metadata["sale_price"]) / factor, UNIT_PRICE_PLACES)
    conn.execute(
        """
        UPDATE investment_transactions
        SET quantity = ?, unit_price = ?, metadata = ?,
            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        WHERE id = ? AND user_id = ?
        """,
        (
            round(safe_float(row["quantity"]) * factor, QUANTITY_PLACES),
            round(safe_float(row["unit_price"]) / factor, UNIT_PRICE_PLACES),
            encode_metadata(metadata),
            row["id"],
            current_user_id,
        ),
    )


def revert_transaction(conn, current_user_id, row, action_id):
    metadata = parse_metadata_value(row["metadata"]) or {}
    adjustments = list(metadata.get("corporate_adjustments") or [])
    entry = next((item for item in adjustments if item.get("action_id") == action_id), None)
    if entry is None:
        return
    adjustments.remove(entry)
    if adjustments:
        metadata["corporate_adjustments"] = adjustments
    else:
        metadata.pop("corporate_adjustments", None)
    factor = safe_float(entry.get("factor")) or 1
    if metadata.get("sale_price") not in (None, ""):
        metadata["sale_price"] = round(safe_float(metadata["sale_price"]) * factor, UNIT_PRICE_PLACES)
    conn.execute(
        """
        UPDATE investment_transactions
        SET quantity = ?, unit_price = ?, metadata = ?,
            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        WHERE id = ? AND user_id = ?
        """,
        (
            entry.get("quantity_before", round(safe_float(row["quantity"]) / factor, QUANTITY_PLACES)),
            entry.get("unit_price_before", round(safe_float(row["unit_price"]) * factor, UNIT_PRICE_PLACES)),
            encode_metadata(metadata),
            row["id"],
            current_user_id,
        ),
    )


def delete_corporate_action(conn, current_user_id, action_id):
    """Desfaz o evento. So o ultimo do ativo, e sem operacao depois da data ex."""
    action = fetch_corporate_action(conn, current_user_id, action_id)
    if not action:
        raise LookupError("Evento nao encontrado.")
    latest = latest_action(conn, current_user_id, action["asset_id"])
    if latest and latest["id"] != action["id"]:
        raise ValidationError(
            f"Ha um evento mais recente neste ativo ({latest['ex_date']}); exclua-o primeiro."
        )
    later = conn.execute(
        """
        SELECT COUNT(*) FROM investment_transactions
        WHERE user_id = ? AND asset_id = ? AND transaction_date >= ?
          AND id <> COALESCE(?, '')
        """,
        (current_user_id, action["asset_id"], action["ex_date"], action["bonus_transaction_id"]),
    ).fetchone()[0]
    if later:
        raise ValidationError(
            f"Ha {later} operacao(oes) a partir de {action['ex_date']} feitas na base nova; "
            "exclua-as antes de desfazer o evento."
        )

    adjusted = parse_metadata_value(action["adjusted_ids"]) or {}
    if action["action_type"] in ("SPLIT", "REVERSE_SPLIT"):
        factor = action_factor(action)
        for transaction_id in adjusted.get("transactions") or []:
            row = conn.execute(
                "SELECT * FROM investment_transactions WHERE id = ? AND user_id = ?",
                (transaction_id, current_user_id),
            ).fetchone()
            if row:
                revert_transaction(conn, current_user_id, row, action_id)
        for quote_id in adjusted.get("quotes") or []:
            quote = conn.execute(
                "SELECT price FROM price_quotes WHERE id = ? AND user_id = ?", (quote_id, current_user_id),
            ).fetchone()
            if quote:
                conn.execute(
                    "UPDATE price_quotes SET price = ? WHERE id = ? AND user_id = ?",
                    (round(safe_float(quote["price"]) * factor, UNIT_PRICE_PLACES), quote_id, current_user_id),
                )
    elif action["bonus_transaction_id"]:
        conn.execute(
            "DELETE FROM investment_transactions WHERE id = ? AND user_id = ?",
            (action["bonus_transaction_id"], current_user_id),
        )

    conn.execute("DELETE FROM corporate_actions WHERE id = ? AND user_id = ?", (action_id, current_user_id))
    return row_to_dict(action)


def is_bonus_movement(metadata):
    return bool((metadata or {}).get("corporate_action_id"))
