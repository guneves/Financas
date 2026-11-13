"""Open Finance: o cliente da Pluggy, as preferencias e as leituras basicas.

O cliente (um por processo; os testes trocam com `set_client()`), a trava de um
pull por usuario, as preferencias de `user_settings` (`sync_hours`,
`include_pending`, `first_sync_days`, `auto_record`) e as leituras de conexoes e
contas da Pluggy.

Saiu de services/open_finance.py (2026-11-13), que continua reexportando todos
estes nomes: `open_finance.set_client`, `open_finance.settings`... valem como antes.
"""

import re
import threading
import time

import pluggy_client
from applog import get_logger
from config import (
    OPEN_FINANCE_SYNC_SECONDS,
    PLUGGY_BASE_URL,
    PLUGGY_CLIENT_ID,
    PLUGGY_CLIENT_SECRET,
    PLUGGY_TIMEOUT_SECONDS,
)
from services import (
    inbox,
    invoices,
    open_finance_auto,
)
from validators import ValidationError

logger = get_logger(__name__)


PluggyError = pluggy_client.PluggyError


# Folga do pull (definida em services/inbox.py, que este modulo importa e que
# tambem a usa no par aproximado; o nome continua valendo aqui).
LATE_POSTING_DAYS = inbox.LATE_POSTING_DAYS


# Sem nenhuma linha da conta ainda, a folga antiga: nao traz o que o dono deixou
# fora da primeira busca.
OVERLAP_DAYS = 7


FIRST_SYNC_SETTING = "open_finance_first_days"


DEFAULT_FIRST_SYNC_DAYS = 30


# A Pluggy guarda ate 12 meses de transacoes.
MAX_FIRST_SYNC_DAYS = 365


# Busca automatica por usuario (Ajustes). Toda conta mapeada atualiza sem o dono
# (dono, 2026-10-30): sem escolha vale o padrao, e so "Desligada" escolhida em
# Ajustes (gravada como SYNC_OFF) deixa so o botao "Atualizar"; um "0" gravado
# antes disso nao diz que alguem escolheu e vale o padrao. Nunca abaixo de 6 h
# (dono, 2026-10-27): a Pluggy so traz dado novo do banco de 6 em 6 a 24 h, ler
# mais vezes nao adianta.
SYNC_HOURS_SETTING = "open_finance_sync_hours"


SYNC_OFF = "off"


MIN_SYNC_HOURS = 6


MAX_SYNC_HOURS = 24


DEFAULT_SYNC_HOURS = 6


INCLUDE_PENDING_SETTING = "open_finance_include_pending"


# Gravar sozinho (044): services/open_finance_auto.py.
AUTO_RECORD_SETTING = open_finance_auto.AUTO_RECORD_SETTING


# O historico (preview -> apply): ate onde a Pluggy guarda.
DEFAULT_HISTORY_DAYS = 365


# Status em que so o dono resolve (nova senha, um codigo, aceitar termos no
# banco): a mensagem fica em Ajustes.
OWNER_ACTION_STATUSES = {"LOGIN_ERROR", "WAITING_USER_INPUT"}


OWNER_ACTION_EXECUTIONS = {
    "INVALID_CREDENTIALS", "ACCOUNT_LOCKED", "ACCOUNT_NEEDS_ACTION", "USER_NOT_SUPPORTED",
    "ACCOUNT_CREDENTIALS_RESET", "USER_AUTHORIZATION_NOT_GRANTED", "USER_AUTHORIZATION_REVOKED",
    "USER_AUTHORIZATION_PENDING", "INVALID_CREDENTIALS_MFA",
}


PLUGGY_ID_PATTERN = re.compile(r"^[0-9A-Fa-f-]{8,64}$")


_client = None


_client_lock = threading.Lock()


_sync_locks = {}


_sync_locks_guard = threading.Lock()


class NotConfigured(Exception):
    pass


def client():
    global _client
    with _client_lock:
        if _client is None:
            _client = pluggy_client.PluggyClient(
                PLUGGY_CLIENT_ID, PLUGGY_CLIENT_SECRET, PLUGGY_BASE_URL, PLUGGY_TIMEOUT_SECONDS,
            )
        return _client


def set_client(value):
    """Para os testes: um cliente falso (None volta ao de verdade)."""
    global _client
    with _client_lock:
        _client = value


def is_configured():
    return bool(client().configured)


def _require_configured():
    if not is_configured():
        raise NotConfigured("Open Finance desligado: o servidor nao tem PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET.")


def _sync_lock(current_user_id):
    with _sync_locks_guard:
        return _sync_locks.setdefault(current_user_id, threading.Lock())


def _today():
    return invoices.local_today()


def _day_text(day):
    return day.strftime("%Y-%m-%d")


def first_sync_days(conn, current_user_id):
    row = conn.execute(
        "SELECT value FROM user_settings WHERE user_id = ? AND setting_key = ?",
        (current_user_id, FIRST_SYNC_SETTING),
    ).fetchone()
    try:
        value = int(row["value"]) if row else DEFAULT_FIRST_SYNC_DAYS
    except (TypeError, ValueError):
        value = DEFAULT_FIRST_SYNC_DAYS
    return min(max(value, 1), MAX_FIRST_SYNC_DAYS)


def _parse_first_sync_days(value):
    if isinstance(value, bool):
        raise ValidationError("Informe os dias da primeira busca.")
    try:
        days = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Informe os dias da primeira busca.") from exc
    if not 1 <= days <= MAX_FIRST_SYNC_DAYS:
        raise ValidationError(f"A primeira busca vai de 1 a {MAX_FIRST_SYNC_DAYS} dias.")
    return days


def default_sync_hours():
    """O intervalo de quem nunca escolheu: o do servidor (OPEN_FINANCE_SYNC_SECONDS),
    6 h se ele desligou a thread (aí nada roda sozinho para ninguém)."""
    if OPEN_FINANCE_SYNC_SECONDS <= 0:
        return DEFAULT_SYNC_HOURS
    return min(max(round(OPEN_FINANCE_SYNC_SECONDS / 3600), MIN_SYNC_HOURS), MAX_SYNC_HOURS)


def sync_hours(conn, current_user_id):
    """0 (o dono escolheu so o botao) ou MIN_SYNC_HOURS..MAX_SYNC_HOURS; um valor
    antigo abaixo de 6 h (o limite era 1 h ate 044) sobe para 6."""
    value = inbox.setting_value(conn, current_user_id, SYNC_HOURS_SETTING)
    if value == SYNC_OFF:
        return 0
    try:
        hours = int(value)
    except (TypeError, ValueError):
        return default_sync_hours()
    return max(hours, MIN_SYNC_HOURS) if 0 < hours <= MAX_SYNC_HOURS else default_sync_hours()


def include_pending(conn, current_user_id):
    """Ligado sem escolha (dono, 2026-11-01: toda transacao, no momento em que
    chega; migracao 052): so "0" gravado em Ajustes desliga."""
    return inbox.setting_value(conn, current_user_id, INCLUDE_PENDING_SETTING) != "0"


def settings(conn, current_user_id):
    return {
        "first_sync_days": first_sync_days(conn, current_user_id),
        "sync_hours": sync_hours(conn, current_user_id),
        "min_sync_hours": MIN_SYNC_HOURS,
        "include_pending": include_pending(conn, current_user_id),
        "auto_sync_available": OPEN_FINANCE_SYNC_SECONDS > 0,
        "auto_record": open_finance_auto.enabled(conn, current_user_id),
        "auto_record_blockers": open_finance_auto.blockers(conn, current_user_id, time.time()),
        # Sem efeito desde 2026-10-30 (o servidor ignora os avisos dos bancos
        # sempre): so para um APK antigo que ainda le o campo.
        "ignore_notifications": True,
    }


SETTINGS_FIELDS = ("first_sync_days", "sync_hours", "include_pending", "auto_record")


def _bool_field(payload, key):
    if not isinstance(payload[key], bool):
        raise ValidationError(f"Envie {key} como true ou false.")
    return payload[key]


def update_settings(conn, current_user_id, payload):
    """PATCH parcial: valida tudo antes de gravar qualquer coisa. Ligar
    `auto_record` e recusado enquanto houver conta sem destino ou conexao sem
    pull recente; ligado, o que ja esperava no Aprovar vindo da Pluggy e
    gravado numa passada (`auto_recorded` na resposta)."""
    if not isinstance(payload, dict):
        raise ValidationError("Envie um objeto JSON.")
    unknown = sorted(set(payload) - set(SETTINGS_FIELDS))
    if unknown:
        raise ValidationError(f"Preferencia desconhecida: {', '.join(unknown)}.")
    if not payload:
        raise ValidationError("Envie ao menos uma preferencia.")
    writes = []
    if "first_sync_days" in payload:
        writes.append((FIRST_SYNC_SETTING, str(_parse_first_sync_days(payload["first_sync_days"]))))
    if "sync_hours" in payload:
        hours = payload["sync_hours"]
        if isinstance(hours, bool) or not isinstance(hours, int):
            raise ValidationError("Informe a busca automática em horas (0 desliga).")
        if hours != 0 and not MIN_SYNC_HOURS <= hours <= MAX_SYNC_HOURS:
            raise ValidationError(
                f"A busca automática vai de {MIN_SYNC_HOURS} a {MAX_SYNC_HOURS} horas, ou 0 para desligar: "
                f"a Pluggy só traz dados novos do banco de {MIN_SYNC_HOURS} em {MIN_SYNC_HOURS} horas ou mais."
            )
        writes.append((SYNC_HOURS_SETTING, str(hours) if hours else SYNC_OFF))
    if "include_pending" in payload:
        writes.append((INCLUDE_PENDING_SETTING, "1" if _bool_field(payload, "include_pending") else "0"))
    turning_on = False
    if "auto_record" in payload:
        wanted = _bool_field(payload, "auto_record")
        if wanted and not open_finance_auto.enabled(conn, current_user_id):
            problems = open_finance_auto.blockers(conn, current_user_id, time.time())
            if problems:
                raise ValidationError("Gravar sozinho ainda não pode ligar: " + " ".join(problems))
            turning_on = True
        writes.append((AUTO_RECORD_SETTING, "1" if wanted else "0"))
    for key, value in writes:
        inbox.save_setting(conn, current_user_id, key, value)
    body = settings(conn, current_user_id)
    if turning_on:
        body["auto_recorded"] = open_finance_auto.record_pending(conn, current_user_id, _today())
        logger.info("Open Finance: gravar sozinho ligado", extra={"user_id": current_user_id, **body["auto_recorded"]})
    return body


def fetch_item(conn, current_user_id, of_item_id, active_only=True):
    row = conn.execute(
        "SELECT * FROM open_finance_items WHERE id = ? AND user_id = ?",
        (of_item_id, current_user_id),
    ).fetchone()
    if not row or (active_only and row["archived_at"]):
        return None
    return row


def active_items(conn, current_user_id):
    return conn.execute(
        "SELECT * FROM open_finance_items WHERE user_id = ? AND archived_at IS NULL ORDER BY created_at, id",
        (current_user_id,),
    ).fetchall()


def item_accounts(conn, current_user_id, of_item_id):
    return conn.execute(
        "SELECT * FROM open_finance_accounts WHERE user_id = ? AND of_item_id = ? ORDER BY type, name, id",
        (current_user_id, of_item_id),
    ).fetchall()


def needs_owner(item_row):
    return (item_row["status"] in OWNER_ACTION_STATUSES) or (item_row["execution_status"] in OWNER_ACTION_EXECUTIONS)
