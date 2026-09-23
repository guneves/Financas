-- Cambio para ativos e contas em moeda estrangeira (Fase 6, multimoeda).
--
-- assets.currency e accounts.currency existiam desde o inicio, mas nada
-- convertia: uma acao em dolar entrava no patrimonio como se US$ fosse R$.
-- A cotacao de referencia e a PTAX de venda do Banco Central (SGS 1 = dolar,
-- 21619 = euro, 21623 = libra), guardada por dia aqui para o app abrir sem
-- rede e para o custo de cada compra usar o cambio da data dela.
--
-- user_id por convencao do repositorio (toda tabela tem, toda consulta filtra),
-- mesmo sendo dado publico: num app de um usuario a copia nao pesa.

CREATE TABLE IF NOT EXISTS fx_rates (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    currency TEXT NOT NULL,
    rate_date TEXT NOT NULL,
    rate REAL NOT NULL CHECK (rate > 0),
    source TEXT NOT NULL DEFAULT 'bcb_ptax',
    fetched_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (user_id, currency, rate_date)
);
