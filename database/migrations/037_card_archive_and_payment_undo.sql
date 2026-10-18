-- Cartao arquivado, o pagamento que baixou cada item e o desfazer do pagamento.
--
-- credit_cards.archived_at: excluir um cartao com historico o arquiva, como
-- conta e categoria. O DELETE real apagava (CASCADE) todas as compras dele:
-- os orcamentos passados mudavam e os pagamentos de fatura ficavam presos no
-- Extrato. Um cartao arquivado nao aceita compra, estorno nem aprovacao.
--
-- cc_expenses.paid_by: o lancamento (transactions.id) do pagamento que baixou
-- o item, gravado por settle_invoice(). E o que o desfazer do pagamento
-- reabre; um item PAID sem paid_by (anterior a 037, ou baixado sem
-- lancamento) e reaberto pela fatura do pagamento.
--
-- cc_invoice_manual: fatura cujo pagamento foi desfeito. O debito automatico
-- nao a paga de novo; ela volta para o botao Pagar de Lancamentos > Cartoes.
--
-- So colunas e tabela novas: nenhuma tabela e reconstruida.

ALTER TABLE credit_cards ADD COLUMN archived_at TEXT;
ALTER TABLE cc_expenses ADD COLUMN paid_by TEXT;

CREATE INDEX IF NOT EXISTS idx_cc_expenses_user_paid_by
ON cc_expenses(user_id, paid_by)
WHERE paid_by IS NOT NULL;

CREATE TABLE IF NOT EXISTS cc_invoice_manual (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    card_id TEXT NOT NULL REFERENCES credit_cards(id) ON DELETE CASCADE,
    invoice_year INTEGER NOT NULL,
    invoice_month INTEGER NOT NULL CHECK (invoice_month BETWEEN 1 AND 12),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (user_id, card_id, invoice_year, invoice_month)
);
