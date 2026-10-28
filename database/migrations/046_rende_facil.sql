-- Rende Facil do Banco do Brasil (dono, 2026-10-27): a aplicacao automatica da
-- conta corrente nunca entra no app. Daqui em diante place() marca a linha da
-- Pluggy como COVERED (services/open_finance_inbox.py) e o aviso do celular e
-- ignorado (services/inbox.py, is_auto_invest()); aqui, as linhas ja puxadas
-- saem do Aprovar e da conferencia do mesmo jeito. Os lancamentos que elas
-- gravaram nao sao apagados por aqui.

UPDATE open_finance_transactions
SET role = 'COVERED', item_id = NULL
WHERE role <> 'REMOVED'
  AND (UPPER(description) LIKE '%RENDE FACIL%' OR UPPER(description) LIKE '%REND.FACIL%'
       OR UPPER(description) LIKE '%REND FACIL%');

UPDATE inbox_items
SET state = 'DENIED', reason = 'auto_invest', decided_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
WHERE state = 'PENDING'
  AND (UPPER(description) LIKE '%RENDE FACIL%' OR UPPER(description) LIKE '%REND.FACIL%'
       OR UPPER(description) LIKE '%REND FACIL%');
