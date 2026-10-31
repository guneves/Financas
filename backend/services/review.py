"""Revisar (045, dono 2026-10-27): o unico trabalho manual do dono.

A notificacao e a transacao da Pluggy viram lancamento sozinhas
(services/auto_record.py, services/open_finance_auto.py) com
`needs_review = 1`. Revisar e dizer duas coisas: e meu (nao e fraude nem erro)
e a categoria e esta. Feito, o lancamento perde a marca. Nada mais muda: valor,
conta e data se corrigem pela edicao de sempre.

Uma receita pode ser **repasse** (dono, 2026-10-31): dinheiro de outra pessoa para
pagar algo dela. Fica no saldo, fora da renda (`share_mode = 'OTHERS'`, ja acertado).

Uma compra no cartao e o client_id (035): todas as parcelas sao revisadas e
recategorizadas juntas. Uma transferencia nao tem categoria a escolher.
"""

from db import utc_timestamp
from services.accounts import resolve_category
from services.sharing import PERSON_MAX_LENGTH
from validators import ValidationError

TABLES = ("transactions", "cc_expenses")
MAX_ITEMS = 200
# A conta global (outra moeda) revisa na tela dela (GET /api/transactions?
# account_id=<ela>&review=1): a fila e o contador daqui sao em reais.
IN_REAIS = (
    "NOT EXISTS (SELECT 1 FROM accounts a WHERE a.id = t.account_id AND a.user_id = t.user_id"
    " AND COALESCE(a.currency, 'BRL') <> 'BRL')"
)


def mark_for_review(conn, current_user_id, table, target_id):
    """O lancamento (na compra, todas as parcelas) passa a esperar a revisao."""
    if table == "transactions":
        conn.execute(
            "UPDATE transactions SET needs_review = 1 WHERE id = ? AND user_id = ?", (target_id, current_user_id),
        )
    elif table == "cc_expenses":
        conn.execute(
            """
            UPDATE cc_expenses SET needs_review = 1
            WHERE user_id = ? AND client_id = (SELECT client_id FROM cc_expenses WHERE id = ? AND user_id = ?)
            """,
            (current_user_id, target_id, current_user_id),
        )


def awaiting(conn, current_user_id, table, target_id):
    """O lancamento ainda esta a revisar."""
    if table not in TABLES or not target_id:
        return False
    row = conn.execute(
        f"SELECT needs_review FROM {table} WHERE id = ? AND user_id = ?", (target_id, current_user_id),
    ).fetchone()
    return bool(row) and bool(row["needs_review"])


def _transaction_items(conn, current_user_id):
    rows = conn.execute(
        """
        SELECT t.id, t.date, t.occurred_at, t.amount, t.type, t.description, t.category, t.category_id,
               t.account_id, t.transfer_account_id, t.source_type, t.created_at,
               a.name AS account_name, d.name AS transfer_account_name
        FROM transactions t
        LEFT JOIN accounts a ON a.id = t.account_id AND a.user_id = t.user_id
        LEFT JOIN accounts d ON d.id = t.transfer_account_id AND d.user_id = t.user_id
        WHERE t.user_id = ? AND t.needs_review = 1 AND COALESCE(a.currency, 'BRL') = 'BRL'
        """,
        (current_user_id,),
    ).fetchall()
    return [{
        "table": "transactions",
        "id": row["id"],
        "date": row["date"],
        "occurred_at": row["occurred_at"],
        "amount": row["amount"],
        "type": row["type"],
        "description": row["description"],
        "category": row["category"],
        "category_id": row["category_id"],
        "account_id": row["account_id"],
        "account_name": row["account_name"],
        "transfer_account_id": row["transfer_account_id"],
        "transfer_account_name": row["transfer_account_name"],
        "source_type": row["source_type"],
        "created_at": row["created_at"],
    } for row in rows]


def _card_items(conn, current_user_id):
    """Uma linha por compra (client_id): a primeira parcela, com o total."""
    rows = conn.execute(
        """
        SELECT e.client_id, MIN(e.purchase_date) AS date, MIN(e.occurred_at) AS occurred_at,
               SUM(e.amount) AS amount, COUNT(*) AS installments, MIN(e.created_at) AS created_at,
               (SELECT f.id FROM cc_expenses f WHERE f.user_id = e.user_id AND f.client_id = e.client_id
                ORDER BY f.invoice_year, f.invoice_month, f.id LIMIT 1) AS id
        FROM cc_expenses e
        WHERE e.user_id = ? AND e.needs_review = 1
        GROUP BY e.client_id
        """,
        (current_user_id,),
    ).fetchall()
    items = []
    for row in rows:
        first = conn.execute(
            """
            SELECT e.kind, e.description, e.category, e.category_id, e.card_id, c.name AS card_name
            FROM cc_expenses e LEFT JOIN credit_cards c ON c.id = e.card_id AND c.user_id = e.user_id
            WHERE e.id = ? AND e.user_id = ?
            """,
            (row["id"], current_user_id),
        ).fetchone()
        items.append({
            "table": "cc_expenses",
            "id": row["id"],
            "date": row["date"],
            "occurred_at": row["occurred_at"],
            "amount": row["amount"],
            "type": "REFUND" if first["kind"] == "REFUND" else "CARD",
            "description": first["description"],
            "category": first["category"],
            "category_id": first["category_id"],
            "card_id": first["card_id"],
            "card_name": first["card_name"],
            "installments": row["installments"],
            "created_at": row["created_at"],
        })
    return items


def queue(conn, current_user_id):
    """O que espera a revisao, do mais novo para o mais antigo."""
    items = _transaction_items(conn, current_user_id) + _card_items(conn, current_user_id)
    items.sort(key=lambda item: (item["date"] or "", item["created_at"] or "", item["id"]), reverse=True)
    return items


def count(conn, current_user_id):
    transactions = conn.execute(
        f"SELECT COUNT(*) FROM transactions t WHERE t.user_id = ? AND t.needs_review = 1 AND {IN_REAIS}",
        (current_user_id,),
    ).fetchone()[0]
    purchases = conn.execute(
        "SELECT COUNT(DISTINCT client_id) FROM cc_expenses WHERE user_id = ? AND needs_review = 1",
        (current_user_id,),
    ).fetchone()[0]
    return transactions + purchases


def _parse(raw):
    if not isinstance(raw, dict):
        raise ValidationError("Cada item da revisao e um objeto.")
    table = raw.get("table")
    if table not in TABLES:
        raise ValidationError("Tabela invalida.")
    target_id = raw.get("id")
    if not isinstance(target_id, str) or not target_id.strip():
        raise ValidationError("Informe o id do lancamento.")
    category_id = raw.get("category_id")
    if category_id is not None and not isinstance(category_id, str):
        raise ValidationError("Categoria invalida.")
    if not isinstance(raw.get("repasse", False), bool):
        raise ValidationError("Repasse invalido.")
    return table, target_id.strip(), (category_id or "").strip() or None


def mark_repasse(conn, current_user_id, table, row, person):
    if table != "transactions" or row["type"] != "INCOME":
        raise ValidationError("So uma receita pode ser repasse.")
    conn.execute(
        """
        UPDATE transactions SET share_mode = 'OTHERS', share_others_amount = NULL, share_person = ?, share_settled_at = ?
        WHERE id = ? AND user_id = ?
        """,
        (str(person or "Outra pessoa").strip()[:PERSON_MAX_LENGTH], utc_timestamp(), row["id"], current_user_id),
    )


def review_items(conn, current_user_id, raw_items):
    """Confirma cada {table, id, category_id?, repasse?, person?}: e do dono e, com
    category_id, a categoria passa a ser essa. Tudo ou nada; devolve quantos."""
    if not isinstance(raw_items, list) or not raw_items:
        raise ValidationError("Envie a lista de lancamentos revisados.")
    if len(raw_items) > MAX_ITEMS:
        raise ValidationError(f"No maximo {MAX_ITEMS} lancamentos por vez.")
    reviewed = 0
    for raw in raw_items:
        table, target_id, category_id = _parse(raw)
        row = conn.execute(
            f"SELECT * FROM {table} WHERE id = ? AND user_id = ?", (target_id, current_user_id),
        ).fetchone()
        if not row:
            raise LookupError("Lancamento nao encontrado.")
        if raw.get("repasse"):
            mark_repasse(conn, current_user_id, table, row, raw.get("person"))
        category = None
        if category_id and not (table == "transactions" and row["type"] == "TRANSFER"):
            category = resolve_category(conn, current_user_id, {"category_id": category_id})
        if table == "transactions":
            if category:
                conn.execute(
                    "UPDATE transactions SET needs_review = 0, category = ?, category_id = ? WHERE id = ? AND user_id = ?",
                    (*category, target_id, current_user_id),
                )
            else:
                conn.execute(
                    "UPDATE transactions SET needs_review = 0 WHERE id = ? AND user_id = ?", (target_id, current_user_id),
                )
        else:
            if category:
                conn.execute(
                    "UPDATE cc_expenses SET needs_review = 0, category = ?, category_id = ? WHERE user_id = ? AND client_id = ?",
                    (*category, current_user_id, row["client_id"]),
                )
            else:
                conn.execute(
                    "UPDATE cc_expenses SET needs_review = 0 WHERE user_id = ? AND client_id = ?",
                    (current_user_id, row["client_id"]),
                )
        reviewed += 1
    return reviewed
