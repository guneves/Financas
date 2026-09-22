-- Importacao de extrato e regras de categorizacao (Fase 4 de docs/next-steps.md).
--
-- Digitar o extrato do banco a mao e o maior atrito que sobrou no uso diario.
-- A importacao le CSV (mapeamento de colunas configuravel) ou OFX e grava
-- lancamentos normais em `transactions` — nada aqui guarda dinheiro.
--
-- Idempotencia: cada linha importada grava source_type='STATEMENT_IMPORT' e
-- source_id = hash(conta + data + valor + descricao normalizada), ou
-- 'ofx:<conta>:<FITID>' quando o arquivo traz o identificador do banco. O
-- indice unico idx_transactions_user_source (007) faz a reimportacao do mesmo
-- arquivo ser um no-op, a mesma forma que recorrencias e debito automatico
-- usam. Duas linhas identicas no mesmo arquivo (dois cafes iguais no mesmo
-- dia) recebem sufixo de ocorrencia, entao elas nao se anulam.
--
-- import_rules e a categorizacao automatica: "descricao contem X -> categoria
-- Y". Ela roda na previa da importacao, nunca na gravacao direta de um
-- lancamento; o dono ainda ve e pode trocar a categoria linha por linha.
--
-- category (texto) e category_id andam juntos pelo mesmo motivo de 008: o nome
-- e o que sobrevive ao arquivamento da categoria.

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
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- A fila de avaliacao da previa: "regras ativas deste usuario, na ordem".
CREATE INDEX IF NOT EXISTS idx_import_rules_user_priority
ON import_rules(user_id, active, priority DESC);

-- Mesma regra duas vezes nao acrescenta nada e torna a ordem imprevisivel.
CREATE UNIQUE INDEX IF NOT EXISTS idx_import_rules_user_pattern
ON import_rules(user_id, pattern, match_type, applies_to);
