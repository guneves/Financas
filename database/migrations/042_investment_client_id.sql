-- Criacao idempotente das operacoes, proventos e eventos corporativos, como o
-- "+ Novo" (024): o cliente gera um `client_id` por envio e o repete se nao
-- souber se o servidor recebeu (sem rede, fila do celular). A segunda entrega
-- nao grava nada: a rota devolve o que a primeira criou.
--
-- Um envio pode gravar varias linhas (uma lista de operacoes, um resgate do
-- Tesouro em PEPS, um provento com `repeat`): todas levam o mesmo client_id e
-- `client_part` e a posicao da linha no envio (0, 1, ...), por isso o indice
-- unico inclui a parte, como o de cc_expenses inclui a parcela.
--
-- Um evento corporativo e uma linha so; a compra de bonificacao que ele cria
-- e dele (bonus_transaction_id), sem client_id proprio.
--
-- So ADD COLUMN: nenhuma tabela e reconstruida, os indices existentes ficam.

ALTER TABLE investment_transactions ADD COLUMN client_id TEXT;
ALTER TABLE investment_transactions ADD COLUMN client_part INTEGER;

CREATE UNIQUE INDEX IF NOT EXISTS idx_investment_transactions_user_client
ON investment_transactions(user_id, client_id, client_part)
WHERE client_id IS NOT NULL;

ALTER TABLE investment_proceeds ADD COLUMN client_id TEXT;
ALTER TABLE investment_proceeds ADD COLUMN client_part INTEGER;

CREATE UNIQUE INDEX IF NOT EXISTS idx_investment_proceeds_user_client
ON investment_proceeds(user_id, client_id, client_part)
WHERE client_id IS NOT NULL;

ALTER TABLE corporate_actions ADD COLUMN client_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_corporate_actions_user_client
ON corporate_actions(user_id, client_id)
WHERE client_id IS NOT NULL;
