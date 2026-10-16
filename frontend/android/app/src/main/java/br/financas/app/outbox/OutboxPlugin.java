package br.financas.app.outbox;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import org.json.JSONObject;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * A ponte entre lib/outbox.js e a fila nativa (lib/nativeApp.js monta o backend com estes
 * metodos). No APK a tela nunca envia a fila: quem envia e o OutboxSender, aqui ou no
 * WorkManager.
 */
@CapacitorPlugin(name = "Outbox")
public class OutboxPlugin extends Plugin {

    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    @Override
    public void load() {
        OutboxEvents.setListener(sent -> {
            JSObject data = new JSObject();
            data.put("sent", sent);
            notifyListeners("changed", data);
        });
        // Pendentes de uma sessao anterior (o app foi atualizado ou morto no meio).
        OutboxWorker.schedule(getContext());
    }

    @Override
    protected void handleOnDestroy() {
        OutboxEvents.setListener(null);
        executor.shutdown();
    }

    @PluginMethod
    public void all(PluginCall call) {
        JSArray items = new JSArray();
        for (JSONObject item : OutboxStore.get(getContext()).all()) items.put(item);
        JSObject result = new JSObject();
        result.put("items", items);
        call.resolve(result);
    }

    @PluginMethod
    public void put(PluginCall call) {
        JSObject item = call.getObject("item");
        if (item == null || item.optString("client_id").isEmpty()) {
            call.reject("Item sem client_id.");
            return;
        }
        OutboxStore.get(getContext()).put(item);
        OutboxWorker.schedule(getContext());
        call.resolve();
    }

    @PluginMethod
    public void remove(PluginCall call) {
        String clientId = call.getString("clientId", "");
        if (clientId.isEmpty()) {
            call.reject("clientId obrigatório.");
            return;
        }
        OutboxStore.get(getContext()).remove(clientId);
        call.resolve();
    }

    /** "Sincronizar agora" e os gatilhos da tela: uma rodada ja, com o resumo de volta. */
    @PluginMethod
    public void flush(PluginCall call) {
        boolean retryAttention = Boolean.TRUE.equals(call.getBoolean("retryAttention", false));
        executor.execute(() -> {
            OutboxSender.Summary summary = OutboxSender.run(getContext(), retryAttention);
            // Se o servidor nao respondeu, o WorkManager assume e tenta quando der.
            if ("offline".equals(summary.stopped)) OutboxWorker.schedule(getContext());
            JSObject result = new JSObject();
            result.put("sent", summary.sent);
            result.put("kept", summary.kept);
            result.put("attention", summary.attention);
            result.put("stopped", summary.stopped);
            call.resolve(result);
        });
    }

    @PluginMethod
    public void setSession(PluginCall call) {
        String baseUrl = call.getString("baseUrl", "");
        String token = call.getString("token", "");
        String userId = call.getString("userId", "");
        // So https: o Android bloqueia http em claro, e o envio ficaria tentando para sempre.
        if (!baseUrl.startsWith("https://")) {
            call.reject("Endereço da API inválido: o APK precisa ser gerado com VITE_API_BASE_URL.");
            return;
        }
        if (token.isEmpty() || userId.isEmpty()) {
            call.reject("Sessão incompleta.");
            return;
        }
        try {
            Session.save(getContext(), baseUrl, token, userId);
        } catch (Exception error) {
            call.reject("Não foi possível guardar a sessão no aparelho.", error);
            return;
        }
        LoginNotifier.cancel(getContext());
        OutboxWorker.schedule(getContext());
        call.resolve();
    }

    @PluginMethod
    public void clearSession(PluginCall call) {
        Session.clear(getContext());
        call.resolve();
    }
}
