package br.financas.app.ui.charts

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ChartScaleTest {
    @Test
    fun theTicksAreRoundAndIncludeZero() {
        assertEquals(listOf(0.0, 500.0, 1000.0, 1500.0, 2000.0), ChartScale.ticks(0.0, 1800.0))
        val mixed = ChartScale.ticks(-950.0, 2100.0)
        assertTrue(mixed.contains(0.0))
        assertTrue(mixed.first() <= -950.0)
        assertTrue(mixed.last() >= 2100.0)
        assertEquals(listOf(-1000.0, -500.0, 0.0), ChartScale.ticks(-1000.0, -200.0))
    }

    @Test
    fun aFlatSeriesStillHasAScale() {
        assertEquals(listOf(0.0, 1.0), ChartScale.ticks(0.0, 0.0))
        assertTrue(ChartScale.ticks(500.0, 500.0).last() >= 500.0)
    }
}
