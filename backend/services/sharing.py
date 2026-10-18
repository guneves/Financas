"""De quem e o gasto (032): lancamentos e compras no cartao feitos por outra pessoa.

Um lancamento (despesa ou receita) ou uma compra no cartao pode ser inteiro
de outra pessoa (`OTHERS`) ou dividido (`SPLIT`, com a parte dos outros em
`share_others_amount`), sempre com o nome de quem (`share_person`). O dinheiro
sai da conta igual — o saldo nao muda. Muda o que e "do dono": o Fluxo de
caixa mostra a parte dos outros a parte, e Despesas por categoria, o orcamento
e o plano do mes contam so a parte do dono (`own_amount_sql()`).

A parte dos outros de uma despesa fica em "A receber" ate o dono marcar que a
pessoa pagou (`share_settled_at`). Marcar nao grava dinheiro nenhum: o Pix que
a pessoa manda e um lancamento proprio.
"""

from db import row_to_dict, utc_timestamp
from money import rounded_money
from services.attachments import cc_purchase_expense_ids
from validators import ValidationError, parse_number, safe_float

SHARE_MODES = {"OTHERS", "SPLIT"}
SHARE_FIELDS = ("share_mode", "share_others_amount", "share_person")
PERSON_MAX_LENGTH = 120
INVESTMENT_CATEGORY = "Investimento"


def own_amount_sql(prefix=""):
    """Expressao SQL da parte do dono de uma linha (`prefix` = alias com ponto)."""
    return (
        f"(CASE {prefix}share_mode WHEN 'OTHERS' THEN 0"
        f" WHEN 'SPLIT' THEN {prefix}amount - COALESCE({prefix}share_others_amount, 0)"
        f" ELSE {prefix}amount END)"
    )


def others_amount(mode, others, amount):
    if mode == "OTHERS":
        return rounded_money(amount)
    if mode == "SPLIT":
        return rounded_money(others)
    return 0.0


def has_share_fields(payload):
    return any(key in payload for key in SHARE_FIELDS)


def parse_share(payload, amount):
    """Os campos de divisao de um payload contra o valor total `amount`.

    Devolve as colunas a gravar. `share_mode` vazio (ou "MINE") volta a ser so
    do dono e limpa tudo, inclusive o "pago".
    """
    raw_mode = str(payload.get("share_mode") or "").strip().upper()
    if raw_mode in ("", "MINE"):
        return {
            "share_mode": None,
            "share_others_amount": None,
            "share_person": None,
            "share_settled_at": None,
        }
    if raw_mode not in SHARE_MODES:
        raise ValidationError("De quem e: opcao invalida.")

    person = str(payload.get("share_person") or "").strip()
    if not person:
        raise ValidationError("Informe o nome da pessoa.")
    if len(person) > PERSON_MAX_LENGTH:
        raise ValidationError(f"Nome da pessoa deve ter no maximo {PERSON_MAX_LENGTH} caracteres.")

    others = None
    if raw_mode == "SPLIT":
        others = rounded_money(
            parse_number(payload, "share_others_amount", "Parte da outra pessoa", minimum=0, allow_zero=False)
        )
        if others >= rounded_money(amount):
            raise ValidationError(
                "A parte da outra pessoa deve ser menor que o valor. Se e tudo dela, escolha \"De outra pessoa\"."
            )
    return {"share_mode": raw_mode, "share_others_amount": others, "share_person": person}


def check_split_fits(mode, others, amount):
    """Um valor novo nao pode deixar a parte dos outros maior que o total."""
    if mode == "SPLIT" and rounded_money(others) >= rounded_money(amount):
        raise ValidationError(
            "O valor ficou menor que a parte da outra pessoa. Ajuste a divisao junto."
        )


def split_across_installments(amounts, others_total):
    """A parte dos outros de uma compra, repartida pelas parcelas.

    Proporcional ao valor de cada parcela; a ultima leva a sobra do
    arredondamento, para a soma bater com o que o dono digitou.
    """
    total = sum(safe_float(value) for value in amounts)
    shares = []
    remaining = rounded_money(others_total)
    for index, value in enumerate(amounts):
        if index == len(amounts) - 1:
            share = remaining
        else:
            share = rounded_money(others_total * safe_float(value) / total) if total else 0.0
            remaining = rounded_money(remaining - share)
        shares.append(min(max(share, 0.0), rounded_money(value)))
    return shares


def purchase_rows(conn, current_user_id, expense_id):
    ids = cc_purchase_expense_ids(conn, current_user_id, expense_id)
    if not ids:
        return []
    placeholders = ", ".join("?" for _ in ids)
    return conn.execute(
        f"""
        SELECT * FROM cc_expenses
        WHERE user_id = ? AND id IN ({placeholders})
        ORDER BY invoice_year, invoice_month, created_at, id
        """,
        (current_user_id, *ids),
    ).fetchall()


def update_purchase_share(conn, current_user_id, expense_id, payload):
    """Grava a divisao em todas as parcelas da compra; None se nao e do usuario."""
    rows = purchase_rows(conn, current_user_id, expense_id)
    if not rows:
        return None
    if any(row["kind"] == "REFUND" for row in rows):
        raise ValidationError("Um estorno nao se divide.")
    amounts = [safe_float(row["amount"]) for row in rows]
    share = parse_share(payload, sum(amounts))
    settled = share.pop("share_settled_at", "keep")
    if share["share_mode"] == "SPLIT":
        per_row = split_across_installments(amounts, share["share_others_amount"])
    else:
        per_row = [None] * len(rows)
    for row, others in zip(rows, per_row):
        values = [share["share_mode"], others, share["share_person"]]
        settled_clause = ""
        if settled != "keep":
            settled_clause = ", share_settled_at = ?"
            values.append(settled)
        conn.execute(
            f"""
            UPDATE cc_expenses
            SET share_mode = ?, share_others_amount = ?, share_person = ?{settled_clause}
            WHERE id = ? AND user_id = ?
            """,
            (*values, row["id"], current_user_id),
        )
    return [row_to_dict(row) for row in purchase_rows(conn, current_user_id, expense_id)]


# --------------------------------------------------------------------------
# A receber
# --------------------------------------------------------------------------


def list_receivables(conn, current_user_id, *, include_settled=False):
    """A parte dos outros de cada despesa e compra no cartao, por item.

    Uma compra parcelada e um item so (a soma das parcelas), com o id da
    primeira parcela — qualquer parcela leva a compra inteira.
    """
    settled_filter = "" if include_settled else "AND share_settled_at IS NULL"
    items = []
    for row in conn.execute(
        f"""
        SELECT id, date, description, category, amount, share_mode,
               share_others_amount, share_person, share_settled_at
        FROM transactions
        WHERE user_id = ? AND type = 'EXPENSE' AND share_mode IS NOT NULL
        {settled_filter}
        """,
        (current_user_id,),
    ).fetchall():
        items.append({
            "kind": "TRANSACTION",
            "id": row["id"],
            "date": row["date"],
            "description": row["description"] or row["category"],
            "category": row["category"],
            "amount": rounded_money(row["amount"]),
            "share_mode": row["share_mode"],
            "others_amount": others_amount(row["share_mode"], row["share_others_amount"], row["amount"]),
            "person": row["share_person"],
            "settled_at": row["share_settled_at"],
        })

    purchases = {}
    for row in conn.execute(
        f"""
        SELECT cce.*, cc.name AS card_name
        FROM cc_expenses cce
        LEFT JOIN credit_cards cc ON cc.id = cce.card_id
        WHERE cce.user_id = ? AND cce.share_mode IS NOT NULL
        {settled_filter.replace('share_settled_at', 'cce.share_settled_at')}
        ORDER BY cce.invoice_year, cce.invoice_month, cce.created_at, cce.id
        """,
        (current_user_id,),
    ).fetchall():
        # A compra e o client_id (035): duas corridas iguais sao dois itens.
        key = row["client_id"] or (row["card_id"], row["description"], row["purchase_date"], row["category"])
        purchase = purchases.get(key)
        if purchase is None:
            purchase = purchases[key] = {
                "kind": "CARD_PURCHASE",
                "id": row["id"],
                "date": row["purchase_date"],
                "description": row["description"],
                "category": row["category"],
                "card_name": row["card_name"],
                "amount": 0.0,
                "share_mode": row["share_mode"],
                "others_amount": 0.0,
                "person": row["share_person"],
                "settled_at": row["share_settled_at"],
            }
        purchase["amount"] = rounded_money(purchase["amount"] + safe_float(row["amount"]))
        purchase["others_amount"] = rounded_money(
            purchase["others_amount"]
            + others_amount(row["share_mode"], row["share_others_amount"], row["amount"])
        )
    items.extend(purchases.values())
    items.sort(key=lambda item: (item["date"] or "", item["id"]), reverse=True)
    return items


def settle_receivables(conn, current_user_id, transaction_ids, cc_expense_ids, settled):
    """Marca (ou desmarca) a parte dos outros como paga. Devolve quantos itens mudaram."""
    stamp = utc_timestamp() if settled else None
    changed = 0
    for item_id in transaction_ids:
        cursor = conn.execute(
            """
            UPDATE transactions SET share_settled_at = ?
            WHERE id = ? AND user_id = ? AND type = 'EXPENSE' AND share_mode IS NOT NULL
            """,
            (stamp, item_id, current_user_id),
        )
        changed += cursor.rowcount
    for expense_id in cc_expense_ids:
        ids = cc_purchase_expense_ids(conn, current_user_id, expense_id)
        if not ids:
            continue
        placeholders = ", ".join("?" for _ in ids)
        cursor = conn.execute(
            f"""
            UPDATE cc_expenses SET share_settled_at = ?
            WHERE user_id = ? AND share_mode IS NOT NULL AND id IN ({placeholders})
            """,
            (stamp, current_user_id, *ids),
        )
        if cursor.rowcount:
            changed += 1
    return changed
