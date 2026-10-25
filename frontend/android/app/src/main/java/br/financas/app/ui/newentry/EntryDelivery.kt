package br.financas.app.ui.newentry

import android.content.Context
import android.widget.Toast
import br.financas.app.ui.nav.ShellEvents

/**
 * Os avisos do "+ Novo" depois que ele fecha. Com a casca aberta por baixo, ela relê a fila
 * (ShellEvents) e mostra o aviso; sem ela (o app sendo fechado), um Toast do Android.
 * Chamar na thread da tela.
 */
object EntryDelivery {

    fun notice(context: Context, notice: EntryNotice) {
        val delivered = ShellEvents.emitDataChanged(notice.message, notice.tone, notice.durationMs)
        if (!delivered) toast(context, notice.message, notice.durationMs > EntryNotice.DEFAULT_DURATION_MS)
    }

    /** Uma recusa que chegou com o sheet ja fechado: o dono precisa saber que nao gravou. */
    fun error(context: Context, message: String) {
        ShellEvents.emitDataChanged()
        toast(context, message, true)
    }

    /** Sem aviso (um 401): a casca relê; o AppGraph ja apagou a sessao e ela volta ao login. */
    fun dataChanged() {
        ShellEvents.emitDataChanged()
    }

    private fun toast(context: Context, message: String, long: Boolean) {
        Toast.makeText(context.applicationContext, message, if (long) Toast.LENGTH_LONG else Toast.LENGTH_SHORT).show()
    }
}
