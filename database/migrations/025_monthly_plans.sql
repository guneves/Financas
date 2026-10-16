-- Plano do mes (Orcamento > Plano do mes): quanto o usuario decide gastar e
-- investir por mes, em reais, e quanto espera receber (opcional).
--
-- Um plano vale a partir do mes em que foi gravado ate o proximo plano
-- gravado: o mes sem linha propria herda o plano mais recente anterior a ele
-- (resolvido na leitura). Assim o plano e definido uma vez e so muda quando
-- o usuario muda.
--
-- Guarda so o plano. O realizado (gasto e aporte do mes) e os alertas sao
-- calculados na leitura, como em budgets (009) e investment_goals (021).
-- Apagar nao toca em dinheiro, por isso o DELETE e real e sem guarda.

CREATE TABLE IF NOT EXISTS monthly_plans (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    month TEXT NOT NULL CHECK (month GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'),
    spend_amount REAL NOT NULL CHECK (spend_amount >= 0),
    invest_amount REAL NOT NULL CHECK (invest_amount >= 0),
    income_amount REAL CHECK (income_amount IS NULL OR income_amount >= 0),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(user_id, month)
);
