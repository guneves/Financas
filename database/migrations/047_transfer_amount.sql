-- Conta global (dono, 2026-10-27): a conta em dolar (Wise) recebe Pix de uma
-- conta em reais. Uma transferencia continua uma linha so, mas entre moedas o
-- que sai e o que entra sao valores diferentes.
--
-- transactions.transfer_amount: o valor que entra em transfer_account_id, na
--   moeda dela. NULL = o mesmo `amount` (toda transferencia entre contas da
--   mesma moeda, ou seja, todas as de antes). `amount` e sempre o que sai de
--   account_id, na moeda dela.
-- inbox_items.transfer_amount: o mesmo para o item que vai virar a
--   transferencia (a ponta da Pluggy na conta global traz o valor em dolar).

ALTER TABLE transactions ADD COLUMN transfer_amount REAL CHECK (transfer_amount IS NULL OR transfer_amount > 0);
ALTER TABLE inbox_items ADD COLUMN transfer_amount REAL;
