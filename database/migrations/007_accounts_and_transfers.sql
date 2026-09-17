-- Contas bancarias (3.1 de docs/next-steps.md).
--
-- Ate aqui o saldo era um numero implicito: a soma de todas as transactions do
-- usuario. Esta migration introduz a entidade conta, liga cada transaction a
-- uma delas e cria o tipo TRANSFER, para que mover dinheiro entre contas
-- proprias deixe de ser registrado como despesa + receita (o que inflava tanto
-- o total de despesas quanto o de receitas sem mudar o patrimonio).

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

-- Uma "Conta Principal" por usuario que ja tenha dados, para receber o backfill.
INSERT OR IGNORE INTO accounts (id, user_id, name, type, is_default)
SELECT
    'acct:' || u.id,
    u.id,
    'Conta Principal',
    'CHECKING',
    1
FROM users u;

-- transactions precisa ser reconstruida: o CHECK de `type` e imutavel por
-- ALTER TABLE no SQLite e precisa passar a aceitar TRANSFER.
--
-- Uma transferencia e UMA linha, nao duas: type='TRANSFER', account_id = conta
-- de origem, transfer_account_id = conta de destino. Assim o total consolidado
-- ignora TRANSFER naturalmente e o saldo por conta subtrai na origem e soma no
-- destino, sem precisar casar duas linhas irmas.
CREATE TABLE transactions_new (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL,
    transfer_account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL,
    amount REAL NOT NULL CHECK (amount >= 0),
    date TEXT NOT NULL,
    category TEXT NOT NULL,
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

INSERT INTO transactions_new
    (id, user_id, account_id, transfer_account_id, amount, date, category,
     description, type, source_type, source_id, metadata, created_at)
SELECT
    t.id,
    t.user_id,
    'acct:' || t.user_id,
    NULL,
    t.amount,
    t.date,
    t.category,
    t.description,
    t.type,
    t.source_type,
    t.source_id,
    t.metadata,
    t.created_at
FROM transactions t;

DROP TABLE transactions;

ALTER TABLE transactions_new RENAME TO transactions;

CREATE INDEX IF NOT EXISTS idx_transactions_user_date
ON transactions(user_id, date DESC);

CREATE INDEX IF NOT EXISTS idx_transactions_user_created_at
ON transactions(user_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_user_source
ON transactions(user_id, source_type, source_id)
WHERE source_type IS NOT NULL AND source_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_transactions_user_category_date
ON transactions(user_id, category, date DESC);

CREATE INDEX IF NOT EXISTS idx_transactions_user_account_date
ON transactions(user_id, account_id, date DESC);

CREATE INDEX IF NOT EXISTS idx_transactions_user_transfer_account_date
ON transactions(user_id, transfer_account_id, date DESC);
