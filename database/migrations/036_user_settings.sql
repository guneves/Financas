-- Preferencias do dono que valem em todo aparelho (o tema continua por aparelho).
--
-- Uma linha por (user_id, setting_key); value e texto (JSON quando preciso).
-- A primeira: inbox_always_ask — Aprovar pede confirmar a conta/cartao de todo
-- item, inclusive os lembrados ("Aprovar todos" nao leva nenhum).
--
-- So tabela nova: nenhuma tabela e reconstruida.

CREATE TABLE IF NOT EXISTS user_settings (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    setting_key TEXT NOT NULL,
    value TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (user_id, setting_key)
);
