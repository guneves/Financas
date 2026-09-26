-- Pausa com janela e cursor guardado nas recorrencias (decisao 2 de docs/next-steps.md).
--
-- Dois defeitos aceitos ate aqui, os dois por falta de estado:
--
-- 1. Retomar andava o cursor ate hoje sem saber quando a pausa comecou, entao
--    uma ocorrencia que ja tinha vencido ANTES da pausa (e so nao tinha sido
--    lancada) sumia junto com o periodo pausado. `paused_at` guarda o dia da
--    pausa; ao retomar, so as datas estritamente entre esse dia e o dia da
--    retomada sao puladas. A janela vai para `pause_gaps` (lista JSON de
--    [inicio, fim], exclusivos) em vez de mover o cursor, porque o cursor
--    continua parado na ocorrencia vencida antes da pausa: ela fica pendente,
--    e o /run salta a janela quando chegar nela.
--
-- 2. Reviver uma recorrencia encerrada (estender end_date) reconstruia o
--    cursor pela ultima ocorrencia AINDA existente em transactions; apagar o
--    ultimo lancamento gerado fazia ele voltar. `last_occurrence_date` e a
--    ultima data que o /run ja percorreu, gravada e nunca derivada — mesma
--    razao de next_run_date (010).
--
-- O backfill usa o que existe: a maior data ainda materializada. Uma
-- recorrencia pausada antes desta migracao fica com paused_at nulo e retoma
-- como antes (pula ate hoje).

ALTER TABLE recurring_transactions ADD COLUMN paused_at TEXT;
ALTER TABLE recurring_transactions ADD COLUMN pause_gaps TEXT;
ALTER TABLE recurring_transactions ADD COLUMN last_occurrence_date TEXT;

UPDATE recurring_transactions
SET last_occurrence_date = (
    SELECT MAX(substr(t.source_id, length(recurring_transactions.id) + 2))
    FROM transactions t
    WHERE t.user_id = recurring_transactions.user_id
      AND t.source_type = 'RECURRING_TRANSACTION'
      AND t.source_id LIKE recurring_transactions.id || ':%'
);
