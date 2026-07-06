ALTER TABLE transactions ADD COLUMN source_type TEXT;
ALTER TABLE transactions ADD COLUMN source_id TEXT;
ALTER TABLE transactions ADD COLUMN metadata TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_user_source
ON transactions(user_id, source_type, source_id)
WHERE source_type IS NOT NULL AND source_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_transactions_user_category_date
ON transactions(user_id, category, date DESC);

INSERT OR IGNORE INTO transactions
    (
        id, user_id, amount, date, category, description, type,
        source_type, source_id, metadata, created_at
    )
SELECT
    'cash:' || source.id,
    source.user_id,
    ROUND(source.cash_amount, 2),
    source.transaction_date,
    'Investimento',
    source.description,
    source.cash_type,
    'INVESTMENT_TRANSACTION',
    source.id,
    source.cash_metadata,
    source.created_at
FROM (
    SELECT
        it.id,
        it.user_id,
        it.transaction_date,
        it.created_at,
        CASE
            WHEN it.movement_type = 'BUY' THEN 'EXPENSE'
            WHEN it.movement_type IN ('SELL', 'REDEMPTION') THEN 'INCOME'
            ELSE NULL
        END AS cash_type,
        CASE
            WHEN it.movement_type = 'BUY' THEN
                CASE
                    WHEN ABS(it.quantity * it.unit_price) > 0
                    THEN ABS(it.quantity * it.unit_price)
                    ELSE 0
                END
            WHEN it.movement_type = 'SELL' THEN
                CASE
                    WHEN (
                        ABS(it.quantity) * COALESCE(
                            CASE
                                WHEN it.metadata IS NOT NULL
                                    AND json_valid(it.metadata)
                                    AND json_extract(it.metadata, '$.sale_price') IS NOT NULL
                                THEN CAST(json_extract(it.metadata, '$.sale_price') AS REAL)
                            END,
                            (
                                SELECT pq.price
                                FROM price_quotes pq
                                WHERE pq.user_id = it.user_id
                                  AND pq.asset_id = it.asset_id
                                  AND pq.transaction_id IS NULL
                                ORDER BY pq.quoted_at DESC, pq.created_at DESC
                                LIMIT 1
                            ),
                            it.unit_price
                        ) - CASE
                            WHEN it.metadata IS NOT NULL
                                AND json_valid(it.metadata)
                                AND json_extract(it.metadata, '$.other_costs') IS NOT NULL
                            THEN ABS(CAST(json_extract(it.metadata, '$.other_costs') AS REAL))
                            ELSE 0
                        END
                    ) > 0
                    THEN (
                        ABS(it.quantity) * COALESCE(
                            CASE
                                WHEN it.metadata IS NOT NULL
                                    AND json_valid(it.metadata)
                                    AND json_extract(it.metadata, '$.sale_price') IS NOT NULL
                                THEN CAST(json_extract(it.metadata, '$.sale_price') AS REAL)
                            END,
                            (
                                SELECT pq.price
                                FROM price_quotes pq
                                WHERE pq.user_id = it.user_id
                                  AND pq.asset_id = it.asset_id
                                  AND pq.transaction_id IS NULL
                                ORDER BY pq.quoted_at DESC, pq.created_at DESC
                                LIMIT 1
                            ),
                            it.unit_price
                        ) - CASE
                            WHEN it.metadata IS NOT NULL
                                AND json_valid(it.metadata)
                                AND json_extract(it.metadata, '$.other_costs') IS NOT NULL
                            THEN ABS(CAST(json_extract(it.metadata, '$.other_costs') AS REAL))
                            ELSE 0
                        END
                    )
                    ELSE 0
                END
            WHEN it.movement_type = 'REDEMPTION' THEN
                CASE
                    WHEN (
                        COALESCE(
                            (
                                SELECT pq.price
                                FROM price_quotes pq
                                WHERE pq.user_id = it.user_id
                                  AND pq.asset_id = it.asset_id
                                  AND pq.transaction_id = it.id
                                ORDER BY pq.quoted_at DESC, pq.created_at DESC
                                LIMIT 1
                            ),
                            ABS(it.quantity * it.unit_price)
                        ) - CASE
                            WHEN it.metadata IS NOT NULL
                                AND json_valid(it.metadata)
                                AND json_extract(it.metadata, '$.other_costs') IS NOT NULL
                            THEN ABS(CAST(json_extract(it.metadata, '$.other_costs') AS REAL))
                            ELSE 0
                        END
                    ) > 0
                    THEN (
                        COALESCE(
                            (
                                SELECT pq.price
                                FROM price_quotes pq
                                WHERE pq.user_id = it.user_id
                                  AND pq.asset_id = it.asset_id
                                  AND pq.transaction_id = it.id
                                ORDER BY pq.quoted_at DESC, pq.created_at DESC
                                LIMIT 1
                            ),
                            ABS(it.quantity * it.unit_price)
                        ) - CASE
                            WHEN it.metadata IS NOT NULL
                                AND json_valid(it.metadata)
                                AND json_extract(it.metadata, '$.other_costs') IS NOT NULL
                            THEN ABS(CAST(json_extract(it.metadata, '$.other_costs') AS REAL))
                            ELSE 0
                        END
                    )
                    ELSE 0
                END
            ELSE 0
        END AS cash_amount,
        CASE
            WHEN it.movement_type = 'BUY' THEN 'Compra de investimento: ' || asset.ticker
            WHEN it.movement_type = 'SELL' THEN 'Venda de investimento: ' || asset.ticker
            WHEN it.movement_type = 'REDEMPTION' THEN 'Resgate de investimento: ' || asset.ticker
            ELSE 'Movimento de investimento: ' || asset.ticker
        END AS description,
        '{"asset_id":"' || REPLACE(asset.id, '"', '""') ||
        '","asset_class":"' || REPLACE(asset.asset_class, '"', '""') ||
        '","ticker":"' || REPLACE(asset.ticker, '"', '""') ||
        '","movement_type":"' || REPLACE(it.movement_type, '"', '""') || '"}' AS cash_metadata
    FROM investment_transactions it
    JOIN assets asset ON asset.id = it.asset_id
) source
WHERE source.cash_type IS NOT NULL
  AND source.cash_amount > 0;
