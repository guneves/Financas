-- Sem Pluggy (2026-10-17, pedido do dono: o plano gratuito nao da acesso a
-- nada). O que 027 e 028 criaram para ela sai; as migrations antigas ficam como
-- estao (append-only).
--
-- - Um item de Aprovar pendente que so a Pluggy trouxe sai da lista (REMOVED),
--   como quando a fonte some; um que tem notificacao fica.
-- - Um lancamento que nasceu da Pluggy vira digitado ("Manual"): continua no
--   extrato, editavel e apagavel.
-- - external_id (transactions, cc_expenses) e source_type/source_id de
--   cc_expenses so a Pluggy usava: saem com seus indices.

UPDATE inbox_items
SET state = 'REMOVED', reason = 'bank_removed', decided_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
    version = version + 1, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
WHERE state = 'PENDING'
  AND id IN (SELECT inbox_item_id FROM pluggy_transactions WHERE inbox_item_id IS NOT NULL)
  AND NOT EXISTS (
      SELECT 1 FROM notify_detections d
      WHERE d.user_id = inbox_items.user_id AND d.item_id = inbox_items.id AND d.role = 'SOURCE'
  );

UPDATE transactions SET source_type = NULL, source_id = NULL WHERE source_type = 'PLUGGY';

DROP INDEX IF EXISTS idx_pluggy_transactions_inbox;
DROP INDEX IF EXISTS idx_pluggy_transactions_state;
DROP INDEX IF EXISTS idx_pluggy_transactions_account_date;
DROP INDEX IF EXISTS idx_pluggy_transactions_target;
DROP TABLE IF EXISTS pluggy_transactions;
DROP TABLE IF EXISTS pluggy_account_links;
DROP TABLE IF EXISTS pluggy_items;

DROP INDEX IF EXISTS idx_transactions_user_external;
ALTER TABLE transactions DROP COLUMN external_id;

DROP INDEX IF EXISTS idx_cc_expenses_user_external;
DROP INDEX IF EXISTS idx_cc_expenses_user_source;
ALTER TABLE cc_expenses DROP COLUMN external_id;
ALTER TABLE cc_expenses DROP COLUMN source_type;
ALTER TABLE cc_expenses DROP COLUMN source_id;
