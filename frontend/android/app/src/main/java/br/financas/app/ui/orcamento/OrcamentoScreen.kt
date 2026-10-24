package br.financas.app.ui.orcamento

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.SheetValue
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.core.formatCurrency
import br.financas.app.core.formatDateBR
import br.financas.app.core.formatSignedCurrency
import br.financas.app.core.monthLabel
import br.financas.app.data.PlanBudgetDto
import br.financas.app.data.BudgetLineDto
import br.financas.app.data.MonthlyPlanDto
import br.financas.app.rules.BudgetStatus
import br.financas.app.rules.FlagTone
import br.financas.app.rules.MonthlyPlan
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AlertTone
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.AppIcons
import br.financas.app.ui.components.AppSheet
import br.financas.app.ui.components.AppTextField
import br.financas.app.ui.components.Badge
import br.financas.app.ui.components.BadgeTone
import br.financas.app.ui.components.ButtonVariant
import br.financas.app.ui.components.ConfirmDialog
import br.financas.app.ui.components.EmptyState
import br.financas.app.ui.components.Field
import br.financas.app.ui.components.ListSkeleton
import br.financas.app.ui.components.MenuAction
import br.financas.app.ui.components.OverflowMenu
import br.financas.app.ui.components.Panel
import br.financas.app.ui.components.PercentSlider
import br.financas.app.ui.components.SelectField
import br.financas.app.ui.components.SelectOption
import br.financas.app.ui.lancamentos.AmountInput
import br.financas.app.ui.lancamentos.moneyOrMasked
import br.financas.app.ui.planejar.BudgetProgressBar
import br.financas.app.ui.planejar.PlanejarScaffold
import br.financas.app.ui.planejar.PlanejarTab
import br.financas.app.ui.planejar.PlanejarTopBar
import br.financas.app.ui.planejar.SummaryPanel
import br.financas.app.ui.planejar.SummaryValue
import br.financas.app.ui.theme.LocalPalette
import java.math.BigDecimal

/**
 * Orcamento nativo (08-orcamento.md): Orcamento.jsx, MonthlyPlanPanel, MonthlyPlanSheet e
 * BudgetLines em Compose, sobre GET /api/monthly-plan.
 */
@Composable
fun OrcamentoScreen(
    viewModel: OrcamentoViewModel,
    onBack: () -> Unit,
    onTab: (PlanejarTab) -> Unit,
    onOpenLink: (String) -> Unit,
) {
    val dismiss = stringResource(R.string.lanc_dismiss)
    PlanejarScaffold(
        notices = viewModel.notices,
        onRefresh = viewModel::refreshAll,
        topBar = {
            PlanejarTopBar(stringResource(R.string.orc_title), PlanejarTab.ORCAMENTO, viewModel.hidden, onBack, viewModel::toggleHidden, onTab)
        },
    ) {
        item(key = "month") { MonthSwitcher(viewModel) }
        item(key = "alerts") {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (viewModel.plan.offline) AlertMessage(viewModel.plan.offlineText, AlertTone.WARNING, dismiss)
                AlertMessage(viewModel.plan.error, AlertTone.DANGER, dismiss)
                AlertMessage(viewModel.actionError, AlertTone.DANGER, dismiss, onDismiss = viewModel::dismissActionError)
            }
        }
        val data = viewModel.data
        val row = viewModel.row
        when {
            data == null -> if (!viewModel.plan.loaded) item(key = "loading") {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Panel { ListSkeleton(rows = 2, modifier = Modifier.padding(16.dp)) }
                    Panel { ListSkeleton(rows = 4, modifier = Modifier.padding(16.dp)) }
                }
            }
            row == null -> item(key = "empty") {
                EmptyWithAction(
                    title = stringResource(R.string.orc_empty_title),
                    message = stringResource(R.string.orc_empty_message),
                    action = stringResource(R.string.orc_define_plan),
                    onAction = viewModel::openSheet,
                )
            }
            row.needsIncome -> item(key = "needs-income") {
                EmptyWithAction(
                    title = stringResource(R.string.orc_needs_income_title),
                    message = stringResource(R.string.orc_needs_income_message),
                    action = stringResource(R.string.orc_inform_income),
                    onAction = viewModel::openSheet,
                )
            }
            else -> {
                item(key = "summary") { Summary(data, viewModel.hidden) }
                item(key = "plan") { PlanPanel(data, viewModel, onOpenLink) }
            }
        }
        if (data != null && viewModel.hasFigures) {
            item(key = "categories") { CategoriesPanel(data, viewModel, onOpenLink) }
        }
    }

    viewModel.sheet?.let { PlanSheet(viewModel) }
    ConfirmDialog(viewModel.confirm, stringResource(R.string.lanc_cancel), viewModel::dismissConfirm)
}

@Composable
private fun MonthSwitcher(viewModel: OrcamentoViewModel) {
    val palette = LocalPalette.current
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
        RoundButton("‹", stringResource(R.string.orc_previous_month)) { viewModel.shift(-1) }
        Text(
            text = monthLabel(viewModel.month).replaceFirstChar { it.uppercase() },
            fontWeight = FontWeight.SemiBold,
            color = palette["zinc-800"],
            modifier = Modifier.weight(1f),
            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
        )
        RoundButton("›", stringResource(R.string.orc_next_month)) { viewModel.shift(1) }
    }
}

@Composable
private fun RoundButton(glyph: String, label: String, onClick: () -> Unit) {
    val palette = LocalPalette.current
    Surface(
        onClick = onClick,
        shape = CircleShape,
        color = palette.surface,
        border = BorderStroke(1.dp, palette.border),
        modifier = Modifier.size(48.dp).semantics { contentDescription = label },
    ) {
        Box(contentAlignment = Alignment.Center) { Text(glyph, fontSize = 22.sp, color = palette.text) }
    }
}

@Composable
private fun EmptyWithAction(title: String, message: String, action: String, onAction: () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        EmptyState(title = title, message = message)
        AppButton(action, onAction, Modifier.fillMaxWidth())
    }
}

@Composable
private fun Summary(data: MonthlyPlanDto, hidden: Boolean) {
    val balance = data.planBalance
    val daily = data.dailyAvailable
    fun money(value: BigDecimal?) = if (value == null) "—" else moneyOrMasked(value, hidden)
    SummaryPanel(
        lead = SummaryValue(
            stringResource(R.string.orc_plan_balance),
            money(balance),
            stringResource(R.string.orc_plan_balance_hint),
            loss = !hidden && (balance?.signum() ?: 0) < 0,
        ),
        figures = listOf(
            SummaryValue(
                stringResource(R.string.orc_daily),
                money(daily),
                stringResource(if (data.period == "PAST") R.string.orc_daily_past else R.string.orc_daily_hint),
                loss = !hidden && (daily?.signum() ?: 0) < 0,
            ),
        ),
    )
}

@Composable
private fun PlanPanel(data: MonthlyPlanDto, viewModel: OrcamentoViewModel, onOpenLink: (String) -> Unit) {
    val palette = LocalPalette.current
    val row = data.plan ?: return
    val actual = data.actual
    val progress = data.progress
    Panel {
        Column {
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(start = 16.dp, end = 8.dp, top = 12.dp, bottom = 4.dp)) {
                Text(stringResource(R.string.orc_income_title), fontWeight = FontWeight.Bold, fontSize = 17.sp, color = palette.text, modifier = Modifier.weight(1f))
                AppButton(stringResource(R.string.orc_edit_plan), viewModel::openSheet, variant = ButtonVariant.SECONDARY)
            }
            Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
                Text(MonthlyPlan.incomeReceivedText(data.income?.received, data.income?.planned), fontWeight = FontWeight.SemiBold, fontSize = 14.sp, color = palette.text)
                if (row.inherited) {
                    Text(
                        stringResource(R.string.orc_plan_from, monthLabel(row.sourceMonth).replaceFirstChar { it.uppercase() }),
                        fontSize = 14.sp,
                        color = palette.muted,
                    )
                }
            }
            HorizontalDivider(color = palette["zinc-100"])
            val investRemaining = progress?.investRemaining ?: BigDecimal.ZERO
            PlanLevel(
                label = stringResource(R.string.orc_invest),
                percent = data.invest?.percent,
                amount = data.invest?.amount,
                realized = stringResource(R.string.orc_invested_so_far, formatCurrency(actual?.invested)),
                progress = progress?.investPercent ?: BigDecimal.ZERO,
                status = BudgetStatus.OK,
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        if (investRemaining.signum() > 0) stringResource(R.string.orc_invest_remaining, formatCurrency(investRemaining)) else stringResource(R.string.orc_invest_done),
                        fontSize = 14.sp,
                        color = palette["zinc-600"],
                        modifier = Modifier.weight(1f),
                    )
                    if ((data.invest?.amount?.signum() ?: 0) > 0) {
                        Text(
                            stringResource(R.string.orc_how_to_split),
                            color = palette["emerald-700"],
                            fontWeight = FontWeight.SemiBold,
                            fontSize = 14.sp,
                            modifier = Modifier.heightIn(min = 48.dp).clickable { onOpenLink("/investimentos/alocacao") }.padding(horizontal = 8.dp, vertical = 14.dp),
                        )
                    }
                }
            }
            HorizontalDivider(color = palette["zinc-100"])
            val spent = actual?.spent ?: BigDecimal.ZERO
            PlanLevel(
                label = stringResource(R.string.orc_spend),
                percent = data.spend?.percent,
                amount = data.spend?.amount,
                realized = stringResource(R.string.orc_spent_so_far, formatCurrency(actual?.spent)),
                progress = progress?.spendPercent ?: if (spent.signum() > 0) BigDecimal(100) else BigDecimal.ZERO,
                status = MonthlyPlan.spendStatus(viewModel.sortedFlags),
            )
            if ((data.unallocated?.percent?.signum() ?: 0) > 0) {
                HorizontalDivider(color = palette["zinc-100"])
                PlanLevel(stringResource(R.string.orc_unallocated), data.unallocated?.percent, data.unallocated?.amount, null, null, BudgetStatus.OK)
            }
            val flags = viewModel.shownFlags
            if (flags.isNotEmpty()) {
                HorizontalDivider(color = palette["zinc-100"])
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    val dismissLabel = stringResource(R.string.orc_flag_dismiss)
                    flags.forEach { flag ->
                        val tone = when (MonthlyPlan.flagTone(flag.tone)) {
                            FlagTone.DANGER -> AlertTone.DANGER
                            FlagTone.WARNING -> AlertTone.WARNING
                            FlagTone.SUCCESS -> AlertTone.SUCCESS
                            FlagTone.INFO -> AlertTone.INFO
                        }
                        AlertMessage(MonthlyPlan.flagText(flag), tone, dismissLabel, onDismiss = { viewModel.dismissFlag(flag) })
                    }
                }
            }
            HorizontalDivider(color = palette["zinc-100"])
            Text(stringResource(R.string.orc_footnote), fontSize = 12.sp, color = palette.muted, modifier = Modifier.padding(16.dp))
        }
    }
}

@Composable
private fun PlanLevel(
    label: String,
    percent: BigDecimal?,
    amount: BigDecimal?,
    realized: String?,
    progress: BigDecimal?,
    status: BudgetStatus,
    footer: (@Composable () -> Unit)? = null,
) {
    val palette = LocalPalette.current
    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(verticalAlignment = Alignment.Bottom) {
            Text(
                "$label · ${MonthlyPlan.formatPlanPercent(percent)}",
                fontWeight = FontWeight.SemiBold,
                color = palette.text,
                modifier = Modifier.weight(1f),
            )
            Text(formatCurrency(amount), fontWeight = FontWeight.Bold, fontSize = 16.sp, color = palette.text)
        }
        if (realized != null) Text(realized, fontSize = 14.sp, color = palette["zinc-600"])
        if (progress != null) BudgetProgressBar(progress, status, Modifier.padding(top = 6.dp), height = 10)
        footer?.invoke()
    }
}

@Composable
private fun CategoriesPanel(data: MonthlyPlanDto, viewModel: OrcamentoViewModel, onOpenLink: (String) -> Unit) {
    val palette = LocalPalette.current
    val items = viewModel.items
    Panel {
        Column {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(stringResource(R.string.orc_categories_title), fontWeight = FontWeight.Bold, fontSize = 17.sp, color = palette.text)
                Text(stringResource(R.string.orc_categories_description, formatCurrency(viewModel.spendAmount)), fontSize = 13.sp, color = palette.muted)
            }
            HorizontalDivider(color = palette["zinc-100"])
            AddCategory(viewModel)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
                AppButton(stringResource(R.string.orc_copy_previous), viewModel::copyPrevious, variant = ButtonVariant.SECONDARY, loading = viewModel.busy)
                AppButton(stringResource(R.string.orc_manage_categories), { onOpenLink("/ajustes#categorias") }, variant = ButtonVariant.SUBTLE)
            }
            HorizontalDivider(color = palette["zinc-100"])
            if (items.isEmpty()) {
                EmptyState(stringResource(R.string.orc_no_categories_title), stringResource(R.string.orc_no_categories_message), Modifier.padding(16.dp))
            } else {
                items.forEachIndexed { index, item ->
                    if (index > 0) HorizontalDivider(color = palette["zinc-100"])
                    BudgetRow(item, viewModel)
                }
            }
            HorizontalDivider(color = palette["zinc-100"])
            val unassigned = data.categories?.unassigned
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(16.dp)) {
                Column(Modifier.weight(1f)) {
                    Text(stringResource(R.string.orc_unassigned), fontWeight = FontWeight.SemiBold, color = palette.text)
                    Text(stringResource(R.string.orc_unassigned_hint), fontSize = 13.sp, color = palette["zinc-600"])
                }
                val negative = (unassigned?.percent?.signum() ?: 0) < 0 || (unassigned?.amount?.signum() ?: 0) < 0
                Text(
                    "${MonthlyPlan.formatPlanPercent(unassigned?.percent)} · ${formatCurrency(unassigned?.amount)}",
                    fontSize = 14.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = if (negative) palette.loss else palette.text,
                )
            }
            val over = data.categories?.totals?.overCount ?: 0
            if (over > 0) {
                HorizontalDivider(color = palette["zinc-100"])
                Text(
                    if (over == 1) stringResource(R.string.orc_over_one) else stringResource(R.string.orc_over_many, over),
                    color = palette.loss,
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 14.sp,
                    modifier = Modifier.padding(16.dp),
                )
            }
        }
    }
}

@Composable
private fun AddCategory(viewModel: OrcamentoViewModel) {
    val palette = LocalPalette.current
    val form = viewModel.addForm
    val available = viewModel.availableCategories
    val room = viewModel.newCategoryRoom
    Column {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable(onClick = viewModel::toggleAdd).padding(horizontal = 16.dp),
        ) {
            Text(stringResource(R.string.orc_add_category), fontWeight = FontWeight.SemiBold, color = palette.text, modifier = Modifier.weight(1f))
            Icon(AppIcons.ChevronDown, null, tint = palette.muted, modifier = Modifier.size(18.dp).rotate(if (viewModel.addOpen) 180f else 0f))
        }
        if (viewModel.addOpen) {
            Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Field(stringResource(R.string.orc_category)) {
                    SelectField(
                        value = form.categoryId,
                        options = available.map { SelectOption(it.id, viewModel.categoryLabel(it)) },
                        onSelect = { viewModel.changeAdd(form.copy(categoryId = it)) },
                        placeholder = stringResource(R.string.orc_select),
                    )
                }
                PercentSlider(
                    label = stringResource(R.string.orc_percent_of_spend),
                    value = form.percent,
                    onChange = { viewModel.changeAdd(form.copy(percent = it)) },
                    room = room,
                    aside = amountPreview(viewModel.spendAmount, form.percent),
                    hint = stringResource(R.string.orc_free_room, MonthlyPlan.formatPlanPercent(room)),
                )
                Field(stringResource(R.string.orc_note), hint = stringResource(R.string.orc_optional)) {
                    AppTextField(form.note, { viewModel.changeAdd(form.copy(note = it)) })
                }
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.heightIn(min = 48.dp).clickable { viewModel.changeAdd(form.copy(rollover = !form.rollover)) }) {
                    Checkbox(
                        checked = form.rollover,
                        onCheckedChange = { viewModel.changeAdd(form.copy(rollover = it)) },
                        colors = CheckboxDefaults.colors(checkedColor = palette.accent, checkmarkColor = palette.onAccent),
                    )
                    Text(stringResource(R.string.orc_rollover), fontSize = 14.sp, color = palette["zinc-700"])
                }
                AppButton(
                    stringResource(R.string.orc_save),
                    viewModel::createBudget,
                    Modifier.fillMaxWidth(),
                    loading = viewModel.busy,
                    enabled = available.isNotEmpty() && form.categoryId.isNotEmpty(),
                )
                Text(
                    stringResource(if (available.isNotEmpty()) R.string.orc_add_help else R.string.orc_add_none_left),
                    fontSize = 13.sp,
                    color = palette["zinc-600"],
                )
            }
        }
    }
}

private fun amountPreview(spendAmount: BigDecimal?, percent: BigDecimal?): String =
    MonthlyPlan.categoryAmountPreview(spendAmount, percent)?.let { formatCurrency(it) } ?: "R$ —"

@Composable
private fun BudgetRow(item: PlanBudgetDto, viewModel: OrcamentoViewModel) {
    val palette = LocalPalette.current
    val status = BudgetStatus.of(item.status)
    val editing = viewModel.editingId == item.id
    val open = item.id in viewModel.openLines
    Column(Modifier.padding(start = 16.dp, end = 8.dp, top = 12.dp, bottom = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Column(Modifier.weight(1f)) {
                Text(viewModel.itemLabel(item), fontWeight = FontWeight.SemiBold, color = palette.text, maxLines = 1, overflow = TextOverflow.Ellipsis)
                val detail = if (item.needsIncome) {
                    val first = if (item.plannedPercent == null) stringResource(R.string.orc_before_amount, formatCurrency(item.legacyAmount))
                    else stringResource(R.string.orc_percent_of_spend_value, MonthlyPlan.formatPlanPercent(item.plannedPercent))
                    stringResource(R.string.orc_needs_income_line, first)
                } else {
                    "${MonthlyPlan.formatPlanPercent(item.plannedPercent)} · ${formatCurrency(item.plannedAmount)}"
                }
                Text(detail, fontSize = 14.sp, color = palette["zinc-600"])
            }
            Badge(
                status.label,
                when (status) {
                    BudgetStatus.OVER -> BadgeTone.DANGER
                    BudgetStatus.WARNING, BudgetStatus.NEEDS_INCOME -> BadgeTone.WARNING
                    BudgetStatus.OK -> BadgeTone.NEUTRAL
                },
            )
        }
        if (editing) {
            PercentSlider(
                label = stringResource(R.string.orc_percent_of_spend),
                value = viewModel.editValue,
                onChange = viewModel::changeEdit,
                room = viewModel.editRoom(item),
                aside = amountPreview(viewModel.spendAmount, viewModel.editValue),
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AppButton(stringResource(R.string.lanc_cancel), viewModel::cancelEdit, Modifier.weight(1f), ButtonVariant.SECONDARY)
                AppButton(stringResource(R.string.orc_save), { viewModel.saveEdit(item) }, Modifier.weight(1f), loading = viewModel.busy)
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.padding(end = 8.dp)) {
            BudgetProgressBar(item.percent, status, Modifier.weight(1f))
            Text(
                item.remaining?.let { formatCurrency(it) } ?: "—",
                fontWeight = FontWeight.SemiBold,
                fontSize = 14.sp,
                color = if ((item.remaining?.signum() ?: 0) < 0) palette.loss else palette["zinc-700"],
            )
        }
        val carry = item.carryover?.takeIf { it.signum() != 0 }
        Text(
            buildString {
                append(stringResource(R.string.orc_spent_value, formatCurrency(item.spent)))
                if (item.available != null) append(stringResource(R.string.orc_of_available, formatCurrency(item.available)))
                if (carry != null) append(stringResource(R.string.orc_carryover, formatCurrency(carry)))
            },
            fontSize = 14.sp,
            color = palette["zinc-600"],
        )
        if (!item.note.isNullOrEmpty()) Text(item.note, fontSize = 14.sp, color = palette["zinc-600"])
        Row(verticalAlignment = Alignment.CenterVertically) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.weight(1f).heightIn(min = 48.dp).clickable { viewModel.toggleLines(item) },
            ) {
                Icon(AppIcons.ChevronDown, null, tint = palette["zinc-700"], modifier = Modifier.size(16.dp).rotate(if (open) 180f else 0f))
                Text(
                    stringResource(if (open) R.string.orc_hide_lines else R.string.orc_show_lines),
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 14.sp,
                    color = palette["zinc-700"],
                    modifier = Modifier.padding(start = 4.dp),
                )
            }
            if (!editing) {
                Surface(
                    onClick = { viewModel.toggleRollover(item) },
                    shape = RoundedCornerShape(50),
                    color = if (item.rollover) palette["emerald-50"] else palette.surface,
                    border = BorderStroke(1.dp, if (item.rollover) palette.accent.copy(alpha = 0.35f) else palette.border),
                    modifier = Modifier.heightIn(min = 48.dp).padding(vertical = 4.dp),
                ) {
                    Box(contentAlignment = Alignment.Center, modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp)) {
                        Text(
                            stringResource(R.string.orc_rollover_pill),
                            fontSize = 12.sp,
                            fontWeight = FontWeight.SemiBold,
                            color = if (item.rollover) palette["emerald-700"] else palette["zinc-600"],
                        )
                    }
                }
                OverflowMenu(
                    actions = listOf(
                        MenuAction(stringResource(R.string.orc_edit_percent)) { viewModel.startEdit(item) },
                        MenuAction(stringResource(R.string.orc_remove_from_month)) { viewModel.askRemoveBudget(item) },
                    ),
                    label = stringResource(R.string.orc_budget_actions, item.categoryName.orEmpty()),
                )
            }
        }
        if (open) BudgetLinesBlock(item, viewModel)
    }
}

@Composable
private fun BudgetLinesBlock(item: PlanBudgetDto, viewModel: OrcamentoViewModel) {
    val palette = LocalPalette.current
    val load = viewModel.lines[item.id]
    val data = load?.value
    Column(Modifier.padding(end = 8.dp, bottom = 4.dp)) {
        when {
            data == null && load?.error?.isNotEmpty() == true || data == null && load?.offline == true && load.loaded ->
                AlertMessage(stringResource(R.string.orc_lines_failed), AlertTone.DANGER, stringResource(R.string.lanc_dismiss))
            data == null -> ListSkeleton(rows = 2)
            data.lines.isEmpty() -> Text(stringResource(R.string.orc_no_lines), fontSize = 14.sp, color = palette["zinc-600"])
            else -> {
                // Numa categoria de despesa o valor e saida; um estorno volta com "+".
                val sign = if (item.categoryKind == "INCOME") 1 else -1
                Surface(shape = RoundedCornerShape(16.dp), color = palette.background, border = BorderStroke(1.dp, palette.border)) {
                    Column {
                        data.lines.forEachIndexed { index, line ->
                            if (index > 0) HorizontalDivider(color = palette["zinc-100"])
                            LineRow(line, item, sign)
                        }
                    }
                }
                Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 6.dp)) {
                    Text(stringResource(R.string.orc_lines_count, data.lines.size), fontSize = 12.sp, color = palette["zinc-600"], modifier = Modifier.weight(1f))
                    Text(stringResource(R.string.orc_lines_total, formatCurrency(data.spent)), fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = palette["zinc-600"])
                }
            }
        }
    }
}

@Composable
private fun LineRow(line: BudgetLineDto, item: PlanBudgetDto, sign: Int) {
    val palette = LocalPalette.current
    Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp)) {
        Column(Modifier.weight(1f)) {
            Text(line.description?.takeIf { it.isNotEmpty() } ?: line.category.orEmpty(), fontSize = 14.sp, fontWeight = FontWeight.Medium, color = palette.text, maxLines = 1, overflow = TextOverflow.Ellipsis)
            val parts = mutableListOf(formatDateBR(line.date))
            if (line.source == "CARD") {
                parts += buildString {
                    append(line.cardName?.takeIf { it.isNotEmpty() } ?: stringResource(R.string.orc_card))
                    if ((line.installments ?: 0) > 1) append(" · ${line.installments}x")
                    if (line.refund) append(" · estorno")
                }
            } else if (!line.accountName.isNullOrEmpty()) {
                parts += line.accountName
            }
            if (line.subcategory && line.category != item.categoryName) parts += line.category.orEmpty()
            if (line.shared) parts += stringResource(R.string.orc_your_part_of, formatCurrency(line.totalAmount))
            Text(parts.joinToString(" · "), fontSize = 12.sp, color = palette["zinc-600"])
        }
        val amount = line.amount ?: BigDecimal.ZERO
        Text(formatSignedCurrency(amount, amount.signum() * sign), fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = palette["zinc-800"])
    }
}

@Composable
private fun PlanSheet(viewModel: OrcamentoViewModel) {
    val palette = LocalPalette.current
    val form = viewModel.sheet ?: return
    val sheetState = rememberModalBottomSheetState(
        skipPartiallyExpanded = true,
        confirmValueChange = { value -> value != SheetValue.Hidden || !viewModel.sheetBusy },
    )
    val totals = viewModel.totals(form)
    val needsIncome = viewModel.needsIncome
    val ownPlan = viewModel.row?.let { !it.inherited } == true
    AppSheet(
        title = stringResource(R.string.orc_sheet_title),
        sheetState = sheetState,
        onDismiss = viewModel::closeSheet,
        footer = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                AppButton(
                    stringResource(R.string.orc_save_plan),
                    viewModel::savePlan,
                    Modifier.fillMaxWidth(),
                    loading = viewModel.sheetBusy,
                    enabled = totals.blocked == null,
                )
                if (ownPlan) {
                    AppButton(stringResource(R.string.orc_remove_this_month), viewModel::askRemovePlan, Modifier.fillMaxWidth(), ButtonVariant.SUBTLE, enabled = !viewModel.sheetBusy)
                }
            }
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text(stringResource(R.string.orc_sheet_description, monthLabel(viewModel.month)), fontSize = 14.sp, color = palette["zinc-600"])
            if (needsIncome) {
                val legacy = viewModel.row?.legacy
                AlertMessage(
                    stringResource(R.string.orc_sheet_legacy, formatCurrency(legacy?.investAmount), formatCurrency(legacy?.spendAmount)),
                    AlertTone.WARNING,
                    stringResource(R.string.lanc_dismiss),
                )
            }
            AlertMessage(viewModel.sheetError, AlertTone.DANGER, stringResource(R.string.lanc_dismiss))
            Field(stringResource(R.string.orc_income_field)) {
                AmountInput(form.income, { viewModel.changeSheet(form.copy(income = it)) }, stringResource(R.string.orc_income_field))
            }
            val blankHint = stringResource(R.string.orc_blank_converts)
            PercentSlider(
                label = stringResource(R.string.orc_invest_field),
                value = form.invest,
                onChange = { viewModel.changeSheet(form.copy(invest = it)) },
                room = MonthlyPlan.percentRoom(form.spend),
                aside = totals.investAmount?.let { formatCurrency(it) } ?: "R$ —",
                hint = if (needsIncome && form.invest == null) blankHint else null,
            )
            PercentSlider(
                label = stringResource(R.string.orc_spend_field),
                value = form.spend,
                onChange = { viewModel.changeSheet(form.copy(spend = it)) },
                room = MonthlyPlan.percentRoom(form.invest),
                aside = totals.spendAmount?.let { formatCurrency(it) } ?: "R$ —",
                hint = if (needsIncome && form.spend == null) blankHint else null,
            )
            if (needsIncome && (form.invest != null || form.spend != null)) {
                AppButton(stringResource(R.string.orc_convert_old), { viewModel.changeSheet(form.copy(invest = null, spend = null)) }, variant = ButtonVariant.SUBTLE)
            }
            Surface(shape = RoundedCornerShape(16.dp), color = palette.background) {
                Text(
                    MonthlyPlan.livePlanText(totals),
                    fontSize = 14.sp,
                    fontWeight = if (totals.over) FontWeight.SemiBold else FontWeight.Normal,
                    color = if (totals.over) palette.loss else palette["zinc-700"],
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp),
                )
            }
            if (totals.blocked != null && totals.blocked != viewModel.sheetError) {
                Text(totals.blocked, fontSize = 14.sp, color = palette["zinc-600"])
            }
        }
    }
}
