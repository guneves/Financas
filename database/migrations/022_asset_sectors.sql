-- Setor e segmento de cada ativo, para a alocacao por setor (Investimentos > Alocacao).
--
-- Fica em `assets`, que ja e do usuario (user_id), e nao numa tabela global
-- ticker -> setor: o dono pode corrigir o setor de um papel, e essa correcao e
-- dele. A lista da brapi (/quote/list) e cacheada so em memoria, no
-- brapi_client — nenhum dado de usuario sai do escopo dele.
--
-- sector        - o setor mostrado e agrupado (em portugues). NULL = "Sem setor".
-- segment       - o subsetor/segmento (FII: Logistica, Shoppings...), so exibido.
-- sector_source - 'BRAPI' (preenchido automaticamente), 'MANUAL' (o dono
--                 escreveu; a brapi nunca sobrescreve) ou NULL (nada gravado).
-- sector_checked_at - quando a brapi foi consultada para este ativo. NULL com
--                 source NULL = nunca consultado: a leitura da alocacao por
--                 setor tenta preencher. Preenchido com source NULL = a brapi
--                 nao tinha setor; so o "Buscar setores" pergunta de novo.
--
-- A alocacao em si (valor e percentual por setor) e calculada na leitura a
-- partir de build_portfolio_snapshot(), nunca gravada.

ALTER TABLE assets ADD COLUMN sector TEXT;

ALTER TABLE assets ADD COLUMN segment TEXT;

ALTER TABLE assets ADD COLUMN sector_source TEXT
CHECK (sector_source IS NULL OR sector_source IN ('BRAPI', 'MANUAL'));

ALTER TABLE assets ADD COLUMN sector_checked_at TEXT;
