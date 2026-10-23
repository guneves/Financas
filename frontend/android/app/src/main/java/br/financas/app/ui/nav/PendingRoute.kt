package br.financas.app.ui.nav

/**
 * A rota que uma tela nativa pediu sem WebView viva (NativeScreensPlugin.savePendingRoute): a
 * web vai para ela ao abrir. Par: pendingStartRoute() em frontend/src/lib/nativeScreensRules.js,
 * o mesmo prazo. Puro: PendingRouteTest.
 */
object PendingRoute {
    /** Quanto tempo a rota guardada vale: e so a ponte ate a WebView abrir. */
    const val MAX_AGE_MS = 2 * 60 * 1000L

    /**
     * A rota, se ainda vale: um caminho da propria web ("/...", nunca "//host"), guardado ha no
     * maximo [MAX_AGE_MS] (um relogio que voltou no tempo tambem invalida); senao null.
     */
    fun valid(route: String?, storedAt: Long, now: Long): String? {
        val age = now - storedAt
        return route?.takeIf { it.startsWith("/") && !it.startsWith("//") && age in 0..MAX_AGE_MS }
    }
}
