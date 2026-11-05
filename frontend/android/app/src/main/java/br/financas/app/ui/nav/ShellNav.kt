package br.financas.app.ui.nav

/**
 * A barra de baixo da casca (00-shell.md): as quatro secoes, a pagina de entrada de cada uma e a
 * secao de cada rota. Ajustes e uma secao sem aba: abre pela engrenagem do topo (dono,
 * 2026-11-05). Puro: ShellNavTest.
 */
object ShellNav {

    enum class Section(val root: String) {
        HOME(NativeRoutes.HOME),
        LANCAMENTOS(NativeRoutes.EXTRATO),
        PLANEJAR(NativeRoutes.ORCAMENTO),
        INVESTIR(NativeRoutes.POSICAO),
        AJUSTES(NativeRoutes.AJUSTES),
    }

    private val LANCAMENTOS = setOf(NativeRoutes.EXTRATO, NativeRoutes.CARTOES, NativeRoutes.A_RECEBER)
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

    /**
     * As abas da barra de baixo, na ordem. Ajustes saiu dela para o topo (a engrenagem de
     * NativeTopBar e do Inicio): com quatro abas e o "+" no meio, o "+" fica no centro da barra.
     */
    val BAR: List<Section> = listOf(Section.HOME, Section.LANCAMENTOS, Section.PLANEJAR, Section.INVESTIR)

    /** A engrenagem de Ajustes no topo: em toda pagina com barra, menos no proprio Ajustes. */
    fun showsSettings(route: String?): Boolean = sectionOf(route) != null && route != NativeRoutes.AJUSTES

    /** O toque na aba da propria secao, numa pagina de dentro dela: volta a entrada da secao. */
    fun reopensRoot(selected: Section, current: Section?, route: String?): Boolean =
        selected == current && selected != Section.HOME && selected.root != route

    /**
     * O "+" (o "+ Novo") mora na barra de baixo, logo depois desta aba: o centro exato da barra
     * (duas abas de cada lado, como na web). Antes flutuava por cima da pagina e cobria o fim das
     * listas (dono, 2026-11-05).
     */
    val NEW_ENTRY_AFTER = Section.LANCAMENTOS

    /** O "+" aparece em toda pagina com barra (dentro dela nao cobre nada, nem em Ajustes). */
    fun showsNewEntry(route: String?): Boolean = sectionOf(route) != null

    /**
     * O voltar do sistema numa pagina sem nada por baixo: no Inicio (e no login) o app vai para o
     * fundo sem morrer; em qualquer outra, volta ao Inicio.
     */
    fun backGoesHome(route: String?): Boolean = route != null && route != NativeRoutes.HOME && route != NativeRoutes.LOGIN
}
