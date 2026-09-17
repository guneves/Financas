-- Categorias como dados (3.2 de docs/next-steps.md).
--
-- CATEGORY_OPTIONS vivia hardcoded em frontend/src/pages/Transactions.jsx com
-- 10 valores fixos, sem renomear, criar ou agrupar. Aqui elas viram tabela,
-- com subcategorias via parent_id.
--
-- A coluna transactions.category (texto) NAO sai: ela continua sendo o valor
-- gravado e o fallback para qualquer linha cuja categoria tenha sido apagada.
-- category_id e a ligacao nova, opcional.

CREATE TABLE IF NOT EXISTS categories (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'EXPENSE' CHECK (kind IN ('INCOME', 'EXPENSE', 'BOTH')),
    parent_id TEXT REFERENCES categories(id) ON DELETE SET NULL,
    color TEXT,
    icon TEXT,
    archived_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(user_id, name, parent_id)
);

CREATE INDEX IF NOT EXISTS idx_categories_user_name
ON categories(user_id, name);

CREATE INDEX IF NOT EXISTS idx_categories_user_parent
ON categories(user_id, parent_id);

-- UNIQUE(user_id, name, parent_id) nao cobre as categorias raiz: no SQLite dois
-- NULL sao distintos, entao sem este indice parcial daria para criar "Lazer"
-- duas vezes no topo.
CREATE UNIQUE INDEX IF NOT EXISTS idx_categories_user_root_name
ON categories(user_id, name)
WHERE parent_id IS NULL;

ALTER TABLE transactions ADD COLUMN category_id TEXT REFERENCES categories(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_transactions_user_category_id_date
ON transactions(user_id, category_id, date DESC);

-- As 10 categorias que estavam no frontend, uma vez por usuario existente.
INSERT OR IGNORE INTO categories (id, user_id, name, kind)
SELECT 'cat:' || u.id || ':receita',      u.id, 'Receita',      'INCOME'  FROM users u
UNION ALL
SELECT 'cat:' || u.id || ':investimento', u.id, 'Investimento', 'BOTH'    FROM users u
UNION ALL
SELECT 'cat:' || u.id || ':alimentacao',  u.id, 'Alimentação',  'EXPENSE' FROM users u
UNION ALL
SELECT 'cat:' || u.id || ':moradia',      u.id, 'Moradia',      'EXPENSE' FROM users u
UNION ALL
SELECT 'cat:' || u.id || ':transporte',   u.id, 'Transporte',   'EXPENSE' FROM users u
UNION ALL
SELECT 'cat:' || u.id || ':saude',        u.id, 'Saúde',        'EXPENSE' FROM users u
UNION ALL
SELECT 'cat:' || u.id || ':educacao',     u.id, 'Educação',     'EXPENSE' FROM users u
UNION ALL
SELECT 'cat:' || u.id || ':lazer',        u.id, 'Lazer',        'EXPENSE' FROM users u
UNION ALL
SELECT 'cat:' || u.id || ':servicos',     u.id, 'Serviços',     'EXPENSE' FROM users u
UNION ALL
SELECT 'cat:' || u.id || ':outros',       u.id, 'Outros',       'EXPENSE' FROM users u;

-- Qualquer outra categoria ja usada em transactions vira registro tambem, para
-- que nenhum lancamento historico fique orfao do novo cadastro.
INSERT OR IGNORE INTO categories (id, user_id, name, kind)
SELECT
    'cat:' || t.user_id || ':legacy:' || LOWER(HEX(t.category)),
    t.user_id,
    t.category,
    'BOTH'
FROM (SELECT DISTINCT user_id, category FROM transactions WHERE category <> '') t
WHERE NOT EXISTS (
    SELECT 1 FROM categories c
    WHERE c.user_id = t.user_id AND c.name = t.category
);

UPDATE transactions
SET category_id = (
    SELECT c.id FROM categories c
    WHERE c.user_id = transactions.user_id AND c.name = transactions.category
    LIMIT 1
)
WHERE category_id IS NULL;
