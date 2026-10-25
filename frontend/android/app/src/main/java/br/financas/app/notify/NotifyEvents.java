package br.financas.app.notify;

/**
 * Avisa a tela (se estiver aberta) que o leitor guardou uma notificacao ou foi ligado ou
 * desligado pelo Android. Ajustes (ui/ajustes/) assina enquanto aberta; fora dela ninguem ouve.
 */
public final class NotifyEvents {

    public interface Listener {
        void onChanged();
    }

    private static volatile Listener listener;

    private NotifyEvents() {}

    public static void setListener(Listener next) {
        listener = next;
    }

    static void changed() {
        Listener current = listener;
        if (current != null) current.onChanged();
    }
}
