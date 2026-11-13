"""Cartoes: ler as funcoes do cartao (credito/debito), as contas de debito e de debito automatico, e achar uma compra pelo client_id.

Saiu de routes/cards.py (2026-11-13): nada aqui usa o Flask. A rota continua importando
todos estes nomes.
"""



from services.accounts import (
    fetch_account,
    require_account,
    resolve_account_id,
)
from source_types import INVOICE_PAYMENT_SOURCE_TYPES
from validators import (
    ValidationError,
)


def fetch_purchase_by_client_id(conn, current_user_id, client_id):
    """As parcelas que um envio com este client_id ja criou (024), na ordem das faturas."""
    if not client_id:
        return []
    return conn.execute(
        """
        SELECT * FROM cc_expenses
        WHERE user_id = ? AND client_id = ?
        ORDER BY invoice_year ASC, invoice_month ASC
        """,
        (current_user_id, client_id),
    ).fetchall()


NO_FUNCTION_MESSAGE = "Escolha ao menos uma funcao do cartao: credito ou debito."


DEBIT_ONLY_AUTOPAY_MESSAGE = "Um cartao so de debito nao tem fatura nem debito automatico."


DEBIT_BROKERAGE_MESSAGE = "A conta da corretora fica em Investimentos: escolha uma conta do banco para o debito."


FLAG_VALUES = {True: True, False: False, 1: True, 0: False, "1": True, "0": False, "true": True, "false": False}


def parse_card_flag(payload, key, label, default):
    raw = payload.get(key)
    if raw is None:
        return default
    if isinstance(raw, str):
        raw = raw.strip().lower()
    # Lista ou objeto nao e flag (e nem entra num dict: era um 500).
    value = FLAG_VALUES.get(raw) if isinstance(raw, (str, int, float)) else None
    if value is None:
        raise ValidationError(f"{label} invalida.")
    return value


def resolve_debit_account(conn, current_user_id, payload, current_id=None):
    """A conta da funcao debito; vazio/None tira o debito. Numa edicao, a conta
    que o cartao ja tem fica mesmo arquivada; outra tem que ser ativa."""
    raw = payload.get("debit_account_id")
    if raw in (None, ""):
        return None
    if current_id and str(raw) == current_id:
        return current_id
    account = require_account(conn, current_user_id, str(raw), "Conta do debito")
    if account["type"] == "BROKERAGE":
        # A Corretora e da carteira (Investimentos): nenhuma compra sai dela.
        raise ValidationError(DEBIT_BROKERAGE_MESSAGE)
    return account["id"]


def check_card_functions(credit_enabled, debit_account_id, autopay_account_id):
    if not credit_enabled and not debit_account_id:
        raise ValidationError(NO_FUNCTION_MESSAGE)
    if not credit_enabled and autopay_account_id:
        raise ValidationError(DEBIT_ONLY_AUTOPAY_MESSAGE)


def resolve_autopay_account(conn, current_user_id, payload):
    """Conta do debito automatico no payload; vazio/None desliga o debito."""
    raw = payload.get("autopay_account_id")
    if raw in (None, ""):
        return None
    return require_account(conn, current_user_id, str(raw), "Conta do debito automatico")["id"]


CARD_NAME_TAKEN_MESSAGE = "Ja existe um cartao com este nome."


# O excluido continua com o nome: as compras antigas dele o mostram.
ARCHIVED_CARD_NAME_MESSAGE = "Um cartao excluido ainda usa este nome no historico. Escolha outro nome."


def card_name_conflict_message(conn, current_user_id, name):
    archived = conn.execute(
        "SELECT 1 FROM credit_cards WHERE user_id = ? AND name = ? AND archived_at IS NOT NULL",
        (current_user_id, name),
    ).fetchone()
    return ARCHIVED_CARD_NAME_MESSAGE if archived else CARD_NAME_TAKEN_MESSAGE


def card_payment_count(conn, current_user_id, card_id):
    """Pagamentos de fatura deste cartao no Extrato (source_id '<cartao>:...')."""
    placeholders = ",".join("?" for _ in INVOICE_PAYMENT_SOURCE_TYPES)
    prefix = f"{card_id}:"
    return conn.execute(
        f"""
        SELECT COUNT(*) FROM transactions
        WHERE user_id = ? AND source_type IN ({placeholders})
          AND substr(source_id, 1, ?) = ?
        """,
        (current_user_id, *sorted(INVOICE_PAYMENT_SOURCE_TYPES), len(prefix), prefix),
    ).fetchone()[0]


def invoice_payment_account_id(conn, current_user_id, card, payload):
    """Conta do pagamento manual: a informada, a do debito automatico ou a padrao."""
    if payload.get("account_id") in (None, "") and card["autopay_account_id"]:
        autopay_account = fetch_account(conn, current_user_id, card["autopay_account_id"])
        if autopay_account and not autopay_account["archived_at"]:
            return autopay_account["id"]
    return resolve_account_id(conn, current_user_id, payload)
