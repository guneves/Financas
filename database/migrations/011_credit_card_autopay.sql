-- Debito automatico da fatura do cartao.
--
-- Com `autopay_account_id` preenchido, cada fatura do cartao e paga sozinha no
-- dia do vencimento, debitando essa conta (o lancamento nasce em `transactions`
-- com source_type='CC_AUTOPAY' e source_id='<cartao>:<AAAA-MM>', entao rodar de
-- novo nao paga duas vezes). NULL = debito automatico desligado.
--
-- `autopay_start_date` e o dia em que o debito foi ligado: so faturas que
-- vencem a partir dele sao pagas automaticamente. Sem isso, ligar o debito num
-- cartao com faturas antigas em aberto quitaria todas de uma vez, com datas no
-- passado.
--
-- ON DELETE SET NULL: arquivar/apagar a conta desliga o debito, nunca o cartao.

ALTER TABLE credit_cards
ADD COLUMN autopay_account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL;

ALTER TABLE credit_cards
ADD COLUMN autopay_start_date TEXT;
