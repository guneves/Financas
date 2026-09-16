import json
import os
import sqlite3
import uuid


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "finance.db"))
if not os.path.isabs(DATABASE_PATH):
    DATABASE_PATH = os.path.join(BASE_DIR, DATABASE_PATH)

SNAPSHOT_DATE = "2026-07-02"

PORTFOLIO = [
    {
        "ticker": "BBAS3",
        "average_price": 22.75,
        "current_price": 19.72,
        "lots": [
            {"date": "2025-01-15", "quantity": 140},
            {"date": "2025-07-18", "quantity": 140},
            {"date": "2026-02-20", "quantity": 141},
        ],
    },
    {
        "ticker": "BBSE3",
        "average_price": 32.89,
        "current_price": 38.16,
        "lots": [
            {"date": "2025-02-12", "quantity": 70},
            {"date": "2025-09-10", "quantity": 70},
            {"date": "2026-05-06", "quantity": 60},
        ],
    },
    {
        "ticker": "VALE3",
        "average_price": 56.15,
        "current_price": 77.96,
        "lots": [
            {"date": "2025-03-05", "quantity": 20},
            {"date": "2025-10-14", "quantity": 20},
            {"date": "2026-06-18", "quantity": 17},
        ],
    },
    {
        "ticker": "ITSA4",
        "average_price": 11.86,
        "current_price": 13.38,
        "lots": [
            {"date": "2025-01-30", "quantity": 100},
            {"date": "2025-08-22", "quantity": 100},
            {"date": "2026-04-09", "quantity": 100},
        ],
    },
    {
        "ticker": "RANI3",
        "average_price": 8.41,
        "current_price": 7.96,
        "lots": [
            {"date": "2025-04-11", "quantity": 160},
            {"date": "2025-11-19", "quantity": 160},
            {"date": "2026-03-12", "quantity": 160},
        ],
    },
    {
        "ticker": "KLBN4",
        "average_price": 3.59,
        "current_price": 3.40,
        "lots": [
            {"date": "2025-02-26", "quantity": 350},
            {"date": "2025-09-25", "quantity": 350},
            {"date": "2026-07-02", "quantity": 400},
        ],
    },
    {
        "ticker": "FESA4",
        "average_price": 6.77,
        "current_price": 5.94,
        "lots": [
            {"date": "2025-05-08", "quantity": 200},
            {"date": "2025-12-15", "quantity": 200},
            {"date": "2026-05-24", "quantity": 200},
        ],
    },
    {
        "ticker": "SLCE3",
        "average_price": 15.70,
        "current_price": 12.61,
        "lots": [
            {"date": "2025-06-03", "quantity": 80},
            {"date": "2025-12-29", "quantity": 90},
            {"date": "2026-06-05", "quantity": 90},
        ],
    },
    {
        "ticker": "LEVE3",
        "average_price": 34.90,
        "current_price": 32.95,
        "lots": [
            {"date": "2025-07-07", "quantity": 20},
            {"date": "2026-01-16", "quantity": 25},
            {"date": "2026-06-28", "quantity": 25},
        ],
    },
    {
        "ticker": "SAPR4",
        "average_price": 5.97,
        "current_price": 7.23,
        "lots": [
            {"date": "2025-03-21", "quantity": 80},
            {"date": "2025-10-30", "quantity": 90},
            {"date": "2026-04-27", "quantity": 89},
        ],
    },
    {
        "ticker": "GOAU4",
        "average_price": 8.94,
        "current_price": 9.31,
        "lots": [
            {"date": "2025-05-23", "quantity": 60},
            {"date": "2026-01-30", "quantity": 70},
            {"date": "2026-07-02", "quantity": 70},
        ],
    },
    {
        "ticker": "SOJA3",
        "average_price": 7.44,
        "current_price": 6.04,
        "lots": [
            {"date": "2025-08-08", "quantity": 100},
            {"date": "2026-02-11", "quantity": 100},
            {"date": "2026-06-30", "quantity": 100},
        ],
    },
]


def asset_quantity(asset):
    return sum(lot["quantity"] for lot in asset["lots"])


def main():
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.row_factory = sqlite3.Row
        user = conn.execute("SELECT id, email FROM users ORDER BY created_at LIMIT 1").fetchone()
        if not user:
            raise RuntimeError("Nenhum usuario encontrado. Crie uma conta no app antes de semear a carteira.")

        user_id = user["id"]
        tickers = [asset["ticker"] for asset in PORTFOLIO]
        placeholders = ",".join("?" for _ in tickers)

        conn.execute(
            f"""
            DELETE FROM investments
            WHERE user_id = ?
              AND UPPER(ticker_or_name) IN ({placeholders})
            """,
            [user_id, *tickers],
        )

        for asset in PORTFOLIO:
            for lot in asset["lots"]:
                metadata = json.dumps(
                    {
                        "purchase_date": lot["date"],
                        "source": "carteira_real_screenshot",
                        "snapshot_date": SNAPSHOT_DATE,
                    },
                    ensure_ascii=False,
                )

                conn.execute(
                    """
                    INSERT INTO investments
                    (id, user_id, asset_class, ticker_or_name, quantity, average_price, current_price, metadata)
                    VALUES (?, ?, 'STOCKS', ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        user_id,
                        asset["ticker"],
                        lot["quantity"],
                        asset["average_price"],
                        asset["current_price"],
                        metadata,
                    ),
                )

        invested = sum(asset_quantity(asset) * asset["average_price"] for asset in PORTFOLIO)
        current = sum(asset_quantity(asset) * asset["current_price"] for asset in PORTFOLIO)
        profit = current - invested
        profitability = (profit / invested) * 100 if invested else 0

    print(f"Carteira real aplicada para {user['email']}.")
    print(f"Ativos: {len(PORTFOLIO)}")
    print(f"Lancamentos: {sum(len(asset['lots']) for asset in PORTFOLIO)}")
    print("Periodo simulado: 2025-01-15 a 2026-07-02")
    print(f"Valor investido: R$ {invested:,.2f}")
    print(f"Valor atual: R$ {current:,.2f}")
    print(f"Resultado: R$ {profit:,.2f} ({profitability:.2f}%)")


if __name__ == "__main__":
    main()
