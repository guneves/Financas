"""Lancamentos recorrentes (`/api/recurring`).

Uma recorrencia e um modelo, nao dinheiro: `POST /api/recurring/run` grava as
ocorrencias vencidas como `transactions` com
`source_type = 'RECURRING_TRANSACTION'` e `source_id = '<recorrencia>:<AAAA-MM-DD>'`,
e o indice unico de source torna a segunda execucao um no-op.
"""


from flask import Blueprint, jsonify, request

from auth import token_required
from dates import local_now, parse_iso_date
from db import get_db, new_id, utc_timestamp
from services.recurring import (
    build_recurring_forecast,
    fetch_recurring,
    materialize_recurring,
    recurring_archived_account,
    recurring_occurrence_dates,
    recurring_pending_count,
    recurring_rows,
    serialize_recurring,
)
from services.recurring_payload import (
    read_recurring_payload,
)
from source_types import RECURRING_SOURCE_TYPE
from validators import (
    ValidationError,
    optional_date,
    parse_json_body,
    validation_error,
)

bp = Blueprint("recurring", __name__)


@bp.route("/api/recurring", methods=["GET", "POST"])
@token_required
def recurring_transactions(current_user_id):
    if request.method == "GET":
        include_inactive = str(request.args.get("include_inactive", "1")).lower() in (
            "1", "true", "yes",
        )
        today = local_now().replace(hour=0, minute=0, second=0, microsecond=0)
        with get_db() as conn:
            rows = recurring_rows(conn, current_user_id, include_inactive=include_inactive)
            items = [
                serialize_recurring(row, pending=recurring_pending_count(conn, current_user_id, row, today))
                for row in rows
            ]
        return jsonify({
            "items": items,
            "pending_count": sum(item.get("pending_count", 0) for item in items),
            "today": today.strftime("%Y-%m-%d"),
        }), 200

    payload = parse_json_body()
    with get_db() as conn:
        try:
            fields = read_recurring_payload(conn, current_user_id, payload)
        except ValidationError as exc:
            return validation_error(str(exc))

        recurring_id = new_id()
        columns = ["id", "user_id", *fields.keys()]
        placeholders = ", ".join("?" for _ in columns)
        conn.execute(
            f"INSERT INTO recurring_transactions ({', '.join(columns)}) VALUES ({placeholders})",
            (recurring_id, current_user_id, *fields.values()),
        )
        row = fetch_recurring(conn, current_user_id, recurring_id)
        item = serialize_recurring(row, pending=recurring_pending_count(conn, current_user_id, row, local_now()))
    return jsonify(item), 201


@bp.route("/api/recurring/<recurring_id>", methods=["PATCH", "DELETE"])
@token_required
def recurring_detail(current_user_id, recurring_id):
    with get_db() as conn:
        row = fetch_recurring(conn, current_user_id, recurring_id)
        if not row:
            return jsonify({"error": "Recorrencia nao encontrada."}), 404

        if request.method == "DELETE":
            # O molde e apagado; os lancamentos ja gerados ficam. Eles sao
            # dinheiro que ja entrou ou saiu — apaga-los aqui seria reescrever
            # o passado a partir de uma tela de configuracao.
            kept = conn.execute(
                """
                SELECT COUNT(*) AS total FROM transactions
                WHERE user_id = ? AND source_type = ? AND source_id LIKE ?
                """,
                (current_user_id, RECURRING_SOURCE_TYPE, f"{recurring_id}:%"),
            ).fetchone()["total"]
            conn.execute(
                "DELETE FROM recurring_transactions WHERE id = ? AND user_id = ?",
                (recurring_id, current_user_id),
            )
            return jsonify({"deleted": True, "kept_transactions": kept}), 200

        payload = parse_json_body()
        try:
            fields = read_recurring_payload(conn, current_user_id, payload, existing=row)
        except ValidationError as exc:
            return validation_error(str(exc))

        if not fields:
            return validation_error("Informe ao menos um campo para atualizar.")

        fields["updated_at"] = utc_timestamp()
        assignments = ", ".join(f"{column} = ?" for column in fields)
        conn.execute(
            f"UPDATE recurring_transactions SET {assignments} WHERE id = ? AND user_id = ?",
            (*fields.values(), recurring_id, current_user_id),
        )
        updated = fetch_recurring(conn, current_user_id, recurring_id)
        item = serialize_recurring(
            updated, pending=recurring_pending_count(conn, current_user_id, updated, local_now())
        )
    return jsonify(item), 200


@bp.route("/api/recurring/run", methods=["POST"])
@token_required
def run_recurring(current_user_id):
    """Materializa as ocorrencias vencidas — o substituto local de um cron.

    `through` permite adiantar (fechar o mes antes do dia), `id` limita a uma
    recorrencia. Rodar de novo no mesmo dia nao duplica nada.
    """
    payload = parse_json_body()
    with get_db() as conn:
        try:
            through = optional_date(payload, "through", "Data limite")
        except ValidationError as exc:
            return validation_error(str(exc))
        through_date = parse_iso_date(through) if through else local_now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        target_id = str(payload.get("id") or "").strip()
        if target_id:
            row = fetch_recurring(conn, current_user_id, target_id)
            if not row:
                return jsonify({"error": "Recorrencia nao encontrada."}), 404
            rows = [row] if row["active"] else []
        else:
            rows = [
                row for row in recurring_rows(conn, current_user_id, include_inactive=False)
            ]

        created = []
        skipped = 0
        blocked = []
        for row in rows:
            archived = recurring_archived_account(conn, current_user_id, row)
            if archived:
                if recurring_occurrence_dates(row, through_date):
                    blocked.append({
                        "id": row["id"],
                        "description": row["description"],
                        "account_name": archived["name"],
                    })
                continue
            row_created, row_skipped = materialize_recurring(
                conn, current_user_id, row, through_date
            )
            created.extend(row_created)
            skipped += row_skipped

    return jsonify({
        "through": through_date.strftime("%Y-%m-%d"),
        "created": len(created),
        "already_existed": skipped,
        "transactions": created,
        # Recorrencias com ocorrencia vencida numa conta arquivada: nao lancam.
        "blocked": blocked,
    }), 200


@bp.route("/api/recurring/forecast", methods=["GET"])
@token_required
def recurring_forecast(current_user_id):
    raw_days = request.args.get("days", "90")
    try:
        days = max(1, min(int(raw_days), 365))
    except (TypeError, ValueError):
        return validation_error("Informe days como um numero de dias.")

    with get_db() as conn:
        return jsonify(build_recurring_forecast(conn, current_user_id, days)), 200
