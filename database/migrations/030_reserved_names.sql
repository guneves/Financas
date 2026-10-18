-- 027 e 029 ficaram vazias (027_reserved.sql, 029_reserved.sql); o registro de
-- quem ja as aplicou passa a ter o nome atual dos arquivos.

UPDATE schema_migrations SET name = '027_reserved.sql' WHERE version = '027';
UPDATE schema_migrations SET name = '029_reserved.sql' WHERE version = '029';
