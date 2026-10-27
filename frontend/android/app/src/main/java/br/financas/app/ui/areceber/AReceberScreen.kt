package br.financas.app.ui.areceber

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.core.formatCurrency
import br.financas.app.core.formatDateBR
import br.financas.app.core.localDateOfTimestamp
import br.financas.app.data.ReceivableDto
import br.financas.app.rules.Receivables
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AlertTone
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.AppIcons
import br.financas.app.ui.components.ButtonVariant
import br.financas.app.ui.components.EmptyState
import br.financas.app.ui.components.ListSkeleton
import br.financas.app.ui.components.Panel
import br.financas.app.ui.components.SegmentedChoice
import br.financas.app.ui.components.SelectOption
import br.financas.app.ui.lancamentos.LancamentosTab
import br.financas.app.ui.lancamentos.LancamentosTopBar
import br.financas.app.ui.planejar.PlanejarScaffold
import br.financas.app.ui.planejar.SummaryPanel
import br.financas.app.ui.planejar.SummaryValue
import br.financas.app.ui.theme.LocalPalette

/** A receber nativo (06-a-receber.md): pages/lancamentos/AReceber.jsx em Compose. */
@Composable
fun AReceberScreen(
    viewModel: AReceberViewModel,
    onBack: () -> Unit,
    onTab: (LancamentosTab) -> Unit,
) {
    val palette = LocalPalette.current
    val dismiss = stringResource(R.string.lanc_dismiss)
    PlanejarScaffold(
        notices = viewModel.notices,
        onRefresh = viewModel::refreshAll,
        topBar = {
            LancamentosTopBar(
                title = stringResource(R.string.areceber_title),
                current = LancamentosTab.A_RECEBER,
                hidden = viewModel.hidden,
                onBack = onBack,
                onToggleHidden = viewModel::toggleHidden,
                onTab = onTab,
            )
        },
    ) {
        item(key = "intro") {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(stringResource(R.string.areceber_description), fontSize = 14.sp, color = palette["zinc-600"])
                SegmentedChoice(
                    items = listOf(SelectOption("pending", stringResource(R.string.areceber_pending)), SelectOption("all", stringResource(R.string.areceber_all))),
                    value = if (viewModel.all) "all" else "pending",
                    onChange = { viewModel.chooseView(it == "all") },
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
        val items = viewModel.list.value
        if (items == null || !viewModel.list.loaded && items.isEmpty()) {
            if (!viewModel.list.loaded) item(key = "loading") { Panel { ListSkeleton(rows = 4, modifier = Modifier.padding(16.dp)) } }
            return@PlanejarScaffold
        }
        val view = viewModel.view
        view.summary?.let { summary ->
            item(key = "summary") {
                SummaryPanel(
                    lead = SummaryValue(stringResource(R.string.areceber_pending_total), formatCurrency(summary.total)),
                    figures = listOf(
                        SummaryValue(stringResource(R.string.areceber_people), summary.people.toString()),
                        SummaryValue(stringResource(R.string.areceber_items), summary.items.toString()),
                    ),
                )
            }
        }
        if (view.groups.isEmpty()) {
            item(key = "empty") { EmptyState(stringResource(R.string.areceber_empty_title), stringResource(R.string.areceber_empty_message)) }
        } else {
            view.groups.forEach { group -> item(key = "person:${group.person.lowercase()}") { PersonPanel(group, viewModel) } }
        }
    }
}

@Composable
private fun PersonPanel(group: Receivables.PersonGroup, viewModel: AReceberViewModel) {
    val palette = LocalPalette.current
    Panel {
        Column {
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(start = 16.dp, end = 8.dp, top = 12.dp, bottom = 8.dp)) {
                Column(Modifier.weight(1f)) {
                    Text(
                        if (group.open.isNotEmpty()) "${group.person} · ${formatCurrency(group.openTotal)}" else group.person,
                        fontWeight = FontWeight.Bold,
                        fontSize = 16.sp,
                        color = palette.text,
                    )
                    val description = when {
                        group.open.size > 1 -> stringResource(R.string.areceber_n_pending, group.open.size)
                        group.open.isEmpty() -> stringResource(R.string.areceber_all_paid)
                        else -> ""
                    }
                    if (description.isNotEmpty()) Text(description, fontSize = 13.sp, color = palette.muted)
                }
                if (group.showSettleAll) {
                    val key = "person:${group.person}"
                    AppButton(
                        stringResource(R.string.areceber_all_paid),
                        { viewModel.settle(key, group.open, true) },
                        variant = ButtonVariant.SECONDARY,
                        loading = viewModel.savingKey == key,
                    )
                }
            }
            group.items.forEach { item ->
                HorizontalDivider(color = palette["zinc-100"])
                ItemRow(item, viewModel)
            }
        }
    }
}

@Composable
private fun ItemRow(item: ReceivableDto, viewModel: AReceberViewModel) {
    val palette = LocalPalette.current
    val settled = !item.settledAt.isNullOrEmpty()
    val key = "item:${item.id}"
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        modifier = Modifier.heightIn(min = 56.dp).padding(start = 16.dp, end = 8.dp, top = 8.dp, bottom = 8.dp),
    ) {
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (item.kind == "CARD_PURCHASE") {
                    val cardLabel = stringResource(R.string.areceber_card_purchase)
                    Icon(AppIcons.CreditCard, contentDescription = cardLabel, tint = palette["zinc-400"], modifier = Modifier.size(14.dp))
                    Box(Modifier.size(6.dp))
                }
                Text(item.description.orEmpty(), fontWeight = FontWeight.Medium, color = palette.text, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            val detail = buildString {
                append(formatDateBR(item.date))
                if (!item.cardName.isNullOrEmpty()) append(" · ${item.cardName}")
                if (item.shareMode == "SPLIT") append(stringResource(R.string.areceber_split_total, formatCurrency(item.amount)))
                if (settled) append(stringResource(R.string.areceber_paid_on, formatDateBR(localDateOfTimestamp(item.settledAt))))
            }
            Text(detail, fontSize = 12.sp, color = palette.muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        Text(
            formatCurrency(item.othersAmount),
            fontWeight = FontWeight.SemiBold,
            color = if (settled) palette["zinc-400"] else palette.text,
            textDecoration = if (settled) TextDecoration.LineThrough else null,
        )
        if (settled) {
            val label = stringResource(R.string.areceber_reopen)
            Surface(
                onClick = { viewModel.settle(key, listOf(item), false) },
                enabled = viewModel.savingKey.isEmpty(),
                shape = CircleShape,
                color = palette.surface,
                modifier = Modifier.size(48.dp).semantics { contentDescription = label },
            ) {
                Box(contentAlignment = Alignment.Center) {
                    if (viewModel.savingKey == key) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp, color = palette.muted)
                    else Icon(AppIcons.Undo, null, tint = palette["zinc-700"], modifier = Modifier.size(18.dp))
                }
            }
        } else {
            AppButton(stringResource(R.string.areceber_paid), { viewModel.settle(key, listOf(item), true) }, loading = viewModel.savingKey == key)
        }
    }
}
