"""Proventos automaticos (026): a posicao na data com vezes o valor da StatusInvest.

Para cada acao/FII em reais com operacoes, `sync_proceeds()` le o historico de
proventos do ticker (`statusinvest_client`) e, para cada evento com data com a
partir da primeira operacao, calcula a quantidade em carteira naquela data
(`accumulate_position`, a mesma regra do formulario manual). Quantidade > 0
grava (ou corrige) a linha; quantidade 0 apaga a automatica que houver. Assim
uma compra lancada com data no passado traz os proventos que pagou desde entao,
e apagar ou mover uma operacao corrige os proventos na proxima sincronizacao.

Idempotente como recorrencias e importacao: cada evento tem um `sync_key`
('<ticker>:<natureza>:<data com>:<pagamento>#n', n separa eventos iguais no
mesmo dia) e o indice unico da 026 faz uma segunda passada nao gravar nada.
O que o dono decidiu fica: linha digitada (sync_key NULL) nunca e tocada e
toma o lugar do automatico do mesmo evento (tipo + data com),
automatica editada vira `sync_locked`, e automatica excluida vai para
`proceeds_sync_dismissed` e nao volta.

A rede fica fora da transacao: primeiro os historicos (com cache de horas em
`statusinvest_client`), depois uma escrita so. Falha de um ticker nao apaga os
proventos dele — so pula o ticker.
"""

from bisect import bisect_right
from collections import defaultdict

import statusinvest_client
from applog import get_logger
from asset_classes import QUOTED_ASSET_CLASSES
from db import encode_metadata, get_db, new_id
from integrations import record_provider_result
from money import rounded_money
from services.proceeds import accumulate_position, asset_movement_rows, default_tax_for_proceed

logger = get_logger(__name__)

PROVIDER = "statusinvest"
SOURCE = "statusinvest"
QUANTITY_PLACES = 6
UNIT_VALUE_PLACES = 8


def sync_key_for(event, occurrence):
    return f"{event.ticker}:{event.kind}:{event.record_date}:{event.payment_date}#{occurrence}"


def keyed_events(events):
    """[(sync_key, evento)], com n = ordem do valor entre eventos de mesma chave."""
    groups = defaultdict(list)
    for event in events:
        groups[(event.kind, event.record_date, event.payment_date)].append(event)
    keyed = []
    for group in groups.values():
        for index, event in enumerate(sorted(group, key=lambda item: item.amount_per_unit), start=1):
            keyed.append((sync_key_for(event, index), event))
    return keyed


def desired_proceeds(movement_rows, events):
    """{sync_key: valores} dos eventos em que havia posicao na data com."""
    if not movement_rows:
        return {}
    dates = [row["transaction_date"] for row in movement_rows]
    wanted = {}
    for key, event in keyed_events(events):
        if event.record_date < dates[0]:
            continue
        position = accumulate_position(movement_rows[: bisect_right(dates, event.record_date)])
        quantity = round(position["quantity"], QUANTITY_PLACES)
        if quantity <= 0:
            continue
        gross = rounded_money(event.amount_per_unit * quantity)
        tax = rounded_money(default_tax_for_proceed(
            event.proceeds_type, gross, event.record_date, event.kind,
        ))
        if gross <= 0:
            continue
        wanted[key] = {
            "proceeds_type": event.proceeds_type,
            "kind": event.kind,
            "label": event.source_label,
            "record_date": event.record_date,
            "payment_date": event.payment_date,
            "amount_per_unit": round(event.amount_per_unit, UNIT_VALUE_PLACES),
            "eligible_quantity": quantity,
            "gross_amount": gross,
            "tax_amount": tax,
            "net_amount": rounded_money(gross - tax),
        }
    return wanted


def _changed(existing, values):
    for field in ("proceeds_type", "record_date", "payment_date"):
        if existing[field] != values[field]:
            return True
    for field, places in (("amount_per_unit", 8), ("eligible_quantity", 6),
                          ("gross_amount", 2), ("tax_amount", 2), ("net_amount", 2)):
        if abs(float(existing[field] or 0) - float(values[field])) > 0.5 * 10 ** -places:
            return True
    return False


def _candidate_assets(conn, current_user_id):
    rows = conn.execute(
        """
        SELECT a.id, a.ticker, a.asset_class, a.currency,
               EXISTS (
                   SELECT 1 FROM investment_transactions t
                   WHERE t.user_id = a.user_id AND t.asset_id = a.id
               ) AS has_movements
        FROM assets a
        WHERE a.user_id = ?
        ORDER BY a.ticker
        """,
        (current_user_id,),
    ).fetchall()
    return [
        row for row in rows
        if row["asset_class"] in QUOTED_ASSET_CLASSES
        and str(row["currency"] or "BRL").upper() == "BRL"
        and row["ticker"]
    ]


def sync_proceeds(current_user_id, *, force=False):
    """Sincroniza os proventos automaticos do usuario.

    Devolve {"status": ok|partial|error|skipped, "message", "created",
    "updated", "removed", "failed": [tickers]}. `force` ignora o cache e
    pergunta de novo a StatusInvest.
    """
    with get_db() as conn:
        assets = _candidate_assets(conn, current_user_id)

    if not assets:
        return {"status": "skipped", "message": None, "created": 0, "updated": 0, "removed": 0, "failed": []}

    histories = {}
    failed = []
    for asset in assets:
        if not asset["has_movements"]:
            histories[asset["id"]] = []
            continue
        try:
            histories[asset["id"]] = statusinvest_client.get_proceed_events(
                asset["ticker"], asset["asset_class"], force=force,
            )
        except statusinvest_client.StatusInvestError as exc:
            logger.warning(f"Proventos de {asset['ticker']} indisponiveis: {exc}")
            record_provider_result(PROVIDER, False, exc)
            failed.append(asset["ticker"])
    if len(failed) < len([a for a in assets if a["has_movements"]]):
        record_provider_result(PROVIDER, True)

    counts = {"created": 0, "updated": 0, "removed": 0}
    with get_db() as conn:
        dismissed = {
            row["sync_key"]
            for row in conn.execute(
                "SELECT sync_key FROM proceeds_sync_dismissed WHERE user_id = ?",
                (current_user_id,),
            ).fetchall()
        }
        for asset in assets:
            if asset["id"] not in histories:
                continue
            _sync_asset(conn, current_user_id, asset, histories[asset["id"]], dismissed, counts)

    if failed and len(failed) == len([a for a in assets if a["has_movements"]]):
        status, message = "error", "Nao foi possivel consultar os proventos na StatusInvest agora."
    elif failed:
        status, message = "partial", f"Proventos nao atualizados para: {', '.join(failed)}."
    else:
        status, message = "ok", None
    return {"status": status, "message": message, **counts, "failed": failed}


def _sync_asset(conn, current_user_id, asset, events, dismissed, counts):
    movements = asset_movement_rows(conn, current_user_id, asset["id"]) if events else []
    wanted = desired_proceeds(movements, events)
    existing = {
        row["sync_key"]: row
        for row in conn.execute(
            """
            SELECT id, sync_key, sync_locked, proceeds_type, record_date, payment_date,
                   amount_per_unit, eligible_quantity, gross_amount, tax_amount, net_amount
            FROM investment_proceeds
            WHERE user_id = ? AND asset_id = ? AND sync_key IS NOT NULL
            """,
            (current_user_id, asset["id"]),
        ).fetchall()
    }

    # Provento digitado pelo dono para o mesmo evento (tipo + data com) vale
    # no lugar do automatico: sem isso o mesmo dividendo contaria duas vezes.
    typed = {
        (row["proceeds_type"], row["record_date"])
        for row in conn.execute(
            """
            SELECT proceeds_type, record_date
            FROM investment_proceeds
            WHERE user_id = ? AND asset_id = ? AND sync_key IS NULL
            """,
            (current_user_id, asset["id"]),
        ).fetchall()
    }
    wanted = {
        key: values for key, values in wanted.items()
        if (values["proceeds_type"], values["record_date"]) not in typed
    }

    for key, values in wanted.items():
        if key in dismissed:
            continue
        current = existing.get(key)
        metadata = encode_metadata({"kind": values["kind"], "source_label": values["label"]})
        if current is None:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO investment_proceeds
                (
                    id, user_id, asset_id, proceeds_type, record_date, payment_date,
                    amount_per_unit, eligible_quantity, gross_amount, tax_amount,
                    net_amount, source, notes, metadata, sync_key
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id(), current_user_id, asset["id"], values["proceeds_type"],
                    values["record_date"], values["payment_date"], values["amount_per_unit"],
                    values["eligible_quantity"], values["gross_amount"], values["tax_amount"],
                    values["net_amount"], SOURCE, "", metadata, key,
                ),
            )
            counts["created"] += cursor.rowcount
            continue
        if current["sync_locked"] or not _changed(current, values):
            continue
        conn.execute(
            """
            UPDATE investment_proceeds
            SET proceeds_type = ?, record_date = ?, payment_date = ?,
                amount_per_unit = ?, eligible_quantity = ?, gross_amount = ?,
                tax_amount = ?, net_amount = ?, metadata = ?,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = ? AND user_id = ? AND sync_locked = 0
            """,
            (
                values["proceeds_type"], values["record_date"], values["payment_date"],
                values["amount_per_unit"], values["eligible_quantity"], values["gross_amount"],
                values["tax_amount"], values["net_amount"], metadata,
                current["id"], current_user_id,
            ),
        )
        counts["updated"] += 1

    for key, current in existing.items():
        if key in wanted or current["sync_locked"]:
            continue
        conn.execute(
            "DELETE FROM investment_proceeds WHERE id = ? AND user_id = ? AND sync_locked = 0",
            (current["id"], current_user_id),
        )
        counts["removed"] += 1
