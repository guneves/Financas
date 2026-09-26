-- Alocacao alvo da carteira ("% ideal"): quanto de cada classe, e de cada
-- ativo dentro da classe, o dono quer ter.
--
-- Dois niveis, como a carteira e lida:
--   scope = 'CLASS': percentual da carteira inteira (asset_id nulo);
--   scope = 'ASSET': percentual DENTRO da classe do ativo.
-- Assim mudar a meta de Acoes de 60% para 50% nao obriga a refazer a meta de
-- cada acao. As somas (100% entre as classes, 100% dentro de cada classe com
-- meta por ativo) sao validadas no PUT, que troca o conjunto inteiro de uma
-- vez — linha a linha a soma nunca fecha.
--
-- E um plano, nao um registro (mesma natureza de budgets, 009): o PUT
-- substitui tudo e apagar nao destroi nenhum lancamento. O valor atual, a
-- diferenca e a sugestao de aporte sao calculados na leitura, nunca gravados.

CREATE TABLE IF NOT EXISTS allocation_targets (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scope TEXT NOT NULL CHECK (scope IN ('CLASS', 'ASSET')),
    asset_class TEXT NOT NULL CHECK (asset_class IN ('STOCKS', 'FIXED_INCOME', 'REIT', 'CATTLE', 'OTHER')),
    asset_id TEXT REFERENCES assets(id) ON DELETE CASCADE,
    target_percent REAL NOT NULL CHECK (target_percent >= 0 AND target_percent <= 100),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK ((scope = 'CLASS' AND asset_id IS NULL) OR (scope = 'ASSET' AND asset_id IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_allocation_targets_user_key
ON allocation_targets(user_id, scope, asset_class, COALESCE(asset_id, ''));
