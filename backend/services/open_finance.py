"""Open Finance pela Pluggy (043): conexoes, mapeamento e o pull.

- **Conectar** e na web (Ajustes › Open Finance): o servidor cria o connect
  token (`connect_token()`), o widget Pluggy Connect abre com ele e devolve o
  `itemId`, que `register_item()` guarda com as contas do item.
- **Mapear** (`map_account()`): cada conta BANK da Pluggy a uma conta ativa do
  dono (nunca a Corretora), cada CREDIT a um cartao ativo com credito. Uma
  sugestao pelo banco e pelo final vem na listagem; so o dono confirma.
- **Puxar** (`sync_item()`): o servidor so e alcancavel na tailnet, entao nao
  ha webhook. O botao "Atualizar" e a thread de services/open_finance_refresh.py
  pedem dados novos ao banco (`PATCH /items/{id}`, que gasta o limite mensal da
  instituicao por CPF; nunca para um item que espera o dono) e puxam as
  transacoes desde o ultimo pull menos OVERLAP_DAYS (o primeiro: a janela que o
  dono escolheu, 30 dias por padrao). Tudo vai para o Aprovar
  (services/open_finance_inbox.py).
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
    OPEN_FINANCE_UPDATE_WAIT_SECONDS,
    PLUGGY_BASE_URL,
    PLUGGY_CLIENT_ID,
    PLUGGY_CLIENT_SECRET,
    PLUGGY_TIMEOUT_SECONDS,
)
from dates import parse_iso_date
from db import get_db, new_id, row_to_dict, utc_timestamp
from money import rounded_money
from services import inbox, invoices, open_finance_inbox
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
# Status em que so o dono resolve (nova senha, um codigo, aceitar termos no
# banco): nada pede atualizacao, a mensagem fica em Ajustes.
OWNER_ACTION_STATUSES = {"LOGIN_ERROR", "WAITING_USER_INPUT"}
OWNER_ACTION_EXECUTIONS = {
    "INVALID_CREDENTIALS", "ACCOUNT_LOCKED", "ACCOUNT_NEEDS_ACTION", "USER_NOT_SUPPORTED",
    "ACCOUNT_CREDENTIALS_RESET", "USER_AUTHORIZATION_NOT_GRANTED", "USER_AUTHORIZATION_REVOKED",
    "USER_AUTHORIZATION_PENDING", "INVALID_CREDENTIALS_MFA",
}
# A Pluggy recusa outro pedido de dados novos menos de 1 h depois do ultimo
# ("Client updates on this item are allowed at most every 1 hours", visto em
# 2026-10-27; conectar conta como um). Antes disso, "Atualizar" so le.
MIN_UPDATE_INTERVAL_SECONDS = 3600
UPDATE_POLL_SECONDS = 3
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


def set_first_sync_days(conn, current_user_id, value):
    if isinstance(value, bool):
        raise ValidationError("Informe os dias da primeira busca.")
    try:
        days = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Informe os dias da primeira busca.") from exc
    if not 1 <= days <= MAX_FIRST_SYNC_DAYS:
        raise ValidationError(f"A primeira busca vai de 1 a {MAX_FIRST_SYNC_DAYS} dias.")
    conn.execute(
        """
        INSERT INTO user_settings (user_id, setting_key, value, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (user_id, setting_key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (current_user_id, FIRST_SYNC_SETTING, str(days), utc_timestamp()),
    )
    return days


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
            sync_item(current_user_id, of_item_id, request_update=False)
        except PluggyError as exc:
            logger.warning("Open Finance: primeiro pull falhou", extra={"error": str(exc)})
    return of_item_id


def disconnect(current_user_id, of_item_id, confirm):
    """Apaga o item na Pluggy e arquiva o nosso. `confirm` tem de ser o nome
    do banco (a guarda dos endpoints destrutivos). Nenhum lancamento muda; os
    itens pendentes do Aprovar ficam para o dono decidir."""
    with get_db() as conn:
        row = fetch_item(conn, current_user_id, of_item_id)
    if not row:
        raise LookupError("Conexao nao encontrada.")
    expected = row["connector_name"] or "Open Finance"
    if str(confirm or "").strip() != expected:
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
    dono; `null` desliga. O que ja foi puxado sem mapeamento entra no Aprovar."""
    if not isinstance(payload, dict):
        raise ValidationError("Envie um objeto JSON.")
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
                _require_bank_target(conn, current_user_id, target)
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
            UPDATE open_finance_accounts SET {column} = ?, {other} = NULL, mapped_at = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (target, utc_timestamp() if target else None, utc_timestamp(), of_account_id, current_user_id),
        )
        account = open_finance_inbox.fetch_account(conn, current_user_id, of_account_id)
        placed = []
        if target:
            placed = open_finance_inbox.place_unmapped(
                conn, current_user_id, account, import_rules_for_matching(conn, current_user_id),
            )
    return {"placed": len(placed)}


def _target_id(payload, key):
    if key not in payload:
        raise ValidationError("Escolha a conta ou o cartao.")
    value = payload[key]
    if value in (None, ""):
        return None
    if not isinstance(value, str) or len(value) > 64:
        raise ValidationError("Destino invalido.")
    return value


def _require_bank_target(conn, current_user_id, account_id):
    row = conn.execute(
        "SELECT * FROM accounts WHERE id = ? AND user_id = ?", (account_id, current_user_id),
    ).fetchone()
    if not row:
        raise ValidationError("Conta nao encontrada.")
    if row["archived_at"]:
        raise ValidationError("Conta esta arquivada.")
    if row["type"] == "BROKERAGE":
        # O dinheiro da carteira tem o caminho dele (039): o Open Finance nao entra.
        raise ValidationError("A Corretora nao recebe movimentos do Open Finance.")
    if (row["currency"] or "BRL") != "BRL":
        raise ValidationError("Conta nao e em reais.")


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
    do banco (campo banco ou nome). Nunca gravado sozinho."""
    issuer = inbox.issuer_of_institution(connector_name)
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
    accounts = [
        row for row in inbox._active_accounts(conn, current_user_id)
        if row["type"] != "BROKERAGE" and (row["currency"] or "BRL") == "BRL" and row["id"] not in taken
    ]
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


def _request_update(row, now_seconds):
    """Pedir dados novos ao banco agora? Nao para um item que espera o dono
    (a Pluggy recusaria, e repetir gasta o limite), nem menos de 1 h depois do
    ultimo pedido nosso ou da ultima leitura da Pluggy."""
    if needs_owner(row):
        return False
    for stamp in (row["update_requested_at"], row["pluggy_updated_at"]):
        if stamp and now_seconds - _seconds(stamp) < MIN_UPDATE_INTERVAL_SECONDS:
            return False
    return True


def sync_item(current_user_id, of_item_id, request_update=True, wait_seconds=None, today=None):
    """Um pull completo de um item. Devolve um resumo
    {status, accounts, counts: {new, merged, ...}, removed}."""
    _require_configured()
    wait_seconds = OPEN_FINANCE_UPDATE_WAIT_SECONDS if wait_seconds is None else wait_seconds
    lock = _sync_lock(current_user_id)
    if not lock.acquire(timeout=max(5, wait_seconds + 60)):
        raise ValidationError("Outra atualizacao do Open Finance esta em andamento.")
    try:
        return _sync_item_locked(current_user_id, of_item_id, request_update, wait_seconds, today or _today())
    finally:
        lock.release()


def _sync_item_locked(current_user_id, of_item_id, request_update, wait_seconds, today):
    with get_db() as conn:
        row = fetch_item(conn, current_user_id, of_item_id)
        if not row:
            raise LookupError("Conexao nao encontrada.")
        row = row_to_dict(row)
        windows = {
            account["pluggy_account_id"]: _date_from(conn, current_user_id, account, today)
            for account in item_accounts(conn, current_user_id, of_item_id)
        }
    api = client()
    try:
        pluggy_item = None
        if request_update and _request_update(row, time.time()):
            try:
                pluggy_item = api.update_item(row["pluggy_item_id"]) or {}
            except PluggyError as exc:
                if exc.network or (exc.status or 0) >= 500:
                    raise
                # A Pluggy recusou o pedido (intervalo, limite do mes): le o que ja tem.
                logger.info("Open Finance: pedido de atualizacao recusado", extra={"status": exc.status})
        if pluggy_item is not None:
            with get_db() as conn:
                conn.execute(
                    "UPDATE open_finance_items SET update_requested_at = ? WHERE id = ? AND user_id = ?",
                    (utc_timestamp(), of_item_id, current_user_id),
                )
            deadline = time.monotonic() + wait_seconds
            while pluggy_item.get("status") == "UPDATING" and time.monotonic() < deadline:
                time.sleep(UPDATE_POLL_SECONDS)
                pluggy_item = api.get_item(row["pluggy_item_id"]) or {}
            if pluggy_item.get("status") in (None, "UPDATING") and wait_seconds:
                pluggy_item = api.get_item(row["pluggy_item_id"]) or pluggy_item
        else:
            pluggy_item = api.get_item(row["pluggy_item_id"]) or {}
        accounts = api.list_accounts(row["pluggy_item_id"])
        pulled = {}
        for raw in accounts:
            if not _account_type(raw) or not raw.get("id"):
                continue
            date_from = windows.get(raw["id"]) or _day_text(today - timedelta(days=DEFAULT_FIRST_SYNC_DAYS))
            pulled[raw["id"]] = (date_from, api.list_transactions(raw["id"], date_from))
    except PluggyError as exc:
        with get_db() as conn:
            conn.execute(
                "UPDATE open_finance_items SET last_sync_error = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (str(exc)[:300], utc_timestamp(), of_item_id, current_user_id),
            )
        raise

    counts = {}
    removed = 0
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
                    tx = open_finance_inbox.normalize_transaction(raw, account["type"], account["charge_sign"] or 1)
                except open_finance_inbox.Skip as skip:
                    key = "skipped_pending" if str(skip) == open_finance_inbox.STATUS_SKIPPED_PENDING else "skipped"
                    counts[key] = counts.get(key, 0) + 1
                    continue
                batch.append((tx["date"], tx["direction"] != "OUT", account, tx))
            seen = {str(raw.get("id")) for raw in transactions if isinstance(raw, dict)}
            removed += open_finance_inbox.vanish_missing(conn, current_user_id, account, seen, date_from, today_text)
            conn.execute(
                "UPDATE open_finance_accounts SET synced_until = ? WHERE id = ? AND user_id = ?",
                (today_text, account["id"], current_user_id),
            )
        # Na ordem do tempo, todas as contas juntas: a saida de uma conta e a
        # entrada na outra se encontram no mesmo pull.
        for _date, _incoming, account, tx in sorted(batch, key=lambda entry: (entry[0], entry[1])):
            status = open_finance_inbox.ingest(conn, current_user_id, account, tx, rules, stamp)
            counts[status] = counts.get(status, 0) + 1
        conn.execute(
            "UPDATE open_finance_items SET last_sync_at = ?, last_sync_error = NULL, updated_at = ? WHERE id = ? AND user_id = ?",
            (stamp, stamp, of_item_id, current_user_id),
        )
    logger.info(
        "Open Finance: pull",
        extra={"user_id": current_user_id, "item": of_item_id, "status": pluggy_item.get("status"), **counts,
               "removed": removed},
    )
    return {"status": pluggy_item.get("status"), "counts": counts, "removed": removed}


def sync_user(current_user_id, request_update=True):
    """Todas as conexoes ativas do usuario; uma que falha nao impede as outras."""
    results = {}
    with get_db() as conn:
        ids = [row["id"] for row in active_items(conn, current_user_id)]
    for of_item_id in ids:
        try:
            results[of_item_id] = sync_item(current_user_id, of_item_id, request_update=request_update)
        except (PluggyError, ValidationError, LookupError) as exc:
            results[of_item_id] = {"error": str(exc)}
    return results


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
                    "unmapped_count": conn.execute(
                        "SELECT COUNT(*) FROM open_finance_transactions WHERE user_id = ? AND of_account_id = ? AND role = 'UNMAPPED'",
                        (current_user_id, account["id"]),
                    ).fetchone()[0],
                    "suggested_id": None,
                }
                if not account["account_id"] and not account["card_id"]:
                    entry["suggested_id"] = suggest_target(conn, current_user_id, account, row["connector_name"])
                if account["account_id"] and account["account_id"] in balances:
                    mine = balances[account["account_id"]]
                    entry["target_name"] = mine["name"]
                    # Conferir, nunca ajustar: o saldo da conta e o do app
                    # (inicial + lancamentos), o mesmo do consolidado.
                    entry["app_balance"] = rounded_money(mine["balance"])
                    if account["balance"] is not None:
                        entry["difference"] = rounded_money(account["balance"] - mine["balance"])
                elif account["card_id"]:
                    entry["target_name"] = names.get(account["card_id"])
                accounts.append(entry)
            items.append({
                "id": row["id"],
                "connector_name": row["connector_name"],
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
    return {"configured": configured, "first_sync_days": days, "items": items}
