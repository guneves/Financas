package br.financas.app.ui.nav

import br.financas.app.ui.newentry.NewEntryActivity
import com.getcapacitor.JSArray
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin

/**
 * A ponte entre a WebView e as telas nativas (architecture.md, "Native and WebView side by side").
 * A web usa por lib/nativeScreens.js (frontend/native-level.txt 3 em diante).
 *
 * Metodos (chamados pela web):
 * - routes(): { routes: [...] } as telas que este APK tem em nativo ([ROUTES]). A web abre a
 *   nativa so para uma rota listada; o resto segue React.
 * - open({ screen, params }): abre a tela nativa. "new-entry": o "+ Novo"
 *   (params.type = EXPENSE | INCOME | TRANSFER | CARD; params.client_id = um item da fila a
 *   corrigir, Pendentes › Corrigir). Tela desconhecida: rejeita com "UNIMPLEMENTED".
 *
 * Eventos (escutados pela web com addListener):
 * - "dataChanged" ({ notice? }): uma tela nativa gravou algo (ou guardou na fila); a web chama
 *   invalidateServerData() e relê a fila. notice = { message, tone, duration }: o toast que a
 *   web mostra (a tela nativa ja fechou).
 * - "navigate" ({ route }): uma tela nativa mandou abrir uma rota que ainda e React; o roteador
 *   da web abre.
 *
 * Nunca tire um metodo ou evento que a web de um nivel abaixo ainda chama.
 */
@CapacitorPlugin(name = "NativeScreens")
class NativeScreensPlugin : Plugin() {

    override fun load() {
        current = this
    }

    override fun handleOnDestroy() {
        if (current === this) current = null
        super.handleOnDestroy()
    }

    @PluginMethod
    fun routes(call: PluginCall) {
        val result = JSObject()
        result.put("routes", JSArray(ROUTES))
        call.resolve(result)
    }

    @PluginMethod
    fun open(call: PluginCall) {
        val screen = call.getString("screen", "") ?: ""
        val params = call.getObject("params") ?: JSObject()
        when (screen) {
            SCREEN_NEW_ENTRY -> {
                val host = activity
                if (host == null) {
                    call.reject("Tela nativa indisponível agora.", CODE_UNAVAILABLE)
                    return
                }
                val intent = NewEntryActivity.intent(
                    host,
                    type = params.optString("type", ""),
                    clientId = params.optString("client_id", ""),
                )
                host.runOnUiThread {
                    host.startActivity(intent)
                    // O sheet anima a propria entrada; sem a transicao da janela por cima.
                    @Suppress("DEPRECATION")
                    host.overridePendingTransition(0, 0)
                }
                call.resolve()
            }
            else -> call.reject("Tela nativa não disponível: $screen", CODE_UNIMPLEMENTED)
        }
    }

    private fun emit(event: String, data: JSObject) {
        notifyListeners(event, data)
    }

    companion object {
        const val EVENT_DATA_CHANGED = "dataChanged"
        const val EVENT_NAVIGATE = "navigate"
        const val CODE_UNIMPLEMENTED = "UNIMPLEMENTED"
        const val CODE_UNAVAILABLE = "UNAVAILABLE"

        /** O "+ Novo" (ui/newentry/). */
        const val SCREEN_NEW_ENTRY = "new-entry"

        /** As rotas nativas deste APK (o NativeScreens.routes() da web). */
        val ROUTES: List<String> = listOf(SCREEN_NEW_ENTRY)

        @Volatile
        private var current: NativeScreensPlugin? = null

        /**
         * Uma tela nativa gravou: a WebView (se carregada) atualiza os dados e a fila, e mostra
         * [message] como toast. Devolve false quando nao ha WebView para ouvir (a tela mostra o
         * aviso ela mesma).
         */
        @JvmStatic
        @JvmOverloads
        fun emitDataChanged(message: String? = null, tone: String? = null, durationMs: Int = 0): Boolean {
            val plugin = current ?: return false
            val data = JSObject()
            if (!message.isNullOrEmpty()) {
                val notice = JSObject()
                notice.put("message", message)
                if (!tone.isNullOrEmpty()) notice.put("tone", tone)
                if (durationMs > 0) notice.put("duration", durationMs)
                data.put("notice", notice)
            }
            plugin.emit(EVENT_DATA_CHANGED, data)
            return true
        }

        /** Uma tela nativa pede para a WebView abrir [route] (uma tela ainda React). */
        @JvmStatic
        fun emitNavigate(route: String): Boolean {
            val plugin = current ?: return false
            val data = JSObject()
            data.put("route", route)
            plugin.emit(EVENT_NAVIGATE, data)
            return true
        }
    }
}
