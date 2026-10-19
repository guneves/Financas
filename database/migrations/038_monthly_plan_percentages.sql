-- Plano do mes a partir da renda (038): a renda e o unico valor em reais; o
-- resto e percentual.
--
--   monthly_plans.invest_percent / spend_percent : % da renda (Investir, Gastar)
--   budgets.planned_percent                      : % do Gastar do mes
--
-- Os percentuais sao TEXT com seis casas ("33.333333"): o Python le como
-- Decimal, entao 33,33% x 3 soma 99,99 exatos, sem o erro do REAL. Seis casas
-- guardam o valor em reais de um plano antigo ate R$ 1 milhao de renda (o erro
-- fica abaixo de meio centavo). Os reais sao calculados na leitura
-- (services/budgets.py, services/monthly_plan.py), nunca gravados.
--
-- As colunas antigas em reais ficam (append-only: nada de reconstruir tabela).
-- Uma linha convertida (percentual preenchido) nao tem mais os reais lidos;
-- uma linha nova grava 0 nelas, so para o NOT NULL.
--
-- Conversao:
--   - plano com renda > 0: invest% = invest_amount / renda, spend% = spend_amount / renda;
--   - orcamento cujo plano do mes (o do proprio mes ou o mais recente antes
--     dele) tem renda > 0 e Gastar > 0: planned% = planned_amount / Gastar do mes.
-- O que nao converte (plano sem renda, orcamento sem plano com renda) fica com
-- o percentual NULL: a API devolve `needs_income` e nao calcula nada dele ate
-- o PUT do plano trazer a renda, que converte com as mesmas formulas.

ALTER TABLE monthly_plans ADD COLUMN invest_percent TEXT;
ALTER TABLE monthly_plans ADD COLUMN spend_percent TEXT;
ALTER TABLE budgets ADD COLUMN planned_percent TEXT;

UPDATE monthly_plans
SET invest_percent = printf('%.6f', invest_amount * 100.0 / income_amount),
    spend_percent = printf('%.6f', spend_amount * 100.0 / income_amount)
WHERE income_amount > 0;

UPDATE budgets
SET planned_percent = (
    SELECT printf('%.6f', budgets.planned_amount * 100.0 / p.spend_amount)
    FROM monthly_plans p
    WHERE p.user_id = budgets.user_id AND p.month <= budgets.month
    ORDER BY p.month DESC
    LIMIT 1
)
WHERE (
    SELECT p.income_amount > 0 AND p.spend_amount > 0
    FROM monthly_plans p
    WHERE p.user_id = budgets.user_id AND p.month <= budgets.month
    ORDER BY p.month DESC
    LIMIT 1
) = 1;
