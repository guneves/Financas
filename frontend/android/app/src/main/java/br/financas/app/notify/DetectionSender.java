package br.financas.app.notify;

import android.content.Context;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

import br.financas.app.outbox.Session;

/**
 * Manda a fila de deteccoes para o Aprovar, com o app fechado (DetectionWorker). Em lotes, na
 * ordem em que as notificacoes chegaram. Cada resposta 200 traz um resultado por deteccao, e
 * qualquer resultado (nova, juntada, repetida, ja conhecida, invalida) e final: sai da fila.
 * Sem rede ou 5xx: fica para a proxima rodada. 401 ou sem login: espera o proximo login. Outro
 * 4xx no lote inteiro: o lote nao serve e sai (nao trava a fila para sempre).
 */
public final class DetectionSender {

    private static final String TAG = "FinancasNotify";
    private static final String ENDPOINT = "/api/inbox/detections";
    // backend/services/inbox.py, MAX_DETECTIONS_PER_REQUEST.
    private static final int BATCH = 100;
    private static final int CONNECT_TIMEOUT_MS = 15_000;
    private static final int READ_TIMEOUT_MS = 30_000;
    private static final Object LOCK = new Object();

    /** "" (terminou), "offline" (tentar de novo) ou "login" (esperar o login). */
    public static String run(Context context) {
        synchronized (LOCK) {
            Context app = context.getApplicationContext();
            DetectionQueue queue = DetectionQueue.get(app);
            Session session = Session.load(app);
            if (session == null) return queue.count() > 0 ? "login" : "";
            while (true) {
                List<JSONObject> batch = queue.oldest(BATCH);
                if (batch.isEmpty()) return "";
                JSONArray list = new JSONArray();
                List<String> keys = new ArrayList<>();
                for (JSONObject item : batch) {
                    list.put(item);
                    keys.add(item.optString("key"));
                }
                int status = post(session, list);
                if (status == -1 || status >= 500) return "offline";
                if (status == 401) return "login";
                if (status != 200) Log.w(TAG, "Lote de deteccoes recusado: HTTP " + status);
                queue.remove(keys);
            }
        }
    }

    private static int post(Session session, JSONArray detections) {
        HttpURLConnection connection = null;
        try {
            URL url = new URL(session.baseUrl.replaceAll("/+$", "") + ENDPOINT);
            connection = (HttpURLConnection) url.openConnection();
            connection.setConnectTimeout(CONNECT_TIMEOUT_MS);
            connection.setReadTimeout(READ_TIMEOUT_MS);
            connection.setRequestMethod("POST");
            // Um redirecionamento (portal de Wi-Fi) nao prova que chegou: 3xx e "tentar de novo".
            connection.setInstanceFollowRedirects(false);
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/json");
            connection.setRequestProperty("Accept", "application/json");
            connection.setRequestProperty("Authorization", "Bearer " + session.token);
            byte[] body = new JSONObject().put("detections", detections).toString().getBytes(StandardCharsets.UTF_8);
            connection.setFixedLengthStreamingMode(body.length);
            try (OutputStream out = connection.getOutputStream()) {
                out.write(body);
            }
            int status = connection.getResponseCode();
            if (status >= 300 && status < 400) return -1;
            if (status == 200 && !isResults(read(connection.getInputStream()))) return -1;
            return status;
        } catch (Exception error) {
            // Sem rede, servidor desligado, tempo esgotado: a chave torna o reenvio seguro.
            return -1;
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    /** Um 200 que nao e a resposta do Aprovar (proxy, portal) nao prova que chegou. */
    private static boolean isResults(String body) {
        try {
            return new JSONObject(body).has("results");
        } catch (Exception error) {
            return false;
        }
    }

    private static String read(InputStream in) throws IOException {
        if (in == null) return "";
        try (InputStream stream = in; ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = stream.read(buffer)) != -1) out.write(buffer, 0, count);
            return out.toString(StandardCharsets.UTF_8.name());
        }
    }

    private DetectionSender() {}
}
