-- Aprovar (services/inbox.py): o que o celular (notificacoes dos bancos) traz
-- espera o dono aprovar, recusar ou corrigir. Fica no servidor, entao o
-- celular e o computador veem a mesma lista e as mesmas decisoes.
--
-- inbox_items: um movimento do mundo real esperando o dono (ou ja decidido).
--   Varias fontes do mesmo movimento (a notificacao do banco, a do Samsung
--   Wallet; as duas pontas de uma transferencia entre contas proprias) viram
--   UM item. Os campos de lancamento sao o rascunho que o dono pode corrigir; `source_occurred_at` e a hora que a fonte disse e
--   nunca muda; `version` sobe a cada mudanca (dois aparelhos nao se
--   atropelam: quem grava com a versao velha recebe 409).
-- notify_detections: cada notificacao que um parser do celular leu, so os
--   campos lidos (valor, hora, cartao, estabelecimento) — o texto nunca sai do
--   aparelho. A chave e o dedupKey da notificacao: reenviar nao duplica.
-- inbox_hints: as escolhas que o dono mandou lembrar (este cartao final 1234
--   do Itau e o cartao X; uma compra sem "credito/debito" do Samsung e o
--   cartao Y; "PIX ENVIADO <nome>" desta conta e transferencia para a conta Z).
--
-- occurred_at em transactions e cc_expenses: a hora do movimento, como a
-- fonte disse (AAAA-MM-DDTHH:MM:SS-03:00), ou so a data quando a fonte nao
-- tem hora. `date` / `purchase_date` continuam sendo a data local.
--
-- So tabelas novas e ADD COLUMN: nenhuma tabela e reconstruida.

CREATE TABLE IF NOT EXISTS inbox_items (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- PENDING: espera o dono; APPROVED: virou lancamento (target);
    -- MATCHED: era um lancamento que ja existia (target); DENIED: recusado;
    -- REMOVED: a unica fonte sumiu (o banco negou a compra).
    state TEXT NOT NULL CHECK (state IN ('PENDING', 'APPROVED', 'MATCHED', 'DENIED', 'REMOVED')),
    reason TEXT,
    -- NULL: a fonte nao diz credito nem debito; o dono decide.
    entry_type TEXT CHECK (entry_type IS NULL OR entry_type IN ('EXPENSE', 'INCOME', 'TRANSFER', 'CARD')),
    -- O dinheiro sai (OUT) ou entra (IN), como a fonte disse.
    direction TEXT NOT NULL CHECK (direction IN ('OUT', 'IN')),
    -- No cartao, o total da compra.
    amount REAL NOT NULL CHECK (amount > 0),
    currency TEXT NOT NULL DEFAULT 'BRL',
    installments INTEGER NOT NULL DEFAULT 1 CHECK (installments BETWEEN 1 AND 72),
    occurred_at TEXT NOT NULL,
    source_occurred_at TEXT NOT NULL,
    description TEXT,
    category TEXT,
    category_id TEXT REFERENCES categories(id) ON DELETE SET NULL,
    account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL,
    card_id TEXT REFERENCES credit_cards(id) ON DELETE SET NULL,
    transfer_account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL,
    -- JSON: o que o dono ainda precisa escolher ("method", "card", "account",
    -- "transfer_account", "amount"), o que foi palpite (nao lembrado) e o que o
    -- dono mudou.
    needs TEXT,
    guessed TEXT,
    edited TEXT,
    -- A chave em inbox_hints que a escolha do cartao/conta deste item lembra.
    hint_key TEXT,
    hint_label TEXT,
    -- JSON: [{"table", "id", "kind"}] dos lancamentos parecidos ja gravados.
    candidates TEXT,
    -- O client_id do lancamento que a aprovacao grava (o dedupKey da primeira
    -- notificacao): confirmar pelo celular depois cai no mesmo lancamento.
    client_key TEXT,
    target_table TEXT CHECK (target_table IS NULL OR target_table IN ('transactions', 'cc_expenses')),
    target_id TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    decided_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_inbox_items_state
ON inbox_items(user_id, state, occurred_at);

CREATE INDEX IF NOT EXISTS idx_inbox_items_target
ON inbox_items(user_id, target_table, target_id);

CREATE TABLE IF NOT EXISTS notify_detections (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    dedup_key TEXT NOT NULL,
    app TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN (
        'CREDIT_PURCHASE', 'DEBIT_PURCHASE', 'PURCHASE', 'PIX_OUT', 'PIX_IN',
        'TRANSFER_OUT', 'TRANSFER_IN', 'REFUND', 'DECLINED'
    )),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    currency TEXT NOT NULL DEFAULT 'BRL',
    installments INTEGER NOT NULL DEFAULT 1,
    -- Milissegundos desde a epoca: a janela do pareamento compara exato.
    posted_ms INTEGER NOT NULL,
    occurred_at TEXT NOT NULL,
    posted_at TEXT NOT NULL,
    merchant TEXT,
    card_last4 TEXT,
    card_name TEXT,
    issuer TEXT,
    -- SOURCE: alimenta um item; PAIRED: a outra notificacao da mesma compra
    -- (o Samsung que o banco superou, ou o banco que chegou depois);
    -- MATCHED: um lancamento que ja existia; DECLINED: compra negada;
    -- CANCELLED: do Samsung, de uma compra que o banco negou.
    role TEXT NOT NULL CHECK (role IN ('SOURCE', 'PAIRED', 'MATCHED', 'DECLINED', 'CANCELLED')),
    paired_with TEXT,
    item_id TEXT REFERENCES inbox_items(id) ON DELETE SET NULL,
    target_table TEXT CHECK (target_table IS NULL OR target_table IN ('transactions', 'cc_expenses')),
    target_id TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (user_id, dedup_key)
);

CREATE INDEX IF NOT EXISTS idx_notify_detections_time
ON notify_detections(user_id, posted_ms);

CREATE INDEX IF NOT EXISTS idx_notify_detections_item
ON notify_detections(user_id, item_id);

CREATE INDEX IF NOT EXISTS idx_notify_detections_target
ON notify_detections(user_id, target_table, target_id);

CREATE TABLE IF NOT EXISTS inbox_hints (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    hint_key TEXT NOT NULL,
    label TEXT,
    entry_type TEXT NOT NULL CHECK (entry_type IN ('EXPENSE', 'INCOME', 'TRANSFER', 'CARD')),
    account_id TEXT REFERENCES accounts(id) ON DELETE CASCADE,
    card_id TEXT REFERENCES credit_cards(id) ON DELETE CASCADE,
    transfer_account_id TEXT REFERENCES accounts(id) ON DELETE CASCADE,
    uses INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (user_id, hint_key)
);

ALTER TABLE transactions ADD COLUMN occurred_at TEXT;
ALTER TABLE cc_expenses ADD COLUMN occurred_at TEXT;
