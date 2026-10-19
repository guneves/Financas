-- Investimento deixa de ser categoria (dono, 2026-10-19).
--
-- Ate aqui um lancamento era aporte/resgate por tres caminhos: o caixa de uma
-- operacao (source_type INVESTMENT_TRANSACTION), o provento pago na conta da
-- carteira (INVESTMENT_PROCEED) e qualquer despesa/receita digitada na
-- categoria "Investimento" — comparada pelo nome, entao renomear ou arquivar a
-- categoria fazia os aportes contarem como gasto. Agora o que decide e o
-- proprio lancamento: a origem (source_type) ou a transferencia entre uma
-- conta do banco e uma conta Corretora.
--
--   1. A despesa/receita em "Investimento" vira transferencia com a Corretora
--      (a despesa sai da conta para a Corretora; a receita volta da Corretora
--      para a conta). O saldo da conta do banco nao muda. A Corretora e a da
--      carteira (padrao primeiro, depois o nome — portfolio_cash_account_id());
--      quem nao tem uma ganha "Corretora", saldo inicial 0. Fica como esta a
--      linha que ja esta na propria Corretora ou numa conta que nao e em reais.
--   2. O caixa das operacoes e os proventos pagos perdem a categoria: o texto
--      vira "Aporte", "Resgate" ou "Provento", sem category_id, como a
--      "Transferencia" das transferencias.
--   3. A categoria "Investimento" da raiz e arquivada (nunca apagada). As
--      regras de importacao que a escolhiam sao desligadas; um item pendente
--      do Aprovar nela volta para a categoria padrao da importacao.
--
-- Nao havia recorrencia em "Investimento" (dono); uma que exista fica com a
-- categoria arquivada e lanca uma despesa comum.

CREATE TEMP TABLE m039_categories AS
SELECT id, user_id FROM categories
WHERE name = 'Investimento' AND parent_id IS NULL;

CREATE TEMP TABLE m039_rows AS
SELECT t.id, t.user_id, t.account_id, t.type
FROM transactions t
JOIN accounts a ON a.id = t.account_id AND a.user_id = t.user_id
WHERE t.type IN ('EXPENSE', 'INCOME')
  AND COALESCE(t.source_type, '') NOT IN ('INVESTMENT_TRANSACTION', 'INVESTMENT_PROCEED')
  AND (
    t.category_id IN (SELECT id FROM m039_categories WHERE user_id = t.user_id)
    OR (t.category_id IS NULL AND t.category = 'Investimento')
  )
  AND a.currency = 'BRL';

-- Corretora para quem tem o que converter e nenhuma ativa em reais.
INSERT OR IGNORE INTO accounts (id, user_id, name, type, currency, initial_balance, is_default)
SELECT
    'acct:' || u.id || ':corretora',
    u.id,
    CASE WHEN EXISTS (SELECT 1 FROM accounts x WHERE x.user_id = u.id AND x.name = 'Corretora')
         THEN 'Corretora (carteira)' ELSE 'Corretora' END,
    'BROKERAGE',
    'BRL',
    0,
    0
FROM users u
WHERE EXISTS (SELECT 1 FROM m039_rows r WHERE r.user_id = u.id)
  AND NOT EXISTS (
    SELECT 1 FROM accounts b
    WHERE b.user_id = u.id AND b.type = 'BROKERAGE' AND b.currency = 'BRL' AND b.archived_at IS NULL
  );

CREATE TEMP TABLE m039_portfolio AS
SELECT u.id AS user_id, (
    SELECT b.id FROM accounts b
    WHERE b.user_id = u.id AND b.type = 'BROKERAGE' AND b.currency = 'BRL' AND b.archived_at IS NULL
    ORDER BY b.is_default DESC, b.name COLLATE NOCASE, b.created_at, b.id
    LIMIT 1
) AS account_id
FROM users u;

UPDATE transactions
SET type = 'TRANSFER',
    account_id = CASE WHEN transactions.type = 'EXPENSE' THEN transactions.account_id
                      ELSE (SELECT p.account_id FROM m039_portfolio p WHERE p.user_id = transactions.user_id) END,
    transfer_account_id = CASE WHEN transactions.type = 'EXPENSE'
                               THEN (SELECT p.account_id FROM m039_portfolio p WHERE p.user_id = transactions.user_id)
                               ELSE transactions.account_id END,
    category = 'Transferencia',
    category_id = NULL,
    share_mode = NULL,
    share_others_amount = NULL,
    share_person = NULL,
    share_settled_at = NULL
WHERE id IN (
    SELECT r.id FROM m039_rows r
    JOIN m039_portfolio p ON p.user_id = r.user_id
    WHERE p.account_id IS NOT NULL AND p.account_id <> r.account_id
);

UPDATE transactions
SET category = CASE
        WHEN source_type = 'INVESTMENT_PROCEED' THEN 'Provento'
        WHEN type = 'EXPENSE' THEN 'Aporte'
        ELSE 'Resgate'
    END,
    category_id = NULL
WHERE source_type IN ('INVESTMENT_TRANSACTION', 'INVESTMENT_PROCEED');

UPDATE import_rules
SET active = 0
WHERE category_id IN (SELECT id FROM m039_categories)
   OR (category_id IS NULL AND category = 'Investimento');

UPDATE inbox_items
SET category = CASE WHEN direction = 'IN' THEN 'Receita' ELSE 'Outros' END,
    category_id = (
        SELECT c.id FROM categories c
        WHERE c.user_id = inbox_items.user_id AND c.parent_id IS NULL AND c.archived_at IS NULL
          AND c.name = CASE WHEN inbox_items.direction = 'IN' THEN 'Receita' ELSE 'Outros' END
        ORDER BY c.created_at, c.id
        LIMIT 1
    )
WHERE state = 'PENDING'
  AND (category_id IN (SELECT id FROM m039_categories) OR (category_id IS NULL AND category = 'Investimento'));

UPDATE categories
SET archived_at = COALESCE(archived_at, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
WHERE id IN (SELECT id FROM m039_categories);

DROP TABLE m039_rows;
DROP TABLE m039_portfolio;
DROP TABLE m039_categories;
