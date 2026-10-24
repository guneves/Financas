package br.financas.app.ui.charts

/**
 * A geometria dos graficos de Investimentos (rosca, barras dos dois lados do zero, linhas com
 * buraco), separada do Canvas para o teste JVM (ChartGeometryTest.kt). So posicao de desenho:
 * os valores chegam como Double ja calculados por quem chama — nunca dinheiro.
 */
object ChartGeometry {
    /** Uma fatia da rosca: angulos em graus no sentido horario, 0 = tres horas (o do Canvas). */
    data class Slice(val index: Int, val startAngle: Float, val sweepAngle: Float)

    /**
     * As fatias de [values] a partir do topo (-90 graus), na ordem recebida (a cor segue a
     * entidade, como o SERIES da web). Zero, negativo e NaN nao tem fatia; o [index] aponta o
     * valor original. [gapDegrees] separa as fatias (o stroke branco do recharts) e nunca come
     * mais que metade de uma fatia; uma fatia so e o circulo inteiro, sem separacao.
     */
    fun donutSlices(values: List<Double>, gapDegrees: Float = 0f): List<Slice> {
        val kept = values.withIndex().filter { (_, value) -> value > 0.0 && value.isFinite() }
        val total = kept.sumOf { it.value }
        if (total <= 0.0) return emptyList()
        var angle = -90f
        return kept.map { (index, value) ->
            val sweep = (value / total * 360.0).toFloat()
            val gap = if (kept.size > 1) minOf(gapDegrees, sweep / 2) else 0f
            Slice(index, angle + gap / 2, sweep - gap).also { angle += sweep }
        }
    }

    /** O topo e a base, em px, de uma barra que sai do zero ate [value] numa escala [min]..[max]. */
    data class Span(val top: Float, val bottom: Float) {
        val height: Float get() = bottom - top
    }

    /**
     * A barra de [value] nos dois lados do zero: positivo sobe do zero, negativo desce (o
     * resgate negado do AportesChart, o mes negativo da rentabilidade). [plotTop]/[plotHeight]
     * em px; [min] < [max] e o zero dentro (ChartScale.ticks garante). Zero = altura 0.
     */
    fun signedBar(value: Double, min: Double, max: Double, plotTop: Float, plotHeight: Float): Span {
        fun y(v: Double): Float = plotTop + plotHeight - ((v - min) / (max - min) * plotHeight).toFloat()
        val zero = y(0.0)
        val end = y(value)
        return Span(minOf(zero, end), maxOf(zero, end))
    }

    /**
     * Onde ficam as barras de uma coluna com [series] lado a lado: o x esquerdo de cada uma,
     * centradas no slot de [slotWidth] px que comeca em [slotLeft], cada uma com [barWidth] px e
     * [gap] px entre elas.
     */
    fun groupedBarLefts(slotLeft: Float, slotWidth: Float, series: Int, barWidth: Float, gap: Float): List<Float> {
        if (series <= 0) return emptyList()
        val total = barWidth * series + gap * (series - 1)
        val start = slotLeft + (slotWidth - total) / 2
        return List(series) { start + it * (barWidth + gap) }
    }

    /**
     * Os trechos de uma serie com buracos (o connectNulls=false do recharts): cada trecho e a
     * lista de (indice, valor) seguidos; null ou NaN quebra a linha. Um ponto sozinho e um trecho
     * de um (o Canvas o desenha como ponto).
     */
    fun lineRuns(values: List<Double?>): List<List<Pair<Int, Double>>> {
        val runs = mutableListOf<List<Pair<Int, Double>>>()
        var current = mutableListOf<Pair<Int, Double>>()
        values.forEachIndexed { index, value ->
            if (value == null || !value.isFinite()) {
                if (current.isNotEmpty()) runs.add(current)
                current = mutableListOf()
            } else {
                current.add(index to value)
            }
        }
        if (current.isNotEmpty()) runs.add(current)
        return runs
    }

    /** O menor e o maior valor de varias series com buracos (para ChartScale.ticks); 0..0 sem nenhum. */
    fun extent(series: List<List<Double?>>): Pair<Double, Double> {
        val all = series.flatten().filterNotNull().filter { it.isFinite() }
        return if (all.isEmpty()) 0.0 to 0.0 else all.min() to all.max()
    }
}
