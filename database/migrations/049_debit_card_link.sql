-- A compra no debito sabe o cartao (dono, 2026-10-28: "debit card purchases
-- should appear together in the same screen").
--
-- Uma compra no debito (041) e uma despesa comum na conta do cartao; ate aqui
-- nada dizia que cartao a fez, e a tela Cartoes nao tinha como lista-la.
-- transactions.card_id: o cartao com a funcao debito que fez esta despesa.
-- Gravado pelo "+ Novo" (POST /api/transactions com card_id) e pelo Aprovar
-- quando a notificacao nomeia o cartao; NULL em todo o resto. Nao muda saldo,
-- total nem orcamento: so agrupa a despesa sob o cartao.
--
-- As linhas antigas ficam NULL; um cartao so debito (o Flash) lista tambem as
-- despesas sem cartao da conta dele (services/debit_purchases.py), entao nada
-- e reescrito aqui.

ALTER TABLE transactions ADD COLUMN card_id TEXT REFERENCES credit_cards(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_transactions_user_card ON transactions (user_id, card_id);
