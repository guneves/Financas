package br.financas.app.ui.nav

import br.financas.app.ui.investimentos.InvestimentosTab

/** A rota nativa e o caminho web de cada aba de Investimentos (lib/navigation.js). Puro: NativeLinksTest. */
object InvestimentosRoutes {
    fun routeOf(tab: InvestimentosTab): String = when (tab) {
        InvestimentosTab.POSICAO -> NativeRoutes.POSICAO
        InvestimentosTab.RENTABILIDADE -> NativeRoutes.RENTABILIDADE
        InvestimentosTab.OPERACOES -> NativeRoutes.OPERACOES
        InvestimentosTab.ALOCACAO -> NativeRoutes.ALOCACAO
        InvestimentosTab.PROVENTOS -> NativeRoutes.PROVENTOS
        InvestimentosTab.IR -> NativeRoutes.IR
        InvestimentosTab.CALCULADORA -> NativeRoutes.CALCULADORA
    }

    fun webPathOf(tab: InvestimentosTab): String = "/investimentos/" + routeOf(tab)

    /** A rota nativa de um caminho web de Investimentos ("/investimentos" e Posicao), ou null. */
    fun routeForPath(path: String): String? = when (path) {
        "/investimentos", "/investments" -> NativeRoutes.POSICAO
        "/proventos" -> NativeRoutes.PROVENTOS
        else -> path.removePrefix("/investimentos/").takeIf { path.startsWith("/investimentos/") && it in NativeRoutes.INVESTMENTS }
    }
}
