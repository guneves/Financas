-- Open Finance gravado sozinho (dono, 2026-10-27): para uma conta conectada e
-- mapeada, o movimento da Pluggy vira lancamento (ou compra no cartao) sem
-- passar pelo Aprovar (services/open_finance_auto.py). O interruptor e uma
-- preferencia em user_settings (`open_finance_auto_record`), como as outras.
--
-- open_finance_accounts.ignored_at: a conta "nao usar" (o segundo Ourocard sem
--   movimento): fica puxada, nunca gera nada, e conta como resolvida para ligar
--   o interruptor.
-- open_finance_accounts.account_id pode apontar para a Corretora: a conta
--   "BTG Investimentos" da Pluggy e o caixa da carteira. Os movimentos dela
--   nunca viram lancamento por aqui (COVERED: as operacoes da carteira os
--   explicam), salvo a transferencia do/para o banco, que e aporte/resgate (039).
-- open_finance_transactions.auto_recorded_at: o lancamento foi gravado sozinho.
--   recorded_snapshot (JSON) e como ele nasceu: se o banco mudar o valor ou a
--   transacao sumir, so um lancamento igual ao snapshot (o dono nao editou) e
--   corrigido ou apagado; editado, fica `conflict` e a Conferencia aponta.

ALTER TABLE open_finance_accounts ADD COLUMN ignored_at TEXT;

ALTER TABLE open_finance_transactions ADD COLUMN auto_recorded_at TEXT;
ALTER TABLE open_finance_transactions ADD COLUMN recorded_snapshot TEXT;
ALTER TABLE open_finance_transactions ADD COLUMN conflict TEXT
    CHECK (conflict IS NULL OR conflict IN ('changed', 'vanished'));
ALTER TABLE open_finance_transactions ADD COLUMN conflict_amount_cents INTEGER;

-- Investimentos pela Pluggy (BTG Investimentos): cada operacao da corretora,
-- unica por usuario pela chave dela; investment_id e a movimentacao que ela
-- gravou ou ligou (a digitada pelo dono antes). state: RECORDED (gravada aqui),
-- LINKED (ja existia), HELD (nao gravada: um evento corporativo depois dela,
-- tipo que o app nao grava sozinho, ativo desconhecido), DISMISSED (o dono
-- desfez: nunca volta).
CREATE TABLE IF NOT EXISTS open_finance_investment_operations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    of_item_id TEXT NOT NULL REFERENCES open_finance_items(id) ON DELETE CASCADE,
    op_key TEXT NOT NULL,
    pluggy_investment_id TEXT NOT NULL,
    code TEXT,
    name TEXT,
    pluggy_type TEXT,
    op_type TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    quantity REAL,
    unit_price REAL,
    amount REAL,
    net_amount REAL,
    expenses REAL,
    state TEXT NOT NULL CHECK (state IN ('RECORDED', 'LINKED', 'HELD', 'DISMISSED')),
    held_reason TEXT,
    investment_id TEXT REFERENCES investment_transactions(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (user_id, op_key)
);

CREATE INDEX IF NOT EXISTS idx_open_finance_investment_operations_investment
ON open_finance_investment_operations(user_id, investment_id);

-- As posicoes como a Pluggy as viu no ultimo pull (a conferencia da carteira).
CREATE TABLE IF NOT EXISTS open_finance_positions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    of_item_id TEXT NOT NULL REFERENCES open_finance_items(id) ON DELETE CASCADE,
    pluggy_investment_id TEXT NOT NULL,
    code TEXT,
    name TEXT,
    pluggy_type TEXT,
    subtype TEXT,
    quantity REAL,
    unit_value REAL,
    balance REAL,
    status TEXT,
    position_date TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (user_id, pluggy_investment_id)
);
