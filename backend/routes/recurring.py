"""Lancamentos recorrentes (`/api/recurring`).

Uma recorrencia e um modelo, nao dinheiro: `POST /api/recurring/run` grava as
ocorrencias vencidas como `transactions` com
`source_type = 'RECURRING_TRANSACTION'` e `source_id = '<recorrencia>:<AAAA-MM-DD>'`,
e o indice unico de source torna a segunda execucao um no-op.
"""

import calendar
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from auth import token_required
from dates import parse_iso_date
from db import get_db, new_id, serialize_metadata_row, serialize_transaction, utc_timestamp
from money import rounded_money
from services.accounts import ensure_default_account, resolve_account_id, resolve_category
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


ALLOWED_RECURRING_TYPES = {"INCOME", "EXPENSE"}
ALLOWED_RECURRENCE_FREQUENCIES = {"WEEKLY", "MONTHLY", "YEARLY"}
# Teto por recorrencia numa unica chamada de /api/recurring/run: uma semanal
# esquecida por anos nao pode gerar milhares de lancamentos de uma vez.
RECURRING_MAX_OCCURRENCES = 400


def recurring_add_months(date_value, months, anchor_day=None):
    """Soma meses preservando o dia de ancoragem, com clamp no fim do mes.

    O dia vem de `start_date` e nao da ultima ocorrencia, senao uma recorrencia
    dia 31 cairia em 28 no primeiro fevereiro e ficaria presa no dia 28 para
    sempre.
    """
    index = date_value.year * 12 + (date_value.month - 1) + months
    year, month_index = divmod(index, 12)
    month = month_index + 1
    day = min(anchor_day or date_value.day, calendar.monthrange(year, month)[1])
    return datetime(year, month, day)


def recurring_next_date(date_value, frequency, interval_count, anchor_day=None):
    interval = max(1, int(interval_count or 1))
    if frequency == "WEEKLY":
        return date_value + timedelta(weeks=interval)
    if frequency == "YEARLY":
        return recurring_add_months(date_value, 12 * interval, anchor_day)
    return recurring_add_months(date_value, interval, anchor_day)


def recurring_occurrence_dates(row, through_date, *, limit=RECURRING_MAX_OCCURRENCES):
    """Datas devidas por esta recorrencia ate `through_date`, inclusive.

    Comeca em next_run_date (o que ainda nao foi materializado), respeita
    end_date e tem um teto de seguranca: uma recorrencia semanal esquecida por
    anos nao pode gerar milhares de lancamentos numa chamada.

    next_run_date nulo e recorrencia encerrada: nao deve nada. Cair de volta em
    start_date aqui recontava o historico inteiro como pendente — o /run nao
    duplicava (o indice unico barra), mas o contador nunca zerava.
    """
    start = parse_iso_date(row["start_date"])
    cursor_date = parse_iso_date(row["next_run_date"])
    if not cursor_date or not through_date:
        return []

    end = parse_iso_date(row["end_date"]) if row["end_date"] else None
    anchor_day = start.day if start else cursor_date.day
    dates = []
    while cursor_date <= through_date and len(dates) < limit:
        if end and cursor_date > end:
            break
        dates.append(cursor_date)
        cursor_date = recurring_next_date(
            cursor_date, row["frequency"], row["interval_count"], anchor_day
        )
    return dates


def recurring_date_after(row, date_value):
    """A ocorrencia seguinte a `date_value`, ou None se a recorrencia acabou."""
    start = parse_iso_date(row["start_date"])
    anchor_day = start.day if start else date_value.day
    following = recurring_next_date(
        date_value, row["frequency"], row["interval_count"], anchor_day
    )
    end = parse_iso_date(row["end_date"]) if row["end_date"] else None
    if end and following > end:
        return None
    return following


def recurring_resume_date(row, from_date):
    """Primeira ocorrencia em ou depois de `from_date`, ao retomar uma pausa.

    Retomar nao pode gerar o periodo pausado: a assinatura foi cancelada
    naqueles meses, o dinheiro nao saiu, e materializar aquilo criaria despesas
    que nunca existiram — que o orcamento (009) e o saldo por conta (007)
    contariam como reais.
    """
    cursor_date = parse_iso_date(row["next_run_date"])
    if not cursor_date:
        return None

    end = parse_iso_date(row["end_date"]) if row["end_date"] else None
    start = parse_iso_date(row["start_date"])
    anchor_day = start.day if start else cursor_date.day
    guard = 0
    while cursor_date < from_date and guard < RECURRING_MAX_OCCURRENCES:
        cursor_date = recurring_next_date(
            cursor_date, row["frequency"], row["interval_count"], anchor_day
        )
        guard += 1

    if end and cursor_date > end:
        return None
    return cursor_date.strftime("%Y-%m-%d")


def recurring_revival_date(conn, current_user_id, row):
    """Proxima ocorrencia de uma recorrencia encerrada cujo end_date foi estendido.

    Encerrada perde o next_run_date, entao o cursor e reconstruido: a primeira
    data do calendario (ancorado no dia de start_date, com a frequencia do
    DEPOIS do PATCH) estritamente posterior a ultima ocorrencia ja
    materializada. Sem nada materializado, comeca em start_date.

    Diferente de retomar uma pausa: prorrogar diz que o contrato continuou, e o
    intervalo entre o fim antigo e hoje fica pendente de proposito.
    """
    start = parse_iso_date(row["start_date"])
    if not start:
        return None

    prefix = f"{row['id']}:"
    last_text = conn.execute(
        """
        SELECT MAX(substr(source_id, ?)) AS last_date
        FROM transactions
        WHERE user_id = ? AND source_type = ? AND source_id LIKE ?
        """,
        (len(prefix) + 1, current_user_id, RECURRING_SOURCE_TYPE, f"{prefix}%"),
    ).fetchone()["last_date"]
    last_date = parse_iso_date(last_text)

    cursor_date = start
    if last_date:
        guard = 0
        while cursor_date <= last_date and guard < RECURRING_MAX_OCCURRENCES * 25:
            cursor_date = recurring_next_date(
                cursor_date, row["frequency"], row["interval_count"], start.day
            )
            guard += 1

    end = parse_iso_date(row["end_date"]) if row["end_date"] else None
    if end and cursor_date > end:
        return None
    return cursor_date.strftime("%Y-%m-%d")


def recurring_status(row):
    if not row["active"]:
        return "PAUSED"
    if not row["next_run_date"]:
        return "FINISHED"
    return "ACTIVE"


def recurring_source_id(recurring_id, date_text):
    return f"{recurring_id}:{date_text}"


def serialize_recurring(row, *, pending=None):
    item = serialize_metadata_row(row)
    if not item:
        return item
    item["active"] = bool(item.get("active"))
    item["amount"] = rounded_money(item.get("amount"))
    item["status"] = recurring_status(row)
    if pending is not None:
        item["pending_count"] = pending
    return item


def fetch_recurring(conn, current_user_id, recurring_id):
    return conn.execute(
        "SELECT * FROM recurring_transactions WHERE id = ? AND user_id = ?",
        (recurring_id, current_user_id),
    ).fetchone()


def recurring_rows(conn, current_user_id, *, include_inactive=True):
    query = "SELECT * FROM recurring_transactions WHERE user_id = ?"
    if not include_inactive:
        query += " AND active = 1"
    query += " ORDER BY active DESC, next_run_date IS NULL, next_run_date, description COLLATE NOCASE, id"
    return conn.execute(query, (current_user_id,)).fetchall()


def materialize_recurring(conn, current_user_id, row, through_date):
    """Gera em `transactions` tudo o que esta recorrencia deve ate `through_date`.

    Devolve (lancamentos criados, ja existentes). A repeticao e inofensiva: o
    indice unico (user_id, source_type, source_id) rejeita a segunda insercao
    da mesma data, e o INSERT OR IGNORE transforma isso em "ja existia".
    """
    created = []
    skipped = 0
    dates = recurring_occurrence_dates(row, through_date)
    if not dates:
        return created, skipped

    account_id = row["account_id"] or ensure_default_account(conn, current_user_id)
    amount = rounded_money(row["amount"])
    for occurrence in dates:
        date_text = occurrence.strftime("%Y-%m-%d")
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO transactions
            (id, user_id, account_id, amount, date, category, category_id, description,
             type, source_type, source_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id(),
                current_user_id,
                account_id,
                amount,
                date_text,
                row["category"],
                row["category_id"],
                row["description"],
                row["type"],
                RECURRING_SOURCE_TYPE,
                recurring_source_id(row["id"], date_text),
            ),
        )
        if cursor.rowcount:
            item = conn.execute(
                """
                SELECT * FROM transactions
                WHERE user_id = ? AND source_type = ? AND source_id = ?
                """,
                (current_user_id, RECURRING_SOURCE_TYPE, recurring_source_id(row["id"], date_text)),
            ).fetchone()
            created.append(serialize_transaction(item))
        else:
            skipped += 1

    following = recurring_date_after(row, dates[-1])
    conn.execute(
        """
        UPDATE recurring_transactions
        SET next_run_date = ?, last_run_at = ?, updated_at = ?
        WHERE id = ? AND user_id = ?
        """,
        (
            following.strftime("%Y-%m-%d") if following else None,
            utc_timestamp(),
            utc_timestamp(),
            row["id"],
            current_user_id,
        ),
    )
    return created, skipped


def recurring_pending_count(row, today):
    if not row["active"]:
        return 0
    return len(recurring_occurrence_dates(row, today))


def build_recurring_forecast(conn, current_user_id, days):
    """Previsao de caixa: o que as recorrencias ativas lancam ate hoje + `days`.

    Nada e gravado. Ocorrencias com data <= hoje aparecem como `pending` — elas
    ja venceram e so nao existem porque /run ainda nao foi chamado.
    """
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    horizon = today + timedelta(days=days)
    occurrences = []
    for row in recurring_rows(conn, current_user_id, include_inactive=False):
        for occurrence in recurring_occurrence_dates(row, horizon):
            date_text = occurrence.strftime("%Y-%m-%d")
            occurrences.append({
                "recurring_id": row["id"],
                "date": date_text,
                "type": row["type"],
                "amount": rounded_money(row["amount"]),
                "category": row["category"],
                "category_id": row["category_id"],
                "description": row["description"],
                "account_id": row["account_id"],
                "pending": occurrence <= today,
            })
    occurrences.sort(key=lambda item: (item["date"], item["description"] or "", item["recurring_id"]))

    def totals_through(limit_date):
        income = sum(
            item["amount"] for item in occurrences
            if item["type"] == "INCOME" and item["date"] <= limit_date
        )
        expense = sum(
            item["amount"] for item in occurrences
            if item["type"] == "EXPENSE" and item["date"] <= limit_date
        )
        return {
            "income": rounded_money(income),
            "expense": rounded_money(expense),
            "net": rounded_money(income - expense),
        }

    buckets = {}
    for window in (30, 60, 90):
        if window <= days:
            limit_date = (today + timedelta(days=window)).strftime("%Y-%m-%d")
            buckets[str(window)] = totals_through(limit_date)

    return {
        "from_date": today.strftime("%Y-%m-%d"),
        "through_date": horizon.strftime("%Y-%m-%d"),
        "days": days,
        "occurrences": occurrences,
        "pending_count": sum(1 for item in occurrences if item["pending"]),
        "totals": totals_through(horizon.strftime("%Y-%m-%d")),
        "windows": buckets,
    }


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
        revival = recurring_revival_date(
            conn, current_user_id, {**dict(existing), **fields}
        )
        if revival:
            fields["next_run_date"] = revival
            revived = True

    if (
        existing is not None
        and fields.get("active") == 1
        and not existing["active"]
        and ("next_run_date" not in fields or revived)
    ):
        # Retomar salta o periodo pausado. Sem isso o proximo /run lancaria
        # todos os meses da pausa de uma vez, como se tivessem sido pagos.
        #
        # O calendario usado aqui e o DEPOIS do PATCH: reativar e estender
        # end_date (ou trocar a frequencia) no mesmo salvamento e o caso comum,
        # e avaliar contra o end_date antigo encerraria a recorrencia que o
        # usuario acabou de prorrogar.
        fields["next_run_date"] = recurring_resume_date(
            {**dict(existing), **fields},
            datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
        )

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
                serialize_recurring(row, pending=recurring_pending_count(row, today))
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
        item = serialize_recurring(row, pending=recurring_pending_count(row, datetime.now()))
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
            updated, pending=recurring_pending_count(updated, datetime.now())
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
