package br.financas.app.ui.nav

/**
 * Os links das telas nativas que tem pagina nativa neste APK: abrem direto no NavHost, sem passar
 * pela WebView ("/lancamentos" e o Extrato, como o redirect da web). Puro: NativeLinksTest.
 */
object NativeLinks {

    /**
     * A pagina nativa de [route] e a vista pedida: ?ver= do Extrato, ou a secao de Ajustes
     * (#contas...); null quando e da web.
     */
    data class Target(val route: String, val view: String? = null)

    /** As secoes de Ajustes que o APK tem em nativo; Regras e Integracoes seguem na WebView. */
    val NATIVE_SETTINGS_SECTIONS = listOf("contas", "cartoes", "categorias", "aprovar", "aparencia", "perfil", "notificacoes", "versao")

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
            "/lancamentos/a-receber" -> Target(NativeRoutes.A_RECEBER)
            "/planejamento", "/planejamento/orcamento", "/orcamento" -> Target(NativeRoutes.ORCAMENTO)
            "/planejamento/recorrentes", "/recorrentes" -> Target(NativeRoutes.RECORRENTES)
            "/planejamento/metas" -> Target(NativeRoutes.METAS)
            "/ajustes" -> {
                val section = route.substringAfter('#', "")
                when {
                    section.isEmpty() -> Target(NativeRoutes.AJUSTES)
                    section in NATIVE_SETTINGS_SECTIONS -> Target(NativeRoutes.AJUSTES, section)
                    else -> null
                }
            }
            else -> null
        }
    }
}
