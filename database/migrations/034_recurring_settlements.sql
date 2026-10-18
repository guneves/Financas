-- Aprovar x Recorrentes: uma ocorrencia feita por um lancamento aprovado.
--
-- A notificacao da assinatura (compra no cartao) ou do salario (Pix recebido)
-- chega em Aprovar; o item mostra a recorrencia que ela parece ser, e aprovar
-- grava o lancamento da notificacao E da a ocorrencia como feita. O /run nao
-- grava essa data (o dinheiro ja esta no lancamento aprovado, com o valor e o
-- cartao/conta de verdade), ela deixa de contar como pendente e sai da
-- previsao. A recorrencia continua um molde: nada aqui e dinheiro.
--
-- target_* e o lancamento que fez a ocorrencia (transactions ou a primeira
-- parcela em cc_expenses); apaga-lo nao faz a ocorrencia voltar a dever, como
-- apagar um lancamento gerado pelo /run tambem nao faz.
--
-- inbox_items.recurring_off: o dono disse "nao e esta recorrencia" no item;
-- aprovar (inclusive pelo "Aprovar todos") nao marca nada.

CREATE TABLE IF NOT EXISTS recurring_settlements (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recurring_id TEXT NOT NULL REFERENCES recurring_transactions(id) ON DELETE CASCADE,
    occurrence_date TEXT NOT NULL,
    target_table TEXT CHECK (target_table IS NULL OR target_table IN ('transactions', 'cc_expenses')),
    target_id TEXT,
    inbox_item_id TEXT REFERENCES inbox_items(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_recurring_settlements_occurrence
ON recurring_settlements(user_id, recurring_id, occurrence_date);

CREATE INDEX IF NOT EXISTS idx_recurring_settlements_item
ON recurring_settlements(user_id, inbox_item_id);

ALTER TABLE inbox_items ADD COLUMN recurring_off INTEGER NOT NULL DEFAULT 0;
