package br.financas.app.ui.ajustes

import android.app.Activity
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.SheetValue
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.core.maskEmail
import br.financas.app.data.AccountDto
import br.financas.app.data.CategoryDto
import br.financas.app.data.CreditCardDto
import br.financas.app.data.OpenFinanceCheckDto
import br.financas.app.data.OpenFinanceItemDto
import br.financas.app.data.OpenFinanceSettingsDto
import br.financas.app.rules.ApkUpdateTexts
import br.financas.app.rules.Card
import br.financas.app.rules.CardFunctions
import br.financas.app.rules.GlobalAccount
import br.financas.app.rules.NotifyTexts
import br.financas.app.rules.OpenFinanceRules
import br.financas.app.core.formatDateBR
import br.financas.app.rules.PortfolioView
import br.financas.app.rules.Settings
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AlertTone
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.AppIcons
import br.financas.app.ui.components.AppSheet
import br.financas.app.ui.components.AppTextField
import br.financas.app.ui.components.Badge
import br.financas.app.ui.components.BadgeTone
import br.financas.app.ui.components.ButtonVariant
import br.financas.app.ui.components.ConfirmDialog
import br.financas.app.ui.components.EmptyState
import br.financas.app.ui.components.Field
import br.financas.app.ui.components.ListSkeleton
import br.financas.app.ui.components.MenuAction
import br.financas.app.ui.components.NativeTopBar
import br.financas.app.ui.components.OverflowMenu
import br.financas.app.ui.components.Panel
import br.financas.app.ui.components.SegmentedChoice
import br.financas.app.ui.components.SelectField
import br.financas.app.ui.components.SelectOption
import br.financas.app.ui.lancamentos.moneyOrMasked
import br.financas.app.ui.planejar.PlanejarScaffold
import br.financas.app.ui.theme.LocalPalette

/**
 * Ajustes nativo (11-ajustes.md): a lista de secoes e, por cima dela, a secao aberta. Regras de
 * importação e Integrações abrem a pagina da web (#regras-de-importacao, #integracoes).
 */
@Composable
fun AjustesScreen(
    viewModel: AjustesViewModel,
    onBack: () -> Unit,
    onOpenLink: (String) -> Unit,
    onSignedOut: () -> Unit,
) {
    val section = viewModel.section
    BackHandler(enabled = section != null, onBack = viewModel::closeSection)
    val title = section?.let { stringResource(titleOf(it)) } ?: stringResource(R.string.ajustes_title)
    PlanejarScaffold(
        notices = viewModel.notices,
        onRefresh = viewModel::refreshAll,
        topBar = {
            NativeTopBar(
                title = title,
                onBack = { if (section != null) viewModel.closeSection() else onBack() },
                hidden = viewModel.hidden,
                onToggleHidden = if (section == AjustesSection.CONTAS) viewModel::toggleHidden else null,
            )
        },
    ) {
        item(key = "error") {
            AlertMessage(viewModel.error, AlertTone.DANGER, stringResource(R.string.lanc_dismiss), onDismiss = viewModel::dismissError)
        }
        when (section) {
            null -> sectionList(viewModel)
            AjustesSection.CONTAS -> contas(viewModel, onOpenLink)
            AjustesSection.CARTOES -> cartoes(viewModel, onOpenLink)
            AjustesSection.CATEGORIAS -> categorias(viewModel)
            AjustesSection.APROVAR -> item(key = "aprovar") { AprovarSection(viewModel) }
            AjustesSection.OPEN_FINANCE -> item(key = "open-finance") { OpenFinanceSection(viewModel) }
            AjustesSection.APARENCIA -> item(key = "aparencia") { AparenciaSection(viewModel) }
            AjustesSection.PERFIL -> item(key = "perfil") { PerfilSection(viewModel, onSignedOut) }
            AjustesSection.NOTIFICACOES -> item(key = "notificacoes") { NotificacoesSection(viewModel) }
            AjustesSection.VERSAO -> item(key = "versao") { VersaoSection(viewModel) }
        }
    }
    viewModel.editingAccount?.let { EditAccountSheet(it, viewModel) }
    viewModel.editingCard?.let { EditCardSheet(it, viewModel) }
    ConfirmDialog(viewModel.confirm, stringResource(R.string.lanc_cancel), viewModel::dismissConfirm)
}

private fun titleOf(section: AjustesSection): Int = when (section) {
    AjustesSection.CONTAS -> R.string.ajustes_contas
    AjustesSection.CARTOES -> R.string.ajustes_cartoes
    AjustesSection.CATEGORIAS -> R.string.ajustes_categorias
    AjustesSection.APROVAR -> R.string.ajustes_aprovar
    AjustesSection.OPEN_FINANCE -> R.string.ajustes_open_finance
    AjustesSection.APARENCIA -> R.string.ajustes_aparencia
    AjustesSection.PERFIL -> R.string.ajustes_perfil
    AjustesSection.NOTIFICACOES -> R.string.ajustes_notificacoes
    AjustesSection.VERSAO -> R.string.ajustes_versao
}

private fun hintOf(section: AjustesSection): Int = when (section) {
    AjustesSection.CONTAS -> R.string.ajustes_contas_hint
    AjustesSection.CARTOES -> R.string.ajustes_cartoes_hint
    AjustesSection.CATEGORIAS -> R.string.ajustes_categorias_hint
    AjustesSection.APROVAR -> R.string.ajustes_aprovar_hint
    AjustesSection.OPEN_FINANCE -> R.string.ajustes_open_finance_hint
    AjustesSection.APARENCIA -> R.string.ajustes_aparencia_hint
    AjustesSection.PERFIL -> R.string.ajustes_perfil_hint
    AjustesSection.NOTIFICACOES -> R.string.ajustes_notificacoes_hint
    AjustesSection.VERSAO -> R.string.ajustes_versao_hint
}

private fun LazyListScope.sectionList(viewModel: AjustesViewModel) {
    item(key = "intro") {
        val palette = LocalPalette.current
        Text(stringResource(R.string.ajustes_description), fontSize = 14.sp, color = palette["zinc-600"])
    }
    item(key = "list") {
        val palette = LocalPalette.current
        Panel {
            Column {
                AjustesSection.entries.forEachIndexed { index, section ->
                    if (index > 0) HorizontalDivider(color = palette["zinc-100"])
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(min = 64.dp)
                            .clickable { viewModel.open(section) }
                            .padding(horizontal = 16.dp, vertical = 10.dp),
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text(stringResource(titleOf(section)), fontWeight = FontWeight.SemiBold, color = palette.text)
                            Text(stringResource(hintOf(section)), fontSize = 13.sp, color = palette.muted, maxLines = 2, overflow = TextOverflow.Ellipsis)
                        }
                        Icon(AppIcons.ChevronRight, null, tint = palette.muted, modifier = Modifier.size(18.dp))
                    }
                }
            }
        }
    }
    item(key = "desktop-only") {
        Text(stringResource(R.string.ajustes_desktop_only), fontSize = 13.sp, color = LocalPalette.current.muted)
    }
}

@Composable
private fun Collapsible(label: String, open: Boolean, onToggle: () -> Unit, content: @Composable () -> Unit) {
    val palette = LocalPalette.current
    Column {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable(onClick = onToggle).padding(horizontal = 16.dp),
        ) {
            Text(label, fontWeight = FontWeight.SemiBold, color = palette.text, modifier = Modifier.weight(1f))
            Icon(AppIcons.ChevronDown, null, tint = palette.muted, modifier = Modifier.size(18.dp).rotate(if (open) 180f else 0f))
        }
        if (open) Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) { content() }
    }
}

@Composable
private fun SectionHeader(title: String, description: String, badge: String? = null) {
    val palette = LocalPalette.current
    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, fontWeight = FontWeight.Bold, fontSize = 17.sp, color = palette.text, modifier = Modifier.weight(1f))
            if (badge != null) Badge(badge)
        }
        Text(description, fontSize = 13.sp, color = palette.muted)
    }
}

// ---- Contas ----

private fun LazyListScope.contas(viewModel: AjustesViewModel, onOpenLink: (String) -> Unit) {
    item(key = "contas") {
        val palette = LocalPalette.current
        val active = viewModel.activeAccounts
        Panel {
            Column {
                SectionHeader(
                    stringResource(R.string.ajustes_contas),
                    stringResource(R.string.ajustes_contas_description),
                    stringResource(R.string.ajustes_accounts_badge, active.size),
                )
                HorizontalDivider(color = palette["zinc-100"])
                when {
                    viewModel.accounts.value == null && !viewModel.accounts.loaded -> ListSkeleton(rows = 3, modifier = Modifier.padding(16.dp))
                    active.isEmpty() -> EmptyState(stringResource(R.string.ajustes_no_accounts_title), stringResource(R.string.ajustes_no_accounts_message), Modifier.padding(16.dp))
                    else -> active.forEachIndexed { index, account ->
                        if (index > 0) HorizontalDivider(color = palette["zinc-100"])
                        AccountRow(account, viewModel, onOpenLink)
                    }
                }
                val archived = viewModel.archivedAccounts
                if (archived.isNotEmpty()) {
                    HorizontalDivider(color = palette["zinc-100"])
                    var open by remember { mutableStateOf(false) }
                    Collapsible(stringResource(R.string.ajustes_archived, archived.size), open, { open = !open }) {
                        archived.forEach { account ->
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Column(Modifier.weight(1f)) {
                                    Text(account.name, color = palette["zinc-700"])
                                    Text(Settings.accountTypeLabel(account.type), fontSize = 13.sp, color = palette.muted)
                                }
                                val label = stringResource(R.string.ajustes_reactivate_account, account.name)
                                Surface(
                                    onClick = { viewModel.reactivateAccount(account) },
                                    enabled = !viewModel.busy,
                                    shape = CircleShape,
                                    color = palette.surface,
                                    modifier = Modifier.size(48.dp).semantics { contentDescription = label },
                                ) {
                                    Box(contentAlignment = Alignment.Center) { Icon(AppIcons.Undo, null, tint = palette["zinc-700"], modifier = Modifier.size(18.dp)) }
                                }
                            }
                        }
                    }
                }
                HorizontalDivider(color = palette["zinc-100"])
                Collapsible(stringResource(R.string.ajustes_new_account), viewModel.accountFormOpen, viewModel::toggleAccountForm) {
                    val form = viewModel.accountForm
                    Field(stringResource(R.string.ajustes_name)) {
                        AppTextField(form.name, { viewModel.changeAccountForm(form.copy(name = it)) }, placeholder = stringResource(R.string.ajustes_account_name_placeholder))
                    }
                    Field(
                        stringResource(R.string.ajustes_type),
                        hint = if (form.type == "BROKERAGE") stringResource(R.string.ajustes_brokerage_hint) else null,
                    ) {
                        SelectField(form.type, Settings.NEW_ACCOUNT_TYPES.map { SelectOption(it.first, it.second) }, { viewModel.changeAccountForm(form.copy(type = it)) })
                    }
                    Field(stringResource(R.string.ajustes_institution)) {
                        AppTextField(form.institution, { viewModel.changeAccountForm(form.copy(institution = it)) })
                    }
                    Field(stringResource(R.string.ajustes_initial_balance)) {
                        // Pode ser negativo (cheque especial): o teclado de texto tem o "-".
                        AppTextField(form.initialBalance, { viewModel.changeAccountForm(form.copy(initialBalance = it)) }, placeholder = "0,00", keyboardType = KeyboardType.Text)
                    }
                    AppButton(stringResource(R.string.orc_save), viewModel::createAccount, Modifier.fillMaxWidth(), loading = viewModel.busy, enabled = form.name.isNotBlank())
                }
            }
        }
    }
}

@Composable
private fun AccountRow(account: AccountDto, viewModel: AjustesViewModel, onOpenLink: (String) -> Unit) {
    val palette = LocalPalette.current
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(start = 16.dp, end = 8.dp, top = 10.dp, bottom = 10.dp)) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(account.name, fontWeight = FontWeight.SemiBold, color = palette.text, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                if (account.isDefault) Badge(stringResource(R.string.ajustes_default_badge))
                if (account.id == viewModel.portfolioAccountId) Badge(stringResource(R.string.ajustes_portfolio_badge))
            }
            val institution = account.institution?.takeIf { it.isNotEmpty() }?.let { " · $it" }.orEmpty()
            Text(Settings.accountLabel(account.type, account.currency) + institution, fontSize = 13.sp, color = palette.muted)
        }
        if (GlobalAccount.isGlobal(account)) {
            // O saldo em dolar so na tela dela.
            Text(
                stringResource(R.string.home_global_account),
                color = palette["emerald-700"],
                fontWeight = FontWeight.SemiBold,
                fontSize = 14.sp,
                modifier = Modifier.heightIn(min = 48.dp).clickable { onOpenLink("/inicio/conta-global") }.padding(horizontal = 8.dp, vertical = 14.dp),
            )
        } else if (account.isBrokerage) {
            // O saldo da Corretora so aparece em Investimentos.
            Text(
                stringResource(R.string.ajustes_in_investments),
                color = palette["emerald-700"],
                fontWeight = FontWeight.SemiBold,
                fontSize = 14.sp,
                modifier = Modifier.heightIn(min = 48.dp).clickable { onOpenLink("/investimentos/posicao") }.padding(horizontal = 8.dp, vertical = 14.dp),
            )
        } else {
            val balance = Settings.accountBalanceBrl(account.balance, account.balanceBrl, account.currency)
            Text(
                if (balance == null) stringResource(R.string.ajustes_no_rate) else moneyOrMasked(balance, viewModel.hidden),
                fontWeight = FontWeight.Bold,
                color = if (!viewModel.hidden && (balance?.signum() ?: 0) < 0) palette.loss else palette.text,
            )
        }
        val menu = Settings.accountMenu(account.type, account.isDefault, account.currency)
        val actions = buildList {
            add(MenuAction(stringResource(R.string.ajustes_edit_account)) { viewModel.openEditAccount(account) })
            if (menu.makeDefault) add(MenuAction(stringResource(R.string.ajustes_make_default)) { viewModel.makeDefault(account) })
            if (menu.linkToPortfolio) add(MenuAction(stringResource(R.string.ajustes_link)) { viewModel.askLink(account) })
            if (menu.unlinkFromPortfolio) add(MenuAction(stringResource(R.string.ajustes_unlink)) { viewModel.askUnlink(account) })
            add(MenuAction(stringResource(R.string.ajustes_archive_account)) { viewModel.askArchiveAccount(account) })
        }
        OverflowMenu(actions, stringResource(R.string.ajustes_account_actions, account.name))
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun EditAccountSheet(account: AccountDto, viewModel: AjustesViewModel) {
    val palette = LocalPalette.current
    val form = viewModel.editAccountForm
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true, confirmValueChange = { it != SheetValue.Hidden || !viewModel.busy })
    AppSheet(
        title = stringResource(R.string.ajustes_edit_title, account.name),
        sheetState = sheetState,
        onDismiss = viewModel::closeEditAccount,
        footer = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AppButton(stringResource(R.string.lanc_cancel), viewModel::closeEditAccount, Modifier.weight(1f), ButtonVariant.SECONDARY, enabled = !viewModel.busy)
                AppButton(stringResource(R.string.orc_save), viewModel::saveEditAccount, Modifier.weight(1f), loading = viewModel.busy)
            }
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(stringResource(R.string.ajustes_edit_account_description), fontSize = 14.sp, color = palette["zinc-600"])
            AlertMessage(viewModel.error, AlertTone.DANGER, stringResource(R.string.lanc_dismiss))
            Field(stringResource(R.string.ajustes_name)) { AppTextField(form.name, { viewModel.changeEditAccount(form.copy(name = it)) }) }
            Field(stringResource(R.string.ajustes_institution)) { AppTextField(form.institution, { viewModel.changeEditAccount(form.copy(institution = it)) }) }
            Field(stringResource(R.string.ajustes_initial_balance)) {
                AppTextField(form.initialBalance, { viewModel.changeEditAccount(form.copy(initialBalance = it)) }, placeholder = "0,00", keyboardType = KeyboardType.Text)
            }
        }
    }
}

// ---- Cartoes ----

private fun cardOf(card: CreditCardDto) = Card(card.id, card.name, card.creditEnabled, card.debitAccountId)

private fun LazyListScope.cartoes(viewModel: AjustesViewModel, onOpenLink: (String) -> Unit) {
    item(key = "cartoes") {
        val palette = LocalPalette.current
        val cards = viewModel.cards.value.orEmpty()
        Panel {
            Column {
                SectionHeader(
                    stringResource(R.string.ajustes_cartoes),
                    stringResource(R.string.ajustes_cartoes_description),
                    stringResource(R.string.ajustes_cards_badge, cards.size),
                )
                HorizontalDivider(color = palette["zinc-100"])
                when {
                    viewModel.cards.value == null && !viewModel.cards.loaded -> ListSkeleton(rows = 3, modifier = Modifier.padding(16.dp))
                    cards.isEmpty() -> EmptyState(stringResource(R.string.ajustes_no_cards_title), stringResource(R.string.ajustes_no_cards_message), Modifier.padding(16.dp))
                    else -> cards.forEachIndexed { index, card ->
                        if (index > 0) HorizontalDivider(color = palette["zinc-100"])
                        CardRow(card, viewModel)
                    }
                }
                HorizontalDivider(color = palette["zinc-100"])
                Collapsible(stringResource(R.string.ajustes_new_card), viewModel.cardFormOpen, viewModel::toggleCardForm) {
                    CardFields(viewModel.cardForm, viewModel::changeCardForm, viewModel, onDueDay = viewModel::changeDueDay, debitOptions = viewModel.debitAccounts.map { it.id to it.name }, withAutopay = true)
                    AppButton(stringResource(R.string.orc_save), viewModel::createCard, Modifier.fillMaxWidth(), loading = viewModel.busy)
                }
                if (cards.isNotEmpty() && !viewModel.cardFormOpen) {
                    Text(
                        stringResource(R.string.ajustes_see_invoices),
                        color = palette["emerald-700"],
                        fontWeight = FontWeight.SemiBold,
                        fontSize = 14.sp,
                        modifier = Modifier.heightIn(min = 48.dp).clickable { onOpenLink("/lancamentos/cartoes") }.padding(horizontal = 16.dp, vertical = 14.dp),
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun CardRow(card: CreditCardDto, viewModel: AjustesViewModel) {
    val palette = LocalPalette.current
    val rule = cardOf(card)
    val credit = CardFunctions.hasCredit(rule)
    Column(Modifier.padding(start = 16.dp, end = 8.dp, top = 10.dp, bottom = 10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(card.name, fontWeight = FontWeight.SemiBold, color = palette.text)
                    Badge(CardFunctions.cardFunctionLabel(rule))
                    if (!card.autopayAccountId.isNullOrEmpty()) Badge(stringResource(R.string.ajustes_autopay_badge))
                }
                val debitName = if (CardFunctions.hasDebit(rule)) viewModel.accountName(card.debitAccountId) else null
                Text(Settings.cardDetail(credit, card.dueDay, card.closingDay, debitName), fontSize = 13.sp, color = palette.muted)
            }
            OverflowMenu(
                listOf(
                    MenuAction(stringResource(R.string.ajustes_edit_card)) { viewModel.openEditCard(card) },
                    MenuAction(stringResource(R.string.ajustes_delete_card)) { viewModel.askDeleteCard(card) },
                ),
                stringResource(R.string.ajustes_card_actions, card.name),
            )
        }
        if (credit) {
            Field(stringResource(R.string.ajustes_autopay)) {
                SelectField(
                    value = card.autopayAccountId.orEmpty(),
                    options = viewModel.activeAccounts.map { SelectOption(it.id, it.name) },
                    onSelect = { if (it != card.autopayAccountId.orEmpty()) viewModel.setAutopay(card, it) },
                    placeholder = stringResource(R.string.ajustes_autopay_off),
                )
            }
        }
    }
}

@Composable
private fun CardFields(
    form: CardFormState,
    onChange: (CardFormState) -> Unit,
    viewModel: AjustesViewModel,
    onDueDay: (String) -> Unit,
    debitOptions: List<Pair<String, String>>,
    withAutopay: Boolean,
) {
    Field(stringResource(R.string.ajustes_card_name)) { AppTextField(form.name, { onChange(form.copy(name = it)) }) }
    Field(stringResource(R.string.ajustes_card_functions), hint = stringResource(R.string.ajustes_card_functions_hint)) {
        SegmentedChoice(CardFunctions.CARD_FUNCTION_ITEMS.map { SelectOption(it.value, it.label) }, form.functions, { onChange(form.copy(functions = it)) })
    }
    if (form.functions != CardFunctions.DEBIT) {
        Field(stringResource(R.string.ajustes_due_day)) {
            AppTextField(form.dueDay, { onDueDay(it.filter(Char::isDigit).take(2)) }, keyboardType = KeyboardType.Number)
        }
        Field(stringResource(R.string.ajustes_closing_day), hint = if (withAutopay) stringResource(R.string.ajustes_closing_hint) else null) {
            AppTextField(form.closingDay, { onChange(form.copy(closingDay = it.filter(Char::isDigit).take(2))) }, keyboardType = KeyboardType.Number)
        }
        if (withAutopay) {
            Field(stringResource(R.string.ajustes_autopay), hint = stringResource(R.string.ajustes_autopay_hint)) {
                SelectField(form.autopayAccountId, viewModel.activeAccounts.map { SelectOption(it.id, it.name) }, { onChange(form.copy(autopayAccountId = it)) }, placeholder = stringResource(R.string.ajustes_autopay_off))
            }
        }
    }
    if (form.functions != CardFunctions.CREDIT) {
        Field(stringResource(R.string.ajustes_debit_account), hint = stringResource(R.string.ajustes_debit_account_hint)) {
            SelectField(form.debitAccountId, debitOptions.map { SelectOption(it.first, it.second) }, { onChange(form.copy(debitAccountId = it)) }, placeholder = stringResource(R.string.ajustes_select))
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun EditCardSheet(card: CreditCardDto, viewModel: AjustesViewModel) {
    val palette = LocalPalette.current
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true, confirmValueChange = { it != SheetValue.Hidden || !viewModel.busy })
    AppSheet(
        title = stringResource(R.string.ajustes_edit_title, card.name),
        sheetState = sheetState,
        onDismiss = viewModel::closeEditCard,
        footer = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AppButton(stringResource(R.string.lanc_cancel), viewModel::closeEditCard, Modifier.weight(1f), ButtonVariant.SECONDARY, enabled = !viewModel.busy)
                AppButton(stringResource(R.string.orc_save), viewModel::saveEditCard, Modifier.weight(1f), loading = viewModel.busy)
            }
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(stringResource(R.string.ajustes_edit_card_description), fontSize = 14.sp, color = palette["zinc-600"])
            AlertMessage(viewModel.error, AlertTone.DANGER, stringResource(R.string.lanc_dismiss))
            val form = viewModel.editCardForm
            CardFields(form, viewModel::changeEditCard, viewModel, onDueDay = { viewModel.changeEditCard(form.copy(dueDay = it)) }, debitOptions = viewModel.editDebitAccounts(card), withAutopay = false)
        }
    }
}

// ---- Categorias ----

private fun LazyListScope.categorias(viewModel: AjustesViewModel) {
    item(key = "categorias") {
        val palette = LocalPalette.current
        val all = viewModel.categories.value.orEmpty()
        Panel {
            Column {
                SectionHeader(
                    stringResource(R.string.ajustes_categorias),
                    stringResource(R.string.ajustes_categorias_description),
                    stringResource(R.string.ajustes_categories_badge, all.count { !it.isArchived }),
                )
                HorizontalDivider(color = palette["zinc-100"])
                Collapsible(stringResource(R.string.ajustes_new_category), viewModel.categoryFormOpen, viewModel::toggleCategoryForm) {
                    val form = viewModel.categoryForm
                    Field(stringResource(R.string.ajustes_name)) {
                        AppTextField(form.name, { viewModel.changeCategoryForm(form.copy(name = it)) }, placeholder = stringResource(R.string.ajustes_category_placeholder))
                    }
                    Field(stringResource(R.string.ajustes_type)) {
                        SelectField(form.kind, Settings.CATEGORY_KINDS.map { SelectOption(it.first, it.second) }, { viewModel.changeCategoryForm(form.copy(kind = it)) })
                    }
                    Field(stringResource(R.string.ajustes_parent), hint = stringResource(R.string.ajustes_parent_hint)) {
                        SelectField(
                            form.parentId,
                            viewModel.rootCategories.map { SelectOption(it.id, it.name) },
                            { viewModel.changeCategoryForm(form.copy(parentId = it)) },
                            placeholder = stringResource(R.string.ajustes_parent_none),
                        )
                    }
                    AppButton(stringResource(R.string.orc_save), viewModel::createCategory, Modifier.fillMaxWidth(), loading = viewModel.busy, enabled = form.name.isNotBlank())
                }
                HorizontalDivider(color = palette["zinc-100"])
                when {
                    viewModel.categories.value == null && !viewModel.categories.loaded -> ListSkeleton(rows = 5, modifier = Modifier.padding(16.dp))
                    all.isEmpty() -> EmptyState(stringResource(R.string.ajustes_no_categories_title), stringResource(R.string.ajustes_no_categories_message), Modifier.padding(16.dp))
                    else -> all.forEachIndexed { index, category ->
                        if (index > 0) HorizontalDivider(color = palette["zinc-100"])
                        CategoryRow(category, viewModel)
                    }
                }
            }
        }
    }
}

@Composable
private fun CategoryRow(category: CategoryDto, viewModel: AjustesViewModel) {
    val palette = LocalPalette.current
    if (viewModel.editingCategoryId == category.id) {
        val form = viewModel.categoryEdit
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Field(stringResource(R.string.ajustes_name)) { AppTextField(form.name, { viewModel.changeCategoryEdit(form.copy(name = it)) }) }
            Field(stringResource(R.string.ajustes_type)) {
                SelectField(form.kind, Settings.CATEGORY_KINDS.map { SelectOption(it.first, it.second) }, { viewModel.changeCategoryEdit(form.copy(kind = it)) })
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AppButton(stringResource(R.string.lanc_cancel), viewModel::cancelCategoryEdit, Modifier.weight(1f), ButtonVariant.SECONDARY)
                AppButton(stringResource(R.string.orc_save), { viewModel.saveCategoryEdit(category) }, Modifier.weight(1f), loading = viewModel.busy)
            }
        }
        return
    }
    val archived = category.isArchived
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(start = 16.dp, end = 8.dp, top = 10.dp, bottom = 10.dp)) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(
                if (category.parentName.isNullOrEmpty()) category.name else "${category.parentName} › ${category.name}",
                fontWeight = if (category.parentId.isNullOrEmpty()) FontWeight.SemiBold else FontWeight.Normal,
                color = if (archived) palette.muted else if (category.parentId.isNullOrEmpty()) palette.text else palette["zinc-700"],
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(Settings.categoryKindLabel(category.kind), fontSize = 13.sp, color = palette["zinc-600"])
                if (archived) Badge(stringResource(R.string.ajustes_archived_badge))
            }
        }
        if (archived) {
            AppButton(stringResource(R.string.ajustes_reactivate), { viewModel.reactivateCategory(category) }, variant = ButtonVariant.SECONDARY, enabled = !viewModel.busy)
        } else {
            OverflowMenu(
                listOf(
                    MenuAction(stringResource(R.string.ajustes_rename_category)) { viewModel.startCategoryEdit(category) },
                    MenuAction(stringResource(R.string.ajustes_archive_category)) { viewModel.askArchiveCategory(category) },
                ),
                stringResource(R.string.ajustes_category_actions, category.name),
            )
        }
    }
}

// ---- Aprovar, Aparencia, Perfil ----

/** Open Finance (043): o estado de cada banco conectado, o saldo do banco ao lado do do app e o
 *  "Atualizar". Conectar, reconectar e mapear ficam no computador (o widget da Pluggy e web). */
@Composable
private fun OpenFinanceSection(viewModel: AjustesViewModel) {
    val palette = LocalPalette.current
    val load = viewModel.openFinance
    val data = load.value
    Panel {
        Column {
            SectionHeader(stringResource(R.string.ajustes_open_finance), stringResource(R.string.ajustes_open_finance_description))
            HorizontalDivider(color = palette["zinc-100"])
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                AlertMessage(load.error, AlertTone.DANGER, stringResource(R.string.lanc_dismiss))
                if (load.offline) Text(load.offlineText, fontSize = 13.sp, color = palette.muted)
                when {
                    data == null && !load.loaded -> ListSkeleton(rows = 2)
                    data != null && !data.configured -> AlertMessage(stringResource(R.string.ajustes_open_finance_off), AlertTone.INFO, stringResource(R.string.lanc_dismiss))
                    data != null && data.items.isEmpty() -> EmptyState(stringResource(R.string.ajustes_open_finance_empty))
                }
                data?.items.orEmpty().forEach { item -> OpenFinanceItemCard(item, viewModel) }
                val settings = viewModel.openFinanceSettings.value
                if (data?.configured == true && settings != null) OpenFinanceSettingsBlock(settings, viewModel)
                Text(stringResource(R.string.ajustes_open_finance_desktop), fontSize = 13.sp, color = palette.muted)
            }
        }
    }
}

@Composable
private fun OpenFinanceSettingsBlock(settings: OpenFinanceSettingsDto, viewModel: AjustesViewModel) {
    val palette = LocalPalette.current
    val enabled = !viewModel.busy
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        HorizontalDivider(color = palette["zinc-100"])
        Text(stringResource(R.string.ajustes_open_finance_auto), fontWeight = FontWeight.SemiBold, fontSize = 14.sp, color = palette.text)
        SelectField(
            settings.syncHours.toString(),
            OpenFinanceRules.syncHoursChoices(settings.syncHours).map { SelectOption(it.first.toString(), it.second) },
            { value -> if (enabled) value.toIntOrNull()?.let { viewModel.setOpenFinanceSyncHours(it) } },
            contentDescription = stringResource(R.string.ajustes_open_finance_auto),
        )
        Text(
            stringResource(if (settings.autoSyncAvailable) R.string.ajustes_open_finance_auto_hint else R.string.ajustes_open_finance_auto_server_off),
            fontSize = 13.sp,
            color = palette.muted,
        )
        val canRecord = settings.autoRecord || settings.autoRecordBlockers.isEmpty()
        Row(verticalAlignment = Alignment.Top, modifier = Modifier.clickable(enabled = enabled && canRecord) { viewModel.setOpenFinanceAutoRecord(!settings.autoRecord) }) {
            Checkbox(
                settings.autoRecord,
                { viewModel.setOpenFinanceAutoRecord(it) },
                enabled = enabled && canRecord,
                colors = CheckboxDefaults.colors(checkedColor = palette.accent, checkmarkColor = palette.onAccent),
            )
            Column(Modifier.padding(top = 12.dp)) {
                Text(stringResource(R.string.ajustes_open_finance_record), fontWeight = FontWeight.SemiBold, fontSize = 14.sp, color = palette.text)
                Text(OpenFinanceRules.autoRecordHint(settings.autoRecord, settings.autoRecordBlockers), fontSize = 14.sp, color = palette["zinc-600"])
            }
        }
        Text(stringResource(R.string.ajustes_open_finance_notices_line), fontSize = 14.sp, color = palette["zinc-600"])
        Row(verticalAlignment = Alignment.Top, modifier = Modifier.clickable(enabled = enabled) { viewModel.setOpenFinanceIncludePending(!settings.includePending) }) {
            Checkbox(
                settings.includePending,
                { viewModel.setOpenFinanceIncludePending(it) },
                enabled = enabled,
                colors = CheckboxDefaults.colors(checkedColor = palette.accent, checkmarkColor = palette.onAccent),
            )
            Column(Modifier.padding(top = 12.dp)) {
                Text(stringResource(R.string.ajustes_open_finance_pending), fontWeight = FontWeight.SemiBold, fontSize = 14.sp, color = palette.text)
                Text(stringResource(R.string.ajustes_open_finance_pending_hint), fontSize = 14.sp, color = palette["zinc-600"])
            }
        }
    }
}

@Composable
private fun OpenFinanceCheckBlock(check: OpenFinanceCheckDto?, hidden: Boolean) {
    val palette = LocalPalette.current
    val summary = OpenFinanceRules.checkSummary(check != null, check?.bankOnlyCount ?: 0, check?.appOnlyCount ?: 0, check?.awaitingCount ?: 0)
    if (summary.state == "none" || check == null) return
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Badge(
            stringResource(if (summary.state == "match") R.string.ajustes_open_finance_check_match else R.string.ajustes_open_finance_check_drift),
            if (summary.state == "match") BadgeTone.SUCCESS else BadgeTone.WARNING,
        )
    }
    if (summary.state == "drift" || check.awaitingCount > 0) Text(summary.text, fontSize = 13.sp, color = palette["zinc-600"])
    listOf(
        R.string.ajustes_open_finance_check_bank to check.bankOnly,
        R.string.ajustes_open_finance_check_app to check.appOnly,
        R.string.ajustes_open_finance_check_conflicts to check.conflicts,
    )
        .filter { it.second.isNotEmpty() }
        .forEach { (title, rows) ->
            Text(stringResource(title), fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = palette["zinc-700"])
            rows.forEach { row ->
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    val reason = OpenFinanceRules.checkReasonLabel(row.reason)
                    Text(
                        "${formatDateBR(row.date)} · ${row.description.orEmpty().ifEmpty { "Sem descrição" }}" +
                            (if (reason.isNotEmpty()) " · $reason" else ""),
                        fontSize = 12.sp,
                        color = palette["zinc-600"],
                        modifier = Modifier.weight(1f),
                    )
                    Text(moneyOrMasked(row.amount, hidden), fontSize = 12.sp, color = palette["zinc-600"])
                }
            }
        }
    val explanation = check.explanation
    if (explanation != null && !hidden) {
        OpenFinanceRules.balanceExplanation(
            explanation.difference, explanation.bankOnly, explanation.awaiting, explanation.appOnly, explanation.before,
        ) { value -> moneyOrMasked(value, false) }.forEach { line ->
            Text(line, fontSize = 12.sp, color = palette["zinc-600"])
        }
    }
}

@Composable
private fun OpenFinanceItemCard(item: OpenFinanceItemDto, viewModel: AjustesViewModel) {
    val palette = LocalPalette.current
    val status = OpenFinanceRules.itemStatus(item.status, item.needsOwner)
    val problem = OpenFinanceRules.itemProblem(item.errorMessage, item.needsOwner, item.lastSyncError)
    Surface(shape = RoundedCornerShape(16.dp), border = BorderStroke(1.dp, palette.border), color = palette.surface) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(OpenFinanceRules.itemBankName(item.bankName, item.connectorName), fontWeight = FontWeight.SemiBold, color = palette.text, modifier = Modifier.weight(1f, fill = false))
                Badge(status.label, badgeTone(status.tone))
            }
            Text(
                if (item.lastSyncAt.isNullOrEmpty()) stringResource(R.string.ajustes_open_finance_never)
                else stringResource(R.string.ajustes_open_finance_last_sync, PortfolioView.formatDateTime(item.lastSyncAt)),
                fontSize = 13.sp,
                color = palette.muted,
            )
            if (problem.isNotEmpty()) AlertMessage(problem, AlertTone.WARNING, stringResource(R.string.lanc_dismiss))
            item.accounts.forEach { account ->
                HorizontalDivider(color = palette["zinc-100"])
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(OpenFinanceRules.accountLabel(account.type, account.name, account.number), fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = palette.text)
                    Text(
                        if (account.targetName != null) stringResource(R.string.ajustes_open_finance_goes_to, account.targetName)
                        else stringResource(R.string.ajustes_open_finance_unmapped, account.unmappedCount),
                        fontSize = 13.sp,
                        color = palette["zinc-600"],
                    )
                    val check = OpenFinanceRules.balanceCheck(account.type, account.pluggyBalance, account.appBalance)
                    if (check.state != "none") {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(
                                stringResource(
                                    R.string.ajustes_open_finance_balance,
                                    moneyOrMasked(account.pluggyBalance, viewModel.hidden),
                                    moneyOrMasked(account.appBalance, viewModel.hidden),
                                ),
                                fontSize = 13.sp,
                                color = palette.muted,
                                modifier = Modifier.weight(1f, fill = false),
                            )
                            if (check.state == "match") Badge(stringResource(R.string.ajustes_open_finance_match), BadgeTone.SUCCESS)
                            else Badge(stringResource(R.string.ajustes_open_finance_drift, moneyOrMasked(check.difference, viewModel.hidden)), BadgeTone.WARNING)
                        }
                    } else if (account.type == "CREDIT" && account.pluggyBalance != null) {
                        Text(
                            stringResource(R.string.ajustes_open_finance_card_balance, moneyOrMasked(account.pluggyBalance.abs(), viewModel.hidden)),
                            fontSize = 13.sp,
                            color = palette.muted,
                        )
                    }
                    OpenFinanceCheckBlock(account.check, viewModel.hidden)
                }
            }
            AppButton(
                stringResource(R.string.ajustes_open_finance_refresh),
                { viewModel.syncOpenFinance(item) },
                Modifier.fillMaxWidth(),
                variant = ButtonVariant.SECONDARY,
                loading = viewModel.syncingItemId == item.id,
                enabled = !viewModel.busy,
            )
        }
    }
}

private fun badgeTone(tone: String): BadgeTone = when (tone) {
    "success" -> BadgeTone.SUCCESS
    "info" -> BadgeTone.INFO
    "warning" -> BadgeTone.WARNING
    "danger" -> BadgeTone.DANGER
    else -> BadgeTone.NEUTRAL
}

@Composable
private fun AprovarSection(viewModel: AjustesViewModel) {
    val palette = LocalPalette.current
    Panel {
        Column {
            SectionHeader(stringResource(R.string.ajustes_aprovar), stringResource(R.string.ajustes_aprovar_description))
            HorizontalDivider(color = palette["zinc-100"])
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                AlertMessage(viewModel.alwaysAskError, AlertTone.DANGER, stringResource(R.string.lanc_dismiss))
                val loaded = viewModel.alwaysAsk != null && !viewModel.busy
                // Sem resposta ainda, vale o padrao do servidor: ligado.
                val autoRecord = viewModel.autoRecord ?: true
                SettingCheck(
                    checked = autoRecord,
                    enabled = loaded,
                    title = stringResource(R.string.ajustes_auto_record),
                    hint = stringResource(R.string.ajustes_auto_record_hint),
                    onChange = viewModel::setAutoRecord,
                )
                // "Sempre perguntar" so vale com Gravar sozinho desligado.
                SettingCheck(
                    checked = viewModel.alwaysAsk ?: false,
                    enabled = loaded && !autoRecord,
                    title = stringResource(R.string.ajustes_always_ask),
                    hint = stringResource(R.string.ajustes_always_ask_hint),
                    onChange = viewModel::setAlwaysAsk,
                )
            }
        }
    }
}

/** Uma caixa de marcar com o titulo e a explicacao (o <label> com checkbox da web). */
@Composable
private fun SettingCheck(checked: Boolean, enabled: Boolean, title: String, hint: String, onChange: (Boolean) -> Unit) {
    val palette = LocalPalette.current
    Row(verticalAlignment = Alignment.Top, modifier = Modifier.clickable(enabled = enabled) { onChange(!checked) }) {
        Checkbox(checked, onChange, enabled = enabled, colors = CheckboxDefaults.colors(checkedColor = palette.accent, checkmarkColor = palette.onAccent))
        Column(Modifier.padding(top = 12.dp)) {
            Text(title, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, color = if (enabled) palette.text else palette.muted)
            Text(hint, fontSize = 14.sp, color = palette["zinc-600"])
        }
    }
}

@Composable
private fun AparenciaSection(viewModel: AjustesViewModel) {
    val palette = LocalPalette.current
    val activity = LocalContext.current as? Activity
    Panel {
        Column {
            SectionHeader(stringResource(R.string.ajustes_aparencia), stringResource(R.string.ajustes_aparencia_description))
            HorizontalDivider(color = palette["zinc-100"])
            SegmentedChoice(
                items = listOf(
                    SelectOption("system", stringResource(R.string.ajustes_theme_system)),
                    SelectOption("light", stringResource(R.string.ajustes_theme_light)),
                    SelectOption("dark", stringResource(R.string.ajustes_theme_dark)),
                ),
                value = viewModel.theme,
                // A Activity se refaz no tema novo (telas e barras do sistema).
                onChange = { viewModel.chooseTheme(it) { activity?.recreate() } },
                modifier = Modifier.padding(16.dp),
            )
        }
    }
}

@Composable
private fun PerfilSection(viewModel: AjustesViewModel, onSignedOut: () -> Unit) {
    val palette = LocalPalette.current
    val user = viewModel.me.value?.user
    Panel {
        Column {
            SectionHeader(stringResource(R.string.ajustes_perfil), stringResource(R.string.ajustes_perfil_description))
            HorizontalDivider(color = palette["zinc-100"])
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                val dismiss = stringResource(R.string.lanc_dismiss)
                AlertMessage(viewModel.me.error, AlertTone.DANGER, dismiss)
                if (viewModel.me.value != null && user?.username.isNullOrEmpty()) AlertMessage(stringResource(R.string.ajustes_no_username), AlertTone.INFO, dismiss)
                viewModel.profileMessage?.let { (ok, text) ->
                    AlertMessage(text, if (ok) AlertTone.SUCCESS else AlertTone.DANGER, dismiss, onDismiss = viewModel::dismissProfileMessage)
                }
                Field(stringResource(R.string.ajustes_username), hint = stringResource(R.string.ajustes_username_hint)) {
                    AppTextField(viewModel.username.orEmpty(), { viewModel.changeUsername(it.take(40)) }, placeholder = stringResource(R.string.ajustes_username_placeholder))
                }
                AppButton(stringResource(R.string.orc_save), viewModel::saveUsername, Modifier.fillMaxWidth(), loading = viewModel.busy, enabled = viewModel.canSaveUsername)
                HorizontalDivider(color = palette["zinc-100"])
                Text(stringResource(R.string.ajustes_email), fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = palette.muted)
                Text(maskEmail(user?.email), fontWeight = FontWeight.SemiBold, color = palette.text)
                AppButton(stringResource(R.string.ajustes_sign_out), { viewModel.signOut(onSignedOut) }, Modifier.fillMaxWidth(), ButtonVariant.SECONDARY)
            }
        }
    }
}

// ---- Notificacoes dos bancos ----

@Composable
private fun NotificacoesSection(viewModel: AjustesViewModel) {
    val palette = LocalPalette.current
    val status = viewModel.notify
    Panel {
        Column {
            SectionHeader(stringResource(R.string.ajustes_notificacoes), stringResource(R.string.ajustes_notificacoes_description))
            HorizontalDivider(color = palette["zinc-100"])
            if (status == null) {
                ListSkeleton(rows = 3, modifier = Modifier.padding(16.dp))
            } else {
                NotifyBody(status, viewModel)
            }
        }
    }
}

@Composable
private fun NotifyBody(status: NotifyTexts.NotifyStatus, viewModel: AjustesViewModel) {
    val palette = LocalPalette.current
    Column {
            val dismiss = stringResource(R.string.lanc_dismiss)
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                NotifyTexts.accessMessage(status)?.let { access ->
                    AlertMessage(access.text, if (access.tone == NotifyTexts.Tone.SUCCESS) AlertTone.SUCCESS else AlertTone.WARNING, dismiss)
                }
                NotifyTexts.listenerMessage(status)?.let { Text(it, fontSize = 12.sp, color = palette.muted) }
                AppButton(
                    stringResource(R.string.ajustes_open_access),
                    viewModel::openAccessSettings,
                    Modifier.fillMaxWidth(),
                    if (status.granted) ButtonVariant.SECONDARY else ButtonVariant.PRIMARY,
                )
                var restricted by remember(status.granted, status.sdk) { mutableStateOf(NotifyTexts.showsRestrictedHelp(status)) }
                Surface(shape = RoundedCornerShape(16.dp), border = BorderStroke(1.dp, palette.border), color = palette.surface) {
                    Collapsible(stringResource(R.string.ajustes_restricted_title), restricted, { restricted = !restricted }) {
                        Text(stringResource(R.string.ajustes_restricted_intro), fontSize = 14.sp, color = palette["zinc-700"])
                        Text(stringResource(R.string.ajustes_restricted_step1), fontSize = 14.sp, color = palette["zinc-700"])
                        Text(stringResource(R.string.ajustes_restricted_step2), fontSize = 14.sp, color = palette["zinc-700"])
                        Text(stringResource(R.string.ajustes_restricted_step3), fontSize = 14.sp, color = palette["zinc-700"])
                        Text(stringResource(R.string.ajustes_restricted_installer, NotifyTexts.installerLabel(status.installer)), fontSize = 12.sp, color = palette.muted)
                        AppButton(stringResource(R.string.ajustes_open_app_details), viewModel::openAppDetails, variant = ButtonVariant.SECONDARY)
                    }
                }
            }
            HorizontalDivider(color = palette["zinc-100"])
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(stringResource(R.string.ajustes_capture_mode), fontWeight = FontWeight.SemiBold, fontSize = 14.sp, color = palette.text)
                Text(NotifyTexts.captureMessage(status), fontSize = 12.sp, color = palette.muted)
                SegmentedChoice(
                    listOf(SelectOption("off", stringResource(R.string.ajustes_capture_off_label)), SelectOption("on", stringResource(R.string.ajustes_capture_on_label))),
                    if (status.captureOn) "on" else "off",
                    { viewModel.setCapture(it == "on") },
                )
                Text(stringResource(R.string.ajustes_capture_explain), fontSize = 12.sp, color = palette.muted)
                if (status.acceptsShell) {
                    AlertMessage(stringResource(R.string.ajustes_adb_hint) + "\n" + NotifyTexts.ADB_TEST_COMMAND, AlertTone.INFO, dismiss)
                }
                Surface(shape = RoundedCornerShape(16.dp), border = BorderStroke(1.dp, palette.border), color = palette.surface) {
                    Column {
                        NotifyTexts.appRows(status).forEachIndexed { index, row ->
                            if (index > 0) HorizontalDivider(color = palette["zinc-100"])
                            Column(Modifier.padding(12.dp)) {
                                Text(row.label, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, color = palette.text)
                                Text(row.packageName, fontSize = 12.sp, color = palette.muted)
                                Text(row.detail, fontSize = 12.sp, color = palette.muted)
                            }
                        }
                    }
                }
            }
            val captured = viewModel.captured
            if (captured.isNotEmpty()) {
                HorizontalDivider(color = palette["zinc-100"])
                var open by remember { mutableStateOf(false) }
                Collapsible(stringResource(R.string.ajustes_latest_captured, captured.size), open, { open = !open }) {
                    captured.forEach { item ->
                        Surface(shape = RoundedCornerShape(16.dp), border = BorderStroke(1.dp, palette.border), color = palette.surface) {
                            Column(Modifier.fillMaxWidth().padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                                    Text(item.app, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = palette["zinc-700"])
                                    Text(NotifyTexts.formatStamp(item.postedAt, seconds = true), fontSize = 12.sp, color = palette.muted)
                                    if (item.summary) Badge(stringResource(R.string.ajustes_summary_badge))
                                    if (item.active) Badge(stringResource(R.string.ajustes_active_badge))
                                }
                                if (item.title.isNotEmpty()) Text(item.title, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, color = palette.text)
                                if (item.text.isNotEmpty()) Text(item.text, fontSize = 14.sp, color = palette["zinc-700"])
                            }
                        }
                    }
                }
            }
            HorizontalDivider(color = palette["zinc-100"])
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                val has = status.total > 0
                AppButton(stringResource(R.string.ajustes_refresh), viewModel::reloadNotify, Modifier.fillMaxWidth(), ButtonVariant.SUBTLE)
                AppButton(stringResource(R.string.ajustes_export_json), { viewModel.export(true) }, Modifier.fillMaxWidth(), ButtonVariant.SECONDARY, loading = viewModel.notifyBusy == "export-json", enabled = has)
                AppButton(stringResource(R.string.ajustes_export_text), { viewModel.export(false) }, Modifier.fillMaxWidth(), ButtonVariant.SECONDARY, loading = viewModel.notifyBusy == "export-text", enabled = has)
                AppButton(stringResource(R.string.ajustes_clear_capture), viewModel::askClearCapture, Modifier.fillMaxWidth(), ButtonVariant.SUBTLE, enabled = has)
            }
    }
}

// ---- Versao do app ----

@Composable
private fun VersaoSection(viewModel: AjustesViewModel) {
    val palette = LocalPalette.current
    val dismiss = stringResource(R.string.lanc_dismiss)
    fun tone(value: ApkUpdateTexts.Tone) = when (value) {
        ApkUpdateTexts.Tone.DANGER -> AlertTone.DANGER
        ApkUpdateTexts.Tone.WARNING -> AlertTone.WARNING
        ApkUpdateTexts.Tone.SUCCESS -> AlertTone.SUCCESS
        ApkUpdateTexts.Tone.INFO, ApkUpdateTexts.Tone.NEUTRAL -> AlertTone.INFO
    }
    Panel {
        Column {
            SectionHeader(stringResource(R.string.ajustes_versao), stringResource(R.string.ajustes_versao_description))
            HorizontalDivider(color = palette["zinc-100"])
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                ApkUpdateTexts.apkPrompt(viewModel.apk)?.let { prompt ->
                    AlertMessage(
                        stringResource(R.string.ajustes_apk_new, prompt.versionName),
                        AlertTone.INFO,
                        dismiss,
                    )
                    AppButton(stringResource(R.string.ajustes_apk_install), viewModel::installApk, Modifier.fillMaxWidth(), loading = viewModel.apkBusy == "install")
                    viewModel.apkInstall?.let { Text(it.text, fontSize = 12.sp, color = palette["zinc-600"]) }
                }
                viewModel.apkCheck?.let { AlertMessage(it.text, tone(it.tone), dismiss) }
                Surface(shape = RoundedCornerShape(16.dp), border = BorderStroke(1.dp, palette.border), color = palette.surface) {
                    Column(Modifier.fillMaxWidth().padding(12.dp)) {
                        Text(stringResource(R.string.ajustes_apk), fontWeight = FontWeight.SemiBold, fontSize = 14.sp, color = palette.text)
                        Text(
                            viewModel.apkVersion.ifEmpty { "—" },
                            fontSize = 12.sp,
                            color = palette.muted,
                            fontFamily = FontFamily.Default,
                        )
                    }
                }
                AppButton(stringResource(R.string.ajustes_apk_check), viewModel::checkApk, Modifier.fillMaxWidth(), ButtonVariant.SECONDARY, loading = viewModel.apkBusy == "check")
            }
        }
    }
}
