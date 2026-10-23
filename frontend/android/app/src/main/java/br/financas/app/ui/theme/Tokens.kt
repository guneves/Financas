package br.financas.app.ui.theme

/**
 * Os tokens de cor do app (frontend/src/index.css, blocos `:root` e `:root.dark`) para as telas
 * nativas, como 0xRRGGBB. Os mesmos nomes da CSS, para que as duas interfaces tenham as mesmas
 * cores; TokensTest le a CSS e falha quando um valor daqui diverge. So os tokens que as telas
 * nativas usam: um novo entra aqui com o nome da CSS.
 *
 * Como na web, o escuro inverte a escala neutra: `white` vira a superficie escura e `zinc-950`
 * o texto claro. Verde, vermelho, ambar e azul so quando significam ganho, perda, aviso e
 * informacao (CLAUDE.md, "Visual rules").
 */
object Tokens {
    val light: Map<String, Int> = mapOf(
        "zinc-50" to 0xEFF2ED,
        "zinc-100" to 0xE6EAE3,
        "zinc-200" to 0xDCE2D8,
        "zinc-300" to 0xC9D1C5,
        "zinc-400" to 0x99A59C,
        "zinc-500" to 0x66736B,
        "zinc-600" to 0x4F5D55,
        "zinc-700" to 0x3C4841,
        "zinc-800" to 0x27322C,
        "zinc-900" to 0x1A2620,
        "zinc-950" to 0x12201A,
        "emerald-50" to 0xECFDF5,
        "emerald-500" to 0x10B981,
        "emerald-600" to 0x059669,
        "emerald-700" to 0x047857,
        "rose-50" to 0xFFF1F2,
        "rose-600" to 0xE11D48,
        "amber-50" to 0xFFFBEB,
        "amber-600" to 0xD97706,
        "sky-50" to 0xF0F9FF,
        "sky-600" to 0x0284C7,
        "white" to 0xFFFFFF,
        "brand" to 0x0B3B2C,
        "brand-soft" to 0xB9D7C8,
        "brand-ink" to 0xF2FBF6,
        "on-accent" to 0x052E1F,
    )

    val dark: Map<String, Int> = mapOf(
        "zinc-50" to 0x0B1210,
        "zinc-100" to 0x1B2621,
        "zinc-200" to 0x26332C,
        "zinc-300" to 0x33413A,
        "zinc-400" to 0x5F6E66,
        "zinc-500" to 0x85938A,
        "zinc-600" to 0xA9B6AE,
        "zinc-700" to 0xC3CEC7,
        "zinc-800" to 0xD5DED8,
        "zinc-900" to 0xE3EAE5,
        "zinc-950" to 0xEEF3EF,
        "emerald-50" to 0x0F2A1F,
        "emerald-500" to 0x34D399,
        "emerald-600" to 0x34D399,
        "emerald-700" to 0x6EE7B7,
        "rose-50" to 0x2A1416,
        "rose-600" to 0xF87171,
        "amber-50" to 0x2A200C,
        "amber-600" to 0xF5B94A,
        "sky-50" to 0x0E2231,
        "sky-600" to 0x7CC4F5,
        "white" to 0x131C18,
        "brand" to 0x1F5A44,
        "brand-soft" to 0xB9D7C8,
        "brand-ink" to 0xF2FBF6,
        "on-accent" to 0x052E1F,
    )

    fun of(dark: Boolean): Map<String, Int> = if (dark) this.dark else light
}
