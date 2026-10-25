package br.financas.app.ui.investimentos

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.core.formatPercent
import br.financas.app.core.shortMonthLabel
import br.financas.app.data.ReturnsDto
import br.financas.app.rules.PortfolioView
import br.financas.app.rules.ReturnsRules
import br.financas.app.ui.charts.GapLineChart
import br.financas.app.ui.charts.LineSeries
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AlertTone
import br.financas.app.ui.components.Badge
import br.financas.app.ui.components.EmptyState
import br.financas.app.ui.components.ListSkeleton
import br.financas.app.ui.components.Panel
import br.financas.app.ui.lancamentos.moneyOrMasked
import br.financas.app.ui.planejar.PlanejarScaffold
import br.financas.app.ui.planejar.SummaryPanel
import br.financas.app.ui.planejar.SummaryValue
import br.financas.app.ui.theme.LocalPalette
import br.financas.app.ui.theme.Palette
import kotlinx.coroutines.flow.MutableSharedFlow
import java.math.BigDecimal

private fun toneColor(palette: Palette, value: BigDecimal?): Color = when (ReturnsRules.toneOf(value)) {
    ReturnsRules.Tone.GAIN -> palette["emerald-700"]
    ReturnsRules.Tone.LOSS -> palette.loss
    ReturnsRules.Tone.NEUTRAL -> palette["zinc-700"]
    ReturnsRules.Tone.MUTED -> palette["zinc-400"]
}

@Composable
private fun Pct(value: BigDecimal?, fontSize: Int = 14, bold: Boolean = false) {
    Text(
        ReturnsRules.signedPercent(value),
        color = toneColor(LocalPalette.current, value),
        fontSize = fontSize.sp,
        fontWeight = if (bold) FontWeight.Bold else FontWeight.Medium,
    )
}

/** Investimentos › Rentabilidade nativo (14-investimentos-rentabilidade.md). */
@Composable
fun RentabilidadeScreen(viewModel: RentabilidadeViewModel, onBack: () -> Unit, onTab: (InvestimentosTab) -> Unit) {
    val palette = LocalPalette.current
    val dismiss = stringResource(R.string.lanc_dismiss)
    val data = viewModel.returns.value
    val classLabel = viewModel.assetClass.takeIf { it.isNotEmpty() }?.let { PortfolioView.classLabel(it) }
    PlanejarScaffold(
        notices = remember { MutableSharedFlow() },
        onRefresh = viewModel::refreshAll,
        topBar = {
            InvestimentosTopBar(stringResource(R.string.inv_rent_title), InvestimentosTab.RENTABILIDADE, viewModel.hidden, onBack, viewModel::toggleHidden, onTab)
        },
    ) {
        item(key = "intro") {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(stringResource(R.string.inv_rent_description), fontSize = 14.sp, color = palette["zinc-600"])
                ClassSelect(viewModel.assetClass, viewModel::changeClass)
                PeriodChips(ReturnsRules.PERIODS, viewModel.months, viewModel::changeMonths)
            }
        }
        item(key = "alerts") {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (viewModel.returns.offline) AlertMessage(viewModel.returns.offlineText, AlertTone.WARNING, dismiss)
                AlertMessage(viewModel.returns.error, AlertTone.WARNING, dismiss)
            }
        }
        val empty = data != null && data.twrPercent == null && data.assets.isEmpty()
        when {
            data == null && !viewModel.returns.loaded -> item(key = "loading") { Panel { ListSkeleton(rows = 5, modifier = Modifier.padding(16.dp)) } }
            data == null -> Unit
            empty -> item(key = "empty") {
                EmptyState(
                    if (classLabel != null) stringResource(R.string.inv_rent_empty_class_title, classLabel) else stringResource(R.string.inv_rent_empty_title),
                    stringResource(if (classLabel != null) R.string.inv_rent_empty_class_message else R.string.inv_rent_empty_message),
                )
            }
            else -> {
                item(key = "summary") { ReturnsSummary(data, classLabel, viewModel.hidden) }
                item(key = "chart") { ReturnsChartPanel(data, classLabel, viewModel) }
                item(key = "years") { YearsPanel(data) }
                item(key = "assets") { AssetsPanel(data, viewModel.hidden) }
                item(key = "basis") {
                    Panel {
                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            PanelTitle(stringResource(R.string.inv_rent_basis_title), data.basisLabel)
                            data.notes.forEach { note -> Text("• $note", color = palette["zinc-600"], fontSize = 13.sp) }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun ReturnsSummary(data: ReturnsDto, classLabel: String?, hidden: Boolean) {
    val compared = data.comparison?.let { it.start to it.end } ?: data.period?.let { it.start to it.end }
    val hint = ReturnsRules.periodHint(compared?.first, compared?.second, data.comparison?.startsAfterWindow == true)
    val last = data.series.lastOrNull()?.value
    SummaryPanel(
        lead = SummaryValue(
            if (classLabel != null) stringResource(R.string.inv_rent_lead_class, classLabel) else stringResource(R.string.inv_rent_lead),
            ReturnsRules.signedPercent(data.twrPercent),
            hint,
            loss = ReturnsRules.toneOf(data.twrPercent) == ReturnsRules.Tone.LOSS,
            muted = data.twrPercent == null,
        ),
        figures = listOf(
            SummaryValue(stringResource(R.string.inv_rent_ytd), ReturnsRules.signedPercent(data.ytdPercent), loss = ReturnsRules.toneOf(data.ytdPercent) == ReturnsRules.Tone.LOSS),
            SummaryValue(
                stringResource(R.string.inv_rent_of_cdi),
                data.percentOfCdi?.let { formatPercent(it, 0) } ?: "—",
                data.cdiPercent?.let { stringResource(R.string.inv_rent_cdi_period, formatPercent(it)) } ?: stringResource(R.string.inv_rent_cdi_unavailable),
            ),
            SummaryValue(
                if (classLabel != null) stringResource(R.string.inv_rent_today_class, classLabel) else stringResource(R.string.inv_rent_today),
                if (last != null) moneyOrMasked(last, hidden) else "—",
                stringResource(R.string.inv_rent_gross),
            ),
        ),
    )
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ReturnsChartPanel(data: ReturnsDto, classLabel: String?, viewModel: RentabilidadeViewModel) {
    val palette = LocalPalette.current
    val haptic = LocalHapticFeedback.current
    val comparisons = ReturnsRules.comparisonItems(
        data.twrPercent,
        data.cdiAvailable,
        data.cdiPercent,
        data.benchmarks.map {
            ReturnsRules.Comparison(it.code, it.label ?: it.code, it.available, it.complete, it.monthsCovered, it.monthsTotal, it.periodPercent, it.differencePp, it.note)
        },
    )
    val shown = ReturnsRules.shown(comparisons, viewModel.visible)
    val seriesLabel = classLabel ?: stringResource(R.string.inv_summary_portfolio)
    fun colorOf(code: String) = palette[ReturnsRules.BENCHMARK_COLORS[code] ?: "zinc-400"]
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            PanelTitle(
                stringResource(R.string.inv_rent_chart_title),
                stringResource(R.string.inv_rent_chart_description, shortMonthLabel(data.comparison?.baseMonth)),
            )
            // Os cartoes: o total de cada indice no periodo e o liga/desliga da linha dele.
            comparisons.chunked(2).forEach { row ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    row.forEach { item ->
                        val on = item.available && item.code in viewModel.visible
                        Surface(
                            onClick = {
                                haptic.performHapticFeedback(HapticFeedbackType.TextHandleMove)
                                viewModel.toggleBenchmark(item.code)
                            },
                            enabled = item.available,
                            shape = RoundedCornerShape(12.dp),
                            color = if (on) palette["zinc-50"] else palette.surface,
                            border = BorderStroke(1.dp, if (on) palette["zinc-300"] else palette.border),
                            modifier = Modifier.weight(1f).heightIn(min = 48.dp).alpha(if (item.available) 1f else 0.6f),
                        ) {
                            Column(Modifier.padding(horizontal = 12.dp, vertical = 8.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                    Box(Modifier.width(14.dp).height(3.dp).background(if (on) colorOf(item.code) else palette["zinc-300"], RoundedCornerShape(2.dp)))
                                    Text(item.label, color = palette["zinc-700"], fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                                }
                                Pct(if (item.available) item.periodPercent else null, fontSize = 16, bold = true)
                                Text(ReturnsRules.comparisonHint(item), color = palette.muted, fontSize = 11.sp, maxLines = 1)
                            }
                        }
                    }
                    if (row.size == 1) Box(Modifier.weight(1f))
                }
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                LegendDot(palette[ReturnsRules.PORTFOLIO_COLOR], stringResource(R.string.inv_rent_twr_legend, seriesLabel))
                shown.forEach { LegendDot(colorOf(it.code), it.label) }
            }
            if (data.series.isEmpty()) {
                ListSkeleton(rows = 1)
            } else {
                val labels = data.series.map { shortMonthLabel(it.monthKey) }
                val lines = shown.map { item ->
                    val values = data.series.map { point ->
                        if (item.code == "CDI") point.cdiAccumulatedPercent?.toDouble() else point.benchmarks[item.code]?.accumulatedPercent?.toDouble()
                    }
                    LineSeries(values, colorOf(item.code), dashed = item.code == "IPCA", width = if (item.code == "CDI") 2.dp else 1.75.dp)
                } + LineSeries(data.series.map { it.accumulatedPercent?.toDouble() }, palette[ReturnsRules.PORTFOLIO_COLOR], width = 2.5.dp)
                GapLineChart(
                    labels = labels,
                    series = lines,
                    tickLabel = ReturnsRules::percentAxis,
                    selected = viewModel.selected,
                    onSelect = viewModel::select,
                )
                viewModel.selected?.let { data.series.getOrNull(it) }?.let { point ->
                    Column(
                        Modifier.fillMaxWidth().background(palette["zinc-50"], RoundedCornerShape(12.dp)).padding(12.dp),
                        verticalArrangement = Arrangement.spacedBy(2.dp),
                    ) {
                        Text(shortMonthLabel(point.monthKey), color = palette.text, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                        DetailFigure(seriesLabel, ReturnsRules.signedPercent(point.accumulatedPercent))
                        shown.forEach { item ->
                            val value = if (item.code == "CDI") point.cdiAccumulatedPercent else point.benchmarks[item.code]?.accumulatedPercent
                            DetailFigure(item.label, ReturnsRules.signedPercent(value))
                        }
                    }
                }
            }
            comparisons.filter { it.code != "CDI" && !it.note.isNullOrEmpty() }.forEach { item ->
                Text("${item.label}: ${item.note}", color = palette.muted, fontSize = 12.sp)
            }
        }
    }
}

@Composable
private fun YearsPanel(data: ReturnsDto) {
    val palette = LocalPalette.current
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            PanelTitle(stringResource(R.string.inv_rent_years_title), stringResource(R.string.inv_rent_years_description))
            data.years.reversed().forEach { year ->
                HorizontalDivider(color = palette.border)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(year.year.toString(), color = palette["zinc-800"], fontWeight = FontWeight.SemiBold, fontSize = 14.sp, modifier = Modifier.weight(1f))
                    Pct(year.totalPercent, bold = true)
                }
                year.months.chunked(4).forEachIndexed { rowIndex, row ->
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        row.forEachIndexed { index, value ->
                            Column(Modifier.weight(1f)) {
                                Text(ReturnsRules.MONTH_NAMES.getOrElse(rowIndex * 4 + index) { "" }, color = palette.muted, fontSize = 11.sp)
                                Pct(value, fontSize = 12)
                            }
                        }
                        repeat(4 - row.size) { Box(Modifier.weight(1f)) }
                    }
                }
            }
        }
    }
}

@Composable
private fun AssetsPanel(data: ReturnsDto, hidden: Boolean) {
    val palette = LocalPalette.current
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) { PanelTitle(stringResource(R.string.inv_by_asset_title), stringResource(R.string.inv_rent_assets_description)) }
                Badge(stringResource(R.string.inv_assets_count, data.assets.size))
            }
            if (data.assets.isEmpty()) {
                EmptyState(stringResource(R.string.inv_rent_assets_empty))
            }
            data.assets.forEach { asset ->
                HorizontalDivider(color = palette.border)
                Row(Modifier.padding(vertical = 4.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Column(Modifier.weight(1f)) {
                        Text(asset.ticker.orEmpty(), color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                        val line = stringResource(R.string.inv_rent_since, PortfolioView.classLabel(asset.assetClass), shortMonthLabel(asset.since) + if (asset.capped) "*" else "") +
                            if (asset.open) "" else " · " + stringResource(R.string.inv_rent_closed)
                        Text(line, color = palette.muted, fontSize = 12.sp)
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Pct(asset.twrPercent, bold = true)
                        Text(if (asset.open) moneyOrMasked(asset.currentValue, hidden) else "—", color = palette.muted, fontSize = 12.sp)
                    }
                }
            }
            if (data.assets.any { it.capped }) {
                Text(stringResource(R.string.inv_rent_capped, shortMonthLabel(data.period?.start)), color = palette.muted, fontSize = 12.sp)
            }
        }
    }
}
