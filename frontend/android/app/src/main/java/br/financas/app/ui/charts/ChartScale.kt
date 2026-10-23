package br.financas.app.ui.charts

import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.log10
import kotlin.math.pow

/**
 * As marcas do eixo de valores dos graficos nativos (o que o recharts escolhe sozinho na web):
 * de [min] a [max], com zero sempre dentro, num passo "redondo" (1, 2 ou 5 x 10^n). So posicao de
 * desenho — nunca dinheiro. Puro: ChartScaleTest.kt.
 */
object ChartScale {
    fun ticks(min: Double, max: Double, count: Int = 4): List<Double> {
        val low = minOf(min, 0.0)
        val high = maxOf(max, 0.0)
        if (high - low <= 0.0) return listOf(0.0, 1.0)
        val raw = (high - low) / count
        val magnitude = 10.0.pow(floor(log10(raw)))
        val residual = raw / magnitude
        val step = magnitude * when {
            residual > 5 -> 10.0
            residual > 2 -> 5.0
            residual > 1 -> 2.0
            else -> 1.0
        }
        val start = floor(low / step) * step
        val end = ceil(high / step) * step
        val ticks = mutableListOf<Double>()
        var value = start
        var guard = 0
        while (value <= end + step / 2 && guard < 50) {
            // Sem -0 e sem 0,30000000000000004 no rotulo.
            val rounded = Math.round(value / step) * step
            ticks.add(if (rounded == 0.0) 0.0 else rounded)
            value += step
            guard += 1
        }
        return ticks
    }
}
