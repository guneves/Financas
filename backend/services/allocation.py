"""Alocacao alvo da carteira (020): atual x meta, e para onde vai o proximo aporte.

Dois niveis, na mesma forma que a tela le a carteira:

- classe: percentual da carteira inteira (`scope = 'CLASS'`);
- ativo: percentual DENTRO da classe (`scope = 'ASSET'`).

O valor de cada posicao e o liquido (`net_value` de build_portfolio_snapshot),
o mesmo da distribuicao da Posicao. Renda fixa e agrupada por ativo (um
titulo pode ter varias aplicacoes).

Sugestao de aporte, sem vender nada: com a carteira depois do aporte
(total + aporte), cada classe com meta precisa de `meta% x total_novo - atual`;
o aporte e repartido na proporcao dessas faltas (so as positivas). Dentro da
classe, o valor que coube a ela e repartido do mesmo jeito entre os ativos com
meta. Proporcional, nao "encher o mais atrasado primeiro": e facil de
conferir de cabeca e nunca manda tudo para um ativo so. A soma das faltas
positivas e sempre >= aporte quando as metas somam 100%, entao a divisao
nunca precisa de sobra.

Concentracao (`concentration` na resposta): cada ativo acima de
`CONCENTRATION_THRESHOLD`% do valor liquido da carteira vira um aviso, e a
carteira sem nenhum ativo em moeda estrangeira ganha uma nota de que nao ha
exposicao ao exterior. Nao ha classe "exterior": o que conta e a moeda do
ativo (018).
"""

from asset_classes import ALLOWED_ASSET_CLASSES, ASSET_CLASS_LABELS, QUOTED_ASSET_CLASSES
from db import get_db, new_id
from money import rounded_money
from services.investments import ensure_asset_owner
from services.portfolio import build_portfolio_snapshot
from validators import ValidationError, safe_float

# Um ativo acima disto (% do valor liquido da carteira) pede atencao.
CONCENTRATION_THRESHOLD = 10.0

# Tolerancia da soma das metas: 33,33 + 33,33 + 33,34 fecha, 99,9 nao.
SUM_TOLERANCE = 0.01


def fetch_targets(conn, current_user_id):
    rows = conn.execute(
        """
        SELECT scope, asset_class, asset_id, target_percent
        FROM allocation_targets
        WHERE user_id = ?
        """,
        (current_user_id,),
    ).fetchall()
    classes = {}
    assets = {}
    for row in rows:
        if row["scope"] == "CLASS":
            classes[row["asset_class"]] = safe_float(row["target_percent"])
        else:
            assets[row["asset_id"]] = safe_float(row["target_percent"])
    return classes, assets


def percent_of(part, whole):
    return rounded_money(part / whole * 100) if whole > 0 else 0.0


def split_by_shortfall(amount, items):
    """Reparte `amount` entre `items` na proporcao de `shortfall` (> 0).

    items: lista de dicts com "key" e "shortfall". Devolve {key: valor}, com
    centavos que sobram do arredondamento no item de maior falta, para que a
    soma bata exatamente com o aporte.
    """
    positive = [item for item in items if item["shortfall"] > 0]
    total = sum(item["shortfall"] for item in positive)
    if amount <= 0 or total <= 0:
        return {}
    shares = {item["key"]: rounded_money(amount * item["shortfall"] / total) for item in positive}
    residual = rounded_money(amount - sum(shares.values()))
    if residual:
        largest = max(positive, key=lambda item: item["shortfall"])["key"]
        shares[largest] = rounded_money(shares[largest] + residual)
    return shares


def group_positions(snapshot):
    """{classe: {asset_id: posicao agregada}} a partir das posicoes da carteira."""
    classes = {}
    for position in snapshot.get("assets") or []:
        asset_class = position.get("class")
        key = position.get("asset_id") or position.get("id")
        bucket = classes.setdefault(asset_class, {})
        entry = bucket.setdefault(key, {
            "asset_id": position.get("asset_id"),
            "ticker": position.get("ticker"),
            "value": 0.0,
            "quantity": 0.0,
            "invested": 0.0,
            "current_price": position.get("current_price"),
            "average_price": position.get("average_price"),
        })
        entry["value"] += safe_float(position.get("net_value"))
        entry["quantity"] += safe_float(position.get("quantity"))
        entry["invested"] += safe_float(position.get("total_invested"))
    return classes


def asset_labels(conn, current_user_id, asset_ids):
    if not asset_ids:
        return {}
    placeholders = ", ".join("?" for _ in asset_ids)
    rows = conn.execute(
        f"""
        SELECT id, ticker, asset_class FROM assets
        WHERE user_id = ? AND id IN ({placeholders})
        """,
        (current_user_id, *asset_ids),
    ).fetchall()
    return {row["id"]: row for row in rows}


def build_concentration(grouped, snapshot, total):
    """Ativos acima do limite e a exposicao em moeda estrangeira.

    `grouped` e o de group_positions() (valor liquido por ativo); o percentual
    e sobre o mesmo total da tela. Um ativo sem posicao (so com meta) vale 0 e
    nunca entra.
    """
    over = []
    if total > 0:
        for asset_class, bucket in grouped.items():
            for entry in bucket.values():
                share = entry["value"] / total * 100
                if share > CONCENTRATION_THRESHOLD:
                    over.append({
                        "asset_id": entry["asset_id"],
                        "ticker": entry["ticker"],
                        "asset_class": asset_class,
                        "value": rounded_money(entry["value"]),
                        "percent": rounded_money(share),
                    })
    over.sort(key=lambda item: (-item["percent"], str(item["ticker"])))

    foreign_value = 0.0
    currencies = set()
    for position in snapshot.get("assets") or []:
        currency = str(position.get("currency") or "BRL").upper()
        if currency != "BRL" and safe_float(position.get("net_value")) > 0:
            foreign_value += safe_float(position.get("net_value"))
            currencies.add(currency)

    return {
        "threshold_percent": CONCENTRATION_THRESHOLD,
        "assets_over_threshold": over,
        "has_foreign_exposure": bool(currencies),
        "foreign_currencies": sorted(currencies),
        "foreign_value": rounded_money(foreign_value),
        "foreign_percent": percent_of(foreign_value, total),
    }


def build_allocation(current_user_id, contribution=0.0):
    snapshot = build_portfolio_snapshot(current_user_id)
    grouped = group_positions(snapshot)
    contribution = rounded_money(max(safe_float(contribution), 0.0))

    with get_db() as conn:
        class_targets, asset_targets = fetch_targets(conn, current_user_id)
        held_ids = {key for bucket in grouped.values() for key in bucket}
        # Ativo com meta e sem posicao (vendeu tudo, ou quer comecar a comprar)
        # tambem aparece: e justamente para onde o aporte deve ir.
        missing = [asset_id for asset_id in asset_targets if asset_id not in held_ids]
        labels = asset_labels(conn, current_user_id, missing)
    for asset_id in missing:
        row = labels.get(asset_id)
        if not row:
            continue
        grouped.setdefault(row["asset_class"], {})[asset_id] = {
            "asset_id": asset_id,
            "ticker": row["ticker"],
            "value": 0.0,
            "quantity": 0.0,
            "invested": 0.0,
            "current_price": None,
            "average_price": None,
        }

    total = sum(entry["value"] for bucket in grouped.values() for entry in bucket.values())
    total_after = total + contribution
    has_class_targets = bool(class_targets)

    class_keys = sorted(
        set(grouped) | set(class_targets),
        key=lambda key: (-sum(e["value"] for e in grouped.get(key, {}).values()), key),
    )

    class_shares = {}
    if contribution and has_class_targets:
        class_shares = split_by_shortfall(contribution, [
            {
                "key": key,
                "shortfall": class_targets.get(key, 0.0) / 100 * total_after
                - sum(e["value"] for e in grouped.get(key, {}).values()),
            }
            for key in class_keys
        ])

    classes = []
    opportunities = []
    for key in class_keys:
        bucket = grouped.get(key, {})
        value = sum(entry["value"] for entry in bucket.values())
        target = class_targets.get(key) if has_class_targets else None
        target_value = target / 100 * total if target is not None else None
        suggested = class_shares.get(key, 0.0)
        class_asset_targets = {
            asset_id: pct for asset_id, pct in asset_targets.items() if asset_id in bucket
        }
        value_after = value + suggested

        asset_shares = {}
        if suggested and class_asset_targets:
            asset_shares = split_by_shortfall(suggested, [
                {
                    "key": asset_id,
                    "shortfall": class_asset_targets.get(asset_id, 0.0) / 100 * value_after
                    - entry["value"],
                }
                for asset_id, entry in bucket.items()
            ])

        assets = []
        for asset_id, entry in sorted(bucket.items(), key=lambda item: (-item[1]["value"], str(item[1]["ticker"]))):
            asset_target = class_asset_targets.get(asset_id) if class_asset_targets else None
            percent_in_class = percent_of(entry["value"], value)
            average_price = entry.get("average_price")
            current_price = entry.get("current_price")
            below_average = bool(
                key in QUOTED_ASSET_CLASSES
                and entry["quantity"] > 0
                and safe_float(average_price) > 0
                and safe_float(current_price) > 0
                and safe_float(current_price) < safe_float(average_price)
            )
            under_target = asset_target is not None and percent_in_class < asset_target
            item = {
                "asset_id": entry["asset_id"],
                "ticker": entry["ticker"],
                "value": rounded_money(entry["value"]),
                "percent_in_class": percent_in_class,
                "percent_of_total": percent_of(entry["value"], total),
                "target_percent": asset_target,
                "diff_percent": rounded_money(percent_in_class - asset_target) if asset_target is not None else None,
                "gap_value": (
                    rounded_money(asset_target / 100 * value - entry["value"])
                    if asset_target is not None else None
                ),
                "suggested": asset_shares.get(asset_id, 0.0),
                "current_price": current_price,
                "average_price": average_price,
                "below_average_price": below_average,
            }
            assets.append(item)
            # "Oportunidade": abaixo da meta dentro da classe E cotado abaixo
            # do preco medio — comprar agora reduz o medio e aproxima da meta.
            if under_target and below_average:
                opportunities.append({**item, "asset_class": key})

        asset_targets_total = sum(class_asset_targets.values())
        classes.append({
            "asset_class": key,
            "label": ASSET_CLASS_LABELS.get(key, key),
            "value": rounded_money(value),
            "percent": percent_of(value, total),
            "target_percent": target,
            "diff_percent": rounded_money(percent_of(value, total) - target) if target is not None else None,
            "gap_value": rounded_money(target_value - value) if target_value is not None else None,
            "suggested": suggested,
            "has_asset_targets": bool(class_asset_targets),
            "asset_targets_total": rounded_money(asset_targets_total),
            "assets": assets,
        })

    return {
        "total": rounded_money(total),
        "contribution": contribution,
        "has_targets": has_class_targets or bool(asset_targets),
        "has_class_targets": has_class_targets,
        "classes": classes,
        "opportunities": opportunities,
        "concentration": build_concentration(grouped, snapshot, total),
    }


def parse_percent(value, label):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{label}: percentual invalido.")
    if not (0 <= number <= 100):
        raise ValidationError(f"{label}: o percentual deve ficar entre 0 e 100.")
    return rounded_money(number)


def check_sum(values, label):
    total = sum(values)
    if abs(total - 100) > SUM_TOLERANCE:
        raise ValidationError(
            f"{label} somam {str(rounded_money(total)).replace('.', ',')}%; precisam somar 100%."
        )


def replace_targets(current_user_id, payload):
    """Troca o conjunto inteiro de metas. Lista vazia apaga as metas daquele nivel.

    payload: {"classes": {"STOCKS": 60, ...}, "assets": {"<asset_id>": 25, ...}}.
    Metas de classe somam 100%; metas de ativo somam 100% dentro de cada
    classe que tenha alguma. Um ativo sem meta numa classe com metas conta
    como 0% — a tela mostra que ele esta acima do plano.
    """
    raw_classes = payload.get("classes") or {}
    raw_assets = payload.get("assets") or {}
    if not isinstance(raw_classes, dict) or not isinstance(raw_assets, dict):
        raise ValidationError("Envie as metas como {classes: {...}, assets: {...}}.")

    class_rows = {}
    for key, value in raw_classes.items():
        asset_class = str(key or "").strip().upper()
        if asset_class not in ALLOWED_ASSET_CLASSES:
            raise ValidationError(f"Classe de ativo invalida: {key}.")
        class_rows[asset_class] = parse_percent(value, ASSET_CLASS_LABELS.get(asset_class, asset_class))
    if class_rows:
        check_sum(class_rows.values(), "As metas das classes")

    with get_db() as conn:
        asset_rows = {}
        by_class = {}
        for asset_id, value in raw_assets.items():
            asset = ensure_asset_owner(conn, current_user_id, str(asset_id))
            percent = parse_percent(value, asset["ticker"])
            asset_rows[asset["id"]] = (asset["asset_class"], percent)
            by_class.setdefault(asset["asset_class"], []).append(percent)
        for asset_class, values in by_class.items():
            check_sum(values, f"As metas dos ativos de {ASSET_CLASS_LABELS.get(asset_class, asset_class)}")

        conn.execute("DELETE FROM allocation_targets WHERE user_id = ?", (current_user_id,))
        for asset_class, percent in class_rows.items():
            conn.execute(
                """
                INSERT INTO allocation_targets (id, user_id, scope, asset_class, asset_id, target_percent)
                VALUES (?, ?, 'CLASS', ?, NULL, ?)
                """,
                (new_id(), current_user_id, asset_class, percent),
            )
        for asset_id, (asset_class, percent) in asset_rows.items():
            conn.execute(
                """
                INSERT INTO allocation_targets (id, user_id, scope, asset_class, asset_id, target_percent)
                VALUES (?, ?, 'ASSET', ?, ?, ?)
                """,
                (new_id(), current_user_id, asset_class, asset_id, percent),
            )
