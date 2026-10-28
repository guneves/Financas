"""Open Finance pela Pluggy (043): conexoes, mapeamento e o pull.

- **Conectar** e na web (Ajustes › Open Finance): o servidor cria o connect
  token (`connect_token()`), o widget Pluggy Connect abre com ele e devolve o
  `itemId`, que `register_item()` guarda com as contas do item.
- **Mapear** (`map_account()`): cada conta BANK da Pluggy a uma conta ativa do
  dono, cada CREDIT a um cartao ativo com credito, ou "nao usar" (044). A
  Corretora so recebe a conta de investimentos da corretora (044): o caixa
  da carteira. Uma sugestao pelo nome da conta (o MeuPluggy, o conector do
  plano gratis, nao diz o banco; a conta diz) vem na listagem; so o dono confirma.
- **Puxar** (`sync_item()`): o servidor so e alcancavel na tailnet, entao nao
  ha webhook. O botao "Atualizar" e a thread de services/open_finance_refresh.py
  so LEEM (GET) o que a Pluggy ja trouxe do banco — ela atualiza sozinha, de 6
  em 6 a 24 h; pedir dados novos (`PATCH /items`) gastaria o limite mensal do
  CPF e o app nunca pede. As transacoes vem desde o ultimo pull menos
  OVERLAP_DAYS (o primeiro: a janela que o dono escolheu, 30 dias por padrao)
  e vao para o Aprovar (services/open_finance_inbox.py); com "Gravar sozinho"
  ligado, o item pronto e aprovado na hora (services/open_finance_auto.py).
  As posicoes e operacoes da corretora vem no mesmo pull
  (services/open_finance_investments.py).
- **Historico** (`history_preview()` / `history_apply()`): o que a Pluggy tem
  de N dias atras, contado por conta (ligado, a gravar, so no app) antes; aplicado
  so na confirmacao. Nada digitado pelo dono e apagado.
- **Desconectar** (`disconnect()`): apaga o item na Pluggy e arquiva o nosso;
  os lancamentos ja gravados e os itens do Aprovar ficam.
- **Conferir saldo** (`list_view()`): por conta mapeada, o saldo da Pluggy ao
  lado do do app (account_balance_rows, nunca somar transactions). Nada ajusta
  saldo sozinho.

As chamadas a Pluggy acontecem fora da transacao do banco; a escrita vem
depois, numa so.
"""

import re
import threading
import time
from datetime import datetime, timedelta

import pluggy_client
from applog import get_logger
from config import (
    OPEN_FINANCE_SYNC_SECONDS,
    PLUGGY_BASE_URL,
    PLUGGY_CLIENT_ID,
    PLUGGY_CLIENT_SECRET,
    PLUGGY_TIMEOUT_SECONDS,
)
from dates import parse_iso_date
from db import get_db, new_id, row_to_dict, utc_timestamp
from money import rounded_money
from services import (
    inbox,
    invoices,
    open_finance_auto,
    open_finance_check,
    open_finance_inbox,
    open_finance_investments,
    realized_results,
)
from services.accounts import account_balance_rows
from services.import_rules import import_rules_for_matching
from validators import ValidationError

logger = get_logger(__name__)

PluggyError = pluggy_client.PluggyError

# Folga do pull: o banco lanca com data de dias antes (o D+1 do cartao, a
# compensacao); a chave pluggy:<id> faz a repeticao nao custar nada.
OVERLAP_DAYS = 7
FIRST_SYNC_SETTING = "open_finance_first_days"
DEFAULT_FIRST_SYNC_DAYS = 30
# A Pluggy guarda ate 12 meses de transacoes.
MAX_FIRST_SYNC_DAYS = 365
# Busca automatica por usuario (Ajustes): 0 = so o botao "Atualizar". Nunca
# abaixo de 6 h (dono, 2026-10-27): a Pluggy so traz dado novo do banco de 6
# em 6 a 24 h, ler mais vezes nao adianta.
SYNC_HOURS_SETTING = "open_finance_sync_hours"
MIN_SYNC_HOURS = 6
MAX_SYNC_HOURS = 24
DEFAULT_SYNC_HOURS = 6
INCLUDE_PENDING_SETTING = "open_finance_include_pending"
# Gravar sozinho (044): services/open_finance_auto.py; "Ignorar avisos dos
# bancos conectados": services/inbox.py.
AUTO_RECORD_SETTING = open_finance_auto.AUTO_RECORD_SETTING
IGNORE_NOTIFICATIONS_SETTING = inbox.IGNORE_CONNECTED_NOTIFICATIONS_SETTING
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


# ---------------------------------------------------------------------------
# Preferencias
# ---------------------------------------------------------------------------

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


def set_first_sync_days(conn, current_user_id, value):
    days = _parse_first_sync_days(value)
    inbox.save_setting(conn, current_user_id, FIRST_SYNC_SETTING, str(days))
    return days


def default_sync_hours():
    """O intervalo de quem nunca escolheu: o do servidor (OPEN_FINANCE_SYNC_SECONDS),
    6 h se ele desligou a thread (aí nada roda sozinho para ninguém)."""
    if OPEN_FINANCE_SYNC_SECONDS <= 0:
        return DEFAULT_SYNC_HOURS
    return min(max(round(OPEN_FINANCE_SYNC_SECONDS / 3600), MIN_SYNC_HOURS), MAX_SYNC_HOURS)


def sync_hours(conn, current_user_id):
    """0 (so o botao) ou MIN_SYNC_HOURS..MAX_SYNC_HOURS; um valor antigo abaixo
    de 6 h (o limite era 1 h ate 044) sobe para 6."""
    value = inbox.setting_value(conn, current_user_id, SYNC_HOURS_SETTING)
    try:
        hours = int(value)
    except (TypeError, ValueError):
        return default_sync_hours()
    if hours == 0:
        return 0
    return max(hours, MIN_SYNC_HOURS) if 0 < hours <= MAX_SYNC_HOURS else default_sync_hours()


def include_pending(conn, current_user_id):
    return inbox.setting_value(conn, current_user_id, INCLUDE_PENDING_SETTING) == "1"


def settings(conn, current_user_id):
    return {
        "first_sync_days": first_sync_days(conn, current_user_id),
        "sync_hours": sync_hours(conn, current_user_id),
        "min_sync_hours": MIN_SYNC_HOURS,
        "include_pending": include_pending(conn, current_user_id),
        "auto_sync_available": OPEN_FINANCE_SYNC_SECONDS > 0,
        "auto_record": open_finance_auto.enabled(conn, current_user_id),
        "auto_record_blockers": open_finance_auto.blockers(conn, current_user_id, time.time()),
        "ignore_notifications": inbox.ignore_connected_notifications(conn, current_user_id),
    }


SETTINGS_FIELDS = (
    "first_sync_days", "sync_hours", "include_pending", "auto_record", "ignore_notifications",
)


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
        writes.append((SYNC_HOURS_SETTING, str(hours)))
    if "include_pending" in payload:
        writes.append((INCLUDE_PENDING_SETTING, "1" if _bool_field(payload, "include_pending") else "0"))
    if "ignore_notifications" in payload:
        writes.append((IGNORE_NOTIFICATIONS_SETTING, "1" if _bool_field(payload, "ignore_notifications") else "0"))
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


# ---------------------------------------------------------------------------
# Leituras
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Conectar
# ---------------------------------------------------------------------------

def connect_token(current_user_id, of_item_id=None):
    """O token do widget. Com `of_item_id` (um item nosso), o widget abre para
    atualizar a conexao (nova senha, MFA) em vez de criar outra."""
    _require_configured()
    pluggy_item_id = None
    if of_item_id:
        with get_db() as conn:
            row = fetch_item(conn, current_user_id, of_item_id)
        if not row:
            raise LookupError("Conexao nao encontrada.")
        pluggy_item_id = row["pluggy_item_id"]
    return client().create_connect_token(item_id=pluggy_item_id, client_user_id=current_user_id)


def _validate_pluggy_id(value):
    text = str(value or "").strip()
    if not PLUGGY_ID_PATTERN.match(text):
        raise ValidationError("Identificador da conexao invalido.")
    return text


def _item_values(pluggy_item):
    error = pluggy_item.get("error") or {}
    connector = pluggy_item.get("connector") or {}
    return {
        "connector_id": connector.get("id"),
        "connector_name": (connector.get("name") or "")[:120] or None,
        "status": pluggy_item.get("status"),
        "execution_status": pluggy_item.get("executionStatus"),
        "error_code": (str(error.get("code"))[:80] if error.get("code") else None),
        "error_message": (str(error.get("message"))[:300] if error.get("message") else None),
        "pluggy_updated_at": pluggy_item.get("lastUpdatedAt"),
    }


def _save_item_status(conn, current_user_id, of_item_id, pluggy_item):
    values = _item_values(pluggy_item)
    values["updated_at"] = utc_timestamp()
    assignments = ", ".join(f"{column} = ?" for column in values)
    conn.execute(
        f"UPDATE open_finance_items SET {assignments} WHERE id = ? AND user_id = ?",
        (*values.values(), of_item_id, current_user_id),
    )


def _account_type(raw):
    kind = str(raw.get("type") or "").upper()
    return kind if kind in ("BANK", "CREDIT") else None


def _upsert_accounts(conn, current_user_id, of_item_id, accounts):
    """Grava as contas BANK e CREDIT do item (investimentos e emprestimos
    ficam de fora: a carteira tem o seu caminho)."""
    stamp = utc_timestamp()
    for raw in accounts:
        kind = _account_type(raw)
        if not kind or not raw.get("id"):
            continue
        balance = raw.get("balance")
        values = {
            "of_item_id": of_item_id,
            "type": kind,
            "subtype": raw.get("subtype"),
            "name": (raw.get("marketingName") or raw.get("name") or "")[:120] or None,
            "number": (str(raw.get("number") or "")[:40] or None),
            "currency": str(raw.get("currencyCode") or "BRL").upper()[:3],
            "balance": rounded_money(balance) if isinstance(balance, (int, float)) else None,
            "balance_at": stamp,
            "updated_at": stamp,
        }
        existing = conn.execute(
            "SELECT id FROM open_finance_accounts WHERE user_id = ? AND pluggy_account_id = ?",
            (current_user_id, raw["id"]),
        ).fetchone()
        if existing:
            assignments = ", ".join(f"{column} = ?" for column in values)
            conn.execute(
                f"UPDATE open_finance_accounts SET {assignments} WHERE id = ? AND user_id = ?",
                (*values.values(), existing["id"], current_user_id),
            )
        else:
            values.update({"id": new_id(), "user_id": current_user_id, "pluggy_account_id": raw["id"]})
            conn.execute(
                f"INSERT INTO open_finance_accounts ({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})",
                tuple(values.values()),
            )


def register_item(current_user_id, pluggy_item_id):
    """O widget conectou: guarda o item (ou reativa o que foi desconectado) e
    as contas dele, e faz o primeiro pull. Devolve o id do nosso item."""
    _require_configured()
    pluggy_item_id = _validate_pluggy_id(pluggy_item_id)
    pluggy_item = client().get_item(pluggy_item_id)
    if not isinstance(pluggy_item, dict) or pluggy_item.get("id") != pluggy_item_id:
        raise ValidationError("A Pluggy nao reconheceu esta conexao.")
    accounts = client().list_accounts(pluggy_item_id)
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM open_finance_items WHERE user_id = ? AND pluggy_item_id = ?",
            (current_user_id, pluggy_item_id),
        ).fetchone()
        if existing:
            of_item_id = existing["id"]
            conn.execute(
                "UPDATE open_finance_items SET archived_at = NULL WHERE id = ? AND user_id = ?",
                (of_item_id, current_user_id),
            )
        else:
            of_item_id = new_id()
            conn.execute(
                "INSERT INTO open_finance_items (id, user_id, pluggy_item_id) VALUES (?, ?, ?)",
                (of_item_id, current_user_id, pluggy_item_id),
            )
        _save_item_status(conn, current_user_id, of_item_id, pluggy_item)
        _upsert_accounts(conn, current_user_id, of_item_id, accounts)
    if pluggy_item.get("status") == "UPDATED":
        try:
            sync_item(current_user_id, of_item_id)
        except PluggyError as exc:
            logger.warning("Open Finance: primeiro pull falhou", extra={"error": str(exc)})
    return of_item_id


def item_bank_name(conn, current_user_id, item_row):
    """O banco de uma conexao para a tela: o que os nomes das contas dizem (o
    MeuPluggy nao diz o banco), senao o conector."""
    names = [account["name"] for account in item_accounts(conn, current_user_id, item_row["id"]) if account["name"]]
    labels = {inbox.open_finance_bank_name(name, None) for name in names if inbox.issuer_of_institution(name)}
    if len(labels) == 1:
        return labels.pop()
    return inbox.open_finance_bank_name(names[0] if names else None, item_row["connector_name"]) or "Open Finance"


def disconnect(current_user_id, of_item_id, confirm):
    """Apaga o item na Pluggy e arquiva o nosso. `confirm` tem de ser o nome
    do banco (a guarda dos endpoints destrutivos; sem diferenca de
    maiusculas/acentos). Nenhum lancamento muda; os itens pendentes do Aprovar
    ficam para o dono decidir."""
    with get_db() as conn:
        row = fetch_item(conn, current_user_id, of_item_id)
        expected = item_bank_name(conn, current_user_id, row) if row else None
    if not row:
        raise LookupError("Conexao nao encontrada.")
    if inbox.normalized(str(confirm or "")) != inbox.normalized(expected):
        raise ValidationError(f"Confirme com o nome do banco: {expected}.")
    if is_configured():
        client().delete_item(row["pluggy_item_id"])
    with get_db() as conn:
        conn.execute(
            "UPDATE open_finance_items SET archived_at = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (utc_timestamp(), utc_timestamp(), of_item_id, current_user_id),
        )
    return True


# ---------------------------------------------------------------------------
# Mapear
# ---------------------------------------------------------------------------

def map_account(current_user_id, of_account_id, payload):
    """Liga uma conta da Pluggy a uma conta (BANK) ou a um cartao (CREDIT) do
    dono; `null` desliga; `{"ignore": true}` e "nao usar" (044: fica puxada,
    nunca gera nada). O que ja foi puxado sem mapeamento entra no Aprovar (e,
    com "Gravar sozinho", e gravado)."""
    if not isinstance(payload, dict):
        raise ValidationError("Envie um objeto JSON.")
    if "ignore" in payload:
        if not isinstance(payload["ignore"], bool) or set(payload) != {"ignore"}:
            raise ValidationError("Envie so ignore: true ou false.")
        return _set_ignored(current_user_id, of_account_id, payload["ignore"])
    with get_db() as conn:
        account = conn.execute(
            """
            SELECT a.* FROM open_finance_accounts a
            JOIN open_finance_items i ON i.id = a.of_item_id AND i.user_id = a.user_id
            WHERE a.id = ? AND a.user_id = ? AND i.archived_at IS NULL
            """,
            (of_account_id, current_user_id),
        ).fetchone()
        if not account:
            raise LookupError("Conta do Open Finance nao encontrada.")
        if account["type"] == "BANK":
            target = _target_id(payload, "account_id")
            if target:
                _require_bank_target(conn, current_user_id, target, account)
            column, other = "account_id", "card_id"
        else:
            target = _target_id(payload, "card_id")
            if target:
                _require_card_target(conn, current_user_id, target)
            column, other = "card_id", "account_id"
        if target:
            taken = conn.execute(
                f"""
                SELECT 1 FROM open_finance_accounts a
                JOIN open_finance_items i ON i.id = a.of_item_id AND i.user_id = a.user_id
                WHERE a.user_id = ? AND a.{column} = ? AND a.id <> ? AND i.archived_at IS NULL
                """,
                (current_user_id, target, of_account_id),
            ).fetchone()
            if taken:
                # Duas contas da Pluggy no mesmo destino trariam tudo duas vezes.
                raise ValidationError("Outra conta do Open Finance ja vai para este destino.")
        conn.execute(
            f"""
            UPDATE open_finance_accounts SET {column} = ?, {other} = NULL, mapped_at = ?, ignored_at = NULL,
                updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (target, utc_timestamp() if target else None, utc_timestamp(), of_account_id, current_user_id),
        )
        account = open_finance_inbox.fetch_account(conn, current_user_id, of_account_id)
        placed = []
        recorded = None
        if target:
            placed = open_finance_inbox.place_unmapped(
                conn, current_user_id, account, import_rules_for_matching(conn, current_user_id),
            )
            if open_finance_auto.enabled(conn, current_user_id):
                recorded = open_finance_auto.record_pending(conn, current_user_id, _today())
    return {"placed": len(placed), "auto_recorded": recorded}


def _set_ignored(current_user_id, of_account_id, ignored):
    with get_db() as conn:
        account = conn.execute(
            """
            SELECT a.* FROM open_finance_accounts a
            JOIN open_finance_items i ON i.id = a.of_item_id AND i.user_id = a.user_id
            WHERE a.id = ? AND a.user_id = ? AND i.archived_at IS NULL
            """,
            (of_account_id, current_user_id),
        ).fetchone()
        if not account:
            raise LookupError("Conta do Open Finance nao encontrada.")
        if ignored and (account["account_id"] or account["card_id"]):
            raise ValidationError("Tire o destino desta conta antes de marcar \"não usar\".")
        conn.execute(
            "UPDATE open_finance_accounts SET ignored_at = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (utc_timestamp() if ignored else None, utc_timestamp(), of_account_id, current_user_id),
        )
    return {"placed": 0, "auto_recorded": None}


def _target_id(payload, key):
    if key not in payload:
        raise ValidationError("Escolha a conta ou o cartao.")
    value = payload[key]
    if value in (None, ""):
        return None
    if not isinstance(value, str) or len(value) > 64:
        raise ValidationError("Destino invalido.")
    return value


def is_investment_account(of_account):
    """A conta da Pluggy e o caixa da corretora ("BTG Investimentos"): pelo nome
    ou pelo subtipo."""
    text = inbox.normalized(f"{of_account['name'] or ''} {of_account['subtype'] or ''}")
    return any(word in text.split() for word in ("investimentos", "investimento", "investments", "corretora"))


def _require_bank_target(conn, current_user_id, account_id, of_account=None):
    row = conn.execute(
        "SELECT * FROM accounts WHERE id = ? AND user_id = ?", (account_id, current_user_id),
    ).fetchone()
    if not row:
        raise ValidationError("Conta nao encontrada.")
    if row["archived_at"]:
        raise ValidationError("Conta esta arquivada.")
    if row["type"] == "BROKERAGE" and not (of_account is not None and is_investment_account(of_account)):
        # O dinheiro da carteira tem o caminho dele (039): so a conta de
        # investimentos da corretora vai para a Corretora (044), e dela so a
        # transferencia com o banco vira lancamento.
        raise ValidationError("A Corretora so recebe a conta de investimentos da corretora.")
    # A moeda casa (conta global, 2026-10-27): a conta em dolar da Pluggy so
    # vai para a conta em dolar do app, e uma em reais so para uma em reais.
    of_currency = str((of_account["currency"] if of_account is not None else None) or "BRL").upper()
    if (row["currency"] or "BRL").upper() != of_currency:
        if of_currency == "BRL":
            raise ValidationError("Conta nao e em reais.")
        raise ValidationError(f"A conta do banco e em {of_currency}: escolha uma conta do app em {of_currency}.")


def _require_card_target(conn, current_user_id, card_id):
    row = conn.execute(
        "SELECT * FROM credit_cards WHERE id = ? AND user_id = ?", (card_id, current_user_id),
    ).fetchone()
    if not row:
        raise ValidationError("Cartao nao encontrado.")
    if row["archived_at"]:
        raise ValidationError("Cartao esta arquivado.")
    if not row["credit_enabled"]:
        raise ValidationError("Este cartao e so debito: mapeie a conta dele.")


def suggest_target(conn, current_user_id, account_row, connector_name):
    """Um palpite para o dono confirmar: no cartao, o final do numero no nome
    do cartao, senao o unico cartao do banco; na conta, a unica conta ativa
    do banco (campo banco ou nome); a conta de investimentos da corretora, a
    Corretora. O banco sai do nome da conta da Pluggy ("Cartão BTG BLACK") —
    no MeuPluggy o conector nao diz o banco —, senao do conector. Nunca
    gravado sozinho."""
    issuer = inbox.issuer_of_institution(account_row["name"]) or inbox.issuer_of_institution(connector_name)
    taken_column = "card_id" if account_row["type"] == "CREDIT" else "account_id"
    taken = {
        row[taken_column] for row in conn.execute(
            f"""
            SELECT a.{taken_column} FROM open_finance_accounts a
            JOIN open_finance_items i ON i.id = a.of_item_id AND i.user_id = a.user_id
            WHERE a.user_id = ? AND a.{taken_column} IS NOT NULL AND i.archived_at IS NULL
            """,
            (current_user_id,),
        ).fetchall()
    }
    if account_row["type"] == "CREDIT":
        cards = [row for row in inbox._cards(conn, current_user_id) if row["id"] not in taken]
        digits = re.sub(r"\D", "", account_row["number"] or "")[-4:]
        if len(digits) == 4:
            by_digits = [card for card in cards if digits in (card["name"] or "")]
            if len(by_digits) == 1:
                return by_digits[0]["id"]
        if issuer in inbox.ISSUER_ALIASES:
            by_issuer = [card for card in cards if inbox._mentions(card["name"], inbox.ISSUER_ALIASES[issuer])]
            if len(by_issuer) == 1:
                return by_issuer[0]["id"]
        return None
    brokerage = is_investment_account(account_row)
    accounts = [
        row for row in inbox._active_accounts(conn, current_user_id)
        if (row["type"] == "BROKERAGE") == brokerage
        and (row["currency"] or "BRL").upper() == str(account_row["currency"] or "BRL").upper()
        and row["id"] not in taken
    ]
    if brokerage or str(account_row["currency"] or "BRL").upper() != "BRL":
        # A Corretora, e a conta global: a unica da moeda.
        return accounts[0]["id"] if len(accounts) == 1 else None
    if issuer in inbox.ISSUER_ALIASES:
        aliases = inbox.ISSUER_ALIASES[issuer]
        by_issuer = [row for row in accounts if inbox._mentions(row["institution"], aliases) or inbox._mentions(row["name"], aliases)]
        if len(by_issuer) == 1:
            return by_issuer[0]["id"]
    return None


# ---------------------------------------------------------------------------
# Puxar
# ---------------------------------------------------------------------------

def _date_from(conn, current_user_id, account_row, today):
    synced = parse_iso_date(account_row["synced_until"]) if account_row["synced_until"] else None
    if synced:
        start = synced - timedelta(days=OVERLAP_DAYS)
    else:
        start = today - timedelta(days=first_sync_days(conn, current_user_id))
    return _day_text(start)


def _seconds(stamp):
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0


def sync_item(current_user_id, of_item_id, today=None, history_from=None):
    """Um pull completo de um item, so com GET: o item, as contas, as
    transacoes de cada conta e, na corretora, as posicoes e operacoes.
    `history_from` (AAAA-MM-DD) puxa dessa data em todas as contas (o historico).
    Devolve {status, counts: {new, merged, ...}, removed, auto_recorded?, investments?}."""
    _require_configured()
    lock = _sync_lock(current_user_id)
    if not lock.acquire(timeout=120):
        raise ValidationError("Outra atualizacao do Open Finance esta em andamento.")
    try:
        return _sync_item_locked(current_user_id, of_item_id, today or _today(), history_from)
    finally:
        lock.release()


def _record_refusal(current_user_id, of_item_id, exc):
    """A Pluggy recusou (ou nao respondeu): a mensagem fica no item, que Ajustes
    mostra, e no log do container (um limite esgotado aparece nos dois)."""
    logger.warning(
        "Open Finance: a Pluggy recusou o pull",
        extra={"user_id": current_user_id, "item": of_item_id, "status": exc.status, "code": exc.code,
               "error": str(exc)[:300]},
    )
    with get_db() as conn:
        conn.execute(
            "UPDATE open_finance_items SET last_sync_error = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (str(exc)[:300], utc_timestamp(), of_item_id, current_user_id),
        )


def _sync_item_locked(current_user_id, of_item_id, today, history_from):
    with get_db() as conn:
        row = fetch_item(conn, current_user_id, of_item_id)
        if not row:
            raise LookupError("Conexao nao encontrada.")
        row = row_to_dict(row)
        windows = {
            account["pluggy_account_id"]: history_from or _date_from(conn, current_user_id, account, today)
            for account in item_accounts(conn, current_user_id, of_item_id)
        }
        with_pending = include_pending(conn, current_user_id)
        first_days = first_sync_days(conn, current_user_id)
    api = client()
    try:
        pluggy_item = api.get_item(row["pluggy_item_id"]) or {}
        accounts = api.list_accounts(row["pluggy_item_id"])
        pulled = {}
        for raw in accounts:
            if not _account_type(raw) or not raw.get("id"):
                continue
            date_from = windows.get(raw["id"]) or history_from or _day_text(today - timedelta(days=first_days))
            pulled[raw["id"]] = (date_from, api.list_transactions(raw["id"], date_from))
    except PluggyError as exc:
        _record_refusal(current_user_id, of_item_id, exc)
        raise
    investments = open_finance_investments.fetch(api, row["pluggy_item_id"], logger)

    counts = {}
    removed = 0
    auto = None
    today_text = _day_text(today)
    with get_db() as conn:
        _save_item_status(conn, current_user_id, of_item_id, pluggy_item)
        _upsert_accounts(conn, current_user_id, of_item_id, accounts)
        rules = import_rules_for_matching(conn, current_user_id)
        stamp = utc_timestamp()
        batch = []
        for pluggy_account_id, (date_from, transactions) in pulled.items():
            account = row_to_dict(conn.execute(
                "SELECT * FROM open_finance_accounts WHERE user_id = ? AND pluggy_account_id = ?",
                (current_user_id, pluggy_account_id),
            ).fetchone())
            if account["type"] == "CREDIT":
                sign, source = open_finance_inbox.learn_charge_sign(
                    transactions, account["charge_sign"], account["charge_sign_source"],
                )
                if (sign, source) != (account["charge_sign"], account["charge_sign_source"]):
                    conn.execute(
                        "UPDATE open_finance_accounts SET charge_sign = ?, charge_sign_source = ? WHERE id = ? AND user_id = ?",
                        (sign, source, account["id"], current_user_id),
                    )
                    account["charge_sign"], account["charge_sign_source"] = sign, source
            for raw in transactions:
                try:
                    tx = open_finance_inbox.normalize_transaction(
                        raw, account["type"], account["charge_sign"] or 1, include_pending=with_pending,
                        account_currency=account["currency"],
                    )
                except open_finance_inbox.Skip as skip:
                    key = "skipped_pending" if str(skip) == open_finance_inbox.STATUS_SKIPPED_PENDING else "skipped"
                    counts[key] = counts.get(key, 0) + 1
                    continue
                batch.append((tx["date"], tx["direction"] != "OUT", account, tx))
            seen = {str(raw.get("id")) for raw in transactions if isinstance(raw, dict)}
            removed += open_finance_inbox.vanish_missing(conn, current_user_id, account, seen, date_from, today_text)
            if not account["synced_until"] or account["synced_until"] < today_text:
                conn.execute(
                    "UPDATE open_finance_accounts SET synced_until = ? WHERE id = ? AND user_id = ?",
                    (today_text, account["id"], current_user_id),
                )
        # Na ordem do tempo, todas as contas juntas: a saida de uma conta e a
        # entrada na outra se encontram no mesmo pull.
        for _date, _incoming, account, tx in sorted(batch, key=lambda entry: (entry[0], entry[1])):
            status = open_finance_inbox.ingest(conn, current_user_id, account, tx, rules, stamp)
            counts[status] = counts.get(status, 0) + 1
        if investments is not None:
            investments = open_finance_investments.apply(conn, current_user_id, of_item_id, investments, today)
        if open_finance_auto.enabled(conn, current_user_id):
            auto = open_finance_auto.record_pending(conn, current_user_id, today)
        conn.execute(
            "UPDATE open_finance_items SET last_sync_at = ?, last_sync_error = NULL, updated_at = ? WHERE id = ? AND user_id = ?",
            (stamp, stamp, of_item_id, current_user_id),
        )
    if open_finance_investments.recorded_any(investments):
        realized_results.refresh_realized_results(current_user_id)
    logger.info(
        "Open Finance: pull",
        extra={"user_id": current_user_id, "item": of_item_id, "status": pluggy_item.get("status"), **counts,
               "removed": removed, "auto_recorded": auto},
    )
    result = {"status": pluggy_item.get("status"), "counts": counts, "removed": removed}
    if auto is not None:
        result["auto_recorded"] = auto
    if investments is not None:
        result["investments"] = investments
    return result


def sync_user(current_user_id):
    """Todas as conexoes ativas do usuario; uma que falha nao impede as outras."""
    results = {}
    with get_db() as conn:
        ids = [row["id"] for row in active_items(conn, current_user_id)]
    for of_item_id in ids:
        try:
            results[of_item_id] = sync_item(current_user_id, of_item_id)
        except (PluggyError, ValidationError, LookupError) as exc:
            results[of_item_id] = {"error": str(exc)}
    return results


# ---------------------------------------------------------------------------
# Historico: comparar tudo que ja aconteceu, contar, e so gravar confirmado
# ---------------------------------------------------------------------------

def _parse_history_days(value):
    if value is None:
        return DEFAULT_HISTORY_DAYS
    if isinstance(value, bool):
        raise ValidationError("Informe os dias do histórico.")
    try:
        days = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Informe os dias do histórico.") from exc
    if not 1 <= days <= MAX_FIRST_SYNC_DAYS:
        raise ValidationError(f"O histórico vai de 1 a {MAX_FIRST_SYNC_DAYS} dias.")
    return days


def history_preview(current_user_id, days=None, today=None):
    """Le (GET) o que a Pluggy tem dos ultimos `days` dias em cada conta mapeada
    e conta, sem gravar nada: `linked` (ja ligado a um lancamento), `to_link`
    (um lancamento do app e o mesmo movimento: sera ligado), `to_record` (sera
    gravado, a revisar; 045: o investimento numa conta de banco tambem),
    `waiting` (sempre 0 desde 045, mantido para as telas), `covered` (parcela 2..n, pagamento de fatura, caixa da
    corretora) e `app_only` (lancamentos do app que o banco nao tem: ficam
    como estao, nunca apagados)."""
    _require_configured()
    days = _parse_history_days(days)
    today = today or _today()
    history_from = _day_text(today - timedelta(days=days))
    with get_db() as conn:
        items = [row_to_dict(row) for row in active_items(conn, current_user_id)]
        accounts = {
            row["pluggy_account_id"]: row_to_dict(row)
            for item in items for row in item_accounts(conn, current_user_id, item["id"])
            if not row["ignored_at"] and (row["account_id"] or row["card_id"])
        }
        with_pending = include_pending(conn, current_user_id)
    api = client()
    pulled = {}
    for pluggy_account_id in accounts:
        try:
            pulled[pluggy_account_id] = api.list_transactions(pluggy_account_id, history_from)
        except PluggyError as exc:
            logger.warning("Open Finance: historico recusado", extra={"status": exc.status, "error": str(exc)[:300]})
            raise
    result = []
    with get_db() as conn:
        for pluggy_account_id, account in accounts.items():
            counts = {"linked": 0, "to_link": 0, "to_record": 0, "waiting": 0, "covered": 0}
            bank_entries = []
            claimed = set()
            for raw in pulled[pluggy_account_id]:
                try:
                    tx = open_finance_inbox.normalize_transaction(
                        raw, account["type"], account["charge_sign"] or 1, include_pending=with_pending,
                        account_currency=account["currency"],
                    )
                except open_finance_inbox.Skip:
                    continue
                counts[_preview_status(conn, current_user_id, account, tx, claimed, today)] += 1
                bank_entries.append(tx)
            counts["app_only"] = _app_only_count(conn, current_user_id, account, bank_entries, history_from, today)
            result.append({
                "id": account["id"],
                "name": account["name"],
                "type": account["type"],
                "bank_name": inbox.open_finance_bank_name(account["name"], None),
                "target_name": _target_name(conn, current_user_id, account),
                **counts,
            })
    return {"days": days, "from": history_from, "accounts": result}


def _target_name(conn, current_user_id, account):
    if account["account_id"]:
        row = conn.execute("SELECT name FROM accounts WHERE id = ? AND user_id = ?",
                           (account["account_id"], current_user_id)).fetchone()
    else:
        row = conn.execute("SELECT name FROM credit_cards WHERE id = ? AND user_id = ?",
                           (account["card_id"], current_user_id)).fetchone()
    return row["name"] if row else None


def _preview_status(conn, current_user_id, account, tx, claimed, today):
    known = open_finance_inbox.fetch_row(conn, current_user_id, tx["dedup_key"])
    if known and known["target_id"]:
        return "linked"
    if known and known["role"] in ("COVERED", "INVOICE_PAYMENT"):
        return "covered"
    if tx["movement"] == "INVOICE_PAYMENT":
        return "covered"
    if account["type"] == "CREDIT" and tx["direction"] == "OUT" and (tx["installment_number"] or 1) > 1:
        return "covered"
    brokerage = account["type"] == "BANK" and open_finance_inbox.is_brokerage(conn, current_user_id, account["account_id"])
    if brokerage and tx["movement"] not in ("TRANSFER", "SELF_TRANSFER"):
        return "covered"
    entry_type = "CARD" if account["type"] == "CREDIT" else ("EXPENSE" if tx["direction"] == "OUT" else "INCOME")
    candidates = inbox.existing_rows(
        conn, current_user_id, entry_type=entry_type, direction=tx["direction"], cents=tx["amount_cents"],
        date_text=tx["date"], account_id=account["account_id"], card_id=account["card_id"],
    )
    for candidate in candidates:
        key = (candidate["table"], candidate["id"])
        if key in claimed or open_finance_auto._linked_elsewhere(conn, current_user_id, candidate, ""):
            continue
        claimed.add(key)
        return "to_link"
    # Uma transferencia entre contas conectadas vira UMA (as duas pontas chegam
    # no mesmo historico); com terceiros, despesa/receita.
    return "to_record"


def _app_only_count(conn, current_user_id, account, bank_entries, date_from, today):
    """Os lancamentos do app nesta conta, na janela, que nenhum movimento do
    banco explica (a mesma regra da Conferencia)."""
    card = account["type"] == "CREDIT"
    entries = []
    for tx in bank_entries:
        if card and tx["movement"] == "INVOICE_PAYMENT":
            continue
        if card and tx["direction"] == "OUT" and (tx["installment_number"] or 1) > 1:
            continue
        entries.append({
            "id": tx["dedup_key"], "date": tx["date"],
            "cents": -tx["amount_cents"] if tx["direction"] == "OUT" else tx["amount_cents"],
            "tolerance": (tx["total_installments"] or 1) if card and (tx["total_installments"] or 1) > 1 else 0,
        })
    target = account["card_id"] if card else account["account_id"]
    if card:
        app = open_finance_check._card_rows(conn, current_user_id, target, date_from, _day_text(today))
    else:
        app = open_finance_check._account_rows(conn, current_user_id, target, date_from, _day_text(today))
    _bank_only, app_only = open_finance_check.match_movements(entries, app)
    return len(app_only)


def history_apply(current_user_id, days=None, confirm=False, today=None):
    """Aplica o historico: puxa os ultimos `days` dias de cada conexao (GET) e
    grava/liga o que o preview contou. Pede "Gravar sozinho" ligado e
    `confirm: true`. Nada digitado pelo dono e apagado; o que so existe no
    app fica, e a Conferencia o lista."""
    if confirm is not True:
        raise ValidationError("Confirme o histórico (confirm: true) depois de ver a prévia.")
    days = _parse_history_days(days)
    today = today or _today()
    with get_db() as conn:
        if not open_finance_auto.enabled(conn, current_user_id):
            raise ValidationError("Ligue \"Gravar sozinho\" antes de trazer o histórico.")
    history_from = _day_text(today - timedelta(days=days))
    results = {}
    with get_db() as conn:
        ids = [row["id"] for row in active_items(conn, current_user_id)]
    for of_item_id in ids:
        try:
            results[of_item_id] = sync_item(current_user_id, of_item_id, today=today, history_from=history_from)
        except (PluggyError, ValidationError, LookupError) as exc:
            results[of_item_id] = {"error": str(exc)}
    with get_db() as conn:
        # Uma transferencia segurada a espera da outra ponta, de dias atras, ja
        # pode ser decidida depois de todas as conexoes puxadas.
        auto = open_finance_auto.record_pending(conn, current_user_id, today)
    return {"days": days, "from": history_from, "items": results, "auto_recorded": auto}


# ---------------------------------------------------------------------------
# Para a tela
# ---------------------------------------------------------------------------

def list_view(current_user_id):
    configured = is_configured()
    with get_db() as conn:
        balances = {row["id"]: row for row in account_balance_rows(conn, current_user_id)}
        names = {row["id"]: row["name"] for row in conn.execute(
            "SELECT id, name FROM credit_cards WHERE user_id = ?", (current_user_id,),
        ).fetchall()}
        items = []
        for row in active_items(conn, current_user_id):
            accounts = []
            for account in item_accounts(conn, current_user_id, row["id"]):
                entry = {
                    "id": account["id"],
                    "type": account["type"],
                    "subtype": account["subtype"],
                    "name": account["name"],
                    "number": account["number"],
                    "currency": account["currency"],
                    "pluggy_balance": account["balance"],
                    "balance_at": account["balance_at"],
                    "account_id": account["account_id"],
                    "card_id": account["card_id"],
                    "charge_sign": account["charge_sign"],
                    "charge_sign_source": account["charge_sign_source"],
                    "synced_until": account["synced_until"],
                    "ignored": bool(account["ignored_at"]),
                    "brokerage": bool(account["account_id"]) and open_finance_inbox.is_brokerage(
                        conn, current_user_id, account["account_id"],
                    ),
                    "unmapped_count": conn.execute(
                        "SELECT COUNT(*) FROM open_finance_transactions WHERE user_id = ? AND of_account_id = ? AND role = 'UNMAPPED'",
                        (current_user_id, account["id"]),
                    ).fetchone()[0],
                    "suggested_id": None,
                }
                if not account["account_id"] and not account["card_id"] and not account["ignored_at"]:
                    entry["suggested_id"] = suggest_target(conn, current_user_id, account, row["connector_name"])
                difference_cents = None
                if account["account_id"] and account["account_id"] in balances:
                    mine = balances[account["account_id"]]
                    entry["target_name"] = mine["name"]
                    # Conferir, nunca ajustar: o saldo da conta e o do app
                    # (inicial + lancamentos), o mesmo do consolidado.
                    entry["app_balance"] = rounded_money(mine["balance"])
                    if account["balance"] is not None:
                        entry["difference"] = rounded_money(account["balance"] - mine["balance"])
                        difference_cents = int(round(entry["difference"] * 100))
                elif account["card_id"]:
                    entry["target_name"] = names.get(account["card_id"])
                entry["check"] = open_finance_check.account_check(conn, current_user_id, account, difference_cents)
                accounts.append(entry)
            items.append({
                "id": row["id"],
                "connector_name": row["connector_name"],
                "bank_name": item_bank_name(conn, current_user_id, row),
                "status": row["status"],
                "execution_status": row["execution_status"],
                "error_code": row["error_code"],
                "error_message": row["error_message"],
                "needs_owner": needs_owner(row),
                "pluggy_updated_at": row["pluggy_updated_at"],
                "last_sync_at": row["last_sync_at"],
                "last_sync_error": row["last_sync_error"],
                "accounts": accounts,
            })
        days = first_sync_days(conn, current_user_id)
        auto_record = open_finance_auto.enabled(conn, current_user_id)
        portfolio = open_finance_investments.portfolio_check(conn, current_user_id)
    return {"configured": configured, "first_sync_days": days, "auto_record": auto_record, "items": items,
            "investments": portfolio}
