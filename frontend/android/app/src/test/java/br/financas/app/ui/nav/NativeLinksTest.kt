package br.financas.app.ui.nav

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test

class NativeLinksTest {
    @Test
    fun lancamentosLinksOpenTheNativePages() {
        assertEquals(NativeLinks.Target(NativeRoutes.EXTRATO), NativeLinks.targetFor("/lancamentos"))
        assertEquals(NativeLinks.Target(NativeRoutes.EXTRATO), NativeLinks.targetFor("/lancamentos/extrato"))
        assertEquals(NativeLinks.Target(NativeRoutes.EXTRATO, "investimentos"), NativeLinks.targetFor("/lancamentos/extrato?ver=investimentos"))
        assertEquals(NativeLinks.Target(NativeRoutes.CARTOES), NativeLinks.targetFor("/lancamentos/cartoes"))
    }

    @Test
    fun aprovarIsGoneAndOpensTheExtratoInReview() {
        // 045: a tela Aprovar saiu do celular; o link (e o antigo /aprovar) abre o Revisar.
        val review = NativeLinks.Target(NativeRoutes.EXTRATO, NativeLinks.VIEW_REVIEW)
        assertEquals(review, NativeLinks.targetFor("/lancamentos/aprovar"))
        assertEquals(review, NativeLinks.targetFor("/aprovar"))
        assertEquals(review, NativeLinks.targetFor("/lancamentos/extrato?review=1"))
        assertEquals(review, NativeLinks.targetFor(br.financas.app.rules.ReviewRules.REVIEW_PATH))
        assertEquals(NativeLinks.Target(NativeRoutes.EXTRATO), NativeLinks.targetFor("/lancamentos/extrato?review=0"))
        assertFalse(NativeRoutes.ALL.contains("inbox"))
    }

    @Test
    fun desktopOnlyPagesHaveNoTarget() {
        assertNull(NativeLinks.targetFor("/ajustes#regras-de-importacao"))
        assertNull(NativeLinks.targetFor("/ajustes#integracoes"))
        assertNull(NativeLinks.targetFor("/lancamentos/importar"))
        assertNull(NativeLinks.targetFor(""))
        assertNull(NativeLinks.targetFor(null))
        assertEquals(NativeLinks.Target(NativeRoutes.EXTRATO), NativeLinks.targetFor("/lancamentos/extrato?ver=outra"))
        assertEquals(NativeLinks.Target(NativeRoutes.HOME), NativeLinks.targetFor("/inicio"))
    }

    @Test
    fun investmentTabsThisApkHasOpenNatively() {
        assertEquals(NativeLinks.Target(NativeRoutes.POSICAO), NativeLinks.targetFor("/investimentos"))
        assertEquals(NativeLinks.Target(NativeRoutes.POSICAO), NativeLinks.targetFor("/investimentos/posicao"))
        assertEquals(NativeLinks.Target(NativeRoutes.POSICAO), NativeLinks.targetFor("/investments"))
        assertEquals(NativeLinks.Target(NativeRoutes.OPERACOES), NativeLinks.targetFor("/investimentos/operacoes"))
        assertEquals(NativeLinks.Target(NativeRoutes.PROVENTOS), NativeLinks.targetFor("/investimentos/proventos"))
        assertEquals(NativeLinks.Target(NativeRoutes.PROVENTOS), NativeLinks.targetFor("/proventos"))
        assertEquals(NativeLinks.Target(NativeRoutes.RENTABILIDADE), NativeLinks.targetFor("/investimentos/rentabilidade"))
        assertEquals(NativeLinks.Target(NativeRoutes.ALOCACAO), NativeLinks.targetFor("/investimentos/alocacao"))
        assertEquals(NativeLinks.Target(NativeRoutes.IR), NativeLinks.targetFor("/investimentos/ir"))
        assertEquals(NativeLinks.Target(NativeRoutes.CALCULADORA), NativeLinks.targetFor("/investimentos/calculadora"))
        assertNull(NativeLinks.targetFor("/investimentos/outra"))
        assertEquals(NativeRoutes.RENTABILIDADE, InvestimentosRoutes.routeOf(br.financas.app.ui.investimentos.InvestimentosTab.RENTABILIDADE))
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
