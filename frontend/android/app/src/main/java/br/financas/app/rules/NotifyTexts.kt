// Os textos de Ajustes › Notificações dos bancos (eram o port de lib/notifyRules.js, que saiu
// com a WebView; testes: NotifyTextsTest.kt). O estado vem de NotifyAccess.status(Context)
// (NotifyStatus e ele lido); a lista de apps ouvidos e notify/NotifyRules.java.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import java.time.Instant
import java.time.ZoneId

object NotifyTexts {

    /** Android 13: um APK aberto no celular so recebe o acesso depois de "Permitir configurações restritas". */
    const val RESTRICTED_SETTINGS_SDK = 33

    const val ADB_TEST_COMMAND = "adb shell cmd notification post -S bigtext -t \"Compra aprovada\" teste \"Compra de R\$ 10,00 em LOJA TESTE\""

    data class AppStatus(val packageName: String, val label: String, val installed: Boolean, val count: Long, val lastPostedAt: Long)

    /** O { granted, captureOn, ... } de NotifyAccess.status(). */
    data class NotifyStatus(
        val granted: Boolean = false,
        val captureOn: Boolean = false,
        val captureSince: Long = 0,
        val connectedAt: Long = 0,
        val disconnectedAt: Long = 0,
        val acceptsShell: Boolean = false,
        val sdk: Int = 0,
        val installer: String? = null,
        val apps: List<AppStatus> = emptyList(),
        val total: Int = 0,
    )

    enum class Tone { SUCCESS, WARNING }

    data class Message(val tone: Tone, val text: String)

    data class AppRow(val packageName: String, val label: String, val detail: String)

    private fun pad(value: Int) = value.toString().padStart(2, '0')

    /** Hora local do aparelho: "17/10/2026 08:05" (com segundos na lista). 0 -> "". */
    fun formatStamp(ms: Long, seconds: Boolean = false, zone: ZoneId = ZoneId.systemDefault()): String {
        if (ms == 0L) return ""
        val date = Instant.ofEpochMilli(ms).atZone(zone)
        val day = "${pad(date.dayOfMonth)}/${pad(date.monthValue)}/${date.year}"
        val time = "${pad(date.hour)}:${pad(date.minute)}" + if (seconds) ":${pad(date.second)}" else ""
        return "$day $time"
    }

    fun countLabel(count: Long): String = when (count) {
        0L -> "nenhuma"
        1L -> "1 notificação"
        else -> "$count notificações"
    }

    fun accessMessage(status: NotifyStatus?): Message? {
        if (status == null) return null
        if (status.granted) return Message(Tone.SUCCESS, "Acesso permitido: o Android entrega ao Finanças as notificações dos apps abaixo, mesmo com o app fechado.")
        return Message(Tone.WARNING, "Sem acesso às notificações. Toque em “Abrir acesso às notificações” e ligue o Finanças.")
    }

    fun listenerMessage(status: NotifyStatus?, zone: ZoneId = ZoneId.systemDefault()): String? {
        if (status == null || !status.granted) return null
        if (status.connectedAt != 0L && status.connectedAt >= status.disconnectedAt) {
            return "Leitor ligado pelo Android em ${formatStamp(status.connectedAt, zone = zone)}."
        }
        if (status.disconnectedAt != 0L) {
            return "O Android desligou o leitor em ${formatStamp(status.disconnectedAt, zone = zone)}. Se não voltar sozinho, desligue e ligue o acesso de novo."
        }
        return "O Android ainda não ligou o leitor. Feche e abra o app; se continuar assim, desligue e ligue o acesso de novo."
    }

    fun showsRestrictedHelp(status: NotifyStatus?): Boolean = status != null && !status.granted && status.sdk >= RESTRICTED_SETTINGS_SDK

    private val INSTALLERS = mapOf(
        "com.android.shell" to "o cabo USB (adb install)",
        "br.financas.app" to "o próprio app (Nova versão disponível)",
        "com.android.packageinstaller" to "o instalador do Android (arquivo APK aberto no celular)",
        "com.google.android.packageinstaller" to "o instalador do Android (arquivo APK aberto no celular)",
        "com.samsung.android.packageinstaller" to "o instalador do Android (arquivo APK aberto no celular)",
        "com.android.vending" to "a Play Store",
    )

    fun installerLabel(installer: String?): String {
        if (installer.isNullOrEmpty()) return "desconhecido"
        return INSTALLERS[installer] ?: installer
    }

    fun captureMessage(status: NotifyStatus?, zone: ZoneId = ZoneId.systemDefault()): String {
        if (status == null) return ""
        val total = status.total.toLong()
        val one = total == 1L
        if (status.captureOn) {
            val since = if (status.captureSince != 0L) " desde ${formatStamp(status.captureSince, zone = zone)}" else ""
            return if (total != 0L) "Ligada$since: ${countLabel(total)} guardada${if (one) "" else "s"}."
            else "Ligada$since. Nada chegou ainda dos apps abaixo."
        }
        return if (total != 0L) "Desligada. ${countLabel(total)} guardada${if (one) "" else "s"} continua${if (one) "" else "m"} aqui até exportar ou apagar."
        else "Desligada: nenhuma notificação é guardada."
    }

    /** Os apps ouvidos, na ordem do Java; o shell do adb so quando guardou algo. */
    fun appRows(status: NotifyStatus?, zone: ZoneId = ZoneId.systemDefault()): List<AppRow> =
        status?.apps.orEmpty()
            .filter { it.count > 0 || it.packageName != "com.android.shell" }
            .map { app ->
                val detail = when {
                    app.count > 0 -> "${countLabel(app.count)} · última ${formatStamp(app.lastPostedAt, zone = zone)}"
                    !app.installed -> "não instalado"
                    else -> "nada ainda"
                }
                AppRow(app.packageName, app.label, detail)
            }
}
