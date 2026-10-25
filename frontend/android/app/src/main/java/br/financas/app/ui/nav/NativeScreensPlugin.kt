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
 *   native-level 5; a WebView fica parada em /inicio por baixo). "extrato" (params.view) e
 *   "cartoes": Lancamentos › Extrato e Cartoes (ui/extrato/, ui/cartoes/; native-level 6).
 *   "a-receber", "orcamento", "recorrentes", "metas" e "ajustes" (params.section) — native-level 7.
 *   As abas de Investimentos pelo nome ("posicao", "operacoes", "proventos"...;
 *   NativeRoutes.INVESTMENTS) — native-level 8.
 *   Tela desconhecida: rejeita com
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
            SCREEN_INBOX, SCREEN_HOME, SCREEN_EXTRATO, SCREEN_CARTOES, SCREEN_A_RECEBER,
            SCREEN_ORCAMENTO, SCREEN_RECORRENTES, SCREEN_METAS, SCREEN_AJUSTES,
            in NativeRoutes.INVESTMENTS -> {
                val host = activity
                if (host == null) {
                    call.reject("Tela nativa indisponível agora.", CODE_UNAVAILABLE)
                    return
                }
                val route = when (screen) {
                    SCREEN_HOME -> NativeRoutes.HOME
                    SCREEN_EXTRATO -> NativeRoutes.EXTRATO
                    SCREEN_CARTOES -> NativeRoutes.CARTOES
                    SCREEN_A_RECEBER -> NativeRoutes.A_RECEBER
                    SCREEN_ORCAMENTO -> NativeRoutes.ORCAMENTO
                    SCREEN_RECORRENTES -> NativeRoutes.RECORRENTES
                    SCREEN_METAS -> NativeRoutes.METAS
                    SCREEN_AJUSTES -> NativeRoutes.AJUSTES
                    in NativeRoutes.INVESTMENTS -> screen
                    else -> NativeRoutes.INBOX
                }
                val view = if (screen == SCREEN_AJUSTES) {
                    params.optString("section", "").takeIf { it in NativeLinks.NATIVE_SETTINGS_SECTIONS }
                } else {
                    params.optString("view", "").takeIf { it == "contas" || it == "investimentos" }
                }
                val intent = NativeActivity.intent(host, route, view = view)
                host.runOnUiThread {
                    host.startActivity(intent)
                    // O Inicio e uma aba (a da esquerda), nao uma pagina empilhada: fade, nao o
                    // "avancar" que entra pela direita. Aprovar segue empilhada, com o padrao.
                    if (screen == SCREEN_HOME) host.tabTransition()
                }
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

        /** Lancamentos › Extrato, as duas vistas (ui/extrato/; native-level 6). params.view = contas | investimentos. */
        const val SCREEN_EXTRATO = "extrato"

        /** Lancamentos › Cartoes (ui/cartoes/; native-level 6). */
        const val SCREEN_CARTOES = "cartoes"

        /** Lancamentos › A receber (ui/areceber/; native-level 7). */
        const val SCREEN_A_RECEBER = "a-receber"

        /** Planejar › Orcamento, Recorrentes e Metas (native-level 7). */
        const val SCREEN_ORCAMENTO = "orcamento"
        const val SCREEN_RECORRENTES = "recorrentes"
        const val SCREEN_METAS = "metas"

        /** Ajustes (ui/ajustes/; native-level 7). params.section = a secao a abrir (#contas...). */
        const val SCREEN_AJUSTES = "ajustes"

        /**
         * As rotas nativas deste APK (o NativeScreens.routes() da web). As de Investimentos
         * (native-level 8) tem o nome da aba: "posicao", "operacoes", "proventos"...
         */
        val ROUTES: List<String> = listOf(
            SCREEN_NEW_ENTRY, SCREEN_INBOX, SCREEN_HOME, SCREEN_EXTRATO, SCREEN_CARTOES,
            SCREEN_A_RECEBER, SCREEN_ORCAMENTO, SCREEN_RECORRENTES, SCREEN_METAS, SCREEN_AJUSTES,
        ) + NativeRoutes.INVESTMENTS

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
            return PendingRoute.valid(route, at, System.currentTimeMillis())
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
