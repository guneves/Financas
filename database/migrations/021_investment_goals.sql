-- Metas financeiras (Planejamento > Metas).
--
-- kind:
--   PORTFOLIO      - valor liquido da carteira de investimentos;
--   NET_WORTH      - patrimonio: carteira + saldo das contas (o numero do Inicio);
--   ASSET_CLASS    - valor liquido de uma classe (asset_class obrigatorio);
--   MONTHLY_INCOME - media mensal de proventos liquidos dos ultimos 12 meses.
--
-- Guarda so o plano: alvo, aporte mensal previsto, rentabilidade anual
-- esperada (opcional, para a previsao) e data desejada (opcional). O valor
-- atual, o progresso e a data estimada sao calculados na leitura — gravar
-- exigiria recalcular a cada cotacao. Apagar uma meta nao toca em dinheiro,
-- por isso o DELETE e real (mesma natureza de budgets, 009).

CREATE TABLE IF NOT EXISTS investment_goals (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('PORTFOLIO', 'NET_WORTH', 'ASSET_CLASS', 'MONTHLY_INCOME')),
    asset_class TEXT CHECK (asset_class IS NULL OR asset_class IN ('STOCKS', 'FIXED_INCOME', 'REIT', 'CATTLE', 'OTHER')),
    target_amount REAL NOT NULL CHECK (target_amount > 0),
    monthly_contribution REAL NOT NULL DEFAULT 0 CHECK (monthly_contribution >= 0),
    annual_return_percent REAL CHECK (annual_return_percent IS NULL OR (annual_return_percent > -100 AND annual_return_percent <= 100)),
    target_date TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK ((kind = 'ASSET_CLASS') = (asset_class IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_investment_goals_user
ON investment_goals(user_id, created_at);
