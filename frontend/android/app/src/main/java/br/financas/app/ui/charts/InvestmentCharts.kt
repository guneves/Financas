package br.financas.app.ui.charts

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import br.financas.app.ui.theme.LocalPalette

/**
 * Os graficos que Investimentos pede alem dos do Inicio (14-investimentos-rentabilidade.md, "Charts
 * used across Investimentos"): a rosca da Alocacao/Posicao, barras dos dois lados do zero (aportes
 * e resgates, proventos por ano) e linhas que quebram no buraco (rentabilidade contra os indices).
 * A geometria e de ChartGeometry (testada na JVM); aqui so o desenho, com as cores do LocalPalette.
 */

/**
 * A rosca: uma fatia por valor positivo, a partir do topo, na cor que vem junto (a cor segue a
 * entidade). [selected] destaca uma fatia (as outras ficam mais claras); o centro e de quem chama.
 */
@Composable
fun DonutChart(
    slices: List<Pair<Double, Color>>,
    modifier: Modifier = Modifier,
    diameter: Dp = 180.dp,
    thickness: Dp = 26.dp,
    selected: Int? = null,
) {
    val empty = LocalPalette.current["zinc-100"]
    Canvas(modifier = modifier.size(diameter)) {
        val stroke = thickness.toPx()
        val inset = stroke / 2
        val arcSize = Size(size.width - stroke, size.height - stroke)
        // O separador de 2 dp do recharts (stroke branco), como angulo no raio do meio.
        val radius = (size.minDimension - stroke) / 2
        val gap = if (radius > 0f) Math.toDegrees((2.dp.toPx() / radius).toDouble()).toFloat() else 0f
        ChartGeometry.donutSlices(slices.map { it.first }, gap).forEach { slice ->
            val color = slices[slice.index].second
            drawArc(
                color = if (selected == null || selected == slice.index) color else color.copy(alpha = 0.35f),
                startAngle = slice.startAngle,
                sweepAngle = slice.sweepAngle,
                useCenter = false,
                topLeft = Offset(inset, inset),
                size = arcSize,
                style = Stroke(width = stroke),
            )
        }
        // Sem nada positivo: o anel vazio, na cor da grade.
        if (slices.none { it.first > 0.0 && it.first.isFinite() }) {
            drawCircle(empty, radius = radius, style = Stroke(width = stroke))
        }
    }
}

/** Uma serie de [SignedBarChart]: um valor por coluna (null = sem barra) e a cor. */
data class BarSeries(val values: List<Double?>, val color: Color)

/**
 * Barras lado a lado que saem do zero: positivas sobem, negativas descem (o AportesChart desenha o
 * resgate negado; a rentabilidade mensal tem meses negativos). Uma ou mais series por coluna.
 * Tocar numa coluna escolhe-a ([onSelect]); a escolhida ganha um fundo.
 */
@Composable
fun SignedBarChart(
    labels: List<String>,
    series: List<BarSeries>,
    tickLabel: (Double) -> String,
    selected: Int?,
    onSelect: (Int) -> Unit,
    modifier: Modifier = Modifier,
    height: Dp = 240.dp,
    maxBarWidth: Dp = 24.dp,
) {
    val palette = LocalPalette.current
    val measurer = rememberTextMeasurer()
    val grid = palette["zinc-100"]
    val axis = palette["zinc-300"]
    val tick = palette["zinc-500"]
    val highlight = palette.text.copy(alpha = 0.05f)
    Canvas(
        modifier = modifier
            .fillMaxWidth()
            .height(height)
            .pointerInput(labels.size) {
                detectTapGestures { offset ->
                    val left = AXIS_WIDTH.toPx()
                    slotAt(offset.x, left, size.width - left, labels.size)?.let(onSelect)
                }
            },
    ) {
        if (labels.isEmpty() || series.isEmpty()) return@Canvas
        val (low, high) = ChartGeometry.extent(series.map { it.values })
        val ticks = ChartScale.ticks(low, high)
        val plot = Plot(
            left = AXIS_WIDTH.toPx(),
            top = 8.dp.toPx(),
            width = size.width - AXIS_WIDTH.toPx(),
            height = size.height - 8.dp.toPx() - LABEL_HEIGHT.toPx(),
            min = ticks.first(),
            max = ticks.last(),
        )
        val slot = plot.width / labels.size
        if (selected != null && selected in labels.indices) {
            drawRect(highlight, Offset(plot.left + slot * selected, plot.top), Size(slot, plot.height))
        }
        axisAndGrid(measurer, plot, ticks, tickLabel, grid, axis, tick)
        val gap = 2.dp.toPx()
        val barWidth = minOf(maxBarWidth.toPx(), (slot * 0.7f - gap * (series.size - 1)) / series.size).coerceAtLeast(1f)
        labels.indices.forEach { index ->
            val lefts = ChartGeometry.groupedBarLefts(plot.left + slot * index, slot, series.size, barWidth, gap)
            series.forEachIndexed { s, bars ->
                val value = bars.values.getOrNull(index) ?: return@forEachIndexed
                if (value == 0.0 || !value.isFinite()) return@forEachIndexed
                val span = ChartGeometry.signedBar(value, plot.min, plot.max, plot.top, plot.height)
                drawRect(bars.color, Offset(lefts[s], span.top), Size(barWidth, maxOf(span.height, 1f)))
            }
        }
        xLabels(measurer, plot, labels, tick)
    }
}

/** Uma serie de [GapLineChart]: um valor por coluna, null onde nao ha dado (a linha quebra). */
data class LineSeries(val values: List<Double?>, val color: Color, val dashed: Boolean = false, val width: Dp = 2.dp)

/**
 * Varias linhas sobre as mesmas colunas, cada uma quebrando onde falta dado (o indice que comecou
 * depois, o mes sem cotacao) em vez de ligar por cima do buraco. Um ponto isolado vira um ponto.
 */
@Composable
fun GapLineChart(
    labels: List<String>,
    series: List<LineSeries>,
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
            .pointerInput(labels.size) {
                detectTapGestures { offset ->
                    val left = AXIS_WIDTH.toPx()
                    slotAt(offset.x, left, size.width - left, labels.size)?.let(onSelect)
                }
            },
    ) {
        if (labels.isEmpty() || series.isEmpty()) return@Canvas
        val (low, high) = ChartGeometry.extent(series.map { it.values })
        val ticks = ChartScale.ticks(low, high)
        val plot = Plot(
            left = AXIS_WIDTH.toPx(),
            top = 8.dp.toPx(),
            width = size.width - AXIS_WIDTH.toPx(),
            height = size.height - 8.dp.toPx() - LABEL_HEIGHT.toPx(),
            min = ticks.first(),
            max = ticks.last(),
        )
        axisAndGrid(measurer, plot, ticks, tickLabel, grid, axis, tick)
        val slot = plot.width / labels.size
        val x = { index: Int -> plot.left + slot * index + slot / 2 }
        if (selected != null && selected in labels.indices) {
            drawLine(axis, Offset(x(selected), plot.top), Offset(x(selected), plot.top + plot.height), strokeWidth = 1.dp.toPx())
        }
        series.forEach { line ->
            val effect = if (line.dashed) {
                androidx.compose.ui.graphics.PathEffect.dashPathEffect(floatArrayOf(6.dp.toPx(), 4.dp.toPx()))
            } else {
                null
            }
            ChartGeometry.lineRuns(line.values).forEach { run ->
                val points = run.map { (index, value) -> Offset(x(index), plot.y(value)) }
                if (points.size == 1) {
                    drawCircle(line.color, radius = 2.5f.dp.toPx(), center = points[0])
                } else {
                    val path = Path().apply {
                        moveTo(points[0].x, points[0].y)
                        points.drop(1).forEach { lineTo(it.x, it.y) }
                    }
                    drawPath(path, line.color, style = Stroke(width = line.width.toPx(), pathEffect = effect))
                }
            }
            if (selected != null) {
                line.values.getOrNull(selected)?.takeIf { it.isFinite() }?.let { value ->
                    val point = Offset(x(selected), plot.y(value))
                    drawCircle(surface, radius = 5.dp.toPx(), center = point)
                    drawCircle(line.color, radius = 3.5f.dp.toPx(), center = point)
                }
            }
        }
        xLabels(measurer, plot, labels, tick)
    }
}

/** Uma camada de [StackedAreaChart]: um valor por coluna e a cor. */
data class AreaSeries(val values: List<Double>, val color: Color)

/**
 * Areas empilhadas (a Calculadora: investido embaixo, juros por cima) e, se houver, uma linha
 * tracejada por cima (o valor em reais de hoje). Tocar escolhe a coluna ([onSelect]).
 */
@Composable
fun StackedAreaChart(
    labels: List<String>,
    areas: List<AreaSeries>,
    dashedLine: LineSeries?,
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
    Canvas(
        modifier = modifier
            .fillMaxWidth()
            .height(height)
            .pointerInput(labels.size) {
                detectTapGestures { offset ->
                    val left = AXIS_WIDTH.toPx()
                    slotAt(offset.x, left, size.width - left, labels.size)?.let(onSelect)
                }
            },
    ) {
        if (labels.isEmpty() || areas.isEmpty()) return@Canvas
        // O topo de cada camada e a soma dela com as de baixo.
        val tops = areas.indices.map { layer -> labels.indices.map { index -> (0..layer).sumOf { areas[it].values.getOrElse(index) { 0.0 } } } }
        val (low, high) = ChartGeometry.extent(tops + listOfNotNull(dashedLine?.values?.map { it ?: 0.0 }))
        val ticks = ChartScale.ticks(low, high)
        val plot = Plot(
            left = AXIS_WIDTH.toPx(),
            top = 8.dp.toPx(),
            width = size.width - AXIS_WIDTH.toPx(),
            height = size.height - 8.dp.toPx() - LABEL_HEIGHT.toPx(),
            min = ticks.first(),
            max = ticks.last(),
        )
        axisAndGrid(measurer, plot, ticks, tickLabel, grid, axis, tick)
        val slot = plot.width / labels.size
        val x = { index: Int -> plot.left + slot * index + slot / 2 }
        areas.indices.forEach { layer ->
            val top = tops[layer].mapIndexed { index, value -> Offset(x(index), plot.y(value)) }
            val bottom = if (layer == 0) labels.indices.map { Offset(x(it), plot.y(0.0)) } else tops[layer - 1].mapIndexed { index, value -> Offset(x(index), plot.y(value)) }
            if (top.size > 1) {
                val area = Path().apply {
                    moveTo(top[0].x, top[0].y)
                    top.drop(1).forEach { lineTo(it.x, it.y) }
                    bottom.reversed().forEach { lineTo(it.x, it.y) }
                    close()
                }
                drawPath(area, areas[layer].color.copy(alpha = 0.28f))
                val line = Path().apply {
                    moveTo(top[0].x, top[0].y)
                    top.drop(1).forEach { lineTo(it.x, it.y) }
                }
                drawPath(line, areas[layer].color, style = Stroke(width = 2.dp.toPx()))
            }
        }
        dashedLine?.let { line ->
            val effect = androidx.compose.ui.graphics.PathEffect.dashPathEffect(floatArrayOf(5.dp.toPx(), 4.dp.toPx()))
            ChartGeometry.lineRuns(line.values).forEach { run ->
                if (run.size < 2) return@forEach
                val path = Path().apply {
                    moveTo(x(run[0].first), plot.y(run[0].second))
                    run.drop(1).forEach { (index, value) -> lineTo(x(index), plot.y(value)) }
                }
                drawPath(path, line.color, style = Stroke(width = line.width.toPx(), pathEffect = effect))
            }
        }
        if (selected != null && selected in labels.indices) {
            drawLine(axis, Offset(x(selected), plot.top), Offset(x(selected), plot.top + plot.height), strokeWidth = 1.dp.toPx())
        }
        xLabels(measurer, plot, labels, tick)
    }
}
