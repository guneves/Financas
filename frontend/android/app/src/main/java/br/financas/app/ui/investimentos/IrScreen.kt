package br.financas.app.ui.investimentos

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.core.formatCurrency
import br.financas.app.core.formatPercent
import br.financas.app.core.monthLabel
import br.financas.app.data.ExemptionDto
import br.financas.app.data.TaxMonthDto
import br.financas.app.data.TaxReportDto
import br.financas.app.rules.AllocationRules
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AlertTone
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.Badge
import br.financas.app.ui.components.BadgeTone
import br.financas.app.ui.components.ButtonVariant
import br.financas.app.ui.components.EmptyState
import br.financas.app.ui.components.ListSkeleton
import br.financas.app.ui.components.Panel
import br.financas.app.ui.components.SelectField
import br.financas.app.ui.components.SelectOption
import br.financas.app.ui.planejar.PlanejarScaffold
import br.financas.app.ui.theme.LocalPalette
import kotlinx.coroutines.flow.MutableSharedFlow
import java.math.BigDecimal

/** O relatorio completo de IR: a pagina React, mesmo num APK que tem a nativa. */
const val IR_WEB_ROUTE = "/investimentos/ir?web=1"

private fun TaxMonthDto.view() = AllocationRules.TaxMonth(month, stocks.sales, etfs.sales, reits.sales, darf, darfCarried)

/**
 * Investimentos › IR nativo (16-…, B): o medidor da isencao e os meses de DARF. Sem mascara, como
 * na web (o modo privado so esconde Bens e direitos, que ficam no relatorio completo).
 */
@Composable
fun IrScreen(viewModel: IrViewModel, onBack: () -> Unit, onTab: (InvestimentosTab) -> Unit, onOpenWeb: (String) -> Unit) {
    val palette = LocalPalette.current
    val dismiss = stringResource(R.string.lanc_dismiss)
    PlanejarScaffold(
        notices = remember { MutableSharedFlow() },
        onRefresh = viewModel::refreshAll,
        topBar = {
            InvestimentosTopBar(stringResource(R.string.inv_ir_title), InvestimentosTab.IR, false, onBack, null, onTab)
        },
    ) {
        item(key = "intro") {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(stringResource(R.string.inv_ir_description), fontSize = 14.sp, color = palette["zinc-600"])
                Text(stringResource(R.string.inv_ir_full_report), fontSize = 13.sp, color = palette.muted)
                AppButton(stringResource(R.string.inv_ir_open_full), { onOpenWeb(IR_WEB_ROUTE) }, Modifier.fillMaxWidth(), variant = ButtonVariant.SECONDARY)
            }
        }
        item(key = "meter") { ExemptionPanel(viewModel.month, viewModel.exemption.value, viewModel.exemption.error, dismiss) }
        item(key = "year") {
            val report = viewModel.report.value
            SelectField(
                viewModel.year.toString(),
                AllocationRules.yearOptions(viewModel.year, report?.availableYears.orEmpty(), viewModel.currentYear)
                    .map { SelectOption(it.toString(), stringResource(R.string.inv_ir_year, it)) },
                { viewModel.changeYear(it.toInt()) },
            )
        }
        item(key = "alerts") {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (viewModel.report.offline) AlertMessage(viewModel.report.offlineText, AlertTone.WARNING, dismiss)
                AlertMessage(viewModel.report.error, AlertTone.DANGER, dismiss)
            }
        }
        val report = viewModel.report.value
        when {
            report == null && !viewModel.report.loaded -> item(key = "loading") { Panel { ListSkeleton(rows = 6, modifier = Modifier.padding(16.dp)) } }
            report == null -> Unit
            else -> item(key = "months") { DarfPanel(report, viewModel.year) }
        }
    }
}

@Composable
private fun ExemptionPanel(month: String, data: ExemptionDto?, error: String, dismiss: String) {
    val palette = LocalPalette.current
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) { PanelTitle(stringResource(R.string.inv_ir_meter_title, monthLabel(month)), stringResource(R.string.inv_ir_meter_description)) }
                if (data != null) {
                    if (data.exempt) Badge(stringResource(R.string.inv_ir_exempt), BadgeTone.SUCCESS) else Badge(stringResource(R.string.inv_ir_over), BadgeTone.DANGER)
                }
            }
            AlertMessage(error, AlertTone.DANGER, dismiss)
            if (data == null) {
                ListSkeleton(rows = 1)
                return@Column
            }
            Text(stringResource(R.string.inv_ir_sold_of, formatCurrency(data.stockSales), formatCurrency(data.limit)), color = palette["zinc-700"], fontSize = 14.sp)
            if (data.exempt) {
                Text(stringResource(R.string.inv_ir_room, formatCurrency(data.remaining)), color = palette["zinc-700"], fontSize = 14.sp)
            } else {
                Text(stringResource(R.string.inv_ir_stock_tax, formatCurrency(data.stockTax)), color = palette.loss, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
            }
            val percent = data.percent ?: BigDecimal.ZERO
            val fill = when {
                !data.exempt -> palette["rose-500"]
                percent >= BigDecimal(80) -> palette["amber-500"]
                else -> palette.accent
            }
            Box(Modifier.fillMaxWidth().height(8.dp).background(palette["zinc-100"], RoundedCornerShape(50))) {
                val fraction = (percent.toFloat() / 100f).coerceIn(0f, 1f)
                if (fraction > 0f) Box(Modifier.fillMaxWidth(fraction).fillMaxHeight().background(fill, RoundedCornerShape(50)))
            }
            val notes = buildList {
                add(stringResource(R.string.inv_ir_percent_of_limit, formatPercent(percent, 1)))
                if (data.stockResult.nonZero()) add(stringResource(R.string.inv_ir_result, formatCurrency(data.stockResult)))
                if (data.exempt && data.stockTax.nonZero()) add(stringResource(R.string.inv_ir_etf_tax, formatCurrency(data.stockTax)))
                if (data.stockLossBalance.nonZero()) add(stringResource(R.string.inv_ir_loss, formatCurrency(data.stockLossBalance)))
                if (data.reitSales.nonZero()) add(stringResource(R.string.inv_ir_reits, formatCurrency(data.reitSales), formatCurrency(data.reitTax)))
                if (data.darf.nonZero()) add(stringResource(R.string.inv_ir_darf, formatCurrency(data.darf)))
            }
            notes.forEach { Text(it, color = palette.muted, fontSize = 12.sp) }
        }
    }
}

private fun BigDecimal?.nonZero(): Boolean = this != null && signum() != 0

@Composable
private fun DarfPanel(report: TaxReportDto, year: Int) {
    val palette = LocalPalette.current
    val months = report.rendaVariavel.months
    val active = AllocationRules.activeMonths(months) { it.view() }
    val hasEtfs = AllocationRules.hasEtfs(months) { it.view() }
    val totals = report.rendaVariavel.totals
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) { PanelTitle(stringResource(R.string.inv_ir_variable), stringResource(R.string.inv_ir_variable_description)) }
                Badge(stringResource(R.string.inv_ir_darf_year, formatCurrency(totals.taxDue)), if (totals.taxDue.nonZero()) BadgeTone.WARNING else BadgeTone.NEUTRAL)
            }
            if (active.isEmpty()) {
                EmptyState(stringResource(R.string.inv_ir_no_sales_title), stringResource(R.string.inv_ir_no_sales_message))
            }
            active.forEach { item ->
                HorizontalDivider(color = palette.border)
                Column(Modifier.padding(vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(AllocationRules.monthName(item.month), color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                        if (item.stocks.exempt && item.stocks.sales.nonZero()) Badge(stringResource(R.string.inv_ir_exempt_tag))
                        Box(Modifier.weight(1f))
                        val darf = when {
                            item.darf.nonZero() -> formatCurrency(item.darf)
                            item.darfCarried.nonZero() -> stringResource(R.string.inv_ir_carried, formatCurrency(item.darfCarried))
                            else -> "—"
                        }
                        Text(darf, color = palette.text, fontWeight = if (item.darf.nonZero()) FontWeight.Bold else FontWeight.Normal, fontSize = 14.sp)
                    }
                    DetailFigure(stringResource(R.string.inv_ir_stock_sales), formatCurrency(item.stocks.sales))
                    DetailFigure(stringResource(R.string.inv_ir_stock_result), formatCurrency(item.stocks.result))
                    if (hasEtfs) DetailFigure(stringResource(R.string.inv_ir_etfs), formatCurrency(item.etfs.result))
                    DetailFigure(stringResource(R.string.inv_ir_reit_result), formatCurrency(item.reits.result))
                    DetailFigure(
                        stringResource(R.string.inv_ir_loss_used),
                        formatCurrency((item.stocks.lossUsed ?: BigDecimal.ZERO) + (item.reits.lossUsed ?: BigDecimal.ZERO)),
                    )
                }
            }
            HorizontalDivider(color = palette.border)
            Text(
                stringResource(
                    R.string.inv_ir_loss_balance,
                    year,
                    if (hasEtfs) stringResource(R.string.inv_ir_loss_etfs) else "",
                    formatCurrency(totals.stockLossBalance),
                    formatCurrency(totals.reitLossBalance),
                ),
                color = palette.muted,
                fontSize = 12.sp,
            )
        }
    }
}
