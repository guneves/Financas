-- ============================================================
-- FinanceMVP - schema SQLite local
-- ============================================================

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount REAL NOT NULL CHECK (amount >= 0),
    date TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    type TEXT NOT NULL CHECK (type IN ('INCOME', 'EXPENSE')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_transactions_user_date
ON transactions(user_id, date DESC);

CREATE TABLE IF NOT EXISTS investments (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    asset_class TEXT NOT NULL CHECK (asset_class IN ('STOCKS', 'FIXED_INCOME', 'REIT', 'CATTLE', 'OTHER')),
    ticker_or_name TEXT NOT NULL,
    quantity REAL NOT NULL,
    average_price REAL NOT NULL CHECK (average_price >= 0),
    current_price REAL,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_investments_user_asset_class
ON investments(user_id, asset_class);

CREATE INDEX IF NOT EXISTS idx_investments_user_ticker
ON investments(user_id, ticker_or_name);

CREATE TABLE IF NOT EXISTS credit_cards (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    due_day INTEGER NOT NULL CHECK (due_day BETWEEN 1 AND 31),
    closing_day INTEGER NOT NULL CHECK (closing_day BETWEEN 1 AND 31),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(user_id, name)
);

CREATE INDEX IF NOT EXISTS idx_credit_cards_user_name
ON credit_cards(user_id, name);

CREATE TABLE IF NOT EXISTS cc_expenses (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    card_id TEXT NOT NULL REFERENCES credit_cards(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount >= 0),
    purchase_date TEXT NOT NULL,
    invoice_month INTEGER NOT NULL CHECK (invoice_month BETWEEN 1 AND 12),
    invoice_year INTEGER NOT NULL CHECK (invoice_year >= 2000),
    installment_info TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'PAID')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_cc_expenses_invoice
ON cc_expenses(user_id, invoice_year, invoice_month);

CREATE INDEX IF NOT EXISTS idx_cc_expenses_status
ON cc_expenses(user_id, status);
