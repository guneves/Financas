package br.financas.app.outbox;

import android.content.Context;
import android.util.Log;

import org.json.JSONObject;
import org.json.JSONTokener;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * O remetente da fila no APK. Roda no WorkManager (OutboxWorker, com o app fechado) e no
 * "Sincronizar agora" de Pendentes (Outbox.flush); um lock garante uma rodada por vez.
 * Mesmas regras de lib/outbox.js: um item por vez, na ordem; 2xx sai da fila, sem rede
 * ou 5xx para a rodada, 401 para tudo, 400/409 marca o item e segue.
 */
public final class OutboxSender {

    private static final String TAG = "FinancasOutbox";
    private static final int CONNECT_TIMEOUT_MS = 15_000;
    private static final int READ_TIMEOUT_MS = 30_000;
    private static final Object LOCK = new Object();

    public static final class Summary {
        public int sent;
        public int kept;
        public int attention;
        /** "" (terminou), "offline" (servidor nao respondeu) ou "login" (sem sessao ou 401). */
        public String stopped = "";
    }

    private static final class Response {
        boolean network;
        int status;
        String body = "";
    }

    private OutboxSender() {}

    public static Summary run(Context context, boolean retryAttention) {
        synchronized (LOCK) {
            Summary summary = runLocked(context.getApplicationContext(), retryAttention);
            if (summary.sent > 0 || summary.attention > 0) OutboxEvents.changed(summary.sent);
            return summary;
        }
    }

    private static Summary runLocked(Context context, boolean retryAttention) {
        Summary summary = new Summary();
        OutboxStore store = OutboxStore.get(context);
        Session session = Session.load(context);
        if (session == null) {
            summary.stopped = "login";
            summary.kept = store.countPending();
            return summary;
        }

        // Um item que entrou na fila durante a rodada tambem vai nela: a rodada so acaba
        // quando nao sobra nada que ela ainda nao tentou.
        Set<String> attempted = new HashSet<>();
        while (true) {
            List<JSONObject> queue = store.toSend(session.userId, retryAttention);
            queue.removeIf(item -> attempted.contains(item.optString("client_id")));
            if (queue.isEmpty()) return summary;

            for (int index = 0; index < queue.size(); index++) {
                JSONObject item = queue.get(index);
                String clientId = item.optString("client_id");
                attempted.add(clientId);
                String endpoint = OutboxRules.endpointFor(item.optString("kind"));
                if (endpoint == null) {
                    markAttention(store, item, item.toString(), "Tipo de lançamento desconhecido.");
                    summary.attention += 1;
                    continue;
                }

                // O item como estava quando saiu: a tela pode corrigi-lo ou descarta-lo enquanto
                // o pedido esta no ar, e o resultado so vale para esta versao (ver OutboxStore).
                String sentVersion = item.toString();
                Response response = post(session, endpoint, item.optJSONObject("payload"));
                switch (OutboxRules.outcomeOf(response.network, response.status)) {
                    case DONE:
                        Object data = parse(response.body);
                        if (!OutboxRules.isCreationResponse(item.optString("kind"), data)) {
                            // 2xx que nao e o lancamento (portal de Wi-Fi, proxy): nao prova que
                            // chegou, entao o item fica, para o dono ver.
                            markAttention(store, item, sentVersion, OutboxRules.UNEXPECTED_RESPONSE_MESSAGE);
                            summary.attention += 1;
                        } else if (item.optBoolean("edited") && OutboxRules.deliveredDiffers(item, data)) {
                            // A primeira tentativa tinha chegado e a resposta se perdeu: o servidor
                            // devolveu o lancamento antigo, sem a correcao. Nao some em silencio.
                            markAttention(store, item, sentVersion, OutboxRules.ALREADY_DELIVERED_MESSAGE);
                            summary.attention += 1;
                        } else {
                            // Corrigido durante o envio: fica (pendente, com edited), e a proxima
                            // rodada compara o que o servidor gravou com a correcao.
                            store.removeIfUnchanged(clientId, sentVersion);
                            summary.sent += 1;
                        }
                        break;
                    case ATTENTION:
                        markAttention(store, item, sentVersion, errorMessage(response.body));
                        summary.attention += 1;
                        break;
                    case STOP:
                        summary.stopped = "login";
                        summary.kept = queue.size() - index;
                        return summary;
                    case RETRY:
                    default:
                        summary.stopped = "offline";
                        summary.kept = queue.size() - index;
                        return summary;
                }
            }
        }
    }

    // Marca so a versao que foi enviada: um item corrigido ou descartado no meio do envio
    // fica como a tela deixou (nada de gravar a versao velha por cima, nem ressuscitar).
    private static void markAttention(OutboxStore store, JSONObject item, String sentVersion, String message) {
        try {
            item.put("status", OutboxStore.NEEDS_ATTENTION);
            item.put("last_error", message);
            store.replaceIfUnchanged(item.optString("client_id"), sentVersion, item);
        } catch (Exception error) {
            Log.w(TAG, "Nao foi possivel marcar o item", error);
        }
    }

    private static Response post(Session session, String endpoint, JSONObject payload) {
        Response response = new Response();
        HttpURLConnection connection = null;
        try {
            URL url = new URL(session.baseUrl.replaceAll("/+$", "") + endpoint);
            connection = (HttpURLConnection) url.openConnection();
            connection.setConnectTimeout(CONNECT_TIMEOUT_MS);
            connection.setReadTimeout(READ_TIMEOUT_MS);
            connection.setRequestMethod("POST");
            // Um redirecionamento (portal de Wi-Fi, proxy) viraria GET e um 200 falso: 3xx
            // chega aqui como resposta e o item vai para "precisa de atencao".
            connection.setInstanceFollowRedirects(false);
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/json");
            connection.setRequestProperty("Accept", "application/json");
            connection.setRequestProperty("Authorization", "Bearer " + session.token);
            byte[] body = (payload == null ? "{}" : payload.toString()).getBytes(StandardCharsets.UTF_8);
            connection.setFixedLengthStreamingMode(body.length);
            try (OutputStream out = connection.getOutputStream()) {
                out.write(body);
            }
            response.status = connection.getResponseCode();
            InputStream in = response.status >= 400 ? connection.getErrorStream() : connection.getInputStream();
            response.body = read(in);
        } catch (IOException error) {
            // Sem rede, DNS do Tailscale fora, PC desligado, tempo esgotado: o pedido nao chegou
            // (ou a resposta se perdeu — o client_id torna o reenvio seguro).
            response.network = true;
        } finally {
            if (connection != null) connection.disconnect();
        }
        return response;
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

    private static Object parse(String body) {
        if (body == null || body.isEmpty()) return null;
        try {
            return new JSONTokener(body).nextValue();
        } catch (Exception error) {
            return null;
        }
    }

    private static String errorMessage(String body) {
        Object parsed = parse(body);
        if (parsed instanceof JSONObject) {
            JSONObject json = (JSONObject) parsed;
            String message = json.optString("error", json.optString("message", ""));
            if (!message.isEmpty()) return message;
        }
        return OutboxRules.REFUSED_MESSAGE;
    }
}
