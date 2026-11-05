-- Investimentos so pela Pluggy (Fase 3, docs/notifications-pluggy-design.md §5):
-- a posicao inteira como a Pluggy a mandou (JSON, sem `transactions`), para
-- gravar renda fixa, Tesouro e cupom so com dados exatos (taxa, indexador,
-- tipo do titulo). O cupom gravado pela Pluggy e um provento: a linha da
-- operacao aponta para ele.
ALTER TABLE open_finance_positions ADD COLUMN raw TEXT;
ALTER TABLE open_finance_investment_operations ADD COLUMN proceed_id TEXT REFERENCES investment_proceeds(id) ON DELETE SET NULL;
