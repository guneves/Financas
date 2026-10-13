-- Criacao idempotente dos lancamentos do "+ Novo" (despesa, receita,
-- transferencia e compra no cartao).
--
-- O cliente gera um `client_id` por envio e o repete se nao souber se o
-- servidor recebeu (sem rede, fila do celular). Com o indice unico, a segunda
-- entrega nao grava nada: a rota devolve o que a primeira criou.
--
-- Nao e source_type/source_id: source_type vazio continua querendo dizer
-- "digitado", e um lancamento que chegou com client_id foi digitado -- segue
-- editavel e excluivel pelo extrato, e sai como "Manual" na exportacao.
--
-- Uma transferencia e uma linha, entao um id por envio basta. Uma compra
-- parcelada sao N linhas do mesmo envio: todas levam o mesmo client_id, e por
-- isso o indice de cc_expenses inclui a parcela.
--
-- So ADD COLUMN: nenhuma tabela e reconstruida, os indices existentes ficam.

ALTER TABLE transactions ADD COLUMN client_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_user_client
ON transactions(user_id, client_id)
WHERE client_id IS NOT NULL;

ALTER TABLE cc_expenses ADD COLUMN client_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_cc_expenses_user_client
ON cc_expenses(user_id, client_id, installment_info)
WHERE client_id IS NOT NULL;
