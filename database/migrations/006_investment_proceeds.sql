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
