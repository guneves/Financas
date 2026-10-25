package br.financas.app.ui.investimentos

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.core.formatCurrency
import br.financas.app.core.formatPercent
import br.financas.app.rules.CompoundInterest
import br.financas.app.rules.HomeFlow
import br.financas.app.ui.charts.AreaSeries
import br.financas.app.ui.charts.LineSeries
import br.financas.app.ui.charts.StackedAreaChart
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AlertTone
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.AppTextField
import br.financas.app.ui.components.ButtonVariant
import br.financas.app.ui.components.Field
import br.financas.app.ui.components.Panel
import br.financas.app.ui.components.SelectField
import br.financas.app.ui.components.SelectOption
import br.financas.app.ui.planejar.PlanejarScaffold
import br.financas.app.ui.planejar.SummaryPanel
import br.financas.app.ui.planejar.SummaryValue
import br.financas.app.ui.theme.LocalPalette
import kotlinx.coroutines.flow.MutableSharedFlow
import java.math.BigDecimal

private fun money(value: Double?): String = formatCurrency(value?.takeIf { it.isFinite() }?.let { BigDecimal.valueOf(it) })

/** Investimentos › Calculadora nativa (16-…, C). Nada e mascarado: nao e dado do dono. */
@Composable
fun CalculadoraScreen(viewModel: CalculadoraViewModel, onBack: () -> Unit, onTab: (InvestimentosTab) -> Unit) {
    val palette = LocalPalette.current
    val form = viewModel.form
    val result = viewModel.result
    val ok = result as? CompoundInterest.Result
    PlanejarScaffold(
        notices = remember { MutableSharedFlow() },
        onRefresh = {},
        topBar = {
            InvestimentosTopBar(stringResource(R.string.inv_calc_title), InvestimentosTab.CALCULADORA, false, onBack, null, onTab)
        },
    ) {
        item(key = "intro") {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(stringResource(R.string.inv_calc_description), fontSize = 14.sp, color = palette["zinc-600"])
                AppButton(stringResource(R.string.inv_clear), viewModel::clear, variant = ButtonVariant.SECONDARY)
            }
        }
        item(key = "form") {
            Panel {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Field(stringResource(R.string.inv_calc_initial)) {
                        AppTextField(form.initial, { viewModel.change(form.copy(initial = it)) }, placeholder = "0,00", keyboardType = KeyboardType.Decimal)
                    }
                    Field(stringResource(R.string.inv_calc_monthly)) {
                        AppTextField(form.monthly, { viewModel.change(form.copy(monthly = it)) }, placeholder = "0,00", keyboardType = KeyboardType.Decimal)
                    }
                    Field(stringResource(R.string.inv_calc_timing)) {
                        SelectField(
                            form.timing,
                            listOf(SelectOption("end", stringResource(R.string.inv_calc_timing_end)), SelectOption("start", stringResource(R.string.inv_calc_timing_start))),
                            { viewModel.change(form.copy(timing = it)) },
                        )
                    }
                    val rateHint = ok?.let {
                        if (form.rateUnit == "month") {
                            stringResource(R.string.inv_calc_rate_yearly, formatPercent(BigDecimal.valueOf(it.input.annualRatePercent), 2))
                        } else {
                            stringResource(R.string.inv_calc_rate_monthly, formatPercent(BigDecimal.valueOf(it.input.monthlyRatePercent), 4))
                        }
                    }
                    Field(stringResource(R.string.inv_calc_rate), hint = rateHint) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            // Sem o teclado decimal: a taxa pode ser negativa e ele nao tem o sinal.
                            AppTextField(form.rate, { viewModel.change(form.copy(rate = it)) }, Modifier.weight(1f), placeholder = "Ex.: 10")
                            SelectField(
                                form.rateUnit,
                                listOf(SelectOption("year", stringResource(R.string.inv_calc_per_year)), SelectOption("month", stringResource(R.string.inv_calc_per_month))),
                                { viewModel.change(form.copy(rateUnit = it)) },
                                Modifier.width(132.dp),
                            )
                        }
                    }
                    Field(stringResource(R.string.inv_calc_period)) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            AppTextField(form.period, { viewModel.change(form.copy(period = it)) }, Modifier.weight(1f), placeholder = "Ex.: 10", keyboardType = KeyboardType.Decimal)
                            SelectField(
                                form.periodUnit,
                                listOf(SelectOption("year", stringResource(R.string.inv_calc_years)), SelectOption("month", stringResource(R.string.inv_calc_months))),
                                { viewModel.change(form.copy(periodUnit = it)) },
                                Modifier.width(132.dp),
                            )
                        }
                    }
                    Field(stringResource(R.string.inv_calc_inflation), hint = stringResource(R.string.inv_calc_inflation_hint)) {
                        AppTextField(form.inflation, { viewModel.change(form.copy(inflation = it)) }, placeholder = "Ex.: 4,5")
                    }
                }
            }
        }
        if (result is CompoundInterest.FormError) {
            item(key = "error") { AlertMessage(result.message, AlertTone.WARNING, stringResource(R.string.lanc_dismiss)) }
        }
        if (ok != null) {
            val withReal = ok.input.inflationPercent != null
            item(key = "summary") {
                val third = if (withReal) {
                    SummaryValue(
                        stringResource(R.string.inv_calc_real),
                        money(ok.real),
                        stringResource(R.string.inv_calc_real_rate, formatPercent(ok.realAnnualRatePercent?.let { BigDecimal.valueOf(it) }, 2)),
                    )
                } else {
                    SummaryValue(stringResource(R.string.inv_calc_income_at_end), money(ok.monthlyIncomeAtEnd), stringResource(R.string.inv_calc_income_at_end_hint))
                }
                SummaryPanel(
                    lead = SummaryValue(stringResource(R.string.inv_calc_final), money(ok.final), stringResource(R.string.inv_calc_after, CompoundInterest.durationText(ok.input.months))),
                    figures = listOf(
                        SummaryValue(stringResource(R.string.inv_calc_invested), money(ok.invested)),
                        SummaryValue(stringResource(R.string.inv_calc_interest), money(ok.interest), loss = ok.interest < 0),
                        third,
                    ),
                )
            }
            item(key = "chart") { GrowthPanel(ok, withReal, viewModel) }
            item(key = "years") { YearsList(ok, withReal) }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun GrowthPanel(result: CompoundInterest.Result, withReal: Boolean, viewModel: CalculadoraViewModel) {
    val palette = LocalPalette.current
    val points = CompoundInterest.chartPoints(result.schedule)
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            PanelTitle(stringResource(R.string.inv_calc_growth), stringResource(R.string.inv_calc_growth_description))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                LegendDot(palette["flow-investment"], stringResource(R.string.inv_calc_invested))
                LegendDot(palette["series-2"], stringResource(R.string.inv_calc_interest))
                if (withReal) LegendDot(palette["series-3"], stringResource(R.string.inv_calc_real))
            }
            StackedAreaChart(
                labels = points.map { CompoundInterest.periodLabel(it.month) },
                areas = listOf(
                    AreaSeries(points.map { it.invested }, palette["flow-investment"]),
                    AreaSeries(points.map { it.interest }, palette["series-2"]),
                ),
                dashedLine = if (withReal) LineSeries(points.map { it.real }, palette["series-3"], dashed = true) else null,
                tickLabel = { HomeFlow.compactAxis(BigDecimal.valueOf(it)) },
                selected = viewModel.selected,
                onSelect = viewModel::select,
            )
            viewModel.selected?.let { points.getOrNull(it) }?.let { row ->
                Column(Modifier.fillMaxWidth().background(palette["zinc-50"], RoundedCornerShape(12.dp)).padding(12.dp)) {
                    Text(CompoundInterest.periodLabel(row.month), color = palette.text, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                    DetailFigure(stringResource(R.string.inv_calc_invested), money(row.invested))
                    DetailFigure(stringResource(R.string.inv_calc_interest), money(row.interest))
                    if (withReal) DetailFigure(stringResource(R.string.inv_calc_real), money(row.real))
                    Text(stringResource(R.string.inv_calc_balance, money(row.balance)), color = palette.muted, fontSize = 12.sp)
                }
            }
        }
    }
}

@Composable
private fun YearsList(result: CompoundInterest.Result, withReal: Boolean) {
    val palette = LocalPalette.current
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            PanelTitle(stringResource(R.string.inv_calc_years_title), stringResource(R.string.inv_calc_years_description))
            result.years.forEach { row ->
                HorizontalDivider(color = palette.border)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Column(Modifier.weight(1f)) {
                        val label = if (row.months == 12) {
                            stringResource(R.string.inv_calc_year, row.year)
                        } else {
                            stringResource(if (row.months == 1) R.string.inv_calc_year_month else R.string.inv_calc_year_months, row.year, row.months)
                        }
                        Text(label, color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                        Text(stringResource(R.string.inv_calc_year_line, money(row.interestInYear), money(row.invested)), color = palette.muted, fontSize = 12.sp)
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text(money(row.balance), color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                        if (withReal) Text(stringResource(R.string.inv_calc_today, money(row.real)), color = palette.muted, fontSize = 12.sp)
                    }
                }
            }
        }
    }
}
