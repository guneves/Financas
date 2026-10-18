-- Compra no cartao: a categoria pelo id e cada compra com o seu id.
--
-- 1. cc_expenses.category_id. A compra guardava so o nome da categoria e o
--    orcamento a achava pelo nome: uma compra em "Lazer › Outros" caia no
--    "Outros" da raiz, e renomear a categoria tirava as compras dela do
--    orcamento. As linhas que ja existem recebem o id da categoria com aquele
--    nome na ordem em que o orcamento ja as lia (a raiz, que e unica, antes;
--    depois a subcategoria mais antiga), entao nenhum realizado muda aqui.
--    Um nome sem categoria (texto livre) fica sem id, como em transactions.
--
-- 2. client_id em toda compra. A compra era a chave cartao + descricao + data
--    + categoria, e duas corridas iguais no mesmo dia viravam uma: dividir uma
--    dividia as duas, A receber as juntava, excluir uma excluia as duas e o
--    comprovante de uma aparecia na outra. O client_id (024) ja identifica a
--    compra -- todas as parcelas o dividem --, mas as anteriores a 024 nao tem
--    um. Cada uma recebe 'legacy:' + o id de uma parcela dela. Parcelas de
--    compras identicas sao separadas pela ordem em que foram gravadas: a
--    k-esima "1/3" fica com a k-esima "2/3" e a k-esima "3/3".
--
-- So ADD COLUMN e UPDATE: nenhuma tabela e reconstruida.

ALTER TABLE cc_expenses ADD COLUMN category_id TEXT REFERENCES categories(id) ON DELETE SET NULL;

UPDATE cc_expenses
SET category_id = (
    SELECT c.id FROM categories c
    WHERE c.user_id = cc_expenses.user_id AND c.name = cc_expenses.category
    ORDER BY c.parent_id IS NOT NULL, c.created_at, c.id
    LIMIT 1
)
WHERE category_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_cc_expenses_user_category
ON cc_expenses(user_id, category_id);

CREATE TEMP TABLE legacy_cc_purchases AS
SELECT
    id,
    user_id,
    card_id,
    description,
    purchase_date,
    category,
    kind,
    substr(installment_info, instr(installment_info, '/') + 1) AS installments,
    ROW_NUMBER() OVER (
        PARTITION BY user_id, card_id, description, purchase_date, category, kind, installment_info
        ORDER BY created_at, id
    ) AS ordinal
FROM cc_expenses
WHERE client_id IS NULL;

CREATE INDEX temp.idx_legacy_cc_purchases
ON legacy_cc_purchases(user_id, card_id, purchase_date, ordinal);

UPDATE cc_expenses
SET client_id = 'legacy:' || (
    SELECT MIN(other.id)
    FROM legacy_cc_purchases self
    JOIN legacy_cc_purchases other
      ON other.user_id = self.user_id
     AND other.card_id = self.card_id
     AND other.purchase_date = self.purchase_date
     AND other.ordinal = self.ordinal
     AND other.description = self.description
     AND other.category = self.category
     AND other.kind = self.kind
     AND other.installments = self.installments
    WHERE self.id = cc_expenses.id
)
WHERE client_id IS NULL;

DROP TABLE legacy_cc_purchases;
