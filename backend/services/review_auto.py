"""Auto-confirmar o Revisar (automation-prompt 1.2, dono 2026-11-18: "tudo
automatico").

Uma linha a revisar (`needs_review = 1`) datada ha mais de N dias
(`review_auto_days` em user_settings; padrao REVIEW_AUTO_DAYS_DEFAULT, 3;
0 = desligado, maximo 30) sai
da revisao sozinha, com a categoria que tem. Revisar so muda a marca: o valor,
a data, a categoria e o "intocado" (o snapshot) ficam como estao, entao o banco
continua corrigindo depois como antes.

Numa conta ou cartao que a Pluggy alimenta, a linha antes espera o banco, para
a categoria da Pluggy (1.1) entrar primeiro: sai quando uma transacao da Pluggy
ja a reclama, ou, sem isso, BANK_WAIT_MAX_DAYS depois do prazo (conexao morta
nao segura nada para sempre).

A linha que o dono editou tambem sai: a edicao ja foi a decisao dele.
Cada uma fica no registro (auto_decisions, `auto_confirm`) com "Desfazer", que a
devolve ao Revisar para sempre (a regra nao a pega de novo).
"""

from datetime import timedelta

from config import REVIEW_AUTO_DAYS_DEFAULT
from dates import local_today
from services import auto_decisions, inbox, review
from services.manual_entries import bank_fed_account_ids, bank_fed_card_ids
from services.open_finance_auto import BANK_WAIT_MAX_DAYS

SETTING = "review_auto_days"
MAX_DAYS = 30


def days(conn, current_user_id):
    value = inbox.setting_value(conn, current_user_id, SETTING)
    try:
        number = int(value)
    except (TypeError, ValueError):
        return REVIEW_AUTO_DAYS_DEFAULT
    return min(max(number, 0), MAX_DAYS)


def set_days(conn, current_user_id, number):
    inbox.save_setting(conn, current_user_id, SETTING, str(int(number)))


def _claimed_by_pluggy(conn, current_user_id, table, target_ids):
    marks = ", ".join("?" for _ in target_ids)
    return conn.execute(
        f"""
        SELECT 1 FROM open_finance_transactions
        WHERE user_id = ? AND target_table = ? AND target_id IN ({marks}) AND role <> 'REMOVED'
        LIMIT 1
        """,
        (current_user_id, table, *target_ids),
    ).fetchone() is not None


def _due_transactions(conn, current_user_id, cutoff):
    return conn.execute(
        """
        SELECT id, date, account_id, transfer_account_id, source_type FROM transactions
        WHERE user_id = ? AND needs_review = 1 AND date <= ?
        ORDER BY date, id
        """,
        (current_user_id, cutoff),
    ).fetchall()


def _due_purchases(conn, current_user_id, cutoff):
    return conn.execute(
        """
        SELECT e.client_id, MIN(e.purchase_date) AS date, MIN(e.card_id) AS card_id,
               (SELECT f.id FROM cc_expenses f WHERE f.user_id = e.user_id AND f.client_id = e.client_id
                ORDER BY f.invoice_year, f.invoice_month, f.id LIMIT 1) AS id
        FROM cc_expenses e
        WHERE e.user_id = ? AND e.needs_review = 1
        GROUP BY e.client_id
        HAVING MIN(e.purchase_date) <= ?
        ORDER BY date, client_id
        """,
        (current_user_id, cutoff),
    ).fetchall()


def confirm_due(conn, current_user_id, today=None):
    """Tira da revisao o que passou do prazo. Devolve quantas saíram."""
    window = days(conn, current_user_id)
    if window <= 0:
        return 0
    today = today or local_today()
    cutoff = (today - timedelta(days=window)).isoformat()
    hard = (today - timedelta(days=window + BANK_WAIT_MAX_DAYS)).isoformat()
    fed_accounts = bank_fed_account_ids(conn, current_user_id)
    fed_cards = bank_fed_card_ids(conn, current_user_id)
    confirmed = 0
    for row in _due_transactions(conn, current_user_id, cutoff):
        fed = row["account_id"] in fed_accounts or row["transfer_account_id"] in fed_accounts
        if fed and row["date"] > hard and row["source_type"] != "OPEN_FINANCE" and not _claimed_by_pluggy(
            conn, current_user_id, "transactions", [row["id"]],
        ):
            continue
        confirmed += _confirm(conn, current_user_id, "transactions", row["id"], row["date"])
    for row in _due_purchases(conn, current_user_id, cutoff):
        if row["card_id"] in fed_cards and row["date"] > hard and not str(row["client_id"]).startswith("pluggy:"):
            ids = [entry["id"] for entry in conn.execute(
                "SELECT id FROM cc_expenses WHERE user_id = ? AND client_id = ?", (current_user_id, row["client_id"]),
            ).fetchall()]
            if not _claimed_by_pluggy(conn, current_user_id, "cc_expenses", ids):
                continue
        confirmed += _confirm(conn, current_user_id, "cc_expenses", row["id"], row["date"])
    return confirmed


def _confirm(conn, current_user_id, table, target_id, date):
    # Uma decisao desfeita (esta ou o palpite que gravou a linha): o dono quis
    # a linha no Revisar, e ela fica la.
    if auto_decisions.was_undone(conn, current_user_id, None, table, target_id):
        return 0
    category = review.current_category(conn, current_user_id, table, target_id)
    review.clear(conn, current_user_id, table, target_id)
    auto_decisions.record(
        conn, current_user_id, auto_decisions.AUTO_CONFIRM, table, target_id,
        {"date": date, "category": list(category) if category else None},
    )
    return 1
