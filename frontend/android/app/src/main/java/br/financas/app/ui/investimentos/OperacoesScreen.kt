package br.financas.app.ui.investimentos

import android.app.Application
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.core.formatCurrency
import br.financas.app.core.formatDateBR
import br.financas.app.core.formatPercent
import br.financas.app.core.formatSignedCurrency
import br.financas.app.core.monthLabel
import br.financas.app.core.shortMonthLabel
import br.financas.app.data.CorporateActionDto
import br.financas.app.data.OperationDto
import br.financas.app.rules.FixedIncome
import br.financas.app.rules.HomeFlow
import br.financas.app.rules.Operations
import br.financas.app.rules.PortfolioView
import br.financas.app.ui.charts.BarColumn
import br.financas.app.ui.charts.StackedBarChart
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AlertTone
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.AppSheet
import br.financas.app.ui.components.AppTextField
import br.financas.app.ui.components.Badge
import br.financas.app.ui.components.ButtonVariant
import br.financas.app.ui.components.ConfirmDialog
import br.financas.app.ui.components.DateField
import br.financas.app.ui.components.EmptyState
import br.financas.app.ui.components.Field
import br.financas.app.ui.components.ListSkeleton
import br.financas.app.ui.components.MenuAction
import br.financas.app.ui.components.OverflowMenu
import br.financas.app.ui.components.Panel
import br.financas.app.ui.components.SegmentedChoice
import br.financas.app.ui.components.SelectField
import br.financas.app.ui.components.SelectOption
import br.financas.app.ui.home.HomeLogic
import br.financas.app.ui.lancamentos.moneyOrMasked
import br.financas.app.ui.planejar.PlanejarScaffold
import br.financas.app.ui.planejar.SummaryPanel
import br.financas.app.ui.planejar.SummaryValue
import br.financas.app.ui.theme.LocalPalette
import java.math.BigDecimal

/** Um valor com sinal, mascarado no modo privado. */
internal fun signedOrMasked(value: BigDecimal?, hidden: Boolean): String =
    if (hidden) HomeLogic.MASKED_CURRENCY else formatSignedCurrency(value)

/** Investimentos › Operacoes nativo (13-investimentos-operacoes.md). */
@Composable
fun OperacoesScreen(viewModel: OperacoesViewModel, onBack: () -> Unit, onTab: (InvestimentosTab) -> Unit) {
    val palette = LocalPalette.current
    val app = LocalContext.current.applicationContext as Application
    val dismiss = stringResource(R.string.lanc_dismiss)
    val hidden = viewModel.hidden
    val movements = viewModel.operations.value
    PlanejarScaffold(
        notices = viewModel.notices,
        onRefresh = viewModel::refreshAll,
        topBar = {
            InvestimentosTopBar(stringResource(R.string.inv_operacoes_title), InvestimentosTab.OPERACOES, hidden, onBack, viewModel::toggleHidden, onTab)
        },
    ) {
        item(key = "intro") {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(stringResource(R.string.inv_operacoes_description), fontSize = 14.sp, color = palette["zinc-600"])
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    AppButton(stringResource(R.string.inv_register_operation), viewModel.launchSheet::openBuy, Modifier.weight(1f))
                    AppButton(stringResource(R.string.inv_export), viewModel.export::show, variant = ButtonVariant.SECONDARY, enabled = !movements.isNullOrEmpty())
                }
            }
        }
        item(key = "alerts") {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (viewModel.operations.offline) AlertMessage(viewModel.operations.offlineText, AlertTone.WARNING, dismiss)
                AlertMessage(viewModel.operations.error, AlertTone.WARNING, dismiss)
                AlertMessage(viewModel.dataError, AlertTone.WARNING, dismiss, onDismiss = viewModel::dismissError)
                if (viewModel.queued > 0) AlertMessage(stringResource(R.string.inv_operations_queued, viewModel.queued), AlertTone.INFO, dismiss)
            }
        }
        viewModel.portfolio.value?.realizedResult?.takeIf { it.operationCount > 0 }?.let { realized ->
            item(key = "summary") {
                val after = realized.netProfitAfterTax ?: BigDecimal.ZERO
                val profit = realized.realizedProfit ?: BigDecimal.ZERO
                SummaryPanel(
                    lead = SummaryValue(
                        stringResource(R.string.inv_realized_after_tax),
                        signedOrMasked(after, hidden),
                        stringResource(R.string.inv_realized_count, realized.operationCount),
                        loss = !hidden && after.signum() < 0,
                    ),
                    figures = listOf(
                        SummaryValue(stringResource(R.string.inv_realized_profit), signedOrMasked(profit, hidden), stringResource(R.string.inv_realized_profit_hint), loss = !hidden && profit.signum() < 0),
                        SummaryValue(stringResource(R.string.inv_realized_tax), moneyOrMasked(realized.taxAmount, hidden), stringResource(R.string.inv_realized_tax_hint)),
                        SummaryValue(stringResource(R.string.inv_realized_cost), moneyOrMasked(realized.costBasis, hidden), stringResource(R.string.inv_realized_cost_hint)),
                    ),
                )
            }
        }
        item(key = "aportes") { AportesPanel(viewModel) }
        item(key = "list-title") {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) { PanelTitle(stringResource(R.string.inv_operacoes_title), stringResource(R.string.inv_operations_list_description)) }
                Badge(stringResource(R.string.inv_records, movements?.size ?: 0))
            }
        }
        when {
            movements == null && !viewModel.operations.loaded -> item(key = "loading") { Panel { ListSkeleton(rows = 6, modifier = Modifier.padding(16.dp)) } }
            movements == null -> Unit
            movements.isEmpty() -> item(key = "empty") { EmptyState(stringResource(R.string.inv_operations_empty_title), stringResource(R.string.inv_operations_empty_message)) }
            else -> movements.forEach { movement -> item(key = "mov-${movement.id}") { MovementCard(movement, viewModel) } }
        }
        item(key = "events") { EventsPanel(viewModel) }
    }
    LaunchSheetView(viewModel.launchSheet, hidden, app)
    InvestExportSheet(viewModel.export, stringResource(R.string.inv_export_movements_title), stringResource(R.string.inv_export_movements_description))
    viewModel.edit?.let { EditSheetView(it, viewModel) }
    viewModel.corporate?.let { CorporateSheet(it, viewModel) }
    ConfirmDialog(viewModel.confirm, stringResource(R.string.lanc_cancel), viewModel::dismissConfirm)
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun AportesPanel(viewModel: OperacoesViewModel) {
    val palette = LocalPalette.current
    val hidden = viewModel.hidden
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) { PanelTitle(stringResource(R.string.inv_aportes_title), stringResource(R.string.inv_aportes_description)) }
                AppButton(stringResource(if (viewModel.aportesOpen) R.string.inv_hide else R.string.inv_show), viewModel::toggleAportes, variant = ButtonVariant.SUBTLE)
            }
            if (!viewModel.aportesOpen) return@Column
            PeriodChips(OperacoesViewModel.APORTES_PERIODS, viewModel.aportesMonths.toString()) { viewModel.changeAportesMonths(it.toInt()) }
            ClassSelect(viewModel.aportesClass, viewModel::changeAportesClass)
            if (viewModel.contributions.error.isNotEmpty()) AlertMessage(viewModel.contributions.error, AlertTone.DANGER, stringResource(R.string.lanc_dismiss))
            val data = viewModel.contributions.value
            when {
                data == null && !viewModel.contributions.loaded -> ListSkeleton(rows = 1)
                data == null -> Unit
                data.totals.count == 0 -> EmptyState(stringResource(R.string.inv_aportes_empty_title), stringResource(R.string.inv_aportes_empty_message))
                else -> {
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        MiniFigure(stringResource(R.string.inv_aportes), moneyOrMasked(data.totals.aportes, hidden), Modifier.weight(1f))
                        MiniFigure(stringResource(R.string.inv_resgates), moneyOrMasked(data.totals.resgates, hidden), Modifier.weight(1f))
                        MiniFigure(stringResource(R.string.inv_liquido), signedOrMasked(data.totals.liquido, hidden), Modifier.weight(1f))
                    }
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                        LegendDot(palette["flow-investment"], stringResource(R.string.inv_aportes))
                        LegendDot(palette["series-1"], stringResource(R.string.inv_resgates))
                    }
                    // Aportes sobem, resgates descem (desenhados negados), empilhados pelo sinal.
                    StackedBarChart(
                        columns = data.months.map { month ->
                            BarColumn(
                                shortMonthLabel(month.month),
                                listOf(
                                    (month.aportes ?: BigDecimal.ZERO).toDouble() to palette["flow-investment"],
                                    -(month.resgates ?: BigDecimal.ZERO).toDouble() to palette["series-1"],
                                ),
                                null,
                            )
                        },
                        lineColor = palette["zinc-900"],
                        tickLabel = { if (hidden) "" else HomeFlow.compactAxis(BigDecimal.valueOf(it)) },
                        selected = viewModel.aportesSelected,
                        onSelect = viewModel::selectAportesMonth,
                    )
                    viewModel.aportesSelected?.let { data.months.getOrNull(it) }?.let { month ->
                        Column(
                            Modifier.fillMaxWidth().background(palette["zinc-50"], RoundedCornerShape(12.dp)).padding(12.dp),
                            verticalArrangement = Arrangement.spacedBy(2.dp),
                        ) {
                            Text(monthLabel(month.month), color = palette.text, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                            DetailFigure(stringResource(R.string.inv_aportes), moneyOrMasked(month.aportes, hidden))
                            DetailFigure(stringResource(R.string.inv_resgates), moneyOrMasked(month.resgates, hidden))
                            Text(stringResource(R.string.inv_aportes_net, signedOrMasked(month.liquido, hidden)), color = palette.muted, fontSize = 12.sp)
                        }
                    }
                }
            }
        }
    }
}

/** O seletor de classe ("Todas as classes", Acoes, FIIs, Renda Fixa, Outros). */
@Composable
internal fun ClassSelect(value: String, onSelect: (String) -> Unit) {
    SelectField(
        value = value,
        options = listOf(SelectOption("", stringResource(R.string.inv_all_classes))) +
            PortfolioView.ASSET_CLASSES.map { SelectOption(it, PortfolioView.classLabel(it)) },
        onSelect = onSelect,
    )
}

@Composable
internal fun MiniFigure(label: String, value: String, modifier: Modifier = Modifier) {
    val palette = LocalPalette.current
    Column(modifier) {
        Text(label, color = palette.muted, fontSize = 12.sp)
        Text(value, color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
    }
}

@Composable
private fun MovementCard(movement: OperationDto, viewModel: OperacoesViewModel) {
    val palette = LocalPalette.current
    val hidden = viewModel.hidden
    val view = OperacoesViewModel.movementOf(movement)
    val info = Operations.describe(view)
    Panel {
        Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Column(Modifier.weight(1f)) {
                    Text(movement.tickerOrName.orEmpty(), color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
                    val category = movement.assetCategoryLabel?.takeIf { it.isNotEmpty() } ?: PortfolioView.classLabel(movement.assetClass)
                    Text("$category · ${info.dateLabel}", color = palette.muted, fontSize = 12.sp)
                }
                Text(moneyOrMasked(info.totalValue, hidden), color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                val parts = buildList {
                    add(stringResource(R.string.inv_movement_at, moneyOrMasked(info.unitPrice, hidden)))
                    if (info.fees.signum() > 0) add(stringResource(R.string.inv_movement_costs, moneyOrMasked(info.fees, hidden)))
                    if (info.isSale) add(stringResource(R.string.inv_movement_net, moneyOrMasked(info.netProceeds, hidden)))
                    if (info.inStatement) add(stringResource(R.string.inv_movement_in_statement))
                    if (info.adjusted) add(stringResource(R.string.inv_movement_adjusted))
                }
                Column(Modifier.weight(1f)) {
                    Text(info.kindLabel, color = palette["zinc-800"], fontWeight = FontWeight.Medium, fontSize = 13.sp)
                    Text(parts.joinToString(" · "), color = palette["zinc-600"], fontSize = 12.sp)
                }
                // Uma bonificacao e do evento corporativo: muda ou sai desfazendo o evento.
                if (!info.isBonus) {
                    OverflowMenu(
                        listOf(
                            MenuAction(stringResource(R.string.inv_movement_edit)) { viewModel.openEdit(movement) },
                            MenuAction(stringResource(R.string.inv_movement_delete)) { viewModel.askDelete(movement) },
                        ),
                        stringResource(R.string.inv_movement_actions, movement.tickerOrName.orEmpty()),
                    )
                }
            }
            if (info.hasResult) {
                Row(
                    Modifier.fillMaxWidth().background(palette["zinc-50"], RoundedCornerShape(12.dp)).padding(12.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(stringResource(R.string.inv_result), color = palette["zinc-600"], fontSize = 12.sp)
                        Text(signedOrMasked(movement.realizedProfit, hidden), color = if (hidden) palette.text else profitColor(palette, movement.realizedProfit), fontWeight = FontWeight.SemiBold)
                        Text(stringResource(R.string.inv_result_base, moneyOrMasked(movement.realizedCostBasis, hidden)), color = palette["zinc-600"], fontSize = 12.sp)
                        Text(Operations.realizedDetail(view), color = palette["zinc-600"], fontSize = 12.sp)
                    }
                    Column(Modifier.weight(1f)) {
                        Text(stringResource(R.string.inv_realized_tax), color = palette["zinc-600"], fontSize = 12.sp)
                        Text(moneyOrMasked(movement.realizedTaxAmount, hidden), color = palette.text, fontWeight = FontWeight.Medium)
                        Text(
                            stringResource(R.string.inv_result_after_tax, signedOrMasked(movement.realizedNetProfitAfterTax, hidden)),
                            color = if (hidden) palette["zinc-600"] else profitColor(palette, movement.realizedNetProfitAfterTax),
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Medium,
                        )
                        Text(
                            stringResource(R.string.inv_result_rate, formatPercent((movement.realizedTaxRate ?: BigDecimal.ZERO).multiply(BigDecimal(100)))),
                            color = palette["zinc-600"],
                            fontSize = 12.sp,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun EventsPanel(viewModel: OperacoesViewModel) {
    val palette = LocalPalette.current
    val events = viewModel.events.value
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            PanelTitle(stringResource(R.string.inv_events_title), stringResource(R.string.inv_events_description))
            AppButton(
                stringResource(R.string.inv_events_register),
                viewModel::openCorporate,
                Modifier.fillMaxWidth(),
                variant = ButtonVariant.SECONDARY,
                enabled = viewModel.eligibleAssets.isNotEmpty(),
            )
            AlertMessage(viewModel.eventsError, AlertTone.DANGER, stringResource(R.string.lanc_dismiss), onDismiss = viewModel::dismissEventsError)
            AlertMessage(viewModel.events.error, AlertTone.DANGER, stringResource(R.string.lanc_dismiss))
            when {
                events == null -> Unit
                events.isEmpty() -> EmptyState(stringResource(R.string.inv_events_empty_title), stringResource(R.string.inv_events_empty_message))
                else -> events.forEach { event ->
                    HorizontalDivider(color = palette.border)
                    EventRow(event, viewModel)
                }
            }
        }
    }
}

@Composable
private fun EventRow(event: CorporateActionDto, viewModel: OperacoesViewModel) {
    val palette = LocalPalette.current
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Column(Modifier.weight(1f)) {
            Text(
                "${event.ticker.orEmpty()} · ${event.label.orEmpty()} ${Operations.ratioLabel(event.ratioFrom, event.ratioTo)}",
                color = palette.text,
                fontWeight = FontWeight.SemiBold,
                fontSize = 14.sp,
            )
            val details = buildString {
                append(stringResource(R.string.inv_events_ex_date, formatDateBR(event.exDate)))
                if (event.actionType == "BONUS") append(" · " + stringResource(R.string.inv_events_bonus_cost, formatCurrency(event.bonusUnitCost ?: BigDecimal.ZERO)))
                if (!event.notes.isNullOrEmpty()) append(" · ${event.notes}")
            }
            Text(details, color = palette.muted, fontSize = 12.sp)
        }
        AppButton(stringResource(R.string.inv_corporate_undo), { viewModel.askUndo(event) }, variant = ButtonVariant.SUBTLE)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun EditSheetView(sheet: EditSheet, viewModel: OperacoesViewModel) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val palette = LocalPalette.current
    val form = sheet.form
    val cancel = stringResource(R.string.lanc_cancel)
    val fixed = form.assetClass == "FIXED_INCOME"
    AppSheet(
        title = stringResource(R.string.inv_edit_title),
        sheetState = sheetState,
        onDismiss = viewModel::closeEdit,
        footer = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AppButton(cancel, viewModel::closeEdit, Modifier.weight(1f), variant = ButtonVariant.SECONDARY)
                AppButton(stringResource(R.string.lanc_save), viewModel::saveEdit, Modifier.weight(1f), loading = viewModel.editSaving)
            }
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text(stringResource(R.string.inv_edit_asset, form.tickerOrName), color = palette["zinc-600"], fontSize = 14.sp)
            AlertMessage(viewModel.editError, AlertTone.DANGER, stringResource(R.string.lanc_dismiss))
            if (!fixed) {
                Field(stringResource(R.string.inv_launch_quantity)) {
                    AppTextField(form.quantity, { viewModel.changeEdit(form.copy(quantity = it)) }, keyboardType = KeyboardType.Decimal)
                }
            }
            if (!form.isSale) {
                val label = when {
                    form.isRedemption -> R.string.inv_edit_redeemed_cost
                    fixed -> R.string.inv_edit_applied
                    else -> R.string.inv_edit_average
                }
                Field(stringResource(label)) {
                    AppTextField(form.averagePrice, { viewModel.changeEdit(form.copy(averagePrice = it)) }, keyboardType = KeyboardType.Decimal)
                }
            } else {
                Field(stringResource(R.string.inv_edit_sale_price), hint = stringResource(R.string.inv_edit_sale_price_hint)) {
                    AppTextField(form.salePrice, { viewModel.changeEdit(form.copy(salePrice = it)) }, keyboardType = KeyboardType.Decimal)
                }
            }
            Field(stringResource(R.string.inv_edit_costs)) {
                AppTextField(form.otherCosts, { viewModel.changeEdit(form.copy(otherCosts = it)) }, keyboardType = KeyboardType.Decimal)
            }
            Field(stringResource(R.string.inv_launch_date)) {
                DateField(form.movementDate, { viewModel.changeEdit(form.copy(movementDate = it)) }, stringResource(R.string.lanc_date_ok), cancel)
            }
            CashLinkField(
                form.cashLink,
                viewModel::cashLinkChange,
                viewModel.accounts.value,
                if (form.isRedemption) "REDEMPTION" else if (form.isSale) "SELL" else "BUY",
                savedAccountId = form.savedCashAccountId,
                allAccounts = viewModel.allAccounts.value,
            )
            if (form.isTreasuryBuy) {
                Field(stringResource(R.string.inv_launch_units), hint = stringResource(R.string.inv_edit_units_hint)) {
                    AppTextField(form.treasuryUnits, { viewModel.changeEdit(form.copy(treasuryUnits = it)) }, placeholder = "Ex: 0,85", keyboardType = KeyboardType.Decimal)
                }
            }
            if (fixed && !form.isRedemption) {
                FixedIncomeFieldsView(form.fixedIncome, { viewModel.changeEdit(form.copy(fixedIncome = it)) }, FixedIncome.FIXED_INCOME_TYPES)
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CorporateSheet(form: CorporateForm, viewModel: OperacoesViewModel) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val palette = LocalPalette.current
    val cancel = stringResource(R.string.lanc_cancel)
    AppSheet(
        title = stringResource(R.string.inv_corporate_title),
        sheetState = sheetState,
        onDismiss = viewModel::closeCorporate,
        footer = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AppButton(cancel, viewModel::closeCorporate, Modifier.weight(1f), variant = ButtonVariant.SECONDARY)
                AppButton(stringResource(R.string.inv_corporate_register), viewModel::saveCorporate, Modifier.weight(1f), loading = viewModel.corporateSaving)
            }
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text(Operations.CORPORATE_HINTS[form.actionType].orEmpty(), color = palette["zinc-600"], fontSize = 14.sp)
            AlertMessage(viewModel.corporateError, AlertTone.DANGER, stringResource(R.string.lanc_dismiss))
            SegmentedChoice(
                items = Operations.CORPORATE_TYPES.map { SelectOption(it.first, it.second) },
                value = form.actionType,
                onChange = viewModel::changeCorporateType,
            )
            Field(stringResource(R.string.inv_launch_asset)) {
                SelectField(form.assetId, viewModel.eligibleAssets.map { SelectOption(it.first, it.second) }, { viewModel.changeCorporate(form.copy(assetId = it)) })
            }
            Field(stringResource(R.string.inv_corporate_ex_date), hint = stringResource(R.string.inv_corporate_ex_date_hint)) {
                DateField(form.exDate, { viewModel.changeCorporate(form.copy(exDate = it)) }, stringResource(R.string.lanc_date_ok), cancel)
            }
            Field(stringResource(R.string.inv_corporate_from)) {
                AppTextField(form.ratioFrom, { viewModel.changeCorporate(form.copy(ratioFrom = it)) }, keyboardType = KeyboardType.Decimal)
            }
            Field(stringResource(if (form.actionType == "BONUS") R.string.inv_corporate_to_new else R.string.inv_corporate_to)) {
                AppTextField(form.ratioTo, { viewModel.changeCorporate(form.copy(ratioTo = it)) }, keyboardType = KeyboardType.Decimal)
            }
            if (form.actionType == "BONUS") {
                Field(stringResource(R.string.inv_corporate_cost), hint = stringResource(R.string.inv_corporate_cost_hint)) {
                    AppTextField(form.bonusUnitCost, { viewModel.changeCorporate(form.copy(bonusUnitCost = it)) }, placeholder = "0,00", keyboardType = KeyboardType.Decimal)
                }
            }
            Field(stringResource(R.string.inv_corporate_notes)) {
                AppTextField(form.notes, { viewModel.changeCorporate(form.copy(notes = it)) })
            }
            Text(stringResource(R.string.inv_corporate_footnote), color = palette.muted, fontSize = 12.sp)
        }
    }
}
