"""O pagamento de fatura que o banco manda (dono, 2026-10-30): segue a Pluggy.

Uma saida da conta que a Pluggy marca como pagamento de fatura (role
INVOICE_PAYMENT) nunca e despesa: as compras ja contam no cartao. Depois de cada
pull (com as compras do pull ja gravadas), `record_bank_payments()` cuida de cada
uma ainda sem lancamento (`invoice_payment_link()` ja ligou as que tem um
pay-invoice do app):

- achado o cartao e a fatura, a baixa e a de sempre (`settle_invoice()`: itens
  PAID, `paid_by`), datada no dia do banco e com o valor do banco;
- sem fatura para baixar (a compra e de antes do que a Pluggy guarda), o
  lancamento fica sozinho, na origem de pagamento de fatura, que nenhum total de
  despesa conta: o dinheiro saiu, e o saldo da conta tem de dizer isso.

Idempotente pelo id da Pluggy, no `source_id` e no `target_id` da linha.

**Qual cartao**: o credito de mesmo valor na conta do cartao, ate
CARD_SIDE_DAYS dias; senao os cartoes conectados da mesma conexao, depois os do
mesmo banco; o resto so entra com o valor exato de uma fatura.
**Qual fatura**: a mais antiga fechada de valor exato (no banco que arredonda,
o valor que arredonda para o do banco); senao, de um cartao certo, a mais antiga
fechada perto do vencimento (DUE_WINDOW_DAYS): a fatura do app nao fecha igual a do
banco quando falta uma parcela antiga ou a data da compra difere.
"""

from datetime import date as date_type

from db import new_id, row_to_dict, utc_timestamp
from money import rounded_money
from services import inbox, invoices
from source_types import CC_INVOICE_PAYMENT_SOURCE_TYPE

CARD_SIDE_DAYS = 5
DUE_WINDOW_DAYS = 45


def _ordinal(text):
    return date_type.fromisoformat(str(text)[:10]).toordinal()


def _cents(value):
    return int(round(float(value) * 100))


def mapped_cards(conn, current_user_id):
    """Os cartoes conectados, com a conta da Pluggy de cada um."""
    return [row_to_dict(row) for row in conn.execute(
        """
        SELECT c.*, o.id AS of_account_id, o.of_item_id, o.name AS of_name
        FROM open_finance_accounts o
        JOIN open_finance_items i ON i.id = o.of_item_id AND i.user_id = o.user_id
        JOIN credit_cards c ON c.id = o.card_id AND c.user_id = o.user_id
        WHERE o.user_id = ? AND o.ignored_at IS NULL AND i.archived_at IS NULL
        ORDER BY c.created_at, c.id
        """,
        (current_user_id,),
    ).fetchall()]


def open_invoices(conn, current_user_id, card):
    """[{month, year, cents, closing, due}] das faturas com item em aberto, da
    mais antiga para a mais nova."""
    rows = conn.execute(
        f"""
        SELECT invoice_month, invoice_year, SUM({invoices.signed_amount_sql()} * amount) AS total
        FROM cc_expenses
        WHERE user_id = ? AND card_id = ? AND status = 'OPEN'
        GROUP BY invoice_year, invoice_month
        ORDER BY invoice_year, invoice_month
        """,
        (current_user_id, card["id"]),
    ).fetchall()
    return [
        {
            "month": row["invoice_month"], "year": row["invoice_year"], "cents": _cents(row["total"]),
            "closing": invoices.invoice_closing_date(
                row["invoice_month"], row["invoice_year"], card["due_day"], card["closing_day"],
            ),
            "due": invoices.invoice_due_date(row["invoice_month"], row["invoice_year"], card["due_day"]),
        }
        for row in rows
    ]


def _card_side_claims(conn, current_user_id):
    """Os creditos de pagamento nas contas dos cartoes, ainda sem par."""
    return [row_to_dict(row) for row in conn.execute(
        """
        SELECT t.id, t.date, t.amount_cents, a.card_id FROM open_finance_transactions t
        JOIN open_finance_accounts a ON a.id = t.of_account_id AND a.user_id = t.user_id
        WHERE t.user_id = ? AND t.role = 'INVOICE_PAYMENT' AND t.direction = 'IN' AND a.card_id IS NOT NULL
        ORDER BY t.date, t.id
        """,
        (current_user_id,),
    ).fetchall()]


def _known_cards(row, account, cards, claims):
    """Os cartoes que esta saida pode pagar com certeza (nao so pelo valor)."""
    day = _ordinal(row["date"])
    for claim in claims:
        if claim["amount_cents"] == row["amount_cents"] and abs(_ordinal(claim["date"]) - day) <= CARD_SIDE_DAYS:
            claims.remove(claim)
            found = [card for card in cards if card["id"] == claim["card_id"]]
            if found:
                return found
    same_item = [card for card in cards if card["of_item_id"] == account["of_item_id"]]
    if same_item:
        return same_item
    issuer = inbox.issuer_of_institution(account["name"])
    return [card for card in cards if issuer and inbox.issuer_of_institution(card["of_name"]) == issuer]


def _pick_invoice(conn, current_user_id, row, account, known, cards):
    """(cartao, fatura) ou None."""
    cents = int(row["amount_cents"])
    rounds_up = inbox.open_finance_rounds_up(conn, current_user_id, account["id"])
    lowest = cents - 99 if rounds_up and cents % 100 == 0 else cents
    paid_on = date_type.fromisoformat(row["date"])
    ordered = known + [card for card in cards if card["id"] not in {entry["id"] for entry in known}]
    usable = {}
    for card in ordered:
        usable[card["id"]] = [
            invoice for invoice in open_invoices(conn, current_user_id, card)
            if invoice["closing"] <= paid_on and abs((invoice["due"] - paid_on).days) <= DUE_WINDOW_DAYS
        ]
        for invoice in usable[card["id"]]:
            if lowest <= invoice["cents"] <= cents:
                return card, invoice
    if len(known) == 1:
        for invoice in usable[known[0]["id"]]:
            if invoice["cents"] > 0:
                return known[0], invoice
    return None


def record_bank_payments(conn, current_user_id):
    """Grava as saidas de pagamento de fatura ainda sem lancamento. Devolve
    {settled, loose, amount_differs}: `loose` sem fatura para baixar;
    `amount_differs` baixou uma fatura de outro valor (vale o do banco)."""
    rows = conn.execute(
        """
        SELECT * FROM open_finance_transactions
        WHERE user_id = ? AND role = 'INVOICE_PAYMENT' AND direction = 'OUT' AND target_id IS NULL
        ORDER BY date, id
        """,
        (current_user_id,),
    ).fetchall()
    counts = {"settled": 0, "loose": 0, "amount_differs": 0}
    if not rows:
        return counts
    cards = mapped_cards(conn, current_user_id)
    claims = _card_side_claims(conn, current_user_id)
    for row in rows:
        account = conn.execute(
            "SELECT * FROM open_finance_accounts WHERE id = ? AND user_id = ?",
            (row["of_account_id"], current_user_id),
        ).fetchone()
        if not account or not account["account_id"] or account["ignored_at"]:
            continue
        counts[_record_one(conn, current_user_id, row, account, cards, claims)] += 1
    return counts


def _link(conn, current_user_id, row, transaction_id):
    conn.execute(
        "UPDATE open_finance_transactions SET target_table = 'transactions', target_id = ?, updated_at = ?"
        " WHERE id = ? AND user_id = ?",
        (transaction_id, utc_timestamp(), row["id"], current_user_id),
    )


def _record_one(conn, current_user_id, row, account, cards, claims):
    amount = rounded_money(int(row["amount_cents"]) / 100)
    known = _known_cards(row, account, cards, claims)
    picked = _pick_invoice(conn, current_user_id, row, account, known, cards)
    if picked:
        card, invoice = picked
        payment = invoices.settle_invoice(
            conn, current_user_id, card, invoice["month"], invoice["year"],
            account_id=account["account_id"], payment_date=row["date"],
            source_type=CC_INVOICE_PAYMENT_SOURCE_TYPE,
            source_id=f"{card['id']}:{invoice['year']:04d}-{invoice['month']:02d}:{row['pluggy_transaction_id']}",
        )
        if payment:
            differs = _cents(payment["amount"]) != int(row["amount_cents"])
            conn.execute(
                "UPDATE transactions SET amount = ? WHERE id = ? AND user_id = ?",
                (amount, payment["id"], current_user_id),
            )
            _link(conn, current_user_id, row, payment["id"])
            return "amount_differs" if differs else "settled"
    return _record_loose(conn, current_user_id, row, account, amount, known)


def _record_loose(conn, current_user_id, row, account, amount, known):
    label = known[0]["name"] if len(known) == 1 else "cartão"
    transaction_id = new_id()
    conn.execute(
        """
        INSERT OR IGNORE INTO transactions
        (id, user_id, account_id, amount, date, category, description, type, source_type, source_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'EXPENSE', ?, ?)
        """,
        (
            transaction_id, current_user_id, account["account_id"], amount, row["date"],
            f"Pagamento Fatura {label}", "Pagamento de fatura", CC_INVOICE_PAYMENT_SOURCE_TYPE,
            f"pluggy:{row['pluggy_transaction_id']}",
        ),
    )
    found = conn.execute(
        "SELECT id FROM transactions WHERE user_id = ? AND source_type = ? AND source_id = ?",
        (current_user_id, CC_INVOICE_PAYMENT_SOURCE_TYPE, f"pluggy:{row['pluggy_transaction_id']}"),
    ).fetchone()
    _link(conn, current_user_id, row, found["id"])
    return "loose"


def close_past_invoices(conn, current_user_id, today):
    """Na reconstrucao: fatura vencida que nenhum pagamento da Pluggy baixou
    (de antes do que ela guarda, ou paga por uma conta sem Pluggy) e historia,
    nao atraso: PAID sem lancamento. Devolve as baixadas, para o relatorio."""
    closed = []
    for card in mapped_cards(conn, current_user_id):
        for invoice in open_invoices(conn, current_user_id, card):
            if invoice["due"] >= today:
                continue
            conn.execute(
                """
                UPDATE cc_expenses SET status = 'PAID', paid_by = NULL
                WHERE user_id = ? AND card_id = ? AND status = 'OPEN' AND invoice_month = ? AND invoice_year = ?
                """,
                (current_user_id, card["id"], invoice["month"], invoice["year"]),
            )
            closed.append({
                "card": card["name"], "invoice": invoices.invoice_label(invoice["month"], invoice["year"]),
                "due": invoice["due"].isoformat(), "amount": invoice["cents"] / 100,
            })
    return closed
