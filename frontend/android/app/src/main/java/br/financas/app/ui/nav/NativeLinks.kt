package br.financas.app.ui.nav

/**
 * Os links entre as telas (caminhos da web, "/lancamentos" e o Extrato, como o redirect da web)
 * para a pagina do NavHost. Os que nao tem pagina no celular (Importar, Regras de importação,
 * Integrações: so no computador) nao tem alvo e a casca diz isso. Puro: NativeLinksTest.
 */
object NativeLinks {

    /**
     * A pagina nativa de [route] e a vista pedida: ?ver= do Extrato, ou a secao de Ajustes
     * (#contas...); null quando a pagina so existe no computador.
     */
    data class Target(val route: String, val view: String? = null)

    /** As secoes de Ajustes do celular; Regras de importação e Integrações sao so do computador. */
    val NATIVE_SETTINGS_SECTIONS = listOf("contas", "cartoes", "categorias", "aprovar", "open-finance", "aparencia", "perfil", "notificacoes", "versao")

    fun targetFor(route: String?): Target? {
        if (route.isNullOrEmpty()) return null
        val path = route.substringBefore('#').substringBefore('?').trimEnd('/')
        val query = route.substringBefore('#').substringAfter('?', "")
        val params = query.split('&').filter { it.isNotEmpty() }.associate { it.substringBefore('=') to it.substringAfter('=', "") }
        return when (path) {
            "/inicio", "/dashboard", "" -> Target(NativeRoutes.HOME)
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
            // Investimentos: as sete abas (InvestimentosRoutes).
            else -> InvestimentosRoutes.routeForPath(path)?.let { Target(it) }
        }
    }
}
