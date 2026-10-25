package br.financas.app.ui.investimentos

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
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
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.core.formatDateBR
import br.financas.app.core.formatDecimal
import br.financas.app.core.formatPercent
import br.financas.app.core.formatUnitCurrency
import br.financas.app.core.monthLabel
import br.financas.app.core.shortMonthLabel
import br.financas.app.data.ProceedDto
import br.financas.app.rules.HomeFlow
import br.financas.app.rules.ProceedsForm
import br.financas.app.rules.ProceedsRules
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
import br.financas.app.ui.lancamentos.moneyOrMasked
import br.financas.app.ui.planejar.PlanejarScaffold
import br.financas.app.ui.planejar.SummaryPanel
import br.financas.app.ui.planejar.SummaryValue
import br.financas.app.ui.theme.LocalPalette
import java.math.BigDecimal

/** Investimentos › Proventos nativo (15-investimentos-proventos.md): o calendario primeiro, filtros que recolhem. */
@Composable
fun ProventosScreen(viewModel: ProventosViewModel, onBack: () -> Unit, onTab: (InvestimentosTab) -> Unit) {
    val palette = LocalPalette.current
    val dismiss = stringResource(R.string.lanc_dismiss)
    val hidden = viewModel.hidden
    val summary = viewModel.summary.value
    val proceeds = viewModel.proceeds.value
    PlanejarScaffold(
        notices = viewModel.notices,
        onRefresh = viewModel::refreshAll,
        topBar = {
            InvestimentosTopBar(stringResource(R.string.inv_proventos_title), InvestimentosTab.PROVENTOS, hidden, onBack, viewModel::toggleHidden, onTab)
        },
    ) {
        item(key = "intro") {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(stringResource(R.string.inv_proventos_description), fontSize = 14.sp, color = palette["zinc-600"])
                AppButton(stringResource(R.string.inv_proceed_register), viewModel::openNew, Modifier.fillMaxWidth())
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    AppButton(stringResource(R.string.inv_proceeds_refresh), viewModel::sync, Modifier.weight(1f), variant = ButtonVariant.SECONDARY, loading = viewModel.syncing)
                    AppButton(stringResource(R.string.inv_export), viewModel.export::show, Modifier.weight(1f), variant = ButtonVariant.SECONDARY, enabled = !proceeds.isNullOrEmpty())
                }
            }
        }
        item(key = "alerts") {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (viewModel.proceeds.offline) AlertMessage(viewModel.proceeds.offlineText, AlertTone.WARNING, dismiss)
                AlertMessage(viewModel.proceeds.error, AlertTone.DANGER, dismiss)
                AlertMessage(viewModel.error, AlertTone.DANGER, dismiss, onDismiss = viewModel::dismissError)
                if (viewModel.queued > 0) AlertMessage(stringResource(R.string.inv_proceeds_queued, viewModel.queued), AlertTone.INFO, dismiss)
            }
        }
        item(key = "calendar") { CalendarPanel(viewModel) }
        item(key = "summary") {
            SummaryPanel(
                lead = SummaryValue(
                    stringResource(R.string.inv_proceeds_net),
                    moneyOrMasked(summary?.netAmount, hidden),
                    stringResource(R.string.inv_proceeds_net_hint, summary?.eventCount ?: 0, moneyOrMasked(summary?.grossAmount, hidden)),
                ),
                figures = listOf(
                    SummaryValue(stringResource(R.string.inv_proceeds_yoc), formatPercent(summary?.yieldOnCostPercent), stringResource(R.string.inv_proceeds_yoc_hint)),
                    SummaryValue(stringResource(R.string.inv_proceeds_scheduled), moneyOrMasked(summary?.scheduledNetAmount, hidden), stringResource(R.string.inv_proceeds_scheduled_hint)),
                    SummaryValue(stringResource(R.string.inv_proceeds_tax), moneyOrMasked(summary?.taxAmount, hidden), stringResource(R.string.inv_proceeds_tax_hint)),
                ),
            )
        }
        if (!summary?.byMonth.isNullOrEmpty()) item(key = "chart") { ReceiptsPanel(viewModel) }
        if (!summary?.byAsset.isNullOrEmpty()) item(key = "by-asset") { ByAssetPanel(viewModel) }
        item(key = "filters") { FiltersPanel(viewModel) }
        item(key = "history-title") {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) { PanelTitle(stringResource(R.string.inv_proceeds_history), stringResource(R.string.inv_proceeds_history_description)) }
                Badge(stringResource(R.string.inv_records, proceeds?.size ?: 0))
            }
        }
        when {
            proceeds == null && !viewModel.proceeds.loaded -> item(key = "loading") { Panel { ListSkeleton(rows = 5, modifier = Modifier.padding(16.dp)) } }
            proceeds == null -> Unit
            proceeds.isEmpty() -> item(key = "empty") { EmptyState(stringResource(R.string.inv_proceeds_empty_title), stringResource(R.string.inv_proceeds_empty_message)) }
            else -> proceeds.forEach { item -> item(key = "p-${item.id}") { ProceedCard(item, viewModel) } }
        }
    }
    InvestExportSheet(viewModel.export, stringResource(R.string.inv_export_proceeds_title), stringResource(R.string.inv_export_proceeds_description))
    viewModel.sheet?.let { ProceedSheetView(it, viewModel) }
    ConfirmDialog(viewModel.confirm, stringResource(R.string.lanc_cancel), viewModel::dismissConfirm)
}

@Composable
private fun CalendarPanel(viewModel: ProventosViewModel) {
    val palette = LocalPalette.current
    val events = viewModel.calendar.value.orEmpty()
    val filtered = viewModel.filters.assetId.isNotEmpty() || viewModel.filters.proceedsType.isNotEmpty()
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) { PanelTitle(stringResource(R.string.inv_calendar_title), stringResource(R.string.inv_calendar_description)) }
                Badge(stringResource(R.string.inv_events_count, events.size))
            }
            if (events.isEmpty()) {
                EmptyState(
                    stringResource(R.string.inv_calendar_empty_title),
                    stringResource(if (filtered) R.string.inv_calendar_empty_filtered else R.string.inv_calendar_empty_message),
                )
            } else {
                events.take(8).forEach { item ->
                    HorizontalDivider(color = palette.border)
                    Column(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                        Row {
                            Text(formatDateBR(item.paymentDate), color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                            Text(" " + ProceedsRules.typeLabel(item.proceedsType.orEmpty()), color = palette["zinc-600"], fontSize = 14.sp)
                        }
                        Text("${item.asset?.ticker.orEmpty()} - ${moneyOrMasked(item.netAmount, viewModel.hidden)}", color = palette["zinc-600"], fontSize = 13.sp)
                    }
                }
            }
        }
    }
}

@Composable
private fun ReceiptsPanel(viewModel: ProventosViewModel) {
    val palette = LocalPalette.current
    val hidden = viewModel.hidden
    val summary = viewModel.summary.value ?: return
    val year = viewModel.chartPeriod == "year"
    // by_month (AAAA-MM) e by_year vem somados do servidor; aqui so a ordem.
    val rows: List<Triple<String, BigDecimal, Int>> = if (year) {
        ProceedsForm.chartRows(summary.byYear) { it.year.toString() }.map { Triple(it.year.toString(), it.netAmount ?: BigDecimal.ZERO, it.eventCount) }
    } else {
        ProceedsForm.chartRows(summary.byMonth) { it.month.orEmpty() }.map { Triple(it.month.orEmpty(), it.netAmount ?: BigDecimal.ZERO, it.eventCount) }
    }
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            PanelTitle(stringResource(if (year) R.string.inv_receipts_year else R.string.inv_receipts_month), stringResource(R.string.inv_receipts_description))
            PeriodChips(ProventosViewModel.CHART_PERIODS, viewModel.chartPeriod, viewModel::changeChartPeriod)
            StackedBarChart(
                columns = rows.map { (key, net, _) -> BarColumn(if (year) key else shortMonthLabel(key), listOf(net.toDouble() to palette["flow-income"]), null) },
                lineColor = palette["zinc-900"],
                tickLabel = { if (hidden) "" else HomeFlow.compactAxis(BigDecimal.valueOf(it)) },
                selected = viewModel.chartSelected,
                onSelect = viewModel::selectChart,
            )
            viewModel.chartSelected?.let { rows.getOrNull(it) }?.let { (key, net, count) ->
                Column(Modifier.fillMaxWidth().background(palette["zinc-50"], RoundedCornerShape(12.dp)).padding(12.dp)) {
                    Text(if (year) key else monthLabel(key), color = palette.text, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                    DetailFigure(stringResource(R.string.inv_liquido), moneyOrMasked(net, hidden))
                    Text(stringResource(R.string.inv_events_count, count), color = palette.muted, fontSize = 12.sp)
                }
            }
        }
    }
}

@Composable
private fun ByAssetPanel(viewModel: ProventosViewModel) {
    val palette = LocalPalette.current
    val hidden = viewModel.hidden
    val items = viewModel.summary.value?.byAsset.orEmpty()
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) { PanelTitle(stringResource(R.string.inv_by_asset_title), stringResource(R.string.inv_by_asset_description)) }
                Badge(stringResource(R.string.inv_assets_count, items.size))
            }
            items.forEach { item ->
                HorizontalDivider(color = palette.border)
                Row(Modifier.padding(vertical = 4.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Column(Modifier.weight(1f)) {
                        Text(item.ticker.orEmpty(), color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                        Text(
                            stringResource(R.string.inv_by_asset_line, item.eventCount, moneyOrMasked(item.net12m, hidden), formatPercent(item.yieldOnCostPercent)),
                            color = palette["zinc-600"],
                            fontSize = 12.sp,
                        )
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text(moneyOrMasked(item.netAmount, hidden), color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                        Text(stringResource(R.string.inv_by_asset_share, formatPercent(item.sharePercent)), color = palette.muted, fontSize = 12.sp)
                    }
                }
            }
        }
    }
}

@Composable
private fun FiltersPanel(viewModel: ProventosViewModel) {
    val palette = LocalPalette.current
    val filters = viewModel.filters
    val cancel = stringResource(R.string.lanc_cancel)
    val ok = stringResource(R.string.lanc_date_ok)
    val loading = viewModel.proceeds.value != null && !viewModel.proceeds.loaded
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    PanelTitle(stringResource(R.string.inv_filters_title), stringResource(R.string.inv_filters_summary, formatDateBR(filters.dateFrom), formatDateBR(filters.dateTo)))
                }
                if (loading) Badge(stringResource(R.string.inv_filters_updating))
                AppButton(stringResource(if (viewModel.filtersOpen) R.string.inv_hide else R.string.inv_filters_change), viewModel::toggleFilters, variant = ButtonVariant.SUBTLE)
            }
            SegmentedChoice(
                items = ProventosViewModel.STATUS_ITEMS.map { SelectOption(it.first, it.second) },
                value = filters.status,
                onChange = { viewModel.changeFilters(filters.copy(status = it)) },
            )
            if (viewModel.filtersOpen) {
                Text(stringResource(R.string.inv_filters_description), color = palette.muted, fontSize = 13.sp)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Field(stringResource(R.string.inv_filters_from), Modifier.weight(1f)) { DateField(filters.dateFrom, { viewModel.changeFilters(filters.copy(dateFrom = it)) }, ok, cancel) }
                    Field(stringResource(R.string.inv_filters_to), Modifier.weight(1f)) { DateField(filters.dateTo, { viewModel.changeFilters(filters.copy(dateTo = it)) }, ok, cancel) }
                }
                Field(stringResource(R.string.inv_launch_asset)) {
                    SelectField(
                        filters.assetId,
                        listOf(SelectOption("", stringResource(R.string.inv_filters_all))) + viewModel.assets.value.orEmpty().map { SelectOption(it.id, it.ticker.orEmpty()) },
                        { viewModel.changeFilters(filters.copy(assetId = it)) },
                    )
                }
                Field(stringResource(R.string.inv_filters_type)) {
                    SelectField(
                        filters.proceedsType,
                        listOf(SelectOption("", stringResource(R.string.inv_filters_all))) + ProceedsRules.PROCEEDS_TYPES.map { SelectOption(it.value, it.label) },
                        { viewModel.changeFilters(filters.copy(proceedsType = it)) },
                    )
                }
            }
        }
    }
}

@Composable
private fun ProceedCard(item: ProceedDto, viewModel: ProventosViewModel) {
    val palette = LocalPalette.current
    val hidden = viewModel.hidden
    // Cupom ou amortizacao de renda fixa (e Tesouro): sem data com nem valor por cota.
    val fixed = item.asset?.assetClass == "FIXED_INCOME"
    Panel {
        Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Column(Modifier.weight(1f)) {
                    Text(item.asset?.ticker.orEmpty(), color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
                    val dates = formatDateBR(item.paymentDate) + if (fixed) "" else " · com ${formatDateBR(item.recordDate)}"
                    Text("$dates · ${viewModel.categoryOf(item.assetId, item.asset?.assetClass)}", color = palette["zinc-600"], fontSize = 12.sp)
                }
                Text(moneyOrMasked(item.netAmount, hidden), color = if (hidden) palette.text else palette["emerald-700"], fontWeight = FontWeight.Bold, fontSize = 15.sp)
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Row {
                        Text(ProceedsRules.typeLabel(item.proceedsType.orEmpty()), color = palette["zinc-700"], fontSize = 14.sp)
                        if (item.status != "PAID") Text(" " + stringResource(R.string.inv_proceed_scheduled_tag), color = palette["sky-700"], fontWeight = FontWeight.Medium, fontSize = 14.sp)
                    }
                    val perUnit = if (fixed) {
                        ""
                    } else {
                        stringResource(
                            R.string.inv_proceed_per_unit,
                            if (hidden) br.financas.app.ui.home.HomeLogic.MASKED_CURRENCY else formatUnitCurrency(item.amountPerUnit),
                            if (hidden) "••••••" else formatDecimal(item.eligibleQuantity ?: BigDecimal.ZERO, 6),
                        ) + " · "
                    }
                    Text(
                        perUnit + stringResource(
                            R.string.inv_proceed_values,
                            moneyOrMasked(item.grossAmount, hidden),
                            moneyOrMasked(item.taxAmount, hidden),
                            formatPercent(item.yieldOnCostPercent, 4),
                        ),
                        color = palette["zinc-600"],
                        fontSize = 12.sp,
                    )
                }
                OverflowMenu(
                    listOf(
                        MenuAction(stringResource(R.string.inv_proceed_edit)) { viewModel.openEdit(item) },
                        MenuAction(stringResource(R.string.inv_proceed_delete)) { viewModel.askDelete(item) },
                    ),
                    stringResource(R.string.inv_proceed_actions, item.asset?.ticker ?: stringResource(R.string.inv_proceed_asset_fallback)),
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ProceedSheetView(sheet: ProceedSheet, viewModel: ProventosViewModel) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val palette = LocalPalette.current
    val form = sheet.form
    val editing = sheet.editing != null
    val cancel = stringResource(R.string.lanc_cancel)
    val ok = stringResource(R.string.lanc_date_ok)
    val asset = viewModel.assetsById[form.assetId]
    val ruleAsset = asset?.let(viewModel::ruleAsset)
    val layout = ProceedsRules.proceedsLayout(form.proceedsType, ruleAsset)
    val taxField = ProceedsRules.proceedsTaxField(form.proceedsType)
    AppSheet(
        title = stringResource(if (editing) R.string.inv_proceed_edit else R.string.inv_proceed_register),
        sheetState = sheetState,
        onDismiss = viewModel::closeSheet,
        footer = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AppButton(cancel, viewModel::closeSheet, Modifier.weight(1f), variant = ButtonVariant.SECONDARY)
                AppButton(stringResource(R.string.lanc_save), viewModel::save, Modifier.weight(1f), loading = viewModel.sheetSaving)
            }
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text(stringResource(R.string.inv_proceed_sheet_description), color = palette["zinc-600"], fontSize = 14.sp)
            AlertMessage(viewModel.sheetError, AlertTone.DANGER, stringResource(R.string.lanc_dismiss))
            Field(stringResource(R.string.inv_proceed_type), hint = ProceedsRules.TYPE_HINTS[form.proceedsType]) {
                SelectField(form.proceedsType, ProceedsRules.PROCEEDS_TYPES.map { SelectOption(it.value, it.label) }, viewModel::changeType)
            }
            Field(stringResource(R.string.inv_launch_asset)) {
                val options = viewModel.assetOptions()
                val selected = asset?.let { PickerOption(it.id, it.ticker.orEmpty(), listOfNotNull(ProceedsRules.categoryLabel(ruleAsset).takeIf { c -> c.isNotEmpty() }, it.name?.takeIf { n -> n.isNotEmpty() && n != it.ticker }).joinToString(" · ")) }
                AssetPickerField(
                    query = sheet.assetQuery,
                    onQuery = viewModel::typeAssetQuery,
                    selected = selected,
                    options = options,
                    onPick = { viewModel.pickAsset(it.value) },
                    placeholder = stringResource(R.string.inv_launch_sale_search),
                    emptyMessage = stringResource(R.string.inv_proceed_no_assets),
                    open = sheet.pickerOpen || selected == null,
                    onOpen = viewModel::reopenPicker,
                )
            }
            if (asset == null) {
                Text(stringResource(R.string.inv_proceed_pick_asset), color = palette.muted, fontSize = 14.sp)
                return@Column
            }
            val change = { next: ProceedsForm.Form -> viewModel.changeForm(next) }
            val taxInput: @Composable () -> Unit = {
                if (taxField != null) {
                    Field(taxField.label, hint = taxField.hint) {
                        AppTextField(form.taxAmount, { change(form.copy(taxAmount = it)) }, placeholder = "auto", keyboardType = KeyboardType.Decimal)
                    }
                }
            }
            if (layout == "FIXED") {
                Field(stringResource(if (editing || form.repeatEvery.isEmpty()) R.string.inv_proceed_payment else R.string.inv_proceed_first_payment)) {
                    DateField(form.paymentDate, { change(form.copy(paymentDate = it)) }, ok, cancel)
                }
                Field(stringResource(R.string.inv_proceed_gross), hint = if (form.proceedsType == "AMORTIZATION") stringResource(R.string.inv_proceed_amortization_hint) else null) {
                    AppTextField(form.grossAmount, { change(form.copy(grossAmount = it)) }, placeholder = "0,00", keyboardType = KeyboardType.Decimal)
                }
                taxInput()
                if (!editing) {
                    Field(stringResource(R.string.inv_proceed_repeat)) {
                        SelectField(form.repeatEvery, ProceedsForm.REPEAT_OPTIONS.map { SelectOption(it.first, it.second) }, { change(form.copy(repeatEvery = it)) })
                    }
                    if (form.repeatEvery.isNotEmpty()) {
                        Field(stringResource(R.string.inv_proceed_count), hint = stringResource(R.string.inv_proceed_count_hint)) {
                            AppTextField(form.repeatCount, { change(form.copy(repeatCount = it)) }, keyboardType = KeyboardType.Number)
                        }
                    }
                }
            } else {
                Field(stringResource(R.string.inv_proceed_record_date), hint = stringResource(R.string.inv_proceed_record_date_hint)) {
                    DateField(form.recordDate, { change(form.copy(recordDate = it)) }, ok, cancel)
                }
                Field(stringResource(R.string.inv_proceed_ex_date)) {
                    DateField(form.exDate, { change(form.copy(exDate = it)) }, ok, cancel, clearLabel = stringResource(R.string.inv_clear), onClear = { change(form.copy(exDate = "")) })
                }
                Field(stringResource(R.string.inv_proceed_payment)) {
                    DateField(form.paymentDate, { change(form.copy(paymentDate = it)) }, ok, cancel)
                }
                Field(stringResource(R.string.inv_proceed_declared)) {
                    DateField(form.declaredDate, { change(form.copy(declaredDate = it)) }, ok, cancel, clearLabel = stringResource(R.string.inv_clear), onClear = { change(form.copy(declaredDate = "")) })
                }
                Field(stringResource(R.string.inv_proceed_per_unit_label)) {
                    AppTextField(form.amountPerUnit, { change(form.copy(amountPerUnit = it)) }, placeholder = "0,00", keyboardType = KeyboardType.Decimal)
                }
                Field(stringResource(R.string.inv_proceed_eligible)) {
                    AppTextField(form.eligibleQuantity, { change(form.copy(eligibleQuantity = it)) }, placeholder = "auto", keyboardType = KeyboardType.Decimal)
                }
                Field(
                    stringResource(R.string.inv_proceed_gross),
                    hint = stringResource(if (form.proceedsType == "AMORTIZATION") R.string.inv_proceed_amortization_hint else R.string.inv_proceed_gross_hint),
                ) {
                    AppTextField(form.grossAmount, { change(form.copy(grossAmount = it)) }, placeholder = "auto", keyboardType = KeyboardType.Decimal)
                }
                taxInput()
            }
            Field(stringResource(R.string.inv_proceed_notes)) {
                AppTextField(form.notes, { change(form.copy(notes = it)) })
            }
        }
    }
}
