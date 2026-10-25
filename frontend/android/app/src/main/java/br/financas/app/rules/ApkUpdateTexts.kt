// O aviso do APK novo (o Inicio e Ajustes › Versão do app): quando oferecer e o texto de cada
// resposta da instalacao (update/ApkUpdater.java). Era o port de apkPrompt/installStatusMessage
// de lib/appBundleRules.js, que saiu com a WebView. Testes: ApkUpdateTextsTest.kt.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

object ApkUpdateTexts {

    /** O APK publicado, como ApkUpdater.latestState o devolve. */
    data class Latest(val versionCode: Long, val versionName: String?)

    data class ApkState(val newer: Boolean, val latest: Latest?)

    data class Prompt(val versionName: String)

    /** "Nova versão disponível (<nome>)" quando o publicado e mais novo que o instalado. */
    fun apkPrompt(apk: ApkState?): Prompt? {
        val latest = apk?.latest
        if (apk == null || !apk.newer || latest == null) return null
        return Prompt(latest.versionName?.takeIf { it.isNotEmpty() } ?: latest.versionCode.toString())
    }

    enum class Tone { INFO, WARNING, SUCCESS, NEUTRAL, DANGER }

    data class Message(val tone: Tone, val text: String)

    /** O texto de cada resposta de ApkUpdater.installNow (ou de uma falha dela). */
    fun installStatusMessage(status: String?, message: String? = null): Message? = when (status) {
        null -> null
        "error" -> Message(Tone.DANGER, message?.takeIf { it.isNotEmpty() } ?: "Não foi possível baixar o APK novo.")
        "installing" -> Message(Tone.INFO, "Instalador aberto. Toque em \"Atualizar\"; os dados do app são mantidos.")
        "needs-permission" -> Message(Tone.WARNING, "Permita \"Instalar apps desconhecidos\" para o Finanças e volte: o download começa sozinho.")
        "up-to-date" -> Message(Tone.SUCCESS, "O APK instalado já é o mais novo.")
        "busy" -> Message(Tone.NEUTRAL, "Já baixando o APK novo…")
        else -> Message(Tone.NEUTRAL, "Resposta inesperada: $status")
    }
}
