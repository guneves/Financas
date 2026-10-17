package br.financas.app.notify;

import android.content.Context;
import android.content.SharedPreferences;

/**
 * O que o leitor guarda fora da tabela: se a captura esta ligada (desligada de fabrica) e
 * quando o Android ligou e desligou o leitor pela ultima vez (Ajustes mostra, para saber se
 * ele esta mesmo ouvindo).
 */
public final class NotifySettings {

    private static final String PREFS = "financas_notify";
    private static final String CAPTURE_ON = "capture_on";
    private static final String CAPTURE_SINCE = "capture_since";
    private static final String CONNECTED_AT = "connected_at";
    private static final String DISCONNECTED_AT = "disconnected_at";

    private NotifySettings() {}

    private static SharedPreferences prefs(Context context) {
        return context.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    public static boolean isCaptureOn(Context context) {
        return prefs(context).getBoolean(CAPTURE_ON, false);
    }

    /** Quando a captura foi ligada da ultima vez (0 = nunca). */
    public static long captureSince(Context context) {
        return prefs(context).getLong(CAPTURE_SINCE, 0);
    }

    public static void setCapture(Context context, boolean on, long now) {
        SharedPreferences.Editor editor = prefs(context).edit().putBoolean(CAPTURE_ON, on);
        if (on && !isCaptureOn(context)) editor.putLong(CAPTURE_SINCE, now);
        // commit, nao apply: o leitor pode ler logo em seguida, em outra thread.
        editor.commit();
    }

    public static long connectedAt(Context context) {
        return prefs(context).getLong(CONNECTED_AT, 0);
    }

    public static long disconnectedAt(Context context) {
        return prefs(context).getLong(DISCONNECTED_AT, 0);
    }

    static void markConnected(Context context, long now) {
        prefs(context).edit().putLong(CONNECTED_AT, now).apply();
    }

    static void markDisconnected(Context context, long now) {
        prefs(context).edit().putLong(DISCONNECTED_AT, now).apply();
    }
}
