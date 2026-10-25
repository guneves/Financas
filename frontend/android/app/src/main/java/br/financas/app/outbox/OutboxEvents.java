package br.financas.app.outbox;

/**
 * Avisa a tela (se estiver aberta) que a fila mudou sem ela pedir: o WorkManager enviou
 * ou o servidor recusou um item. A casca nativa (ui/nav/ShellViewModel) assina.
 */
public final class OutboxEvents {

    public interface Listener {
        void onChanged(int sent);
    }

    private static volatile Listener listener;

    private OutboxEvents() {}

    public static void setListener(Listener next) {
        listener = next;
    }

    static void changed(int sent) {
        Listener current = listener;
        if (current != null) current.onChanged(sent);
    }
}
