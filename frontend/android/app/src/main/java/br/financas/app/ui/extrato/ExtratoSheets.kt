package br.financas.app.ui.extrato

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.SheetValue
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.data.TransactionDto
import br.financas.app.rules.EntryOptions
import br.financas.app.rules.ExtratoRules
import br.financas.app.rules.TransactionEditForm
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.AppSheet
import br.financas.app.ui.components.AppTextField
import br.financas.app.ui.components.Badge
import br.financas.app.ui.components.ButtonVariant
import br.financas.app.ui.components.DateField
import br.financas.app.ui.components.Field
import br.financas.app.ui.components.SegmentedChoice
import br.financas.app.ui.components.SelectField
import br.financas.app.ui.components.SelectOption
import br.financas.app.ui.lancamentos.AmountInput
import br.financas.app.ui.lancamentos.ShareFields
import br.financas.app.ui.theme.LocalPalette

/**
 * Editar um lancamento (o formulario inline da web, empilhado): Data, Valor, Descricao,
 * Categoria (ou o destino numa transferencia), Tipo, Conta e "De quem é?". So com o servidor.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun EditTransactionSheet(row: TransactionDto, form: TransactionEditForm, viewModel: ExtratoViewModel) {
    val sheetState = rememberModalBottomSheetState(
        skipPartiallyExpanded = true,
        confirmValueChange = { value -> value != SheetValue.Hidden || !viewModel.saving },
    )
    val transfer = row.type == ExtratoRules.TRANSFER
    val set: (TransactionEditForm) -> Unit = viewModel::changeEditForm
    AppSheet(
        title = stringResource(R.string.extrato_edit_title),
        sheetState = sheetState,
        onDismiss = viewModel::cancelEditing,
        footer = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AppButton(
                    text = stringResource(R.string.extrato_delete_confirm),
                    onClick = { viewModel.askDelete(row) },
                    variant = ButtonVariant.SUBTLE,
                    enabled = !viewModel.saving,
                )
                AppButton(
                    text = stringResource(R.string.lanc_cancel),
                    onClick = viewModel::cancelEditing,
                    variant = ButtonVariant.SECONDARY,
                    enabled = !viewModel.saving,
                    modifier = Modifier.weight(1f),
                )
                AppButton(
                    text = stringResource(R.string.lanc_save),
                    onClick = viewModel::saveEdit,
                    loading = viewModel.saving,
                    modifier = Modifier.weight(1f),
                )
            }
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            AlertMessage(message = viewModel.editError, dismissLabel = stringResource(R.string.lanc_dismiss))
            Field(stringResource(R.string.extrato_edit_amount)) {
                AmountInput(form.amount, { set(form.copy(amount = it)) }, stringResource(R.string.extrato_edit_amount))
            }
            Field(stringResource(R.string.extrato_edit_date)) {
                DateField(form.date, { set(form.copy(date = it)) }, stringResource(R.string.lanc_date_ok), stringResource(R.string.lanc_cancel))
            }
            Field(stringResource(R.string.extrato_edit_description)) {
                AppTextField(form.description, { set(form.copy(description = it)) })
            }
            if (transfer) {
                Badge(stringResource(R.string.extrato_edit_transfer))
                Field(stringResource(R.string.extrato_edit_from)) { AccountSelect(form.accountId, row.accountId, viewModel) { set(form.copy(accountId = it)) } }
                Field(stringResource(R.string.extrato_edit_to)) {
                    AccountSelect(form.transferAccountId, row.transferAccountId, viewModel) { set(form.copy(transferAccountId = it)) }
                }
            } else {
                Field(stringResource(R.string.extrato_edit_type)) {
                    SegmentedChoice(
                        items = listOf(
                            SelectOption(ExtratoRules.EXPENSE, stringResource(R.string.extrato_edit_type_expense)),
                            SelectOption(ExtratoRules.INCOME, stringResource(R.string.extrato_edit_type_income)),
                        ),
                        value = form.type,
                        onChange = { set(form.copy(type = it)) },
                    )
                }
                Field(stringResource(R.string.extrato_edit_category)) {
                    val options = EntryOptions.filterCategoryOptions(viewModel.categoryOptions, form.type)
                    // A categoria que a linha ja tem, quando nao esta na lista (arquivada, do outro
                    // tipo ou texto livre), fica como esta.
                    val keep = if (options.none { it.id == row.categoryId.orEmpty() }) {
                        listOf(SelectOption(row.categoryId.orEmpty(), row.category?.takeIf { it.isNotEmpty() } ?: stringResource(R.string.extrato_edit_no_category)))
                    } else {
                        emptyList()
                    }
                    SelectField(
                        value = form.categoryId,
                        options = keep + options.map { SelectOption(it.id, it.label) },
                        onSelect = { set(form.copy(categoryId = it)) },
                    )
                }
                Field(stringResource(R.string.extrato_edit_account)) { AccountSelect(form.accountId, row.accountId, viewModel) { set(form.copy(accountId = it)) } }
                if (ExtratoRules.canShare(row)) {
                    ShareFields(form.share, { set(form.copy(share = it)) }, income = form.type == ExtratoRules.INCOME, enabled = !viewModel.saving)
                }
            }
        }
    }
}

/** As contas ativas; a da linha, se arquivada, fica como "<nome> (arquivada)". */
@Composable
private fun AccountSelect(value: String, currentId: String?, viewModel: ExtratoViewModel, onSelect: (String) -> Unit) {
    val active = viewModel.activeAccounts
    val archived = if (!currentId.isNullOrEmpty() && active.none { it.id == currentId }) {
        listOf(SelectOption(currentId, stringResource(R.string.extrato_edit_archived, viewModel.accountName(currentId))))
    } else {
        emptyList()
    }
    SelectField(value = value, options = archived + active.map { SelectOption(it.id, it.name) }, onSelect = onSelect)
}

/** "Exportar extrato" (o ExportSheet da web): formato, colunas, e a folha de compartilhar. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun ExportSheet(viewModel: ExtratoViewModel) {
    val palette = LocalPalette.current
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val choice = viewModel.exportChoice
    AppSheet(
        title = stringResource(R.string.extrato_export_title),
        sheetState = sheetState,
        onDismiss = viewModel::closeExport,
        footer = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AppButton(
                    text = stringResource(R.string.lanc_cancel),
                    onClick = viewModel::closeExport,
                    variant = ButtonVariant.SECONDARY,
                    modifier = Modifier.weight(1f),
                )
                AppButton(
                    text = stringResource(R.string.extrato_export_share),
                    onClick = viewModel::export,
                    loading = viewModel.exporting,
                    enabled = choice.columns.isNotEmpty(),
                    modifier = Modifier.weight(1f),
                )
            }
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(stringResource(R.string.extrato_export_description), color = palette["zinc-600"], fontSize = 14.sp)
            AlertMessage(message = viewModel.exportError, dismissLabel = stringResource(R.string.lanc_dismiss))
            SegmentedChoice(
                items = listOf(
                    SelectOption("xlsx", stringResource(R.string.extrato_export_xlsx)),
                    SelectOption("csv", stringResource(R.string.extrato_export_csv)),
                ),
                value = choice.format,
                onChange = { viewModel.changeExport(choice.copy(format = it)) },
            )
            Text(
                stringResource(if (choice.format == "csv") R.string.extrato_export_csv_hint else R.string.extrato_export_xlsx_hint),
                color = palette.muted,
                fontSize = 13.sp,
            )
            val all = viewModel.exportColumns.map { it.key }.toSet()
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(R.string.extrato_export_columns), color = palette.text, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                val allChosen = all.isNotEmpty() && choice.columns.containsAll(all)
                AppButton(
                    text = stringResource(if (allChosen) R.string.extrato_export_none else R.string.extrato_export_all),
                    onClick = { viewModel.changeExport(choice.copy(columns = if (allChosen) emptySet() else all)) },
                    variant = ButtonVariant.SUBTLE,
                )
            }
            viewModel.exportColumns.forEach { column ->
                val checked = column.key in choice.columns
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 48.dp)
                        .clickable {
                            viewModel.changeExport(choice.copy(columns = if (checked) choice.columns - column.key else choice.columns + column.key))
                        },
                ) {
                    Checkbox(
                        checked = checked,
                        onCheckedChange = null,
                        colors = CheckboxDefaults.colors(checkedColor = palette.accent, checkmarkColor = palette.onAccent),
                    )
                    Text(column.label, color = palette.text)
                }
            }
            if (choice.columns.isEmpty()) Text(stringResource(R.string.extrato_export_pick_one), color = palette.loss, fontSize = 13.sp)
        }
    }
}
