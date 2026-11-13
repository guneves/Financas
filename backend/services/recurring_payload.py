"""Recorrentes: ler e validar o que a tela manda.

Saiu de routes/recurring.py (2026-11-13): nada aqui usa o Flask. A rota continua importando
todos estes nomes.
"""


from dates import local_now, parse_iso_date
from db import get_db, new_id, utc_timestamp
from money import parse_money
from services.accounts import resolve_account_id, resolve_category
from services.recurring import (
    ALLOWED_RECURRENCE_FREQUENCIES,
    ALLOWED_RECURRING_TYPES,
    build_recurring_forecast,
    encode_pause_gaps,
    fetch_recurring,
    materialize_recurring,
    recurring_archived_account,
    recurring_cursor_after_gaps,
    recurring_occurrence_dates,
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
    require_choice,
    require_date,
    validation_error,
)


def read_recurring_payload(conn, current_user_id, payload, existing=None):
    """Valida o payload de uma recorrencia e devolve as colunas a gravar."""
    fields = {}
    is_new = existing is None

    if is_new or "amount" in payload:
        fields["amount"] = parse_money(payload, "amount", "Valor")
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
        category, category_id = resolve_category(conn, current_user_id, payload, current=existing)
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
