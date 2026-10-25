package br.financas.app.ui.nav

/**
 * A barra de baixo da casca (00-shell.md): as quatro secoes e Ajustes, a pagina de entrada de
 * cada uma e a secao de cada rota. Puro: ShellNavTest.
 */
object ShellNav {

    enum class Section(val root: String) {
        HOME(NativeRoutes.HOME),
        LANCAMENTOS(NativeRoutes.EXTRATO),
        PLANEJAR(NativeRoutes.ORCAMENTO),
        INVESTIR(NativeRoutes.POSICAO),
        AJUSTES(NativeRoutes.AJUSTES),
    }

    private val LANCAMENTOS = setOf(NativeRoutes.EXTRATO, NativeRoutes.INBOX, NativeRoutes.CARTOES, NativeRoutes.A_RECEBER)
    private val PLANEJAR = setOf(NativeRoutes.ORCAMENTO, NativeRoutes.RECORRENTES, NativeRoutes.METAS)

    /** A secao acesa na barra; null no login (sem barra). */
    fun sectionOf(route: String?): Section? = when (route) {
        null, NativeRoutes.LOGIN -> null
        NativeRoutes.HOME -> Section.HOME
        NativeRoutes.AJUSTES -> Section.AJUSTES
        in LANCAMENTOS -> Section.LANCAMENTOS
        in PLANEJAR -> Section.PLANEJAR
        in NativeRoutes.INVESTMENTS -> Section.INVESTIR
        else -> null
    }

    /** O "+" (o "+ Novo") aparece em toda pagina com barra, menos Ajustes. */
    fun showsNewEntry(route: String?): Boolean {
        val section = sectionOf(route)
        return section != null && section != Section.AJUSTES
    }

    /**
     * O voltar do sistema numa pagina sem nada por baixo: no Inicio (e no login) o app vai para o
     * fundo sem morrer; em qualquer outra, volta ao Inicio.
     */
    fun backGoesHome(route: String?): Boolean = route != null && route != NativeRoutes.HOME && route != NativeRoutes.LOGIN

    /**
     * A pagina para onde o voltar leva, seja o que estiver por baixo: Aprovar volta ao Extrato
     * (venha da aba, do Inicio ou da notificacao). null: o voltar de sempre.
     */
    fun backTarget(route: String?): String? = when (route) {
        NativeRoutes.INBOX -> NativeRoutes.EXTRATO
        else -> null
    }
}
