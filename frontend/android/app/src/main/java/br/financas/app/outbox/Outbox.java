package br.financas.app.outbox;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;

import br.financas.app.notify.DetectionWorker;

/**
 * A fila e a sessao vistas pelas telas nativas: entrar e sair, ha rede de verdade, e uma rodada
 * de envio ja ("Sincronizar agora"). Quem envia e sempre o OutboxSender, aqui ou no WorkManager.
 */
public final class Outbox {

    private Outbox() {}

    /**
     * Ha alguma rede de verdade por baixo? A VPN do Tailscale continua "conectada" em modo
     * aviao e o pedido fica pendurado, entao ela nao conta: sem outra rede com internet, o
     * "+ Novo" guarda direto na fila em vez de esperar o prazo.
     */
    public static boolean hasRealNetwork(Context context) {
        ConnectivityManager manager = (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
        if (manager == null) return true;
        for (Network network : manager.getAllNetworks()) {
            NetworkCapabilities caps = manager.getNetworkCapabilities(network);
            if (caps == null || caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN)) continue;
            if (caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)) return true;
        }
        return false;
    }

    /**
     * O login deu certo: guarda a sessao (so https), tira o aviso "Sessão expirada" e acorda o
     * envio da fila e o das deteccoes que esperavam o login.
     */
    public static void signIn(Context context, String baseUrl, String token, String userId) throws Exception {
        if (baseUrl == null || !baseUrl.startsWith("https://")) {
            throw new IllegalArgumentException("Endereço da API inválido.");
        }
        if (token == null || token.isEmpty() || userId == null || userId.isEmpty()) {
            throw new IllegalArgumentException("Sessão incompleta.");
        }
        Session.save(context, baseUrl, token, userId);
        LoginNotifier.cancel(context);
        OutboxWorker.schedule(context);
        DetectionWorker.schedule(context);
    }

    /** "Sair" (ou um 401): o envio para; a fila fica no aparelho, de cada usuario. */
    public static void signOut(Context context) {
        Session.clear(context);
    }

    /**
     * Uma rodada de envio agora, tentando tambem os recusados quando [retryAttention]. Bloqueia
     * (rede): fora da thread da tela. Sem resposta do servidor, o WorkManager assume.
     */
    public static OutboxSender.Summary flush(Context context, boolean retryAttention) {
        OutboxSender.Summary summary = OutboxSender.run(context, retryAttention);
        if ("offline".equals(summary.stopped)) OutboxWorker.schedule(context);
        return summary;
    }

    /** Pendentes de uma sessao anterior (o app foi atualizado ou morto no meio): ao abrir. */
    public static void resume(Context context) {
        OutboxWorker.schedule(context);
    }
}
