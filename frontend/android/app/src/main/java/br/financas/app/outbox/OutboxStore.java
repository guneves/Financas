package br.financas.app.outbox;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

/**
 * A fila de envio no aparelho (mobile-docs/steps-to-production.md, "Where the outbox lives").
 *
 * Cada linha guarda o item inteiro, no mesmo formato da fila do navegador
 * (lib/outboxRules.js: client_id, user_id, kind, payload, status, last_error,
 * created_at, edited). As colunas soltas existem so para filtrar e ordenar.
 */
public final class OutboxStore extends SQLiteOpenHelper {

    public static final String PENDING = "pending";
    public static final String NEEDS_ATTENTION = "needs_attention";

    private static final String DB_NAME = "financas_outbox.db";
    private static final int DB_VERSION = 1;

    private static OutboxStore instance;

    public static synchronized OutboxStore get(Context context) {
        if (instance == null) instance = new OutboxStore(context.getApplicationContext());
        return instance;
    }

    private OutboxStore(Context context) {
        super(context, DB_NAME, null, DB_VERSION);
    }

    @Override
    public void onCreate(SQLiteDatabase db) {
        db.execSQL(
            "CREATE TABLE outbox ("
                + " client_id TEXT PRIMARY KEY,"
                + " user_id TEXT NOT NULL DEFAULT '',"
                + " status TEXT NOT NULL,"
                + " created_at TEXT NOT NULL,"
                + " item TEXT NOT NULL)"
        );
    }

    @Override
    public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {
        // Versao 1 e a unica ate aqui. Uma versao nova migra; nunca apaga a fila.
    }

    public synchronized List<JSONObject> all() {
        return query(null, null);
    }

    /** Os itens de um usuario que uma rodada de envio deve tentar, na ordem em que foram lancados. */
    public synchronized List<JSONObject> toSend(String userId, boolean retryAttention) {
        if (retryAttention) {
            return query("user_id = ?", new String[] { userId });
        }
        return query("user_id = ? AND status = ?", new String[] { userId, PENDING });
    }

    public synchronized int countPending() {
        try (Cursor cursor = getReadableDatabase().rawQuery(
            "SELECT COUNT(*) FROM outbox WHERE status = ?", new String[] { PENDING })) {
            return cursor.moveToFirst() ? cursor.getInt(0) : 0;
        }
    }

    public synchronized void put(JSONObject item) {
        ContentValues values = new ContentValues();
        values.put("client_id", item.optString("client_id"));
        values.put("user_id", item.optString("user_id", ""));
        values.put("status", item.optString("status", PENDING));
        values.put("created_at", item.optString("created_at", ""));
        values.put("item", item.toString());
        getWritableDatabase().insertWithOnConflict("outbox", null, values, SQLiteDatabase.CONFLICT_REPLACE);
    }

    /** Tira o item so se ele ainda e a versao {@code expected} (o texto do item inteiro). */
    public synchronized boolean removeIfUnchanged(String clientId, String expected) {
        if (!isUnchanged(clientId, expected)) return false;
        remove(clientId);
        return true;
    }

    /** Grava {@code next} so se o item ainda e a versao {@code expected}; descartado, nao volta. */
    public synchronized boolean replaceIfUnchanged(String clientId, String expected, JSONObject next) {
        if (!isUnchanged(clientId, expected)) return false;
        put(next);
        return true;
    }

    private boolean isUnchanged(String clientId, String expected) {
        try (Cursor cursor = getReadableDatabase().query(
            "outbox", new String[] { "item" }, "client_id = ?", new String[] { clientId }, null, null, null)) {
            if (!cursor.moveToFirst()) return false;
            // Mesmo caminho do lado de quem enviou (parse do texto guardado, depois toString),
            // para que uma linha intocada sempre bata, qualquer que seja a formatacao guardada.
            return expected.equals(new JSONObject(cursor.getString(0)).toString());
        } catch (JSONException error) {
            return false;
        }
    }

    public synchronized void remove(String clientId) {
        getWritableDatabase().delete("outbox", "client_id = ?", new String[] { clientId });
    }

    public synchronized JSONObject find(String clientId) {
        List<JSONObject> rows = query("client_id = ?", new String[] { clientId });
        return rows.isEmpty() ? null : rows.get(0);
    }

    private List<JSONObject> query(String where, String[] args) {
        List<JSONObject> items = new ArrayList<>();
        try (Cursor cursor = getReadableDatabase().query(
            "outbox", new String[] { "item" }, where, args, null, null, "created_at ASC")) {
            while (cursor.moveToNext()) {
                try {
                    items.add(new JSONObject(cursor.getString(0)));
                } catch (JSONException ignored) {
                    // Linha corrompida: fica no banco, mas nao derruba a fila inteira.
                }
            }
        }
        return items;
    }
}
