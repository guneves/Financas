package br.financas.app.notify;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * A tabela do leitor no aparelho (Fase 6, passo 1): uma linha por notificacao de um app da
 * lista, guardada palavra por palavra. Sobrevive ao app fechado e a um APK novo; nao vai para
 * backup nenhum (allowBackup="false") e so sai daqui pela exportacao.
 *
 * dedup_key e unico: a mesma postagem lida de novo (o Android religou o leitor e ela ainda
 * estava na bandeja) nao vira uma segunda linha.
 */
public final class NotifyStore extends SQLiteOpenHelper {

    /** Teto da tabela: alem disso as mais antigas saem. Uma semana de compras fica longe disso. */
    static final int MAX_ROWS = 5000;

    private static final String DB_NAME = "financas_notify.db";
    private static final int DB_VERSION = 1;

    private static final String[] COLUMNS = {
        "package", "notification_key", "posted_at", "received_at", "when_at",
        "title", "text", "big_text", "extras", "channel_id", "category",
        "group_summary", "ongoing", "via",
    };

    private static NotifyStore instance;

    public static synchronized NotifyStore get(Context context) {
        if (instance == null) instance = new NotifyStore(context.getApplicationContext());
        return instance;
    }

    private NotifyStore(Context context) {
        super(context, DB_NAME, null, DB_VERSION);
    }

    @Override
    public void onCreate(SQLiteDatabase db) {
        db.execSQL(
            "CREATE TABLE notifications ("
                + " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                + " dedup_key TEXT NOT NULL UNIQUE,"
                + " package TEXT NOT NULL,"
                + " notification_key TEXT NOT NULL,"
                + " posted_at INTEGER NOT NULL,"
                + " received_at INTEGER NOT NULL,"
                + " when_at INTEGER NOT NULL DEFAULT 0,"
                + " title TEXT,"
                + " text TEXT,"
                + " big_text TEXT,"
                + " extras TEXT NOT NULL DEFAULT '{}',"
                + " channel_id TEXT,"
                + " category TEXT,"
                + " group_summary INTEGER NOT NULL DEFAULT 0,"
                + " ongoing INTEGER NOT NULL DEFAULT 0,"
                + " via TEXT NOT NULL)"
        );
        db.execSQL("CREATE INDEX idx_notifications_posted ON notifications (posted_at)");
    }

    @Override
    public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {
        // Versao 1 e a unica ate aqui. Uma versao nova migra; nunca apaga as capturas.
    }

    /** Guarda a notificacao; false quando essa postagem ja estava guardada. */
    public synchronized boolean insert(NotifyRules.Captured row) {
        ContentValues values = new ContentValues();
        values.put("dedup_key", row.dedupKey());
        values.put("package", row.packageName);
        values.put("notification_key", row.key == null ? "" : row.key);
        values.put("posted_at", row.postedAt);
        values.put("received_at", row.receivedAt);
        values.put("when_at", row.when);
        values.put("title", row.title);
        values.put("text", row.text);
        values.put("big_text", row.bigText);
        values.put("extras", new JSONObject(row.extras).toString());
        values.put("channel_id", row.channelId);
        values.put("category", row.category);
        values.put("group_summary", row.groupSummary ? 1 : 0);
        values.put("ongoing", row.ongoing ? 1 : 0);
        values.put("via", row.via);
        SQLiteDatabase db = getWritableDatabase();
        long id = db.insertWithOnConflict("notifications", null, values, SQLiteDatabase.CONFLICT_IGNORE);
        if (id == -1) return false;
        db.execSQL(
            "DELETE FROM notifications WHERE id NOT IN"
                + " (SELECT id FROM notifications ORDER BY posted_at DESC, id DESC LIMIT " + MAX_ROWS + ")"
        );
        return true;
    }

    /** Todas, em ordem de postagem (a exportacao). */
    public synchronized List<NotifyRules.Captured> all() {
        return query("posted_at ASC, id ASC", null);
    }

    /** As mais recentes primeiro (a lista em Ajustes). */
    public synchronized List<NotifyRules.Captured> latest(int limit) {
        return query("posted_at DESC, id DESC", String.valueOf(limit));
    }

    public synchronized int total() {
        try (Cursor cursor = getReadableDatabase().rawQuery("SELECT COUNT(*) FROM notifications", null)) {
            return cursor.moveToFirst() ? cursor.getInt(0) : 0;
        }
    }

    /** Quantas e a mais recente, por app: {pacote: [quantidade, posted_at da ultima]}. */
    public synchronized Map<String, long[]> countsByPackage() {
        Map<String, long[]> counts = new LinkedHashMap<>();
        try (Cursor cursor = getReadableDatabase().rawQuery(
            "SELECT package, COUNT(*), MAX(posted_at) FROM notifications GROUP BY package ORDER BY package", null)) {
            while (cursor.moveToNext()) {
                counts.put(cursor.getString(0), new long[] { cursor.getLong(1), cursor.getLong(2) });
            }
        }
        return counts;
    }

    public synchronized void clear() {
        getWritableDatabase().delete("notifications", null, null);
    }

    private List<NotifyRules.Captured> query(String orderBy, String limit) {
        List<NotifyRules.Captured> rows = new ArrayList<>();
        try (Cursor cursor = getReadableDatabase().query(
            "notifications", COLUMNS, null, null, null, null, orderBy, limit)) {
            while (cursor.moveToNext()) rows.add(fromCursor(cursor));
        }
        return rows;
    }

    private static NotifyRules.Captured fromCursor(Cursor cursor) {
        NotifyRules.Captured row = new NotifyRules.Captured();
        row.packageName = cursor.getString(0);
        row.key = cursor.getString(1);
        row.postedAt = cursor.getLong(2);
        row.receivedAt = cursor.getLong(3);
        row.when = cursor.getLong(4);
        row.title = cursor.getString(5);
        row.text = cursor.getString(6);
        row.bigText = cursor.getString(7);
        try {
            JSONObject extras = new JSONObject(cursor.getString(8));
            Iterator<String> names = extras.keys();
            while (names.hasNext()) {
                String name = names.next();
                row.extras.put(name, extras.optString(name));
            }
        } catch (JSONException ignored) {
            // Extras ilegiveis: a linha continua com titulo e texto.
        }
        row.channelId = cursor.getString(9);
        row.category = cursor.getString(10);
        row.groupSummary = cursor.getInt(11) != 0;
        row.ongoing = cursor.getInt(12) != 0;
        row.via = cursor.getString(13);
        return row;
    }
}
