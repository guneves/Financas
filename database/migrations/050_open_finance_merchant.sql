-- Identificar melhor o que a Pluggy traz (2026-10-30): o comerciante da
-- transacao (merchant.name/businessName, cnpj, cnae) decide o nome legivel do
-- lancamento e a categoria (open_finance_categories.py). posted_on e o dia em
-- que a transacao caiu na conta ou na fatura; `date` e o dia da compra quando a
-- Pluggy o manda, entao os dois iguais numa parcela 2..n dizem que o conector
-- nao mandou a data da compra.

ALTER TABLE open_finance_transactions ADD COLUMN merchant_name TEXT;
ALTER TABLE open_finance_transactions ADD COLUMN merchant_cnpj TEXT;
ALTER TABLE open_finance_transactions ADD COLUMN merchant_cnae TEXT;
ALTER TABLE open_finance_transactions ADD COLUMN posted_on TEXT;
