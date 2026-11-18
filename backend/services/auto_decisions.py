"""O registro das decisoes automaticas (058, dono 2026-11-18: "tudo automatico").

O que o app antes perguntava ao dono, agora decide por uma regra escrita; cada
decisao fica aqui, visivel e desfazivel (nunca uma perda calada). `kind` e a
regra:

- `pluggy_category`: a categoria da Pluggy entrou numa linha ainda na padrao
  (open_finance_inbox.settle_review);
- `auto_confirm`: a linha saiu da revisao sozinha depois de N dias
  (services/review_auto.py);
- `transfer_guess`: a ponta so da Corretora virou aporte/resgate com o banco
  adivinhado (services/transfer_timeouts.py);
- `fx_fallback`: o valor em outra moeda entrou pela ultima PTAX antes do dia
  (open_finance_auto.in_reais_now);
- `conflict_changed` / `conflict_vanished`: o conflito da Pluggy que se
  resolveu sozinho (services/conflict_resolution.py).

`detail` (JSON) guarda o antes, para o "Desfazer" (services/auto_undo.py).
Desfeita, a regra nunca volta a decidir o mesmo lancamento (`was_undone()`).
Cada decisao tambem vai para o log (applog), uma linha.
"""

import json

from applog import get_logger
from db import new_id, utc_timestamp

logger = get_logger(__name__)

PLUGGY_CATEGORY = "pluggy_category"
AUTO_CONFIRM = "auto_confirm"
TRANSFER_GUESS = "transfer_guess"
FX_FALLBACK = "fx_fallback"
CONFLICT_CHANGED = "conflict_changed"
CONFLICT_VANISHED = "conflict_vanished"
# O que gravou sozinho com um palpite: "Desfazer" devolve a linha ao Revisar.
BACK_TO_REVIEW = (AUTO_CONFIRM, TRANSFER_GUESS, FX_FALLBACK)
KINDS = (PLUGGY_CATEGORY, *BACK_TO_REVIEW, CONFLICT_CHANGED, CONFLICT_VANISHED)
LIST_LIMIT = 200


def record(conn, current_user_id, kind, table, target_id, detail=None):
    decision_id = new_id()
    conn.execute(
        """
        INSERT INTO auto_decisions (id, user_id, kind, target_table, target_id, detail, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (decision_id, current_user_id, kind, table, target_id, json.dumps(detail or {}), utc_timestamp()),
    )
    logger.info(
        "Decisao automatica",
        extra={"user_id": current_user_id, "kind": kind, "table": table, "target_id": target_id},
    )
    return decision_id


def was_undone(conn, current_user_id, kind, table, target_id):
    """O dono desfez esta regra (`kind`; None = qualquer uma) neste lancamento:
    ela nao decide de novo."""
    kind_clause = "" if kind is None else " AND kind = ?"
    return conn.execute(
        f"""
        SELECT 1 FROM auto_decisions
        WHERE user_id = ? AND target_table = ? AND target_id = ? AND undone_at IS NOT NULL{kind_clause}
        LIMIT 1
        """,
        (current_user_id, table, target_id, *(() if kind is None else (kind,))),
    ).fetchone() is not None


def _serialize(row):
    try:
        detail = json.loads(row["detail"] or "{}")
    except (TypeError, ValueError):
        detail = {}
    return {
        "id": row["id"],
        "kind": row["kind"],
        "table": row["target_table"],
        "target_id": row["target_id"],
        "detail": detail,
        "created_at": row["created_at"],
        "undone_at": row["undone_at"],
    }


def fetch(conn, current_user_id, decision_id):
    row = conn.execute(
        "SELECT * FROM auto_decisions WHERE id = ? AND user_id = ?", (decision_id, current_user_id),
    ).fetchone()
    return _serialize(row) if row else None


def recent(conn, current_user_id, since=None, kinds=None, limit=LIST_LIMIT):
    """As decisoes, da mais nova para a mais antiga; `since` (texto ISO) corta."""
    clauses, params = ["user_id = ?"], [current_user_id]
    if since:
        clauses.append("created_at >= ?")
        params.append(since)
    if kinds:
        clauses.append(f"kind IN ({', '.join('?' for _ in kinds)})")
        params.extend(kinds)
    rows = conn.execute(
        f"SELECT * FROM auto_decisions WHERE {' AND '.join(clauses)} ORDER BY created_at DESC, id LIMIT ?",
        (*params, limit),
    ).fetchall()
    return [_serialize(row) for row in rows]


def counts(conn, current_user_id, since=None):
    """{kind: quantas} desde `since` (as desfeitas fora)."""
    clauses, params = ["user_id = ?", "undone_at IS NULL"], [current_user_id]
    if since:
        clauses.append("created_at >= ?")
        params.append(since)
    rows = conn.execute(
        f"SELECT kind, COUNT(*) AS total FROM auto_decisions WHERE {' AND '.join(clauses)} GROUP BY kind",
        params,
    ).fetchall()
    return {row["kind"]: row["total"] for row in rows}


def mark_undone(conn, current_user_id, decision_id):
    conn.execute(
        "UPDATE auto_decisions SET undone_at = ? WHERE id = ? AND user_id = ?",
        (utc_timestamp(), decision_id, current_user_id),
    )
