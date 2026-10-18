-- Estorno no cartao (routes/cards.py, POST /api/cc-expenses/refunds): um
-- credito na fatura, que abate o total dela em vez de somar. Fica na mesma
-- tabela das compras para seguir as mesmas regras de fatura (mes, fechamento,
-- pagamento, debito automatico); `amount` continua positivo e `kind` diz o
-- sinal. Um estorno e sempre 1/1 e nunca e dividido (032).
--
-- refund_of: a compra estornada (o id de uma parcela dela), quando o estorno
-- nasceu do menu da compra; so informativo.

ALTER TABLE cc_expenses ADD COLUMN kind TEXT NOT NULL DEFAULT 'PURCHASE'
    CHECK (kind IN ('PURCHASE', 'REFUND'));
ALTER TABLE cc_expenses ADD COLUMN refund_of TEXT;
