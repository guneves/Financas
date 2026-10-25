package br.financas.app.ui.nav

import android.os.Handler
import android.os.Looper

/**
 * Os avisos das telas nativas para a casca (NativeActivity): uma tela gravou algo ou guardou na
 * fila (a casca rele os Pendentes e mostra o aviso, se houver) ou pediu outra pagina. Sem a
 * casca na frente (o "+ Novo" aberto pela notificacao, por exemplo), ninguem ouve: quem chamou
 * mostra o aviso ele mesmo.
 */
object ShellEvents {

    /** Um aviso para a casca mostrar: [tone] success | info | warning; [durationMs] 0 = o padrao. */
    data class Notice(val message: String, val tone: String?, val durationMs: Int)

    interface Listener {
        fun dataChanged(notice: Notice?)

        /** Um caminho da web ("/ajustes#contas"); a casca abre a pagina nativa dele. */
        fun navigate(route: String)
    }

    @Volatile
    private var listener: Listener? = null

    private val main = Handler(Looper.getMainLooper())

    fun setListener(next: Listener?) {
        listener = next
    }

    fun clearListener(current: Listener) {
        if (listener === current) listener = null
    }

    /**
     * Uma tela nativa gravou: a casca rele a fila e mostra [message] (se houver). Devolve false
     * sem casca para ouvir (a tela mostra o aviso ela mesma).
     */
    @JvmStatic
    @JvmOverloads
    fun emitDataChanged(message: String? = null, tone: String? = null, durationMs: Int = 0): Boolean {
        val current = listener ?: return false
        val notice = message?.takeIf { it.isNotEmpty() }?.let { Notice(it, tone, durationMs) }
        onMain { current.dataChanged(notice) }
        return true
    }

    /** Uma tela pede outra pagina (um link do "+ Novo"); false sem casca para abrir. */
    @JvmStatic
    fun emitNavigate(route: String): Boolean {
        val current = listener ?: return false
        onMain { current.navigate(route) }
        return true
    }

    private fun onMain(block: () -> Unit) {
        if (Looper.myLooper() == Looper.getMainLooper()) block() else main.post(block)
    }
}
