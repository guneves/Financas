package br.financas.app.rules

import org.junit.Assert.assertEquals
import org.junit.Test
import java.math.BigDecimal

class HomePanelsRulesTest {
    @Test
    fun deltaTextKeepsOneDecimalWithoutTrailingZero() {
        assertEquals("12,3%", HomePanelsRules.deltaText(12.34))
        assertEquals("50%", HomePanelsRules.deltaText(50.0))
        assertEquals("7,5%", HomePanelsRules.deltaText(-7.45))
    }

    @Test
    fun spendingUpIsBadDownIsGoodNearZeroIsFlat() {
        assertEquals(HomePanelsRules.DeltaTone.BAD, HomePanelsRules.deltaTone(10.0))
        assertEquals(HomePanelsRules.DeltaTone.GOOD, HomePanelsRules.deltaTone(-10.0))
        assertEquals(HomePanelsRules.DeltaTone.FLAT, HomePanelsRules.deltaTone(0.04))
        assertEquals(HomePanelsRules.DeltaTone.GOOD, HomePanelsRules.deltaTone(10.0, inverse = false))
    }

    @Test
    fun categoryColorsGroupFromTheSixthWhenMoreThanSix() {
        assertEquals(5, HomePanelsRules.categoryColorIndex(5, 6))
        assertEquals(-1, HomePanelsRules.categoryColorIndex(5, 7))
        assertEquals(4, HomePanelsRules.categoryColorIndex(4, 9))
    }

    @Test
    fun channelLabel() {
        assertEquals("25% conta", HomePanelsRules.channelLabel(BigDecimal("25"), BigDecimal("75"), BigDecimal("100")))
        assertEquals("cartão", HomePanelsRules.channelLabel(BigDecimal.ZERO, BigDecimal("75"), BigDecimal("75")))
        assertEquals("conta", HomePanelsRules.channelLabel(BigDecimal("10"), BigDecimal.ZERO, BigDecimal("10")))
    }

    @Test
    fun paceLabelsAndDirection() {
        assertEquals("Média de 3 meses", HomePanelsRules.paceAverageLabel(listOf("2026-09", "2026-08", "2026-07")))
        assertEquals("Mês de set/26", HomePanelsRules.paceAverageLabel(listOf("2026-09")))
        assertEquals(0, HomePanelsRules.paceDirection(BigDecimal("100.00"), BigDecimal("100.004")))
        assertEquals(1, HomePanelsRules.paceDirection(BigDecimal("100.01"), BigDecimal("100")))
        assertEquals(-1, HomePanelsRules.paceDirection(BigDecimal("90"), BigDecimal("100")))
    }

    @Test
    fun smallTexts() {
        assertEquals(" · 2/3", HomePanelsRules.installmentSuffix("2/3"))
        assertEquals("", HomePanelsRules.installmentSuffix("1/1"))
        assertEquals("", HomePanelsRules.installmentSuffix(null))
        assertEquals(listOf("1", "", "", "", "", "6"), (1..6).map(HomePanelsRules::paceAxisLabel))
        assertEquals(0.5f, HomePanelsRules.paidFraction(1, 2))
        assertEquals("Em destaque, a fatura de X.", HomePanelsRules.projectionNote(listOf("2026-11")) { "X" })
        assertEquals("", HomePanelsRules.projectionNote(emptyList()) { it })
    }
}
