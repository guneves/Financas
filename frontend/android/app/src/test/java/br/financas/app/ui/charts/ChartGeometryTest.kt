package br.financas.app.ui.charts

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ChartGeometryTest {
    private val eps = 0.001f

    @Test
    fun theDonutStartsAtTheTopAndClosesTheCircle() {
        val slices = ChartGeometry.donutSlices(listOf(50.0, 25.0, 25.0))
        assertEquals(listOf(0, 1, 2), slices.map { it.index })
        assertEquals(-90f, slices[0].startAngle, eps)
        assertEquals(180f, slices[0].sweepAngle, eps)
        assertEquals(90f, slices[1].startAngle, eps)
        assertEquals(90f, slices[1].sweepAngle, eps)
        assertEquals(180f, slices[2].startAngle, eps)
        assertEquals(270f, slices[2].startAngle + slices[2].sweepAngle, eps)
    }

    @Test
    fun zeroAndNegativeHaveNoSliceButKeepTheirIndex() {
        val slices = ChartGeometry.donutSlices(listOf(0.0, 30.0, -5.0, Double.NaN, 10.0))
        assertEquals(listOf(1, 4), slices.map { it.index })
        assertEquals(270f, slices[0].sweepAngle, eps)
        assertTrue(ChartGeometry.donutSlices(listOf(0.0, -1.0)).isEmpty())
        assertTrue(ChartGeometry.donutSlices(emptyList()).isEmpty())
    }

    @Test
    fun theGapSeparatesSlicesButNotALoneOne() {
        val slices = ChartGeometry.donutSlices(listOf(1.0, 1.0), gapDegrees = 4f)
        assertEquals(-88f, slices[0].startAngle, eps)
        assertEquals(176f, slices[0].sweepAngle, eps)
        assertEquals(92f, slices[1].startAngle, eps)
        val alone = ChartGeometry.donutSlices(listOf(7.0), gapDegrees = 4f).single()
        assertEquals(360f, alone.sweepAngle, eps)
        // Uma fatia minuscula nao fica com angulo negativo.
        val tiny = ChartGeometry.donutSlices(listOf(1000.0, 1.0), gapDegrees = 4f)
        assertTrue(tiny[1].sweepAngle > 0f)
    }

    @Test
    fun aBarGrowsUpOrDownFromZero() {
        // Escala -1000..2000 num plot de 300 px a partir de y = 10: o zero fica em y = 210.
        val up = ChartGeometry.signedBar(1000.0, -1000.0, 2000.0, 10f, 300f)
        assertEquals(110f, up.top, eps)
        assertEquals(210f, up.bottom, eps)
        val down = ChartGeometry.signedBar(-500.0, -1000.0, 2000.0, 10f, 300f)
        assertEquals(210f, down.top, eps)
        assertEquals(260f, down.bottom, eps)
        assertEquals(50f, down.height, eps)
        assertEquals(0f, ChartGeometry.signedBar(0.0, -1000.0, 2000.0, 10f, 300f).height, eps)
    }

    @Test
    fun groupedBarsAreCenteredInTheSlot() {
        // 2 barras de 10 + 2 de folga = 22 px num slot de 40 que comeca em 30: (40 - 22) / 2 = 9.
        assertEquals(listOf(39f, 51f), ChartGeometry.groupedBarLefts(30f, 40f, 2, 10f, 2f))
        assertEquals(listOf(45f), ChartGeometry.groupedBarLefts(30f, 40f, 1, 10f, 2f))
        assertTrue(ChartGeometry.groupedBarLefts(0f, 40f, 0, 10f, 2f).isEmpty())
    }

    @Test
    fun aGapBreaksTheLine() {
        val runs = ChartGeometry.lineRuns(listOf(1.0, 2.0, null, 4.0, Double.NaN, null, 6.0, 7.0))
        assertEquals(
            listOf(listOf(0 to 1.0, 1 to 2.0), listOf(3 to 4.0), listOf(6 to 6.0, 7 to 7.0)),
            runs,
        )
        assertTrue(ChartGeometry.lineRuns(listOf(null, null)).isEmpty())
        assertEquals(listOf(listOf(0 to -1.5)), ChartGeometry.lineRuns(listOf(-1.5)))
    }

    @Test
    fun theExtentSkipsTheGaps() {
        assertEquals(-3.0 to 9.0, ChartGeometry.extent(listOf(listOf(1.0, null, -3.0), listOf(null, 9.0))))
        assertEquals(0.0 to 0.0, ChartGeometry.extent(listOf(listOf(null))))
    }
}
