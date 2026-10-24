// Port: mudou um, muda o outro, com um teste de cada lado.
// Este arquivo e o port da metade do APK de frontend/src/lib/appBundleRules.js (apkPrompt,
// installStatusMessage; testes: appBundleRules.test.js e ApkUpdateTextsTest.kt). A metade da
// tela baixada (AppBundle) segue na web: Versao do app nativa so oferece o APK novo.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

object ApkUpdateTexts {

    /** O que ApkUpdatePlugin.latest devolve. */
    data class Latest(val versionCode: Long, val versionName: String?, val nativeLevel: Int)

    data class ApkState(val newer: Boolean, val latest: Latest?, val nativeLevel: Int)

    data class Prompt(val versionName: String, val required: Boolean)

    /**
     * "Nova versão disponível" quando o publicado e mais novo; `required` quando ele (ou a tela
     * do servidor, [bundleLevel] de um check "incompatible") pede um nivel nativo acima do instalado.
     */
    fun apkPrompt(apk: ApkState?, bundleLevel: Int = 0): Prompt? {
        val latest = apk?.latest
        if (apk == null || !apk.newer || latest == null) return null
        val installed = apk.nativeLevel
        return Prompt(
            versionName = latest.versionName?.takeIf { it.isNotEmpty() } ?: latest.versionCode.toString(),
            required = bundleLevel > installed || latest.nativeLevel > installed,
        )
    }

    enum class Tone { INFO, WARNING, SUCCESS, NEUTRAL, DANGER }

    data class Message(val tone: Tone, val text: String)

    /** O texto de cada resposta de ApkUpdatePlugin.install (ou de uma falha dela). */
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
