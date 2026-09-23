-- Comprovantes de compras no cartao.
--
-- Ate aqui um comprovante so podia ir num lancamento do extrato (014), e uma
-- compra no cartao so chega ao extrato como o pagamento da fatura inteira. A
-- nota do mercado ficava pendurada no pagamento de um mes com quarenta compras.
--
-- Mesmo desenho de 014: a linha referencia, o arquivo mora em
-- ATTACHMENTS_DIR/<user_id>/<stored_name> (o mesmo diretorio, stored_name
-- unico entre as duas tabelas porque e um uuid). Tabela propria em vez de
-- afrouxar transaction_attachments.transaction_id: aquela coluna e NOT NULL e
-- mudar isso exigiria reconstruir a tabela.
--
-- Uma compra parcelada sao N linhas de cc_expenses sem id de compra; o
-- comprovante fica preso a parcela em que foi anexado e a API lista os
-- comprovantes de todas as parcelas da mesma compra (cartao, descricao, data,
-- categoria — a mesma chave de /api/cc-expenses/candidates). ON DELETE CASCADE:
-- excluir a compra (todas as parcelas) leva as linhas; os arquivos saem pela
-- rota ou pela varredura de boot.

CREATE TABLE IF NOT EXISTS cc_expense_attachments (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    cc_expense_id TEXT NOT NULL REFERENCES cc_expenses(id) ON DELETE CASCADE,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL UNIQUE,
    content_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes > 0),
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_cc_expense_attachments_user_expense
ON cc_expense_attachments(user_id, cc_expense_id);
