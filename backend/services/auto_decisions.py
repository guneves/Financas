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
  resolveu sozinho (services/conflict_resolution.py);
- a carteira (fase 2, alvo `open_finance_investment_operations`):
  `investment_custody` (a TRANSFER de renda variavel que so registra a
  custodia), `investment_proceed_link` (o INTEREST de uma acao ligado ao
  provento calculado), `investment_closed_fund` (a operacao de um fundo do
  banco ja zerado), `investment_custody_in` (o titulo de renda fixa que
  veio de outra corretora, gravado ao custo) e `investment_rate_deduced` (o
  titulo sem indexador gravado como pre). As tres primeiras se desfazem aqui
  (a linha volta a esperar); as duas ultimas gravaram uma operacao, que se
  desfaz apagando-a no Extrato (`undoable` falso).

`detail` (JSON) guarda o antes, para o "Desfazer" (services/auto_undo.py).
Desfeita, a regra nunca volta a decidir o mesmo lancamento (`was_undone()`).
Cada decisao tambem vai para o log (applog), uma linha; e uma vez por semana,
uma linha com quantas de cada regra (`log_weekly()`, chamada pela thread da
Pluggy). A Conferencia lista as suas (`CONFERENCE_KINDS`: o conflito com o
banco e a carteira) em "Resolvido automaticamente".
"""

import json
from datetime import date, timedelta

from applog import get_logger
from dates import local_today
from db import new_id, utc_timestamp

logger = get_logger(__name__)

PLUGGY_CATEGORY = "pluggy_category"
AUTO_CONFIRM = "auto_confirm"
TRANSFER_GUESS = "transfer_guess"
FX_FALLBACK = "fx_fallback"
CONFLICT_CHANGED = "conflict_changed"
CONFLICT_VANISHED = "conflict_vanished"
INVESTMENT_CUSTODY = "investment_custody"
INVESTMENT_PROCEED_LINK = "investment_proceed_link"
INVESTMENT_CUSTODY_IN = "investment_custody_in"
INVESTMENT_RATE_DEDUCED = "investment_rate_deduced"
INVESTMENT_CLOSED_FUND = "investment_closed_fund"
# A linha da carteira volta a esperar o dono (HELD, com o "Lancar").
INVESTMENT_UNDO_TO_HELD = (INVESTMENT_CUSTODY, INVESTMENT_PROCEED_LINK, INVESTMENT_CLOSED_FUND)
INVESTMENT_KINDS = (*INVESTMENT_UNDO_TO_HELD, INVESTMENT_CUSTODY_IN, INVESTMENT_RATE_DEDUCED)
# O que gravou sozinho com um palpite: "Desfazer" devolve a linha ao Revisar.
BACK_TO_REVIEW = (AUTO_CONFIRM, TRANSFER_GUESS, FX_FALLBACK)
KINDS = (PLUGGY_CATEGORY, *BACK_TO_REVIEW, CONFLICT_CHANGED, CONFLICT_VANISHED, *INVESTMENT_KINDS)
# Gravaram uma operacao: o "Desfazer" e apaga-la no Extrato.
NOT_UNDOABLE = (INVESTMENT_CUSTODY_IN, INVESTMENT_RATE_DEDUCED)
LIST_LIMIT = 200
# O que a Conferencia (Ajustes > Open Finance) mostra em "Resolvido automaticamente":
# o que ela antes apontava para o dono (o conflito com o banco, a linha da carteira).
CONFERENCE_KINDS = (CONFLICT_CHANGED, CONFLICT_VANISHED, *INVESTMENT_KINDS)
# A linha semanal do log (log_weekly): o dia (local) da ultima, em user_settings.
WEEKLY_SETTING = "auto_decisions_weekly"
WEEK_DAYS = 7


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
        "undoable": row["kind"] not in NOT_UNDOABLE,
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


def counts(conn, current_user_id, since=None, undone=False):
    """{kind: quantas} desde `since` (as desfeitas fora; `undone` = so elas)."""
    clauses = ["user_id = ?", "undone_at IS NOT NULL" if undone else "undone_at IS NULL"]
    params = [current_user_id]
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


def log_weekly(conn, current_user_id, today=None):
    """Uma linha no log por semana: quantas decisoes de cada regra nos ultimos
    WEEK_DAYS dias (pela data em que o app decidiu), e quantas o dono desfez.
    Devolve o que logou, ou None quando a ultima linha tem menos de uma semana."""
    today = today or local_today()
    row = conn.execute(
        "SELECT value FROM user_settings WHERE user_id = ? AND setting_key = ?", (current_user_id, WEEKLY_SETTING),
    ).fetchone()
    try:
        last = date.fromisoformat(row["value"]) if row and row["value"] else None
    except ValueError:
        last = None
    if last is not None and (today - last).days < WEEK_DAYS:
        return None
    since = (today - timedelta(days=WEEK_DAYS)).isoformat()
    taken = counts(conn, current_user_id, since=since)
    undone = counts(conn, current_user_id, since=since, undone=True)
    report = {
        "since": since,
        "total": sum(taken.values()),
        "undone": sum(undone.values()),
        **{f"n_{kind}": taken.get(kind, 0) for kind in KINDS},
        **{f"undone_{kind}": total for kind, total in undone.items()},
    }
    logger.info("Decisoes automaticas da semana", extra={"user_id": current_user_id, **report})
    conn.execute(
        """
        INSERT INTO user_settings (user_id, setting_key, value, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (user_id, setting_key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (current_user_id, WEEKLY_SETTING, today.isoformat(), utc_timestamp()),
    )
    return report
