package br.financas.app.ui.nav

import android.content.Context
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
 * - takePendingRoute(): { route? } a rota que uma tela nativa pediu quando nao havia WebView
 *   para ouvir (processo recriado); a web vai para ela ao abrir (native-level 5).
 * - open({ screen, params }): abre a tela nativa. "new-entry": o "+ Novo"
 *   (params.type = EXPENSE | INCOME | TRANSFER | CARD; params.client_id = um item da fila a
 *   corrigir, Pendentes › Corrigir). "inbox": Lancamentos › Aprovar (ui/inbox/, numa
 *   NativeActivity; frontend/native-level.txt 4 em diante). "home": Inicio e o sino (ui/home/,
 *   native-level 5; a WebView fica parada em /inicio por baixo). Tela desconhecida: rejeita com
 *   "UNIMPLEMENTED".
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
            SCREEN_INBOX, SCREEN_HOME -> {
                val host = activity
                if (host == null) {
                    call.reject("Tela nativa indisponível agora.", CODE_UNAVAILABLE)
                    return
                }
                val route = if (screen == SCREEN_HOME) NativeRoutes.HOME else NativeRoutes.INBOX
                val intent = NativeActivity.intent(host, route)
                host.runOnUiThread { host.startActivity(intent) }
                call.resolve()
            }
            else -> call.reject("Tela nativa não disponível: $screen", CODE_UNIMPLEMENTED)
        }
    }

    /**
     * A rota que uma tela nativa pediu sem WebView viva para ouvir (o app recriado depois de o
     * Android matar o processo): a web pergunta uma vez ao abrir e vai direto para ela.
     * { route } ou {} sem nenhuma (ou velha demais).
     */
    @PluginMethod
    fun takePendingRoute(call: PluginCall) {
        val result = JSObject()
        takePendingRoute(context)?.let { result.put("route", it) }
        call.resolve(result)
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

        /** Lancamentos › Aprovar (ui/inbox/), uma pagina da NativeActivity. */
        const val SCREEN_INBOX = "inbox"

        /** Inicio e o sino (ui/home/), a pagina de partida da NativeActivity (native-level 5). */
        const val SCREEN_HOME = "home"

        /** As rotas nativas deste APK (o NativeScreens.routes() da web). */
        val ROUTES: List<String> = listOf(SCREEN_NEW_ENTRY, SCREEN_INBOX, SCREEN_HOME)

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

        private const val PREFS = "financas_native_screens"
        private const val PENDING_ROUTE = "pending_route"
        private const val PENDING_AT = "pending_route_at"

        /** Quanto tempo a rota guardada vale: e so a ponte ate a WebView abrir. */
        private const val PENDING_ROUTE_MS = 2 * 60 * 1000L

        /** Guarda [route] para a WebView que vai abrir (sem WebView viva para o "navigate"). */
        @JvmStatic
        fun savePendingRoute(context: Context, route: String) {
            prefs(context).edit()
                .putString(PENDING_ROUTE, route)
                .putLong(PENDING_AT, System.currentTimeMillis())
                .apply()
        }

        /** A rota guardada, se ainda vale; e apagada ao ser lida. */
        @JvmStatic
        fun takePendingRoute(context: Context): String? {
            val prefs = prefs(context)
            val route = prefs.getString(PENDING_ROUTE, null)
            val at = prefs.getLong(PENDING_AT, 0L)
            prefs.edit().remove(PENDING_ROUTE).remove(PENDING_AT).apply()
            val age = System.currentTimeMillis() - at
            return route?.takeIf { it.startsWith("/") && age in 0..PENDING_ROUTE_MS }
        }

        private fun prefs(context: Context) =
            context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

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
