-- Comprovantes por lancamento ("Smaller gaps" de docs/next-steps.md).
--
-- O arquivo fica no disco, em ATTACHMENTS_DIR/<user_id>/<stored_name>; o banco
-- guarda so a referencia. Uma tabela e nao uma chave em transactions.metadata
-- porque um lancamento pode ter mais de um comprovante (nota + recibo), porque
-- metadata ja e reescrito por sync_investment_cash_transaction() e porque aqui
-- o user_id fica numa coluna que toda consulta filtra, como no resto do banco.
--
-- ON DELETE CASCADE: excluir o lancamento leva o comprovante junto — um recibo
-- sem lancamento nao tem onde aparecer. O arquivo no disco sai no DELETE do
-- lancamento; os que sobram de outros caminhos (movimentacao de investimento
-- excluida) saem na varredura de boot, prune_orphan_attachment_files().
--
-- stored_name e um id gerado (nunca o nome enviado), entao o nome original nao
-- chega ao sistema de arquivos; original_name e so para exibir e baixar.

CREATE TABLE IF NOT EXISTS transaction_attachments (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    transaction_id TEXT NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL UNIQUE,
    content_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes > 0),
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- "Comprovantes deste lancamento" e a contagem por linha do extrato.
CREATE INDEX IF NOT EXISTS idx_transaction_attachments_user_transaction
ON transaction_attachments(user_id, transaction_id);
