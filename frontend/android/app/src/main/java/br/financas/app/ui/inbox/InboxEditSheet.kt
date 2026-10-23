package br.financas.app.ui.inbox

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import br.financas.app.R
import br.financas.app.data.InboxItemDto
import br.financas.app.rules.InboxRules
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.AppSheet
import br.financas.app.ui.components.AppTextField
import br.financas.app.ui.components.ButtonVariant
import br.financas.app.ui.components.DateField
import br.financas.app.ui.components.Field
import br.financas.app.ui.components.SegmentedChoice
import br.financas.app.ui.components.SelectField
import br.financas.app.ui.components.SelectOption
import br.financas.app.ui.components.TimeField
import br.financas.app.ui.theme.LocalPalette

/**
 * "Corrigir antes de aprovar" (o EditSheet de Aprovar.jsx): tipo, valor, data e hora, descricao,
 * categoria, conta/cartao, parcelas. Salva so o que mudou (InboxRules.changesFromDraft), com a
 * versao do item; "Salvar e aprovar" manda o mesmo corpo para o approve.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun InboxEditSheet(item: InboxItemDto, viewModel: InboxViewModel) {
    val palette = LocalPalette.current
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var draft by remember(item.id, item.version) { mutableStateOf(InboxRules.draftFromItem(item.rule)) }
    val type = draft.entryType
    val choose = stringResource(R.string.inbox_choose)
    val accounts = viewModel.pickerAccounts
    val enabled = !viewModel.offline

    AppSheet(
        title = stringResource(R.string.inbox_edit_title),
        sheetState = sheetState,
        onDismiss = viewModel::closeEdit,
        footer = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                AppButton(
                    text = stringResource(R.string.inbox_edit_approve),
                    onClick = { viewModel.saveEdit(item, draft, andApprove = true) },
                    loading = viewModel.editSaving == "approve",
                    enabled = enabled && viewModel.editSaving.isEmpty(),
                    modifier = Modifier.fillMaxWidth(),
                )
                AppButton(
                    text = stringResource(R.string.inbox_edit_save),
                    onClick = { viewModel.saveEdit(item, draft, andApprove = false) },
                    variant = ButtonVariant.SECONDARY,
                    loading = viewModel.editSaving == "save",
                    enabled = enabled && viewModel.editSaving.isEmpty(),
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
    ) {
        Text(
            text = stringResource(R.string.inbox_edit_description, InboxRules.whenText(item.sourceOccurredAt)),
            style = MaterialTheme.typography.bodyMedium,
            color = palette.muted,
        )
        Spacer(Modifier.height(12.dp))
        AlertMessage(
            message = viewModel.error,
            dismissLabel = stringResource(R.string.inbox_dismiss_error),
            onDismiss = viewModel::dismissError,
            modifier = Modifier.padding(bottom = 12.dp),
        )
        Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
            SegmentedChoice(
                items = InboxRules.ENTRY_TYPE_LABELS.map { (value, label) ->
                    SelectOption(value, if (value == "CARD") stringResource(R.string.inbox_type_card_short) else label)
                },
                value = type,
                onChange = { draft = draft.copy(entryType = it) },
            )
            Field(label = stringResource(R.string.inbox_edit_amount)) {
                AppTextField(
                    value = draft.amount,
                    onValueChange = { draft = draft.copy(amount = it) },
                    keyboardType = KeyboardType.Decimal,
                    textStyle = MaterialTheme.typography.headlineSmall.copy(fontWeight = FontWeight.Bold),
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Field(label = stringResource(R.string.inbox_edit_date), modifier = Modifier.weight(1f)) {
                    DateField(
                        value = draft.date,
                        onChange = { draft = draft.copy(date = it) },
                        confirmLabel = stringResource(R.string.inbox_ok),
                        cancelLabel = stringResource(R.string.inbox_cancel),
                    )
                }
                Field(
                    label = stringResource(R.string.inbox_edit_time),
                    hint = if (draft.time.isEmpty()) stringResource(R.string.inbox_edit_time_missing) else null,
                    modifier = Modifier.weight(1f),
                ) {
                    TimeField(
                        value = draft.time,
                        onChange = { draft = draft.copy(time = it) },
                        confirmLabel = stringResource(R.string.inbox_ok),
                        cancelLabel = stringResource(R.string.inbox_cancel),
                        clearLabel = stringResource(R.string.inbox_edit_time_clear),
                    )
                }
            }
            Field(label = stringResource(R.string.inbox_edit_description_label)) {
                AppTextField(value = draft.description, onValueChange = { draft = draft.copy(description = it) })
            }
            if (type != "TRANSFER") {
                Field(label = stringResource(R.string.inbox_edit_category)) {
                    SelectField(
                        value = draft.categoryId,
                        options = InboxLogic.editCategoryOptions(viewModel.categoryOptions, type, item)
                            .map { (value, label) -> SelectOption(value, label) },
                        onSelect = { draft = draft.copy(categoryId = it) },
                        placeholder = stringResource(R.string.inbox_edit_category_suggested),
                    )
                }
            }
            if (type == "CARD") {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Field(label = stringResource(R.string.inbox_edit_card), modifier = Modifier.weight(1f)) {
                        SelectField(
                            value = draft.cardId,
                            options = viewModel.pickerCards.map { SelectOption(it.id, it.name) },
                            onSelect = { draft = draft.copy(cardId = it) },
                            placeholder = choose,
                        )
                    }
                    Field(label = stringResource(R.string.inbox_edit_installments), modifier = Modifier.weight(1f)) {
                        AppTextField(
                            value = draft.installments,
                            onValueChange = { draft = draft.copy(installments = it) },
                            keyboardType = KeyboardType.Number,
                        )
                    }
                }
            }
            if (type == "EXPENSE" || type == "INCOME" || type == "TRANSFER") {
                Field(label = stringResource(if (type == "TRANSFER") R.string.inbox_edit_from else R.string.inbox_edit_account)) {
                    SelectField(
                        value = draft.accountId,
                        options = accounts.map { SelectOption(it.id, it.name) },
                        onSelect = { draft = draft.copy(accountId = it) },
                        placeholder = choose,
                    )
                }
            }
            if (type == "TRANSFER") {
                Field(label = stringResource(R.string.inbox_edit_to)) {
                    SelectField(
                        value = draft.transferAccountId,
                        options = InboxLogic.destinationAccounts(accounts, draft.accountId).map { SelectOption(it.id, it.name) },
                        onSelect = { draft = draft.copy(transferAccountId = it) },
                        placeholder = choose,
                    )
                }
                Text(stringResource(R.string.inbox_edit_transfer_note), style = MaterialTheme.typography.bodyMedium, color = palette.muted)
            }
        }
    }
}
