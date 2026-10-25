package br.financas.app.ui.home

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.core.formatCurrency
import br.financas.app.core.formatDateBR
import br.financas.app.core.monthLabel
import br.financas.app.core.shortMonthLabel
import br.financas.app.data.HomePanelsDto
import br.financas.app.data.InstallmentGroupDto
import br.financas.app.rules.HomeFlow
import br.financas.app.rules.HomePanelsRules
import br.financas.app.rules.HomeRules
import br.financas.app.ui.charts.BarSeries
import br.financas.app.ui.charts.DonutChart
import br.financas.app.ui.charts.GapLineChart
import br.financas.app.ui.charts.LineSeries
import br.financas.app.ui.charts.SignedBarChart
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AlertTone
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.AppIcons
import br.financas.app.ui.components.Badge
import br.financas.app.ui.components.EmptyState
import br.financas.app.ui.components.Panel
import br.financas.app.ui.theme.LocalPalette
import java.math.BigDecimal

// Os quatro paineis de historico do Inicio (pages/Dashboard.jsx), com os numeros de
// GET /api/home/panels (services/home_panels.py). Nenhum valor e somado aqui.

private val axisLabel: (Double) -> String = { HomeFlow.compactAxis(BigDecimal.valueOf(it)) }

@Composable
private fun categoryColor(index: Int, size: Int): Color {
    val palette = LocalPalette.current
    val color = HomePanelsRules.categoryColorIndex(index, size)
    return if (color in 0..7) palette["series-$color"] else palette["zinc-400"]
}

/** O DeltaBadge da web: seta e %, verde quando o gasto caiu, rosa quando subiu. */
@Composable
internal fun DeltaBadge(value: Double?) {
    if (value == null || !value.isFinite()) return
    val palette = LocalPalette.current
    val (fill, ink) = when (HomePanelsRules.deltaTone(value)) {
        HomePanelsRules.DeltaTone.GOOD -> palette["emerald-50"] to palette["emerald-700"]
        HomePanelsRules.DeltaTone.BAD -> palette["rose-50"] to palette["rose-700"]
        HomePanelsRules.DeltaTone.FLAT -> palette["zinc-100"] to palette["zinc-600"]
    }
    Surface(shape = RoundedCornerShape(50), color = fill) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)) {
            Icon(
                if (HomePanelsRules.deltaUp(value)) AppIcons.ArrowUpRight else AppIcons.ArrowDownRight,
                contentDescription = null,
                tint = ink,
                modifier = Modifier.size(14.dp),
            )
            Text(HomePanelsRules.deltaText(value), color = ink, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
        }
    }
}

// ---- Despesas por categoria ----

@Composable
internal fun CategoriesPanel(panels: HomePanelsDto, onOpenLink: (String) -> Unit) {
    val palette = LocalPalette.current
    val items = panels.categories
    Panel {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            PanelTitleLink(stringResource(R.string.home_categories_title)) { onOpenLink("/planejamento/orcamento") }
            Text(stringResource(R.string.home_categories_description), color = palette.muted, fontSize = 13.sp)
            if (items.isEmpty()) {
                EmptyState(
                    title = stringResource(R.string.home_categories_empty_title),
                    message = stringResource(R.string.home_categories_empty_message),
                )
                return@Column
            }
            val colors = items.indices.map { categoryColor(it, items.size) }
            var selected by remember(items) { mutableStateOf<Int?>(null) }
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                DonutChart(items.mapIndexed { index, item -> item.value.toDouble() to colors[index] }, selected = selected)
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    val shown = selected?.let { items.getOrNull(it) }
                    Text(
                        shown?.name ?: stringResource(R.string.home_categories_center),
                        color = palette.muted,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.width(120.dp),
                    )
                    Text(formatCurrency(shown?.value ?: panels.spendingTotal), color = palette.text, fontSize = 15.sp, fontWeight = FontWeight.Bold)
                }
            }
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items.forEachIndexed { index, item ->
                    Column(
                        Modifier
                            .fillMaxWidth()
                            .background(if (selected == index) palette.background else Color.Transparent, RoundedCornerShape(12.dp))
                            .padding(horizontal = 4.dp, vertical = 6.dp),
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(Modifier.size(10.dp).background(colors[index], CircleShape))
                            Text(
                                item.name,
                                color = palette["zinc-700"],
                                fontSize = 14.sp,
                                fontWeight = FontWeight.Medium,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                modifier = Modifier.weight(1f).padding(start = 8.dp),
                            )
                            DeltaBadge(item.delta)
                            Text(
                                formatCurrency(item.value),
                                color = palette.text,
                                fontSize = 14.sp,
                                fontWeight = FontWeight.SemiBold,
                                modifier = Modifier.padding(start = 8.dp),
                            )
                        }
                        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 6.dp)) {
                            Box(Modifier.weight(1f)) {
                                ProgressBar(HomePanelsRules.share(item.value, panels.spendingTotal), colors[index], height = 4)
                            }
                            Text(
                                HomePanelsRules.channelLabel(item.cash, item.credit, item.value),
                                color = palette.muted,
                                fontSize = 12.sp,
                                modifier = Modifier.padding(start = 8.dp),
                            )
                        }
                    }
                }
            }
        }
    }
}

// ---- Proximas faturas ----

@Composable
internal fun InvoicesPanel(
    panels: HomePanelsDto,
    nextInvoicesTotal: BigDecimal,
    payable: Boolean,
    closingDate: String?,
    paying: Boolean,
    onPay: () -> Unit,
    onOpenLink: (String) -> Unit,
) {
    val palette = LocalPalette.current
    val projection = panels.invoiceProjection
    Panel {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                PanelTitleLink(stringResource(R.string.home_invoices_title), Modifier.weight(1f)) { onOpenLink("/lancamentos/cartoes") }
                Text(formatCurrency(nextInvoicesTotal), color = palette.text, fontSize = 18.sp, fontWeight = FontWeight.Bold)
            }
            Text(stringResource(R.string.home_invoices_description), color = palette.muted, fontSize = 13.sp)
            if (projection.any { it.value.signum() > 0 }) {
                var selected by remember(projection) { mutableStateOf<Int?>(projection.indexOfFirst { it.next }.takeIf { it >= 0 }) }
                val color = palette["series-1"]
                SignedBarChart(
                    labels = projection.map { shortMonthLabel(it.month) },
                    series = listOf(BarSeries(projection.map { it.value.toDouble() }, color)),
                    tickLabel = axisLabel,
                    selected = selected,
                    onSelect = { selected = it },
                    maxBarWidth = 28.dp,
                    barColor = { _, index -> if (projection[index].next) color else color.copy(alpha = 0.35f) },
                )
                selected?.let { projection.getOrNull(it) }?.let { month ->
                    Row {
                        Text(HomeRules.sentenceCase(monthLabel(month.month)), color = palette["zinc-600"], fontSize = 13.sp, modifier = Modifier.weight(1f))
                        Text(formatCurrency(month.value), color = palette.text, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                    }
                }
            } else {
                EmptyState(
                    title = stringResource(R.string.home_invoices_empty_title),
                    message = stringResource(R.string.home_invoices_empty_message),
                )
            }
            val note = HomePanelsRules.projectionNote(panels.nextInvoiceMonths, ::monthLabel)
            if (note.isNotEmpty()) Text(note, color = palette["zinc-600"], fontSize = 12.sp)
            if (nextInvoicesTotal.signum() > 0) {
                AlertMessage(
                    message = stringResource(R.string.home_invoices_open_items, panels.nextInvoiceItems.size) + "\n" +
                        stringResource(R.string.home_invoices_open_note),
                    tone = AlertTone.INFO,
                    dismissLabel = "",
                )
                Surface(shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, palette.border), color = palette.surface) {
                    Column {
                        panels.nextInvoiceItems.forEachIndexed { index, item ->
                            if (index > 0) HorizontalDivider(color = palette["zinc-100"])
                            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp)) {
                                Column(Modifier.weight(1f)) {
                                    Text(item.description.orEmpty(), color = palette.text, fontSize = 14.sp, fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                    Text(
                                        (item.cardName ?: stringResource(R.string.home_card_fallback)) + HomePanelsRules.installmentSuffix(item.installmentInfo),
                                        color = palette.muted,
                                        fontSize = 12.sp,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis,
                                    )
                                }
                                Text(formatCurrency(item.amount), color = palette.text, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(start = 8.dp))
                            }
                        }
                    }
                }
                if (!payable && closingDate != null) {
                    Text(stringResource(R.string.home_invoices_closes_note, formatDateBR(closingDate)), color = palette["zinc-600"], fontSize = 12.sp)
                }
                AppButton(stringResource(R.string.home_invoices_pay), onPay, Modifier.fillMaxWidth(), loading = paying, enabled = payable)
            } else {
                EmptyState(
                    title = stringResource(R.string.home_invoices_none_title),
                    message = stringResource(R.string.home_invoices_none_message),
                )
            }
        }
    }
}

// ---- Parcelamentos abertos ----

@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun InstallmentsPanel(panels: HomePanelsDto, onOpenLink: (String) -> Unit) {
    val palette = LocalPalette.current
    Panel {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                PanelTitleLink(stringResource(R.string.home_installments_title), Modifier.weight(1f)) { onOpenLink("/lancamentos/cartoes") }
                Badge(formatCurrency(panels.installmentsTotal))
            }
            Text(stringResource(R.string.home_installments_description), color = palette.muted, fontSize = 13.sp)
            if (panels.installments.isEmpty()) {
                EmptyState(
                    title = stringResource(R.string.home_installments_empty_title),
                    message = stringResource(R.string.home_installments_empty_message),
                )
                return@Column
            }
            panels.installments.forEach { item -> InstallmentCard(item) }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun InstallmentCard(item: InstallmentGroupDto) {
    val palette = LocalPalette.current
    Surface(shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, palette.border), color = palette.surface) {
        Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.Top) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(item.description.orEmpty(), color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Badge(item.cardName ?: stringResource(R.string.home_card_fallback))
                        Badge(stringResource(R.string.home_installments_each, item.remaining, formatCurrency(item.installmentAmount)))
                    }
                }
                Column(horizontalAlignment = Alignment.End, modifier = Modifier.padding(start = 12.dp)) {
                    Text(formatCurrency(item.remainingAmount), color = palette.text, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                    Text(stringResource(R.string.home_installments_remaining), color = palette.muted, fontSize = 11.sp, fontWeight = FontWeight.Medium)
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.weight(1f)) {
                    ProgressBar(HomePanelsRules.paidFraction(item.paid, item.totalInstallments), palette["zinc-800"], height = 6)
                }
                Text(
                    stringResource(R.string.home_installments_paid, item.paid, item.totalInstallments),
                    color = palette["zinc-600"],
                    fontSize = 12.sp,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.padding(start = 12.dp),
                )
            }
        }
    }
}

// ---- Ritmo de gastos ----

@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun PacePanel(panels: HomePanelsDto) {
    val palette = LocalPalette.current
    val pace = panels.pace
    val monthKeys = pace.months.map { it.month }
    val averageLabel = HomePanelsRules.paceAverageLabel(monthKeys)
    Panel {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(R.string.home_pace_title), color = palette.text, fontWeight = FontWeight.Bold, fontSize = 16.sp, modifier = Modifier.weight(1f))
                Column(horizontalAlignment = Alignment.End) {
                    Text(stringResource(R.string.home_pace_to_date), color = palette.muted, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        DeltaBadge(pace.vsAverage)
                        Text(formatCurrency(pace.currentToDate), color = palette.text, fontWeight = FontWeight.Bold, fontSize = 17.sp)
                    }
                }
            }
            Text(stringResource(R.string.home_pace_description), color = palette.muted, fontSize = 13.sp)
            if (panels.spendingTotal.signum() <= 0 && pace.months.isEmpty()) {
                EmptyState(
                    title = stringResource(R.string.home_pace_empty_title),
                    message = stringResource(R.string.home_pace_empty_message),
                )
                return@Column
            }
            if (pace.months.isNotEmpty()) {
                val direction = HomePanelsRules.paceDirection(pace.currentToDate, pace.averageToDate)
                val difference = (pace.currentToDate - pace.averageToDate).abs()
                val lead = when (direction) {
                    0 -> stringResource(R.string.home_pace_on_average)
                    1 -> stringResource(R.string.home_pace_above, formatCurrency(difference))
                    else -> stringResource(R.string.home_pace_below, formatCurrency(difference))
                }
                Text(
                    stringResource(R.string.home_pace_sentence, lead, pace.todayDay, formatCurrency(pace.averageMonth)),
                    color = when (direction) {
                        1 -> palette.loss
                        -1 -> palette["emerald-700"]
                        else -> palette["zinc-700"]
                    },
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Medium,
                )
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    InlineStat(stringResource(R.string.home_pace_average_until, averageLabel, pace.todayDay), formatCurrency(pace.averageToDate), Modifier.width(150.dp))
                    if (pace.months.size > 1) {
                        pace.months.forEach { month ->
                            InlineStat(stringResource(R.string.home_pace_month_until, shortMonthLabel(month.month), pace.todayDay), formatCurrency(month.toDate), Modifier.width(150.dp))
                        }
                    }
                }
            }
            val currentColor = palette["series-0"]
            val averageColor = palette["zinc-400"]
            FlowRow(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                LegendDot(currentColor, stringResource(R.string.home_pace_this_month, shortMonthLabel(panels.month)), line = true)
                if (pace.months.isNotEmpty()) LegendDot(averageColor, averageLabel, line = true)
            }
            val rows = pace.rows
            var selected by remember(rows) { mutableStateOf<Int?>(rows.indexOfFirst { it.day == pace.todayDay }.takeIf { it >= 0 }) }
            GapLineChart(
                labels = rows.map { HomePanelsRules.paceAxisLabel(it.day) },
                series = listOf(
                    LineSeries(rows.map { it.average?.toDouble() }, averageColor),
                    LineSeries(rows.map { it.current?.toDouble() }, currentColor, width = 2.5.dp),
                ),
                tickLabel = axisLabel,
                selected = selected,
                onSelect = { selected = it },
            )
            selected?.let { rows.getOrNull(it) }?.let { row ->
                Surface(shape = RoundedCornerShape(12.dp), color = palette.background) {
                    Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(stringResource(R.string.home_pace_day, row.day), color = palette.text, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                        row.current?.let { value ->
                            Row {
                                Text(stringResource(R.string.home_pace_this_month_short), color = palette["zinc-600"], fontSize = 13.sp, modifier = Modifier.weight(1f))
                                Text(formatCurrency(value), color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                            }
                        }
                        row.average?.let { value ->
                            Row {
                                Text(averageLabel, color = palette["zinc-600"], fontSize = 13.sp, modifier = Modifier.weight(1f))
                                Text(formatCurrency(value), color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                            }
                        }
                    }
                }
            }
        }
    }
}
