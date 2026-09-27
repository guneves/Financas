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
    username TEXT,
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

-- Molde de lancamento recorrente. O dinheiro continua nascendo em
-- transactions: POST /api/recurring/run materializa o que venceu, gravando
-- source_type='RECURRING_TRANSACTION' e source_id='<recorrencia>:<AAAA-MM-DD>',
-- de modo que o indice unico idx_transactions_user_source torne uma segunda
-- rodada inofensiva. Ver database/migrations/010.
CREATE TABLE IF NOT EXISTS recurring_transactions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL,
    category_id TEXT REFERENCES categories(id) ON DELETE SET NULL,
    category TEXT NOT NULL,
    description TEXT,
    type TEXT NOT NULL CHECK (type IN ('INCOME', 'EXPENSE')),
    amount REAL NOT NULL CHECK (amount > 0),
    frequency TEXT NOT NULL CHECK (frequency IN ('WEEKLY', 'MONTHLY', 'YEARLY')),
    interval_count INTEGER NOT NULL DEFAULT 1 CHECK (interval_count >= 1),
    start_date TEXT NOT NULL,
    next_run_date TEXT,
    end_date TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    last_run_at TEXT,
    note TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    -- 019: dia da pausa, janelas de pausa ja retomadas (JSON [[inicio, fim]],
    -- exclusivos) e a ultima data que o /run percorreu.
    paused_at TEXT,
    pause_gaps TEXT,
    last_occurrence_date TEXT,
    CHECK (end_date IS NULL OR end_date >= start_date)
);

CREATE INDEX IF NOT EXISTS idx_recurring_user_next_run
ON recurring_transactions(user_id, active, next_run_date);

CREATE INDEX IF NOT EXISTS idx_recurring_user_category
ON recurring_transactions(user_id, category_id);

-- 013: regras de categorizacao automatica da importacao de extrato.
CREATE TABLE IF NOT EXISTS import_rules (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pattern TEXT NOT NULL,
    match_type TEXT NOT NULL DEFAULT 'CONTAINS'
        CHECK (match_type IN ('CONTAINS', 'STARTS_WITH', 'EQUALS')),
    applies_to TEXT NOT NULL DEFAULT 'BOTH'
        CHECK (applies_to IN ('INCOME', 'EXPENSE', 'BOTH')),
    category TEXT NOT NULL,
    category_id TEXT REFERENCES categories(id) ON DELETE SET NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    hits INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    -- 015: condicoes opcionais de valor (absoluto, inclusivo) e de conta.
    amount_min REAL,
    amount_max REAL,
    account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_import_rules_user_priority
ON import_rules(user_id, active, priority DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_import_rules_user_pattern
ON import_rules(
    user_id, pattern, match_type, applies_to,
    COALESCE(amount_min, -1), COALESCE(amount_max, -1), COALESCE(account_id, '')
);

-- 014: comprovantes por lancamento. O arquivo fica em
-- ATTACHMENTS_DIR/<user_id>/<stored_name>; o banco guarda so a referencia.
CREATE TABLE IF NOT EXISTS transaction_attachments (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    transaction_id TEXT NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL UNIQUE,
    content_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes > 0),
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_transaction_attachments_user_transaction
ON transaction_attachments(user_id, transaction_id);

-- 016: comprovantes de compras no cartao (listados por compra, todas as parcelas).
CREATE TABLE IF NOT EXISTS cc_expense_attachments (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    cc_expense_id TEXT NOT NULL REFERENCES cc_expenses(id) ON DELETE CASCADE,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL UNIQUE,
    content_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes > 0),
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_cc_expense_attachments_user_expense
ON cc_expense_attachments(user_id, cc_expense_id);

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
    autopay_account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL,  -- 011
    autopay_start_date TEXT,                                              -- 011
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

-- 017: eventos corporativos (desdobramento, grupamento, bonificacao), ajustados na gravacao.
CREATE TABLE IF NOT EXISTS corporate_actions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL CHECK (action_type IN ('SPLIT', 'REVERSE_SPLIT', 'BONUS')),
    ex_date TEXT NOT NULL,
    ratio_from REAL NOT NULL CHECK (ratio_from > 0),
    ratio_to REAL NOT NULL CHECK (ratio_to > 0),
    bonus_unit_cost REAL CHECK (bonus_unit_cost IS NULL OR bonus_unit_cost >= 0),
    bonus_transaction_id TEXT REFERENCES investment_transactions(id) ON DELETE SET NULL,
    adjusted_ids TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_corporate_actions_user_asset_date
ON corporate_actions(user_id, asset_id, ex_date);

-- 018: PTAX por dia (BRL por unidade da moeda) para converter ativos e contas.
CREATE TABLE IF NOT EXISTS fx_rates (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    currency TEXT NOT NULL,
    rate_date TEXT NOT NULL,
    rate REAL NOT NULL CHECK (rate > 0),
    source TEXT NOT NULL DEFAULT 'bcb_ptax',
    fetched_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (user_id, currency, rate_date)
);

-- 020: alocacao alvo ("% ideal"): classe em % da carteira, ativo em % da classe.
CREATE TABLE IF NOT EXISTS allocation_targets (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scope TEXT NOT NULL CHECK (scope IN ('CLASS', 'ASSET')),
    asset_class TEXT NOT NULL CHECK (asset_class IN ('STOCKS', 'FIXED_INCOME', 'REIT', 'CATTLE', 'OTHER')),
    asset_id TEXT REFERENCES assets(id) ON DELETE CASCADE,
    target_percent REAL NOT NULL CHECK (target_percent >= 0 AND target_percent <= 100),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK ((scope = 'CLASS' AND asset_id IS NULL) OR (scope = 'ASSET' AND asset_id IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_allocation_targets_user_key
ON allocation_targets(user_id, scope, asset_class, COALESCE(asset_id, ''));

-- 021: metas financeiras (so o plano; atual e previsao sao calculados na leitura).
CREATE TABLE IF NOT EXISTS investment_goals (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('PORTFOLIO', 'NET_WORTH', 'ASSET_CLASS', 'MONTHLY_INCOME')),
    asset_class TEXT CHECK (asset_class IS NULL OR asset_class IN ('STOCKS', 'FIXED_INCOME', 'REIT', 'CATTLE', 'OTHER')),
    target_amount REAL NOT NULL CHECK (target_amount > 0),
    monthly_contribution REAL NOT NULL DEFAULT 0 CHECK (monthly_contribution >= 0),
    annual_return_percent REAL CHECK (annual_return_percent IS NULL OR (annual_return_percent > -100 AND annual_return_percent <= 100)),
    target_date TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK ((kind = 'ASSET_CLASS') = (asset_class IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_investment_goals_user
ON investment_goals(user_id, created_at);

-- 023: fechamentos dos indices de comparacao (Ibovespa, IFIX, IDIV) da Rentabilidade.
CREATE TABLE IF NOT EXISTS benchmark_closes (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    benchmark TEXT NOT NULL,
    close_date TEXT NOT NULL,
    close REAL NOT NULL CHECK (close > 0),
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (user_id, benchmark, close_date)
);
