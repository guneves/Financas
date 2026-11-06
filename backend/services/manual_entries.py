"""O freio do lancamento digitado no que a Pluggy alimenta.

Desde 2026-11-05 (dono) digita-se em tudo: o motor liga o lancamento digitado
ao movimento que o banco trouxer depois (free_candidates()), sem dobrar. Com
MANUAL_ONLY_OFF_PLUGGY ligado (env, desligado por padrao) volta a regra de
2026-10-31: conta e cartao conectados recusam o digitado, a importacao de
extrato tambem, e uma transferencia precisa de uma ponta fora da Pluggy.

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


# Investimentos so pela Pluggy (Fase 3):
# a Corretora alimentada pela Pluggy recebe as operacoes, os resgates e os
# proventos da corretora sozinha; digitar ali seria a mesma operacao em dobro.
# So as rotas HTTP chamam isto; os gravadores do servidor (proceeds_sync,
# apply_paid_proceeds(), open_finance_investments) nunca.
BROKER_FED_MESSAGE = "A Pluggy traz as operações da corretora."


def require_manual_investment_cash(conn, current_user_id, account_id, completes_held=False):
    """Recusa a operacao digitada cujo caixa e uma conta da Pluggy (a Corretora),
    a nao ser que ela complete uma linha HELD da Pluggy (o "Lancar")."""
    if completes_held or not account_id or not MANUAL_ONLY_OFF_PLUGGY:
        return
    if account_id in bank_fed_account_ids(conn, current_user_id):
        raise ValidationError(BROKER_FED_MESSAGE)
