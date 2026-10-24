package br.financas.app.ui.recorrentes

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.core.formatCurrency
import br.financas.app.core.formatDateBR
import br.financas.app.core.formatSignedCurrency
import br.financas.app.data.RecurringDto
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AlertTone
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.AppIcons
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
import br.financas.app.ui.planejar.PlanejarScaffold
import br.financas.app.ui.planejar.PlanejarTab
import br.financas.app.ui.planejar.PlanejarTopBar
import br.financas.app.ui.planejar.SummaryPanel
import br.financas.app.ui.planejar.SummaryValue
import br.financas.app.ui.theme.LocalPalette
import java.math.BigDecimal

/** Recorrentes nativo (09-recorrentes.md): pages/Recorrentes.jsx em Compose. */
@Composable
fun RecorrentesScreen(viewModel: RecorrentesViewModel, onBack: () -> Unit, onTab: (PlanejarTab) -> Unit) {
    val palette = LocalPalette.current
    val dismiss = stringResource(R.string.lanc_dismiss)
    PlanejarScaffold(
        notices = viewModel.notices,
        onRefresh = viewModel::refreshAll,
        topBar = {
            PlanejarTopBar(stringResource(R.string.rec_title), PlanejarTab.RECORRENTES, viewModel.hidden, onBack, viewModel::toggleHidden, onTab)
        },
    ) {
        item(key = "intro") {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(stringResource(R.string.rec_description), fontSize = 14.sp, color = palette["zinc-600"])
                val pending = viewModel.pendingCount
                AppButton(
                    if (pending > 0) stringResource(R.string.rec_run_n, pending) else stringResource(R.string.rec_run),
                    viewModel::run,
                    Modifier.fillMaxWidth(),
                    loading = viewModel.busy,
                )
            }
        }
        item(key = "alerts") {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (viewModel.list.offline) AlertMessage(viewModel.list.offlineText, AlertTone.WARNING, dismiss)
                AlertMessage(viewModel.list.error, AlertTone.DANGER, dismiss)
                AlertMessage(viewModel.actionError, AlertTone.DANGER, dismiss, onDismiss = viewModel::dismissActionError)
            }
        }
        item(key = "summary") { Summary(viewModel) }
        item(key = "list") { ListPanel(viewModel) }
        item(key = "forecast") { ForecastPanel(viewModel) }
    }
    ConfirmDialog(viewModel.confirm, stringResource(R.string.lanc_cancel), viewModel::dismissConfirm)
}

@Composable
private fun Summary(viewModel: RecorrentesViewModel) {
    val forecast = viewModel.forecast.value
    if (forecast == null) {
        Panel { ListSkeleton(rows = 2, modifier = Modifier.padding(16.dp)) }
        return
    }
    val window30 = forecast.windows["30"]
    val window90 = forecast.windows["90"]
    val pending = viewModel.pendingCount
    SummaryPanel(
        lead = SummaryValue(
            stringResource(R.string.rec_net_30),
            formatSignedCurrency(window30?.net),
            if (window90 != null) stringResource(R.string.rec_in_90, formatSignedCurrency(window90.net)) else stringResource(R.string.rec_active_hint),
            loss = (window30?.net?.signum() ?: 0) < 0,
        ),
        figures = listOf(
            SummaryValue(stringResource(R.string.rec_income_30), formatCurrency(window30?.income), stringResource(R.string.rec_next_30)),
            SummaryValue(stringResource(R.string.rec_expense_30), formatCurrency(window30?.expense), stringResource(R.string.rec_next_30)),
            SummaryValue(
                stringResource(R.string.rec_pending),
                pending.toString(),
                stringResource(if (pending > 0) R.string.rec_pending_hint else R.string.rec_all_set),
                muted = pending == 0,
            ),
        ),
    )
}

@Composable
private fun ListPanel(viewModel: RecorrentesViewModel) {
    val palette = LocalPalette.current
    Panel {
        Column {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(stringResource(R.string.rec_list_title), fontWeight = FontWeight.Bold, fontSize = 17.sp, color = palette.text)
                Text(stringResource(R.string.rec_list_description), fontSize = 13.sp, color = palette.muted)
            }
            HorizontalDivider(color = palette["zinc-100"])
            NewForm(viewModel)
            HorizontalDivider(color = palette["zinc-100"])
            val items = viewModel.items
            when {
                viewModel.list.value == null && !viewModel.list.loaded -> ListSkeleton(rows = 5, modifier = Modifier.padding(16.dp))
                items.isEmpty() && viewModel.list.value != null ->
                    EmptyState(stringResource(R.string.rec_empty_title), stringResource(R.string.rec_empty_message), Modifier.padding(16.dp))
                else -> items.forEachIndexed { index, item ->
                    if (index > 0) HorizontalDivider(color = palette["zinc-100"])
                    RecurringRow(item, viewModel)
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun RecurringRow(item: RecurringDto, viewModel: RecorrentesViewModel) {
    val palette = LocalPalette.current
    val editing = viewModel.edit?.takeIf { it.id == item.id }
    Column(Modifier.padding(start = 16.dp, end = 8.dp, top = 12.dp, bottom = 12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(
                        viewModel.title(item),
                        fontWeight = FontWeight.SemiBold,
                        color = if (item.status == "FINISHED") palette.muted else palette.text,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Badge(
                        when (item.status) {
                            "PAUSED" -> stringResource(R.string.rec_status_paused)
                            "FINISHED" -> stringResource(R.string.rec_status_finished)
                            "ACTIVE" -> stringResource(R.string.rec_status_active)
                            else -> item.status
                        },
                    )
                    if (item.pendingCount > 0) Badge(stringResource(R.string.rec_pending_badge, item.pendingCount), BadgeTone.WARNING)
                }
                Text(viewModel.detail(item), fontSize = 14.sp, color = palette["zinc-600"])
            }
            if (editing == null) {
                Text(
                    formatSignedCurrency(item.amount, if (item.type == "INCOME") 1 else -1),
                    fontWeight = FontWeight.SemiBold,
                    color = if (item.type == "INCOME") palette["emerald-700"] else palette.text,
                )
                OverflowMenu(
                    actions = listOf(
                        MenuAction(stringResource(R.string.rec_edit)) { viewModel.startEdit(item) },
                        MenuAction(stringResource(if (item.active) R.string.rec_pause else R.string.rec_resume)) { viewModel.toggleActive(item) },
                        MenuAction(stringResource(R.string.rec_delete)) { viewModel.askDelete(item) },
                    ),
                    label = stringResource(R.string.rec_actions, viewModel.title(item)),
                )
            }
        }
        if (editing != null) {
            Field(stringResource(R.string.rec_amount)) {
                AmountInput(editing.amount, { viewModel.changeEdit(editing.copy(amount = it)) }, stringResource(R.string.rec_amount))
            }
            Field(stringResource(R.string.rec_account)) {
                val options = viewModel.accountOptions(item)
                SelectField(
                    value = editing.accountId,
                    options = options.map { SelectOption(it.id, it.label) },
                    // Uma conta arquivada aparece so como a atual: nao se escolhe de volta.
                    onSelect = { id -> if (options.firstOrNull { it.id == id }?.disabled != true) viewModel.changeEdit(editing.copy(accountId = id)) },
                    placeholder = if (editing.accountId.isEmpty()) stringResource(R.string.rec_default_account) else null,
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(end = 8.dp)) {
                AppButton(stringResource(R.string.lanc_cancel), viewModel::cancelEdit, Modifier.weight(1f), ButtonVariant.SECONDARY)
                AppButton(stringResource(R.string.rec_save_amount), { viewModel.saveEdit(item) }, Modifier.weight(1f), loading = viewModel.busy)
            }
        }
    }
}

@Composable
private fun NewForm(viewModel: RecorrentesViewModel) {
    val palette = LocalPalette.current
    val form = viewModel.form
    Column {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable(onClick = viewModel::toggleForm).padding(horizontal = 16.dp),
        ) {
            Text(stringResource(R.string.rec_new), fontWeight = FontWeight.SemiBold, color = palette.text, modifier = Modifier.weight(1f))
            Icon(AppIcons.ChevronDown, null, tint = palette.muted, modifier = Modifier.size(18.dp).rotate(if (viewModel.formOpen) 180f else 0f))
        }
        if (!viewModel.formOpen) return
        Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(stringResource(R.string.rec_new_intro), fontSize = 14.sp, color = palette["zinc-600"])
            Field(stringResource(R.string.rec_description_field)) {
                AppTextField(form.description, { viewModel.changeForm(form.copy(description = it)) }, placeholder = stringResource(R.string.rec_description_placeholder))
            }
            Field(stringResource(R.string.rec_amount)) {
                AmountInput(form.amount, { viewModel.changeForm(form.copy(amount = it)) }, stringResource(R.string.rec_amount), autoFocus = false)
            }
            Field(stringResource(R.string.rec_type)) {
                SegmentedChoice(
                    items = listOf(SelectOption("EXPENSE", stringResource(R.string.rec_type_expense)), SelectOption("INCOME", stringResource(R.string.rec_type_income))),
                    value = form.type,
                    onChange = { viewModel.changeForm(form.copy(type = it)) },
                )
            }
            Field(stringResource(R.string.rec_category)) {
                SelectField(
                    value = form.categoryId,
                    options = viewModel.categories.map { SelectOption(it.id, viewModel.categoryLabel(it)) },
                    onSelect = { viewModel.changeForm(form.copy(categoryId = it)) },
                    placeholder = stringResource(R.string.orc_select),
                )
            }
            Field(stringResource(R.string.rec_account), hint = stringResource(R.string.rec_account_hint)) {
                SelectField(
                    value = form.accountId,
                    options = viewModel.accounts.map { SelectOption(it.id, it.name) },
                    onSelect = { viewModel.changeForm(form.copy(accountId = it)) },
                    placeholder = stringResource(R.string.rec_default_account),
                )
            }
            Field(stringResource(R.string.rec_frequency)) {
                SegmentedChoice(
                    items = listOf(
                        SelectOption("MONTHLY", stringResource(R.string.rec_monthly)),
                        SelectOption("WEEKLY", stringResource(R.string.rec_weekly)),
                        SelectOption("YEARLY", stringResource(R.string.rec_yearly)),
                    ),
                    value = form.frequency,
                    onChange = { viewModel.changeForm(form.copy(frequency = it)) },
                )
            }
            Field(stringResource(R.string.rec_every), hint = stringResource(R.string.rec_every_hint)) {
                AppTextField(form.intervalCount, { viewModel.changeForm(form.copy(intervalCount = it.filter(Char::isDigit).take(2))) }, keyboardType = KeyboardType.Number)
            }
            val ok = stringResource(R.string.lanc_date_ok)
            val cancel = stringResource(R.string.lanc_cancel)
            Field(stringResource(R.string.rec_start), hint = stringResource(R.string.rec_start_hint)) {
                DateField(form.startDate, { viewModel.changeForm(form.copy(startDate = it)) }, ok, cancel)
            }
            Field(stringResource(R.string.rec_end), hint = stringResource(R.string.rec_end_hint)) {
                DateField(
                    form.endDate,
                    { viewModel.changeForm(form.copy(endDate = it)) },
                    ok,
                    cancel,
                    placeholder = stringResource(R.string.rec_end_placeholder),
                    clearLabel = stringResource(R.string.rec_end_clear),
                    onClear = { viewModel.changeForm(form.copy(endDate = "")) },
                )
            }
            AppButton(stringResource(R.string.orc_save), viewModel::create, Modifier.fillMaxWidth(), loading = viewModel.busy)
        }
    }
}

@Composable
private fun ForecastPanel(viewModel: RecorrentesViewModel) {
    val palette = LocalPalette.current
    val forecast = viewModel.forecast.value
    Panel {
        Column {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(stringResource(R.string.rec_forecast_title), fontWeight = FontWeight.Bold, fontSize = 17.sp, color = palette.text)
                Text(stringResource(R.string.rec_forecast_description), fontSize = 13.sp, color = palette.muted)
            }
            HorizontalDivider(color = palette["zinc-100"])
            val occurrences = forecast?.occurrences.orEmpty()
            when {
                forecast == null -> ListSkeleton(rows = 3, modifier = Modifier.padding(16.dp))
                occurrences.isEmpty() -> EmptyState(stringResource(R.string.rec_forecast_empty_title), stringResource(R.string.rec_forecast_empty_message), Modifier.padding(16.dp))
                else -> occurrences.forEachIndexed { index, occurrence ->
                    if (index > 0) HorizontalDivider(color = palette["zinc-100"])
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        modifier = Modifier.heightIn(min = 48.dp).padding(horizontal = 16.dp, vertical = 10.dp),
                    ) {
                        Text(formatDateBR(occurrence.date), fontSize = 13.sp, color = palette["zinc-600"])
                        Text(
                            occurrence.description?.takeIf { it.isNotEmpty() } ?: occurrence.category.orEmpty(),
                            fontSize = 14.sp,
                            color = palette.text,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.weight(1f),
                        )
                        if (occurrence.pending) Badge(stringResource(R.string.rec_overdue), BadgeTone.WARNING)
                        val income = occurrence.type == "INCOME"
                        Text(
                            formatSignedCurrency(occurrence.amount ?: BigDecimal.ZERO, if (income) 1 else -1),
                            fontSize = 14.sp,
                            fontWeight = FontWeight.SemiBold,
                            color = if (income) palette["emerald-700"] else palette.text,
                        )
                    }
                }
            }
        }
    }
}
