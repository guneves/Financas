-- A funcao debito de um cartao (dono, 2026-10-22: "create the function débito
-- when creating a card").
--
-- credit_cards.debit_account_id: a conta de onde sai uma compra no debito
-- deste cartao. Uma compra no debito nao e um item de fatura: e uma despesa
-- comum (transactions, EXPENSE) nessa conta. NULL = o cartao nao tem debito.
--
-- credit_cards.credit_enabled: 0 = so debito (o cartao de beneficios, como o
-- Flash, ou um cartao de debito puro). Ele nao tem fatura, nao aceita compra
-- parcelada, estorno nem debito automatico; due_day e closing_day (NOT NULL
-- desde a tabela original) guardam 1 e nunca sao lidos. Todo cartao tem ao
-- menos uma funcao: credit_enabled = 1 ou debit_account_id preenchido.
--
-- So colunas novas: nenhuma tabela e reconstruida.

ALTER TABLE credit_cards ADD COLUMN debit_account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL;
ALTER TABLE credit_cards ADD COLUMN credit_enabled INTEGER NOT NULL DEFAULT 1 CHECK (credit_enabled IN (0, 1));
