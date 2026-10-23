package br.financas.app.ui.newentry

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import br.financas.app.R
import br.financas.app.rules.CardFunctions
import br.financas.app.rules.EntryOptions
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AppSheet
import br.financas.app.ui.components.AppTextField
import br.financas.app.ui.components.DateField
import br.financas.app.ui.components.Field
import br.financas.app.ui.components.SegmentedChoice
import br.financas.app.ui.components.SelectField
import br.financas.app.ui.components.SelectOption
import br.financas.app.ui.theme.LocalPalette
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** Para onde os links do "+ Novo" levam (rotas da web, ainda React). */
const val ROUTE_ACCOUNTS = "/ajustes#contas"
const val ROUTE_CARDS = "/ajustes#cartoes"

private data class TypeButton(val value: String, val shortLabel: Int, val label: Int, val icon: Int)

private val TYPE_BUTTONS = listOf(
    TypeButton(EntryType.EXPENSE, R.string.newentry_type_expense, R.string.newentry_type_expense, R.drawable.ic_entry_expense),
    TypeButton(EntryType.INCOME, R.string.newentry_type_income, R.string.newentry_type_income, R.drawable.ic_entry_income),
    TypeButton(EntryType.TRANSFER, R.string.newentry_type_transfer_short, R.string.newentry_type_transfer, R.drawable.ic_entry_transfer),
    TypeButton(EntryType.CARD, R.string.newentry_type_card_short, R.string.newentry_type_card, R.drawable.ic_entry_card),
)

/**
 * O "+ Novo" nativo: o NewEntrySheet.jsx em Compose. O tipo no alto, a caixa de erro e o
 * formulario do tipo, o valor primeiro (grande, com o foco e o teclado numerico).
 * [onClose] fecha sem gravar; [onNavigate] fecha e abre uma rota da web (Ajustes).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NewEntryScreen(
    viewModel: NewEntryViewModel,
    onClose: () -> Unit,
    onNavigate: (String) -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val scope = rememberCoroutineScope()
    val haptic = LocalHapticFeedback.current
    val amountFocus = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current

    val hideThen: (() -> Unit) -> Unit = { action ->
        scope.launch { sheetState.hide() }.invokeOnCompletion { action() }
    }

    // O valor recebe o foco ao abrir e ao trocar de tipo (o autoFocus de cada formulario na web).
    LaunchedEffect(viewModel.type) {
        delay(120)
        try {
            amountFocus.requestFocus()
            keyboard?.show()
        } catch (ignored: IllegalStateException) {
            // Sem campo de valor (Cartao sem cartao): nada a focar.
        }
    }

    LaunchedEffect(viewModel.finished) {
        if (viewModel.finished != null) haptic.performHapticFeedback(HapticFeedbackType.LongPress)
    }

    val title = stringResource(if (viewModel.editingClientId != null) R.string.newentry_title_edit else R.string.newentry_title)
    AppSheet(
        title = title,
        sheetState = sheetState,
        onDismiss = onClose,
        footer = {
            Footer(
                saving = viewModel.saving,
                enabled = !viewModel.cannotSave,
                onCancel = { hideThen(onClose) },
                onSave = { viewModel.save() },
            )
        },
    ) {
        TypePicker(value = viewModel.type, onChange = viewModel::changeType)
        Spacer(Modifier.height(16.dp))
        AlertMessage(
            message = viewModel.error,
            dismissLabel = stringResource(R.string.newentry_dismiss_error),
            onDismiss = viewModel::dismissError,
            modifier = Modifier.padding(bottom = 16.dp),
        )
        val navigate: (String) -> Unit = { route -> hideThen { onNavigate(route) } }
        when (viewModel.type) {
            EntryType.TRANSFER -> TransferFields(viewModel, amountFocus, navigate)
            EntryType.CARD -> CardFields(viewModel, amountFocus, navigate)
            else -> BankFields(viewModel, amountFocus, navigate)
        }
    }
}

@Composable
private fun Footer(saving: Boolean, enabled: Boolean, onCancel: () -> Unit, onSave: () -> Unit) {
    val palette = LocalPalette.current
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
        OutlinedButton(
            onClick = onCancel,
            modifier = Modifier.weight(1f).heightIn(min = 52.dp),
            shape = RoundedCornerShape(16.dp),
            border = BorderStroke(1.dp, palette["zinc-300"]),
            colors = ButtonDefaults.outlinedButtonColors(contentColor = palette.text),
        ) {
            Text(stringResource(R.string.newentry_cancel), fontWeight = FontWeight.Bold)
        }
        Button(
            onClick = onSave,
            enabled = enabled && !saving,
            modifier = Modifier.weight(1f).heightIn(min = 52.dp),
            shape = RoundedCornerShape(16.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = palette.accent,
                contentColor = palette.onAccent,
                disabledContainerColor = palette["zinc-200"],
                disabledContentColor = palette.muted,
            ),
        ) {
            if (saving) {
                CircularProgressIndicator(
                    modifier = Modifier.size(18.dp),
                    strokeWidth = 2.dp,
                    color = palette.muted,
                )
                Spacer(Modifier.width(8.dp))
            }
            Text(stringResource(R.string.newentry_save), fontWeight = FontWeight.Bold)
        }
    }
}

// Os quatro tipos numa linha, icone sobre o rotulo, 56 dp: o polegar acerta sem mirar.
@Composable
private fun TypePicker(value: String, onChange: (String) -> Unit) {
    val palette = LocalPalette.current
    val groupLabel = stringResource(R.string.newentry_type_group)
    Surface(
        shape = RoundedCornerShape(22.dp),
        color = palette.surface,
        border = BorderStroke(1.dp, palette.border),
        modifier = Modifier.fillMaxWidth().semantics { contentDescription = groupLabel },
    ) {
        Row(modifier = Modifier.padding(4.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            TYPE_BUTTONS.forEach { button ->
                val active = button.value == value
                val label = stringResource(button.label)
                Surface(
                    selected = active,
                    onClick = { onChange(button.value) },
                    shape = RoundedCornerShape(18.dp),
                    color = if (active) palette["zinc-100"] else palette.surface,
                    contentColor = if (active) palette.text else palette["zinc-600"],
                    modifier = Modifier
                        .weight(1f)
                        .height(56.dp)
                        .semantics { contentDescription = label },
                ) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center,
                    ) {
                        Icon(
                            painter = painterResource(button.icon),
                            contentDescription = null,
                            modifier = Modifier.size(20.dp),
                        )
                        Spacer(Modifier.height(4.dp))
                        Text(
                            text = stringResource(button.shortLabel),
                            style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.SemiBold,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.padding(horizontal = 4.dp),
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun amountStyle(): TextStyle =
    MaterialTheme.typography.headlineSmall.copy(fontWeight = FontWeight.Bold)

@Composable
private fun AmountField(value: String, onChange: (String) -> Unit, focus: FocusRequester, label: String) {
    AppTextField(
        value = value,
        onValueChange = onChange,
        placeholder = stringResource(R.string.newentry_amount_placeholder),
        keyboardType = KeyboardType.Decimal,
        textStyle = amountStyle(),
        focusRequester = focus,
        contentDescription = label,
    )
}

@Composable
private fun DateInput(value: String, onChange: (String) -> Unit, label: String) {
    DateField(
        value = value,
        onChange = onChange,
        confirmLabel = stringResource(R.string.newentry_date_ok),
        cancelLabel = stringResource(R.string.newentry_date_cancel),
        contentDescription = label,
    )
}

/** Um texto com um link no meio (o settingsLink da web). */
@Composable
private fun LinkLine(before: String, link: String, after: String, onClick: () -> Unit) {
    val palette = LocalPalette.current
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
        if (before.isNotEmpty()) {
            Text("$before ", style = MaterialTheme.typography.bodyMedium, color = palette["zinc-600"])
        }
        Surface(onClick = onClick, color = palette.surface, modifier = Modifier.heightIn(min = 48.dp)) {
            Box(contentAlignment = Alignment.CenterStart) {
                Text(
                    text = link,
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = palette["emerald-700"],
                    textDecoration = TextDecoration.Underline,
                )
            }
        }
        if (after.isNotEmpty()) {
            Text(" $after", style = MaterialTheme.typography.bodyMedium, color = palette["zinc-600"])
        }
    }
}

private val FieldGap = 16.dp

@Composable
private fun BankFields(viewModel: NewEntryViewModel, amountFocus: FocusRequester, navigate: (String) -> Unit) {
    val form = viewModel.bank
    val amountLabel = stringResource(R.string.newentry_amount)
    Column(verticalArrangement = Arrangement.spacedBy(FieldGap)) {
        Field(label = amountLabel) {
            AmountField(form.amount, { viewModel.updateBank(form.copy(amount = it)) }, amountFocus, amountLabel)
        }
        val categoryLabel = stringResource(R.string.newentry_category)
        Field(label = categoryLabel) {
            SelectField(
                value = form.categoryId,
                options = EntryOptions.filterCategoryOptions(viewModel.categoryOptions, form.type)
                    .map { SelectOption(it.id, it.label) },
                onSelect = { viewModel.updateBank(form.copy(categoryId = it)) },
                placeholder = stringResource(R.string.newentry_select),
                contentDescription = categoryLabel,
            )
        }
        val descriptionLabel = stringResource(R.string.newentry_description)
        Field(label = descriptionLabel) {
            AppTextField(
                value = form.description,
                onValueChange = { viewModel.updateBank(form.copy(description = it)) },
                placeholder = stringResource(
                    if (form.type == EntryType.INCOME) R.string.newentry_description_income_placeholder
                    else R.string.newentry_description_expense_placeholder,
                ),
                contentDescription = descriptionLabel,
            )
        }
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            val dateLabel = stringResource(R.string.newentry_date)
            Field(label = dateLabel, modifier = Modifier.weight(1f)) {
                DateInput(form.date, { viewModel.updateBank(form.copy(date = it)) }, dateLabel)
            }
            val accountLabel = stringResource(R.string.newentry_account)
            Field(label = accountLabel, modifier = Modifier.weight(1f)) {
                SelectField(
                    value = form.accountId.ifEmpty { viewModel.defaultAccountId },
                    options = viewModel.accounts.map { SelectOption(it.id, it.name) },
                    onSelect = { viewModel.updateBank(form.copy(accountId = it)) },
                    contentDescription = accountLabel,
                )
            }
        }
        if (!viewModel.lists.loading && viewModel.accounts.isEmpty()) {
            LinkLine(
                before = stringResource(R.string.newentry_no_accounts),
                link = stringResource(R.string.newentry_no_accounts_link),
                after = ".",
                onClick = { navigate(ROUTE_ACCOUNTS) },
            )
        }
    }
}

@Composable
private fun TransferFields(viewModel: NewEntryViewModel, amountFocus: FocusRequester, navigate: (String) -> Unit) {
    val form = viewModel.transfer
    val accounts = viewModel.accounts
    val amountLabel = stringResource(R.string.newentry_amount)
    val select = stringResource(R.string.newentry_select)
    Column(verticalArrangement = Arrangement.spacedBy(FieldGap)) {
        Field(label = amountLabel) {
            AmountField(form.amount, { viewModel.updateTransfer(form.copy(amount = it)) }, amountFocus, amountLabel)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            val fromLabel = stringResource(R.string.newentry_from)
            Field(label = fromLabel, modifier = Modifier.weight(1f)) {
                SelectField(
                    value = form.accountId,
                    options = accounts.map { SelectOption(it.id, it.name) },
                    onSelect = { viewModel.updateTransfer(form.copy(accountId = it)) },
                    placeholder = select,
                    contentDescription = fromLabel,
                )
            }
            val toLabel = stringResource(R.string.newentry_to)
            Field(label = toLabel, modifier = Modifier.weight(1f)) {
                SelectField(
                    value = form.transferAccountId,
                    options = accounts.filter { it.id != form.accountId }.map { SelectOption(it.id, it.name) },
                    onSelect = { viewModel.updateTransfer(form.copy(transferAccountId = it)) },
                    placeholder = select,
                    contentDescription = toLabel,
                )
            }
        }
        val dateLabel = stringResource(R.string.newentry_date)
        Field(label = dateLabel) {
            DateInput(form.date, { viewModel.updateTransfer(form.copy(date = it)) }, dateLabel)
        }
        val descriptionLabel = stringResource(R.string.newentry_description)
        Field(label = descriptionLabel, hint = stringResource(R.string.newentry_optional)) {
            AppTextField(
                value = form.description,
                onValueChange = { viewModel.updateTransfer(form.copy(description = it)) },
                placeholder = stringResource(R.string.newentry_transfer_description_placeholder),
                contentDescription = descriptionLabel,
            )
        }
        if (!viewModel.lists.loading && accounts.size < 2) {
            LinkLine(
                before = stringResource(R.string.newentry_transfer_needs_two_before),
                link = stringResource(R.string.newentry_transfer_needs_two_link),
                after = stringResource(R.string.newentry_transfer_needs_two_after),
                onClick = { navigate(ROUTE_ACCOUNTS) },
            )
        }
    }
}

@Composable
private fun CardFields(viewModel: NewEntryViewModel, amountFocus: FocusRequester, navigate: (String) -> Unit) {
    val palette = LocalPalette.current
    val cards = viewModel.cards
    if (!viewModel.lists.loading && cards.isEmpty()) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.fillMaxWidth().heightIn(min = 160.dp).padding(vertical = 16.dp),
        ) {
            Icon(
                painter = painterResource(R.drawable.ic_entry_card),
                contentDescription = null,
                tint = palette.muted,
                modifier = Modifier.size(28.dp),
            )
            Text(
                text = stringResource(R.string.newentry_card_empty_title),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = palette.text,
                textAlign = TextAlign.Center,
            )
            Text(
                text = stringResource(R.string.newentry_card_empty_message),
                style = MaterialTheme.typography.bodyMedium,
                color = palette["zinc-600"],
                textAlign = TextAlign.Center,
            )
            Surface(onClick = { navigate(ROUTE_CARDS) }, color = palette.surface, modifier = Modifier.heightIn(min = 48.dp)) {
                Box(contentAlignment = Alignment.Center) {
                    Text(
                        text = stringResource(R.string.newentry_card_empty_action),
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.SemiBold,
                        color = palette["emerald-700"],
                        textDecoration = TextDecoration.Underline,
                    )
                }
            }
        }
        return
    }

    val form = viewModel.card
    val selected = cards.firstOrNull { it.id == form.cardId }
    val rulesCard = selected?.let(NewEntryForms::cardOf)
    val method = CardFunctions.resolveCardMethod(rulesCard, form.method)
    val debit = method == CardFunctions.DEBIT
    val amountLabel = stringResource(if (debit) R.string.newentry_amount else R.string.newentry_amount_total)
    Column(verticalArrangement = Arrangement.spacedBy(FieldGap)) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Field(label = amountLabel, modifier = Modifier.weight(1f)) {
                AmountField(form.totalAmount, { viewModel.updateCard(form.copy(totalAmount = it)) }, amountFocus, amountLabel)
            }
            if (!debit) {
                val installmentsLabel = stringResource(R.string.newentry_installments)
                Field(label = installmentsLabel, modifier = Modifier.width(104.dp)) {
                    AppTextField(
                        value = form.installments,
                        onValueChange = { text -> viewModel.updateCard(form.copy(installments = text.filter { it.isDigit() }.take(2))) },
                        keyboardType = KeyboardType.Number,
                        textStyle = amountStyle().copy(textAlign = TextAlign.Center),
                        contentDescription = installmentsLabel,
                    )
                }
            }
        }
        val categoryLabel = stringResource(R.string.newentry_category)
        Field(label = categoryLabel) {
            SelectField(
                value = form.categoryId,
                options = EntryOptions.filterCategoryOptions(viewModel.categoryOptions, EntryType.EXPENSE)
                    .map { SelectOption(it.id, it.label) },
                onSelect = { viewModel.updateCard(form.copy(categoryId = it)) },
                placeholder = stringResource(R.string.newentry_select),
                contentDescription = categoryLabel,
            )
        }
        val descriptionLabel = stringResource(R.string.newentry_description)
        Field(label = descriptionLabel) {
            AppTextField(
                value = form.description,
                onValueChange = { viewModel.updateCard(form.copy(description = it)) },
                placeholder = stringResource(R.string.newentry_card_description_placeholder),
                contentDescription = descriptionLabel,
            )
        }
        val cardLabel = stringResource(R.string.newentry_card)
        Field(label = cardLabel) {
            val creditOption = stringResource(R.string.newentry_card_option_credit)
            val debitOption = stringResource(R.string.newentry_card_option_debit)
            SelectField(
                value = form.cardId,
                options = cards.map { card ->
                    val label = if (CardFunctions.hasCredit(NewEntryForms.cardOf(card))) {
                        String.format(creditOption, card.name, card.dueDay?.toString().orEmpty())
                    } else {
                        String.format(debitOption, card.name)
                    }
                    SelectOption(card.id, label)
                },
                onSelect = { viewModel.updateCard(form.copy(cardId = it)) },
                placeholder = stringResource(R.string.newentry_select),
                contentDescription = cardLabel,
            )
            if (CardFunctions.cardMethods(rulesCard).size > 1) {
                Spacer(Modifier.height(8.dp))
                SegmentedChoice(
                    items = listOf(
                        SelectOption(CardFunctions.CREDIT, stringResource(R.string.newentry_method_credit)),
                        SelectOption(CardFunctions.DEBIT, stringResource(R.string.newentry_method_debit)),
                    ),
                    value = method,
                    onChange = { viewModel.updateCard(form.copy(method = it)) },
                )
            }
            if (debit) {
                val accountName = viewModel.accounts.firstOrNull { it.id == selected?.debitAccountId }?.name
                    ?: stringResource(R.string.newentry_debit_hint_fallback)
                Text(
                    text = stringResource(R.string.newentry_debit_hint, accountName),
                    style = MaterialTheme.typography.bodyMedium,
                    color = palette["zinc-600"],
                    modifier = Modifier.padding(top = 4.dp),
                )
            }
        }
        val dateLabel = stringResource(R.string.newentry_purchase_date)
        Field(label = dateLabel) {
            DateInput(form.purchaseDate, { viewModel.updateCard(form.copy(purchaseDate = it)) }, dateLabel)
        }
    }
}
