-- Juros (cupom) de renda fixa como provento (owner, 2026-10-19): o cupom de
-- uma debenture, de um CRI/CRA ou do Tesouro com juros semestrais nao vem de
-- nenhuma fonte automatica, entao o dono registra os pagamentos futuros a mao,
-- e cada um entra na conta da carteira no dia do pagamento, como os outros
-- proventos (services/proceeds_cash.py).
--
-- O tipo novo e 'INTEREST'. O CHECK de proceeds_type nao muda sem refazer a
-- tabela (SQLite), entao ela e copiada inteira, com as colunas de 026 e os
-- mesmos indices. Nenhuma tabela aponta para investment_proceeds (o lancamento
-- do provento pago guarda o id em transactions.source_id, texto).

CREATE TABLE investment_proceeds_new (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    proceeds_type TEXT NOT NULL CHECK (proceeds_type IN ('DIVIDEND', 'JCP', 'AMORTIZATION', 'INTEREST')),
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
    sync_key TEXT,
    sync_locked INTEGER NOT NULL DEFAULT 0,
    CHECK (net_amount >= 0),
    CHECK (tax_amount <= gross_amount)
);

INSERT INTO investment_proceeds_new
    (id, user_id, asset_id, proceeds_type, declared_date, record_date, ex_date,
     payment_date, amount_per_unit, eligible_quantity, gross_amount, tax_amount,
     net_amount, source, notes, metadata, created_at, updated_at, sync_key, sync_locked)
SELECT
    id, user_id, asset_id, proceeds_type, declared_date, record_date, ex_date,
    payment_date, amount_per_unit, eligible_quantity, gross_amount, tax_amount,
    net_amount, source, notes, metadata, created_at, updated_at, sync_key, sync_locked
FROM investment_proceeds;

DROP TABLE investment_proceeds;

ALTER TABLE investment_proceeds_new RENAME TO investment_proceeds;

CREATE INDEX IF NOT EXISTS idx_investment_proceeds_user_payment
ON investment_proceeds(user_id, payment_date DESC, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_investment_proceeds_asset_payment
ON investment_proceeds(user_id, asset_id, payment_date DESC);

CREATE INDEX IF NOT EXISTS idx_investment_proceeds_user_type_payment
ON investment_proceeds(user_id, proceeds_type, payment_date DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_investment_proceeds_user_sync_key
ON investment_proceeds(user_id, sync_key)
WHERE sync_key IS NOT NULL;
