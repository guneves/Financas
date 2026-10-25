// Os casos de apkPrompt e installStatusMessage (eram os de lib/appBundleRules.test.js).
package br.financas.app.rules

import br.financas.app.rules.ApkUpdateTexts.ApkState
import br.financas.app.rules.ApkUpdateTexts.Latest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ApkUpdateTextsTest {

    // node: 'oferece o APK so quando o publicado e mais novo'
    @Test
    fun ofereceOApkSoQuandoOPublicadoEMaisNovo() {
        val latest = Latest(10012, "2026.10.17-abc")
        assertNull(ApkUpdateTexts.apkPrompt(null))
        assertNull(ApkUpdateTexts.apkPrompt(ApkState(false, latest)))
        assertNull(ApkUpdateTexts.apkPrompt(ApkState(true, null)))
        assertEquals(ApkUpdateTexts.Prompt("2026.10.17-abc"), ApkUpdateTexts.apkPrompt(ApkState(true, latest)))
        assertEquals("10013", ApkUpdateTexts.apkPrompt(ApkState(true, Latest(10013, null)))!!.versionName)
    }

    // node: 'cada resposta da instalacao tem um texto'
    @Test
    fun cadaRespostaDaInstalacaoTemUmTexto() {
        for (status in listOf("installing", "needs-permission", "up-to-date", "busy")) {
            val message = ApkUpdateTexts.installStatusMessage(status)!!
            assertTrue(status, message.text.isNotEmpty() && !message.text.startsWith("Resposta inesperada"))
        }
        assertEquals("falhou", ApkUpdateTexts.installStatusMessage("error", "falhou")!!.text)
        assertNull(ApkUpdateTexts.installStatusMessage(null))
    }
}
