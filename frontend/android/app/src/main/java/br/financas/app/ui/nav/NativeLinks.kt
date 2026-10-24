package br.financas.app.ui.nav

/**
 * Os links das telas nativas que tem pagina nativa neste APK: abrem direto no NavHost, sem passar
 * pela WebView ("/lancamentos" e o Extrato, como o redirect da web). Puro: NativeLinksTest.
 */
object NativeLinks {

    /** A pagina nativa de [route] e a vista pedida (?ver= do Extrato); null quando e da web. */
    data class Target(val route: String, val view: String? = null)

    fun targetFor(route: String?): Target? {
        if (route.isNullOrEmpty()) return null
        val path = route.substringBefore('#').substringBefore('?').trimEnd('/')
        val query = route.substringBefore('#').substringAfter('?', "")
        val params = query.split('&').filter { it.isNotEmpty() }.associate { it.substringBefore('=') to it.substringAfter('=', "") }
        // ?web=1 pede a pagina React de proposito.
        if (params["web"] == "1") return null
        return when (path) {
            "/lancamentos", "/lancamentos/extrato" ->
                Target(NativeRoutes.EXTRATO, params["ver"]?.takeIf { it == "contas" || it == "investimentos" })
            "/lancamentos/cartoes" -> Target(NativeRoutes.CARTOES)
            "/lancamentos/aprovar", "/aprovar" -> Target(NativeRoutes.INBOX)
            else -> null
        }
    }
}
