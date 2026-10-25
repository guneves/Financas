package br.financas.app.ui.nav

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ShellNavTest {
    @Test
    fun everyPageBelongsToOneSectionAndTheLoginToNone() {
        assertNull(ShellNav.sectionOf(NativeRoutes.LOGIN))
        assertNull(ShellNav.sectionOf(null))
        assertEquals(ShellNav.Section.HOME, ShellNav.sectionOf(NativeRoutes.HOME))
        for (route in listOf(NativeRoutes.EXTRATO, NativeRoutes.INBOX, NativeRoutes.CARTOES, NativeRoutes.A_RECEBER)) {
            assertEquals(route, ShellNav.Section.LANCAMENTOS, ShellNav.sectionOf(route))
        }
        for (route in listOf(NativeRoutes.ORCAMENTO, NativeRoutes.RECORRENTES, NativeRoutes.METAS)) {
            assertEquals(route, ShellNav.Section.PLANEJAR, ShellNav.sectionOf(route))
        }
        for (route in NativeRoutes.INVESTMENTS) assertEquals(route, ShellNav.Section.INVESTIR, ShellNav.sectionOf(route))
        assertEquals(ShellNav.Section.AJUSTES, ShellNav.sectionOf(NativeRoutes.AJUSTES))
        // Toda pagina do NavHost tem secao (a barra sempre acende uma).
        for (route in NativeRoutes.ALL) assertTrue(route, ShellNav.sectionOf(route) != null)
    }

    @Test
    fun eachSectionOpensOnItsFirstTab() {
        assertEquals(
            listOf(NativeRoutes.HOME, NativeRoutes.EXTRATO, NativeRoutes.ORCAMENTO, NativeRoutes.POSICAO, NativeRoutes.AJUSTES),
            ShellNav.Section.entries.map { it.root },
        )
    }

    @Test
    fun theNewEntryButtonAndBack() {
        assertTrue(ShellNav.showsNewEntry(NativeRoutes.HOME))
        assertTrue(ShellNav.showsNewEntry(NativeRoutes.PROVENTOS))
        assertFalse(ShellNav.showsNewEntry(NativeRoutes.AJUSTES))
        assertFalse(ShellNav.showsNewEntry(NativeRoutes.LOGIN))
        assertFalse(ShellNav.backGoesHome(NativeRoutes.HOME))
        assertFalse(ShellNav.backGoesHome(NativeRoutes.LOGIN))
        assertTrue(ShellNav.backGoesHome(NativeRoutes.INBOX))
    }
}
