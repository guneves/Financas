package br.financas.app.notify;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

/**
 * As deteccoes esperando ir para o Aprovar (POST /api/inbox/detections): so os campos que o
 * parser leu (NotifyParsers.toDetection), nunca o texto da notificacao. Sobrevive ao app fechado
 * e a falta de rede; DetectionSender esvazia. A chave e o dedupKey da notificacao, a mesma do
 * servidor: guardar ou mandar duas vezes nao duplica nada.
 */
public final class DetectionQueue extends SQLiteOpenHelper {

    /** Teto da fila sem servidor: alem disso as mais antigas saem. */
    static final int MAX_ROWS = 2000;

    private static final String DB_NAME = "financas_detections.db";
    private static final int DB_VERSION = 1;

    private static DetectionQueue instance;

    public static synchronized DetectionQueue get(Context context) {
        if (instance == null) instance = new DetectionQueue(context.getApplicationContext());
        return instance;
    }

    private DetectionQueue(Context context) {
        super(context, DB_NAME, null, DB_VERSION);
    }

    @Override
    public void onCreate(SQLiteDatabase db) {
        db.execSQL(
            "CREATE TABLE detections ("
                + " id INTEGER PRIMARY KEY AUTOINCREMENT,"
                + " detection_key TEXT NOT NULL UNIQUE,"
                + " posted_at INTEGER NOT NULL,"
                + " payload TEXT NOT NULL)"
        );
    }

    @Override
    public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {
        // Versao 1 e a unica ate aqui.
    }

    /** Guarda a deteccao; false quando essa notificacao ja estava na fila. */
    public synchronized boolean add(JSONObject detection) {
        ContentValues values = new ContentValues();
        values.put("detection_key", detection.optString("key"));
        values.put("posted_at", detection.optLong("posted_ms"));
        values.put("payload", detection.toString());
        SQLiteDatabase db = getWritableDatabase();
        long id = db.insertWithOnConflict("detections", null, values, SQLiteDatabase.CONFLICT_IGNORE);
        if (id == -1) return false;
        db.execSQL(
            "DELETE FROM detections WHERE id NOT IN"
                + " (SELECT id FROM detections ORDER BY posted_at DESC, id DESC LIMIT " + MAX_ROWS + ")"
        );
        return true;
    }

    /** As mais antigas primeiro: o pareamento do servidor depende da ordem em que aconteceram. */
    public synchronized List<JSONObject> oldest(int limit) {
        List<JSONObject> rows = new ArrayList<>();
        try (Cursor cursor = getReadableDatabase().query(
            "detections", new String[] { "payload" }, null, null, null, null,
            "posted_at ASC, id ASC", String.valueOf(limit))) {
            while (cursor.moveToNext()) {
                try {
                    rows.add(new JSONObject(cursor.getString(0)));
                } catch (JSONException ignored) {
                    // Linha ilegivel: sai na proxima remocao pelo teto.
                }
            }
        }
        return rows;
    }

    public synchronized void remove(Collection<String> keys) {
        SQLiteDatabase db = getWritableDatabase();
        db.beginTransaction();
        try {
            for (String key : keys) db.delete("detections", "detection_key = ?", new String[] { key });
            db.setTransactionSuccessful();
        } finally {
            db.endTransaction();
        }
    }

    public synchronized int count() {
        try (Cursor cursor = getReadableDatabase().rawQuery("SELECT COUNT(*) FROM detections", null)) {
            return cursor.moveToFirst() ? cursor.getInt(0) : 0;
        }
    }
}
