-- Conferencia: o dono diz que um lancamento que o banco nao mostra aconteceu
-- mesmo (dono, 2026-10-30). A linha sai de "so no app" e fica listada a parte.
CREATE TABLE IF NOT EXISTS open_finance_confirmed (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_table TEXT NOT NULL CHECK (target_table IN ('transactions', 'cc_expenses')),
    target_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (user_id, target_table, target_id)
);

-- A fatura que o banco diz (billForecastDate da Pluggy, AAAA-MM): manda sobre a conta
-- do app numa compra que veio dele (open_finance_invoices.mirror_cards()).
ALTER TABLE open_finance_transactions ADD COLUMN bill_month TEXT;
