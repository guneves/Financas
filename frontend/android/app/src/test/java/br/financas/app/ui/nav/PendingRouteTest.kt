package br.financas.app.ui.nav

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PendingRouteTest {
    private val now = 1_000_000_000L

    @Test
    fun aRecentWebRouteIsDelivered() {
        assertEquals("/lancamentos/cartoes", PendingRoute.valid("/lancamentos/cartoes", now, now))
        assertEquals("/ajustes", PendingRoute.valid("/ajustes", now - PendingRoute.MAX_AGE_MS, now))
    }

    @Test
    fun staleMissingOrForeignRoutesAreDropped() {
        assertNull(PendingRoute.valid("/ajustes", now - PendingRoute.MAX_AGE_MS - 1, now))
        assertNull(PendingRoute.valid("/ajustes", now + 1, now))
        assertNull(PendingRoute.valid(null, now, now))
        assertNull(PendingRoute.valid("https://exemplo.com", now, now))
        assertNull(PendingRoute.valid("//exemplo.com", now, now))
        assertNull(PendingRoute.valid("", now, now))
    }
}
