package br.financas.app.ui.nav

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class NativeLinksTest {
    @Test
    fun lancamentosLinksOpenTheNativePages() {
        assertEquals(NativeLinks.Target(NativeRoutes.EXTRATO), NativeLinks.targetFor("/lancamentos"))
        assertEquals(NativeLinks.Target(NativeRoutes.EXTRATO), NativeLinks.targetFor("/lancamentos/extrato"))
        assertEquals(NativeLinks.Target(NativeRoutes.EXTRATO, "investimentos"), NativeLinks.targetFor("/lancamentos/extrato?ver=investimentos"))
        assertEquals(NativeLinks.Target(NativeRoutes.CARTOES), NativeLinks.targetFor("/lancamentos/cartoes"))
        assertEquals(NativeLinks.Target(NativeRoutes.INBOX), NativeLinks.targetFor("/lancamentos/aprovar"))
    }

    @Test
    fun everythingElseStaysOnTheWeb() {
        assertNull(NativeLinks.targetFor("/ajustes#regras-de-importacao"))
        assertNull(NativeLinks.targetFor("/ajustes?web=1#categorias"))
        assertNull(NativeLinks.targetFor("/investimentos/alocacao"))
        assertNull(NativeLinks.targetFor("/lancamentos/extrato?web=1"))
        assertNull(NativeLinks.targetFor(""))
        assertNull(NativeLinks.targetFor(null))
        assertEquals(NativeLinks.Target(NativeRoutes.EXTRATO), NativeLinks.targetFor("/lancamentos/extrato?ver=outra"))
    }

    @Test
    fun investmentTabsThisApkHasOpenNatively() {
        assertEquals(NativeLinks.Target(NativeRoutes.POSICAO), NativeLinks.targetFor("/investimentos"))
        assertEquals(NativeLinks.Target(NativeRoutes.POSICAO), NativeLinks.targetFor("/investimentos/posicao"))
        assertEquals(NativeLinks.Target(NativeRoutes.POSICAO), NativeLinks.targetFor("/investments"))
        assertEquals(NativeLinks.Target(NativeRoutes.OPERACOES), NativeLinks.targetFor("/investimentos/operacoes"))
        assertEquals(NativeLinks.Target(NativeRoutes.PROVENTOS), NativeLinks.targetFor("/investimentos/proventos"))
        assertEquals(NativeLinks.Target(NativeRoutes.PROVENTOS), NativeLinks.targetFor("/proventos"))
        assertNull(NativeLinks.targetFor("/investimentos/posicao?web=1"))
        assertNull(NativeLinks.targetFor("/investimentos/outra"))
        // Cada aba sabe a rota nativa e o caminho web dela.
        assertEquals("/investimentos/rentabilidade", InvestimentosRoutes.webPathOf(br.financas.app.ui.investimentos.InvestimentosTab.RENTABILIDADE))
    }

    @Test
    fun planejarAReceberAndAjustesOpenTheNativePages() {
        assertEquals(NativeLinks.Target(NativeRoutes.A_RECEBER), NativeLinks.targetFor("/lancamentos/a-receber"))
        assertEquals(NativeLinks.Target(NativeRoutes.ORCAMENTO), NativeLinks.targetFor("/planejamento"))
        assertEquals(NativeLinks.Target(NativeRoutes.ORCAMENTO), NativeLinks.targetFor("/planejamento/orcamento"))
        assertEquals(NativeLinks.Target(NativeRoutes.ORCAMENTO), NativeLinks.targetFor("/orcamento"))
        assertEquals(NativeLinks.Target(NativeRoutes.RECORRENTES), NativeLinks.targetFor("/planejamento/recorrentes"))
        assertEquals(NativeLinks.Target(NativeRoutes.METAS), NativeLinks.targetFor("/planejamento/metas"))
        assertEquals(NativeLinks.Target(NativeRoutes.AJUSTES), NativeLinks.targetFor("/ajustes"))
        assertEquals(NativeLinks.Target(NativeRoutes.AJUSTES, "categorias"), NativeLinks.targetFor("/ajustes#categorias"))
        assertEquals(NativeLinks.Target(NativeRoutes.AJUSTES, "cartoes"), NativeLinks.targetFor("/ajustes#cartoes"))
    }
}
