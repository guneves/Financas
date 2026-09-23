-- Condicoes de valor e de conta numa regra de importacao.
--
-- "UBER" acima de R$ 80 e viagem, abaixo e transporte; "PIX RECEBIDO" na conta
-- da empresa e receita do trabalho, na pessoal nao. O texto sozinho nao separa
-- esses casos. As tres colunas sao opcionais e somam restricoes: uma regra so
-- casa quando o texto casa E o valor cabe na faixa E a conta e a da regra.
--
-- amount_min / amount_max comparam o valor absoluto do lancamento (o extrato
-- guarda o valor positivo e a natureza em `type`), os dois inclusivos.
-- account_id e a conta do lancamento (na previa, a conta de destino da
-- importacao). ON DELETE SET NULL segue 007: contas sao arquivadas, nunca
-- apagadas, e uma regra que perde a conta volta a valer para todas.
--
-- O indice unico de 013 impedia "UBER" duas vezes mesmo com faixas diferentes;
-- ele passa a incluir as condicoes. COALESCE porque no SQLite NULLs sao
-- distintos num indice unico, e duas regras sem condicao seriam aceitas.

ALTER TABLE import_rules ADD COLUMN amount_min REAL;
ALTER TABLE import_rules ADD COLUMN amount_max REAL;
ALTER TABLE import_rules ADD COLUMN account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL;

DROP INDEX IF EXISTS idx_import_rules_user_pattern;

CREATE UNIQUE INDEX IF NOT EXISTS idx_import_rules_user_pattern
ON import_rules(
    user_id, pattern, match_type, applies_to,
    COALESCE(amount_min, -1), COALESCE(amount_max, -1), COALESCE(account_id, '')
);
