package br.financas.app.ui.newentry

import android.content.Context
import android.widget.Toast
import br.financas.app.ui.nav.NativeScreensPlugin

/**
 * Os avisos do "+ Novo" depois que ele fecha. Com a WebView carregada, ela relê a fila e os dados
 * (NativeScreens "dataChanged") e mostra o toast dela; sem WebView para ouvir, um Toast do Android.
 * Chamar na thread da tela.
 */
object EntryDelivery {

    fun notice(context: Context, notice: EntryNotice) {
        val delivered = NativeScreensPlugin.emitDataChanged(notice.message, notice.tone, notice.durationMs)
        if (!delivered) toast(context, notice.message, notice.durationMs > EntryNotice.DEFAULT_DURATION_MS)
    }

    /** Uma recusa que chegou com o sheet ja fechado: o dono precisa saber que nao gravou. */
    fun error(context: Context, message: String) {
        NativeScreensPlugin.emitDataChanged()
        toast(context, message, true)
    }

    /** Sem aviso (um 401): so a WebView relê, recebe o 401 e mostra o login. */
    fun dataChanged() {
        NativeScreensPlugin.emitDataChanged()
    }

    private fun toast(context: Context, message: String, long: Boolean) {
        Toast.makeText(context.applicationContext, message, if (long) Toast.LENGTH_LONG else Toast.LENGTH_SHORT).show()
    }
}
