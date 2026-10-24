package br.financas.app.ui.metas

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.SheetValue
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.core.formatCurrency
import br.financas.app.core.formatPercent
import br.financas.app.core.monthLabel
import br.financas.app.data.GoalDto
import br.financas.app.rules.BudgetStatus
import br.financas.app.rules.Goals
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AlertTone
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.AppSheet
import br.financas.app.ui.components.AppTextField
import br.financas.app.ui.components.Badge
import br.financas.app.ui.components.BadgeTone
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
import br.financas.app.ui.lancamentos.AmountInput
import br.financas.app.ui.lancamentos.moneyOrMasked
import br.financas.app.ui.planejar.BudgetProgressBar
import br.financas.app.ui.planejar.PlanejarScaffold
import br.financas.app.ui.planejar.PlanejarTab
import br.financas.app.ui.planejar.PlanejarTopBar
import br.financas.app.ui.theme.LocalPalette
import java.math.BigDecimal

/** Metas nativo (10-metas.md): pages/Metas.jsx e o GoalSheet em Compose. */
@Composable
fun MetasScreen(viewModel: MetasViewModel, onBack: () -> Unit, onTab: (PlanejarTab) -> Unit) {
    val palette = LocalPalette.current
    val dismiss = stringResource(R.string.lanc_dismiss)
    PlanejarScaffold(
        notices = viewModel.notices,
        onRefresh = viewModel::refreshAll,
        topBar = {
            PlanejarTopBar(stringResource(R.string.metas_title), PlanejarTab.METAS, viewModel.hidden, onBack, viewModel::toggleHidden, onTab)
        },
    ) {
        item(key = "intro") {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(stringResource(R.string.metas_description), fontSize = 14.sp, color = palette["zinc-600"])
                AppButton(stringResource(R.string.metas_new), viewModel::openNew, Modifier.fillMaxWidth())
            }
        }
        item(key = "alerts") {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                // Os valores sao os da ultima leitura: sem conexao, o aviso diz de quando.
                if (viewModel.goals.offline) AlertMessage(viewModel.goals.offlineText, AlertTone.WARNING, dismiss)
                AlertMessage(viewModel.goals.error, AlertTone.DANGER, dismiss)
                AlertMessage(viewModel.actionError, AlertTone.DANGER, dismiss, onDismiss = viewModel::dismissActionError)
            }
        }
        val goals = viewModel.goals.value
        when {
            goals == null && !viewModel.goals.loaded -> item(key = "loading") { Panel { ListSkeleton(rows = 3, modifier = Modifier.padding(16.dp)) } }
            goals == null -> Unit
            goals.isEmpty() -> item(key = "empty") { EmptyState(stringResource(R.string.metas_empty_title), stringResource(R.string.metas_empty_message)) }
            else -> goals.forEach { goal -> item(key = goal.id) { GoalCard(goal, viewModel) } }
        }
    }
    viewModel.sheet?.let { GoalSheetView(it, viewModel) }
    ConfirmDialog(viewModel.confirm, stringResource(R.string.lanc_cancel), viewModel::dismissConfirm)
}

@Composable
private fun GoalCard(goal: GoalDto, viewModel: MetasViewModel) {
    val palette = LocalPalette.current
    val hidden = viewModel.hidden
    val income = goal.kind == Goals.INCOME
    Panel {
        Column(Modifier.padding(start = 16.dp, end = 8.dp, top = 12.dp, bottom = 16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Column(Modifier.weight(1f)) {
                    Text(goal.name, fontWeight = FontWeight.Bold, fontSize = 17.sp, color = palette.text, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    val subtitle = goal.kindLabel.orEmpty() + (goal.assetClass?.let { " · ${Goals.classLabel(it)}" } ?: "")
                    Text(subtitle, fontSize = 14.sp, color = palette.muted)
                }
                Goals.badge(goal.reached, goal.onTrack)?.let { badge ->
                    Badge(
                        badge.label,
                        when (badge.tone) {
                            Goals.BadgeTone.SUCCESS -> BadgeTone.SUCCESS
                            Goals.BadgeTone.WARNING -> BadgeTone.WARNING
                            Goals.BadgeTone.NEUTRAL -> BadgeTone.NEUTRAL
                        },
                    )
                }
                OverflowMenu(
                    actions = listOf(
                        MenuAction(stringResource(R.string.metas_edit)) { viewModel.openEdit(goal) },
                        MenuAction(stringResource(R.string.orc_remove)) { viewModel.askRemove(goal) },
                    ),
                    label = stringResource(R.string.metas_actions, goal.name),
                )
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.padding(end = 8.dp)) {
                BudgetProgressBar(goal.percent, BudgetStatus.OK, Modifier.weight(1f))
                val percent = (goal.percent ?: BigDecimal.ZERO).min(BigDecimal(999))
                Text(formatPercent(percent, 1), fontWeight = FontWeight.SemiBold, fontSize = 14.sp, color = palette["zinc-700"], textAlign = TextAlign.End, modifier = Modifier.width(64.dp))
            }
            Column(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(end = 8.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Figure(stringResource(R.string.metas_current), moneyOrMasked(goal.current, hidden), null, Modifier.weight(1f))
                    Figure(stringResource(R.string.metas_remaining), moneyOrMasked(goal.remaining, hidden), null, Modifier.weight(1f))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Figure(stringResource(R.string.metas_target), moneyOrMasked(goal.targetAmount, hidden), null, Modifier.weight(1f))
                    if (income) {
                        Figure(stringResource(R.string.metas_income_12), formatCurrency(goal.incomeLast12Months), null, Modifier.weight(1f))
                    } else {
                        Figure(
                            stringResource(R.string.metas_forecast),
                            Goals.forecastText(goal.reached, goal.kind, goal.estimatedMonth),
                            Goals.forecastHint(goal.reached, goal.kind, goal.estimatedMonth, goal.estimatedMonths).ifEmpty { null },
                            Modifier.weight(1f),
                        )
                    }
                }
            }
            if (!income) {
                val rate = goal.annualReturnPercent?.let { stringResource(R.string.metas_rate, formatPercent(it, 1)) } ?: stringResource(R.string.metas_no_rate)
                val needed = if (!goal.targetMonth.isNullOrEmpty() && !goal.reached && goal.requiredContribution != null) {
                    stringResource(R.string.metas_needed, monthLabel(goal.targetMonth), formatCurrency(goal.requiredContribution))
                } else {
                    "."
                }
                Text(
                    stringResource(R.string.metas_contribution, formatCurrency(goal.monthlyContribution)) + rate + needed,
                    fontSize = 14.sp,
                    color = palette["zinc-600"],
                    modifier = Modifier.padding(end = 8.dp),
                )
            }
        }
    }
}

@Composable
private fun Figure(label: String, value: String, hint: String?, modifier: Modifier) {
    val palette = LocalPalette.current
    Surface(shape = RoundedCornerShape(16.dp), color = palette.background, modifier = modifier) {
        Column(Modifier.padding(horizontal = 12.dp, vertical = 10.dp)) {
            Text(label, fontSize = 12.sp, fontWeight = FontWeight.Medium, color = palette.muted)
            Text(value, fontWeight = FontWeight.SemiBold, color = palette.text)
            if (hint != null) Text(hint, fontSize = 12.sp, color = palette.muted)
        }
    }
}

@Composable
private fun GoalSheetView(sheet: GoalSheet, viewModel: MetasViewModel) {
    val palette = LocalPalette.current
    val form = sheet.form
    val income = form.kind == Goals.INCOME
    val sheetState = rememberModalBottomSheetState(
        skipPartiallyExpanded = true,
        confirmValueChange = { value -> value != SheetValue.Hidden || !viewModel.sheetBusy },
    )
    AppSheet(
        title = stringResource(if (sheet.goal == null) R.string.metas_new else R.string.metas_edit_title),
        sheetState = sheetState,
        onDismiss = viewModel::closeSheet,
        footer = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AppButton(stringResource(R.string.lanc_cancel), viewModel::closeSheet, Modifier.weight(1f), ButtonVariant.SECONDARY, enabled = !viewModel.sheetBusy)
                AppButton(
                    stringResource(if (sheet.goal == null) R.string.metas_create else R.string.orc_save),
                    viewModel::save,
                    Modifier.weight(1f),
                    loading = viewModel.sheetBusy,
                )
            }
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text(
                stringResource(
                    when (form.kind) {
                        "PORTFOLIO" -> R.string.metas_hint_portfolio
                        "ASSET_CLASS" -> R.string.metas_hint_class
                        Goals.INCOME -> R.string.metas_hint_income
                        else -> R.string.metas_hint_net_worth
                    },
                ),
                fontSize = 14.sp,
                color = palette["zinc-600"],
            )
            AlertMessage(viewModel.sheetError, AlertTone.DANGER, stringResource(R.string.lanc_dismiss))
            SegmentedChoice(
                items = listOf(
                    SelectOption("NET_WORTH", stringResource(R.string.metas_kind_net_worth)),
                    SelectOption("PORTFOLIO", stringResource(R.string.metas_kind_portfolio)),
                    SelectOption("ASSET_CLASS", stringResource(R.string.metas_kind_class)),
                    SelectOption(Goals.INCOME, stringResource(R.string.metas_kind_income)),
                ),
                value = form.kind,
                onChange = { viewModel.changeForm(form.copy(kind = it)) },
            )
            Field(stringResource(R.string.metas_name)) {
                AppTextField(form.name, { viewModel.changeForm(form.copy(name = it.take(120))) }, placeholder = stringResource(R.string.metas_name_placeholder))
            }
            if (form.kind == Goals.ASSET_CLASS) {
                Field(stringResource(R.string.metas_class)) {
                    SelectField(
                        value = form.assetClass,
                        options = Goals.CLASSES.map { SelectOption(it, Goals.classLabel(it)) },
                        onSelect = { viewModel.changeForm(form.copy(assetClass = it)) },
                    )
                }
            }
            val targetLabel = stringResource(if (income) R.string.metas_target_income else R.string.metas_target_amount)
            Field(targetLabel) {
                AmountInput(form.targetAmount, { viewModel.changeForm(form.copy(targetAmount = it)) }, targetLabel, autoFocus = sheet.goal == null)
            }
            if (!income) {
                val contribution = stringResource(R.string.metas_contribution_field)
                Field(contribution, hint = stringResource(R.string.metas_contribution_hint)) {
                    AppTextField(form.monthlyContribution, { viewModel.changeForm(form.copy(monthlyContribution = it)) }, placeholder = "0,00", keyboardType = KeyboardType.Decimal, contentDescription = contribution)
                }
                val rate = stringResource(R.string.metas_rate_field)
                Field(rate, hint = stringResource(R.string.metas_rate_hint)) {
                    // A rentabilidade pode ser negativa: o teclado de texto tem o "-".
                    AppTextField(form.annualReturnPercent, { viewModel.changeForm(form.copy(annualReturnPercent = it)) }, placeholder = stringResource(R.string.metas_rate_placeholder), keyboardType = KeyboardType.Text, contentDescription = rate)
                }
                Field(stringResource(R.string.metas_date_field), hint = stringResource(R.string.metas_date_hint)) {
                    DateField(
                        form.targetDate,
                        { viewModel.changeForm(form.copy(targetDate = it)) },
                        stringResource(R.string.lanc_date_ok),
                        stringResource(R.string.lanc_cancel),
                        placeholder = stringResource(R.string.metas_date_placeholder),
                        clearLabel = stringResource(R.string.metas_date_clear),
                        onClear = { viewModel.changeForm(form.copy(targetDate = "")) },
                    )
                }
            }
        }
    }
}
