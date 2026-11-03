"""De quem e o gasto (032): lancamentos e compras no cartao feitos por outra pessoa.

Um lancamento (despesa ou receita) ou uma compra no cartao pode ser inteiro
de outra pessoa (`OTHERS`) ou dividido (`SPLIT`, com a parte dos outros em
`share_others_amount`), sempre com o nome de quem (`share_person`). O dinheiro
sai da conta igual — o saldo nao muda. Muda o que e "do dono": o Fluxo de
caixa mostra a parte dos outros a parte, e Despesas por categoria, o orcamento
e o plano do mes contam so a parte do dono (`own_amount_sql()`).

A parte dos outros de uma despesa fica em "A receber" ate o dono marcar que a
pessoa pagou (`share_settled_at`). Marcar nao grava dinheiro nenhum: o Pix que
a pessoa manda e um lancamento proprio. Ao marcar, o dono pode dizer qual receita
pagou (`share_paid_by`, 052, dono 2026-11-02): a parte dos outros sai dessa receita
(`link_income()`), no mes dela. O tio paga R$ 300 por um fone de R$ 230,28: so
R$ 69,72 e receita. Sem receita, o pago abate a do mes em que foi marcado
(`services.home.apply_settled_others()`).
"""

from datetime import date, timedelta

from db import row_to_dict, utc_timestamp
from money import parse_money, rounded_money
from services.attachments import cc_purchase_expense_ids
from source_types import INVESTMENT_SOURCE_TYPES, MONTH_SUMMARY_SOURCE_TYPE
from validators import ValidationError, require_date, safe_float

SHARE_MODES = {"OTHERS", "SPLIT"}
SHARE_FIELDS = ("share_mode", "share_others_amount", "share_person")
PERSON_MAX_LENGTH = 120


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
        others = parse_money(payload, "share_others_amount", "Parte da outra pessoa")
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
               share_others_amount, share_person, share_settled_at, share_paid_by
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
            "paid_by": row["share_paid_by"],
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
                "paid_by": row["share_paid_by"],
            }
        purchase["amount"] = rounded_money(purchase["amount"] + safe_float(row["amount"]))
        purchase["others_amount"] = rounded_money(
            purchase["others_amount"]
            + others_amount(row["share_mode"], row["share_others_amount"], row["amount"])
        )
    items.extend(purchases.values())
    incomes = _incomes_by_id(conn, current_user_id, {item["paid_by"] for item in items if item["paid_by"]})
    for item in items:
        item["paid_by"] = incomes.get(item["paid_by"])
    items.sort(key=lambda item: (item["date"] or "", item["id"]), reverse=True)
    return items


def _income_summary(row):
    return {
        "id": row["id"],
        "date": row["date"],
        "description": row["description"] or row["category"],
        "amount": rounded_money(row["amount"]),
    }


def _incomes_by_id(conn, current_user_id, ids):
    ids = sorted(ids)
    if not ids:
        return {}
    placeholders = ", ".join("?" for _ in ids)
    rows = conn.execute(
        f"SELECT * FROM transactions WHERE user_id = ? AND type = 'INCOME' AND id IN ({placeholders})",
        (current_user_id, *ids),
    ).fetchall()
    return {row["id"]: _income_summary(row) for row in rows}


def settle_receivables(conn, current_user_id, transaction_ids, cc_expense_ids, settled, income_id=None):
    """Marca (ou desmarca) a parte dos outros como paga. Devolve quantos itens mudaram.

    Com `income_id`, a receita que pagou: os itens ficam ligados a ela e a parte dos
    outros sai dela (`link_income()`). Desmarcar desliga e devolve a receita."""
    income = require_income(conn, current_user_id, income_id) if settled and income_id else None
    stamp = utc_timestamp() if settled else None
    paid_by = income["id"] if income else None
    touched = {paid_by} if paid_by else set()
    changed = 0
    for item_id in transaction_ids:
        before = conn.execute(
            "SELECT share_paid_by FROM transactions WHERE id = ? AND user_id = ? AND type = 'EXPENSE'"
            " AND share_mode IS NOT NULL",
            (item_id, current_user_id),
        ).fetchone()
        if not before:
            continue
        if before["share_paid_by"]:
            touched.add(before["share_paid_by"])
        conn.execute(
            "UPDATE transactions SET share_settled_at = ?, share_paid_by = ? WHERE id = ? AND user_id = ?",
            (stamp, paid_by, item_id, current_user_id),
        )
        changed += 1
    for expense_id in cc_expense_ids:
        ids = cc_purchase_expense_ids(conn, current_user_id, expense_id)
        if not ids:
            continue
        placeholders = ", ".join("?" for _ in ids)
        touched.update(
            row["share_paid_by"] for row in conn.execute(
                f"SELECT share_paid_by FROM cc_expenses WHERE user_id = ? AND share_paid_by IS NOT NULL"
                f" AND share_mode IS NOT NULL AND id IN ({placeholders})",
                (current_user_id, *ids),
            ).fetchall()
        )
        cursor = conn.execute(
            f"""
            UPDATE cc_expenses SET share_settled_at = ?, share_paid_by = ?
            WHERE user_id = ? AND share_mode IS NOT NULL AND id IN ({placeholders})
            """,
            (stamp, paid_by, current_user_id, *ids),
        )
        if cursor.rowcount:
            changed += 1
    for target in touched:
        link_income(conn, current_user_id, target)
    return changed


def _candidate_sql():
    investment = ", ".join(f"'{value}'" for value in sorted(INVESTMENT_SOURCE_TYPES))
    return f"""
        FROM transactions t
        JOIN accounts a ON a.id = t.account_id AND a.user_id = t.user_id
        WHERE t.user_id = ? AND t.type = 'INCOME'
          AND COALESCE(a.currency, 'BRL') = 'BRL' AND COALESCE(a.type, '') != 'BROKERAGE'
          AND COALESCE(t.source_type, '') NOT IN ({investment}, '{MONTH_SUMMARY_SOURCE_TYPE}')
    """


def require_income(conn, current_user_id, income_id):
    """A receita que pagou: uma receita em reais do dono, fora da carteira."""
    row = conn.execute(
        f"SELECT t.* {_candidate_sql()} AND t.id = ?", (current_user_id, str(income_id)),
    ).fetchone()
    if not row:
        raise ValidationError("Escolha uma receita em reais que pagou este item.")
    return row


def _cents_of(value):
    return round(safe_float(value) * 100)


def linked_others_cents(conn, current_user_id, income_id):
    """A parte dos outros, em centavos, dos itens de A receber pagos por esta receita."""
    total = 0
    for table in ("transactions", "cc_expenses"):
        for row in conn.execute(
            f"SELECT share_mode, share_others_amount, amount FROM {table}"
            " WHERE user_id = ? AND share_paid_by = ? AND share_mode IS NOT NULL AND share_settled_at IS NOT NULL",
            (current_user_id, income_id),
        ).fetchall():
            total += _cents_of(others_amount(row["share_mode"], row["share_others_amount"], row["amount"]))
    return total


def link_income(conn, current_user_id, income_id):
    """A receita leva como dos outros o que pagou em A receber (no maximo ela toda):
    `OTHERS` se cobre tudo, `SPLIT` com a parte, nada se nao pagou mais nada. O nome
    e o do primeiro item. O saldo nao muda; muda so a receita do dono."""
    row = conn.execute(
        "SELECT * FROM transactions WHERE id = ? AND user_id = ? AND type = 'INCOME'", (income_id, current_user_id),
    ).fetchone()
    if not row:
        return
    amount = _cents_of(row["amount"])
    cents = min(linked_others_cents(conn, current_user_id, income_id), amount)
    if cents <= 0:
        conn.execute(
            """UPDATE transactions SET share_mode = NULL, share_others_amount = NULL, share_person = NULL,
               share_settled_at = NULL WHERE id = ? AND user_id = ?""",
            (income_id, current_user_id),
        )
        return
    people = [
        found["share_person"]
        for table in ("transactions", "cc_expenses")
        for found in conn.execute(
            f"SELECT share_person, share_settled_at FROM {table} WHERE user_id = ? AND share_paid_by = ?"
            " AND share_mode IS NOT NULL AND share_settled_at IS NOT NULL ORDER BY share_settled_at LIMIT 1",
            (current_user_id, income_id),
        ).fetchall()
        if found["share_person"]
    ]
    whole = cents >= amount
    conn.execute(
        """UPDATE transactions SET share_mode = ?, share_others_amount = ?, share_person = ?, share_settled_at = ?
           WHERE id = ? AND user_id = ?""",
        (
            "OTHERS" if whole else "SPLIT",
            None if whole else rounded_money(cents / 100),
            (people[0] if people else "Outra pessoa")[:PERSON_MAX_LENGTH],
            utc_timestamp(),
            income_id,
            current_user_id,
        ),
    )


CANDIDATE_DAYS_BEFORE = 7
CANDIDATE_LIMIT = 30


def income_candidates(conn, current_user_id, since):
    """As receitas que podem ter pago um item de A receber feito em `since`: em
    reais, de uma semana antes dele em diante, sem divisao ou ja ligadas a A
    receber e com sobra (`room`, o que ainda pode ser dos outros). A mais recente
    primeiro."""
    first = date.fromisoformat(require_date({"since": since}, "since", "Data"))
    start = (first - timedelta(days=CANDIDATE_DAYS_BEFORE)).isoformat()
    rows = conn.execute(
        f"""
        SELECT t.* {_candidate_sql()} AND t.date >= ?
          AND (t.share_mode IS NULL
               OR EXISTS (SELECT 1 FROM transactions x WHERE x.user_id = t.user_id AND x.share_paid_by = t.id)
               OR EXISTS (SELECT 1 FROM cc_expenses x WHERE x.user_id = t.user_id AND x.share_paid_by = t.id))
        ORDER BY t.date DESC, t.created_at DESC
        LIMIT {CANDIDATE_LIMIT}
        """,
        (current_user_id, start),
    ).fetchall()
    items = []
    for row in rows:
        room = _cents_of(row["amount"]) - linked_others_cents(conn, current_user_id, row["id"])
        if room > 0:
            items.append({**_income_summary(row), "room": rounded_money(room / 100)})
    return items
