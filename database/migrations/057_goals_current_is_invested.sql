-- Metas: o "Atual" e o que esta investido hoje (dono, 2026-11-13). O tipo
-- "Patrimonio" (NET_WORTH) somava a carteira ao saldo das contas; deixa de
-- existir e as metas dele passam a ser de carteira. O CHECK de 021 continua
-- aceitando o nome antigo; services/goals.py nao o grava mais.
UPDATE investment_goals SET kind = 'PORTFOLIO', updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
WHERE kind = 'NET_WORTH';
