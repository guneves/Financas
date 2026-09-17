-- ============================================================
-- FinanceMVP - schema SQLite local
-- ============================================================

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'CHECKING'
        CHECK (type IN ('CHECKING', 'SAVINGS', 'BROKERAGE', 'CASH', 'OTHER')),
    institution TEXT,
    initial_balance REAL NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'BRL',
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    archived_at TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(user_id, name)
);

CREATE INDEX IF NOT EXISTS idx_accounts_user_name
ON accounts(user_id, name);

CREATE INDEX IF NOT EXISTS idx_accounts_user_active
ON accounts(user_id, archived_at);

CREATE TABLE IF NOT EXISTS categories (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'EXPENSE' CHECK (kind IN ('INCOME', 'EXPENSE', 'BOTH')),
    parent_id TEXT REFERENCES categories(id) ON DELETE SET NULL,
    color TEXT,
    icon TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(user_id, name, parent_id)
);

CREATE INDEX IF NOT EXISTS idx_categories_user_name
ON categories(user_id, name);

CREATE INDEX IF NOT EXISTS idx_categories_user_parent
ON categories(user_id, parent_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_categories_user_root_name
ON categories(user_id, name)
WHERE parent_id IS NULL;

-- Orcamento mensal por categoria. month e TEXT 'YYYY-MM'; o saldo transportado
-- de rollover e calculado na leitura, nunca gravado. Ver migrations/009.
CREATE TABLE IF NOT EXISTS budgets (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id TEXT NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    month TEXT NOT NULL CHECK (month GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'),
    planned_amount REAL NOT NULL CHECK (planned_amount >= 0),
    rollover INTEGER NOT NULL DEFAULT 0 CHECK (rollover IN (0, 1)),
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(user_id, category_id, month)
);

CREATE INDEX IF NOT EXISTS idx_budgets_user_month
ON budgets(user_id, month);

CREATE INDEX IF NOT EXISTS idx_budgets_user_category
ON budgets(user_id, category_id);

-- Uma transferencia e UMA linha: type='TRANSFER', saindo de account_id e
-- entrando em transfer_account_id. Ver database/migrations/007.
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL,
    transfer_account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL,
    amount REAL NOT NULL CHECK (amount >= 0),
    date TEXT NOT NULL,
    category TEXT NOT NULL,
    category_id TEXT REFERENCES categories(id) ON DELETE SET NULL,
    description TEXT,
    type TEXT NOT NULL CHECK (type IN ('INCOME', 'EXPENSE', 'TRANSFER')),
    source_type TEXT,
    source_id TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (type <> 'TRANSFER' OR (account_id IS NOT NULL
                                  AND transfer_account_id IS NOT NULL
                                  AND account_id <> transfer_account_id)),
    CHECK (type = 'TRANSFER' OR transfer_account_id IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_transactions_user_date
ON transactions(user_id, date DESC);

CREATE INDEX IF NOT EXISTS idx_transactions_user_created_at
ON transactions(user_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_user_source
ON transactions(user_id, source_type, source_id)
WHERE source_type IS NOT NULL AND source_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_transactions_user_category_date
ON transactions(user_id, category, date DESC);

CREATE INDEX IF NOT EXISTS idx_transactions_user_category_id_date
ON transactions(user_id, category_id, date DESC);

CREATE INDEX IF NOT EXISTS idx_transactions_user_account_date
ON transactions(user_id, account_id, date DESC);

CREATE INDEX IF NOT EXISTS idx_transactions_user_transfer_account_date
ON transactions(user_id, transfer_account_id, date DESC);

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

CREATE INDEX IF NOT EXISTS idx_investments_user_class_ticker
ON investments(user_id, asset_class, ticker_or_name);

CREATE INDEX IF NOT EXISTS idx_investments_user_created_at
ON investments(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    asset_class TEXT NOT NULL CHECK (asset_class IN ('STOCKS', 'FIXED_INCOME', 'REIT', 'CATTLE', 'OTHER')),
    ticker TEXT NOT NULL,
    name TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'BRL',
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(user_id, asset_class, ticker)
);

CREATE INDEX IF NOT EXISTS idx_assets_user_class_ticker
ON assets(user_id, asset_class, ticker);

CREATE TABLE IF NOT EXISTS investment_transactions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    movement_type TEXT NOT NULL CHECK (movement_type IN ('BUY', 'SELL', 'REDEMPTION', 'ADJUSTMENT')),
    quantity REAL NOT NULL CHECK (quantity <> 0),
    unit_price REAL NOT NULL CHECK (unit_price >= 0),
    gross_amount REAL NOT NULL CHECK (gross_amount >= 0),
    fee_amount REAL NOT NULL DEFAULT 0 CHECK (fee_amount >= 0),
    transaction_date TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_investment_transactions_user_date
ON investment_transactions(user_id, transaction_date DESC, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_investment_transactions_asset_date
ON investment_transactions(asset_id, transaction_date DESC, created_at DESC);

CREATE TABLE IF NOT EXISTS price_quotes (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    transaction_id TEXT REFERENCES investment_transactions(id) ON DELETE CASCADE,
    price REAL NOT NULL CHECK (price >= 0),
    quoted_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(asset_id, transaction_id, quoted_at, source)
);

CREATE INDEX IF NOT EXISTS idx_price_quotes_asset_latest
ON price_quotes(asset_id, transaction_id, quoted_at DESC, created_at DESC);

CREATE TABLE IF NOT EXISTS investment_positions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    source_transaction_id TEXT REFERENCES investment_transactions(id) ON DELETE CASCADE,
    quantity REAL NOT NULL,
    invested_amount REAL NOT NULL,
    average_price REAL NOT NULL,
    current_price REAL NOT NULL,
    current_value REAL NOT NULL,
    net_value REAL NOT NULL,
    taxes REAL NOT NULL,
    profitability_percent REAL NOT NULL,
    metadata TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_investment_positions_identity
ON investment_positions(user_id, asset_id, COALESCE(source_transaction_id, ''));

CREATE INDEX IF NOT EXISTS idx_investment_positions_user_asset
ON investment_positions(user_id, asset_id);

CREATE TABLE IF NOT EXISTS investment_realized_results (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    source_transaction_id TEXT NOT NULL REFERENCES investment_transactions(id) ON DELETE CASCADE,
    movement_type TEXT NOT NULL CHECK (movement_type IN ('SELL', 'REDEMPTION')),
    quantity REAL NOT NULL CHECK (quantity > 0),
    average_cost REAL NOT NULL DEFAULT 0 CHECK (average_cost >= 0),
    gross_proceeds REAL NOT NULL DEFAULT 0 CHECK (gross_proceeds >= 0),
    fee_amount REAL NOT NULL DEFAULT 0 CHECK (fee_amount >= 0),
    net_proceeds REAL NOT NULL DEFAULT 0 CHECK (net_proceeds >= 0),
    net_unit_price REAL NOT NULL DEFAULT 0 CHECK (net_unit_price >= 0),
    cost_basis REAL NOT NULL DEFAULT 0 CHECK (cost_basis >= 0),
    realized_profit REAL NOT NULL DEFAULT 0,
    profitability_percent REAL NOT NULL DEFAULT 0,
    tax_rate REAL NOT NULL DEFAULT 0 CHECK (tax_rate >= 0),
    tax_amount REAL NOT NULL DEFAULT 0 CHECK (tax_amount >= 0),
    net_profit_after_tax REAL NOT NULL DEFAULT 0,
    operation_date TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(user_id, source_transaction_id)
);

CREATE INDEX IF NOT EXISTS idx_investment_realized_results_user_date
ON investment_realized_results(user_id, operation_date DESC, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_investment_realized_results_asset
ON investment_realized_results(user_id, asset_id, operation_date DESC);

CREATE TABLE IF NOT EXISTS investment_proceeds (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    proceeds_type TEXT NOT NULL CHECK (proceeds_type IN ('DIVIDEND', 'JCP', 'AMORTIZATION')),
    declared_date TEXT,
    record_date TEXT NOT NULL,
    ex_date TEXT,
    payment_date TEXT NOT NULL,
    amount_per_unit REAL CHECK (amount_per_unit IS NULL OR amount_per_unit >= 0),
    eligible_quantity REAL CHECK (eligible_quantity IS NULL OR eligible_quantity >= 0),
    gross_amount REAL NOT NULL CHECK (gross_amount >= 0),
    tax_amount REAL NOT NULL DEFAULT 0 CHECK (tax_amount >= 0),
    net_amount REAL NOT NULL CHECK (net_amount >= 0),
    source TEXT NOT NULL DEFAULT 'manual',
    notes TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (net_amount >= 0),
    CHECK (tax_amount <= gross_amount)
);

CREATE INDEX IF NOT EXISTS idx_investment_proceeds_user_payment
ON investment_proceeds(user_id, payment_date DESC, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_investment_proceeds_asset_payment
ON investment_proceeds(user_id, asset_id, payment_date DESC);

CREATE INDEX IF NOT EXISTS idx_investment_proceeds_user_type_payment
ON investment_proceeds(user_id, proceeds_type, payment_date DESC);

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

CREATE INDEX IF NOT EXISTS idx_cc_expenses_card_invoice
ON cc_expenses(user_id, card_id, invoice_year, invoice_month);
