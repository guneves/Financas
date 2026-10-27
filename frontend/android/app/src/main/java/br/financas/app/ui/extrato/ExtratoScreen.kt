package br.financas.app.ui.extrato

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.Icon
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Snackbar
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import br.financas.app.R
import br.financas.app.core.formatSignedCurrency
import br.financas.app.data.TransactionDto
import br.financas.app.data.storedTimeLabel
import br.financas.app.rules.ExtratoRules
import br.financas.app.rules.ReviewRules
import br.financas.app.rules.InvestmentStatement
import br.financas.app.rules.Sharing
import br.financas.app.rules.SharedRow
import br.financas.app.rules.StatementEntry
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
import br.financas.app.ui.components.FitText
import br.financas.app.ui.components.ListSkeleton
import br.financas.app.ui.components.MenuAction
import br.financas.app.ui.components.OverflowMenu
import br.financas.app.ui.components.Panel
import br.financas.app.ui.components.SegmentedChoice
import br.financas.app.ui.components.SelectField
import br.financas.app.ui.components.SelectOption
import br.financas.app.ui.home.HomeLogic
import br.financas.app.ui.lancamentos.AttachmentsSheet
import br.financas.app.ui.lancamentos.LancamentosTab
import br.financas.app.ui.lancamentos.LancamentosTopBar
import br.financas.app.ui.lancamentos.ProjectionHeader
import br.financas.app.ui.lancamentos.moneyOrMasked
import br.financas.app.ui.theme.LocalPalette
import kotlinx.coroutines.flow.distinctUntilChanged
import java.time.LocalDate

/**
 * O Extrato nativo (04-extrato.md): pages/lancamentos/Extrato.jsx e ExtratoInvestimentos.jsx em
 * Compose. [onTab] troca de aba de Lancamentos (uma compra no cartao abre Cartoes); [onOpenWeb]
 * abre uma tela ainda React. No alto de Contas, Revisar e o que nao gravou sozinho (ReviewSection).
 */
@Composable
fun ExtratoScreen(
    viewModel: ExtratoViewModel,
    onBack: () -> Unit,
    onTab: (LancamentosTab) -> Unit,
    onOpenWeb: (String) -> Unit,
    onNewEntry: () -> Unit,
) {
    val palette = LocalPalette.current
    val snackbar = remember { SnackbarHostState() }
    val haptic = LocalHapticFeedback.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val listState = rememberLazyListState()

    LaunchedEffect(lifecycleOwner) {
        lifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) { viewModel.refreshAll() }
    }
    LaunchedEffect(Unit) {
        viewModel.notices.collect { message ->
            haptic.performHapticFeedback(HapticFeedbackType.LongPress)
            snackbar.showSnackbar(message)
        }
    }
    // Rolou ate perto do fim: a pagina seguinte (no lugar do "Mostrar mais").
    val nearEnd by remember {
        derivedStateOf {
            val info = listState.layoutInfo
            val last = info.visibleItemsInfo.lastOrNull()?.index ?: 0
            info.totalItemsCount > 0 && last >= info.totalItemsCount - 6
        }
    }
    LaunchedEffect(listState) {
        snapshotFlow { nearEnd }.distinctUntilChanged().collect { if (it && viewModel.view == ExtratoMemory.VIEW_CONTAS) viewModel.loadMore() }
    }

    Scaffold(
        containerColor = palette.background,
        snackbarHost = {
            SnackbarHost(snackbar) { data ->
                Snackbar(snackbarData = data, containerColor = palette["zinc-900"], contentColor = palette["zinc-50"])
            }
        },
        topBar = {
            LancamentosTopBar(
                title = stringResource(R.string.extrato_title),
                current = LancamentosTab.EXTRATO,
                hidden = viewModel.hidden,
                onBack = onBack,
                onToggleHidden = viewModel::toggleHidden,
                onTab = onTab,
            )
        },
    ) { padding ->
        LazyColumn(
            state = listState,
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 32.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item(key = "view") {
                SegmentedChoice(
                    items = listOf(
                        SelectOption(ExtratoMemory.VIEW_CONTAS, stringResource(R.string.extrato_view_contas)),
                        SelectOption(ExtratoMemory.VIEW_INVESTIMENTOS, stringResource(R.string.extrato_view_investimentos)),
                    ),
                    value = viewModel.view,
                    onChange = viewModel::chooseView,
                )
            }
            if (viewModel.view == ExtratoMemory.VIEW_INVESTIMENTOS) {
                investmentsView(viewModel, onOpenWeb)
            } else {
                contasView(viewModel, onTab, onNewEntry)
            }
        }
    }

    viewModel.editing?.let { row -> viewModel.editForm?.let { form -> EditTransactionSheet(row, form, viewModel) } }
    AttachmentsSheet(viewModel.attachments)
    if (viewModel.exportOpen) ExportSheet(viewModel)
    ConfirmDialog(request = viewModel.confirm, cancelLabel = stringResource(R.string.lanc_cancel), onDismiss = viewModel::dismissConfirm)
}

// ---- Contas ----

@OptIn(ExperimentalFoundationApi::class)
private fun LazyListScope.contasView(viewModel: ExtratoViewModel, onTab: (LancamentosTab) -> Unit, onNewEntry: () -> Unit) {
    item(key = "intro") {
        val palette = LocalPalette.current
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(stringResource(R.string.extrato_description), color = palette.muted, fontSize = 14.sp, modifier = Modifier.weight(1f))
            AppButton(
                text = stringResource(R.string.extrato_export),
                onClick = viewModel::openExport,
                variant = ButtonVariant.SECONDARY,
                enabled = viewModel.statementRows.isNotEmpty(),
            )
        }
    }
    item(key = "alerts") { ContasAlerts(viewModel) }
    // Gravar sozinho e revisar (045): o unico trabalho do dono, no alto.
    item(key = "review") { ReviewPanel(viewModel) }
    item(key = "waiting") { WaitingPanel(viewModel) }
    item(key = "header") {
        val header = viewModel.header
        if (header != null) {
            ProjectionHeader(header.first, header.second, header.third, viewModel.hidden, estimated = viewModel.balanceEstimated)
        }
    }
    item(key = "panel") { StatementPanelHeader(viewModel) }
    item(key = "filters") { FiltersBlock(viewModel) }

    val rows = viewModel.rows
    val shown = viewModel.statementRows
    when {
        rows == null || (viewModel.filtering && viewModel.filtersActive && shown.isEmpty()) ->
            item(key = "skeleton") { ListSkeleton(rows = 8) }
        shown.isEmpty() -> item(key = "empty") {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                EmptyState(
                    title = stringResource(R.string.extrato_empty_title),
                    message = stringResource(if (viewModel.filtersActive) R.string.extrato_empty_filtered else R.string.extrato_empty_message),
                )
                if (!viewModel.filtersActive) {
                    AppButton(text = stringResource(R.string.extrato_new), onClick = onNewEntry, modifier = Modifier.fillMaxWidth())
                }
            }
        }
        else -> {
            val today = LocalDate.now()
            // A chave leva a posicao: um pendente da fila com data antiga abre o mesmo dia duas vezes.
            ExtratoRules.groupByDay(shown, viewModel.dayTotals).forEachIndexed { index, day ->
                stickyHeader(key = "day:$index:${day.date}") {
                    // Um dia so de compras no cartao nao tem total: elas nao mexem em conta.
                    DayHeader(ExtratoRules.dayLabel(day.date, today), if (day.hasTotal) formatSignedCurrency(day.total) else "")
                }
                day.items.forEach { row ->
                    item(key = "row:${ReviewRules.statementKey(row)}") { TransactionRow(row, viewModel, onOpenCards = { onTab(LancamentosTab.CARTOES) }) }
                }
            }
            item(key = "more") { MoreFooter(viewModel) }
        }
    }
}

@Composable
private fun ContasAlerts(viewModel: ExtratoViewModel) {
    val dismiss = stringResource(R.string.lanc_dismiss)
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (viewModel.offline) {
            val stored = viewModel.cachedAt
            AlertMessage(
                message = if (stored != null) stringResource(R.string.lanc_offline, storedTimeLabel(stored)) else stringResource(R.string.lanc_offline_no_copy),
                tone = AlertTone.WARNING,
                dismissLabel = dismiss,
            )
        }
        AlertMessage(message = viewModel.loadError, tone = AlertTone.WARNING, dismissLabel = dismiss)
        AlertMessage(message = viewModel.actionError, tone = AlertTone.WARNING, dismissLabel = dismiss, onDismiss = viewModel::dismissActionError)
        AlertMessage(message = viewModel.reviewError, tone = AlertTone.WARNING, dismissLabel = dismiss, onDismiss = viewModel::dismissReviewError)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun StatementPanelHeader(viewModel: ExtratoViewModel) {
    val palette = LocalPalette.current
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(stringResource(R.string.extrato_panel_title), color = palette.text, fontWeight = FontWeight.Bold, fontSize = 17.sp)
        Text(
            stringResource(if (viewModel.filtersActive) R.string.extrato_panel_filtered else R.string.extrato_panel_latest),
            color = palette.muted,
            fontSize = 13.sp,
        )
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            if (viewModel.filtersActive) {
                val totals = viewModel.totals
                GainBadge(formatSignedCurrency(totals.income, 1))
                Badge(formatSignedCurrency(totals.expense, -1))
                if (totals.investment.abs() >= java.math.BigDecimal("0.005")) {
                    val text = formatSignedCurrency(totals.investment, 0)
                    Badge(
                        if (totals.investment.signum() > 0) stringResource(R.string.extrato_invested, text) else stringResource(R.string.extrato_redeemed, text),
                    )
                }
            }
            Badge(if (viewModel.filtering && viewModel.filtersActive) stringResource(R.string.extrato_filtering) else stringResource(R.string.extrato_count, viewModel.count + pendingShown(viewModel)))
        }
    }
}

private fun pendingShown(viewModel: ExtratoViewModel): Int = viewModel.statementRows.size - (viewModel.rows?.size ?: 0)

/** O selo verde (o Badge tone="success" da web): so para entrada. */
@Composable
private fun GainBadge(text: String) {
    val palette = LocalPalette.current
    androidx.compose.material3.Surface(shape = androidx.compose.foundation.shape.RoundedCornerShape(50), color = palette["emerald-50"]) {
        Text(text, color = palette["emerald-700"], fontWeight = FontWeight.SemiBold, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp))
    }
}

@Composable
private fun FiltersBlock(viewModel: ExtratoViewModel) {
    val palette = LocalPalette.current
    val filters = viewModel.filters
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Icon(AppIcons.Search, contentDescription = null, tint = palette.muted, modifier = Modifier.size(20.dp))
            AppTextField(
                value = filters.q,
                onValueChange = { viewModel.changeFilters(filters.copy(q = it.take(100))) },
                placeholder = stringResource(R.string.extrato_search),
                modifier = Modifier.weight(1f),
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val hiddenCount = ExtratoRules.countHiddenFilters(filters)
            AppButton(
                text = if (hiddenCount > 0) stringResource(R.string.extrato_filters_count, hiddenCount) else stringResource(R.string.extrato_filters),
                onClick = viewModel::toggleFilters,
                variant = ButtonVariant.SECONDARY,
            )
            if (viewModel.filtersActive) {
                AppButton(text = stringResource(R.string.extrato_clear_filters), onClick = viewModel::clearFilters, variant = ButtonVariant.SUBTLE)
            }
        }
        if (viewModel.filtersOpen) FilterPanel(viewModel)
        if (viewModel.filterError.isNotEmpty()) Text(viewModel.filterError, color = palette.loss, fontSize = 13.sp)
    }
}

@Composable
private fun FilterPanel(viewModel: ExtratoViewModel) {
    val filters = viewModel.filters
    val ok = stringResource(R.string.lanc_date_ok)
    val cancel = stringResource(R.string.lanc_cancel)
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Field(stringResource(R.string.extrato_filter_from), Modifier.weight(1f)) {
                    DateField(filters.from, { viewModel.changeFilters(filters.copy(from = it)) }, ok, cancel)
                }
                Field(stringResource(R.string.extrato_filter_to), Modifier.weight(1f)) {
                    DateField(filters.to, { viewModel.changeFilters(filters.copy(to = it)) }, ok, cancel)
                }
            }
            Field(stringResource(R.string.extrato_filter_type)) {
                SelectField(
                    value = filters.type,
                    options = listOf(
                        SelectOption("", stringResource(R.string.extrato_filter_type_all)),
                        SelectOption("INCOME", stringResource(R.string.extrato_filter_type_income)),
                        SelectOption("EXPENSE", stringResource(R.string.extrato_filter_type_expense)),
                        SelectOption("TRANSFER", stringResource(R.string.extrato_filter_type_transfer)),
                    ),
                    onSelect = { viewModel.changeFilters(filters.copy(type = it)) },
                )
            }
            Field(stringResource(R.string.extrato_filter_account)) {
                SelectField(
                    value = filters.accountId,
                    options = listOf(SelectOption("", stringResource(R.string.extrato_filter_account_all))) +
                        viewModel.activeAccounts.map { SelectOption(it.id, it.name) },
                    onSelect = { viewModel.changeFilters(filters.copy(accountId = it)) },
                )
            }
            Field(stringResource(R.string.extrato_filter_category)) {
                SelectField(
                    value = filters.categoryId,
                    options = listOf(SelectOption("", stringResource(R.string.extrato_filter_category_all))) +
                        viewModel.categoryOptions.map { SelectOption(it.id, it.label) },
                    onSelect = { viewModel.changeFilters(filters.copy(categoryId = it)) },
                )
            }
            Field(stringResource(R.string.extrato_filter_review)) {
                SelectField(
                    value = filters.review,
                    options = listOf(
                        SelectOption("", stringResource(R.string.extrato_filter_review_all)),
                        SelectOption("1", stringResource(R.string.extrato_filter_review_only)),
                    ),
                    onSelect = { viewModel.changeFilters(filters.copy(review = it)) },
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Field(stringResource(R.string.extrato_filter_min), Modifier.weight(1f)) {
                    AppTextField(filters.minAmount, { viewModel.changeFilters(filters.copy(minAmount = it)) }, keyboardType = KeyboardType.Decimal)
                }
                Field(stringResource(R.string.extrato_filter_max), Modifier.weight(1f)) {
                    AppTextField(filters.maxAmount, { viewModel.changeFilters(filters.copy(maxAmount = it)) }, keyboardType = KeyboardType.Decimal)
                }
            }
        }
    }
}

@Composable
private fun DayHeader(label: String, total: String) {
    val palette = LocalPalette.current
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier.fillMaxWidth().background(palette.background).padding(horizontal = 4.dp, vertical = 8.dp),
    ) {
        Text(label, color = palette["zinc-700"], fontWeight = FontWeight.Bold, fontSize = 14.sp, modifier = Modifier.weight(1f))
        if (total.isNotEmpty()) Text(total, color = palette.muted, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun TransactionRow(row: TransactionDto, viewModel: ExtratoViewModel, onOpenCards: () -> Unit) {
    val palette = LocalPalette.current
    val editable = ExtratoRules.isEditableHere(row)
    val card = ReviewRules.isCardRow(row)
    val actions = rowActions(row, viewModel)
    val onTap: () -> Unit = when {
        // A compra no cartao se edita (e se paga) em Cartoes.
        card -> onOpenCards
        editable -> { { viewModel.startEditing(row) } }
        !row.pending -> { { viewModel.openAttachments(row) } }
        else -> { {} }
    }
    Panel {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier
                .clickable(onClick = onTap)
                .heightIn(min = 56.dp)
                .padding(start = 14.dp, end = 6.dp, top = 10.dp, bottom = 10.dp),
        ) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(
                        ExtratoRules.title(row),
                        color = palette.text,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f, fill = false),
                    )
                    if (ExtratoRules.reviewMark(row)) Badge(stringResource(R.string.extrato_review_mark), BadgeTone.WARNING)
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    val second = buildString {
                        append(if (row.type == ExtratoRules.TRANSFER) "${viewModel.accountName(row.accountId)} → ${viewModel.accountName(row.transferAccountId)}" else row.category.orEmpty())
                        if (!editable) append(" · ").append(ExtratoRules.originLabel(row))
                    }
                    Text(second, color = palette.muted, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                    if (row.attachmentCount > 0) {
                        Icon(AppIcons.Paperclip, contentDescription = null, tint = palette.muted, modifier = Modifier.size(14.dp))
                        if (row.attachmentCount > 1) Text(row.attachmentCount.toString(), color = palette.muted, fontSize = 12.sp)
                    }
                }
                val share = Sharing.shareSummary(SharedRow(row.amount, row.shareMode, row.sharePerson, row.shareOthersAmount))
                if (share.isNotEmpty()) Text(share, color = palette.muted, fontSize = 12.sp, fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(4.dp)) {
                val color = when {
                    !card && row.type == ExtratoRules.TRANSFER -> palette.muted
                    ExtratoRules.isGain(row) -> palette["emerald-700"]
                    else -> palette.text
                }
                Text(formatSignedCurrency(row.amount, ExtratoRules.amountSign(row)), color = color, fontWeight = FontWeight.Bold, maxLines = 1)
                ExtratoRules.typeBadge(row)?.let { Badge(it) }
            }
            if (actions.isNotEmpty()) {
                OverflowMenu(actions = actions, label = stringResource(R.string.lanc_actions_of, ExtratoRules.title(row)))
            }
        }
    }
}

@Composable
private fun rowActions(row: TransactionDto, viewModel: ExtratoViewModel): List<MenuAction> {
    if (row.pending || ReviewRules.isCardRow(row)) return emptyList()
    val receipts = if (row.attachmentCount > 0) stringResource(R.string.attach_menu_count, row.attachmentCount) else stringResource(R.string.attach_menu)
    val list = mutableListOf<MenuAction>()
    if (ExtratoRules.isEditableHere(row)) list += MenuAction(stringResource(R.string.extrato_edit)) { viewModel.startEditing(row) }
    list += MenuAction(receipts) { viewModel.openAttachments(row) }
    when {
        ExtratoRules.isEditableHere(row) -> list += MenuAction(stringResource(R.string.extrato_delete)) { viewModel.askDelete(row) }
        ExtratoRules.isInvoicePayment(row) -> list += MenuAction(stringResource(R.string.extrato_undo)) { viewModel.askUndoPayment(row) }
        ExtratoRules.isInvestmentCash(row) -> list += MenuAction(stringResource(R.string.extrato_delete_operation)) { viewModel.askDeleteInvestmentCash(row) }
    }
    return list
}

@Composable
private fun MoreFooter(viewModel: ExtratoViewModel) {
    val palette = LocalPalette.current
    val shown = viewModel.rows?.size ?: 0
    if (!viewModel.hasMore && shown >= viewModel.count) return
    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
        Text(stringResource(R.string.extrato_showing, shown, viewModel.count), color = palette.muted, fontSize = 13.sp)
        if (viewModel.hasMore) {
            AppButton(
                text = stringResource(if (viewModel.loadingMore) R.string.extrato_loading_more else R.string.extrato_load_more),
                onClick = viewModel::loadMore,
                variant = ButtonVariant.SECONDARY,
                loading = viewModel.loadingMore,
            )
        }
    }
}

// ---- Investimentos ----

@OptIn(ExperimentalFoundationApi::class)
private fun LazyListScope.investmentsView(viewModel: ExtratoViewModel, onOpenWeb: (String) -> Unit) {
    item(key = "inv-intro") {
        val palette = LocalPalette.current
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(stringResource(R.string.extrato_inv_description), color = palette.muted, fontSize = 14.sp)
            AlertMessage(message = viewModel.invError, tone = AlertTone.WARNING, dismissLabel = stringResource(R.string.lanc_dismiss))
            AlertMessage(message = viewModel.actionError, tone = AlertTone.WARNING, dismissLabel = stringResource(R.string.lanc_dismiss), onDismiss = viewModel::dismissActionError)
        }
    }
    val entries = viewModel.investmentEntries
    val totals = InvestmentStatement.statementTotals(entries)
    item(key = "inv-summary") { InvestmentSummary(totals, viewModel.hidden) }
    item(key = "inv-panel") {
        val palette = LocalPalette.current
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(stringResource(R.string.extrato_inv_panel_title), color = palette.text, fontWeight = FontWeight.Bold, fontSize = 17.sp)
                    Text(stringResource(R.string.extrato_inv_panel_description), color = palette.muted, fontSize = 13.sp)
                }
                Badge(stringResource(R.string.extrato_count, entries.size))
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Icon(AppIcons.Search, contentDescription = null, tint = palette.muted, modifier = Modifier.size(20.dp))
                AppTextField(
                    value = viewModel.invQuery,
                    onValueChange = viewModel::changeInvQuery,
                    placeholder = stringResource(R.string.extrato_inv_search),
                    modifier = Modifier.weight(1f),
                )
            }
            SegmentedChoice(
                items = listOf(
                    SelectOption(InvestmentStatement.KIND_ALL, stringResource(R.string.extrato_inv_all)),
                    SelectOption(InvestmentStatement.KIND_MOVEMENTS, stringResource(R.string.extrato_inv_movements)),
                    SelectOption(InvestmentStatement.KIND_PROCEEDS, stringResource(R.string.extrato_inv_proceeds_tab)),
                ),
                value = viewModel.invKind,
                onChange = viewModel::changeInvKind,
            )
        }
    }
    when {
        viewModel.movements == null || viewModel.proceeds == null -> item(key = "inv-skeleton") { ListSkeleton(rows = 8) }
        entries.isEmpty() -> item(key = "inv-empty") {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                EmptyState(title = stringResource(R.string.extrato_inv_empty_title))
                AppButton(
                    text = stringResource(R.string.extrato_inv_go_operations),
                    onClick = { onOpenWeb("/investimentos/operacoes") },
                    variant = ButtonVariant.SECONDARY,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }
        else -> {
            val today = LocalDate.now()
            InvestmentStatement.groupEntriesByDay(entries).forEach { day ->
                stickyHeader(key = "inv-day:${day.date}") {
                    DayHeader(ExtratoRules.dayLabel(day.date, today, relative = false), moneyOrSigned(day.total, viewModel.hidden))
                }
                day.items.forEach { entry -> item(key = entry.id) { EntryRow(entry, viewModel) } }
            }
        }
    }
}

private fun moneyOrSigned(value: java.math.BigDecimal, hidden: Boolean): String =
    if (hidden) HomeLogic.MASKED_CURRENCY else formatSignedCurrency(value)

@Composable
private fun InvestmentSummary(totals: br.financas.app.rules.StatementTotals, hidden: Boolean) {
    val palette = LocalPalette.current
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(stringResource(R.string.extrato_inv_proceeds), color = palette.muted, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                FitText(moneyOrMasked(totals.proceeds, hidden), maxSize = 30.sp, minSize = 20.sp, color = if (hidden) palette.text else palette.gain)
                if (totals.scheduled.signum() > 0) {
                    Text(stringResource(R.string.extrato_inv_scheduled, moneyOrMasked(totals.scheduled, hidden)), color = palette.muted, fontSize = 12.sp)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                SummaryFigure(stringResource(R.string.extrato_inv_invested), moneyOrMasked(totals.invested, hidden), Modifier.weight(1f))
                SummaryFigure(stringResource(R.string.extrato_inv_withdrawn), moneyOrMasked(totals.withdrawn, hidden), Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun SummaryFigure(label: String, value: String, modifier: Modifier) {
    val palette = LocalPalette.current
    Column(modifier) {
        Text(label, color = palette.muted, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
        FitText(value, maxSize = 18.sp, minSize = 12.sp, color = palette.text, fontWeight = FontWeight.Bold)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun EntryRow(entry: StatementEntry, viewModel: ExtratoViewModel) {
    val palette = LocalPalette.current
    Panel {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier.heightIn(min = 56.dp).padding(start = 14.dp, end = 6.dp, top = 10.dp, bottom = 10.dp),
        ) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(entry.title, color = palette.text, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Badge(entry.kind)
                    if (entry.scheduled) Badge(stringResource(R.string.extrato_inv_scheduled_badge), BadgeTone.INFO)
                }
                val detail = listOf(InvestmentStatement.detailText(entry), if (entry.inStatement) stringResource(R.string.extrato_inv_in_statement) else "")
                    .filter { it.isNotEmpty() }
                    .joinToString(" · ")
                if (detail.isNotEmpty()) Text(detail, color = palette.muted, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            val color: Color = when {
                entry.scheduled || entry.amount.signum() == 0 -> palette.muted
                entry.amount.signum() > 0 && !viewModel.hidden -> palette["emerald-700"]
                else -> palette.text
            }
            Text(
                if (entry.amount.signum() == 0) stringResource(R.string.extrato_inv_no_cost) else moneyOrSigned(entry.amount, viewModel.hidden),
                color = color,
                fontWeight = FontWeight.Bold,
                maxLines = 1,
            )
            if (entry.deletable) {
                OverflowMenu(
                    actions = listOf(MenuAction(stringResource(R.string.extrato_inv_delete)) { viewModel.askDeleteMovement(entry) }),
                    label = stringResource(R.string.lanc_actions_of, "${entry.kind} ${entry.title}"),
                )
            } else {
                Box(Modifier.size(48.dp))
            }
        }
    }
}

