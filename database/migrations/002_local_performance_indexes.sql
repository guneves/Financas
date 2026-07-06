CREATE INDEX IF NOT EXISTS idx_transactions_user_created_at
ON transactions(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_investments_user_class_ticker
ON investments(user_id, asset_class, ticker_or_name);

CREATE INDEX IF NOT EXISTS idx_investments_user_created_at
ON investments(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_cc_expenses_card_invoice
ON cc_expenses(user_id, card_id, invoice_year, invoice_month);
