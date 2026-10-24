// Port: mudou um, muda o outro, com um teste de cada lado.
// Os casos de frontend/src/lib/notifyRules.test.js, na mesma ordem.
package br.financas.app.rules

import br.financas.app.rules.NotifyTexts.AppStatus
import br.financas.app.rules.NotifyTexts.NotifyStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDateTime
import java.time.ZoneId

class NotifyTextsTest {
    private val zone = ZoneId.of("America/Sao_Paulo")
    private fun at(h: Int, m: Int, s: Int = 0) = LocalDateTime.of(2026, 10, 17, h, m, s).atZone(zone).toInstant().toEpochMilli()

    // node: 'hora local, com segundos quando pedido'
    @Test
    fun horaLocalComSegundosQuandoPedido() {
        assertEquals("17/10/2026 08:05", NotifyTexts.formatStamp(at(8, 5, 9), zone = zone))
        assertEquals("17/10/2026 08:05:09", NotifyTexts.formatStamp(at(8, 5, 9), seconds = true, zone = zone))
        assertEquals("", NotifyTexts.formatStamp(0, zone = zone))
    }

    // node: 'contagem no singular e no plural'
    @Test
    fun contagemNoSingularENoPlural() {
        assertEquals("nenhuma", NotifyTexts.countLabel(0))
        assertEquals("1 notificação", NotifyTexts.countLabel(1))
        assertEquals("12 notificações", NotifyTexts.countLabel(12))
    }

    // node: 'acesso permitido ou nao'
    @Test
    fun acessoPermitidoOuNao() {
        assertEquals(NotifyTexts.Tone.SUCCESS, NotifyTexts.accessMessage(NotifyStatus(granted = true))!!.tone)
        assertEquals(NotifyTexts.Tone.WARNING, NotifyTexts.accessMessage(NotifyStatus(granted = false))!!.tone)
        assertNull(NotifyTexts.accessMessage(null))
    }

    // node: 'o leitor: ligado, desligado depois de ligar, ou nunca ligado'
    @Test
    fun oLeitor() {
        assertNull(NotifyTexts.listenerMessage(NotifyStatus(granted = false, connectedAt = at(8, 0)), zone))
        assertTrue(NotifyTexts.listenerMessage(NotifyStatus(granted = true, connectedAt = at(9, 0), disconnectedAt = at(8, 0)), zone)!!.contains("ligado pelo Android em 17/10/2026 09:00"))
        assertTrue(NotifyTexts.listenerMessage(NotifyStatus(granted = true, connectedAt = at(8, 0), disconnectedAt = at(9, 0)), zone)!!.contains("desligou o leitor em 17/10/2026 09:00"))
        assertTrue(NotifyTexts.listenerMessage(NotifyStatus(granted = true), zone)!!.contains("ainda não ligou"))
    }

    // node: 'configuracoes restritas: so sem acesso e a partir do Android 13'
    @Test
    fun configuracoesRestritas() {
        assertEquals(true, NotifyTexts.showsRestrictedHelp(NotifyStatus(granted = false, sdk = 33)))
        assertEquals(true, NotifyTexts.showsRestrictedHelp(NotifyStatus(granted = false, sdk = 36)))
        assertEquals(false, NotifyTexts.showsRestrictedHelp(NotifyStatus(granted = false, sdk = 32)))
        assertEquals(false, NotifyTexts.showsRestrictedHelp(NotifyStatus(granted = true, sdk = 36)))
        assertEquals(false, NotifyTexts.showsRestrictedHelp(null))
    }

    // node: 'quem instalou o APK, em palavras'
    @Test
    fun quemInstalouOApk() {
        assertTrue(NotifyTexts.installerLabel("com.android.shell").contains("adb"))
        assertTrue(NotifyTexts.installerLabel("br.financas.app").contains("próprio app"))
        assertTrue(NotifyTexts.installerLabel("com.google.android.packageinstaller").contains("arquivo APK"))
        assertEquals("com.outra.loja", NotifyTexts.installerLabel("com.outra.loja"))
        assertEquals("desconhecido", NotifyTexts.installerLabel(null))
    }

    // node: 'o resumo da captura'
    @Test
    fun oResumoDaCaptura() {
        assertEquals("Desligada: nenhuma notificação é guardada.", NotifyTexts.captureMessage(NotifyStatus(captureOn = false, total = 0), zone))
        assertTrue(NotifyTexts.captureMessage(NotifyStatus(captureOn = false, total = 1), zone).startsWith("Desligada. 1 notificação guardada continua aqui"))
        assertTrue(NotifyTexts.captureMessage(NotifyStatus(captureOn = false, total = 3), zone).contains("3 notificações guardadas continuam aqui"))
        assertEquals("Ligada desde 17/10/2026 08:00. Nada chegou ainda dos apps abaixo.", NotifyTexts.captureMessage(NotifyStatus(captureOn = true, captureSince = at(8, 0), total = 0), zone))
        assertEquals("Ligada desde 17/10/2026 08:00: 2 notificações guardadas.", NotifyTexts.captureMessage(NotifyStatus(captureOn = true, captureSince = at(8, 0), total = 2), zone))
        assertEquals("", NotifyTexts.captureMessage(null, zone))
    }

    // node: 'a lista de apps: o adb so quando guardou algo'
    @Test
    fun aListaDeApps() {
        val rows = NotifyTexts.appRows(
            NotifyStatus(
                apps = listOf(
                    AppStatus("com.samsung.android.spay", "Samsung Wallet", true, 2, at(14, 30)),
                    AppStatus("com.itaucard.activity", "Itaú Cartões", false, 0, 0),
                    AppStatus("com.itau", "Itaú", true, 0, 0),
                    AppStatus("com.android.shell", "Teste (adb)", true, 0, 0),
                ),
            ),
            zone,
        )
        assertEquals(listOf("com.samsung.android.spay", "com.itaucard.activity", "com.itau"), rows.map { it.packageName })
        assertEquals("2 notificações · última 17/10/2026 14:30", rows[0].detail)
        assertEquals("não instalado", rows[1].detail)
        assertEquals("nada ainda", rows[2].detail)
        val withShell = NotifyTexts.appRows(NotifyStatus(apps = listOf(AppStatus("com.android.shell", "Teste (adb)", true, 1, at(9, 0)))), zone)
        assertEquals(1, withShell.size)
        assertEquals(emptyList<NotifyTexts.AppRow>(), NotifyTexts.appRows(null, zone))
    }

    // node: 'o comando de teste usa o caminho do plano (bigtext, titulo, tag, texto)'
    @Test
    fun oComandoDeTeste() {
        assertTrue(Regex("^adb shell cmd notification post -S bigtext -t \"[^\"]+\" \\S+ \"[^\"]+\"$").matches(NotifyTexts.ADB_TEST_COMMAND))
    }
}
