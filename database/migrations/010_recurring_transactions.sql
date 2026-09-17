-- Lancamentos recorrentes (3.4 de docs/next-steps.md).
--
-- Aluguel, salario, mensalidade, assinatura: ate aqui tudo isso era digitado a
-- mao todo mes. Esta tabela guarda o *molde*; o lancamento de verdade continua
-- nascendo em `transactions`, materializado por POST /api/recurring/run.
--
-- Por que materializar em vez de calcular na leitura: um lancamento recorrente
-- ja materializado pode ser editado, apagado ou reconciliado como qualquer
-- outro, e entra no orcamento (009) e no saldo por conta (007) sem que
-- nenhuma dessas consultas precise saber que recorrencia existe.
--
-- A idempotencia vem de graca do indice unico
-- idx_transactions_user_source (007): cada ocorrencia grava
-- source_type='RECURRING_TRANSACTION' e source_id='<recorrencia>:<AAAA-MM-DD>',
-- entao rodar duas vezes no mesmo dia nao duplica nada.
--
-- next_run_date e a proxima ocorrencia AINDA nao materializada. E gravada (e
-- nao derivada) porque e o unico estado que diz ate onde a recorrencia ja
-- andou; apagar um lancamento gerado nao faz a recorrencia voltar atras.

CREATE TABLE IF NOT EXISTS recurring_transactions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL,
    category_id TEXT REFERENCES categories(id) ON DELETE SET NULL,
    category TEXT NOT NULL,
    description TEXT,
    type TEXT NOT NULL CHECK (type IN ('INCOME', 'EXPENSE')),
    amount REAL NOT NULL CHECK (amount > 0),
    frequency TEXT NOT NULL CHECK (frequency IN ('WEEKLY', 'MONTHLY', 'YEARLY')),
    interval_count INTEGER NOT NULL DEFAULT 1 CHECK (interval_count >= 1),
    start_date TEXT NOT NULL,
    next_run_date TEXT,
    end_date TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    last_run_at TEXT,
    note TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK (end_date IS NULL OR end_date >= start_date)
);

-- A fila de trabalho do /run: "o que vence ate hoje, para este usuario".
CREATE INDEX IF NOT EXISTS idx_recurring_user_next_run
ON recurring_transactions(user_id, active, next_run_date);

CREATE INDEX IF NOT EXISTS idx_recurring_user_category
ON recurring_transactions(user_id, category_id);
