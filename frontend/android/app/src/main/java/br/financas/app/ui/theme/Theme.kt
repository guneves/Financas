package br.financas.app.ui.theme

import android.content.Context
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext

/** As cores do app numa tela nativa, pelos nomes da web (Tokens). */
@Immutable
class Palette(private val tokens: Map<String, Int>) {
    operator fun get(name: String): Color =
        Color(0xFF000000 or (tokens[name] ?: error("Token sem valor: $name")).toLong())

    val background get() = this["zinc-50"]
    val surface get() = this["white"]
    val text get() = this["zinc-950"]
    val muted get() = this["zinc-500"]
    val border get() = this["zinc-200"]
    val accent get() = this["emerald-500"]
    val onAccent get() = this["on-accent"]
    val gain get() = this["emerald-600"]
    val loss get() = this["rose-600"]
    val warning get() = this["amber-600"]
    val info get() = this["sky-600"]
    val brand get() = this["brand"]
    val brandInk get() = this["brand-ink"]
}

val LocalPalette = staticCompositionLocalOf { Palette(Tokens.light) }

/**
 * O tema das telas nativas. Escuro ou claro como a ultima escolha da web (Ajustes › Aparência,
 * gravada pelo ShellPlugin em ShellPrefs); antes da primeira, o do sistema.
 */
@Composable
fun FinancasTheme(
    dark: Boolean = ShellPrefs.dark(LocalContext.current) ?: isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val palette = Palette(Tokens.of(dark))
    CompositionLocalProvider(LocalPalette provides palette) {
        MaterialTheme(colorScheme = colorScheme(palette, dark), content = content)
    }
}

private fun colorScheme(p: Palette, dark: Boolean): ColorScheme {
    val base = if (dark) darkColorScheme() else lightColorScheme()
    return base.copy(
        primary = p.accent,
        onPrimary = p.onAccent,
        primaryContainer = p["emerald-50"],
        onPrimaryContainer = p["emerald-700"],
        secondary = p.brand,
        onSecondary = p.brandInk,
        background = p.background,
        onBackground = p.text,
        surface = p.surface,
        onSurface = p.text,
        surfaceVariant = p["zinc-100"],
        onSurfaceVariant = p.muted,
        surfaceContainer = p.surface,
        surfaceContainerLow = p.surface,
        surfaceContainerHigh = p["zinc-100"],
        outline = p["zinc-300"],
        outlineVariant = p.border,
        error = p.loss,
        onError = p["white"],
        errorContainer = p["rose-50"],
        onErrorContainer = p.loss,
    )
}

/**
 * O tema escolhido na web, guardado para as telas nativas. A escolha mora no localStorage da
 * WebView (lib/theme.js), que o Kotlin nao le; o ShellPlugin recebe cada troca (setTheme) e a
 * grava aqui. O modo privado tambem mora aqui, nos dois sentidos (ver saveValuesHidden).
 */
object ShellPrefs {
    private const val PREFS = "financas_shell"
    private const val DARK = "dark"
    private const val VALUES_HIDDEN = "values_hidden"

    @JvmStatic
    fun saveDark(context: Context, dark: Boolean) {
        prefs(context).edit().putBoolean(DARK, dark).apply()
    }

    @JvmStatic
    fun dark(context: Context): Boolean? {
        val prefs = prefs(context)
        return if (prefs.contains(DARK)) prefs.getBoolean(DARK, false) else null
    }

    /**
     * O modo privado (o olho): o mesmo nas duas interfaces. A web grava cada troca
     * (ShellPlugin.setValuesHidden, lib/nativeApp.js) e le a ultima ao voltar para a WebView
     * (getValuesHidden); o Inicio nativo grava a dele aqui.
     */
    @JvmStatic
    fun saveValuesHidden(context: Context, hidden: Boolean) {
        prefs(context).edit().putBoolean(VALUES_HIDDEN, hidden).apply()
    }

    /** O modo privado guardado; null antes da primeira escolha (vale o da web). */
    @JvmStatic
    fun valuesHidden(context: Context): Boolean? {
        val prefs = prefs(context)
        return if (prefs.contains(VALUES_HIDDEN)) prefs.getBoolean(VALUES_HIDDEN, false) else null
    }

    private fun prefs(context: Context) =
        context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
}
