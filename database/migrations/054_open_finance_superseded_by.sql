-- Sucessao da Pluggy (2026-11-04, docs/notifications-pluggy-design.md §3.3 passo 0):
-- a transacao PENDING que liquida com outra id passa o lugar (papel, item,
-- lancamento, snapshot) para a nova. A velha fica REMOVED e aponta para a
-- sucessora; nada mais le esta coluna como "viva".
ALTER TABLE open_finance_transactions ADD COLUMN superseded_by TEXT;
