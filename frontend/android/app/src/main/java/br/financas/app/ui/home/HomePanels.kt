package br.financas.app.ui.home

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.SheetValue
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.core.formatCurrency
import br.financas.app.core.monthLabel
import br.financas.app.data.BudgetMonthDto
import br.financas.app.rules.AttentionRules
import br.financas.app.rules.FlowPoint
import br.financas.app.rules.HomeFlow
import br.financas.app.rules.HomeRules
import br.financas.app.ui.charts.AreaLineChart
import br.financas.app.ui.charts.BarColumn
import br.financas.app.ui.charts.StackedBarChart
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AlertTone
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.AppSheet
import br.financas.app.ui.components.Badge
import br.financas.app.ui.components.BadgeTone
import br.financas.app.ui.components.ButtonVariant
import br.financas.app.ui.components.EmptyState
import br.financas.app.ui.components.Field
import br.financas.app.ui.components.FitText
import br.financas.app.ui.components.Panel
import br.financas.app.ui.components.SelectField
import br.financas.app.ui.components.SelectOption
import br.financas.app.ui.theme.LocalPalette
import java.math.BigDecimal

// ---- Fluxo de caixa ----

@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun CashFlowPanel(view: HomeView, onOpenWeb: (String) -> Unit) {
    val palette = LocalPalette.current
    val points = remember(view.flow) { view.flow.map(HomeFlow::flowPoint) }
    val summary = remember(points) { HomeFlow.flowSummary(points) }
    val description = listOfNotNull(
        stringResource(if (summary.hasInvestment) R.string.home_flow_description_investment else R.string.home_flow_description),
        stringResource(R.string.home_flow_card_note),
        if (summary.hasOthers) stringResource(R.string.home_flow_others_note) else null,
    ).joinToString(" ")
    Panel {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            PanelTitleLink(stringResource(R.string.home_flow_title)) { onOpenWeb("/lancamentos/extrato") }
            Text(description, color = palette.muted, fontSize = 13.sp)
            if (!summary.hasData) {
                EmptyState(
                    title = stringResource(R.string.home_flow_empty_title),
                    message = stringResource(R.string.home_flow_empty_message),
                )
                return@Column
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                InlineStat(stringResource(R.string.home_avg_income), formatCurrency(summary.avgIncome), Modifier.weight(1f))
                InlineStat(stringResource(R.string.home_avg_expense), formatCurrency(summary.avgExpense), Modifier.weight(1f))
            }
            val rate = summary.savingsRate
            val rateColor = if (rate != null && rate.signum() < 0) palette.loss else palette["emerald-700"]
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                if (summary.hasInvestment) {
                    InlineStat(
                        label = stringResource(
                            if (summary.avgInvestment.signum() < 0) R.string.home_avg_redeemed else R.string.home_avg_invested,
                        ),
                        value = formatCurrency(summary.avgInvestment.abs()),
                        modifier = Modifier.weight(1f),
                    )
                }
                InlineStat(
                    label = stringResource(R.string.home_savings_rate),
                    value = HomeFlow.savingsRateText(rate),
                    modifier = Modifier.weight(1f),
                    valueColor = rateColor,
                )
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                LegendDot(palette["flow-income"], stringResource(R.string.home_legend_income))
                LegendDot(palette["flow-expense"], stringResource(R.string.home_legend_expense))
                if (summary.hasInvestment) LegendDot(palette["flow-investment"], stringResource(R.string.home_legend_investment))
                if (summary.hasOthers) LegendDot(palette["flow-others"], stringResource(R.string.home_legend_others))
                LegendDot(palette["zinc-900"], stringResource(R.string.home_legend_net), line = true)
            }
            var selected by remember(points.size) { mutableStateOf<Int?>(points.lastIndex.takeIf { it >= 0 }) }
            val columns = points.map { point ->
                val parts = mutableListOf(
                    point.income.toDouble() to palette["flow-income"],
                    point.expense.toDouble() to palette["flow-expense"],
                )
                if (summary.hasInvestment) parts += point.investment.toDouble() to palette["flow-investment"]
                if (summary.hasOthers) parts += point.others.toDouble() to palette["flow-others"]
                BarColumn(point.label, parts, point.net.toDouble())
            }
            StackedBarChart(
                columns = columns,
                lineColor = palette["zinc-900"],
                tickLabel = { HomeFlow.compactAxis(BigDecimal.valueOf(it)) },
                selected = selected,
                onSelect = { selected = it },
            )
            selected?.let { index -> points.getOrNull(index)?.let { FlowDetail(it, summary.hasInvestment, summary.hasOthers) } }
        }
    }
}

/** O que o tooltip do grafico da web mostra, para o mes tocado. */
@Composable
private fun FlowDetail(point: FlowPoint, hasInvestment: Boolean, hasOthers: Boolean) {
    val palette = LocalPalette.current
    val lines = mutableListOf(
        stringResource(R.string.home_tip_income) to formatCurrency(point.income),
        stringResource(R.string.home_tip_expense) to formatCurrency(point.expense.abs()),
    )
    if (hasInvestment) {
        val redeemed = point.investment.signum() > 0
        lines += stringResource(if (redeemed) R.string.home_tip_redeemed else R.string.home_tip_invested) to formatCurrency(point.investment.abs())
    }
    if (hasOthers) {
        val back = point.others.signum() > 0
        lines += stringResource(if (back) R.string.home_tip_others_received else R.string.home_tip_others_paid) to formatCurrency(point.others.abs())
    }
    lines += stringResource(R.string.home_tip_net) to formatCurrency(point.net)
    Surface(shape = RoundedCornerShape(12.dp), color = palette.background) {
        Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(monthLabel(point.key), color = palette.text, fontWeight = FontWeight.Bold, fontSize = 13.sp)
            lines.forEach { (label, value) ->
                Row {
                    Text(label, color = palette["zinc-600"], fontSize = 13.sp, modifier = Modifier.weight(1f))
                    Text(value, color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                }
            }
        }
    }
}

@Composable
private fun LegendDot(color: Color, label: String, line: Boolean = false) {
    val palette = LocalPalette.current
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            Modifier
                .size(width = if (line) 14.dp else 10.dp, height = if (line) 3.dp else 10.dp)
                .background(color, if (line) RoundedCornerShape(2.dp) else CircleShape),
        )
        Spacer(Modifier.width(6.dp))
        Text(label, color = palette["zinc-600"], fontSize = 12.sp)
    }
}

@Composable
private fun InlineStat(label: String, value: String, modifier: Modifier = Modifier, valueColor: Color? = null) {
    val palette = LocalPalette.current
    Surface(
        shape = RoundedCornerShape(12.dp),
        color = palette.background,
        border = BorderStroke(1.dp, palette.border),
        modifier = modifier,
    ) {
        Column(Modifier.padding(horizontal = 12.dp, vertical = 10.dp)) {
            Text(label, color = palette.muted, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
            FitText(
                text = value,
                maxSize = 16.sp,
                minSize = 12.sp,
                color = valueColor ?: palette.text,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(top = 4.dp),
            )
        }
    }
}

// ---- Orcamento do mes ----

@Composable
internal fun BudgetStrip(budget: BudgetMonthDto, onOpenWeb: (String) -> Unit) {
    val palette = LocalPalette.current
    val lines = budget.items.map { it.rule }
    val totals = budget.totals
    val spent = totals.spent ?: BigDecimal.ZERO
    val available = totals.available ?: BigDecimal.ZERO
    val remaining = totals.remaining ?: BigDecimal.ZERO
    val status = HomeRules.budgetStatus(spent, available)
    val flagged = HomeRules.budgetFlagged(lines)
    val shown = flagged.take(HomeRules.BUDGET_FLAGGED_SHOWN)
    Panel {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                PanelTitleLink(stringResource(R.string.home_budget_title), Modifier.weight(1f)) { onOpenWeb("/planejamento/orcamento") }
                BudgetBadge(status)
            }
            Text(stringResource(R.string.home_budget_description), color = palette.muted, fontSize = 13.sp)
            Row(verticalAlignment = Alignment.Bottom) {
                Text(formatCurrency(spent), color = palette.text, fontWeight = FontWeight.Bold, fontSize = 20.sp)
                Text(
                    stringResource(R.string.home_budget_of, formatCurrency(available)),
                    color = palette["zinc-600"],
                    fontSize = 14.sp,
                    modifier = Modifier.padding(start = 4.dp, bottom = 2.dp),
                )
            }
            ProgressBar(HomeRules.barFraction(HomeRules.budgetPercent(spent, available)), statusColor(status), height = 10)
            Text(
                HomeRules.budgetRemainingText(remaining),
                color = if (remaining.signum() < 0) palette.loss else palette["zinc-700"],
                fontWeight = FontWeight.SemiBold,
                fontSize = 14.sp,
            )
            if (shown.isEmpty()) {
                Text(HomeRules.budgetAllOk(lines.size), color = palette["zinc-600"], fontSize = 14.sp)
            } else {
                shown.forEach { line ->
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                HomeRules.budgetCategoryName(line),
                                color = palette["zinc-700"],
                                fontWeight = FontWeight.Medium,
                                fontSize = 14.sp,
                                maxLines = 1,
                                modifier = Modifier.weight(1f),
                            )
                            Text(
                                formatCurrency(line.spent),
                                color = if (line.status == HomeRules.OVER) palette.loss else palette.text,
                                fontWeight = FontWeight.SemiBold,
                                fontSize = 14.sp,
                            )
                            Text(" / ${formatCurrency(line.available)}", color = palette["zinc-600"], fontSize = 14.sp)
                        }
                        ProgressBar(HomeRules.barFraction(line.percent), statusColor(line.status), height = 6)
                    }
                }
                if (flagged.size > shown.size) {
                    Text(
                        HomeRules.budgetMoreFlagged(flagged.size - shown.size),
                        color = palette.muted,
                        fontSize = 14.sp,
                        modifier = Modifier.clickable { onOpenWeb("/planejamento/orcamento") }.padding(vertical = 8.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun BudgetBadge(status: String) {
    val (label, tone) = when (status) {
        HomeRules.OVER -> R.string.home_budget_over to BadgeTone.DANGER
        HomeRules.WARNING -> R.string.home_budget_warning to BadgeTone.WARNING
        HomeRules.NEEDS_INCOME -> R.string.home_budget_needs_income to BadgeTone.WARNING
        else -> R.string.home_budget_ok to BadgeTone.NEUTRAL
    }
    Badge(stringResource(label), tone)
}

@Composable
private fun statusColor(status: String): Color {
    val palette = LocalPalette.current
    return when (status) {
        HomeRules.OVER -> palette["rose-500"]
        HomeRules.WARNING -> palette["amber-500"]
        else -> palette["emerald-500"]
    }
}

@Composable
private fun ProgressBar(fraction: Float, color: Color, height: Int) {
    val palette = LocalPalette.current
    Box(
        Modifier
            .fillMaxWidth()
            .height(height.dp)
            .background(palette["zinc-100"], RoundedCornerShape(50)),
    ) {
        if (fraction > 0f) {
            Box(
                Modifier
                    .fillMaxWidth(fraction)
                    .height(height.dp)
                    .background(color, RoundedCornerShape(50)),
            )
        }
    }
}

// ---- Evolucao do saldo ----

@Composable
internal fun BalancePanel(view: HomeView, hidden: Boolean) {
    val palette = LocalPalette.current
    val points = remember(view.flow) { view.flow.map(HomeFlow::flowPoint) }
    val hasData = remember(points) { HomeFlow.flowSummary(points).hasData }
    val balance = view.consolidatedBalance
    Panel {
        Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.Top) {
                Column(Modifier.weight(1f)) {
                    Text(stringResource(R.string.home_balance_chart_title), color = palette.text, fontWeight = FontWeight.Bold, fontSize = 16.sp)
                    Text(
                        stringResource(R.string.home_balance_chart_description),
                        color = palette.muted,
                        fontSize = 13.sp,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                }
                Badge(
                    if (hidden) HomeLogic.MASKED_CURRENCY else formatCurrency(balance),
                    // No modo privado sem a cor do negativo: ela revelaria o sinal.
                    if (!hidden && balance.signum() < 0) BadgeTone.DANGER else BadgeTone.NEUTRAL,
                )
            }
            if (!hasData) {
                EmptyState(
                    title = stringResource(R.string.home_balance_empty_title),
                    message = stringResource(R.string.home_balance_empty_message),
                )
                return@Column
            }
            var selected by remember(points.size) { mutableStateOf<Int?>(points.lastIndex.takeIf { it >= 0 }) }
            AreaLineChart(
                values = points.map { it.balance.toDouble() },
                labels = points.map { it.label },
                color = palette["series-0"],
                // Modo privado: o eixo sem rotulos (usePrivateAxisFormatter).
                tickLabel = { if (hidden) "" else HomeFlow.compactAxis(BigDecimal.valueOf(it)) },
                selected = selected,
                onSelect = { selected = it },
            )
            selected?.let { index ->
                points.getOrNull(index)?.let { point ->
                    Row {
                        Text(monthLabel(point.key), color = palette["zinc-600"], fontSize = 13.sp, modifier = Modifier.weight(1f))
                        Text(
                            stringResource(R.string.home_tip_balance) + ": " +
                                if (hidden) HomeLogic.MASKED_CURRENCY else formatCurrency(point.balance),
                            color = palette.text,
                            fontWeight = FontWeight.SemiBold,
                            fontSize = 13.sp,
                        )
                    }
                }
            }
        }
    }
}

// ---- Pagar fatura ----

/**
 * O PayInvoiceSheet da web com `allowPerCard`: a conta de onde sai o dinheiro ("Conta de cada
 * cartão" deixa o servidor escolher por cartao), o aviso quando o saldo nao cobre, e "Pagar R$ X".
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun PayInvoiceSheet(request: PayRequest, viewModel: HomeViewModel, accounts: List<HomeAccount>) {
    val palette = LocalPalette.current
    val sheetState = rememberModalBottomSheetState(
        skipPartiallyExpanded = true,
        // Com o pagamento no ar o sheet nao fecha (a web desliga o fechar enquanto salva).
        confirmValueChange = { value -> value != SheetValue.Hidden || !viewModel.paying },
    )
    var accountId by remember(request) { mutableStateOf("") }
    val hidden = viewModel.hidden
    val active = HomeLogic.activeAccounts(accounts)
    val selected = active.firstOrNull { it.id == accountId }
    AppSheet(
        title = request.title,
        sheetState = sheetState,
        onDismiss = viewModel::closePay,
        footer = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AppButton(
                    text = stringResource(R.string.home_pay_cancel),
                    onClick = viewModel::closePay,
                    variant = ButtonVariant.SECONDARY,
                    enabled = !viewModel.paying,
                    modifier = Modifier.weight(1f),
                )
                AppButton(
                    text = stringResource(R.string.home_pay_confirm, formatCurrency(request.total)),
                    onClick = { viewModel.confirmPay(accountId) },
                    loading = viewModel.paying,
                    modifier = Modifier.weight(1f),
                )
            }
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text(request.description, color = palette["zinc-600"], fontSize = 14.sp)
            AlertMessage(message = viewModel.payError, tone = AlertTone.DANGER, dismissLabel = stringResource(R.string.home_dismiss_error))
            Field(label = stringResource(R.string.home_pay_account)) {
                SelectField(
                    value = accountId,
                    options = listOf(SelectOption("", stringResource(R.string.home_pay_per_card))) +
                        active.map { SelectOption(it.id, HomeLogic.accountOptionLabel(it, hidden)) },
                    onSelect = { accountId = it },
                )
            }
            if (accountId.isEmpty()) {
                Text(stringResource(R.string.home_pay_per_card_hint), color = palette.muted, fontSize = 13.sp)
            }
            if (selected != null && HomeLogic.shortfall(selected, request.total)) {
                AlertMessage(
                    message = HomeLogic.shortfallText(selected, hidden),
                    tone = AlertTone.WARNING,
                    dismissLabel = stringResource(R.string.home_dismiss_error),
                )
            }
        }
    }
}

// ---- O sino ----

/**
 * "Precisa de atenção" do sino (AttentionBell da web): todos os avisos de agora, os dispensados
 * no Inicio inclusive. Tocar num leva para a tela dele.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun AttentionBellSheet(viewModel: HomeViewModel, onOpenWeb: (String) -> Unit) {
    val palette = LocalPalette.current
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val items = viewModel.attention
    AppSheet(
        title = stringResource(R.string.bell_title),
        sheetState = sheetState,
        onDismiss = viewModel::closeBell,
        footer = {},
    ) {
        if (items.isEmpty()) {
            Text(stringResource(R.string.bell_empty), color = palette["zinc-600"], fontSize = 14.sp)
        } else {
            items.forEach { item ->
                val text = AttentionRules.attentionText(item.rule) { value ->
                    if (viewModel.hidden) HomeLogic.MASKED_CURRENCY else formatCurrency(value)
                }
                val link = AttentionRules.attentionLink(item.kind)
                Row(
                    verticalAlignment = Alignment.Top,
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable {
                            viewModel.closeBell()
                            if (link != null) onOpenWeb(link.route)
                        }
                        .padding(vertical = 10.dp),
                ) {
                    ToneIcon(item.kind, item.tone)
                    Column(Modifier.weight(1f).padding(start = 12.dp)) {
                        Text(text.title, color = palette.text, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                        if (text.detail.isNotEmpty()) {
                            Text(text.detail, color = palette["zinc-600"], fontSize = 14.sp, modifier = Modifier.padding(top = 2.dp))
                        }
                        if (link != null) {
                            Text(
                                link.label,
                                color = palette["emerald-700"],
                                fontWeight = FontWeight.Bold,
                                fontSize = 14.sp,
                                modifier = Modifier.padding(top = 2.dp),
                            )
                        }
                    }
                }
            }
        }
    }
}
