package br.financas.app.ui.inbox

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Snackbar
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import br.financas.app.R
import br.financas.app.data.InboxCandidateDto
import br.financas.app.data.InboxHintDto
import br.financas.app.data.InboxItemDto
import br.financas.app.data.InboxRepository
import br.financas.app.data.storedTimeLabel
import br.financas.app.rules.InboxRules
import br.financas.app.rules.QuickChoice
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AlertTone
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.Badge
import br.financas.app.ui.components.BadgeTone
import br.financas.app.ui.components.ButtonVariant
import br.financas.app.ui.components.ConfirmDialog
import br.financas.app.ui.components.EmptyState
import br.financas.app.ui.components.Field
import br.financas.app.ui.components.ListSkeleton
import br.financas.app.ui.components.MenuAction
import br.financas.app.ui.components.OverflowMenu
import br.financas.app.ui.components.SegmentedChoice
import br.financas.app.ui.components.SelectField
import br.financas.app.ui.components.SelectOption
import br.financas.app.ui.theme.LocalPalette
import kotlinx.coroutines.delay

// Os itens fixos do alto da lista (introducao, abas, avisos): o item da notificacao fica depois.
private const val HEADER_ROWS = 3

/**
 * Aprovar nativo (mobile-docs/native/screens/02-aprovar.md): o pages/lancamentos/Aprovar.jsx em
 * Compose. [onBack] volta para o Extrato.
 */
@Composable
fun InboxScreen(viewModel: InboxViewModel, onBack: () -> Unit) {
    val palette = LocalPalette.current
    val snackbar = remember { SnackbarHostState() }
    val haptic = LocalHapticFeedback.current
    val listState = rememberLazyListState()
    val lifecycleOwner = LocalLifecycleOwner.current

    // Com a tela na frente: tudo de novo ao abrir e ao voltar, e a lista pendente a cada 20 s.
    LaunchedEffect(lifecycleOwner) {
        lifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
            InboxNotifier.screenVisible = true
            try {
                viewModel.refreshAll()
                while (true) {
                    delay(InboxLogic.REFRESH_MS)
                    if (viewModel.isPendingView) viewModel.refresh(InboxRepository.VIEW_PENDING)
                }
            } finally {
                InboxNotifier.screenVisible = false
            }
        }
    }

    LaunchedEffect(Unit) {
        viewModel.notices.collect { message ->
            haptic.performHapticFeedback(HapticFeedbackType.LongPress)
            snackbar.showSnackbar(message)
        }
    }

    // O item da notificacao: a lista rola ate ele assim que ele esta nela.
    val focusIndex = InboxLogic.indexOf(viewModel.pending, viewModel.focusId)
    LaunchedEffect(focusIndex) {
        if (focusIndex >= 0 && viewModel.isPendingView) {
            listState.animateScrollToItem(HEADER_ROWS + focusIndex)
            viewModel.focusDone()
        }
    }

    Scaffold(
        containerColor = palette.background,
        snackbarHost = {
            SnackbarHost(snackbar) { data ->
                Snackbar(snackbarData = data, containerColor = palette["zinc-900"], contentColor = palette["zinc-50"])
            }
        },
        topBar = { TopBar(onBack) },
    ) { padding ->
        LazyColumn(
            state = listState,
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 32.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item(key = "intro") { Intro(viewModel) }
            item(key = "tabs") { ViewTabs(viewModel) }
            item(key = "alerts") { Alerts(viewModel) }
            val items = viewModel.items
            when {
                items == null -> item(key = "skeleton") { ListSkeleton(rows = 3) }
                viewModel.isPendingView && items.isEmpty() -> item(key = "empty") {
                    EmptyState(
                        title = stringResource(R.string.inbox_empty_pending_title),
                        message = stringResource(R.string.inbox_empty_pending_message),
                    )
                }
                viewModel.isPendingView -> items(items, key = { it.id }) { item -> ItemCard(item, viewModel) }
                items.isEmpty() -> item(key = "empty-decided") {
                    EmptyState(title = stringResource(R.string.inbox_empty_decided))
                }
                else -> items(items, key = { "decided:" + it.id }) { item -> DecidedRow(item, viewModel) }
            }
            if (viewModel.hints.isNotEmpty()) item(key = "hints") { Hints(viewModel) }
            item(key = "settings") { AlwaysAsk(viewModel) }
        }
    }

    viewModel.editing?.let { item -> InboxEditSheet(item, viewModel) }
    ConfirmDialog(
        request = viewModel.confirm,
        cancelLabel = stringResource(R.string.inbox_cancel),
        onDismiss = viewModel::dismissConfirm,
    )
}

@Composable
private fun TopBar(onBack: () -> Unit) {
    val palette = LocalPalette.current
    val backLabel = stringResource(R.string.native_back)
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .fillMaxWidth()
            .windowInsetsPadding(WindowInsets.statusBars)
            .padding(horizontal = 8.dp, vertical = 8.dp),
    ) {
        Surface(
            onClick = onBack,
            shape = RoundedCornerShape(50),
            color = palette.background,
            contentColor = palette.text,
            modifier = Modifier.size(48.dp).semantics { contentDescription = backLabel },
        ) {
            Box(contentAlignment = Alignment.Center) {
                Text("←", style = MaterialTheme.typography.titleLarge, color = palette.text)
            }
        }
        Text(
            text = stringResource(R.string.inbox_title),
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.ExtraBold,
            color = palette.text,
            modifier = Modifier.padding(start = 8.dp),
        )
    }
}

@Composable
private fun Intro(viewModel: InboxViewModel) {
    val palette = LocalPalette.current
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(
            text = stringResource(R.string.inbox_description),
            style = MaterialTheme.typography.bodyMedium,
            color = palette.muted,
        )
        val ready = viewModel.readyIds
        if (ready.isNotEmpty()) {
            AppButton(
                text = stringResource(R.string.inbox_approve_ready, ready.size),
                onClick = viewModel::approveReady,
                loading = viewModel.busyKey == InboxLogic.BUSY_READY,
                enabled = !viewModel.offline,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

@Composable
private fun ViewTabs(viewModel: InboxViewModel) {
    val count = viewModel.pendingCount
    SegmentedChoice(
        items = listOf(
            SelectOption(
                InboxRepository.VIEW_PENDING,
                if (count > 0) stringResource(R.string.inbox_tab_pending_count, count) else stringResource(R.string.inbox_tab_pending),
            ),
            SelectOption(InboxRepository.VIEW_DECIDED, stringResource(R.string.inbox_tab_decided)),
        ),
        value = viewModel.view,
        onChange = viewModel::changeView,
    )
}

@Composable
private fun Alerts(viewModel: InboxViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (viewModel.offline) {
            val stored = viewModel.cachedAt
            val text = if (stored != null && viewModel.items != null) {
                stringResource(R.string.inbox_offline, storedTimeLabel(stored))
            } else {
                stringResource(R.string.inbox_offline_no_copy)
            }
            AlertMessage(message = text, tone = AlertTone.WARNING, dismissLabel = stringResource(R.string.inbox_dismiss_error))
            AppButton(
                text = stringResource(R.string.inbox_retry),
                onClick = viewModel::refreshAll,
                variant = ButtonVariant.SECONDARY,
            )
        }
        val message = viewModel.error.ifEmpty { viewModel.listError }
        AlertMessage(
            message = message,
            dismissLabel = stringResource(R.string.inbox_dismiss_error),
            onDismiss = if (viewModel.error.isNotEmpty()) viewModel::dismissError else null,
        )
    }
}

@Composable
private fun Panel(modifier: Modifier = Modifier, warn: Boolean = false, content: @Composable () -> Unit) {
    val palette = LocalPalette.current
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        color = if (warn) palette["amber-50"] else palette.surface,
        border = BorderStroke(1.dp, if (warn) palette.warning.copy(alpha = 0.35f) else palette.border),
    ) { content() }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ItemCard(item: InboxItemDto, viewModel: InboxViewModel) {
    val palette = LocalPalette.current
    val rule = item.rule
    var rememberChoice by rememberSaveable(item.id) { mutableStateOf(true) }
    var changing by rememberSaveable(item.id) { mutableStateOf(false) }
    val busy = { action: String -> viewModel.busyKey == InboxLogic.busyKey(item.id, action) }
    val enabled = !viewModel.offline

    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.Top) {
                Column(Modifier.weight(1f)) {
                    Text(
                        text = InboxLogic.itemTitle(item),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                        color = palette.text,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(InboxRules.whenText(item.occurredAt), style = MaterialTheme.typography.bodyMedium, color = palette["zinc-600"])
                }
                Text(
                    text = InboxLogic.amountText(item),
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    color = palette.text,
                    textAlign = TextAlign.End,
                    modifier = Modifier.padding(start = 12.dp),
                )
            }

            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Badge(InboxRules.entryTypeLabel(item.entryType), if (item.entryType.isNullOrEmpty()) BadgeTone.WARNING else BadgeTone.NEUTRAL)
                if (!item.category.isNullOrEmpty() && item.entryType != "TRANSFER") Badge(item.category)
                if (InboxRules.onlySamsung(rule)) Badge(stringResource(R.string.inbox_badge_samsung), BadgeTone.INFO)
                if (item.edited.isNotEmpty()) Badge(stringResource(R.string.inbox_badge_edited), BadgeTone.INFO)
            }

            if (item.sources.isNotEmpty()) {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    item.sources.forEach { source ->
                        Text(InboxLogic.sourceLine(source), style = MaterialTheme.typography.bodySmall, color = palette.muted)
                    }
                }
            }

            val reason = InboxRules.reasonText(rule)
            if (reason.isNotEmpty()) Text(reason, style = MaterialTheme.typography.bodyMedium, color = palette["zinc-600"])

            TargetLine(item, changing) { changing = !changing }

            Decisions(item, viewModel, changing, enabled) { changing = false }

            if (item.recurring != null) {
                Panel {
                    Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("↻  " + InboxRules.recurringText(rule), style = MaterialTheme.typography.bodyMedium, color = palette["zinc-700"])
                        AppButton(
                            text = stringResource(if (item.recurringOff) R.string.inbox_recurring_undo else R.string.inbox_recurring_off),
                            onClick = { viewModel.toggleRecurring(item) },
                            variant = ButtonVariant.SUBTLE,
                            loading = busy("quick"),
                            enabled = enabled,
                        )
                    }
                }
            }

            if (item.candidates.isNotEmpty()) {
                Panel {
                    Column {
                        item.candidates.forEachIndexed { index, candidate ->
                            if (index > 0) HorizontalDivider(color = palette["zinc-100"])
                            CandidateRow(candidate, busy("match:${candidate.id}"), enabled) {
                                viewModel.match(item, candidate, rememberChoice)
                            }
                        }
                    }
                }
            }

            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
                itemVerticalAlignment = Alignment.CenterVertically,
            ) {
                AppButton(
                    text = stringResource(if (InboxLogic.approvesAsNew(item)) R.string.inbox_approve_new else R.string.inbox_approve),
                    onClick = { viewModel.approve(item, rememberChoice) },
                    loading = busy("approve"),
                    enabled = enabled,
                )
                AppButton(
                    text = stringResource(R.string.inbox_edit),
                    onClick = { viewModel.openEdit(item) },
                    variant = ButtonVariant.SECONDARY,
                    enabled = enabled,
                )
                AppButton(
                    text = stringResource(R.string.inbox_deny),
                    onClick = { viewModel.deny(item) },
                    variant = ButtonVariant.SUBTLE,
                    loading = busy("deny"),
                    enabled = enabled,
                )
                if (InboxRules.offersRemember(rule)) {
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.heightIn(min = 48.dp)) {
                        Checkbox(
                            checked = rememberChoice,
                            onCheckedChange = { rememberChoice = it },
                            colors = CheckboxDefaults.colors(checkedColor = palette.accent, checkmarkColor = palette.onAccent),
                        )
                        Text(stringResource(R.string.inbox_remember), style = MaterialTheme.typography.bodyMedium, color = palette["zinc-600"])
                    }
                }
                if (InboxLogic.showsMenu(item)) {
                    val editLabel = stringResource(R.string.inbox_edit_before)
                    val splitTemplate = stringResource(R.string.inbox_split_option)
                    val actions = listOf(MenuAction(editLabel) { viewModel.openEdit(item) }) +
                        InboxLogic.splittable(item).map { source ->
                            MenuAction(splitTemplate.format(InboxRules.sourceLabel(source.rule))) { viewModel.askSplit(item, source) }
                        }
                    OverflowMenu(actions = actions, label = stringResource(R.string.inbox_more), enabled = enabled)
                }
            }
        }
    }
}

@Composable
private fun TargetLine(item: InboxItemDto, changing: Boolean, onToggle: () -> Unit) {
    val palette = LocalPalette.current
    val rule = item.rule
    val text = InboxRules.targetText(rule)
    if (text.isEmpty()) return
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text("→", color = palette.muted, style = MaterialTheme.typography.titleMedium)
        Text(
            text = text,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.Medium,
            color = palette["zinc-800"],
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f).padding(start = 8.dp),
        )
        if (!InboxRules.alreadyOpen(rule, changing)) {
            AppButton(
                text = stringResource(if (changing) R.string.inbox_close else R.string.inbox_change),
                onClick = onToggle,
                variant = ButtonVariant.SUBTLE,
            )
        }
    }
}

/**
 * As escolhas que o item pede, ali mesmo: credito ou debito, qual cartao, qual conta. Um palpite
 * vem preenchido com "confirme"; "Trocar" abre os mesmos seletores. Escolheu: o item volta do
 * servidor e os seletores fecham ([onChosen]).
 */
@Composable
private fun Decisions(item: InboxItemDto, viewModel: InboxViewModel, changing: Boolean, enabled: Boolean, onChosen: () -> Unit) {
    val palette = LocalPalette.current
    val rule = item.rule
    if (!InboxRules.showsDecisions(rule, changing)) return
    val open = InboxRules.openPickers(rule, changing)
    val choose = { choice: QuickChoice -> viewModel.quick(item, InboxRules.quickChoice(rule, choice), onChosen) }
    val choosePlaceholder = stringResource(R.string.inbox_choose)
    Panel(warn = InboxRules.decisionsWarn(rule, changing)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if ("method" in item.needs) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(InboxRules.needText("method"), style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, color = palette["zinc-800"])
                    SegmentedChoice(
                        items = listOf(
                            SelectOption("CARD", stringResource(R.string.inbox_method_card)),
                            SelectOption("DEBIT", stringResource(R.string.inbox_method_debit)),
                        ),
                        value = "",
                        onChange = { method -> if (enabled) choose(QuickChoice(method = method)) },
                    )
                }
            }
            if ("card" in open) {
                Field(label = InboxRules.needText("card"), hint = InboxRules.CONFIRM_TEXTS["card"].takeIf { "card" in item.confirm }) {
                    SelectField(
                        value = item.cardId.orEmpty(),
                        options = viewModel.pickerCards.map { SelectOption(it.id, it.name) },
                        onSelect = { id -> if (enabled) choose(QuickChoice(cardId = id)) },
                        placeholder = choosePlaceholder,
                    )
                }
            }
            if ("account" in open) {
                Field(label = InboxRules.accountPickerLabel(rule), hint = InboxRules.CONFIRM_TEXTS["account"].takeIf { "account" in item.confirm }) {
                    SelectField(
                        value = item.accountId.orEmpty(),
                        options = viewModel.pickerAccounts.map { SelectOption(it.id, it.name) },
                        onSelect = { id -> if (enabled) choose(QuickChoice(accountId = id)) },
                        placeholder = choosePlaceholder,
                    )
                }
            }
            if ("transfer_account" in open) {
                Field(
                    label = InboxRules.needText("transfer_account"),
                    hint = InboxRules.CONFIRM_TEXTS["transfer_account"].takeIf { "transfer_account" in item.confirm },
                ) {
                    SelectField(
                        value = item.transferAccountId.orEmpty(),
                        options = InboxLogic.destinationAccounts(viewModel.pickerAccounts, item.accountId).map { SelectOption(it.id, it.name) },
                        onSelect = { id -> if (enabled) choose(QuickChoice(transferAccountId = id)) },
                        placeholder = choosePlaceholder,
                    )
                }
            }
            val ambiguous = InboxRules.ambiguousText(rule)
            if (ambiguous.isNotEmpty()) Text(ambiguous, style = MaterialTheme.typography.bodySmall, color = palette["zinc-600"])
        }
    }
}

@Composable
private fun CandidateRow(candidate: InboxCandidateDto, busy: Boolean, enabled: Boolean, onPick: () -> Unit) {
    val palette = LocalPalette.current
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp)) {
        Column(Modifier.weight(1f)) {
            Text(
                InboxLogic.candidateTitle(candidate),
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium,
                color = palette["zinc-900"],
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(InboxLogic.candidateLine(candidate), style = MaterialTheme.typography.bodySmall, color = palette.muted)
        }
        Spacer(Modifier.size(8.dp))
        AppButton(
            text = stringResource(R.string.inbox_match),
            onClick = onPick,
            variant = ButtonVariant.SECONDARY,
            loading = busy,
            enabled = enabled,
        )
    }
}

@Composable
private fun DecidedRow(item: InboxItemDto, viewModel: InboxViewModel) {
    val palette = LocalPalette.current
    Panel {
        Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(
                InboxLogic.itemTitle(item),
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium,
                color = palette["zinc-900"],
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(InboxLogic.decidedLine(item), style = MaterialTheme.typography.bodySmall, color = palette.muted)
            if (item.recurring != null) {
                Text(InboxRules.recurringText(item.rule), style = MaterialTheme.typography.bodySmall, color = palette.muted)
            }
            if (InboxLogic.restorable(item)) {
                AppButton(
                    text = stringResource(R.string.inbox_restore),
                    onClick = { viewModel.restore(item) },
                    variant = ButtonVariant.SECONDARY,
                    loading = viewModel.busyKey == InboxLogic.busyKey(item.id, "restore"),
                    enabled = !viewModel.offline,
                )
            }
        }
    }
}

@Composable
private fun Hints(viewModel: InboxViewModel) {
    val palette = LocalPalette.current
    var open by rememberSaveable { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        AppButton(
            text = stringResource(R.string.inbox_hints, viewModel.hints.size) + if (open) "  ▴" else "  ▾",
            onClick = { open = !open },
            variant = ButtonVariant.SECONDARY,
        )
        if (open) {
            Panel {
                Column {
                    viewModel.hints.forEachIndexed { index, hint ->
                        if (index > 0) HorizontalDivider(color = palette["zinc-100"])
                        HintRow(hint, viewModel)
                    }
                }
            }
        }
    }
}

@Composable
private fun HintRow(hint: InboxHintDto, viewModel: InboxViewModel) {
    val palette = LocalPalette.current
    val forget = stringResource(R.string.inbox_hint_forget)
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(start = 16.dp, end = 4.dp, top = 8.dp, bottom = 8.dp)) {
        Column(Modifier.weight(1f)) {
            Text(InboxRules.hintText(hint.rule), style = MaterialTheme.typography.bodyMedium, color = palette["zinc-800"])
            Text(InboxLogic.hintUsage(hint), style = MaterialTheme.typography.bodySmall, color = palette.muted)
        }
        Surface(
            onClick = { viewModel.askForgetHint(hint) },
            enabled = !viewModel.offline,
            shape = RoundedCornerShape(12.dp),
            color = palette.surface,
            contentColor = palette["zinc-700"],
            modifier = Modifier.size(48.dp).semantics { contentDescription = forget },
        ) {
            Box(contentAlignment = Alignment.Center) {
                Text("×", style = MaterialTheme.typography.titleLarge, color = palette["zinc-700"])
            }
        }
    }
}

/** "Sempre perguntar a conta/cartão": o mesmo ajuste de Ajustes › Aprovar, aqui ao alcance. */
@Composable
private fun AlwaysAsk(viewModel: InboxViewModel) {
    val palette = LocalPalette.current
    val value = viewModel.alwaysAsk
    Panel {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(16.dp)) {
            Column(Modifier.weight(1f).padding(end = 12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(stringResource(R.string.inbox_always_ask), style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, color = palette["zinc-900"])
                Text(stringResource(R.string.inbox_always_ask_help), style = MaterialTheme.typography.bodySmall, color = palette["zinc-600"])
            }
            Switch(
                checked = value == true,
                onCheckedChange = viewModel::setAlwaysAsk,
                enabled = value != null && !viewModel.settingsSaving && !viewModel.offline,
                colors = SwitchDefaults.colors(
                    checkedTrackColor = palette.accent,
                    checkedThumbColor = palette.surface,
                    uncheckedTrackColor = palette["zinc-200"],
                    uncheckedThumbColor = palette["zinc-500"],
                    uncheckedBorderColor = palette["zinc-300"],
                ),
            )
        }
    }
}
