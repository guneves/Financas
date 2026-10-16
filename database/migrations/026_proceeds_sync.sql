-- Proventos automaticos: a posicao na data com vezes o valor por cota que a
-- StatusInvest publica (services/proceeds_sync.py).
--
-- `sync_key` identifica o evento na fonte ('<ticker>:<tipo>:<data com>:<pagamento>#n');
-- o indice unico faz uma segunda sincronizacao nao gravar nada de novo, como
-- source_type/source_id nas recorrencias. Linha digitada pelo dono fica com
-- sync_key NULL e a sincronizacao nunca toca nela.
--
-- `sync_locked` = 1 quando o dono editou um provento automatico: a
-- sincronizacao deixa de recalcular aquela linha.
--
-- Um provento automatico excluido pelo dono fica em proceeds_sync_dismissed,
-- para nao voltar na proxima sincronizacao.

ALTER TABLE investment_proceeds ADD COLUMN sync_key TEXT;
ALTER TABLE investment_proceeds ADD COLUMN sync_locked INTEGER NOT NULL DEFAULT 0;

CREATE UNIQUE INDEX IF NOT EXISTS idx_investment_proceeds_user_sync_key
ON investment_proceeds(user_id, sync_key)
WHERE sync_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS proceeds_sync_dismissed (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sync_key TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (user_id, sync_key)
);
