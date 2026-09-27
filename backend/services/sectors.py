"""Alocacao por setor (022): o setor de cada ativo e a carteira agrupada por ele.

De onde vem o setor:

- brapi (/quote/list, `brapi_client.get_sectors`), so para acao/ETF/BDR/FII
  em reais — a brapi e B3. O `sector` dela e uma taxonomia em ingles
  ("Finance"), traduzida aqui por SECTOR_LABELS; o `subsector` vira o
  segmento. Para FII o `sector` da brapi nao diz nada ("Finance",
  "Miscellaneous"), entao o setor de um FII e o segmento dele (Logistica,
  Shoppings, Escritorios...);
- o dono (`MANUAL`), para qualquer ativo: renda fixa, exterior, ou
  quando a brapi erra. A brapi nunca sobrescreve um setor manual.

A leitura (`build_sector_allocation`) tenta preencher, uma vez, os ativos em
carteira que nunca foram consultados; falhar na brapi nao falha a leitura — o
ativo fica em "Sem setor" e a resposta diz o porque. "Buscar setores"
(`refresh_sectors`) pergunta de novo por todos os nao-manuais.

O valor por setor e o liquido (`net_value`) de build_portfolio_snapshot(), o
mesmo da alocacao por classe — calculado na leitura, nunca gravado.
"""

import brapi_client
from applog import get_logger
from asset_classes import ASSET_CLASS_LABELS, QUOTED_ASSET_CLASSES
from db import get_db, utc_timestamp
from integrations import record_provider_result
from money import rounded_money
from services.allocation import percent_of
from services.investments import ensure_asset_owner
from services.portfolio import build_portfolio_snapshot
from validators import ValidationError, safe_float

logger = get_logger(__name__)

NO_SECTOR_LABEL = "Sem setor"
MAX_SECTOR_LENGTH = 60

# Taxonomia da brapi (`availableSectors` da /quote/list, 2026-09-26).
SECTOR_LABELS = {
    "Retail Trade": "Varejo",
    "Energy Minerals": "Petróleo e gás",
    "Health Services": "Serviços de saúde",
    "Utilities": "Utilidade pública",
    "Finance": "Financeiro",
    "Consumer Services": "Serviços ao consumidor",
    "Consumer Non-Durables": "Bens de consumo não duráveis",
    "Non-Energy Minerals": "Mineração e siderurgia",
    "Commercial Services": "Serviços comerciais",
    "Distribution Services": "Distribuição",
    "Transportation": "Transporte",
    "Technology Services": "Serviços de tecnologia",
    "Process Industries": "Indústrias de processo",
    "Communications": "Comunicações",
    "Producer Manufacturing": "Bens industriais",
    "Miscellaneous": "Diversos",
    "Electronic Technology": "Tecnologia eletrônica",
    "Industrial Services": "Serviços industriais",
    "Health Technology": "Tecnologia em saúde",
    "Consumer Durables": "Bens de consumo duráveis",
}


def sector_from_brapi(info, asset_class):
    """(setor, segmento) em portugues a partir de um SectorInfo, ou (None, None)."""
    if info is None:
        return None, None
    segment = info.subsector or None
    if asset_class == "REIT" or info.sub_type == "fii":
        return segment, segment
    if not info.sector:
        return None, segment
    return SECTOR_LABELS.get(info.sector, info.sector), segment


def fetchable(asset):
    """So acao/FII em reais: a brapi e B3."""
    return (
        asset["asset_class"] in QUOTED_ASSET_CLASSES
        and str(asset["currency"] or "BRL").upper() == "BRL"
        and asset["sector_source"] != "MANUAL"
    )


def fill_sectors_from_brapi(current_user_id, asset_ids=None, *, only_unchecked=True, force=False):
    """Consulta a brapi e grava o setor dos ativos elegiveis do usuario.

    Devolve {"status": ok|unconfigured|error|skipped, "message": str|None,
    "updated": n}. Um ativo que a brapi nao conhece fica com checked_at
    preenchido e setor vazio, para a leitura nao perguntar de novo a cada vez.
    """
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, ticker, asset_class, currency, sector_source, sector_checked_at
            FROM assets
            WHERE user_id = ?
            """,
            (current_user_id,),
        ).fetchall()
    wanted_ids = set(asset_ids) if asset_ids is not None else None
    candidates = [
        row for row in rows
        if fetchable(row)
        and (wanted_ids is None or row["id"] in wanted_ids)
        and not (only_unchecked and (row["sector_source"] or row["sector_checked_at"]))
    ]
    if not candidates:
        return {"status": "skipped", "message": None, "updated": 0}
    if not brapi_client.is_configured():
        return {
            "status": "unconfigured",
            "message": "BRAPI_TOKEN nao configurado: o setor so pode ser preenchido a mao.",
            "updated": 0,
        }

    symbols = [brapi_client.normalize_symbol(row["ticker"]) for row in candidates]
    try:
        found = brapi_client.get_sectors(symbols, force=force)
    except brapi_client.BrapiError as exc:
        logger.warning(f"Erro ao consultar setores na brapi: {exc}")
        record_provider_result("brapi", False, exc)
        return {
            "status": "error",
            "message": "Nao foi possivel consultar os setores na brapi agora.",
            "updated": 0,
        }
    record_provider_result("brapi", True)

    now = utc_timestamp()
    updated = 0
    with get_db() as conn:
        for row in candidates:
            info = found.get(brapi_client.normalize_symbol(row["ticker"]))
            sector, segment = sector_from_brapi(info, row["asset_class"])
            # O WHERE repete a guarda: um setor manual gravado entre a leitura
            # e esta escrita nao e sobrescrito.
            cursor = conn.execute(
                """
                UPDATE assets
                SET sector = ?, segment = ?, sector_source = ?, sector_checked_at = ?
                WHERE id = ? AND user_id = ?
                  AND (sector_source IS NULL OR sector_source <> 'MANUAL')
                """,
                (sector, segment, "BRAPI" if sector else None, now, row["id"], current_user_id),
            )
            if sector and cursor.rowcount:
                updated += 1
    return {"status": "ok", "message": None, "updated": updated}


def refresh_sectors(current_user_id):
    """"Buscar setores": pergunta de novo por todos os ativos nao-manuais."""
    return fill_sectors_from_brapi(current_user_id, only_unchecked=False, force=True)


def clean_label(value, label):
    text = " ".join(str(value or "").split())
    if len(text) > MAX_SECTOR_LENGTH:
        raise ValidationError(f"{label}: use no maximo {MAX_SECTOR_LENGTH} caracteres.")
    return text or None


def set_manual_sector(current_user_id, asset_id, payload):
    """Setor escrito pelo dono. Setor vazio devolve o ativo para a brapi."""
    if not isinstance(payload, dict) or "sector" not in payload:
        raise ValidationError("Informe o setor (vazio para voltar ao automatico).")
    sector = clean_label(payload.get("sector"), "Setor")
    segment = clean_label(payload.get("segment"), "Segmento")
    with get_db() as conn:
        asset = ensure_asset_owner(conn, current_user_id, str(asset_id))
        if sector:
            conn.execute(
                """
                UPDATE assets
                SET sector = ?, segment = ?, sector_source = 'MANUAL', sector_checked_at = NULL,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ? AND user_id = ?
                """,
                (sector, segment, asset["id"], current_user_id),
            )
        else:
            # Volta ao estado "nunca consultado": a proxima leitura pergunta a brapi.
            conn.execute(
                """
                UPDATE assets
                SET sector = NULL, segment = NULL, sector_source = NULL, sector_checked_at = NULL,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ? AND user_id = ?
                """,
                (asset["id"], current_user_id),
            )
    return asset["id"]


def asset_sector_rows(conn, current_user_id):
    rows = conn.execute(
        """
        SELECT id, ticker, asset_class, sector, segment, sector_source
        FROM assets
        WHERE user_id = ?
        """,
        (current_user_id,),
    ).fetchall()
    return {row["id"]: row for row in rows}


def build_sector_allocation(current_user_id, asset_class=None, *, fill=True):
    """Carteira agrupada por setor (valor liquido), opcionalmente de uma classe.

    Preenche antes, pela brapi, os ativos em carteira nunca consultados.
    """
    snapshot = build_portfolio_snapshot(current_user_id)
    positions = [
        position for position in snapshot.get("assets") or []
        if asset_class is None or position.get("class") == asset_class
    ]

    fetch = {"status": "skipped", "message": None, "updated": 0}
    held_ids = {position.get("asset_id") for position in positions if position.get("asset_id")}
    if fill and held_ids:
        fetch = fill_sectors_from_brapi(current_user_id, held_ids)

    with get_db() as conn:
        sector_rows = asset_sector_rows(conn, current_user_id)

    # Renda fixa pode ter varias aplicacoes do mesmo ativo: agrupa por ativo.
    by_asset = {}
    for position in positions:
        key = position.get("asset_id") or position.get("id")
        row = sector_rows.get(position.get("asset_id"))
        entry = by_asset.setdefault(key, {
            "asset_id": position.get("asset_id"),
            "ticker": position.get("ticker"),
            "asset_class": position.get("class"),
            "sector": row["sector"] if row else None,
            "segment": row["segment"] if row else None,
            "source": row["sector_source"] if row else None,
            "value": 0.0,
        })
        entry["value"] += safe_float(position.get("net_value"))

    total = sum(entry["value"] for entry in by_asset.values())

    buckets = {}
    for entry in by_asset.values():
        bucket = buckets.setdefault(entry["sector"], {"value": 0.0, "assets": [], "classes": set()})
        bucket["value"] += entry["value"]
        bucket["classes"].add(entry["asset_class"])
        bucket["assets"].append(entry)

    sectors = []
    for sector, bucket in buckets.items():
        assets = sorted(bucket["assets"], key=lambda item: (-item["value"], str(item["ticker"])))
        sectors.append({
            "sector": sector,
            "label": sector or NO_SECTOR_LABEL,
            "value": rounded_money(bucket["value"]),
            "percent": percent_of(bucket["value"], total),
            "classes": sorted(bucket["classes"]),
            "assets": [
                {
                    "asset_id": item["asset_id"],
                    "ticker": item["ticker"],
                    "asset_class": item["asset_class"],
                    "class_label": ASSET_CLASS_LABELS.get(item["asset_class"], item["asset_class"]),
                    "segment": item["segment"],
                    "source": item["source"],
                    "value": rounded_money(item["value"]),
                    "percent_of_total": percent_of(item["value"], total),
                    "percent_in_sector": percent_of(item["value"], bucket["value"]),
                }
                for item in assets
            ],
        })
    # Maior primeiro; "Sem setor" sempre no fim.
    sectors.sort(key=lambda item: (item["sector"] is None, -item["value"], item["label"]))

    unassigned = buckets.get(None, {}).get("value", 0.0)
    known = sorted({row["sector"] for row in sector_rows.values() if row["sector"]} | set(SECTOR_LABELS.values()))
    return {
        "asset_class": asset_class,
        "total": rounded_money(total),
        "sectors": sectors,
        "unassigned_value": rounded_money(unassigned),
        "unassigned_percent": percent_of(unassigned, total),
        "suggestions": known,
        "fetch": fetch,
    }
