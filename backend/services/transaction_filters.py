"""Extrato: os filtros de GET /api/transactions em SQL, e o cartao de uma compra no debito.

Saiu de routes/transactions.py (2026-11-13): nada aqui usa o Flask. A rota continua importando
todos estes nomes.
"""

import sqlite3


from db import get_db, serialize_transaction
from money import parse_money, rounded_money
from export_csv import ColumnError
from responses import export_response, read_export_options
from services.accounts import (
    CLIENT_ID_OTHER_KIND_MESSAGE,
    fetch_account,
    fetch_transaction_by_client_id,
    keep_or_require_account,
    resolve_account_id,
    resolve_category,
    transfer_amount_for,
)
from services import auto_record, entries, manual_entries
from services.attachments import remove_attachment_files
from services.inbox import TRANSFER_CATEGORY
from services.inbox_decisions import absorb_created, absorb_other_side
from services.invoices import apply_due_autopay
from services.proceeds_cash import apply_paid_proceeds
from services.transaction_pages import fetch_page, parse_page_args
from services.twins import transaction_twin_ids
from services.sharing import (
    check_split_fits,
    has_share_fields,
    parse_share,
)
from source_types import (
    INVESTMENT_CASH_SOURCE_TYPE,
    INVESTMENT_PROCEED_SOURCE_TYPE,
    INVOICE_PAYMENT_LOCKED_MESSAGE,
    INVOICE_PAYMENT_SOURCE_TYPES,
)
from validators import (
    ValidationError,
    optional_client_id,
    optional_date,
    optional_string,
    parse_json_body,
    parse_optional_number,
    require_choice,
    require_date,
    validation_error,
)


ALLOWED_TRANSACTION_TYPES = {"INCOME", "EXPENSE", "TRANSFER"}


def escape_like(value):
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def transaction_filter_clause(conn, current_user_id, args):
    """Monta o WHERE dos filtros do extrato. Todo filtro e opcional.

    - from / to: periodo inclusivo (AAAA-MM-DD)
    - type: INCOME | EXPENSE | TRANSFER
    - account_id: a conta de origem ou, numa transferencia, a de destino
    - category_id: a categoria e as subcategorias dela; lancamentos que so
      carregam o nome (texto livre ou anteriores a 008) casam pelo nome
    - q: texto livre em descricao e categoria
    - min_amount / max_amount: faixa de valor, inclusiva
    - review=1: so o gravado sozinho que espera a revisao (045)
    """
    clauses = ["user_id = ?"]
    params = [current_user_id]

    date_from = optional_date(args, "from", "Data inicial")
    date_to = optional_date(args, "to", "Data final")
    if date_from and date_to and date_from > date_to:
        raise ValidationError("Data inicial deve ser anterior ou igual a data final.")
    if date_from:
        clauses.append("date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("date <= ?")
        params.append(date_to)

    if args.get("type"):
        transaction_type = require_choice(args, "type", "Tipo", ALLOWED_TRANSACTION_TYPES)
        clauses.append("type = ?")
        params.append(transaction_type)

    account_id = str(args.get("account_id") or "").strip()
    if account_id:
        clauses.append("(account_id = ? OR transfer_account_id = ?)")
        params.extend([account_id, account_id])
    else:
        # O Extrato e em reais: o que a conta global (outra moeda) movimenta
        # sozinha fica na tela dela; a transferencia de reais para ela fica.
        clauses.append(
            "NOT EXISTS (SELECT 1 FROM accounts fa WHERE fa.id = transactions.account_id"
            " AND fa.user_id = transactions.user_id AND COALESCE(fa.currency, 'BRL') <> 'BRL')"
        )

    category_id = str(args.get("category_id") or "").strip()
    if category_id:
        category_rows = conn.execute(
            """
            SELECT id, name FROM categories
            WHERE user_id = ? AND (id = ? OR parent_id = ?)
            """,
            (current_user_id, category_id, category_id),
        ).fetchall()
        if not category_rows:
            raise ValidationError("Categoria nao encontrada.")
        ids = [row["id"] for row in category_rows]
        names = [row["name"] for row in category_rows]
        id_marks = ", ".join("?" for _ in ids)
        name_marks = ", ".join("?" for _ in names)
        clauses.append(
            f"(category_id IN ({id_marks}) OR (category_id IS NULL AND category IN ({name_marks})))"
        )
        params.extend(ids + names)

    text = str(args.get("q") or "").strip()
    if len(text) > 100:
        raise ValidationError("Busca deve ter no maximo 100 caracteres.")
    if text:
        pattern = f"%{escape_like(text)}%"
        clauses.append(
            "(description LIKE ? ESCAPE '\\' OR category LIKE ? ESCAPE '\\')"
        )
        params.extend([pattern, pattern])

    min_amount = parse_optional_number(args, "min_amount", "Valor minimo", minimum=0)
    max_amount = parse_optional_number(args, "max_amount", "Valor maximo", minimum=0)
    if min_amount is not None and max_amount is not None and min_amount > max_amount:
        raise ValidationError("Valor minimo deve ser menor ou igual ao valor maximo.")
    if min_amount is not None:
        clauses.append("amount >= ?")
        params.append(rounded_money(min_amount))
    if max_amount is not None:
        clauses.append("amount <= ?")
        params.append(rounded_money(max_amount))

    if str(args.get("review") or "") in ("1", "true"):
        clauses.append("needs_review = 1")

    return " AND ".join(clauses), params


def debit_card_owns(conn, current_user_id, card_id, account_id):
    """O cartao debita desta conta (041)?"""
    return bool(conn.execute(
        "SELECT 1 FROM credit_cards WHERE id = ? AND user_id = ? AND debit_account_id = ?",
        (card_id, current_user_id, account_id),
    ).fetchone())


def debit_card_id(conn, current_user_id, payload, transaction_type, account_id):
    """`card_id` de uma compra no debito (049): uma despesa na conta do cartao.
    Ausente ou vazio, None."""
    card_id = str(payload.get("card_id") or "").strip()
    if not card_id:
        return None
    card = conn.execute(
        "SELECT * FROM credit_cards WHERE id = ? AND user_id = ?", (card_id, current_user_id),
    ).fetchone()
    if not card:
        raise ValidationError("Cartao nao encontrado.")
    if card["archived_at"]:
        raise ValidationError(f"O cartao {card['name']} foi excluido; ele nao recebe lancamentos novos.")
    if transaction_type != "EXPENSE" or not card["debit_account_id"] or card["debit_account_id"] != account_id:
        raise ValidationError("A compra no debito e uma despesa na conta do cartao.")
    return card_id


def with_twins(conn, current_user_id, rows):
    """As linhas serializadas, com `twin` (services/twins.py: "2x igual")."""
    twins = transaction_twin_ids(conn, current_user_id, rows)
    items = []
    for row in rows:
        item = serialize_transaction(row)
        item["twin"] = row["id"] in twins
        items.append(item)
    return items


def account_names_map(conn, current_user_id):
    rows = conn.execute(
        "SELECT id, name FROM accounts WHERE user_id = ?",
        (current_user_id,),
    ).fetchall()
    return {row["id"]: row["name"] for row in rows}
