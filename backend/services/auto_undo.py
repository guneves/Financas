"""O "Desfazer" de uma decisao automatica (auto_decisions).

- `pluggy_category`: a categoria volta a de antes, se a linha ainda esta com a
  que a Pluggy pos (o dono que trocou depois manda);
- `auto_confirm` e o que gravou com um palpite (`transfer_guess`,
  `fx_fallback`): a linha volta ao Revisar, onde o dono
  corrige o lado, a conta ou o valor;
- `conflict_changed`: o valor volta e o conflito volta a ser apontado;
  `conflict_vanished`: a linha apagada volta (services/conflict_resolution.py).

Desfeita, a regra nao decide de novo o mesmo lancamento. O que o app desfaz
renova os snapshots: desfazer nao conta como toque do dono.
"""

from services import auto_decisions, conflict_resolution, review
from services.recorded_snapshot import refresh_snapshots


class AlreadyUndone(Exception):
    pass


def _item_for(conn, current_user_id, table, target_id):
    row = conn.execute(
        "SELECT id FROM inbox_items WHERE user_id = ? AND target_table = ? AND target_id = ? ORDER BY created_at LIMIT 1",
        (current_user_id, table, target_id),
    ).fetchone()
    return row["id"] if row else None


def undo(conn, current_user_id, decision_id):
    """Desfaz e devolve a decisao (LookupError se nao existe; AlreadyUndone)."""
    decision = auto_decisions.fetch(conn, current_user_id, decision_id)
    if not decision:
        raise LookupError("Decisao nao encontrada.")
    if decision["undone_at"]:
        raise AlreadyUndone("Esta decisao ja foi desfeita.")
    table, target_id, detail = decision["table"], decision["target_id"], decision["detail"]
    if table == "inbox_items":
        # O cambio decidiu no item, antes do lancamento existir: vale o dele.
        item = conn.execute(
            "SELECT target_table, target_id FROM inbox_items WHERE id = ? AND user_id = ?", (target_id, current_user_id),
        ).fetchone()
        table, target_id = (item["target_table"], item["target_id"]) if item else (None, None)
    exists = table in review.TABLES and review.current_category(conn, current_user_id, table, target_id) is not None
    if decision["kind"] == auto_decisions.PLUGGY_CATEGORY and exists:
        current = review.current_category(conn, current_user_id, table, target_id)
        if list(current) == list(detail.get("after") or []) and detail.get("before"):
            review.set_category(conn, current_user_id, table, target_id, tuple(detail["before"]))
            refresh_snapshots(
                conn, current_user_id, detail.get("item_id") or _item_for(conn, current_user_id, table, target_id),
                table, target_id,
            )
    elif decision["kind"] in auto_decisions.BACK_TO_REVIEW and exists:
        review.mark_for_review(conn, current_user_id, table, target_id)
    elif decision["kind"] == auto_decisions.CONFLICT_CHANGED:
        conflict_resolution.undo_changed(conn, current_user_id, decision)
    elif decision["kind"] == auto_decisions.CONFLICT_VANISHED:
        conflict_resolution.undo_vanished(conn, current_user_id, decision)
    auto_decisions.mark_undone(conn, current_user_id, decision_id)
    return auto_decisions.fetch(conn, current_user_id, decision_id)
