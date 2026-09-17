-- Orcamento mensal por categoria (3.3 de docs/next-steps.md).
--
-- So e possivel agora que categorias tem id estavel (migration 008): o
-- orcamento e chaveado por (category_id, month) e nao pelo texto da categoria,
-- que muda quando o usuario renomeia.
--
-- month e TEXT 'YYYY-MM' porque e assim que o app ja agrupa mes
-- (substr(date, 1, 7)) e assim ordena alfabeticamente igual a cronologicamente.
--
-- rollover=1 significa "o que sobrou do mes anterior nesta categoria entra
-- neste mes". O saldo transportado e calculado na leitura, nao gravado: gravar
-- exigiria recalcular a cadeia inteira a cada lancamento retroativo.

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
