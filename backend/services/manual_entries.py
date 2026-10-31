"""O que a Pluggy alimenta nao se digita (dono, 2026-10-31).

Conta e cartao conectados sao atualizados so pela Pluggy: um lancamento digitado
neles viraria o mesmo movimento em dobro quando o banco o trouxesse. Digita-se so
no que nao tem Pluggy, a Flash; a mesma regra vale para importar extrato. Uma
transferencia pode ser digitada quando uma das pontas nao tem Pluggy.

`"pluggy": true` em GET /api/accounts e /api/credit-cards e como as telas sabem.
"""

from config import MANUAL_ONLY_OFF_PLUGGY
from validators import ValidationError

BANK_FED_MESSAGE = "Esta conta e atualizada pela Pluggy. Lancamento manual so na Flash."
BANK_FED_CARD_MESSAGE = "Este cartao e atualizado pela Pluggy. Lancamento manual so na Flash."


def _bank_fed(conn, current_user_id, column):
    rows = conn.execute(
        f"""
        SELECT o.{column} AS target FROM open_finance_accounts o
        JOIN open_finance_items i ON i.id = o.of_item_id AND i.user_id = o.user_id
        WHERE o.user_id = ? AND o.{column} IS NOT NULL AND o.ignored_at IS NULL AND i.archived_at IS NULL
        """,
        (current_user_id,),
    ).fetchall()
    return {row["target"] for row in rows}


def bank_fed_account_ids(conn, current_user_id):
    return _bank_fed(conn, current_user_id, "account_id")


def bank_fed_card_ids(conn, current_user_id):
    return _bank_fed(conn, current_user_id, "card_id")


def require_manual_account(conn, current_user_id, account_id):
    if MANUAL_ONLY_OFF_PLUGGY and account_id in bank_fed_account_ids(conn, current_user_id):
        raise ValidationError(BANK_FED_MESSAGE)


def require_manual_transfer(conn, current_user_id, origin_id, destination_id):
    fed = bank_fed_account_ids(conn, current_user_id)
    if MANUAL_ONLY_OFF_PLUGGY and origin_id in fed and destination_id in fed:
        raise ValidationError(BANK_FED_MESSAGE)


def require_manual_card(conn, current_user_id, card_id):
    if MANUAL_ONLY_OFF_PLUGGY and card_id in bank_fed_card_ids(conn, current_user_id):
        raise ValidationError(BANK_FED_CARD_MESSAGE)
