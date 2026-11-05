-- O par aproximado (2026-11-04, docs/notifications-pluggy-design.md §3.7): a
-- compra internacional tem faixa propria. Na Pluggy, a moeda de origem quando
-- ela converteu para a moeda da conta; na notificacao, o aviso de compra no
-- exterior (o APK manda desde a Fase 2) ou outra moeda.
ALTER TABLE open_finance_transactions ADD COLUMN original_currency TEXT;
ALTER TABLE notify_detections ADD COLUMN international INTEGER NOT NULL DEFAULT 0;
