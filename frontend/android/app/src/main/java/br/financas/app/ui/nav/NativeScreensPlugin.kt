package br.financas.app.ui.nav

import com.getcapacitor.JSArray
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin

/**
 * A ponte entre a WebView e as telas nativas (architecture.md, "Native and WebView side by side").
 *
 * Metodos (chamados pela web):
 * - routes(): { routes: [...] } as telas que este APK tem em nativo. Por enquanto nenhuma: a web
 *   segue com as telas React.
 * - open({ screen, params }): abre a tela nativa. Ainda nao ha nenhuma; rejeita com
 *   "UNIMPLEMENTED".
 *
 * Eventos (escutados pela web com addListener):
 * - "dataChanged" ({}): uma tela nativa gravou algo; a web chama invalidateServerData(), como no
 *   evento "changed" do outbox.
 * - "navigate" ({ route }): uma tela nativa mandou abrir uma rota que ainda e React; o roteador
 *   da web abre.
 *
 * A web ainda nao chama este plugin; quando chamar, sobe frontend/native-level.txt.
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
        call.reject("Tela nativa não disponível: $screen", CODE_UNIMPLEMENTED)
    }

    private fun emit(event: String, data: JSObject) {
        notifyListeners(event, data)
    }

    companion object {
        const val EVENT_DATA_CHANGED = "dataChanged"
        const val EVENT_NAVIGATE = "navigate"
        const val CODE_UNIMPLEMENTED = "UNIMPLEMENTED"

        /** As rotas nativas deste APK (o NativeScreens.routes() da web). Nenhuma ainda. */
        val ROUTES: List<String> = emptyList()

        @Volatile
        private var current: NativeScreensPlugin? = null

        /** Uma tela nativa gravou: a WebView (se carregada) atualiza os dados dela. */
        @JvmStatic
        fun emitDataChanged() {
            current?.emit(EVENT_DATA_CHANGED, JSObject())
        }

        /** Uma tela nativa pede para a WebView abrir [route] (uma tela ainda React). */
        @JvmStatic
        fun emitNavigate(route: String) {
            val data = JSObject()
            data.put("route", route)
            current?.emit(EVENT_NAVIGATE, data)
        }
    }
}
