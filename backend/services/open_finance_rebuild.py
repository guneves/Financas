"""Refazer os lancamentos do dono a partir da Pluggy (dono, 2026-10-30).

Roda pela linha de comando (scripts/rebuild_from_pluggy.py), nunca por uma rota.
Sem `--apply` e um ensaio: nada grava, e as operacoes de investimento sao
simuladas numa copia em memoria do banco.

Com `--apply`, nesta ordem (cada passo pode ser refeito: `--from-step`):

0. **Backup** verificado (`integrity_check`), com nome proprio que a retencao nao
   apaga. Falhou, nada anda. Depois a **trava da carteira** (`investment_gate()`).
1. `register`: a conexao que faltava (a Wise), mapeada e com o resto "nao usar".
2. `wipe`, numa transacao, sempre por `user_id`: apaga TODO lancamento e compra,
   pagamentos de fatura, itens e linhas da Pluggy, comprovantes (os arquivos
   depois do commit). Ficam: a(s) conta(s) de `keep_accounts` (a Flash, que o dono
   mantem a mao), e o caixa de operacoes e proventos que continuam (metadata
   .cash_account_id e exatamente um lancamento). Os investimentos perdem so as
   operacoes do mes `month`, menos as de bitcoin; as operacoes da Pluggy desse mes
   voltam a ser avaliadas, as DISMISSED e HELD tambem. O saldo das contas sem
   Pluggy e guardado antes, com as transferencias apagadas (`STATE_SETTING`).
3. `pull`: todas as conexoes desde HISTORY_START, so GET, e so entao a gravacao
   (o motor do historico). As transferencias apagadas devolvem a outra conta ao
   lado que sobrou; as parcelas sem a parcela 1 viram a compra; os pagamentos de
   fatura baixam as faturas (services/open_finance_invoices.py).
4. `settle`: fatura vencida sem pagamento vira historia; transferencia de uma
   ponta so vira despesa/receita.
5. `review`: so o que precisa de olhos fica a revisar.
6. `balances`: `initial_balance` de cada conta mapeada para o saldo do app ser o
   da Pluggy, e das outras para ficarem como estavam; depois a conferencia final.
"""

import json
import os
import shutil
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import db as database
from applog import get_logger
from asset_classes import QUOTED_ASSET_CLASSES, is_crypto_asset
from dates import parse_iso_datetime
from db import create_database_backup, get_db, parse_metadata_value, row_to_dict
from money import rounded_money
from services import (
    inbox,
    invoices,
    open_finance,
    open_finance_auto,
    open_finance_inbox,
    open_finance_investments,
    open_finance_invoices,
    proceeds_cash,
    proceeds_sync,
    realized_results,
)
from services.accounts import account_balance_rows
from services.attachments import attachment_path, remove_attachment_files
from services.broker_cash import settled_balance
from services.corporate_actions import is_bonus_movement, latest_action
from services.import_rules import import_rules_for_matching
from services.investments import resync_investment_cash_dates, validate_asset_transaction_backing
from source_types import INVESTMENT_CASH_SOURCE_TYPE, INVESTMENT_PROCEED_SOURCE_TYPE
from validators import ValidationError, safe_float

logger = get_logger(__name__)

# A Pluggy serve o que tem; pedir de longe nao custa nada e nao ha limite de dias.
HISTORY_START = "2015-01-01"
DEFAULT_RESET_MONTH = "2026-10"
DEFAULT_KEEP_ACCOUNTS = ("Flash",)
DEFAULT_REVIEW_DAYS = 30
STATE_SETTING = "open_finance_rebuild_state"
STEPS = ("register", "wipe", "pull", "settle", "review", "balances")
RESTORE_TRANSFER_DAYS = 3
# Um saldo inicial que mudou mais que isto diz que pode faltar lancamento.
BALANCE_SHIFT_ALERT = 1000.0
CARD_TOLERANCE = 0.05
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REFUSED = 2


class RebuildRefused(Exception):
    """Parou antes de gravar qualquer coisa."""


class RebuildFailed(Exception):
    """Um passo nao terminou: rode de novo com `--from-step`."""


@dataclass
class Options:
    month: str = DEFAULT_RESET_MONTH
    keep_accounts: tuple = DEFAULT_KEEP_ACCOUNTS
    register_item: str = None
    maps: dict = field(default_factory=dict)
    ignores: tuple = ()
    accept_investment_gaps: bool = False
    allow_pending: bool = False
    accept_balance_shift: bool = False
    reviewed_before: str = None
    from_step: str = STEPS[0]
    today: object = None


def _today(options):
    return options.today or invoices.local_today()


def find_user(email):
    """O id do usuario com este e-mail exato, ou RebuildRefused."""
    with get_db() as conn:
        row = conn.execute("SELECT id FROM users WHERE email = ?", (str(email or "").strip(),)).fetchone()
    if not row:
        raise RebuildRefused(f"Nenhum usuario com o e-mail exato {email}.")
    return row["id"]


def _chunks(values, size=400):
    values = list(values)
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _marks(values):
    return ", ".join("?" for _ in values)


def _select_ids(conn, sql, user_id, ids):
    """Linhas de `sql` (com um {ids}) para uma lista grande de ids."""
    found = []
    for chunk in _chunks(ids):
        found.extend(conn.execute(sql.format(ids=_marks(chunk)), (user_id, *chunk)).fetchall())
    return found


def _execute_ids(conn, sql, user_id, ids):
    total = 0
    for chunk in _chunks(ids):
        total += conn.execute(sql.format(ids=_marks(chunk)), (user_id, *chunk)).rowcount
    return total


# ---------------------------------------------------------------------------
# O que entra e o que fica
# ---------------------------------------------------------------------------

def mapped_targets(conn, user_id, extra_accounts=()):
    accounts, cards = set(extra_accounts), set()
    for row in conn.execute(
        """
        SELECT a.account_id, a.card_id FROM open_finance_accounts a
        JOIN open_finance_items i ON i.id = a.of_item_id AND i.user_id = a.user_id
        WHERE a.user_id = ? AND i.archived_at IS NULL AND a.ignored_at IS NULL
        """,
        (user_id,),
    ).fetchall():
        if row["account_id"]:
            accounts.add(row["account_id"])
        if row["card_id"]:
            cards.add(row["card_id"])
    return accounts, cards


def _folded_names(names):
    return {str(name).strip().casefold() for name in names if str(name or "").strip()}


def kept_account_ids(conn, user_id, names):
    """Pelo nome ou pelo banco da conta, sem diferenca de maiusculas."""
    wanted = _folded_names(names)
    return {
        row["id"] for row in conn.execute(
            "SELECT id, name, institution FROM accounts WHERE user_id = ?", (user_id,),
        ).fetchall()
        if str(row["name"] or "").strip().casefold() in wanted
        or str(row["institution"] or "").strip().casefold() in wanted
    }


def kept_card_ids(conn, user_id, names):
    """O cartao que debita numa conta mantida, ou com o nome dela no nome."""
    wanted = _folded_names(names)
    accounts = kept_account_ids(conn, user_id, names)
    return {
        row["id"] for row in conn.execute(
            "SELECT id, name, debit_account_id FROM credit_cards WHERE user_id = ?", (user_id,),
        ).fetchall()
        if row["debit_account_id"] in accounts or any(name in str(row["name"] or "").casefold() for name in wanted)
    }


def preflight(conn, user_id, options):
    """O que impede o --apply antes de qualquer escrita (o ensaio tambem diz)."""
    problems = []
    if not open_finance_auto.enabled(conn, user_id):
        problems.append("Gravar sozinho esta desligado: nada voltaria da Pluggy. Ligue antes.")
    label = ", ".join(options.keep_accounts)
    if not kept_account_ids(conn, user_id, options.keep_accounts):
        problems.append(f"Conta mantida nao encontrada ({label}): tudo seria apagado.")
    if not kept_card_ids(conn, user_id, options.keep_accounts):
        problems.append(f"Cartao mantido nao encontrado ({label}).")
    if options.from_step == "pull":
        saved = inbox.setting_value(conn, user_id, STATE_SETTING)
        if not saved:
            problems.append("--from-step pull sem o estado do wipe: rode desde o wipe.")
        elif json.loads(saved).get("recorded"):
            problems.append("A gravacao ja rodou: repetir o pull duplicaria lancamentos. Rode --from-step wipe.")
    return problems


def is_bitcoin(row):
    """Pelo ticker exato (ABTC11 e um ETF, BTCI11 um FII: nada de "contem BTC")."""
    return is_crypto_asset(row["asset_class"], row["ticker"])


def classify_movements(conn, user_id, month):
    """[{id, date, ticker, type, quantity, action, reason}] das operacoes do mes."""
    rows = conn.execute(
        """
        SELECT it.id, it.asset_id, it.transaction_date, it.movement_type, it.quantity, it.metadata,
               a.ticker, a.asset_class
        FROM investment_transactions it
        JOIN assets a ON a.id = it.asset_id AND a.user_id = it.user_id
        WHERE it.user_id = ? AND substr(it.transaction_date, 1, 7) = ?
        ORDER BY it.transaction_date, a.ticker, it.id
        """,
        (user_id, month),
    ).fetchall()
    listed = []
    for row in rows:
        reason = None
        action = latest_action(conn, user_id, row["asset_id"])
        if is_bitcoin(row):
            reason = "bitcoin" if row["movement_type"] == "BUY" else "bitcoin (nao e compra: confira)"
        elif is_bonus_movement(parse_metadata_value(row["metadata"])):
            reason = "bonificacao de um evento corporativo"
        elif action and str(row["transaction_date"])[:10] < action["ex_date"]:
            reason = f"antes do evento corporativo de {action['ex_date']}: nao poderia voltar"
        listed.append({
            "id": row["id"], "asset_id": row["asset_id"], "date": str(row["transaction_date"])[:10],
            "ticker": row["ticker"], "asset_class": row["asset_class"], "type": row["movement_type"],
            "quantity": safe_float(row["quantity"]), "action": "keep" if reason else "delete", "reason": reason,
        })
    for asset_id in {entry["asset_id"] for entry in listed}:
        mine = [entry for entry in listed if entry["asset_id"] == asset_id]
        going = {entry["id"] for entry in mine if entry["action"] == "delete"}
        if not going:
            continue
        try:
            validate_asset_transaction_backing(conn, user_id, asset_id, exclude_ids=going)
        except ValidationError as exc:
            for entry in mine:
                if entry["action"] == "delete":
                    entry.update(action="keep", reason=f"apagar deixaria uma venda sem lastro: {exc}", unbacked=True)
    return listed


def build_plan(conn, user_id, options, extra_accounts=()):
    """Tudo o que o wipe faria, sem gravar nada."""
    keep_ids = kept_account_ids(conn, user_id, options.keep_accounts)
    mapped_accounts, mapped_cards = mapped_targets(conn, user_id, extra_accounts)
    movements = classify_movements(conn, user_id, options.month)
    going_movements = {entry["id"] for entry in movements if entry["action"] == "delete"}
    live_movements = {
        row["id"] for row in conn.execute("SELECT id FROM investment_transactions WHERE user_id = ?", (user_id,)).fetchall()
    } - going_movements
    live_proceeds = {
        row["id"] for row in conn.execute("SELECT id FROM investment_proceeds WHERE user_id = ?", (user_id,)).fetchall()
    }

    doomed, kept_flash, kept_investment = [], [], []
    for row in conn.execute(
        """
        SELECT id, account_id, transfer_account_id, amount, transfer_amount, date, description, type, source_type,
               source_id
        FROM transactions WHERE user_id = ?
        """,
        (user_id,),
    ).fetchall():
        row = row_to_dict(row)
        investment = (
            (row["source_type"] == INVESTMENT_CASH_SOURCE_TYPE and row["source_id"] in live_movements)
            or (row["source_type"] == INVESTMENT_PROCEED_SOURCE_TYPE and row["source_id"] in live_proceeds)
        )
        if investment:
            kept_investment.append(row)
        elif row["source_type"] == INVESTMENT_CASH_SOURCE_TYPE:
            doomed.append(row)
        elif row["account_id"] in keep_ids or row["transfer_account_id"] in keep_ids:
            kept_flash.append(row)
        else:
            doomed.append(row)

    kept_cards = kept_card_ids(conn, user_id, options.keep_accounts)
    doomed_cards = [row_to_dict(row) for row in conn.execute(
        "SELECT id, card_id, purchase_date AS date FROM cc_expenses WHERE user_id = ?", (user_id,),
    ).fetchall() if row["card_id"] not in kept_cards]
    doomed_ids = {row["id"] for row in doomed}
    doomed_card_ids = {row["id"] for row in doomed_cards}

    of_items = {row["item_id"] for row in conn.execute(
        "SELECT DISTINCT item_id FROM open_finance_transactions WHERE user_id = ? AND item_id IS NOT NULL", (user_id,),
    ).fetchall()}
    doomed_items = []
    for row in conn.execute(
        "SELECT id, state, account_id, transfer_account_id, card_id, target_table, target_id FROM inbox_items WHERE user_id = ?",
        (user_id,),
    ).fetchall():
        target_gone = row["target_id"] in doomed_ids or row["target_id"] in doomed_card_ids
        waiting_on_bank = row["state"] == inbox.PENDING and (
            row["account_id"] in mapped_accounts or row["transfer_account_id"] in mapped_accounts
            or row["card_id"] in mapped_cards
        )
        if row["id"] in of_items or target_gone or waiting_on_bank:
            doomed_items.append(row["id"])

    tx_attachments = [row["stored_name"] for row in _select_ids(
        conn, "SELECT stored_name FROM transaction_attachments WHERE user_id = ? AND transaction_id IN ({ids})",
        user_id, doomed_ids,
    )]
    cc_attachments = [row["stored_name"] for row in _select_ids(
        conn, "SELECT stored_name FROM cc_expense_attachments WHERE user_id = ? AND cc_expense_id IN ({ids})",
        user_id, doomed_card_ids,
    )]
    operations = _operations_to_reset(conn, user_id, options.month, going_movements, movements)
    count = lambda table: conn.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", (user_id,)).fetchone()[0]
    return {
        "keep_ids": keep_ids, "kept_cards": kept_cards, "mapped_accounts": mapped_accounts,
        "mapped_cards": mapped_cards, "movements": movements, "going_movements": going_movements,
        "doomed": doomed, "doomed_ids": doomed_ids, "doomed_cards": doomed_cards,
        "doomed_card_ids": doomed_card_ids, "kept_flash": kept_flash, "kept_investment": kept_investment,
        "doomed_items": doomed_items, "attachments": tx_attachments + cc_attachments, "operations": operations,
        "counts": {
            "transactions": len(doomed_ids),
            "cc_expenses": len(doomed_card_ids),
            "inbox_items": len(doomed_items),
            "open_finance_transactions": count("open_finance_transactions"),
            "recurring_settlements": count("recurring_settlements"),
            "cc_invoice_manual": count("cc_invoice_manual"),
            "comprovantes": len(tx_attachments) + len(cc_attachments),
            "investment_transactions": len(going_movements),
            "open_finance_investment_operations": len(operations),
        },
    }


def _operations_to_reset(conn, user_id, month, going_movements, movements):
    """As operacoes da Pluggy do mes, em qualquer estado, e as ligadas a uma
    movimentacao que sai; menos as ligadas a uma que fica."""
    staying = {entry["id"] for entry in movements if entry["action"] == "keep"}
    found = []
    for row in conn.execute(
        "SELECT id, code, trade_date, investment_id FROM open_finance_investment_operations WHERE user_id = ?",
        (user_id,),
    ).fetchall():
        if row["investment_id"] in staying:
            continue
        if str(row["trade_date"])[:7] == month or row["investment_id"] in going_movements:
            found.append(row["id"])
    return found


def capture_state(conn, user_id, plan):
    """O saldo de hoje das contas que nao tem Pluggy e as transferencias que vao
    sair. Numa segunda rodada vale a primeira: este banco ja esta sem elas."""
    saved = inbox.setting_value(conn, user_id, STATE_SETTING)
    if saved:
        state = json.loads(saved)
        state["recorded"] = False
        inbox.save_setting(conn, user_id, STATE_SETTING, json.dumps(state))
        return state
    rows = account_balance_rows(conn, user_id)
    balances = {
        row["id"]: rounded_money(row["balance"]) for row in rows
        if row["id"] not in plan["mapped_accounts"] and row["id"] not in plan["keep_ids"]
    }
    kept = {row["id"]: rounded_money(row["balance"]) for row in rows if row["id"] in plan["keep_ids"]}
    transfers = [
        {key: row[key] for key in ("id", "account_id", "transfer_account_id", "amount", "transfer_amount", "date",
                                   "description")}
        for row in plan["doomed"] if row["type"] == "TRANSFER" and row["account_id"] and row["transfer_account_id"]
    ]
    earliest = {}
    for row in conn.execute(
        """
        SELECT a.id, MIN(t.date) AS first FROM accounts a
        JOIN transactions t ON t.user_id = a.user_id AND (t.account_id = a.id OR t.transfer_account_id = a.id)
        WHERE a.user_id = ? GROUP BY a.id
        """,
        (user_id,),
    ).fetchall():
        earliest[row["id"]] = str(row["first"])[:10]
    state = {
        "balances": balances, "kept": kept, "transfers": transfers, "recorded": False, "earliest": earliest,
        "initial": {row["id"]: rounded_money(row["initial_balance"]) for row in rows},
    }
    inbox.save_setting(conn, user_id, STATE_SETTING, json.dumps(state))
    return state


def wipe(conn, user_id, plan):
    """Executa o plano na transacao de `conn`. Devolve os arquivos a apagar."""
    conn.execute("DELETE FROM recurring_settlements WHERE user_id = ?", (user_id,))
    _execute_ids(
        conn, "UPDATE notify_detections SET target_table = NULL, target_id = NULL WHERE user_id = ? AND target_id IN ({ids})",
        user_id, plan["doomed_ids"] | plan["doomed_card_ids"],
    )
    conn.execute("DELETE FROM open_finance_transactions WHERE user_id = ?", (user_id,))
    _execute_ids(conn, "DELETE FROM inbox_items WHERE user_id = ? AND id IN ({ids})", user_id, plan["doomed_items"])
    _execute_ids(conn, "DELETE FROM transactions WHERE user_id = ? AND id IN ({ids})", user_id, plan["doomed_ids"])
    _execute_ids(conn, "DELETE FROM cc_expenses WHERE user_id = ? AND id IN ({ids})", user_id, plan["doomed_card_ids"])
    conn.execute("DELETE FROM cc_invoice_manual WHERE user_id = ?", (user_id,))
    _execute_ids(
        conn, "DELETE FROM open_finance_investment_operations WHERE user_id = ? AND id IN ({ids})",
        user_id, plan["operations"],
    )
    _execute_ids(
        conn, "DELETE FROM investment_transactions WHERE user_id = ? AND id IN ({ids})", user_id, plan["going_movements"],
    )
    conn.execute("UPDATE open_finance_accounts SET synced_until = NULL WHERE user_id = ?", (user_id,))
    return plan["attachments"]


# ---------------------------------------------------------------------------
# Ensaio: a Pluggy (so GET) e a trava da carteira
# ---------------------------------------------------------------------------

def _stored_items(conn, user_id):
    return [row_to_dict(row) for row in conn.execute(
        "SELECT * FROM open_finance_items WHERE user_id = ? AND archived_at IS NULL ORDER BY created_at, id", (user_id,),
    ).fetchall()]


def probe_pluggy(user_id, options):
    """Por conta de cada conexao (a registrar tambem): o que a Pluggy tem desde
    HISTORY_START. So GET; nada grava."""
    api = open_finance.client()
    with get_db() as conn:
        items = _stored_items(conn, user_id)
        stored = {row["pluggy_account_id"]: row_to_dict(row) for row in conn.execute(
            "SELECT * FROM open_finance_accounts WHERE user_id = ?", (user_id,),
        ).fetchall()}
    pluggy_ids = [item["pluggy_item_id"] for item in items]
    if options.register_item and options.register_item not in pluggy_ids:
        pluggy_ids.append(options.register_item)
    listed = []
    for pluggy_item_id in pluggy_ids:
        for raw in api.list_accounts(pluggy_item_id):
            if str(raw.get("type") or "").upper() not in ("BANK", "CREDIT"):
                continue
            rows = api.list_transactions(raw["id"], HISTORY_START)
            dates = sorted(str(tx.get("date") or "")[:10] for tx in rows if tx.get("date"))
            mine = stored.get(raw["id"]) or {}
            listed.append({
                "item": pluggy_item_id, "id": raw["id"], "type": raw.get("type"),
                "name": raw.get("marketingName") or raw.get("name"), "currency": raw.get("currencyCode") or "BRL",
                "balance": raw.get("balance"), "rows": len(rows), "earliest": dates[0] if dates else None,
                "latest": dates[-1] if dates else None, "stored": raw["id"] in stored,
                "account_id": mine.get("account_id"), "card_id": mine.get("card_id"),
                "ignored": bool(mine.get("ignored_at")),
            })
    return listed


def _extra_mapped(options):
    return {target for target in options.maps.values()}


def _memory_copy():
    copy = sqlite3.connect(":memory:")
    source = sqlite3.connect(database.DATABASE_PATH)
    try:
        source.backup(copy)
    finally:
        source.close()
    copy.row_factory = sqlite3.Row
    copy.execute("PRAGMA foreign_keys = ON")
    return copy


def investment_gate(user_id, options):
    """Simula numa copia em memoria: apaga as operacoes do mes e reavalia as da
    Pluggy. Devolve {tickers, held_reasons, other_held, gaps, ...}; `gaps` nao
    vazio trava o `--apply` sem `--accept-investment-gaps`."""
    today = _today(options)
    api = open_finance.client()
    with get_db() as conn:
        items = _stored_items(conn, user_id)
    pulled = {item["id"]: open_finance_investments.fetch(api, item["pluggy_item_id"], logger) for item in items}
    gaps = []
    memory = _memory_copy()
    try:
        plan = build_plan(memory, user_id, options, _extra_mapped(options))
        for entry in plan["movements"]:
            if entry.get("unbacked"):
                gaps.append(f"{entry['ticker']} {entry['date']}: {entry['reason']}")
        reasons_before = Counter(
            f"{row['pluggy_type']} | {str(row['held_reason'] or '').split(':')[0]}" for row in memory.execute(
                "SELECT pluggy_type, held_reason FROM open_finance_investment_operations WHERE user_id = ? AND state = 'HELD'",
                (user_id,),
            ).fetchall()
        )
        deleted = Counter()
        for entry in plan["movements"]:
            if entry["action"] == "delete":
                deleted[entry["ticker"]] += entry["quantity"]
        wipe(memory, user_id, plan)
        for of_item_id, data in pulled.items():
            if data is None:
                gaps.append("A Pluggy recusou os investimentos de uma conexao: a carteira nao foi conferida.")
                continue
            open_finance_investments.apply(memory, user_id, of_item_id, data, today)
        stayed = {entry["id"] for entry in plan["movements"] if entry["action"] == "keep"}
        result = _gate_result(memory, user_id, options, deleted, stayed, today, gaps)
        result["held_reasons_before"] = dict(reasons_before)
        result["movements"] = plan["movements"]
        return result
    finally:
        memory.close()


def _gate_result(memory, user_id, options, deleted, stayed, today, gaps):
    month_ops = memory.execute(
        "SELECT * FROM open_finance_investment_operations WHERE user_id = ? AND substr(trade_date, 1, 7) = ?",
        (user_id, options.month),
    ).fetchall()
    held, other_held = [], []
    for row in month_ops:
        if row["state"] != "HELD":
            continue
        line = f"{row['trade_date']} {row['code'] or row['name']} {row['op_type']} {row['quantity']} ({row['pluggy_type']}): {row['held_reason']}"
        counted = row["op_type"] in open_finance_investments.RECORDED_TYPES and (
            row["pluggy_type"] in open_finance_investments.EQUITY_TYPES
        )
        (held if counted else other_held).append(line)
    gaps.extend(f"Operacao do mes continuaria segurada: {line}" for line in held)

    check = open_finance_investments.portfolio_check(memory, user_id, today) or {"positions": []}
    tickers = []
    listed = set()
    for entry in check["positions"]:
        if "matches" not in entry:
            continue
        listed.add(entry["code"])
        tickers.append({
            "ticker": entry["code"], "pluggy": entry["pluggy_quantity"], "expected": entry["expected_quantity"],
            "app": entry["app_quantity"], "matches": entry["matches"],
        })
        if not entry["matches"]:
            gaps.append(f"{entry['code']}: app {entry['app_quantity']} x Pluggy {entry['expected_quantity']}")
    classes = sorted(QUOTED_ASSET_CLASSES)
    for row in memory.execute(
        f"""
        SELECT a.ticker, SUM(it.quantity) AS quantity FROM investment_transactions it
        JOIN assets a ON a.id = it.asset_id AND a.user_id = it.user_id
        WHERE it.user_id = ? AND a.asset_class IN ({_marks(classes)})
        GROUP BY a.ticker
        """,
        (user_id, *classes),
    ).fetchall():
        quantity = safe_float(row["quantity"])
        if row["ticker"] not in listed and abs(quantity) > open_finance_investments.QUANTITY_TOLERANCE:
            tickers.append({"ticker": row["ticker"], "pluggy": None, "expected": 0, "app": quantity, "matches": False})
            gaps.append(f"{row['ticker']}: app {quantity}, sem posicao na Pluggy")

    came_back = Counter()
    for row in memory.execute(
        """
        SELECT it.id, a.ticker, it.quantity FROM investment_transactions it
        JOIN assets a ON a.id = it.asset_id AND a.user_id = it.user_id
        WHERE it.user_id = ? AND substr(it.transaction_date, 1, 7) = ?
        """,
        (user_id, options.month),
    ).fetchall():
        if row["id"] not in stayed:
            came_back[row["ticker"]] += safe_float(row["quantity"])
    lost = []
    for ticker, quantity in deleted.items():
        if abs(quantity - came_back.get(ticker, 0)) > open_finance_investments.QUANTITY_TOLERANCE:
            lost.append(f"{ticker}: apagado {quantity}, a Pluggy traz {came_back.get(ticker, 0)}")
    gaps.extend(f"Operacao apagada sem reposicao: {line}" for line in lost)
    states = Counter(row["state"] for row in month_ops)
    reasons = Counter(
        f"{row['pluggy_type']} | {str(row['held_reason'] or '').split(':')[0]}" for row in memory.execute(
            "SELECT pluggy_type, held_reason FROM open_finance_investment_operations WHERE user_id = ? AND state = 'HELD'",
            (user_id,),
        ).fetchall()
    )
    return {"tickers": sorted(tickers, key=lambda entry: str(entry["ticker"])), "month_states": dict(states),
            "held_reasons": dict(reasons), "other_held": other_held, "gaps": gaps}


def print_gate(gate, out):
    out("")
    out(f"Operacoes da Pluggy do mes depois de reavaliar: {gate['month_states']}")
    out("Motivos de HELD antes:")
    for reason, total in sorted(gate["held_reasons_before"].items()):
        out(f"  {total:4d}  {reason}")
    out("Motivos de HELD depois:")
    for reason, total in sorted(gate["held_reasons"].items()):
        out(f"  {total:4d}  {reason}")
    if gate["other_held"]:
        out("Do mes, seguram sem travar (nao sao compra/venda de renda variavel):")
        for line in gate["other_held"]:
            out(f"  {line}")
    out("Quantidade por ativo (app depois do rebuild x Pluggy):")
    for entry in gate["tickers"]:
        mark = "ok " if entry["matches"] else "DIF"
        out(f"  {mark} {entry['ticker']}: app {entry['app']} x Pluggy {entry['expected']} (posicao {entry['pluggy']})")
    if gate["gaps"]:
        out(f"TRAVA DA CARTEIRA: {len(gate['gaps'])} problema(s); --apply recusa sem --accept-investment-gaps:")
        for line in gate["gaps"]:
            out(f"  {line}")
    else:
        out("Trava da carteira: nada a apontar.")


def dry_run(user_id, options, out=print):
    """So le. Devolve EXIT_OK; os problemas saem impressos."""
    today = _today(options)
    probe = []
    try:
        probe = probe_pluggy(user_id, options)
    except open_finance.PluggyError as exc:
        out(f"AVISO: a Pluggy recusou a leitura: {exc}")
    with get_db() as conn:
        plan = build_plan(conn, user_id, options, _extra_mapped(options))
        names = {row["id"]: row for row in account_balance_rows(conn, user_id)}
        card_names = {row["id"]: row["name"] for row in conn.execute(
            "SELECT id, name FROM credit_cards WHERE user_id = ?", (user_id,),
        ).fetchall()}
        recurrences = conn.execute(
            "SELECT description, account_id, active, next_run_date FROM recurring_transactions WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        pending = inbox_pending(conn, user_id)
    out(f"ENSAIO: nada foi gravado. Hoje {today}, historico desde {HISTORY_START}.")
    with get_db() as conn:
        for problem in preflight(conn, user_id, options):
            out(f"--apply RECUSARIA: {problem}")
    out("")
    out("Apagaria, por tabela:")
    for table, total in plan["counts"].items():
        out(f"  {total:6d}  {table}")
    out("")
    out("Contas da Pluggy (todas as conexoes):")
    for entry in probe:
        target = names[entry["account_id"]]["name"] if entry["account_id"] in names else (
            card_names.get(entry["card_id"]) or ("nao usar" if entry["ignored"] else "sem destino")
        )
        note = "" if entry["stored"] else " [ainda nao gravada no app]"
        out(f"  {entry['type']:6} {entry['name']} ({entry['currency']}) saldo {entry['balance']}: {entry['rows']} linhas, "
            f"{entry['earliest']} a {entry['latest']} -> {target}{note}")
    unreplaceable = _unreplaceable(plan, probe, options)
    out("")
    out("Linhas apagadas de antes do que a Pluggy guarda (nao voltam):")
    for label, total, earliest in unreplaceable:
        out(f"  {total:6d}  {names[label]['name'] if label in names else card_names.get(label, label)} (Pluggy desde {earliest})")
    out("")
    out(f"Ficam {len(plan['kept_flash'])} lancamentos de {', '.join(options.keep_accounts)}, intactos.")
    out(f"Ficam {len(plan['kept_investment'])} lancamentos de investimento (caixa de operacoes e proventos que continuam):")
    for label, total in Counter(
        names[row["account_id"]]["name"] if row["account_id"] in names else "sem conta"
        for row in plan["kept_investment"]
    ).items():
        out(f"  {total:6d}  {label}")
    out("")
    out("Saldos preservados no initial_balance (contas sem Pluggy):")
    for account_id, row in names.items():
        if account_id not in plan["mapped_accounts"]:
            action = "intacta" if account_id in plan["keep_ids"] else "os lancamentos saem, o saldo fica"
            out(f"  {row['name']}: {rounded_money(row['balance'])} ({action})")
    out("")
    out(f"Recorrencias ({len(recurrences)}): modelos ficam; em conta conectada o /run nao grava mais nada.")
    for row in recurrences:
        where = "conta conectada" if row["account_id"] in plan["mapped_accounts"] else "conta sem Pluggy"
        out(f"  {row['description']}: {where}, ativa {row['active']}, proxima {row['next_run_date']}")
    out(f"Itens pendentes hoje: {len(pending)}.")
    out("")
    out("Operacoes do mes:")
    for entry in plan["movements"]:
        action = "APAGA" if entry["action"] == "delete" else f"FICA ({entry['reason']})"
        out(f"  {entry['date']} {entry['ticker']} {entry['type']} {entry['quantity']}: {action}")
    print_gate(investment_gate(user_id, options), out)
    return EXIT_OK


def _unreplaceable(plan, probe, options):
    earliest = {}
    for entry in probe:
        target = entry["account_id"] or entry["card_id"]
        if target:
            earliest[target] = entry["earliest"]
    for key, target in options.maps.items():
        for entry in probe:
            if key.casefold() in (str(entry["name"]).casefold(), str(entry["currency"]).casefold(), entry["id"]):
                earliest[target] = entry["earliest"]
    totals = Counter()
    for row in plan["doomed"]:
        for side in (row["account_id"], row["transfer_account_id"]):
            first = earliest.get(side)
            if side and side in earliest and (first is None or str(row["date"]) < first):
                totals[side] += 1
    for row in plan["doomed_cards"]:
        first = earliest.get(row["card_id"])
        if row["card_id"] in earliest and (first is None or str(row["date"]) < first):
            totals[row["card_id"]] += 1
    return [(target, total, earliest[target]) for target, total in totals.items()]


# ---------------------------------------------------------------------------
# Passos do --apply
# ---------------------------------------------------------------------------

def verified_backup():
    """O backup de sempre, conferido, mais uma copia que a retencao nao apaga."""
    try:
        backup = create_database_backup()
        path = backup["database_path"]
        check = sqlite3.connect(path)
        try:
            verdict = check.execute("PRAGMA integrity_check").fetchone()[0]
            users = check.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        finally:
            check.close()
        if verdict != "ok" or not users:
            raise RebuildRefused(f"O backup {path} nao passou na conferencia: {verdict}.")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        milestone = os.path.join(os.path.dirname(path), f"finance-before-rebuild-{stamp}.db")
        shutil.copy2(path, milestone)
    except RebuildRefused:
        raise
    except Exception as exc:
        raise RebuildRefused(f"O backup falhou, nada foi feito: {exc}") from exc
    return milestone


def copy_receipts(user_id, names, out):
    """Os comprovantes que vao sair, numa pasta so deste rebuild, fora da rotacao
    dos backups. Um que nao copia para tudo: o espelho do backup so avisa no log."""
    if not names:
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = os.path.join(database.DATABASE_BACKUP_DIR, f"receipts-before-rebuild-{stamp}", user_id)
    try:
        os.makedirs(folder, exist_ok=True)
        for name in names:
            source = attachment_path(user_id, name)
            target = os.path.join(folder, os.path.basename(source))
            shutil.copy2(source, target)
            if os.path.getsize(target) != os.path.getsize(source):
                raise OSError(f"copia incompleta de {name}")
    except OSError as exc:
        raise RebuildRefused(f"Comprovante sem copia, nada foi apagado: {exc}") from exc
    out(f"Comprovantes copiados: {len(names)} em {folder}")
    return folder


def register_and_map(user_id, options, out):
    """A conexao nova e o destino de cada conta dela. Refazer nao muda nada."""
    if not options.register_item:
        return
    of_item_id = open_finance.register_item(user_id, options.register_item, first_pull=False)

    def find(accounts, key):
        wanted = str(key).casefold()
        for account in accounts:
            if wanted in (str(account["name"]).casefold(), str(account["currency"]).casefold(),
                          account["pluggy_account_id"]):
                return account
        raise RebuildFailed(f"A conexao nao tem a conta {key}.")

    with get_db() as conn:
        accounts = [row_to_dict(row) for row in open_finance.item_accounts(conn, user_id, of_item_id)]
    for key, target in options.maps.items():
        account = find(accounts, key)
        if account["account_id"] == target or account["card_id"] == target:
            continue
        field_name = "card_id" if account["type"] == "CREDIT" else "account_id"
        open_finance.map_account(user_id, account["id"], {field_name: target})
        out(f"Mapeada {account['name']} -> {target}")
    for key in options.ignores:
        account = find(accounts, key)
        if not account["ignored_at"]:
            open_finance.map_account(user_id, account["id"], {"ignore": True})
            out(f"Nao usar: {account['name']}")


def step_wipe(user_id, options, out):
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        plan = build_plan(conn, user_id, options)
        copy_receipts(user_id, plan["attachments"], out)
        capture_state(conn, user_id, plan)
        names = wipe(conn, user_id, plan)
    remove_attachment_files(user_id, names)
    realized_results.refresh_realized_results(user_id)
    out(f"Apagado: {plan['counts']}")


def load_state(conn, user_id):
    saved = inbox.setting_value(conn, user_id, STATE_SETTING)
    return json.loads(saved) if saved else {"balances": {}, "kept": {}, "transfers": []}


def _source_side(conn, user_id, item):
    sources = inbox.open_finance_sources(conn, user_id, item["id"], roles=(inbox.SOURCE,))
    if len(sources) != 1:
        return None, None
    source = row_to_dict(sources[0]) if not isinstance(sources[0], dict) else sources[0]
    account = open_finance_inbox.fetch_account(conn, user_id, source["of_account_id"])
    if not account or account["type"] != "BANK" or not account["account_id"]:
        return None, None
    return source, account


def _pending_open_finance(conn, user_id):
    return conn.execute(
        """
        SELECT DISTINCT i.* FROM inbox_items i
        JOIN open_finance_transactions o ON o.item_id = i.id AND o.user_id = i.user_id
        WHERE i.user_id = ? AND i.state = 'PENDING' AND o.role = 'SOURCE'
        ORDER BY i.occurred_at, i.id
        """,
        (user_id,),
    ).fetchall()


def restore_known_transfers(conn, user_id, state):
    """O lado que a Pluggy trouxe de uma transferencia que o app tinha: a outra
    ponta nao vem (conta sem Pluggy, ou de antes do que ela guarda), entao a
    transferencia volta inteira, com a outra conta e o valor no destino que
    estavam na linha apagada. Devolve {restored, unarchived: {id: archived_at}}:
    a conta arquivada e ativada so durante a gravacao (restore_archived())."""
    free = list(state.get("transfers") or [])
    restored = 0
    unarchived = {}
    for row in _pending_open_finance(conn, user_id):
        item = inbox.item_dict(row)
        if item["entry_type"] == "TRANSFER" and item.get("account_id") and item.get("transfer_account_id"):
            continue
        source, account = _source_side(conn, user_id, item)
        if not source:
            continue
        best = None
        for transfer in free:
            side = transfer["account_id"] if source["direction"] == "OUT" else transfer["transfer_account_id"]
            value = transfer["amount"] if source["direction"] == "OUT" else (
                transfer["transfer_amount"] if transfer["transfer_amount"] is not None else transfer["amount"]
            )
            gap = abs(open_finance_invoices._ordinal(transfer["date"]) - open_finance_invoices._ordinal(source["date"]))
            if side != account["account_id"] or open_finance_invoices._cents(value) != source["amount_cents"]:
                continue
            if gap <= RESTORE_TRANSFER_DAYS and (best is None or gap < best[0]):
                best = (gap, transfer)
        if not best:
            continue
        transfer = best[1]
        free.remove(transfer)
        origin = conn.execute(
            "SELECT currency FROM accounts WHERE id = ? AND user_id = ?", (transfer["account_id"], user_id),
        ).fetchone()
        for account_id in (transfer["account_id"], transfer["transfer_account_id"]):
            archived = conn.execute(
                "SELECT archived_at FROM accounts WHERE id = ? AND user_id = ?", (account_id, user_id),
            ).fetchone()
            if archived and archived["archived_at"]:
                unarchived[account_id] = archived["archived_at"]
                conn.execute("UPDATE accounts SET archived_at = NULL WHERE id = ? AND user_id = ?", (account_id, user_id))
        currency = (origin["currency"] if origin else None) or "BRL"
        changes = {
            "entry_type": "TRANSFER", "direction": "OUT", "account_id": transfer["account_id"],
            "transfer_account_id": transfer["transfer_account_id"], "amount": rounded_money(transfer["amount"]),
            "transfer_amount": transfer["transfer_amount"], "currency": currency, "category": inbox.TRANSFER_CATEGORY,
            "category_id": None, "reason": "own_transfer", "guessed": [],
            "description": transfer["description"] or item["description"],
            "edited": ["amount"] if currency != "BRL" else [],
        }
        changes["needs"] = inbox.recompute_needs({**item, **changes})
        inbox.save_item(conn, user_id, item, changes)
        restored += 1
    return {"restored": restored, "unarchived": unarchived}


def restore_archived(conn, user_id, unarchived):
    for account_id, archived_at in unarchived.items():
        conn.execute("UPDATE accounts SET archived_at = ? WHERE id = ? AND user_id = ?", (archived_at, account_id, user_id))


def step_pull(user_id, options, out):
    today = _today(options)
    with get_db() as conn:
        if not open_finance_auto.enabled(conn, user_id):
            raise RebuildFailed("Gravar sozinho esta desligado: ligue antes de refazer.")
        state = load_state(conn, user_id)
    restored = {}

    def before_record(conn):
        restored.update(restore_known_transfers(conn, user_id, state))

    def after_record(conn):
        restore_archived(conn, user_id, restored.get("unarchived") or {})
        inbox.save_setting(conn, user_id, STATE_SETTING, json.dumps({**state, "recorded": True}))

    result = open_finance.pull_history(
        user_id, HISTORY_START, today, adopt_orphans=True, before_record=before_record, after_record=after_record,
        abort_on_failure=True,
    )
    if result.get("aborted"):
        problems = []
        for of_item_id, body in result["items"].items():
            if body.get("error"):
                problems.append(f"{of_item_id}: {body['error']}")
            elif body.get("investments") is None:
                problems.append(f"{of_item_id}: a Pluggy nao devolveu os investimentos")
        raise RebuildFailed("O pull nao terminou, nada foi gravado: " + "; ".join(problems))
    out(f"Puxado desde {HISTORY_START}: gravados {result['auto_recorded']}, "
        f"compras de antes do historico {result['adopted_installments']}, "
        f"transferencias devolvidas {restored.get('restored', 0)}, pagamentos de fatura {result['invoice_payments']}.")


def resolve_one_sided(conn, user_id, today):
    """Transferencia de uma ponta so que nada completou: despesa/receita da conta
    da Pluggy, a revisar. So o que esta dentro de TRANSFER_HOLD_DAYS segue
    esperando (a outra ponta ainda pode vir)."""
    resolved = 0
    for row in _pending_open_finance(conn, user_id):
        item = inbox.item_dict(row)
        source, account = _source_side(conn, user_id, item)
        if not source or item["entry_type"] != "TRANSFER":
            continue
        if open_finance_auto._days_since(source["date"], today) < open_finance_auto.TRANSFER_HOLD_DAYS:
            continue
        entry_type = "EXPENSE" if source["direction"] == "OUT" else "INCOME"
        name, category_id = open_finance_inbox.category_for_row(
            conn, user_id, source, entry_type, item["amount"], account["account_id"],
        )
        changes = {
            "entry_type": entry_type, "direction": source["direction"], "account_id": account["account_id"],
            "transfer_account_id": None, "transfer_amount": None, "category": name, "category_id": category_id,
            "reason": "external_transfer", "guessed": [],
            "amount": inbox._reais(source["amount_cents"]),
            "description": open_finance_inbox.display_name(
                source["description"], source.get("merchant_name"), source.get("counterparty"), "TRANSFER",
                source["direction"],
            ),
        }
        changes["needs"] = inbox.recompute_needs({**item, **changes})
        inbox.save_item(conn, user_id, item, changes)
        fresh = inbox.fetch_item(conn, user_id, item["id"])
        if open_finance_auto.record_item(conn, user_id, fresh, today) != "held":
            resolved += 1
    return resolved


def step_settle(user_id, options, out):
    today = _today(options)
    with get_db() as conn:
        resolved = resolve_one_sided(conn, user_id, today)
        closed = open_finance_invoices.close_past_invoices(conn, user_id, today)
    out(f"Transferencias de uma ponta so viradas despesa/receita: {resolved}.")
    out(f"Faturas vencidas sem pagamento na Pluggy, baixadas sem dinheiro: {len(closed)}.")
    for entry in closed:
        out(f"  {entry['card']} {entry['invoice']} (venceu {entry['due']}): {entry['amount']:.2f}")


def _clear_review(conn, user_id, table, target_id):
    if table == "transactions":
        conn.execute("UPDATE transactions SET needs_review = 0 WHERE id = ? AND user_id = ?", (target_id, user_id))
    else:
        conn.execute(
            """
            UPDATE cc_expenses SET needs_review = 0
            WHERE user_id = ? AND client_id = (SELECT client_id FROM cc_expenses WHERE id = ? AND user_id = ?)
            """,
            (user_id, target_id, user_id),
        )


def step_review(user_id, options, out):
    """Fica a revisar so o que e recente e sem categoria segura."""
    today = _today(options)
    cutoff = options.reviewed_before or (today - timedelta(days=DEFAULT_REVIEW_DAYS)).isoformat()
    cleared = 0
    with get_db() as conn:
        rules = import_rules_for_matching(conn, user_id)
        rows = conn.execute(
            """
            SELECT o.*, i.entry_type AS item_type, i.amount AS item_amount, i.account_id AS item_account,
                   i.target_table AS item_table, i.target_id AS item_target
            FROM open_finance_transactions o
            JOIN inbox_items i ON i.id = o.item_id AND i.user_id = o.user_id
            WHERE o.user_id = ? AND o.role = 'SOURCE' AND i.state = 'APPROVED' AND i.target_id IS NOT NULL
            """,
            (user_id,),
        ).fetchall()
        for row in rows:
            row = row_to_dict(row)
            confident = open_finance_inbox.category_decision(
                conn, user_id, row, row["item_type"], row["item_amount"], row["item_account"], rules,
            )[2] in open_finance_inbox.CONFIDENT_CATEGORY_SOURCES
            if row["date"] < cutoff or confident:
                _clear_review(conn, user_id, row["item_table"], row["item_target"])
                cleared += 1
        left = conn.execute("SELECT COUNT(*) FROM transactions WHERE user_id = ? AND needs_review = 1", (user_id,)).fetchone()[0]
        left += conn.execute(
            "SELECT COUNT(DISTINCT client_id) FROM cc_expenses WHERE user_id = ? AND needs_review = 1", (user_id,),
        ).fetchone()[0]
    out(f"Revisao: {cleared} sem precisar (antes de {cutoff} ou categoria segura); {left} a revisar.")


# ---------------------------------------------------------------------------
# Saldos e a conferencia final
# ---------------------------------------------------------------------------

def inbox_pending(conn, user_id):
    return [row_to_dict(row) for row in conn.execute(
        "SELECT id, entry_type, amount, currency, occurred_at, description, account_id, reason FROM inbox_items"
        " WHERE user_id = ? AND state = 'PENDING' ORDER BY occurred_at, id",
        (user_id,),
    ).fetchall()]


def _mapped_bank_accounts(conn, user_id):
    return [row_to_dict(row) for row in conn.execute(
        """
        SELECT o.*, a.name AS app_name, a.type AS app_type, a.currency AS app_currency,
               i.pluggy_updated_at
        FROM open_finance_accounts o
        JOIN open_finance_items i ON i.id = o.of_item_id AND i.user_id = o.user_id
        JOIN accounts a ON a.id = o.account_id AND a.user_id = o.user_id
        WHERE o.user_id = ? AND o.ignored_at IS NULL AND i.archived_at IS NULL
        ORDER BY a.name
        """,
        (user_id,),
    ).fetchall()]


def _as_of(conn, user_id, of_account, today):
    """O dia do saldo da Pluggy. Na Corretora importa: o lancamento de uma operacao
    fica na liquidacao, e o saldo so conta o que liquidou ate o dia em que a Pluggy
    leu o banco. Nas outras contas tudo o que existe veio dele (ate hoje)."""
    text = today.isoformat()
    if of_account["app_type"] != "BROKERAGE":
        return text
    moment = parse_iso_datetime(of_account["pluggy_updated_at"])
    newest = conn.execute(
        "SELECT MAX(date) AS last FROM open_finance_transactions WHERE user_id = ? AND of_account_id = ? AND date <= ?",
        (user_id, of_account["id"], text),
    ).fetchone()["last"]
    days = [day for day in (moment.astimezone().date().isoformat() if moment else None, newest) if day]
    return min(max(days), text) if days else text


def _awaiting_cents(conn, user_id, of_account, as_of):
    """O que o banco ja moveu e ainda espera a outra ponta: entra no saldo quando
    gravar, entao o saldo inicial nao pode absorver."""
    total = 0
    for row in conn.execute(
        """
        SELECT o.direction, o.amount_cents FROM open_finance_transactions o
        JOIN inbox_items i ON i.id = o.item_id AND i.user_id = o.user_id
        WHERE o.user_id = ? AND o.of_account_id = ? AND o.role = 'SOURCE' AND i.state = 'PENDING' AND o.date <= ?
        """,
        (user_id, of_account["id"], as_of),
    ).fetchall():
        total += row["amount_cents"] if row["direction"] == "IN" else -row["amount_cents"]
    return total


def _balance(conn, user_id, account_id):
    return next(row for row in account_balance_rows(conn, user_id) if row["id"] == account_id)


def _initial_balance(conn, user_id, account_id):
    return safe_float(conn.execute(
        "SELECT initial_balance FROM accounts WHERE id = ? AND user_id = ?", (account_id, user_id),
    ).fetchone()["initial_balance"])


def set_balances(conn, user_id, state, today, accept_shift=False):
    """Acerta o initial_balance: a conta mapeada na da Pluggy, a sem Pluggy no que
    tinha. Refazer da o mesmo resultado. Devolve cada mudanca. Numa conta cujo
    historico no app nao ia alem do que a Pluggy guarda, nada justifica um salto
    acima de BALANCE_SHIFT_ALERT: falta lancamento, e sem `accept_shift` nada muda."""
    changes = []
    for of_account in _mapped_bank_accounts(conn, user_id):
        if of_account["balance"] is None:
            continue
        account_id = of_account["account_id"]
        as_of = _as_of(conn, user_id, of_account, today)
        app = settled_balance(conn, user_id, account_id, as_of)
        awaiting = _awaiting_cents(conn, user_id, of_account, as_of) / 100
        old = _initial_balance(conn, user_id, account_id)
        new = rounded_money(old + rounded_money(of_account["balance"] - app - awaiting))
        before = safe_float((state.get("initial") or {}).get(account_id), old)
        first_bank = conn.execute(
            "SELECT MIN(date) AS first FROM open_finance_transactions WHERE user_id = ? AND of_account_id = ?",
            (user_id, of_account["id"]),
        ).fetchone()["first"]
        first_app = (state.get("earliest") or {}).get(account_id)
        reaches = bool(first_bank) and (first_app is None or first_app >= first_bank)
        flagged = abs(new - before) > BALANCE_SHIFT_ALERT
        changes.append({
            "account_id": account_id, "name": of_account["app_name"], "before": rounded_money(before), "old": old,
            "new": new, "flagged": flagged, "needs_accept": flagged and reaches,
        })
    blocked = [change for change in changes if change["needs_accept"]]
    if blocked and not accept_shift:
        return changes, blocked
    for change in changes:
        conn.execute(
            "UPDATE accounts SET initial_balance = ? WHERE id = ? AND user_id = ?",
            (change["new"], change["account_id"], user_id),
        )
    for account_id, wanted in (state.get("balances") or {}).items():
        row = next((entry for entry in account_balance_rows(conn, user_id) if entry["id"] == account_id), None)
        if row is None:
            continue
        conn.execute(
            "UPDATE accounts SET initial_balance = ROUND(initial_balance + ?, 2) WHERE id = ? AND user_id = ?",
            (rounded_money(wanted - safe_float(row["balance"])), account_id, user_id),
        )
    return changes, []


def balance_from_rows(conn, user_id, account_id, as_of):
    """O saldo refeito das linhas, sem account_balance_rows() nem o que acertou o
    saldo inicial: a conferencia depois do commit."""
    account = conn.execute(
        "SELECT initial_balance, currency FROM accounts WHERE id = ? AND user_id = ?", (account_id, user_id),
    ).fetchone()
    cents = open_finance_invoices._cents(account["initial_balance"])
    currency = account["currency"] or "BRL"
    for row in conn.execute(
        """
        SELECT t.type, t.amount, t.transfer_amount, t.account_id, t.transfer_account_id, o.currency AS origin
        FROM transactions t LEFT JOIN accounts o ON o.id = t.account_id AND o.user_id = t.user_id
        WHERE t.user_id = ? AND (t.account_id = ? OR t.transfer_account_id = ?) AND substr(t.date, 1, 10) <= ?
        """,
        (user_id, account_id, account_id, as_of),
    ).fetchall():
        amount = open_finance_invoices._cents(row["amount"])
        if row["type"] == "INCOME":
            cents += amount
        elif row["type"] == "EXPENSE" or (row["type"] == "TRANSFER" and row["account_id"] == account_id):
            cents -= amount
        elif row["transfer_amount"] is not None:
            cents += open_finance_invoices._cents(row["transfer_amount"])
        elif (row["origin"] or "BRL") == currency:
            cents += amount
    return cents / 100


def bank_rows_without_entry(conn, user_id):
    """Movimentos do banco sem o lancamento certo no app: o que nenhum ajuste de
    saldo inicial pode esconder. Fora o que nunca entra (COVERED) e o que espera."""
    problems = []
    for row in conn.execute(
        """
        SELECT o.date, o.direction, o.amount_cents, o.description, a.account_id AS mine, t.id AS entry,
               t.amount, t.transfer_amount, t.account_id AS origin, i.state
        FROM open_finance_transactions o
        JOIN open_finance_accounts a ON a.id = o.of_account_id AND a.user_id = o.user_id
        LEFT JOIN transactions t ON t.id = o.target_id AND t.user_id = o.user_id
        LEFT JOIN inbox_items i ON i.id = o.item_id AND i.user_id = o.user_id
        WHERE o.user_id = ? AND a.account_id IS NOT NULL AND a.ignored_at IS NULL
          AND o.role IN ('SOURCE', 'MATCHED', 'INVOICE_PAYMENT')
        """,
        (user_id,),
    ).fetchall():
        if row["state"] == inbox.PENDING:
            continue
        label = f"{row['date']} {row['amount_cents'] / 100:.2f} {row['description']}"
        if not row["entry"]:
            problems.append(f"sem lancamento: {label}")
            continue
        value = row["transfer_amount"] if row["origin"] != row["mine"] and row["transfer_amount"] is not None else row["amount"]
        if open_finance_invoices._cents(value) != row["amount_cents"]:
            problems.append(f"valor diferente ({value}): {label}")
    return problems


def account_lines(conn, user_id, state, today):
    """[{name, bank, app, awaiting, difference, ok}] de cada conta, mapeada ou nao."""
    lines = []
    seen = set()
    for of_account in _mapped_bank_accounts(conn, user_id):
        seen.add(of_account["account_id"])
        as_of = _as_of(conn, user_id, of_account, today)
        app = rounded_money(balance_from_rows(conn, user_id, of_account["account_id"], as_of))
        awaiting = _awaiting_cents(conn, user_id, of_account, as_of) / 100
        bank = of_account["balance"]
        difference = None if bank is None else rounded_money(bank - app)
        lines.append({
            "name": of_account["app_name"], "currency": of_account["app_currency"] or "BRL", "bank": bank,
            "app": app, "awaiting": rounded_money(awaiting), "as_of": as_of, "difference": difference,
            "ok": bank is not None and abs(rounded_money(difference - awaiting)) < 0.005,
        })
    for account_id, wanted in {**(state.get("balances") or {}), **(state.get("kept") or {})}.items():
        if account_id in seen:
            continue
        row = next((entry for entry in account_balance_rows(conn, user_id) if entry["id"] == account_id), None)
        if row is None:
            continue
        app = rounded_money(row["balance"])
        lines.append({
            "name": row["name"], "currency": row["currency"] or "BRL", "bank": wanted, "app": app, "awaiting": 0,
            "as_of": "antes do rebuild", "difference": rounded_money(wanted - app), "ok": abs(wanted - app) < 0.005,
        })
    return lines


def card_lines(conn, user_id, today):
    """Cada cartao: o que a Pluggy diz contra a fatura aberta. A Pluggy nao diz se o
    saldo conta as parcelas futuras: confere se bate com a fatura atual, com ela
    mais a proxima, ou com todo o aberto; senao a diferenca fica nomeada."""
    lines = []
    for of_account in conn.execute(
        """
        SELECT o.* FROM open_finance_accounts o
        JOIN open_finance_items i ON i.id = o.of_item_id AND i.user_id = o.user_id
        WHERE o.user_id = ? AND o.card_id IS NOT NULL AND o.ignored_at IS NULL AND i.archived_at IS NULL
        """,
        (user_id,),
    ).fetchall():
        card = conn.execute(
            "SELECT * FROM credit_cards WHERE id = ? AND user_id = ?", (of_account["card_id"], user_id),
        ).fetchone()
        open_list = open_finance_invoices.open_invoices(conn, user_id, card)
        amounts = [entry["cents"] / 100 for entry in open_list]
        total = sum(amounts)
        bank = abs(of_account["balance"]) if of_account["balance"] is not None else None
        options_seen = {"fatura atual": amounts[0] if amounts else 0.0, "fatura atual e a proxima": sum(amounts[:2]),
                        "todo o aberto": total}
        explained = None
        if bank is not None:
            explained = next((label for label, value in options_seen.items() if abs(bank - value) <= CARD_TOLERANCE), None)
        lines.append({
            "name": card["name"], "bank": bank, "open_total": rounded_money(total),
            "current": rounded_money(options_seen["fatura atual"]), "future": rounded_money(total - options_seen["fatura atual"]),
            "explained": explained, "difference": None if bank is None else rounded_money(bank - options_seen["fatura atual"]),
        })
    return lines


def non_pluggy_rows(conn, user_id, keep_ids, kept_cards=()):
    """Quantos lancamentos nao vieram da Pluggy, nem da Flash, nem da carteira."""
    keep = sorted(keep_ids)
    marks = _marks(keep) if keep else "''"
    count = conn.execute(
        f"""
        SELECT COUNT(*) FROM transactions t
        WHERE t.user_id = ? AND COALESCE(t.source_type, '') NOT IN (?, ?)
          AND COALESCE(t.account_id, '') NOT IN ({marks}) AND COALESCE(t.transfer_account_id, '') NOT IN ({marks})
          AND NOT EXISTS (
              SELECT 1 FROM open_finance_transactions o
              WHERE o.user_id = t.user_id AND o.target_table = 'transactions' AND o.target_id = t.id
          )
        """,
        (user_id, INVESTMENT_CASH_SOURCE_TYPE, INVESTMENT_PROCEED_SOURCE_TYPE, *keep, *keep),
    ).fetchone()[0]
    kept_cards = sorted(kept_cards or ())
    count += conn.execute(
        f"""
        SELECT COUNT(*) FROM cc_expenses
        WHERE user_id = ? AND COALESCE(client_id, '') NOT LIKE 'pluggy:%'
          AND card_id NOT IN ({_marks(kept_cards) if kept_cards else "''"})
        """,
        (user_id, *kept_cards),
    ).fetchone()[0]
    return count


def step_balances(user_id, options, out):
    today = _today(options)
    result = proceeds_sync.sync_proceeds(user_id, force=True)
    out(f"Proventos recalculados: {result['status']} {result.get('message') or ''}".rstrip())
    with get_db() as conn:
        proceeds_cash.apply_paid_proceeds(conn, user_id)
        resync_investment_cash_dates(conn, user_id)
    realized_results.refresh_realized_results(user_id)
    failures = [] if result["status"] in ("ok", "skipped") else ["Os proventos nao foram recalculados: rode --from-step balances."]
    with get_db() as conn:
        state = load_state(conn, user_id)
        changes, blocked = set_balances(conn, user_id, state, today, options.accept_balance_shift)
    out("Saldo inicial (o que estava -> o novo):")
    for change in changes:
        alert = " ALERTA: mudou mais de R$ 1.000 desde antes do rebuild" if change["flagged"] else ""
        out(f"  {change['name']}: {change['old']} -> {change['new']} (antes do rebuild {change['before']}){alert}")
    if blocked:
        names_blocked = ", ".join(change["name"] for change in blocked)
        raise RebuildFailed(
            f"Pode faltar lancamento em {names_blocked}: a Pluggy cobre todo o historico e o saldo inicial saltou. "
            "Nada mudou nos saldos; confira e rode --from-step balances --accept-balance-shift."
        )
    with get_db() as conn:
        keep_ids = kept_account_ids(conn, user_id, options.keep_accounts)
        missing = bank_rows_without_entry(conn, user_id)
        lines = account_lines(conn, user_id, state, today)
        cards = card_lines(conn, user_id, today)
        pending = inbox_pending(conn, user_id)
        foreign = non_pluggy_rows(conn, user_id, keep_ids, kept_card_ids(conn, user_id, options.keep_accounts))
        check = open_finance_investments.portfolio_check(conn, user_id, today)
        flash_rows = conn.execute(
            f"SELECT COUNT(*) FROM transactions WHERE user_id = ? AND account_id IN ({_marks(keep_ids) or chr(39) * 2})",
            (user_id, *keep_ids),
        ).fetchone()[0] if keep_ids else 0
        investment_rows = conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE user_id = ? AND source_type IN (?, ?)",
            (user_id, INVESTMENT_CASH_SOURCE_TYPE, INVESTMENT_PROCEED_SOURCE_TYPE),
        ).fetchone()[0]
    out("")
    out("Saldos (banco x app):")
    for line in lines:
        mark = "ok " if line["ok"] else "DIF"
        extra = f", aguardando {line['awaiting']}" if line["awaiting"] else ""
        out(f"  {mark} {line['name']} ({line['currency']}): {line['bank']} x {line['app']} em {line['as_of']}{extra}")
        if not line["ok"]:
            failures.append(f"{line['name']}: banco {line['bank']} x app {line['app']} (diferenca {line['difference']})")
    out("Cartoes (banco x fatura):")
    for line in cards:
        if line["explained"]:
            out(f"  ok  {line['name']}: {line['bank']} = {line['explained']} (aberto {line['open_total']})")
        else:
            out(f"  DIF {line['name']}: banco {line['bank']} x fatura atual {line['current']}, "
                f"parcelas futuras {line['future']}, diferenca {line['difference']}")
            failures.append(f"{line['name']}: cartao {line['bank']} x fatura {line['current']} (diferenca {line['difference']})")
    if missing:
        out(f"Movimentos do banco sem lancamento certo: {len(missing)}")
        for line in missing[:50]:
            out(f"  {line}")
        failures.append(f"{len(missing)} movimento(s) do banco sem lancamento certo no app.")
    if pending:
        out(f"Itens pendentes: {len(pending)}")
        for entry in pending:
            out(f"  {str(entry['occurred_at'])[:10]} {entry['amount']} {entry['description']} ({entry['reason']})")
        if not options.allow_pending:
            failures.append(f"{len(pending)} item(ns) pendente(s).")
    out(f"Lancamentos fora da Pluggy: {flash_rows} da(s) conta(s) mantida(s), {investment_rows} de investimento, {foreign} outros.")
    if foreign:
        failures.append(f"{foreign} lancamento(s) nao vieram da Pluggy.")
    if check:
        for entry in check["positions"]:
            if entry.get("matches") is False:
                failures.append(f"{entry['code']}: app {entry['app_quantity']} x Pluggy {entry['expected_quantity']}")
        out(f"Carteira: {check['mismatched_count']} ativo(s) diferente(s), caixa {check['cash']}.")
    if failures:
        out("")
        out("FALHOU:")
        for line in failures:
            out(f"  {line}")
        return EXIT_FAILED
    with get_db() as conn:
        conn.execute("DELETE FROM user_settings WHERE user_id = ? AND setting_key = ?", (user_id, STATE_SETTING))
    out("Tudo confere.")
    return EXIT_OK


def apply(user_id, options, out=print):
    """Roda os passos a partir de `options.from_step`. Devolve o codigo de saida."""
    try:
        order = STEPS[STEPS.index(options.from_step):]
        if {"wipe", "pull"} & set(order):
            with get_db() as conn:
                problems = preflight(conn, user_id, options)
            if problems:
                raise RebuildRefused(" ".join(problems))
        path = verified_backup()
        out(f"Backup verificado: {path}")
        if "wipe" in order:
            gate = investment_gate(user_id, options)
            print_gate(gate, out)
            if gate["gaps"] and not options.accept_investment_gaps:
                raise RebuildRefused("A carteira nao fecharia: nada foi feito (--accept-investment-gaps para seguir).")
        if "register" in order:
            register_and_map(user_id, options, out)
        if "wipe" in order:
            step_wipe(user_id, options, out)
        if "pull" in order:
            step_pull(user_id, options, out)
        if "settle" in order:
            step_settle(user_id, options, out)
        if "review" in order:
            step_review(user_id, options, out)
        return step_balances(user_id, options, out)
    except RebuildRefused as exc:
        out(f"RECUSADO: {exc}")
        return EXIT_REFUSED
    except (RebuildFailed, open_finance.PluggyError) as exc:
        out(f"FALHOU: {exc}")
        out("Nada se perdeu: o estado esta guardado. Corrija e rode de novo com --from-step.")
        return EXIT_FAILED


# ---------------------------------------------------------------------------
# Relatorio de categorias
# ---------------------------------------------------------------------------

UNCATEGORIZED = ("Outros", "Receita")


def category_report(user_id, top=25):
    """Quantas linhas em cada categoria e o que mais ficou sem categoria."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT COALESCE(category, '(sem)') AS category, COALESCE(description, '') AS description FROM transactions
            WHERE user_id = ? AND type IN ('EXPENSE', 'INCOME')
              AND COALESCE(source_type, '') NOT IN ('INVESTMENT_TRANSACTION', 'INVESTMENT_PROCEED', 'CC_INVOICE_PAYMENT', 'CC_AUTOPAY')
            UNION ALL
            SELECT COALESCE(MIN(category), '(sem)'), COALESCE(MIN(description), '') FROM cc_expenses
            WHERE user_id = ? AND kind <> 'REFUND'
            GROUP BY COALESCE(client_id, id)
            """,
            (user_id, user_id),
        ).fetchall()
    categories = Counter(row["category"] for row in rows)
    loose = Counter(row["description"] for row in rows if row["category"] in UNCATEGORIZED or row["category"] == "(sem)")
    return {"categories": categories.most_common(), "uncategorized": loose.most_common(top), "total": len(rows)}


def print_category_report(report, out=print):
    out(f"{report['total']} lancamentos e compras:")
    for name, total in report["categories"]:
        out(f"  {total:6d}  {name}")
    out("Mais frequentes sem categoria:")
    for name, total in report["uncategorized"]:
        out(f"  {total:6d}  {name}")
