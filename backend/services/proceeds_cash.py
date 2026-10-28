"""Proventos pagos entram na conta da carteira (dono, 2026-10-17).

Cada provento pago (data de pagamento ate hoje, valor liquido > 0) vira um
lancamento de receita na conta da carteira (`portfolio_cash_account_id()`, a
conta Corretora), com `source_type = INVESTMENT_PROCEED_SOURCE_TYPE` e
`source_id` = o id do provento — o mesmo formato idempotente das recorrencias
e do debito automatico. Materializado na leitura (`apply_paid_proceeds()`,
chamado junto com `apply_due_autopay()`), porque um provento agendado so vira
dinheiro no dia do pagamento.

So entram os pagos a partir do dia em que a conta virou a conta da carteira
(`portfolio_since()`): o saldo inicial da conta ja contem o que foi pago antes,
e os proventos automaticos trazem anos de historico. Um lancamento ja gravado
fica na conta em que nasceu (trocar a conta da carteira nao move o passado),
acompanha o provento (valor, data, ativo) e sai quando o provento some, fica
com valor zero ou volta a ser agendado. Sem conta da carteira nada novo e
gravado.
"""

from dates import parse_iso_date, parse_iso_datetime
from db import encode_metadata, parse_metadata_value
from money import rounded_money
from services.investments import PORTFOLIO_ACCOUNT_TYPE, portfolio_cash_account_id
from source_types import INVESTMENT_PROCEED_SOURCE_TYPE
from validators import safe_float
import services.invoices as invoices

# Chave do metadata da conta: o dia em que ela virou a conta da carteira.
PORTFOLIO_SINCE_KEY = "portfolio_since"
# O texto em transactions.category do provento pago (039): rotulo, sem categoria.
PROCEED_LABEL = "Provento"

PROCEED_LABELS = {"DIVIDEND": "Dividendo", "JCP": "JCP", "AMORTIZATION": "Amortização", "INTEREST": "Juros"}


def portfolio_since(account):
    """O primeiro dia de pagamento que entra na conta (AAAA-MM-DD)."""
    metadata = parse_metadata_value(account["metadata"]) or {}
    value = metadata.get(PORTFOLIO_SINCE_KEY) if isinstance(metadata, dict) else None
    parsed = parse_iso_date(value) if isinstance(value, str) else None
    if parsed:
        return parsed.date().isoformat()
    # Conta criada ja como Corretora: desde o dia (local, como local_today) em
    # que foi criada; created_at e UTC, e depois das 21h ja seria amanha.
    created = parse_iso_datetime(account["created_at"])
    return created.astimezone().date().isoformat() if created else ""


def mark_portfolio_since(metadata_value):
    """O metadata da conta que acabou de virar Corretora, com o dia de hoje."""
    metadata = parse_metadata_value(metadata_value)
    metadata = dict(metadata) if isinstance(metadata, dict) else {}
    metadata[PORTFOLIO_SINCE_KEY] = invoices.local_today().isoformat()
    return encode_metadata(metadata)


def portfolio_account_row(conn, current_user_id):
    account_id = portfolio_cash_account_id(conn, current_user_id)
    if not account_id:
        return None
    return conn.execute(
        "SELECT * FROM accounts WHERE id = ? AND user_id = ? AND type = ?",
        (account_id, current_user_id, PORTFOLIO_ACCOUNT_TYPE),
    ).fetchone()


def proceed_description(row):
    label = PROCEED_LABELS.get(row["proceeds_type"], "Provento")
    return f"{label}: {row['ticker'] or 'ativo'}"


def apply_paid_proceeds(conn, current_user_id):
    """Deixa os lancamentos de provento iguais aos proventos pagos. Idempotente."""
    today = invoices.local_today().isoformat()
    proceeds = {
        row["id"]: row
        for row in conn.execute(
            """
            SELECT p.id, p.proceeds_type, p.payment_date, p.net_amount, a.ticker
            FROM investment_proceeds p
            JOIN assets a ON a.id = p.asset_id AND a.user_id = p.user_id
            WHERE p.user_id = ?
            """,
            (current_user_id,),
        ).fetchall()
    }

    def is_paid(row):
        return bool(row) and rounded_money(safe_float(row["net_amount"])) > 0 and row["payment_date"][:10] <= today

    existing = conn.execute(
        """
        SELECT id, source_id, amount, date, description FROM transactions
        WHERE user_id = ? AND source_type = ?
        """,
        (current_user_id, INVESTMENT_PROCEED_SOURCE_TYPE),
    ).fetchall()
    written = set()
    for item in existing:
        proceed = proceeds.get(item["source_id"])
        if not is_paid(proceed):
            conn.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (item["id"], current_user_id))
            continue
        written.add(item["source_id"])
        values = (
            rounded_money(safe_float(proceed["net_amount"])),
            proceed["payment_date"][:10],
            proceed_description(proceed),
        )
        if (rounded_money(safe_float(item["amount"])), str(item["date"])[:10], item["description"]) != values:
            conn.execute(
                "UPDATE transactions SET amount = ?, date = ?, description = ? WHERE id = ? AND user_id = ?",
                (*values, item["id"], current_user_id),
            )

    account = portfolio_account_row(conn, current_user_id)
    if not account:
        return
    since = portfolio_since(account)
    for proceed_id, proceed in proceeds.items():
        if proceed_id in written or not is_paid(proceed) or proceed["payment_date"][:10] < since:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO transactions
            (id, user_id, account_id, amount, date, category, description, type, source_type, source_id, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'INCOME', ?, ?, ?)
            """,
            (
                f"proceed:{proceed_id}",
                current_user_id,
                account["id"],
                rounded_money(safe_float(proceed["net_amount"])),
                proceed["payment_date"][:10],
                PROCEED_LABEL,
                proceed_description(proceed),
                INVESTMENT_PROCEED_SOURCE_TYPE,
                proceed_id,
                encode_metadata({"proceed_id": proceed_id}),
            ),
        )
