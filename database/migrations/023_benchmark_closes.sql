-- Fechamentos dos indices de comparacao da Rentabilidade (Ibovespa, IFIX, IDIV).
--
-- O yfinance entrega o historico mensal do Ibovespa (^BVSP), mas do IFIX e do
-- IDIV so o valor do dia; a brapi gratuita so devolve 3 meses de historico.
-- Guardar cada fechamento visto aqui faz duas coisas: o app abre sem rede com
-- o que ja buscou, e o IFIX/IDIV ganham historico a partir do primeiro dia em
-- que a tela foi aberta (o fechamento de um mes e o ultimo guardado nele).
-- O IPCA vem do BCB como variacao mensal e nao passa por aqui.
--
-- close_date: dia do fechamento; um mes completo vindo do historico mensal
-- do yfinance fica no ultimo dia do mes.
--
-- user_id por convencao do repositorio (toda tabela tem, toda consulta filtra),
-- mesmo sendo dado publico -- mesmo raciocinio de fx_rates (018).

CREATE TABLE IF NOT EXISTS benchmark_closes (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    benchmark TEXT NOT NULL,
    close_date TEXT NOT NULL,
    close REAL NOT NULL CHECK (close > 0),
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (user_id, benchmark, close_date)
);
