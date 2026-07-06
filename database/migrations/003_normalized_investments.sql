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

INSERT OR IGNORE INTO assets
    (id, user_id, asset_class, ticker, name, created_at, updated_at)
SELECT
    'asset:' || user_id || ':' || asset_class || ':' || UPPER(TRIM(ticker_or_name)),
    user_id,
    asset_class,
    UPPER(TRIM(ticker_or_name)),
    MIN(TRIM(ticker_or_name)),
    MIN(created_at),
    MAX(created_at)
FROM investments
GROUP BY user_id, asset_class, UPPER(TRIM(ticker_or_name));

INSERT OR IGNORE INTO investment_transactions
    (
        id, user_id, asset_id, movement_type, quantity, unit_price,
        gross_amount, fee_amount, transaction_date, metadata, created_at, updated_at
    )
SELECT
    inv.id,
    inv.user_id,
    asset.id,
    CASE
        WHEN inv.quantity < 0
            AND inv.metadata IS NOT NULL
            AND json_valid(inv.metadata)
            AND COALESCE(json_extract(inv.metadata, '$.is_redemption'), 0) THEN 'REDEMPTION'
        WHEN inv.quantity < 0 THEN 'SELL'
        ELSE 'BUY'
    END,
    inv.quantity,
    inv.average_price,
    ABS(inv.quantity * inv.average_price),
    CASE
        WHEN inv.metadata IS NOT NULL
            AND json_valid(inv.metadata)
            AND json_extract(inv.metadata, '$.other_costs') IS NOT NULL
        THEN ABS(CAST(json_extract(inv.metadata, '$.other_costs') AS REAL))
        ELSE 0
    END,
    CASE
        WHEN inv.metadata IS NOT NULL
            AND json_valid(inv.metadata)
            AND json_extract(inv.metadata, '$.redemption_date') IS NOT NULL
        THEN json_extract(inv.metadata, '$.redemption_date')
        WHEN inv.metadata IS NOT NULL
            AND json_valid(inv.metadata)
            AND json_extract(inv.metadata, '$.sale_date') IS NOT NULL
        THEN json_extract(inv.metadata, '$.sale_date')
        WHEN inv.metadata IS NOT NULL
            AND json_valid(inv.metadata)
            AND json_extract(inv.metadata, '$.purchase_date') IS NOT NULL
        THEN json_extract(inv.metadata, '$.purchase_date')
        ELSE substr(inv.created_at, 1, 10)
    END,
    inv.metadata,
    inv.created_at,
    inv.created_at
FROM investments inv
JOIN assets asset
  ON asset.user_id = inv.user_id
 AND asset.asset_class = inv.asset_class
 AND asset.ticker = UPPER(TRIM(inv.ticker_or_name));

INSERT OR IGNORE INTO price_quotes
    (id, user_id, asset_id, transaction_id, price, quoted_at, source, metadata, created_at)
SELECT
    'quote:' || inv.id,
    inv.user_id,
    asset.id,
    CASE
        WHEN inv.asset_class IN ('STOCKS', 'REIT') THEN NULL
        ELSE inv.id
    END,
    inv.current_price,
    inv.created_at,
    'legacy',
    '{"legacy_investment_id":"' || REPLACE(inv.id, '"', '""') || '"}',
    inv.created_at
FROM investments inv
JOIN assets asset
  ON asset.user_id = inv.user_id
 AND asset.asset_class = inv.asset_class
 AND asset.ticker = UPPER(TRIM(inv.ticker_or_name))
WHERE inv.current_price IS NOT NULL;
