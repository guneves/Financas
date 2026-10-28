package br.financas.app.ui.globalaccount

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
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
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.data.AccountDto
import br.financas.app.core.formatCurrency
import br.financas.app.core.formatDateBR
import br.financas.app.core.formatForeignCurrency
import br.financas.app.core.formatSignedForeignCurrency
import br.financas.app.rules.GlobalAccount
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AlertTone
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.AppSheet
import br.financas.app.ui.components.AppTextField
import br.financas.app.ui.components.DateField
import br.financas.app.ui.components.Field
import br.financas.app.ui.components.SelectField
import br.financas.app.ui.components.Badge
import br.financas.app.ui.components.BadgeTone
import br.financas.app.ui.components.ButtonVariant
import br.financas.app.ui.components.EmptyState
import br.financas.app.ui.components.ListSkeleton
import br.financas.app.ui.components.NativeTopBar
import br.financas.app.ui.components.Panel
import br.financas.app.ui.components.SegmentedChoice
import br.financas.app.ui.components.SelectOption
import br.financas.app.ui.planejar.PlanejarScaffold
import br.financas.app.ui.planejar.SummaryPanel
import br.financas.app.ui.planejar.SummaryValue
import br.financas.app.ui.theme.LocalPalette
import java.math.BigDecimal

private const val MASKED_FOREIGN = "US$ ••••••"
private const val MASKED_REAIS = "R$ ••••••"

/**
 * Conta global nativa (17-conta-global.md): a unica tela do celular em outra moeda. Saldo e
 * extrato na moeda da conta, "~ R$" pelo cambio de hoje; o que espera revisao se confirma aqui.
 */
@Composable
fun GlobalAccountScreen(viewModel: GlobalAccountViewModel, onBack: () -> Unit) {
    val palette = LocalPalette.current
    val dismiss = stringResource(R.string.lanc_dismiss)
    PlanejarScaffold(
        notices = viewModel.notices,
        onRefresh = viewModel::refreshAll,
        topBar = {
            NativeTopBar(
                title = stringResource(R.string.global_title),
                onBack = onBack,
                hidden = viewModel.hidden,
                onToggleHidden = viewModel::toggleHidden,
            )
        },
    ) {
        item(key = "alerts") {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (viewModel.accounts.offline) AlertMessage(viewModel.accounts.offlineText, AlertTone.WARNING, dismiss)
                AlertMessage(viewModel.accounts.error, AlertTone.DANGER, dismiss)
                AlertMessage(viewModel.page.error, AlertTone.DANGER, dismiss)
                AlertMessage(viewModel.actionError, AlertTone.DANGER, dismiss, onDismiss = viewModel::dismissActionError)
            }
        }
        if (!viewModel.accounts.loaded) {
            item(key = "loading") { Panel { ListSkeleton(rows = 3, modifier = Modifier.padding(16.dp)) } }
            return@PlanejarScaffold
        }
        val account = viewModel.account
        if (account == null) {
            item(key = "none") { EmptyState(stringResource(R.string.global_none_title), stringResource(R.string.global_none_message)) }
            return@PlanejarScaffold
        }
        val currency = GlobalAccount.currencyOf(account)
        val hidden = viewModel.hidden
        val foreign = { value: BigDecimal? -> if (hidden) MASKED_FOREIGN else formatForeignCurrency(value, currency) }
        item(key = "intro") {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(stringResource(R.string.global_description, account.name, currency), fontSize = 14.sp, color = palette["zinc-600"])
                if (viewModel.globals.size > 1) {
                    SegmentedChoice(
                        items = viewModel.globals.map { SelectOption(it.id, it.name) },
                        value = account.id,
                        onChange = viewModel::choose,
                    )
                }
            }
        }
        val rows = viewModel.statement
        val totals = GlobalAccount.totals(rows)
        val hint = GlobalAccount.brlHint(account)
        item(key = "summary") {
            SummaryPanel(
                lead = SummaryValue(
                    stringResource(R.string.global_balance),
                    foreign(account.balance),
                    hint = if (hint == null) stringResource(R.string.home_no_rate)
                    else stringResource(R.string.global_brl_hint, if (hidden) MASKED_REAIS else formatCurrency(hint)),
                    loss = !hidden && (account.balance?.signum() ?: 0) < 0,
                ),
                figures = listOf(
                    SummaryValue(stringResource(R.string.global_in), foreign(totals.incoming)),
                    SummaryValue(
                        stringResource(R.string.global_out),
                        foreign(totals.outgoing),
                        hint = if (totals.pending > 0) stringResource(R.string.global_pending_n, totals.pending) else null,
                    ),
                ),
            )
        }
        val toReview = rows.filter { it.transaction.needsReview }
        item(key = "statement") {
            Panel {
                Column {
                    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(start = 16.dp, end = 8.dp, top = 12.dp, bottom = 8.dp)) {
                        Column(Modifier.weight(1f)) {
                            Text(stringResource(R.string.global_statement), fontWeight = FontWeight.Bold, fontSize = 16.sp, color = palette.text)
                            Text(stringResource(R.string.global_statement_hint, currency), fontSize = 13.sp, color = palette.muted)
                        }
                        if (toReview.size > 1) {
                            AppButton(
                                stringResource(R.string.global_confirm_all),
                                { viewModel.confirm("all", toReview) },
                                variant = ButtonVariant.SECONDARY,
                                loading = viewModel.savingKey == "all",
                            )
                        }
                    }
                    AppButton(
                        stringResource(R.string.global_pix),
                        viewModel::openPix,
                        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
                    )
                    if (!viewModel.page.loaded) {
                        ListSkeleton(rows = 4, modifier = Modifier.padding(16.dp))
                    } else if (rows.isEmpty()) {
                        EmptyState(stringResource(R.string.global_empty_title), stringResource(R.string.global_empty_message))
                    } else {
                        rows.forEach { row ->
                            HorizontalDivider(color = palette["zinc-100"])
                            StatementRow(row, currency, viewModel)
                        }
                        if (viewModel.nextCursor != null) {
                            HorizontalDivider(color = palette["zinc-100"])
                            AppButton(
                                stringResource(R.string.global_more),
                                viewModel::loadMore,
                                modifier = Modifier.fillMaxWidth().padding(16.dp),
                                variant = ButtonVariant.SECONDARY,
                                loading = viewModel.loadingMore,
                            )
                        }
                    }
                }
            }
        }
    }
    viewModel.account?.let { PixSheet(viewModel, it, GlobalAccount.currencyOf(it)) }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PixSheet(viewModel: GlobalAccountViewModel, account: AccountDto, currency: String) {
    val form = viewModel.pix ?: return
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val palette = LocalPalette.current
    val cancel = stringResource(R.string.lanc_cancel)
    val change = { next: GlobalAccount.PixForm -> viewModel.changePix(next) }
    AppSheet(
        title = stringResource(R.string.global_pix_title, account.name),
        sheetState = sheetState,
        onDismiss = viewModel::closePix,
        footer = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AppButton(cancel, viewModel::closePix, Modifier.weight(1f), variant = ButtonVariant.SECONDARY)
                AppButton(stringResource(R.string.lanc_save), viewModel::savePix, Modifier.weight(1f), loading = viewModel.savingKey == "pix")
            }
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text(stringResource(R.string.global_pix_description, currency), color = palette["zinc-600"], fontSize = 14.sp)
            AlertMessage(viewModel.pixError, AlertTone.DANGER, stringResource(R.string.lanc_dismiss))
            Field(stringResource(R.string.global_pix_from)) {
                SelectField(
                    form.accountId,
                    viewModel.pixSources.map { SelectOption(it.id, it.name) },
                    { change(form.copy(accountId = it)) },
                    placeholder = stringResource(R.string.global_pix_pick),
                )
            }
            Field(stringResource(R.string.global_pix_amount)) {
                AppTextField(form.amount, { change(form.copy(amount = it)) }, placeholder = "0,00", keyboardType = KeyboardType.Decimal)
            }
            Field(stringResource(R.string.global_pix_received, currency)) {
                AppTextField(form.transferAmount, { change(form.copy(transferAmount = it)) }, placeholder = "0,00", keyboardType = KeyboardType.Decimal)
            }
            Field(stringResource(R.string.global_pix_date)) {
                DateField(form.date, { change(form.copy(date = it)) }, stringResource(R.string.lanc_date_ok), cancel)
            }
            Field(stringResource(R.string.global_pix_note)) {
                AppTextField(form.description, { change(form.copy(description = it)) }, placeholder = stringResource(R.string.global_pix_note_placeholder))
            }
        }
    }
}

@Composable
private fun StatementRow(row: GlobalAccount.Row, currency: String, viewModel: GlobalAccountViewModel) {
    val palette = LocalPalette.current
    val transaction = row.transaction
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        modifier = Modifier.heightIn(min = 56.dp).padding(start = 16.dp, end = 8.dp, top = 8.dp, bottom = 8.dp),
    ) {
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(
                    transaction.description.orEmpty().ifBlank { row.counterpart.orEmpty() },
                    fontWeight = FontWeight.Medium,
                    color = palette.text,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f, fill = false),
                )
                if (transaction.needsReview) Badge(stringResource(R.string.global_to_review), BadgeTone.INFO)
            }
            val rate = GlobalAccount.impliedRate(row)
            val from = stringResource(R.string.global_from)
            val to = stringResource(R.string.global_to)
            val detail = buildString {
                append(formatDateBR(transaction.date))
                if (transaction.type == "TRANSFER" && row.counterpart != null) {
                    append(" · ")
                    append(if (row.direction > 0) from else to)
                    append(" ")
                    append(row.counterpart)
                }
                row.sourceAmount?.let { append(" · saiu ").append(formatCurrency(it)) }
                rate?.let { append(" · ").append(formatCurrency(it)).append(" por ").append(currency) }
            }
            Text(detail, fontSize = 12.sp, color = palette.muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        if (row.pending) {
            Text(stringResource(R.string.global_pending_value, currency), fontSize = 13.sp, color = palette.warning)
        } else {
            Text(
                formatSignedForeignCurrency(row.native, row.direction, currency),
                fontWeight = FontWeight.SemiBold,
                color = if (row.direction > 0) palette.gain else palette.text,
                maxLines = 1,
            )
        }
        if (transaction.needsReview) {
            val key = transaction.id
            AppButton(
                stringResource(R.string.global_mine),
                { viewModel.confirm(key, listOf(row)) },
                variant = ButtonVariant.SECONDARY,
                loading = viewModel.savingKey == key,
            )
        }
    }
}
