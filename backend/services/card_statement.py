"""As compras no cartao no Extrato (045, dono 2026-10-27).

O Extrato mostra a vida financeira numa linha do tempo so: os lancamentos das
contas e, entre eles, cada compra no cartao no dia em que foi feita. Uma compra
e o client_id (035): uma linha com o total e o numero de parcelas, nunca uma
linha por parcela. Um estorno (033) e uma linha de credito.

A compra nao mexe em saldo de conta (quem mexe e o pagamento da fatura), entao
nao entra no total do dia nem nos totais do filtro do Extrato: so aparece.

Os filtros sao os do extrato (GET /api/transactions): from/to na data da
compra, q na descricao e na categoria, category_id com as subcategorias,
min/max sobre o total, type (EXPENSE = compras, INCOME = estornos, TRANSFER =
nada) e account_id (uma compra nao e de conta nenhuma: com conta, nada).
`review=1` deixa so o que espera a revisao.
"""

from money import rounded_money
from validators import ValidationError, optional_date, parse_optional_number, require_choice

TYPES = ("INCOME", "EXPENSE", "TRANSFER")
MAX_QUERY = 100


def _category_ids(conn, current_user_id, category_id):
    rows = conn.execute(
        "SELECT id, name FROM categories WHERE user_id = ? AND (id = ? OR parent_id = ?)",
        (current_user_id, category_id, category_id),
    ).fetchall()
    if not rows:
        raise ValidationError("Categoria nao encontrada.")
    return {row["id"] for row in rows}, {row["name"] for row in rows}


def parse_filters(conn, current_user_id, args):
    date_from = optional_date(args, "from", "Data inicial")
    date_to = optional_date(args, "to", "Data final")
    if date_from and date_to and date_from > date_to:
        raise ValidationError("Data inicial deve ser anterior ou igual a data final.")
    kind = require_choice(args, "type", "Tipo", TYPES) if args.get("type") else None
    text = str(args.get("q") or "").strip()
    if len(text) > MAX_QUERY:
        raise ValidationError(f"Busca deve ter no maximo {MAX_QUERY} caracteres.")
    min_amount = parse_optional_number(args, "min_amount", "Valor minimo", minimum=0)
    max_amount = parse_optional_number(args, "max_amount", "Valor maximo", minimum=0)
    if min_amount is not None and max_amount is not None and min_amount > max_amount:
        raise ValidationError("Valor minimo deve ser menor ou igual ao valor maximo.")
    category_id = str(args.get("category_id") or "").strip()
    return {
        "from": date_from,
        "to": date_to,
        "type": kind,
        "q": text.casefold(),
        "min": rounded_money(min_amount) if min_amount is not None else None,
        "max": rounded_money(max_amount) if max_amount is not None else None,
        "categories": _category_ids(conn, current_user_id, category_id) if category_id else None,
        "account_id": str(args.get("account_id") or "").strip(),
        "card_id": str(args.get("card_id") or "").strip(),
        "review": str(args.get("review") or "") in ("1", "true"),
    }


def _purchases(conn, current_user_id, card_id=None):
    """Uma entrada por compra, na ordem das parcelas: a primeira manda."""
    sql = """
        SELECT e.*, c.name AS card_name FROM cc_expenses e
        LEFT JOIN credit_cards c ON c.id = e.card_id AND c.user_id = e.user_id
        WHERE e.user_id = ?
    """
    params = [current_user_id]
    if card_id:
        sql += " AND e.card_id = ?"
        params.append(card_id)
    sql += " ORDER BY e.invoice_year, e.invoice_month, e.id"
    purchases = {}
    for row in conn.execute(sql, params).fetchall():
        key = row["client_id"] or f"legacy:{row['id']}"
        entry = purchases.get(key)
        if entry is None:
            purchases[key] = {
                "kind": "card",
                "id": row["id"],
                "client_id": key,
                "date": row["purchase_date"],
                "occurred_at": row["occurred_at"],
                "type": "REFUND" if row["kind"] == "REFUND" else "CARD",
                "amount": 0.0,
                "description": row["description"],
                "category": row["category"],
                "category_id": row["category_id"],
                "card_id": row["card_id"],
                "card_name": row["card_name"],
                "installments": 0,
                "paid_installments": 0,
                "needs_review": 0,
                "share_mode": row["share_mode"],
                "share_others_amount": row["share_others_amount"],
                "share_person": row["share_person"],
                "created_at": row["created_at"],
            }
            entry = purchases[key]
        entry["amount"] += float(row["amount"] or 0)
        entry["installments"] += 1
        entry["paid_installments"] += 1 if row["status"] == "PAID" else 0
        entry["needs_review"] = max(entry["needs_review"], int(row["needs_review"] or 0))
    for entry in purchases.values():
        entry["amount"] = rounded_money(entry["amount"])
    return list(purchases.values())


def _matches(entry, filters):
    if filters["account_id"] or filters["type"] == "TRANSFER":
        return False
    if filters["type"] == "EXPENSE" and entry["type"] != "CARD":
        return False
    if filters["type"] == "INCOME" and entry["type"] != "REFUND":
        return False
    if filters["from"] and entry["date"] < filters["from"]:
        return False
    if filters["to"] and entry["date"] > filters["to"]:
        return False
    if filters["min"] is not None and entry["amount"] < filters["min"]:
        return False
    if filters["max"] is not None and entry["amount"] > filters["max"]:
        return False
    if filters["review"] and not entry["needs_review"]:
        return False
    if filters["q"] and not any(
        filters["q"] in str(entry[field] or "").casefold() for field in ("description", "category")
    ):
        return False
    if filters["categories"]:
        ids, names = filters["categories"]
        if entry["category_id"] not in ids and not (entry["category_id"] is None and entry["category"] in names):
            return False
    return True


def card_purchases(conn, current_user_id, args):
    """As compras (e estornos) que atendem aos filtros, da mais nova para a
    mais antiga."""
    filters = parse_filters(conn, current_user_id, args)
    found = [entry for entry in _purchases(conn, current_user_id, filters["card_id"]) if _matches(entry, filters)]
    found.sort(key=lambda entry: (entry["date"] or "", entry["created_at"] or "", entry["id"]), reverse=True)
    return found
