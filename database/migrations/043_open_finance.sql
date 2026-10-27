-- Open Finance pela Pluggy (services/open_finance.py): os movimentos das contas
-- e cartoes do dono chegam sem digitar, e TUDO passa pelo Aprovar — nada e
-- gravado sem o dono aprovar. A Pluggy esteve no app ate 2026-10-17 (027/029
-- ficaram vazias, 030 renomeou as linhas delas); isto e um desenho novo.
--
-- open_finance_items: uma conexao com um banco (o "item" da Pluggy). O
--   servidor so e alcancavel dentro da tailnet, entao nao ha webhook: o app
--   puxa (botao "Atualizar" e uma thread de tempos em tempos). Desconectar
--   apaga o item na Pluggy e arquiva o nosso; os lancamentos ja gravados ficam.
-- open_finance_accounts: cada conta da Pluggy (BANK ou CREDIT) e a conta ou o
--   cartao do dono a que ela corresponde — escolhido por ele, nunca adivinhado
--   em silencio. Sem mapeamento, a conta e puxada mas nao gera nada.
--   charge_sign: no cartao, o sinal com que uma COMPRA chega (+1/-1). A doc da
--   Pluggy diz "positivo e debito"; o sandbox manda compras negativas com
--   type CREDIT (2026-10-27). Cada cartao aprende o seu (charge_sign_source:
--   payment = um pagamento de fatura no pull; majority; default = a doc).
-- open_finance_transactions: cada transacao puxada, unica por usuario pela
--   chave 'pluggy:<id da transacao>' — puxar de novo, a janela de folga e
--   reconectar nunca duplicam.
--
-- Por que tabela propria e nao notify_detections com outra fonte: aquela
-- tabela e a notificacao do celular — a identidade e o dedupKey e o posted_ms
-- (o pareamento e uma janela de 10 minutos), kind e role tem CHECK com as
-- formas de notificacao, e todo SELECT nela supoe uma. Uma transacao da Pluggy
-- tem outra identidade (o id), quase nunca tem hora, traz parcela e status, e
-- precisa existir antes do mapeamento. O papel e o mesmo: item_id liga a
-- linha ao item do Aprovar; role diz o que ela e para ele; target_* e o
-- lancamento que ela explica.
--
-- role: SOURCE (alimenta um item), PAIRED (a mesma compra de um item ja
-- recusado), MATCHED (um lancamento que ja existe), COVERED (parcela 2..n:
-- a compra ja gerou todas as parcelas), INVOICE_PAYMENT (pagamento de fatura:
-- nunca vira lancamento por aqui), UNMAPPED (a conta ainda sem mapeamento),
-- REMOVED (sumiu ou mudou de valor antes da aprovacao).

CREATE TABLE IF NOT EXISTS open_finance_items (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pluggy_item_id TEXT NOT NULL,
    connector_id INTEGER,
    connector_name TEXT,
    status TEXT,
    execution_status TEXT,
    error_code TEXT,
    error_message TEXT,
    -- lastUpdatedAt da Pluggy: quando ela trouxe dados do banco pela ultima vez.
    pluggy_updated_at TEXT,
    -- Ultimo PATCH /items/{id} (pedir dados novos ao banco gasta o limite mensal).
    update_requested_at TEXT,
    last_sync_at TEXT,
    last_sync_error TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (user_id, pluggy_item_id)
);

CREATE TABLE IF NOT EXISTS open_finance_accounts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    of_item_id TEXT NOT NULL REFERENCES open_finance_items(id) ON DELETE CASCADE,
    pluggy_account_id TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('BANK', 'CREDIT')),
    subtype TEXT,
    name TEXT,
    number TEXT,
    currency TEXT NOT NULL DEFAULT 'BRL',
    balance REAL,
    balance_at TEXT,
    account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL,
    card_id TEXT REFERENCES credit_cards(id) ON DELETE SET NULL,
    mapped_at TEXT,
    charge_sign INTEGER CHECK (charge_sign IS NULL OR charge_sign IN (-1, 1)),
    charge_sign_source TEXT CHECK (charge_sign_source IS NULL OR charge_sign_source IN ('payment', 'majority', 'default')),
    -- Ate que data (local) o ultimo pull chegou; o proximo comeca dias antes.
    synced_until TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (user_id, pluggy_account_id),
    CHECK (account_id IS NULL OR card_id IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_open_finance_accounts_item
ON open_finance_accounts(user_id, of_item_id);

CREATE TABLE IF NOT EXISTS open_finance_transactions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    of_account_id TEXT NOT NULL REFERENCES open_finance_accounts(id) ON DELETE CASCADE,
    pluggy_transaction_id TEXT NOT NULL,
    dedup_key TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('OUT', 'IN')),
    -- Positivo. Na primeira parcela de uma compra parcelada, o total da compra.
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    -- O valor como a Pluggy mandou (com sinal), para conferir a convencao.
    raw_amount_cents INTEGER NOT NULL,
    currency TEXT NOT NULL DEFAULT 'BRL',
    date TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    description TEXT,
    pluggy_type TEXT,
    pluggy_category TEXT,
    pluggy_category_id TEXT,
    -- NULL; TRANSFER (Pix/TED/DOC); SELF_TRANSFER (mesma titularidade);
    -- INVOICE_PAYMENT (pagamento de fatura de cartao).
    movement TEXT CHECK (movement IS NULL OR movement IN ('TRANSFER', 'SELF_TRANSFER', 'INVOICE_PAYMENT')),
    installment_number INTEGER,
    total_installments INTEGER,
    counterparty TEXT,
    counterparty_doc TEXT,
    role TEXT NOT NULL CHECK (role IN (
        'SOURCE', 'PAIRED', 'MATCHED', 'COVERED', 'INVOICE_PAYMENT', 'UNMAPPED', 'REMOVED'
    )),
    item_id TEXT REFERENCES inbox_items(id) ON DELETE SET NULL,
    target_table TEXT CHECK (target_table IS NULL OR target_table IN ('transactions', 'cc_expenses')),
    target_id TEXT,
    last_seen_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (user_id, dedup_key)
);

CREATE INDEX IF NOT EXISTS idx_open_finance_transactions_item
ON open_finance_transactions(user_id, item_id);

CREATE INDEX IF NOT EXISTS idx_open_finance_transactions_account
ON open_finance_transactions(user_id, of_account_id, date);

CREATE INDEX IF NOT EXISTS idx_open_finance_transactions_target
ON open_finance_transactions(user_id, target_table, target_id);
