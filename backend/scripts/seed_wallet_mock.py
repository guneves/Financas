import calendar
import os
import sqlite3
import uuid
from datetime import date


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "finance.db"))
if not os.path.isabs(DATABASE_PATH):
    DATABASE_PATH = os.path.join(BASE_DIR, DATABASE_PATH)


MOCK_CARDS = [
    {"name": "Nubank Demo", "due_day": 10, "closing_day": 3},
    {"name": "Inter Demo", "due_day": 20, "closing_day": 13},
]


def add_months(year, month, offset):
    month_index = month - 1 + offset
    new_year = year + month_index // 12
    new_month = month_index % 12 + 1
    return new_year, new_month


def date_at_day(day, month_offset=0):
    today = date.today()
    year, month = add_months(today.year, today.month, month_offset)
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(max(day, 1), last_day)).isoformat()


MOCK_TRANSACTIONS = [
    {
        "type": "INCOME",
        "amount": 8500.00,
        "date": date_at_day(1),
        "category": "Salario",
        "description": "Demo - salario mensal",
    },
    {
        "type": "INCOME",
        "amount": 1250.00,
        "date": date_at_day(2),
        "category": "Freelance",
        "description": "Demo - projeto extra",
    },
    {
        "type": "EXPENSE",
        "amount": 2250.00,
        "date": date_at_day(3),
        "category": "Moradia",
        "description": "Demo - aluguel",
    },
    {
        "type": "EXPENSE",
        "amount": 486.70,
        "date": date_at_day(4),
        "category": "Mercado",
        "description": "Demo - mercado da semana",
    },
    {
        "type": "EXPENSE",
        "amount": 178.90,
        "date": date_at_day(5),
        "category": "Transporte",
        "description": "Demo - combustivel",
    },
    {
        "type": "INCOME",
        "amount": 8400.00,
        "date": date_at_day(1, -1),
        "category": "Salario",
        "description": "Demo - salario mes anterior",
    },
    {
        "type": "EXPENSE",
        "amount": 2130.00,
        "date": date_at_day(3, -1),
        "category": "Moradia",
        "description": "Demo - aluguel mes anterior",
    },
]

MOCK_PURCHASES = [
    {
        "card_name": "Nubank Demo",
        "category": "Alimentacao",
        "description": "Demo - supermercado no credito",
        "total_amount": 392.45,
        "purchase_date": date_at_day(2),
        "installments": 1,
    },
    {
        "card_name": "Nubank Demo",
        "category": "Servicos",
        "description": "Demo - notebook parcelado",
        "total_amount": 3600.00,
        "purchase_date": date_at_day(6),
        "installments": 6,
    },
    {
        "card_name": "Inter Demo",
        "category": "Saude",
        "description": "Demo - academia",
        "total_amount": 129.90,
        "purchase_date": date_at_day(8),
        "installments": 1,
    },
    {
        "card_name": "Inter Demo",
        "category": "Educacao",
        "description": "Demo - curso online",
        "total_amount": 900.00,
        "purchase_date": date_at_day(12),
        "installments": 3,
    },
]


def new_id():
    return str(uuid.uuid4())


def split_installments(total_amount, installments):
    total_cents = round(total_amount * 100)
    base_cents = total_cents // installments
    remainder = total_cents % installments
    return [
        (base_cents + (1 if index < remainder else 0)) / 100
        for index in range(installments)
    ]


def invoice_start(purchase_date, card):
    purchase = date.fromisoformat(purchase_date)
    invoice_month = purchase.month
    invoice_year = purchase.year
    due_day = int(card["due_day"])
    closing_day = int(card["closing_day"])

    if closing_day < due_day:
        if purchase.day >= closing_day:
            invoice_month += 1
    elif purchase.day < closing_day:
        invoice_month += 1
    else:
        invoice_month += 2

    while invoice_month > 12:
        invoice_month -= 12
        invoice_year += 1

    return invoice_month, invoice_year


def card_by_name(conn, user_id, name):
    return conn.execute(
        "SELECT * FROM credit_cards WHERE user_id = ? AND name = ?",
        (user_id, name),
    ).fetchone()


def ensure_card(conn, user_id, card):
    existing = card_by_name(conn, user_id, card["name"])
    if existing:
        return existing, False

    conn.execute(
        """
        INSERT INTO credit_cards (id, user_id, name, due_day, closing_day)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            new_id(),
            user_id,
            card["name"],
            card["due_day"],
            card["closing_day"],
        ),
    )
    return card_by_name(conn, user_id, card["name"]), True


def transaction_exists(conn, user_id, item):
    return conn.execute(
        """
        SELECT 1 FROM transactions
        WHERE user_id = ?
          AND type = ?
          AND amount = ?
          AND date = ?
          AND category = ?
          AND description = ?
        LIMIT 1
        """,
        (
            user_id,
            item["type"],
            item["amount"],
            item["date"],
            item["category"],
            item["description"],
        ),
    ).fetchone() is not None


def expense_exists(conn, user_id, item):
    return conn.execute(
        """
        SELECT 1 FROM cc_expenses
        WHERE user_id = ?
          AND card_id = ?
          AND category = ?
          AND description = ?
          AND amount = ?
          AND purchase_date = ?
          AND invoice_month = ?
          AND invoice_year = ?
          AND installment_info = ?
        LIMIT 1
        """,
        (
            user_id,
            item["card_id"],
            item["category"],
            item["description"],
            item["amount"],
            item["purchase_date"],
            item["invoice_month"],
            item["invoice_year"],
            item["installment_info"],
        ),
    ).fetchone() is not None


def seed_transactions(conn, user_id):
    created = 0
    for item in MOCK_TRANSACTIONS:
        if transaction_exists(conn, user_id, item):
            continue

        conn.execute(
            """
            INSERT INTO transactions
            (id, user_id, amount, date, category, description, type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id(),
                user_id,
                item["amount"],
                item["date"],
                item["category"],
                item["description"],
                item["type"],
            ),
        )
        created += 1
    return created


def seed_card_expenses(conn, user_id, cards_by_name):
    created = 0
    for purchase in MOCK_PURCHASES:
        card = cards_by_name.get(purchase["card_name"])
        if not card:
            continue

        current_month, current_year = invoice_start(purchase["purchase_date"], card)
        amounts = split_installments(purchase["total_amount"], purchase["installments"])

        for index, amount in enumerate(amounts, start=1):
            item = {
                "card_id": card["id"],
                "category": purchase["category"],
                "description": purchase["description"],
                "amount": amount,
                "purchase_date": purchase["purchase_date"],
                "invoice_month": current_month,
                "invoice_year": current_year,
                "installment_info": f"{index}/{purchase['installments']}",
                "status": "OPEN",
            }

            if expense_exists(conn, user_id, item):
                next_year, next_month = add_months(current_year, current_month, 1)
                current_year, current_month = next_year, next_month
                continue

            conn.execute(
                """
                INSERT INTO cc_expenses
                (id, user_id, card_id, category, description, amount, purchase_date,
                 invoice_month, invoice_year, installment_info, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id(),
                    user_id,
                    item["card_id"],
                    item["category"],
                    item["description"],
                    item["amount"],
                    item["purchase_date"],
                    item["invoice_month"],
                    item["invoice_year"],
                    item["installment_info"],
                    item["status"],
                ),
            )
            created += 1

            next_year, next_month = add_months(current_year, current_month, 1)
            current_year, current_month = next_year, next_month
    return created


def main():
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.row_factory = sqlite3.Row
        user = conn.execute(
            "SELECT id, email FROM users ORDER BY created_at LIMIT 1"
        ).fetchone()
        if not user:
            raise RuntimeError("Nenhum usuario encontrado. Crie uma conta no app antes de semear a carteira.")

        user_id = user["id"]
        created_cards = 0
        cards_by_name = {}
        for card in MOCK_CARDS:
            saved_card, was_created = ensure_card(conn, user_id, card)
            cards_by_name[card["name"]] = saved_card
            created_cards += 1 if was_created else 0

        created_transactions = seed_transactions(conn, user_id)
        created_expenses = seed_card_expenses(conn, user_id, cards_by_name)

    print(f"Carteira demo aplicada para {user['email']}.")
    print(f"Cartoes criados: {created_cards}")
    print(f"Lancamentos bancarios criados: {created_transactions}")
    print(f"Parcelas de cartao criadas: {created_expenses}")


if __name__ == "__main__":
    main()
