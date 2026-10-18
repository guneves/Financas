"""Pluggy (Open Finance): o que o banco registrou entra no app, conciliado (027).

`sync_pluggy()` le, para cada conta da Pluggy ligada a uma conta ou cartao do
app (`pluggy_account_links`), as transacoes desde `since` na primeira vez, e
dos ultimos PLUGGY_LOOKBACK_DAYS depois. Cada transacao ganha uma linha no
livro `pluggy_transactions` — a chave e o id da Pluggy, entao sincronizar de
novo nao grava nada que o livro ja decidiu — e o livro diz o que foi feito:

- ATTACHED: confirma um lancamento que ja existia. Mesma conta (ou cartao),
  mesmo tipo, mesmo valor, data a PLUGGY_MATCH_DAYS dias, e um candidato so
  entre os que a conciliacao pode tocar: os digitados (com ou sem client_id,
  os do celular inclusive), os de extrato importado e os de recorrencia. O
  lancamento ganha `external_id` e fica como o dono deixou; uma diferenca de
  data fica anotada em `difference`, nunca corrigida.
- IMPORTED: nenhum candidato, nasce um lancamento com source_type 'PLUGGY'. No
  cartao, uma compra em cc_expenses pela regra da fatura do backend
  (`build_installment_rows`), com as parcelas da Pluggy: a primeira parcela
  que chega cria a compra inteira, as seguintes marcam a parcela delas.
- REVIEW ("Possivel duplicata"): dois candidatos ou mais; um lancamento que a
  conciliacao nao toca (transferencia, pagamento de fatura, caixa de
  investimento, provento) com o mesmo valor e data; ou, no cartao, uma compra
  de mesmo total com outro numero de parcelas. Nada e gravado ate o dono
  decidir (`resolve_review`): e o mesmo, lancar separado, ou ignorar.
- WAITING: PENDING na Pluggy (no cartao, a compra da fatura ainda aberta),
  ate virar POSTED, a menos que PLUGGY_IMPORT_PENDING.
- SKIPPED: fora do que o app guarda — antes de `since`; credito no cartao
  (pagamento da fatura, estorno, cashback: o app nao tem item negativo de
  fatura, e o pagamento ja e o lancamento da conta).
- DISMISSED: o dono mandou ignorar. REMOVED: sumiu da Pluggy.

O que a Pluggy muda depois e seguido so no que nasceu dela (valor e data; no
cartao, o valor da parcela em aberto). Uma transacao que some da Pluggy apaga
o lancamento que nasceu dela — menos o que tem comprovante ou parcela paga, e o
que o dono confirmou do celular, que vira lancamento manual — e solta o
external_id do lancamento que ela confirmava.

O caminho inverso (a Pluggy trouxe primeiro, o dono confirma do celular
depois) esta em `claim_bank_transaction` / `claim_bank_purchase`, chamados
pelas rotas de criacao.

A rede fica fora da transacao do banco: primeiro todas as leituras, depois uma
escrita so. Uma conta cuja leitura falhou nao e comparada: o que faltasse seria
lido como apagado na Pluggy.
"""

import json
import threading
import time
from datetime import timedelta

import pluggy_client
import statement_import
from applog import get_logger
from config import (
    PLUGGY_IMPORT_PENDING,
    PLUGGY_LOOKBACK_DAYS,
    PLUGGY_MATCH_DAYS,
    PLUGGY_SYNC_MIN_INTERVAL_SECONDS,
)
from dates import parse_iso_date, subtract_months
from db import get_db, new_id, row_to_dict, utc_timestamp
from integrations import record_provider_result
from money import rounded_money
from services.import_rules import (
    DEFAULT_IMPORT_CATEGORIES,
    count_rule_hits,
    import_default_category,
    import_rules_for_matching,
)
from services.invoices import build_installment_rows, local_today
from source_types import (
    CC_AUTOPAY_SOURCE_TYPE,
    CC_INVOICE_PAYMENT_SOURCE_TYPE,
    INVESTMENT_CASH_SOURCE_TYPE,
    INVESTMENT_PROCEED_SOURCE_TYPE,
    PLUGGY_SOURCE_TYPE,
    RECURRING_SOURCE_TYPE,
    STATEMENT_IMPORT_SOURCE_TYPE,
)
from validators import ValidationError

logger = get_logger(__name__)

PROVIDER = "pluggy"

IMPORTED = "IMPORTED"
ATTACHED = "ATTACHED"
REVIEW = "REVIEW"
WAITING = "WAITING"
SKIPPED = "SKIPPED"
DISMISSED = "DISMISSED"
REMOVED = "REMOVED"
# O que uma nova leitura decide de novo do zero.
REDECIDED_STATES = {WAITING, REMOVED}

# Lancamentos que a conciliacao confirma (external_id): digitados, de extrato
# importado e de recorrencia. Os outros tem dono proprio e so entram como
# "possivel duplicata".
ATTACHABLE_SOURCES = (STATEMENT_IMPORT_SOURCE_TYPE, RECURRING_SOURCE_TYPE)
OUT_OF_REACH_SOURCES = {
    CC_INVOICE_PAYMENT_SOURCE_TYPE: "invoice_payment",
    CC_AUTOPAY_SOURCE_TYPE: "invoice_payment",
    INVESTMENT_CASH_SOURCE_TYPE: "investment_cash",
    INVESTMENT_PROCEED_SOURCE_TYPE: "proceed",
}

_sync_lock = threading.Lock()
_last_run = {}


def reset_sync_throttle():
    """Para os testes: a proxima sincronizacao automatica roda."""
    _last_run.clear()


def external_key(pluggy_id):
    return f"pluggy:{pluggy_id}"


def _cents(value):
    return int(round(float(value) * 100))


def _reais(cents):
    return rounded_money(cents / 100)


def _shift(date_text, days):
    return (parse_iso_date(date_text) + timedelta(days=days)).strftime("%Y-%m-%d")


def card_purchase_date(tx):
    """A data da compra: a da Pluggy (purchaseDate) ou, sem ela, a da parcela
    recuada para a primeira — uma estimativa."""
    if tx.purchase_date:
        return tx.purchase_date
    if tx.installment_number > 1:
        first = subtract_months(parse_iso_date(tx.date).date(), tx.installment_number - 1)
        return first.strftime("%Y-%m-%d")
    return tx.date


def _result(status, message=None, **counts):
    base = {
        "status": status,
        "message": message,
        "created": 0,
        "attached": 0,
        "review": 0,
        "waiting": 0,
        "skipped": 0,
        "updated": 0,
        "removed": 0,
        "failed": [],
    }
    base.update(counts)
    return base


def sync_pluggy(current_user_id, *, force=False, today=None):
    """Sincroniza as contas ligadas do usuario.

    Devolve {"status": ok|partial|error|skipped|running|not_configured,
    "message", contagens, "failed": [contas]}. Sem `force`, roda no maximo uma
    vez a cada PLUGGY_SYNC_MIN_INTERVAL_SECONDS.
    """
    if not pluggy_client.is_configured():
        return _result("not_configured", pluggy_client.not_configured_message())
    now = time.monotonic()
    last = _last_run.get(current_user_id)
    if not force and last is not None and now - last < PLUGGY_SYNC_MIN_INTERVAL_SECONDS:
        return _result("skipped")
    if not _sync_lock.acquire(blocking=False):
        return _result("running", "Uma sincronizacao ja esta em andamento.")
    try:
        _last_run[current_user_id] = now
        return _run(current_user_id, today or local_today())
    finally:
        _sync_lock.release()


def _window_start(link, today):
    if not link["full_sync_done"]:
        return link["since"]
    recent = (today - timedelta(days=PLUGGY_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    return max(link["since"], recent)


def _run(current_user_id, today):
    with get_db() as conn:
        items = conn.execute(
            "SELECT * FROM pluggy_items WHERE user_id = ? ORDER BY created_at",
            (current_user_id,),
        ).fetchall()
        links = conn.execute(
            "SELECT * FROM pluggy_account_links WHERE user_id = ? ORDER BY created_at",
            (current_user_id,),
        ).fetchall()
    if not links:
        return _result("skipped", "Nenhuma conta da Pluggy ligada a uma conta ou cartao.")

    item_reads = {}
    failed = []
    for item in items:
        try:
            item_reads[item["item_id"]] = (pluggy_client.get_item(item["item_id"]), None)
        except pluggy_client.PluggyError as exc:
            item_reads[item["item_id"]] = (None, str(exc))

    reads = []
    for link in links:
        window_start = _window_start(link, today)
        try:
            # Um dia antes: o filtro `from` da Pluggy pode ser "maior que".
            transactions = pluggy_client.list_transactions(
                link["pluggy_account_id"],
                _shift(window_start, -1),
                account_type=link["pluggy_account_type"],
            )
        except pluggy_client.PluggyError as exc:
            failed.append(link["name"] or link["pluggy_account_id"])
            logger.warning(
                "Pluggy: leitura da conta falhou",
                extra={"pluggy_account_id": link["pluggy_account_id"], "error": str(exc)},
            )
            continue
        reads.append((link, window_start, transactions))

    item_errors = [error for _item, error in item_reads.values() if error]
    errors = item_errors + [f"Conta {name}" for name in failed]
    record_provider_result(PROVIDER, not errors, "; ".join(errors) if errors else None)

    counts = {key: 0 for key in ("created", "attached", "review", "waiting", "skipped", "updated", "removed")}
    with get_db() as conn:
        stamp = utc_timestamp()
        for item in items:
            read, error = item_reads[item["item_id"]]
            conn.execute(
                """
                UPDATE pluggy_items
                SET connector_name = COALESCE(?, connector_name), status = COALESCE(?, status),
                    execution_status = COALESCE(?, execution_status),
                    last_updated_at = COALESCE(?, last_updated_at),
                    last_sync_at = ?, last_error = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    read.connector_name or None if read else None,
                    read.status or None if read else None,
                    read.execution_status or None if read else None,
                    read.last_updated_at or None if read else None,
                    stamp,
                    error,
                    item["id"],
                    current_user_id,
                ),
            )
        context = SyncContext(conn, current_user_id, import_rules_for_matching(conn, current_user_id))
        for link, window_start, transactions in reads:
            # O que sumiu sai antes: um PENDING que voltou POSTED com outro id deixa
            # livre o lancamento que o dono confirmou, e o POSTED confirma esse.
            counts["removed"] += remove_missing(
                context, link, window_start, {tx.id for tx in transactions}
            )
            for tx in sorted(transactions, key=lambda item: (item.date, item.id)):
                outcome = apply_transaction(context, link, tx)
                if outcome:
                    counts[outcome] += 1
            if not link["full_sync_done"]:
                conn.execute(
                    "UPDATE pluggy_account_links SET full_sync_done = 1 WHERE id = ? AND user_id = ?",
                    (link["id"], current_user_id),
                )
        count_rule_hits(conn, current_user_id, context.rule_hits)

    if errors and not reads:
        status = "error"
    elif errors:
        status = "partial"
    else:
        status = "ok"
    message = "; ".join(errors) if errors else None
    return _result(status, message, failed=failed, **counts)


class SyncContext:
    def __init__(self, conn, current_user_id, rules):
        self.conn = conn
        self.user_id = current_user_id
        self.rules = rules
        self.rule_hits = {}

    def categorize(self, description, transaction_type, amount, account_id=None):
        rule = statement_import.first_matching_rule(
            self.rules, description, transaction_type, amount, account_id
        )
        if rule:
            self.rule_hits[str(rule["id"])] = self.rule_hits.get(str(rule["id"]), 0) + 1
            return rule["category"], rule["category_id"]
        name, category_id = import_default_category(self.conn, self.user_id, transaction_type)
        return name or DEFAULT_IMPORT_CATEGORIES[transaction_type], category_id


# ---------------------------------------------------------------------------
# O livro
# ---------------------------------------------------------------------------

def _snapshot(tx, link):
    return {
        "pluggy_account_id": link["pluggy_account_id"],
        "date": tx.date,
        "amount": _reais(tx.amount_cents),
        "direction": tx.direction,
        "description": tx.description,
        "status": tx.status,
        "installment_number": tx.installment_number or None,
        "total_installments": tx.total_installments or None,
        "purchase_date": tx.purchase_date or None,
        "pluggy_updated_at": tx.updated_at or None,
    }


def _write_ledger(context, existing, tx, link, decision):
    values = _snapshot(tx, link)
    values.update({
        "state": decision["state"],
        "reason": decision.get("reason"),
        "target_table": decision.get("target_table"),
        "target_id": decision.get("target_id"),
        "candidates": json.dumps(decision["candidates"]) if decision.get("candidates") else None,
        "difference": json.dumps(decision["difference"]) if decision.get("difference") else None,
        "updated_at": utc_timestamp(),
    })
    if existing is None:
        values.update({"id": new_id(), "user_id": context.user_id, "pluggy_id": tx.id})
        columns = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        context.conn.execute(
            f"INSERT INTO pluggy_transactions ({columns}) VALUES ({marks})",
            tuple(values.values()),
        )
        return
    assignments = ", ".join(f"{column} = ?" for column in values)
    context.conn.execute(
        f"UPDATE pluggy_transactions SET {assignments} WHERE id = ? AND user_id = ?",
        (*values.values(), existing["id"], context.user_id),
    )


def _fetch_ledger(context, pluggy_id):
    return context.conn.execute(
        "SELECT * FROM pluggy_transactions WHERE user_id = ? AND pluggy_id = ?",
        (context.user_id, pluggy_id),
    ).fetchone()


OUTCOME_COUNTER = {
    IMPORTED: "created",
    ATTACHED: "attached",
    REVIEW: "review",
    WAITING: "waiting",
    SKIPPED: "skipped",
}


def apply_transaction(context, link, tx):
    """Decide uma transacao lida agora; devolve o contador que ela soma (ou None)."""
    existing = _fetch_ledger(context, tx.id)
    redecide = (
        existing is None
        or existing["state"] in REDECIDED_STATES
        or (existing["state"] == SKIPPED and existing["reason"] == "before_since")
    )
    if redecide:
        decision = decide(context, link, tx)
        _write_ledger(context, existing, tx, link, decision)
        if existing is not None and existing["state"] == decision["state"]:
            return None
        return OUTCOME_COUNTER.get(decision["state"])

    state = existing["state"]
    decision = {
        "state": state,
        "reason": existing["reason"],
        "target_table": existing["target_table"],
        "target_id": existing["target_id"],
        "candidates": json.loads(existing["candidates"]) if existing["candidates"] else None,
    }
    outcome = None
    if state == IMPORTED and follow_changes(context, existing, link, tx):
        outcome = "updated"
    if state == ATTACHED:
        decision["difference"] = attached_difference(context, existing, tx, link)
    _write_ledger(context, existing, tx, link, decision)
    return outcome


def decide(context, link, tx):
    if tx.status == "PENDING" and not PLUGGY_IMPORT_PENDING:
        return {"state": WAITING}
    if link["pluggy_account_type"] == "CREDIT":
        if tx.direction == "CREDIT":
            return {"state": SKIPPED, "reason": "card_credit"}
        purchase_date = card_purchase_date(tx)
        if purchase_date < link["since"]:
            return {"state": SKIPPED, "reason": "before_since"}
        return decide_card(context, link, tx, purchase_date)
    if tx.date < link["since"]:
        return {"state": SKIPPED, "reason": "before_since"}
    return decide_bank(context, link, tx)


# ---------------------------------------------------------------------------
# Conta
# ---------------------------------------------------------------------------

def bank_type(tx):
    return "EXPENSE" if tx.direction == "DEBIT" else "INCOME"


def candidate_kind(row):
    if row["type"] == "TRANSFER":
        return "transfer"
    return OUT_OF_REACH_SOURCES.get(row["source_type"], "entry")


def bank_candidates(conn, current_user_id, account_id, transaction_type, cents, date_text):
    """Os lancamentos que a transacao pode confirmar: mesmo valor, data na folga, sem external_id."""
    return conn.execute(
        f"""
        SELECT id, date, type, source_type FROM transactions
        WHERE user_id = ? AND account_id = ? AND type = ?
          AND CAST(ROUND(amount * 100) AS INTEGER) = ?
          AND date BETWEEN ? AND ?
          AND external_id IS NULL
          AND (source_type IS NULL OR source_type IN ({", ".join("?" for _ in ATTACHABLE_SOURCES)}))
        ORDER BY date, created_at
        """,
        (
            current_user_id, account_id, transaction_type, cents,
            _shift(date_text, -PLUGGY_MATCH_DAYS), _shift(date_text, PLUGGY_MATCH_DAYS),
            *ATTACHABLE_SOURCES,
        ),
    ).fetchall()


def out_of_reach_candidates(conn, current_user_id, account_id, direction, cents, date_text):
    """Transferencia, pagamento de fatura, caixa de investimento ou provento parecidos,
    que nenhuma outra transacao da Pluggy ja confirmou deste lado."""
    transaction_type = "EXPENSE" if direction == "DEBIT" else "INCOME"
    sources = list(OUT_OF_REACH_SOURCES)
    return conn.execute(
        f"""
        SELECT t.id, t.date, t.type, t.source_type FROM transactions t
        WHERE t.user_id = ?
          AND CAST(ROUND(t.amount * 100) AS INTEGER) = ?
          AND t.date BETWEEN ? AND ?
          AND (
                (t.type = 'TRANSFER' AND (
                    (? = 'DEBIT' AND t.account_id = ?) OR (? = 'CREDIT' AND t.transfer_account_id = ?)
                ))
             OR (t.type = ? AND t.account_id = ?
                 AND t.source_type IN ({", ".join("?" for _ in sources)}))
          )
          AND NOT EXISTS (
                SELECT 1 FROM pluggy_transactions p
                WHERE p.user_id = t.user_id AND p.target_table = 'transactions'
                  AND p.target_id = t.id AND p.direction = ? AND p.state = 'ATTACHED'
          )
        ORDER BY t.date, t.created_at
        """,
        (
            current_user_id, cents,
            _shift(date_text, -PLUGGY_MATCH_DAYS), _shift(date_text, PLUGGY_MATCH_DAYS),
            direction, account_id, direction, account_id,
            transaction_type, account_id, *sources,
            direction,
        ),
    ).fetchall()


def _listed(rows, table="transactions"):
    return [
        {"table": table, "id": row["id"], "kind": candidate_kind(row) if table == "transactions" else "card_purchase"}
        for row in rows
    ]


def decide_bank(context, link, tx):
    conn, user_id = context.conn, context.user_id
    transaction_type = bank_type(tx)
    account_id = link["account_id"]
    candidates = bank_candidates(conn, user_id, account_id, transaction_type, tx.amount_cents, tx.date)
    blockers = out_of_reach_candidates(conn, user_id, account_id, tx.direction, tx.amount_cents, tx.date)
    if blockers:
        return {"state": REVIEW, "reason": "out_of_reach", "candidates": _listed(blockers) + _listed(candidates)}
    if len(candidates) > 1:
        return {"state": REVIEW, "reason": "several_candidates", "candidates": _listed(candidates)}
    if len(candidates) == 1:
        return attach(context, "transactions", candidates[0]["id"], tx, link)
    return import_bank(context, link, tx)


def import_bank(context, link, tx):
    transaction_type = bank_type(tx)
    amount = _reais(tx.amount_cents)
    category, category_id = context.categorize(tx.description, transaction_type, amount, link["account_id"])
    item_id = new_id()
    key = external_key(tx.id)
    context.conn.execute(
        """
        INSERT INTO transactions
        (id, user_id, account_id, amount, date, category, category_id, description, type,
         source_type, source_id, external_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item_id, context.user_id, link["account_id"], amount, tx.date, category, category_id,
            tx.description or None, transaction_type, PLUGGY_SOURCE_TYPE, key, key,
        ),
    )
    return {"state": IMPORTED, "target_table": "transactions", "target_id": item_id}


# ---------------------------------------------------------------------------
# Cartao
# ---------------------------------------------------------------------------

def _installment(tx):
    total = tx.total_installments or 1
    number = tx.installment_number or 1
    return number, total


def card_candidates(conn, current_user_id, card_id, info, cents, purchase_date, tolerance):
    return conn.execute(
        """
        SELECT id, purchase_date, amount FROM cc_expenses
        WHERE user_id = ? AND card_id = ? AND installment_info = ?
          AND external_id IS NULL AND source_type IS NULL
          AND purchase_date BETWEEN ? AND ?
          AND ABS(CAST(ROUND(amount * 100) AS INTEGER) - ?) <= ?
        ORDER BY purchase_date, created_at
        """,
        (
            current_user_id, card_id, info,
            _shift(purchase_date, -PLUGGY_MATCH_DAYS), _shift(purchase_date, PLUGGY_MATCH_DAYS),
            cents, tolerance,
        ),
    ).fetchall()


def installment_count_mismatches(conn, current_user_id, card_id, total, cents, purchase_date):
    """Compras do dono de mesmo total na mesma folga, com outro numero de parcelas."""
    rows = conn.execute(
        """
        SELECT id, amount, installment_info FROM cc_expenses
        WHERE user_id = ? AND card_id = ? AND installment_info LIKE '1/%'
          AND external_id IS NULL AND source_type IS NULL
          AND purchase_date BETWEEN ? AND ?
        """,
        (
            current_user_id, card_id,
            _shift(purchase_date, -PLUGGY_MATCH_DAYS), _shift(purchase_date, PLUGGY_MATCH_DAYS),
        ),
    ).fetchall()
    wanted = cents * total
    found = []
    for row in rows:
        try:
            count = int(str(row["installment_info"]).split("/", 1)[1])
        except (IndexError, ValueError):
            continue
        if count == total:
            continue
        if abs(_cents(row["amount"]) * count - wanted) <= max(count, total):
            found.append(row)
    return found


def decide_card(context, link, tx, purchase_date):
    conn, user_id = context.conn, context.user_id
    number, total = _installment(tx)
    info = f"{number}/{total}"
    tolerance = 1 if total > 1 else 0
    candidates = card_candidates(conn, user_id, link["card_id"], info, tx.amount_cents, purchase_date, tolerance)
    if len(candidates) > 1:
        return {"state": REVIEW, "reason": "several_candidates", "candidates": _listed(candidates, "cc_expenses")}
    if len(candidates) == 1:
        return attach(context, "cc_expenses", candidates[0]["id"], tx, link)
    if number == 1:
        mismatches = installment_count_mismatches(
            conn, user_id, link["card_id"], total, tx.amount_cents, purchase_date
        )
        if mismatches:
            return {
                "state": REVIEW,
                "reason": "installments_differ",
                "candidates": _listed(mismatches, "cc_expenses"),
            }
    return import_card(context, link, tx, purchase_date)


def import_card(context, link, tx, purchase_date):
    conn, user_id = context.conn, context.user_id
    number, total = _installment(tx)
    info = f"{number}/{total}"
    key = external_key(tx.id)
    # Uma parcela de uma compra que outra parcela ja criou.
    born = conn.execute(
        """
        SELECT id FROM cc_expenses
        WHERE user_id = ? AND card_id = ? AND source_type = ? AND installment_info = ?
          AND purchase_date = ? AND external_id IS NULL
          AND ABS(CAST(ROUND(amount * 100) AS INTEGER) - ?) <= 1
        ORDER BY created_at
        LIMIT 1
        """,
        (user_id, link["card_id"], PLUGGY_SOURCE_TYPE, info, purchase_date, tx.amount_cents),
    ).fetchone()
    if born and total > 1:
        conn.execute(
            "UPDATE cc_expenses SET external_id = ? WHERE id = ? AND user_id = ?",
            (key, born["id"], user_id),
        )
        return {"state": IMPORTED, "target_table": "cc_expenses", "target_id": born["id"]}

    card = conn.execute(
        "SELECT due_day, closing_day FROM credit_cards WHERE id = ? AND user_id = ?",
        (link["card_id"], user_id),
    ).fetchone()
    category, _category_id = context.categorize(tx.description, "EXPENSE", _reais(tx.amount_cents))
    rows = build_installment_rows(
        {
            "card_id": link["card_id"],
            "category": category,
            "description": tx.description or "Compra no cartão",
            # Toda parcela com o valor da Pluggy: o total e parcela x parcelas.
            "total_amount": _reais(tx.amount_cents * total),
            "purchase_date": purchase_date,
            "installments": total,
        },
        card,
    )
    target_id = None
    for row in rows:
        row_id = new_id()
        is_target = row["installment_info"] == info
        if is_target:
            target_id = row_id
        conn.execute(
            """
            INSERT INTO cc_expenses
            (id, user_id, card_id, category, description, amount, purchase_date,
             invoice_month, invoice_year, installment_info, status, source_type, source_id,
             external_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id, user_id, row["card_id"], row["category"], row["description"], row["amount"],
                row["purchase_date"], row["invoice_month"], row["invoice_year"],
                row["installment_info"], row["status"], PLUGGY_SOURCE_TYPE, key,
                key if is_target else None,
            ),
        )
    return {"state": IMPORTED, "target_table": "cc_expenses", "target_id": target_id}


# ---------------------------------------------------------------------------
# Confirmar, seguir, soltar
# ---------------------------------------------------------------------------

def attach(context, table, target_id, tx, link):
    context.conn.execute(
        f"UPDATE {table} SET external_id = ? WHERE id = ? AND user_id = ? AND external_id IS NULL",
        (external_key(tx.id), target_id, context.user_id),
    )
    decision = {"state": ATTACHED, "target_table": table, "target_id": target_id}
    decision["difference"] = _difference(context, table, target_id, tx, link)
    return decision


def _difference(context, table, target_id, tx, link):
    row = context.conn.execute(
        f"SELECT * FROM {table} WHERE id = ? AND user_id = ?",
        (target_id, context.user_id),
    ).fetchone()
    if not row:
        return None
    difference = {}
    if _cents(row["amount"]) != tx.amount_cents:
        difference["amount"] = _reais(tx.amount_cents)
    if table == "transactions":
        if row["date"] != tx.date:
            difference["date"] = tx.date
    elif row["purchase_date"] != card_purchase_date(tx):
        difference["date"] = card_purchase_date(tx)
    return difference or None


def attached_difference(context, existing, tx, link):
    if not existing["target_id"]:
        return None
    return _difference(context, existing["target_table"], existing["target_id"], tx, link)


def follow_changes(context, existing, link, tx):
    """Valor e data do que nasceu da Pluggy acompanham a Pluggy."""
    if _cents(existing["amount"]) == tx.amount_cents and existing["date"] == tx.date:
        return False
    if not existing["target_id"]:
        return False
    if existing["target_table"] == "transactions":
        cursor = context.conn.execute(
            """
            UPDATE transactions SET amount = ?, date = ?
            WHERE id = ? AND user_id = ? AND source_type = ?
            """,
            (_reais(tx.amount_cents), tx.date, existing["target_id"], context.user_id, PLUGGY_SOURCE_TYPE),
        )
    else:
        cursor = context.conn.execute(
            """
            UPDATE cc_expenses SET amount = ?
            WHERE id = ? AND user_id = ? AND source_type = ? AND status = 'OPEN'
            """,
            (_reais(tx.amount_cents), existing["target_id"], context.user_id, PLUGGY_SOURCE_TYPE),
        )
    return cursor.rowcount > 0


def _release(conn, current_user_id, table, target_id, key):
    conn.execute(
        f"UPDATE {table} SET external_id = NULL WHERE id = ? AND user_id = ? AND external_id = ?",
        (target_id, current_user_id, key),
    )


def remove_missing(context, link, window_start, seen):
    """O que o livro tem nesta conta, na janela lida, e a Pluggy nao mandou mais."""
    rows = context.conn.execute(
        """
        SELECT * FROM pluggy_transactions
        WHERE user_id = ? AND pluggy_account_id = ? AND date >= ?
          AND state IN ('IMPORTED', 'ATTACHED', 'REVIEW', 'WAITING')
        """,
        (context.user_id, link["pluggy_account_id"], window_start),
    ).fetchall()
    removed = 0
    for row in rows:
        if row["pluggy_id"] in seen:
            continue
        reason = None
        key = external_key(row["pluggy_id"])
        if row["state"] == ATTACHED and row["target_id"]:
            _release(context.conn, context.user_id, row["target_table"], row["target_id"], key)
        elif row["state"] == IMPORTED and row["target_id"]:
            reason = remove_born(context, row, key)
        context.conn.execute(
            """
            UPDATE pluggy_transactions SET state = ?, reason = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (REMOVED, reason, utc_timestamp(), row["id"], context.user_id),
        )
        removed += 1
    return removed


def remove_born(context, ledger_row, key):
    """Apaga o lancamento que nasceu de uma transacao que sumiu; devolve por que ficou, se ficou."""
    conn, user_id = context.conn, context.user_id
    if ledger_row["target_table"] == "transactions":
        row = conn.execute(
            "SELECT id, client_id FROM transactions WHERE id = ? AND user_id = ? AND source_type = ?",
            (ledger_row["target_id"], user_id, PLUGGY_SOURCE_TYPE),
        ).fetchone()
        if not row:
            return None
        receipts = conn.execute(
            "SELECT COUNT(*) FROM transaction_attachments WHERE user_id = ? AND transaction_id = ?",
            (user_id, row["id"]),
        ).fetchone()[0]
        if row["client_id"]:
            # O dono confirmou esta compra no celular: ela fica, como lancamento dele.
            conn.execute(
                """
                UPDATE transactions SET source_type = NULL, source_id = NULL, external_id = NULL
                WHERE id = ? AND user_id = ?
                """,
                (row["id"], user_id),
            )
            return "kept_confirmed"
        if receipts:
            _release(conn, user_id, "transactions", row["id"], key)
            return "kept_receipt"
        conn.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (row["id"], user_id))
        return None

    target = conn.execute(
        "SELECT id, source_id FROM cc_expenses WHERE id = ? AND user_id = ? AND source_type = ?",
        (ledger_row["target_id"], user_id, PLUGGY_SOURCE_TYPE),
    ).fetchone()
    if not target:
        return None
    group = conn.execute(
        """
        SELECT id, status, client_id, external_id FROM cc_expenses
        WHERE user_id = ? AND source_type = ? AND source_id = ?
        """,
        (user_id, PLUGGY_SOURCE_TYPE, target["source_id"]),
    ).fetchall()
    ids = [row["id"] for row in group]
    marks = ", ".join("?" for _ in ids)
    receipts = conn.execute(
        f"SELECT COUNT(*) FROM cc_expense_attachments WHERE user_id = ? AND cc_expense_id IN ({marks})",
        (user_id, *ids),
    ).fetchone()[0]
    if any(row["client_id"] for row in group):
        conn.execute(
            f"""
            UPDATE cc_expenses SET source_type = NULL, source_id = NULL
            WHERE user_id = ? AND id IN ({marks})
            """,
            (user_id, *ids),
        )
        _release(conn, user_id, "cc_expenses", target["id"], key)
        return "kept_confirmed"
    others = [row for row in group if row["external_id"] and row["external_id"] != key]
    if receipts or others or any(row["status"] == "PAID" for row in group):
        _release(conn, user_id, "cc_expenses", target["id"], key)
        return "kept_receipt" if receipts else ("kept_paid" if not others else "kept_other_installments")
    conn.execute(f"DELETE FROM cc_expenses WHERE user_id = ? AND id IN ({marks})", (user_id, *ids))
    return None


# ---------------------------------------------------------------------------
# Possivel duplicata: a decisao do dono
# ---------------------------------------------------------------------------

def _ledger_transaction(row):
    """A transacao da Pluggy como o livro a guardou, para decidir sem ir a rede."""
    return pluggy_client.PluggyTransaction(
        id=row["pluggy_id"],
        account_id=row["pluggy_account_id"],
        date=row["date"],
        description=row["description"] or "",
        amount_cents=_cents(row["amount"]),
        direction=row["direction"],
        status=row["status"],
        installment_number=int(row["installment_number"] or 0),
        total_installments=int(row["total_installments"] or 0),
        purchase_date=row["purchase_date"] or "",
        operation_type="",
        updated_at=row["pluggy_updated_at"] or "",
    )


REVIEW_ACTIONS = {"attach", "insert", "dismiss"}


def resolve_review(conn, current_user_id, ledger_id, action, target_id=None):
    """O dono decide uma possivel duplicata: e o mesmo (attach), lancar separado, ignorar."""
    if action not in REVIEW_ACTIONS:
        raise ValidationError("Acao invalida.")
    row = conn.execute(
        "SELECT * FROM pluggy_transactions WHERE id = ? AND user_id = ?",
        (ledger_id, current_user_id),
    ).fetchone()
    if not row:
        raise LookupError("Transacao da Pluggy nao encontrada.")
    if row["state"] != REVIEW:
        raise ValidationError("Esta transacao ja foi decidida.")
    link = conn.execute(
        "SELECT * FROM pluggy_account_links WHERE user_id = ? AND pluggy_account_id = ?",
        (current_user_id, row["pluggy_account_id"]),
    ).fetchone()
    if not link and action != "dismiss":
        raise ValidationError("A conta da Pluggy desta transacao nao esta mais ligada.")

    tx = _ledger_transaction(row)
    context = SyncContext(conn, current_user_id, import_rules_for_matching(conn, current_user_id))
    if action == "dismiss":
        decision = {"state": DISMISSED, "reason": "owner"}
    elif action == "insert":
        if link["pluggy_account_type"] == "CREDIT":
            decision = import_card(context, link, tx, card_purchase_date(tx))
        else:
            decision = import_bank(context, link, tx)
    else:
        candidates = json.loads(row["candidates"] or "[]")
        chosen = next((item for item in candidates if item.get("id") == target_id), None)
        if not chosen:
            raise ValidationError("Escolha um dos lancamentos parecidos.")
        table = chosen.get("table")
        if table not in ("transactions", "cc_expenses"):
            raise ValidationError("Escolha um dos lancamentos parecidos.")
        target = conn.execute(
            f"SELECT id, external_id FROM {table} WHERE id = ? AND user_id = ?",
            (target_id, current_user_id),
        ).fetchone()
        if not target:
            raise ValidationError("Este lancamento nao existe mais.")
        if chosen.get("kind") in ("entry", "card_purchase"):
            if target["external_id"]:
                raise ValidationError("Este lancamento ja foi conferido com outra transacao do banco.")
            decision = attach(context, table, target_id, tx, link)
        else:
            # Transferencia, fatura, caixa de investimento, provento: o lancamento fica
            # intocado; so o livro sabe que esta transacao e ele.
            decision = {"state": ATTACHED, "target_table": table, "target_id": target_id, "reason": chosen.get("kind")}
    decision.setdefault("candidates", json.loads(row["candidates"]) if row["candidates"] else None)
    _write_ledger(context, row, tx, link or {"pluggy_account_id": row["pluggy_account_id"]}, decision)
    count_rule_hits(conn, current_user_id, context.rule_hits)
    return conn.execute(
        "SELECT * FROM pluggy_transactions WHERE id = ? AND user_id = ?",
        (ledger_id, current_user_id),
    ).fetchone()


# ---------------------------------------------------------------------------
# O caminho inverso: a Pluggy trouxe primeiro, o dono confirma depois
# ---------------------------------------------------------------------------

def claim_bank_transaction(conn, current_user_id, *, account_id, transaction_type, amount, date_text):
    """A linha da Pluggy, ainda sem confirmacao do dono, que este lancamento repetiria.

    Mesma conta, tipo e valor, data na folga; a mais proxima da data (empate: a
    mais antiga). None quando nao ha.
    """
    rows = conn.execute(
        """
        SELECT * FROM transactions
        WHERE user_id = ? AND source_type = ? AND client_id IS NULL
          AND account_id = ? AND type = ?
          AND CAST(ROUND(amount * 100) AS INTEGER) = ?
          AND date BETWEEN ? AND ?
        ORDER BY created_at
        """,
        (
            current_user_id, PLUGGY_SOURCE_TYPE, account_id, transaction_type, _cents(amount),
            _shift(date_text, -PLUGGY_MATCH_DAYS), _shift(date_text, PLUGGY_MATCH_DAYS),
        ),
    ).fetchall()
    if not rows:
        return None
    target = parse_iso_date(date_text)
    return min(rows, key=lambda row: abs((parse_iso_date(row["date"]) - target).days))


def claim_bank_purchase(conn, current_user_id, *, card_id, total_amount, installments, purchase_date):
    """As parcelas de uma compra da Pluggy, ainda sem confirmacao do dono, que esta repetiria.

    Mesmo cartao, mesmo numero de parcelas, mesmo total (um centavo de folga por
    parcela), data da compra na folga. [] quando nao ha.
    """
    groups = conn.execute(
        """
        SELECT source_id, MIN(purchase_date) AS purchase_date, COUNT(*) AS count,
               SUM(CAST(ROUND(amount * 100) AS INTEGER)) AS cents, MIN(created_at) AS created_at
        FROM cc_expenses
        WHERE user_id = ? AND card_id = ? AND source_type = ? AND client_id IS NULL
          AND purchase_date BETWEEN ? AND ?
        GROUP BY source_id
        HAVING COUNT(*) = ?
        ORDER BY created_at
        """,
        (
            current_user_id, card_id, PLUGGY_SOURCE_TYPE,
            _shift(purchase_date, -PLUGGY_MATCH_DAYS), _shift(purchase_date, PLUGGY_MATCH_DAYS),
            int(installments),
        ),
    ).fetchall()
    wanted = _cents(total_amount)
    target = parse_iso_date(purchase_date)
    matching = [group for group in groups if abs(int(group["cents"]) - wanted) <= int(installments)]
    if not matching:
        return []
    chosen = min(matching, key=lambda group: abs((parse_iso_date(group["purchase_date"]) - target).days))
    return conn.execute(
        """
        SELECT * FROM cc_expenses
        WHERE user_id = ? AND source_type = ? AND source_id = ?
        ORDER BY invoice_year ASC, invoice_month ASC
        """,
        (current_user_id, PLUGGY_SOURCE_TYPE, chosen["source_id"]),
    ).fetchall()


# ---------------------------------------------------------------------------
# Leitura para a tela
# ---------------------------------------------------------------------------

def _candidate_details(conn, current_user_id, candidates):
    details = []
    for item in candidates or []:
        table = item.get("table")
        if table == "transactions":
            row = conn.execute(
                """
                SELECT t.id, t.date, t.amount, t.description, t.category, t.type, t.source_type,
                       a.name AS account_name, d.name AS transfer_account_name
                FROM transactions t
                LEFT JOIN accounts a ON a.id = t.account_id AND a.user_id = t.user_id
                LEFT JOIN accounts d ON d.id = t.transfer_account_id AND d.user_id = t.user_id
                WHERE t.id = ? AND t.user_id = ?
                """,
                (item.get("id"), current_user_id),
            ).fetchone()
        elif table == "cc_expenses":
            row = conn.execute(
                """
                SELECT e.id, e.purchase_date AS date, e.amount, e.description, e.category,
                       e.installment_info, c.name AS card_name
                FROM cc_expenses e
                LEFT JOIN credit_cards c ON c.id = e.card_id AND c.user_id = e.user_id
                WHERE e.id = ? AND e.user_id = ?
                """,
                (item.get("id"), current_user_id),
            ).fetchone()
        else:
            row = None
        if row:
            details.append({**item, **row_to_dict(row)})
    return details


def serialize_ledger(conn, current_user_id, row, link_names=None):
    item = row_to_dict(row)
    item["candidates"] = _candidate_details(
        conn, current_user_id, json.loads(item["candidates"]) if item.get("candidates") else []
    )
    item["difference"] = json.loads(item["difference"]) if item.get("difference") else None
    item["account_name"] = (link_names or {}).get(item["pluggy_account_id"])
    return item


def link_names(conn, current_user_id):
    rows = conn.execute(
        """
        SELECT l.pluggy_account_id, COALESCE(a.name, c.name, l.name) AS name
        FROM pluggy_account_links l
        LEFT JOIN accounts a ON a.id = l.account_id AND a.user_id = l.user_id
        LEFT JOIN credit_cards c ON c.id = l.card_id AND c.user_id = l.user_id
        WHERE l.user_id = ?
        """,
        (current_user_id,),
    ).fetchall()
    return {row["pluggy_account_id"]: row["name"] for row in rows}


def review_items(conn, current_user_id):
    """O que espera o dono: as possiveis duplicatas e os conferidos com diferenca."""
    names = link_names(conn, current_user_id)
    review = conn.execute(
        """
        SELECT * FROM pluggy_transactions
        WHERE user_id = ? AND state = 'REVIEW'
        ORDER BY date DESC, created_at DESC
        """,
        (current_user_id,),
    ).fetchall()
    differences = conn.execute(
        """
        SELECT * FROM pluggy_transactions
        WHERE user_id = ? AND state = 'ATTACHED' AND difference IS NOT NULL
        ORDER BY date DESC, created_at DESC
        LIMIT 50
        """,
        (current_user_id,),
    ).fetchall()
    return {
        "review": [serialize_ledger(conn, current_user_id, row, names) for row in review],
        "differences": [serialize_ledger(conn, current_user_id, row, names) for row in differences],
    }


def state_counts(conn, current_user_id):
    rows = conn.execute(
        "SELECT state, COUNT(*) AS count FROM pluggy_transactions WHERE user_id = ? GROUP BY state",
        (current_user_id,),
    ).fetchall()
    return {row["state"]: row["count"] for row in rows}
