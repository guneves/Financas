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
