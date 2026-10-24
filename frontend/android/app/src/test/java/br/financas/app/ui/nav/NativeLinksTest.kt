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
        assertNull(NativeLinks.targetFor("/lancamentos/a-receber"))
        assertNull(NativeLinks.targetFor("/lancamentos/extrato?web=1"))
        assertNull(NativeLinks.targetFor("/ajustes#cartoes"))
        assertNull(NativeLinks.targetFor(""))
        assertNull(NativeLinks.targetFor(null))
        assertEquals(NativeLinks.Target(NativeRoutes.EXTRATO), NativeLinks.targetFor("/lancamentos/extrato?ver=outra"))
    }
}
