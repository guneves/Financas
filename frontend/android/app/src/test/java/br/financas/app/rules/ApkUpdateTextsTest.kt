// Port: mudou um, muda o outro, com um teste de cada lado.
// Os casos de apkPrompt e installStatusMessage de frontend/src/lib/appBundleRules.test.js.
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
        val latest = Latest(10012, "2026.10.17-abc", 1)
        assertNull(ApkUpdateTexts.apkPrompt(null))
        assertNull(ApkUpdateTexts.apkPrompt(ApkState(false, latest, 1)))
        assertNull(ApkUpdateTexts.apkPrompt(ApkState(true, null, 1)))
        assertEquals(ApkUpdateTexts.Prompt("2026.10.17-abc", false), ApkUpdateTexts.apkPrompt(ApkState(true, latest, 1)))
    }

    // node: 'o APK e necessario quando a tela do servidor pede um nivel acima do instalado'
    @Test
    fun oApkENecessarioQuandoPedeNivelAcima() {
        val apk = ApkState(true, Latest(10013, null, 2), 1)
        assertEquals(true, ApkUpdateTexts.apkPrompt(apk)!!.required)
        assertEquals("10013", ApkUpdateTexts.apkPrompt(apk)!!.versionName)
        val sameLevel = apk.copy(latest = Latest(10013, null, 1))
        assertEquals(false, ApkUpdateTexts.apkPrompt(sameLevel)!!.required)
        assertEquals(true, ApkUpdateTexts.apkPrompt(sameLevel, bundleLevel = 2)!!.required)
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
