"""Open Finance: para onde vai cada conta da Pluggy (mapear, "nao usar", sugerir).

Uma conta da Pluggy so entra onde o dono mapeou: a conta bancaria numa conta do
app da mesma moeda, o cartao num cartao com credito, a conta de investimentos da
corretora na Corretora; ou e "nao usar".

Saiu de services/open_finance.py (2026-11-13), que continua reexportando todos
estes nomes.
"""

import re

from db import get_db, utc_timestamp
from services import (
    inbox,
    open_finance_auto,
    open_finance_inbox,
)
from services.import_rules import import_rules_for_matching
from services.open_finance_settings import (
    _today,
)
from validators import ValidationError


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
