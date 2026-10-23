package br.financas.app.ui.charts

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.TextMeasurer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.ui.theme.LocalPalette

/**
 * O kit de graficos nativo (architecture.md: um Canvas do Compose, sem biblioteca). Dois por
 * enquanto, os do Inicio: barras acima e abaixo do zero com uma linha por cima (Fluxo de caixa)
 * e a area de uma serie (Evolucao do saldo). Cores do LocalPalette (os tokens da web: grade
 * zinc-100, eixo zinc-300, rotulo zinc-500, tinta zinc-900); os valores chegam ja como Double
 * de desenho — o dinheiro fica com quem chama.
 */

/** Uma coluna de [StackedBarChart]: as partes (acima ou abaixo do zero) e o ponto da linha. */
data class BarColumn(
    val label: String,
    val parts: List<Pair<Double, Color>>,
    val line: Double?,
)

private val AXIS_WIDTH = 48.dp
private val LABEL_HEIGHT = 20.dp

private class Plot(val left: Float, val top: Float, val width: Float, val height: Float, val min: Double, val max: Double) {
    fun y(value: Double): Float = top + height - ((value - min) / (max - min) * height).toFloat()
}

private fun DrawScope.axisAndGrid(
    measurer: TextMeasurer,
    plot: Plot,
    ticks: List<Double>,
    tickLabel: (Double) -> String,
    grid: Color,
    axis: Color,
    tick: Color,
) {
    val style = TextStyle(color = tick, fontSize = 11.sp)
    ticks.forEach { value ->
        val y = plot.y(value)
        drawLine(if (value == 0.0) axis else grid, Offset(plot.left, y), Offset(plot.left + plot.width, y), strokeWidth = 1.dp.toPx())
        val text = tickLabel(value)
        if (text.isNotEmpty()) {
            val layout = measurer.measure(text, style)
            drawText(
                layout,
                topLeft = Offset(
                    (plot.left - layout.size.width - 6.dp.toPx()).coerceAtLeast(0f),
                    y - layout.size.height / 2f,
                ),
            )
        }
    }
}

private fun DrawScope.xLabels(measurer: TextMeasurer, plot: Plot, labels: List<String>, color: Color) {
    if (labels.isEmpty()) return
    val slot = plot.width / labels.size
    val style = TextStyle(color = color, fontSize = 11.sp)
    // Como o "preserveStartEnd" do recharts: o ultimo sempre, e os outros quando cabem.
    val widest = labels.maxOf { measurer.measure(it, style).size.width }
    val every = maxOf(1, kotlin.math.ceil((widest + 4.dp.toPx()) / slot).toInt())
    labels.forEachIndexed { index, label ->
        if ((labels.size - 1 - index) % every != 0) return@forEachIndexed
        val layout = measurer.measure(label, style)
        val x = (plot.left + slot * index + slot / 2 - layout.size.width / 2f)
            .coerceAtMost(size.width - layout.size.width)
            .coerceAtLeast(0f)
        drawText(layout, topLeft = Offset(x, plot.top + plot.height + 4.dp.toPx()))
    }
}

private fun slotAt(x: Float, left: Float, width: Float, count: Int): Int? {
    if (count == 0 || x < left || x > left + width) return null
    return ((x - left) / (width / count)).toInt().coerceIn(0, count - 1)
}

/**
 * Barras empilhadas pelo sinal (o stackOffset="sign" do recharts: o que e positivo sobe a partir
 * do zero, o negativo desce) e uma linha com pontos por cima. Tocar numa coluna escolhe o mes
 * ([onSelect]); a escolhida ganha um fundo.
 */
@Composable
fun StackedBarChart(
    columns: List<BarColumn>,
    lineColor: Color,
    tickLabel: (Double) -> String,
    selected: Int?,
    onSelect: (Int) -> Unit,
    modifier: Modifier = Modifier,
    height: Dp = 260.dp,
    maxBarWidth: Dp = 24.dp,
) {
    val palette = LocalPalette.current
    val measurer = rememberTextMeasurer()
    val grid = palette["zinc-100"]
    val axis = palette["zinc-300"]
    val tick = palette["zinc-500"]
    val surface = palette.surface
    val highlight = palette.text.copy(alpha = 0.05f)
    Canvas(
        modifier = modifier
            .fillMaxWidth()
            .height(height)
            .pointerInput(columns.size) {
                detectTapGestures { offset ->
                    val left = AXIS_WIDTH.toPx()
                    slotAt(offset.x, left, size.width - left, columns.size)?.let(onSelect)
                }
            },
    ) {
        if (columns.isEmpty()) return@Canvas
        var high = 0.0
        var low = 0.0
        columns.forEach { column ->
            val up = column.parts.sumOf { if (it.first > 0) it.first else 0.0 }
            val down = column.parts.sumOf { if (it.first < 0) it.first else 0.0 }
            high = maxOf(high, up, column.line ?: 0.0)
            low = minOf(low, down, column.line ?: 0.0)
        }
        val ticks = ChartScale.ticks(low, high)
        val plot = Plot(
            left = AXIS_WIDTH.toPx(),
            top = 8.dp.toPx(),
            width = size.width - AXIS_WIDTH.toPx(),
            height = size.height - 8.dp.toPx() - LABEL_HEIGHT.toPx(),
            min = ticks.first(),
            max = ticks.last(),
        )
        val slot = plot.width / columns.size
        if (selected != null && selected in columns.indices) {
            drawRect(highlight, Offset(plot.left + slot * selected, plot.top), Size(slot, plot.height))
        }
        axisAndGrid(measurer, plot, ticks, tickLabel, grid, axis, tick)
        val barWidth = minOf(maxBarWidth.toPx(), slot * 0.6f)
        val radius = CornerRadius(3.dp.toPx(), 3.dp.toPx())
        columns.forEachIndexed { index, column ->
            val x = plot.left + slot * index + (slot - barWidth) / 2
            var up = 0.0
            var down = 0.0
            column.parts.forEach { (value, color) ->
                if (value == 0.0) return@forEach
                val from = if (value > 0) up else down
                val to = from + value
                if (value > 0) up = to else down = to
                val top = plot.y(maxOf(from, to))
                val bottom = plot.y(minOf(from, to))
                drawRoundRect(color, Offset(x, top), Size(barWidth, maxOf(bottom - top, 1f)), radius)
            }
        }
        val points = columns.mapIndexedNotNull { index, column ->
            column.line?.let { Offset(plot.left + slot * index + slot / 2, plot.y(it)) }
        }
        if (points.size > 1) {
            val path = Path().apply {
                moveTo(points[0].x, points[0].y)
                points.drop(1).forEach { lineTo(it.x, it.y) }
            }
            drawPath(path, lineColor, style = Stroke(width = 2.dp.toPx()))
        }
        points.forEach { point ->
            drawCircle(surface, radius = 4.5f.dp.toPx(), center = point)
            drawCircle(lineColor, radius = 3.dp.toPx(), center = point)
        }
        xLabels(measurer, plot, columns.map { it.label }, tick)
    }
}

/**
 * A area de uma serie (o saldo no fim de cada mes): linha, preenchimento que some para baixo e
 * a linha do zero. [tickLabel] devolve "" para esconder o eixo (modo privado).
 */
@Composable
fun AreaLineChart(
    values: List<Double>,
    labels: List<String>,
    color: Color,
    tickLabel: (Double) -> String,
    selected: Int?,
    onSelect: (Int) -> Unit,
    modifier: Modifier = Modifier,
    height: Dp = 240.dp,
) {
    val palette = LocalPalette.current
    val measurer = rememberTextMeasurer()
    val grid = palette["zinc-100"]
    val axis = palette["zinc-300"]
    val tick = palette["zinc-500"]
    val surface = palette.surface
    Canvas(
        modifier = modifier
            .fillMaxWidth()
            .height(height)
            .pointerInput(values.size) {
                detectTapGestures { offset ->
                    val left = AXIS_WIDTH.toPx()
                    slotAt(offset.x, left, size.width - left, values.size)?.let(onSelect)
                }
            },
    ) {
        if (values.isEmpty()) return@Canvas
        val ticks = ChartScale.ticks(values.min(), values.max())
        val plot = Plot(
            left = AXIS_WIDTH.toPx(),
            top = 8.dp.toPx(),
            width = size.width - AXIS_WIDTH.toPx(),
            height = size.height - 8.dp.toPx() - LABEL_HEIGHT.toPx(),
            min = ticks.first(),
            max = ticks.last(),
        )
        axisAndGrid(measurer, plot, ticks, tickLabel, grid, axis, tick)
        val slot = plot.width / values.size
        val points = values.mapIndexed { index, value -> Offset(plot.left + slot * index + slot / 2, plot.y(value)) }
        if (points.size > 1) {
            val line = Path().apply {
                moveTo(points[0].x, points[0].y)
                points.drop(1).forEach { lineTo(it.x, it.y) }
            }
            val area = Path().apply {
                addPath(line)
                lineTo(points.last().x, plot.top + plot.height)
                lineTo(points.first().x, plot.top + plot.height)
                close()
            }
            drawPath(
                area,
                Brush.verticalGradient(
                    listOf(color.copy(alpha = 0.2f), color.copy(alpha = 0f)),
                    startY = plot.top,
                    endY = plot.top + plot.height,
                ),
            )
            drawPath(line, color, style = Stroke(width = 2.dp.toPx()))
        }
        if (selected != null && selected in points.indices) {
            val point = points[selected]
            drawLine(axis, Offset(point.x, plot.top), Offset(point.x, plot.top + plot.height), strokeWidth = 1.dp.toPx())
            drawCircle(surface, radius = 6.dp.toPx(), center = point)
            drawCircle(color, radius = 4.dp.toPx(), center = point)
        } else if (points.size == 1) {
            drawCircle(color, radius = 4.dp.toPx(), center = points[0])
        }
        xLabels(measurer, plot, labels, tick)
    }
}
