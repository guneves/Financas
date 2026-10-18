"""Lancamentos recorrentes (`/api/recurring`).

Uma recorrencia e um modelo, nao dinheiro: `POST /api/recurring/run` grava as
ocorrencias vencidas como `transactions` com
`source_type = 'RECURRING_TRANSACTION'` e `source_id = '<recorrencia>:<AAAA-MM-DD>'`,
e o indice unico de source torna a segunda execucao um no-op.
"""

from datetime import datetime

from flask import Blueprint, jsonify, request

from auth import token_required
from dates import parse_iso_date
from db import get_db, new_id, utc_timestamp
from money import rounded_money
from services.accounts import resolve_account_id, resolve_category
from services.recurring import (
    ALLOWED_RECURRENCE_FREQUENCIES,
    ALLOWED_RECURRING_TYPES,
    build_recurring_forecast,
    encode_pause_gaps,
    fetch_recurring,
    materialize_recurring,
    recurring_cursor_after_gaps,
    recurring_pause_gaps,
    recurring_pending_count,
    recurring_resume_date,
    recurring_revival_date,
    recurring_rows,
    recurring_today,
    serialize_recurring,
)
from source_types import RECURRING_SOURCE_TYPE
from validators import (
    ValidationError,
    optional_date,
    optional_string,
    parse_int_number,
    parse_json_body,
    parse_number,
    require_choice,
    require_date,
    validation_error,
)

bp = Blueprint("recurring", __name__)


def read_recurring_payload(conn, current_user_id, payload, existing=None):
    """Valida o payload de uma recorrencia e devolve as colunas a gravar."""
    fields = {}
    is_new = existing is None

    if is_new or "amount" in payload:
        fields["amount"] = rounded_money(
            parse_number(payload, "amount", "Valor", minimum=0, allow_zero=False)
        )
    if is_new or "type" in payload:
        transaction_type = require_choice(payload, "type", "Tipo", ALLOWED_RECURRING_TYPES)
        fields["type"] = transaction_type
    if is_new or "frequency" in payload:
        fields["frequency"] = require_choice(
            payload, "frequency", "Frequencia", ALLOWED_RECURRENCE_FREQUENCIES
        )
    if is_new or "interval_count" in payload:
        if payload.get("interval_count") in (None, ""):
            fields["interval_count"] = 1
        else:
            fields["interval_count"] = int(
                parse_int_number(payload, "interval_count", "Intervalo", minimum=1, maximum=60)
            )
    if is_new or "start_date" in payload:
        fields["start_date"] = require_date(payload, "start_date", "Data inicial")
    if is_new or "end_date" in payload:
        fields["end_date"] = optional_date(payload, "end_date", "Data final")
    if is_new or "description" in payload:
        fields["description"] = optional_string(payload, "description")
    if is_new or "note" in payload:
        fields["note"] = optional_string(payload, "note", max_length=255) or None
    if is_new or "category" in payload or "category_id" in payload:
        category, category_id = resolve_category(conn, current_user_id, payload)
        fields["category"] = category
        fields["category_id"] = category_id
    if is_new or "account_id" in payload:
        fields["account_id"] = resolve_account_id(conn, current_user_id, payload)
    if "active" in payload:
        fields["active"] = 1 if payload.get("active") in (True, 1, "1", "true", "True") else 0
    if "next_run_date" in payload:
        fields["next_run_date"] = optional_date(payload, "next_run_date", "Proxima data")

    start_date = fields.get("start_date", existing["start_date"] if existing else None)
    end_date = fields.get("end_date", existing["end_date"] if existing else None)
    if start_date and end_date and end_date < start_date:
        raise ValidationError("Data final deve ser igual ou posterior a data inicial.")

    if is_new:
        fields.setdefault("interval_count", 1)
        fields.setdefault("active", 1)
        fields["next_run_date"] = fields.get("next_run_date") or fields["start_date"]
    elif "start_date" in fields and "next_run_date" not in fields and not existing["last_run_at"]:
        # Ainda nao gerou nada: mover a data inicial move a proxima ocorrencia.
        # Depois de gerar, mexer em start_date so muda o dia de ancoragem.
        fields["next_run_date"] = fields["start_date"]

    revived = False
    if (
        existing is not None
        and not existing["next_run_date"]
        and "end_date" in fields
        and "next_run_date" not in fields
        and fields["end_date"] != existing["end_date"]
        and (
            not fields["end_date"]
            or (existing["end_date"] and fields["end_date"] > existing["end_date"])
        )
    ):
        # Encerrada e prorrogada (ou sem data final): sem isto next_run_date
        # ficava nulo e a recorrencia continuava "Encerrada" para sempre.
        revival = recurring_revival_date({**dict(existing), **fields})
        if revival:
            fields["next_run_date"] = revival
            revived = True

    if existing is not None and "next_run_date" in payload:
        # Uma proxima data escolhida a mao e o usuario assumindo o cursor: as
        # janelas de pausa antigas deixam de valer.
        fields["pause_gaps"] = None

    if existing is not None and fields.get("active") == 0 and existing["active"]:
        fields["paused_at"] = recurring_today().strftime("%Y-%m-%d")

    if existing is not None and fields.get("active") == 1 and not existing["active"]:
        fields["paused_at"] = None
        if "next_run_date" not in fields or revived:
            # Retomar salta o periodo pausado. Sem isso o proximo /run lancaria
            # todos os meses da pausa de uma vez, como se tivessem sido pagos.
            # Mas so a pausa: o que ja tinha vencido antes dela continua
            # pendente — o dinheiro saiu, so nao foi lancado ainda.
            #
            # O calendario usado aqui e o DEPOIS do PATCH: reativar e estender
            # end_date (ou trocar a frequencia) no mesmo salvamento e o caso
            # comum, e avaliar contra o end_date antigo encerraria a
            # recorrencia que o usuario acabou de prorrogar.
            today = recurring_today()
            merged = {**dict(existing), **fields}
            paused_at = parse_iso_date(existing["paused_at"])
            if not paused_at:
                fields["next_run_date"] = recurring_resume_date(merged, today)
            else:
                gaps = recurring_pause_gaps(merged)
                if (today - paused_at).days > 1:
                    gaps.append((paused_at, today))
                fields["pause_gaps"] = encode_pause_gaps(gaps)
                merged["pause_gaps"] = fields["pause_gaps"]
                fields["next_run_date"] = recurring_cursor_after_gaps(merged)

    if existing is not None:
        # end_date encolhido para antes da proxima ocorrencia encerra a
        # recorrencia na hora. Sem isso a tela continua mostrando
        # "Ativa, proxima em ..." para algo que nunca mais vai gerar nada —
        # materialize_recurring() sai antes de atualizar a linha.
        effective_end = fields.get("end_date", existing["end_date"])
        effective_next = fields.get("next_run_date", existing["next_run_date"])
        if effective_end and effective_next and effective_next > effective_end:
            if "next_run_date" in payload and payload.get("next_run_date"):
                raise ValidationError(
                    "Proxima data nao pode ser posterior a data final."
                )
            fields["next_run_date"] = None

    return fields


@bp.route("/api/recurring", methods=["GET", "POST"])
@token_required
def recurring_transactions(current_user_id):
    if request.method == "GET":
        include_inactive = str(request.args.get("include_inactive", "1")).lower() in (
            "1", "true", "yes",
        )
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
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
        item = serialize_recurring(row, pending=recurring_pending_count(conn, current_user_id, row, datetime.now()))
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
            updated, pending=recurring_pending_count(conn, current_user_id, updated, datetime.now())
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
        through_date = parse_iso_date(through) if through else datetime.now().replace(
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
        for row in rows:
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
