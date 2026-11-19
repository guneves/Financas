-- Tudo automatico (dono, 2026-11-18, docs/automation-prompt.md): o que o app
-- antes perguntava, agora decide por uma regra escrita. Cada decisao fica aqui,
-- visivel e desfazivel: `kind` diz qual regra, `detail` (JSON) guarda o antes
-- para o "Desfazer", `undone_at` marca o desfeito (e a regra nao volta a
-- decidir o mesmo lancamento).
CREATE TABLE IF NOT EXISTS auto_decisions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    target_table TEXT,
    target_id TEXT,
    detail TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    undone_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_auto_decisions_user ON auto_decisions (user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_auto_decisions_target ON auto_decisions (user_id, target_table, target_id);

-- Conflitos que se resolvem sozinhos (automation-prompt 1.4): quando a
-- Conferencia passou a apontar o conflito. O `changed` espera 7 dias.
ALTER TABLE open_finance_transactions ADD COLUMN conflict_at TEXT;
UPDATE open_finance_transactions SET conflict_at = updated_at WHERE conflict IS NOT NULL;
-- A direcao que o banco mostrou no `changed` (o valor so se aplica na mesma).
ALTER TABLE open_finance_transactions ADD COLUMN conflict_direction TEXT;
