// O que Rentabilidade.jsx faz inline (sem teste do lado web): os casos sao o comportamento da web.
package br.financas.app.rules

import br.financas.app.rules.ReturnsRules.Comparison
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test
import java.math.BigDecimal

class ReturnsRulesTest {
    private fun pct(text: String) = BigDecimal(text)

    @Test
    fun theCdiCardComesFirstWithTheRoundedDifference() {
        val ibov = Comparison("IBOV", "Ibovespa", available = true, complete = true, periodPercent = pct("4.1"), differencePp = pct("3.9"))
        val items = ReturnsRules.comparisonItems(pct("10.005"), true, pct("2"), listOf(ibov))
        assertEquals(listOf("CDI", "IBOV"), items.map { it.code })
        assertEquals(pct("8.01"), items[0].differencePp)
        assertNull(items[0].note)
        val down = ReturnsRules.comparisonItems(null, false, null, emptyList())[0]
        assertFalse(down.available)
        assertNull(down.differencePp)
        assertEquals("O BCB não respondeu o CDI.", down.note)
    }

    @Test
    fun hints() {
        assertEquals("indisponível", ReturnsRules.comparisonHint(Comparison("X", "X", false, false)))
        assertEquals("7 de 12 meses", ReturnsRules.comparisonHint(Comparison("X", "X", true, false, monthsCovered = 7, monthsTotal = 12)))
        assertEquals("carteira +1,50 p.p.", ReturnsRules.comparisonHint(Comparison("X", "X", true, true, differencePp = pct("1.5"))))
        assertEquals("carteira -0,25 p.p.", ReturnsRules.comparisonHint(Comparison("X", "X", true, true, differencePp = pct("-0.25"))))
        assertEquals("carteira 0,00 p.p.", ReturnsRules.comparisonHint(Comparison("X", "X", true, true, differencePp = pct("0"))))
        assertEquals("no período", ReturnsRules.comparisonHint(Comparison("X", "X", true, true)))
    }

    @Test
    fun tonesAndTexts() {
        assertEquals(ReturnsRules.Tone.MUTED, ReturnsRules.toneOf(null))
        assertEquals(ReturnsRules.Tone.GAIN, ReturnsRules.toneOf(pct("0.01")))
        assertEquals(ReturnsRules.Tone.LOSS, ReturnsRules.toneOf(pct("-1")))
        assertEquals(ReturnsRules.Tone.NEUTRAL, ReturnsRules.toneOf(pct("0")))
        assertEquals("—", ReturnsRules.signedPercent(null))
        assertEquals("+1,23%", ReturnsRules.signedPercent(pct("1.23")))
        assertEquals("1,3%", ReturnsRules.percentAxis(1.25))
        assertEquals("-2%", ReturnsRules.percentAxis(-2.0))
        assertEquals("set/25 a out/26 (desde a 1ª operação) · TWR, valor bruto", ReturnsRules.periodHint("2025-09", "2026-10", true))
        assertEquals("set/25 a out/26 · TWR, valor bruto", ReturnsRules.periodHint("2025-09", "2026-10", false))
        assertEquals("TWR, valor bruto", ReturnsRules.periodHint(null, null, false))
    }

    @Test
    fun visibleIndicesAndToggle() {
        val items = listOf(
            Comparison("CDI", "CDI", true, true),
            Comparison("IPCA", "IPCA", false, false),
            Comparison("IBOV", "Ibovespa", true, true),
            Comparison("IFIX", "IFIX", true, true),
        )
        assertEquals(listOf("CDI", "IBOV"), ReturnsRules.shown(items, ReturnsRules.DEFAULT_VISIBLE).map { it.code })
        assertEquals(setOf("CDI", "IPCA", "IBOV", "IFIX"), ReturnsRules.toggle(ReturnsRules.DEFAULT_VISIBLE, "IFIX"))
        assertEquals(setOf("IPCA", "IBOV"), ReturnsRules.toggle(ReturnsRules.DEFAULT_VISIBLE, "CDI"))
    }
}
