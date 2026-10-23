package br.financas.app.ui.theme

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** As cores nativas sao as da web: cada token de Tokens tem o valor de frontend/src/index.css. */
class TokensTest {
    private val css = File("../../src/index.css").readText()

    private fun block(selector: String): Map<String, Int> {
        val start = css.indexOf("$selector {")
        assertTrue("bloco $selector na CSS", start >= 0)
        val body = css.substring(start, css.indexOf('}', start))
        return Regex("""--([a-z0-9-]+):\s*(\d+)\s+(\d+)\s+(\d+);""").findAll(body).associate { m ->
            val (name, r, g, b) = m.destructured
            name to ((r.toInt() shl 16) or (g.toInt() shl 8) or b.toInt())
        }
    }

    private fun assertSame(selector: String, tokens: Map<String, Int>) {
        val web = block(selector)
        for ((name, value) in tokens) {
            val expected = web[name] ?: error("--$name nao existe em $selector")
            assertEquals("--$name em $selector", "%06X".format(expected), "%06X".format(value))
        }
    }

    @Test
    fun lightMatchesTheWeb() = assertSame(":root", Tokens.light)

    @Test
    fun darkMatchesTheWeb() = assertSame(":root.dark", Tokens.dark)

    @Test
    fun bothThemesHaveTheSameNames() = assertEquals(Tokens.light.keys, Tokens.dark.keys)
}
