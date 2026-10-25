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
 * O tema das telas nativas: a escolha de Ajustes › Aparência (ShellPrefs); "Sistema" (e antes da
 * primeira escolha) segue o do celular.
 */
@Composable
fun FinancasTheme(
    dark: Boolean = ShellPrefs.isDark(LocalContext.current, isSystemInDarkTheme()),
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
 * O que o app guarda deste aparelho para a casca: o tema (Ajustes › Aparência) e o modo privado
 * (o olho). Os valores gravados pela WebView antes de ela sair (o "dark" de cada troca de tema)
 * continuam valendo ate a primeira escolha nativa.
 */
object ShellPrefs {
    private const val PREFS = "financas_shell"
    private const val DARK = "dark"
    private const val VALUES_HIDDEN = "values_hidden"
    private const val THEME = "theme"

    /** Escuro? A escolha guardada; "system" (ou nenhuma) segue [systemDark]. */
    @JvmStatic
    fun isDark(context: Context, systemDark: Boolean): Boolean {
        val prefs = prefs(context)
        return when (prefs.getString(THEME, null)) {
            "dark" -> true
            "light" -> false
            "system" -> systemDark
            // Sem escolha: o ultimo tema que a WebView aplicou, se houver.
            else -> if (prefs.contains(DARK)) prefs.getBoolean(DARK, false) else systemDark
        }
    }

    /** O modo privado (o olho), o mesmo em todas as paginas. */
    @JvmStatic
    fun saveValuesHidden(context: Context, hidden: Boolean) {
        prefs(context).edit().putBoolean(VALUES_HIDDEN, hidden).apply()
    }

    /** O modo privado guardado; null antes da primeira escolha. */
    @JvmStatic
    fun valuesHidden(context: Context): Boolean? {
        val prefs = prefs(context)
        return if (prefs.contains(VALUES_HIDDEN)) prefs.getBoolean(VALUES_HIDDEN, false) else null
    }

    /** A escolha de Aparência: "system", "light" ou "dark". */
    @JvmStatic
    fun themePreference(context: Context): String = prefs(context).getString(THEME, null)?.takeIf { it in THEMES } ?: "system"

    /** Ajustes › Aparência trocou o tema (a Activity e recriada para as barras do sistema). */
    @JvmStatic
    fun saveThemePreference(context: Context, preference: String) {
        val choice = preference.takeIf { it in THEMES } ?: "system"
        prefs(context).edit().putString(THEME, choice).remove(DARK).apply()
    }

    private val THEMES = setOf("system", "light", "dark")

    private fun prefs(context: Context) =
        context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
}
