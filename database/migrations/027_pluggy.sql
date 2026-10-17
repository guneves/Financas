-- Pluggy (Open Finance): o que o banco registrou entra no extrato, conciliado
-- com o que o dono e o celular ja lancaram (services/pluggy_sync.py).
--
-- pluggy_items: as conexoes (itens) que o dono cadastrou, pelo id da Pluggy.
-- pluggy_account_links: cada conta da Pluggy ligada a uma conta (BANK) ou a um
--   cartao (CREDIT) do app. So entra o que tem data a partir de `since`: o que
--   veio antes ja esta no saldo inicial ou foi lancado a mao.
-- pluggy_transactions: o livro da sincronizacao, uma linha por transacao da
--   Pluggy, com o que foi feito dela (state). E a chave da idempotencia:
--   sincronizar de novo nao grava nada que o livro ja decidiu, e um lancamento
--   que o dono apagou nao volta.
--
-- external_id ('pluggy:<id>') marca o lancamento ou a parcela que uma
-- transacao da Pluggy confirma, tenha nascido dela ou ja existisse (digitado,
-- do celular, de extrato importado). source_type continua dizendo quem gravou:
-- um lancamento digitado que a Pluggy confirma segue "Manual".
--
-- cc_expenses ganha source_type/source_id como transactions: uma compra que
-- nasceu da Pluggy tem source_type 'PLUGGY' e o mesmo source_id em todas as
-- parcelas.
--
-- So ADD COLUMN e tabelas novas: nenhuma tabela e reconstruida.

CREATE TABLE IF NOT EXISTS pluggy_items (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_id TEXT NOT NULL,
    connector_name TEXT,
    status TEXT,
    execution_status TEXT,
    last_updated_at TEXT,
    last_sync_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (user_id, item_id)
);

CREATE TABLE IF NOT EXISTS pluggy_account_links (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_id TEXT NOT NULL,
    pluggy_account_id TEXT NOT NULL,
    pluggy_account_type TEXT NOT NULL CHECK (pluggy_account_type IN ('BANK', 'CREDIT')),
    name TEXT,
    account_id TEXT REFERENCES accounts(id) ON DELETE CASCADE,
    card_id TEXT REFERENCES credit_cards(id) ON DELETE CASCADE,
    since TEXT NOT NULL,
    -- 1 depois da primeira leitura completa desde `since`; trocar `since` volta a 0.
    full_sync_done INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (pluggy_account_type <> 'BANK' OR (account_id IS NOT NULL AND card_id IS NULL)),
    CHECK (pluggy_account_type <> 'CREDIT' OR (card_id IS NOT NULL AND account_id IS NULL)),
    UNIQUE (user_id, pluggy_account_id)
);

CREATE TABLE IF NOT EXISTS pluggy_transactions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pluggy_id TEXT NOT NULL,
    pluggy_account_id TEXT NOT NULL,
    date TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount > 0),
    direction TEXT NOT NULL CHECK (direction IN ('DEBIT', 'CREDIT')),
    description TEXT,
    -- POSTED | PENDING, como a Pluggy diz.
    status TEXT NOT NULL,
    installment_number INTEGER,
    total_installments INTEGER,
    purchase_date TEXT,
    pluggy_updated_at TEXT,
    -- IMPORTED: virou um lancamento/compra nova (source_type 'PLUGGY');
    -- ATTACHED: confirma um lancamento que ja existia;
    -- REVIEW: possivel duplicata, espera o dono; WAITING: PENDING na Pluggy;
    -- SKIPPED: fora do que o app guarda; DISMISSED: o dono mandou ignorar;
    -- REMOVED: sumiu da Pluggy.
    state TEXT NOT NULL CHECK (state IN (
        'IMPORTED', 'ATTACHED', 'REVIEW', 'WAITING', 'SKIPPED', 'DISMISSED', 'REMOVED'
    )),
    reason TEXT,
    target_table TEXT CHECK (target_table IS NULL OR target_table IN ('transactions', 'cc_expenses')),
    target_id TEXT,
    -- JSON: [{"table", "id", "kind"}] dos lancamentos parecidos (REVIEW).
    candidates TEXT,
    -- JSON: o que a Pluggy diz diferente do lancamento conferido (ATTACHED).
    difference TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (user_id, pluggy_id)
);

CREATE INDEX IF NOT EXISTS idx_pluggy_transactions_state
ON pluggy_transactions(user_id, state);

CREATE INDEX IF NOT EXISTS idx_pluggy_transactions_account_date
ON pluggy_transactions(user_id, pluggy_account_id, date);

CREATE INDEX IF NOT EXISTS idx_pluggy_transactions_target
ON pluggy_transactions(user_id, target_table, target_id);

ALTER TABLE transactions ADD COLUMN external_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_user_external
ON transactions(user_id, external_id)
WHERE external_id IS NOT NULL;

ALTER TABLE cc_expenses ADD COLUMN external_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_cc_expenses_user_external
ON cc_expenses(user_id, external_id)
WHERE external_id IS NOT NULL;

ALTER TABLE cc_expenses ADD COLUMN source_type TEXT;
ALTER TABLE cc_expenses ADD COLUMN source_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_cc_expenses_user_source
ON cc_expenses(user_id, source_type, source_id, installment_info)
WHERE source_type IS NOT NULL AND source_id IS NOT NULL;
