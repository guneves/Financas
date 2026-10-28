-- A aplicacao automatica alem do Rende Facil (046; dono, 2026-10-28): a conta
-- remunerada da BTG ("CONTA REMUNERADA - APLICACAO AUTOMATICA", "- RESGATE
-- APLICACAO") e o que a Pluggy chama de "Automatic investment" (03010000)
-- nunca entram no app. Daqui em diante place() marca a linha como COVERED
-- (services/open_finance_inbox.py, is_auto_invest_row()); aqui, as linhas ja
-- puxadas saem do Aprovar e da conferencia do mesmo jeito. Os lancamentos que
-- elas gravaram nao sao apagados por aqui.

UPDATE open_finance_transactions
SET role = 'COVERED', item_id = NULL
WHERE role <> 'REMOVED'
  AND (UPPER(description) LIKE '%CONTA REMUNERADA%' OR pluggy_category_id LIKE '0301%');

UPDATE inbox_items
SET state = 'DENIED', reason = 'auto_invest', decided_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
WHERE state = 'PENDING'
  AND UPPER(description) LIKE '%CONTA REMUNERADA%';
