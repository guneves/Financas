-- Eventos corporativos: desdobramento, grupamento e bonificacao (Fase 6).
--
-- Sem isto, um desdobramento 1:2 deixava a carteira com metade das cotas e o
-- dobro do preco medio, e a venda das cotas novas era recusada ("venda maior
-- que a posicao").
--
-- Desenho: ajuste na gravacao, nao na leitura. Registrar um desdobramento ou
-- grupamento reescala quantidade e preco unitario de cada operacao do ativo
-- anterior a data ex (quantidade x preco fica igual, entao o caixa ligado e o
-- bruto nao mudam); o valor original vai para metadata.corporate_adjustments.
-- Assim FIFO, posicao, validacao de venda, proventos e a evolucao do
-- patrimonio leem a base nova sem saber que houve evento. A bonificacao vira
-- uma operacao BUY de verdade (sem caixa), presa ao evento por
-- bonus_transaction_id, com o custo atribuido informado pela empresa.
--
-- ratio_from -> ratio_to: "1 para 2" no desdobramento (fator 2), "10 para 1"
-- no grupamento (fator 0,1), e na bonificacao "10 para 1" = 1 cota nova para
-- cada 10. adjusted_ids guarda (json) as operacoes e cotacoes reescaladas,
-- para desfazer o evento exatamente. Excluir so vale para o ultimo evento do
-- ativo e sem operacao depois da data ex (a guarda fica no servico).

CREATE TABLE IF NOT EXISTS corporate_actions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL CHECK (action_type IN ('SPLIT', 'REVERSE_SPLIT', 'BONUS')),
    ex_date TEXT NOT NULL,
    ratio_from REAL NOT NULL CHECK (ratio_from > 0),
    ratio_to REAL NOT NULL CHECK (ratio_to > 0),
    bonus_unit_cost REAL CHECK (bonus_unit_cost IS NULL OR bonus_unit_cost >= 0),
    bonus_transaction_id TEXT REFERENCES investment_transactions(id) ON DELETE SET NULL,
    adjusted_ids TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_corporate_actions_user_asset_date
ON corporate_actions(user_id, asset_id, ex_date);
