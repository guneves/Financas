"""Gravar um lancamento ou uma linha de cartao: o INSERT, um so.

O "+ Novo" (as rotas) e o motor do Aprovar (`inbox_decisions.create_entry()`)
gravam as mesmas linhas; cada um tinha o seu INSERT, com a sua lista de
colunas, e uma coluna nova tinha que ser lembrada em cada copia. Aqui a lista e
uma so. Quem chama ja validou tudo e ja arredondou o valor (`rounded_money()`):
estas funcoes so gravam, e deixam a `sqlite3.IntegrityError` subir (o indice
unico do `client_id` e como quem chama descobre uma entrega repetida).

A linha de cada caminho, coluna por coluna, esta fixada em
tests/test_entry_creation_rows.py.
"""

from db import new_id


def insert_transaction(
    conn, current_user_id, *, entry_type, account_id, amount, date, category, category_id=None,
    description=None, client_id=None, occurred_at=None, card_id=None, transfer_account_id=None,
    transfer_amount=None,
):
    """Uma linha de `transactions` (despesa, receita ou transferencia). Devolve o id."""
    row_id = new_id()
    conn.execute(
        """
        INSERT INTO transactions
        (id, user_id, account_id, transfer_account_id, amount, transfer_amount, date, category,
         category_id, description, type, client_id, occurred_at, card_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row_id, current_user_id, account_id, transfer_account_id, amount, transfer_amount, date, category,
            category_id, description, entry_type, client_id, occurred_at, card_id,
        ),
    )
    return row_id


def insert_card_row(
    conn, current_user_id, *, card_id, category, category_id, description, amount, purchase_date,
    invoice_month, invoice_year, installment_info, client_id, status="OPEN", kind="PURCHASE",
    refund_of=None, occurred_at=None,
):
    """Uma linha de `cc_expenses`: a parcela de uma compra, ou um estorno
    (`kind="REFUND"`, 1/1). Devolve o id."""
    row_id = new_id()
    conn.execute(
        """
        INSERT INTO cc_expenses
        (id, user_id, card_id, category, category_id, description, amount, purchase_date,
         invoice_month, invoice_year, installment_info, status, client_id, kind, refund_of, occurred_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row_id, current_user_id, card_id, category, category_id, description, amount, purchase_date,
            invoice_month, invoice_year, installment_info, status, client_id, kind, refund_of, occurred_at,
        ),
    )
    return row_id


def insert_card_purchase(conn, current_user_id, rows, purchase_id, occurred_at=None):
    """As parcelas de uma compra (as linhas de `build_installment_rows()`), todas
    com o `client_id` da compra (035). Devolve os ids, na ordem das faturas."""
    return [
        insert_card_row(
            conn, current_user_id, card_id=row["card_id"], category=row["category"],
            category_id=row["category_id"], description=row["description"], amount=row["amount"],
            purchase_date=row["purchase_date"], invoice_month=row["invoice_month"],
            invoice_year=row["invoice_year"], installment_info=row["installment_info"],
            status=row["status"], client_id=purchase_id, occurred_at=occurred_at,
        )
        for row in rows
    ]
