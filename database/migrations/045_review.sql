-- Gravar sozinho e revisar (dono, 2026-10-27): a notificacao do celular e a
-- transacao da Pluggy viram lancamento na hora, sem esperar o Aprovar; o
-- trabalho do dono passa a ser so revisar: dizer que e dele e confirmar a
-- categoria (services/review.py, GET/POST /api/review).
--
-- needs_review = 1: gravado sozinho (services/auto_record.py,
--   services/open_finance_auto.py) e ainda nao revisado. Tudo o que o dono
--   digita, e o que outra tela gera (recorrencia, fatura, carteira), nasce 0.
--   Numa compra no cartao, todas as parcelas (o client_id) levam o mesmo valor.
-- inbox_items.auto_recorded_at / recorded_snapshot: o item que uma notificacao
--   gravou sozinha e como o lancamento nasceu (o mesmo JSON de
--   open_finance_transactions.recorded_snapshot): quando a Pluggy traz o mesmo
--   movimento com outra data ou outra conta/cartao, so o intocado (igual ao
--   snapshot e ainda a revisar) e refeito do jeito do banco.

ALTER TABLE transactions ADD COLUMN needs_review INTEGER NOT NULL DEFAULT 0;
ALTER TABLE cc_expenses ADD COLUMN needs_review INTEGER NOT NULL DEFAULT 0;
ALTER TABLE inbox_items ADD COLUMN auto_recorded_at TEXT;
ALTER TABLE inbox_items ADD COLUMN recorded_snapshot TEXT;

CREATE INDEX IF NOT EXISTS idx_transactions_user_review
    ON transactions (user_id, needs_review) WHERE needs_review = 1;
CREATE INDEX IF NOT EXISTS idx_cc_expenses_user_review
    ON cc_expenses (user_id, needs_review) WHERE needs_review = 1;
