package br.financas.app.ui.extrato

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
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
import br.financas.app.core.formatSignedCurrency
import br.financas.app.data.InboxItemDto
import br.financas.app.rules.InboxRules
import br.financas.app.rules.ReviewRules
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AlertTone
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.AppTextField
import br.financas.app.ui.components.ButtonVariant
import br.financas.app.ui.components.Field
import br.financas.app.ui.components.Panel
import br.financas.app.ui.components.SelectField
import br.financas.app.ui.components.SelectOption
import br.financas.app.ui.theme.LocalPalette

/**
 * O que nao gravou sozinho (a transferencia entre contas do dono com uma ponta so, outra moeda; tudo,
 * com Gravar sozinho desligado). A tela Aprovar saiu do celular: aqui o dono diz a outra conta (ou o
 * valor em reais) e grava, grava como despesa/receita ou descarta.
 */
@Composable
fun WaitingPanel(viewModel: ExtratoViewModel) {
    val items = viewModel.waitingItems
    if (viewModel.reviewWaiting <= 0 && items.isEmpty()) return
    val palette = LocalPalette.current
    Panel {
        Column {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(stringResource(R.string.review_waiting_title), color = palette.text, fontWeight = FontWeight.Bold, fontSize = 17.sp)
                Text(ReviewRules.waitingNoticeText(maxOf(items.size, viewModel.reviewWaiting)), color = palette.muted, fontSize = 13.sp)
            }
            items.forEach { item ->
                HorizontalDivider(color = palette["zinc-100"])
                WaitingItemRow(item, viewModel)
            }
        }
    }
}

@Composable
private fun WaitingItemRow(item: InboxItemDto, viewModel: ExtratoViewModel) {
    val palette = LocalPalette.current
    val choice = viewModel.waitingChoice(item)
    val busy = viewModel.waitingBusy.isNotEmpty()
    val sign = InboxRules.amountSign(item.rule)
    val fixes = ReviewRules.waitingFixes(item)
    val computer = ReviewRules.waitingNeedsComputer(item)
    Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(ReviewRules.waitingTitle(item), color = palette.text, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(ReviewRules.waitingLine(item), color = palette.muted, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(ReviewRules.waitingReason(item), color = palette["amber-800"], fontSize = 12.sp)
            }
            Text(formatSignedCurrency(item.amount, sign), color = if (sign > 0) palette["emerald-700"] else palette.text, fontWeight = FontWeight.Bold, maxLines = 1)
        }
        val accounts = ReviewRules.waitingAccountOptions(viewModel.activeAccounts, item).map { SelectOption(it.id, it.name) }
        val pick = stringResource(R.string.review_waiting_pick)
        if (ReviewRules.WaitingFix.ACCOUNT in fixes) {
            Field(stringResource(R.string.review_waiting_from)) {
                SelectField(choice.accountId, accounts, { viewModel.changeWaiting(item, choice.copy(accountId = it)) }, placeholder = pick)
            }
        }
        if (ReviewRules.WaitingFix.TRANSFER_ACCOUNT in fixes) {
            Field(stringResource(R.string.review_waiting_to)) {
                SelectField(choice.transferAccountId, accounts, { viewModel.changeWaiting(item, choice.copy(transferAccountId = it)) }, placeholder = pick)
            }
        }
        if (ReviewRules.WaitingFix.AMOUNT in fixes) {
            Field(stringResource(R.string.review_waiting_amount)) {
                AppTextField(choice.amount, { viewModel.changeWaiting(item, choice.copy(amount = it)) }, keyboardType = KeyboardType.Decimal)
            }
        }
        val transferCurrency = viewModel.waitingTransferCurrency(item)
        if (!computer && transferCurrency != null) {
            // Pix de reais para a conta global (047): quanto entrou nela, na moeda dela.
            Field(stringResource(R.string.review_waiting_transfer_amount, transferCurrency)) {
                AppTextField(choice.transferAmount, { viewModel.changeWaiting(item, choice.copy(transferAmount = it)) }, keyboardType = KeyboardType.Decimal)
            }
        }
        if (computer) {
            AlertMessage(stringResource(R.string.review_waiting_computer), AlertTone.INFO, stringResource(R.string.lanc_dismiss))
        } else {
            val missing = viewModel.waitingMissing(item)
            AppButton(
                text = stringResource(R.string.review_waiting_record),
                onClick = { viewModel.recordWaiting(item) },
                enabled = !busy && missing.isEmpty(),
                loading = viewModel.waitingBusy == item.id,
                modifier = Modifier.fillMaxWidth(),
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (ReviewRules.waitingCanBeSingle(item)) {
                AppButton(
                    text = stringResource(if (ReviewRules.singleType(item) == "INCOME") R.string.review_waiting_as_income else R.string.review_waiting_as_expense),
                    onClick = { viewModel.recordWaitingSingle(item) },
                    variant = ButtonVariant.SECONDARY,
                    enabled = !busy,
                    modifier = Modifier.weight(1f),
                )
            }
            AppButton(
                text = stringResource(R.string.review_waiting_deny),
                onClick = { viewModel.askDenyWaiting(item) },
                variant = ButtonVariant.SUBTLE,
                enabled = !busy,
            )
        }
    }
}
