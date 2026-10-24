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
