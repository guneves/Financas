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
  LATE_POSTING_DAYS (o primeiro: a janela que o dono escolheu, 30 dias por
  padrao; `_date_from()`) e vao para o Aprovar (services/open_finance_inbox.py); com "Gravar sozinho"
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

from datetime import datetime, timedelta

from applog import get_logger
from dates import parse_iso_date
from db import get_db, new_id, row_to_dict, utc_timestamp
from money import rounded_money
from services import (
    inbox,
    open_finance_auto,
    open_finance_check,
    open_finance_inbox,
    open_finance_investments,
    open_finance_invoices,
    open_finance_orphans,
    realized_results,
)
# `open_finance.invoices` e lido de fora (os testes congelam o relogio por ele): fica,
# mesmo sem uso direto aqui desde que `_today()` foi para open_finance_settings.
from services import invoices  # noqa: F401
from services.accounts import account_balance_rows, account_balance_until
from services.broker_cash import settled_balance
from services.import_rules import import_rules_for_matching
from services.open_finance_mapping import (  # noqa: F401  (reexportados: o resto do app os le daqui)
    _require_bank_target,
    _require_card_target,
    _set_ignored,
    _target_id,
    is_investment_account,
    map_account,
    suggest_target,
)
from services.open_finance_settings import (  # noqa: F401  (reexportados: o resto do app os le daqui)
    AUTO_RECORD_SETTING,
    DEFAULT_FIRST_SYNC_DAYS,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_SYNC_HOURS,
    FIRST_SYNC_SETTING,
    INCLUDE_PENDING_SETTING,
    LATE_POSTING_DAYS,
    MAX_FIRST_SYNC_DAYS,
    MAX_SYNC_HOURS,
    MIN_SYNC_HOURS,
    OVERLAP_DAYS,
    OWNER_ACTION_EXECUTIONS,
    OWNER_ACTION_STATUSES,
    PLUGGY_ID_PATTERN,
    SETTINGS_FIELDS,
    SYNC_HOURS_SETTING,
    SYNC_OFF,
    NotConfigured,
    PluggyError,
    _bool_field,
    _client,
    _client_lock,
    _day_text,
    _parse_first_sync_days,
    _require_configured,
    _sync_lock,
    _sync_locks,
    _sync_locks_guard,
    _today,
    active_items,
    client,
    default_sync_hours,
    fetch_item,
    first_sync_days,
    include_pending,
    is_configured,
    item_accounts,
    needs_owner,
    set_client,
    settings,
    sync_hours,
    update_settings,
)
from validators import ValidationError

logger = get_logger(__name__)

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


def register_item(current_user_id, pluggy_item_id, first_pull=True):
    """O widget conectou: guarda o item (ou reativa o que foi desconectado) e
    as contas dele, e faz o primeiro pull (`first_pull=False`: quem chama puxa).
    Devolve o id do nosso item."""
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
    if first_pull and pluggy_item.get("status") == "UPDATED":
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
# Puxar
# ---------------------------------------------------------------------------

def card_rows_with_bill(api, raw_account, rows):
    """A fatura de uma linha lancada e a do `billId` dela: o `billForecastDate` pode
    dizer outra (BTG, 2026-10-31: R$ 7 e R$ 8 um mes fora). Sem /bills, vale a previsao."""
    if _account_type(raw_account) != "CREDIT":
        return rows
    try:
        due_months = {bill["id"]: str(bill.get("dueDate") or "")[:7] for bill in api.list_bills(raw_account["id"])}
    except PluggyError:
        return rows
    for row in rows:
        metadata = row.get("creditCardMetadata") or {}
        month = due_months.get(metadata.get("billId"))
        if month:
            metadata["billForecastDate"] = month
    return rows


def _date_from(conn, current_user_id, account_row, today):
    """De que dia o pull pede as transacoes da conta. A primeira vez, a janela
    que o dono escolheu; depois, LATE_POSTING_DAYS antes do ultimo pull, porque
    o banco pode listar hoje um lancamento de dias atras. Nunca antes do dia mais
    antigo que a Pluggy ja deu desta conta (a primeira busca do dono), salvo os
    OVERLAP_DAYS de sempre."""
    synced = parse_iso_date(account_row["synced_until"]) if account_row["synced_until"] else None
    if not synced:
        return _day_text(today - timedelta(days=first_sync_days(conn, current_user_id)))
    floor = synced - timedelta(days=OVERLAP_DAYS)
    # O dia da Pluggy (posted_on), que e o que o filtro dela olha; a parcela
    # 2..n (COVERED) tem a data da compra, que pode ser de meses antes.
    first = conn.execute(
        """
        SELECT MIN(COALESCE(posted_on, date)) AS first FROM open_finance_transactions
        WHERE user_id = ? AND of_account_id = ? AND role <> 'COVERED'
        """,
        (current_user_id, account_row["id"]),
    ).fetchone()["first"]
    first_day = parse_iso_date(first)
    if first_day:
        floor = min(floor, first_day)
    return _day_text(max(synced - timedelta(days=LATE_POSTING_DAYS), floor))


def _seconds(stamp):
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0


def _foreign_days(pulled):
    """(moeda, dia) dos movimentos que a Pluggy trouxe em outra moeda sem o
    valor na moeda da conta: os que in_reais_now() converte pela PTAX."""
    days = set()
    for _date_from, transactions in pulled.values():
        for raw in transactions:
            if not isinstance(raw, dict) or raw.get("amountInAccountCurrency") is not None:
                continue
            currency = str(raw.get("currencyCode") or "BRL").upper()
            if currency != "BRL":
                days.add((currency, str(raw.get("date") or "")[:10]))
    return days


def sync_item(current_user_id, of_item_id, today=None, history_from=None, record=True):
    """Um pull completo de um item, so com GET: o item, as contas, as
    transacoes de cada conta e, na corretora, as posicoes e operacoes.
    `history_from` (AAAA-MM-DD) puxa dessa data em todas as contas (o historico).
    `record=False`: nao grava os itens ainda (pull_history() grava depois de
    puxar todas as conexoes).
    Devolve {status, counts: {new, merged, ...}, removed, auto_recorded?, investments?}."""
    _require_configured()
    lock = _sync_lock(current_user_id)
    if not lock.acquire(timeout=120):
        raise ValidationError("Outra atualizacao do Open Finance esta em andamento.")
    try:
        return _sync_item_locked(current_user_id, of_item_id, today or _today(), history_from, record)
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


def _sync_item_locked(current_user_id, of_item_id, today, history_from, record=True):
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
            pulled[raw["id"]] = (date_from, card_rows_with_bill(api, raw, api.list_transactions(raw["id"], date_from)))
    except PluggyError as exc:
        _record_refusal(current_user_id, of_item_id, exc)
        raise
    investments = open_finance_investments.fetch(api, row["pluggy_item_id"], logger)
    # Ainda na fase de rede: a PTAX dos movimentos em outra moeda, antes de a
    # transacao de escrita abrir (la dentro in_reais_now() le so o guardado).
    with get_db() as conn:
        open_finance_auto.prefetch_rates(conn, current_user_id, _foreign_days(pulled))

    counts = {}
    removed = 0
    orphans_removed = 0
    auto = None
    today_text = _day_text(today)
    with get_db() as conn:
        _save_item_status(conn, current_user_id, of_item_id, pluggy_item)
        _upsert_accounts(conn, current_user_id, of_item_id, accounts)
        rules = import_rules_for_matching(conn, current_user_id)
        stamp = utc_timestamp()
        batch = []
        # Sucessao: o que sumiu de cada conta e calculado
        # antes, sem gravar; a id nova que continua uma sumida a sucede no
        # ingest(); so o que ninguem sucedeu some depois.
        missing = {}
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
                        raw, account["type"], account["charge_sign"] or 1,
                        include_pending=with_pending or account["type"] == "CREDIT",
                        account_currency=account["currency"],
                    )
                except open_finance_inbox.Skip as skip:
                    key = "skipped_pending" if str(skip) == open_finance_inbox.STATUS_SKIPPED_PENDING else "skipped"
                    counts[key] = counts.get(key, 0) + 1
                    continue
                batch.append((tx["date"], tx["direction"] != "OUT", account, tx))
            seen = {str(raw.get("id")) for raw in transactions if isinstance(raw, dict)}
            missing[account["id"]] = (
                seen, open_finance_inbox.missing_rows(conn, current_user_id, account, seen, date_from, today_text),
                [],
            )
            if not account["synced_until"] or account["synced_until"] < today_text:
                conn.execute(
                    "UPDATE open_finance_accounts SET synced_until = ? WHERE id = ? AND user_id = ?",
                    (today_text, account["id"], current_user_id),
                )
        # As novas de cada conta (o "um de cada lado" da sucessao com outro valor).
        for _date, _incoming, account, tx in batch:
            if open_finance_inbox.fetch_row(conn, current_user_id, tx["dedup_key"]) is None:
                missing[account["id"]][2].append(tx)
        pending_before = open_finance_inbox.pending_pluggy_items(conn, current_user_id)
        # Na ordem do tempo, todas as contas juntas: a saida de uma conta e a
        # entrada na outra se encontram no mesmo pull.
        for _date, _incoming, account, tx in sorted(batch, key=lambda entry: (entry[0], entry[1])):
            _seen, left, pulled_new = missing[account["id"]]
            status = open_finance_inbox.ingest(
                conn, current_user_id, account, tx, rules, stamp, missing=left, pulled=pulled_new,
            )
            counts[status] = counts.get(status, 0) + 1
        for seen, left, _pulled in missing.values():
            removed += open_finance_inbox.vanish_rows(conn, current_user_id, left, seen)
        # O par aproximado: depois de todos os pares
        # exatos do pull e antes de gravar, para nunca gravar duas vezes.
        near = open_finance_inbox.near_match_pass(conn, current_user_id, pending_before)
        if near:
            counts["near_match"] = near
        if investments is not None:
            investments = open_finance_investments.apply(conn, current_user_id, of_item_id, investments, today)
        if record and open_finance_auto.enabled(conn, current_user_id):
            auto = open_finance_auto.record_pending(conn, current_user_id, today)
        if record and open_finance_auto.enabled(conn, current_user_id):
            # Depois das compras: o pagamento do banco baixa a fatura delas.
            open_finance_invoices.record_bank_payments(conn, current_user_id)
            open_finance_inbox.mark_bank_investments(conn, current_user_id)
        conn.execute(
            "UPDATE open_finance_items SET last_sync_at = ?, last_sync_error = NULL, updated_at = ? WHERE id = ? AND user_id = ?",
            (stamp, stamp, of_item_id, current_user_id),
        )
        if record and open_finance_auto.enabled(conn, current_user_id):
            # As orfas (Fase 5): por ultimo, com tudo do pull no
            # lugar (pagamentos e fundos do banco inclusive) e o app ja tendo lido
            # o banco (last_sync_at acima), para o saldo comparar o que ficou.
            orphans_removed = open_finance_orphans.sweep(conn, current_user_id, of_item_id, today)
    if open_finance_investments.recorded_any(investments):
        realized_results.refresh_realized_results(current_user_id)
    logger.info(
        "Open Finance: pull",
        extra={"user_id": current_user_id, "item": of_item_id, "status": pluggy_item.get("status"), **counts,
               "removed": removed, "removed_orphans": orphans_removed, "auto_recorded": auto},
    )
    result = {"status": pluggy_item.get("status"), "counts": counts, "removed": removed,
              "removed_orphans": orphans_removed}
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
        except Exception as exc:  # um dado inesperado de um banco nao para os outros
            logger.exception("Open Finance: o pull falhou", extra={"user_id": current_user_id, "item": of_item_id})
            with get_db() as conn:
                conn.execute(
                    "UPDATE open_finance_items SET last_sync_error = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                    (f"Falha ao gravar o pull: {exc}"[:300], utc_timestamp(), of_item_id, current_user_id),
                )
            results[of_item_id] = {"error": str(exc)}
    return results


def sync_fresh_items(current_user_id):
    """O que a Pluggy acabou de trazer do banco entra ja (dono, 2026-11-01:
    "toda transacao, no momento em que chega"): um GET /items/{id} por conexao
    (so leitura, nao gasta o limite do CPF como o PATCH) e, se `lastUpdatedAt`
    andou desde o nosso ultimo pull, o pull dessa conexao. Devolve
    {of_item_id: resultado} so das puxadas."""
    if not is_configured():
        return {}
    with get_db() as conn:
        items = [row_to_dict(row) for row in active_items(conn, current_user_id)]
    api = client()
    results = {}
    for item in items:
        try:
            pluggy_item = api.get_item(item["pluggy_item_id"]) or {}
        except PluggyError as exc:
            logger.warning(f"Open Finance: a Pluggy nao respondeu o item {item['id']}: {exc}")
            continue
        stamp = pluggy_item.get("lastUpdatedAt")
        if not stamp or not item["last_sync_at"]:
            continue
        if _seconds(stamp) <= _seconds(item["pluggy_updated_at"]):
            continue
        try:
            results[item["id"]] = sync_item(current_user_id, item["id"])
        except (PluggyError, ValidationError, LookupError) as exc:
            results[item["id"]] = {"error": str(exc)}
        except Exception as exc:  # um banco nao para os outros
            logger.exception("Open Finance: o pull falhou", extra={"user_id": current_user_id, "item": item["id"]})
            results[item["id"]] = {"error": str(exc)}
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
                        raw, account["type"], account["charge_sign"] or 1,
                        include_pending=with_pending or account["type"] == "CREDIT",
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
    if brokerage and not open_finance_inbox.is_broker_transfer(tx):
        return "covered"
    if account["type"] == "BANK" and open_finance_inbox.is_auto_invest_row(tx):
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
    return {"days": days, "from": history_from, **pull_history(current_user_id, history_from, today)}


def pull_history(current_user_id, history_from, today, adopt_orphans=False, before_record=None, after_record=None,
                 abort_on_failure=False):
    """Puxa de `history_from` todas as conexoes e so depois grava: um Pix antigo
    gravado no fim da primeira conexao viraria despesa antes de a outra ponta,
    em outra conexao, chegar. `adopt_orphans`: as parcelas sem a parcela 1 viram a
    compra (open_finance_inbox.adopt_orphan_installments). `before_record(conn)` e
    `after_record(conn)` rodam na mesma transacao da gravacao (a reconstrucao).
    `abort_on_failure`: uma conexao que falhou (ou sem os investimentos) nao grava
    nada, de nenhuma: gravar sem a outra ponta faria despesa do que e transferencia."""
    results = {}
    with get_db() as conn:
        ids = [row["id"] for row in active_items(conn, current_user_id)]
    for of_item_id in ids:
        try:
            results[of_item_id] = sync_item(
                current_user_id, of_item_id, today=today, history_from=history_from, record=False,
            )
        except (PluggyError, ValidationError, LookupError) as exc:
            results[of_item_id] = {"error": str(exc)}
    if abort_on_failure and any(body.get("error") or body.get("investments") is None for body in results.values()):
        return {"items": results, "auto_recorded": None, "adopted_installments": 0, "invoice_payments": None,
                "aborted": True}
    adopted = 0
    with get_db() as conn:
        if adopt_orphans:
            rules = import_rules_for_matching(conn, current_user_id)
            for of_item_id in ids:
                for account in item_accounts(conn, current_user_id, of_item_id):
                    if account["card_id"] and not account["ignored_at"]:
                        adopted += open_finance_inbox.adopt_orphan_installments(conn, current_user_id, account, rules)
        if before_record:
            before_record(conn)
        auto = open_finance_auto.record_pending(conn, current_user_id, today)
        if after_record:
            after_record(conn)
        payments = open_finance_invoices.record_bank_payments(conn, current_user_id)
        open_finance_inbox.mark_bank_investments(conn, current_user_id)
    return {"items": results, "auto_recorded": auto, "adopted_installments": adopted, "invoice_payments": payments}


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
                proven = {}
                if account["account_id"] and account["account_id"] in balances:
                    mine = balances[account["account_id"]]
                    entry["target_name"] = mine["name"]
                    # Conferir, nunca ajustar: o saldo da conta e o do app
                    # (inicial + lancamentos), o mesmo do consolidado.
                    # O banco nao tem o que ainda vai acontecer: so o que o app tem ate hoje
                    # (na Corretora, o que ja liquidou; num banco, sem o lancamento futuro).
                    if entry["brokerage"]:
                        settled = settled_balance(conn, current_user_id, account["account_id"], _day_text(_today()))
                    else:
                        settled = account_balance_until(conn, current_user_id, account["account_id"], _day_text(_today()))
                    entry["app_balance"], difference_cents = open_finance_check.balance_difference(account, mine, settled)
                    if difference_cents is not None:
                        entry["difference"] = rounded_money(difference_cents / 100)
                    proven = open_finance_orphans.balance_confirmed(conn, current_user_id, account, difference_cents)
                elif account["card_id"]:
                    entry["target_name"] = names.get(account["card_id"])
                entry["check"] = open_finance_check.account_check(
                    conn, current_user_id, account, difference_cents, balance_confirmed=proven,
                )
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
