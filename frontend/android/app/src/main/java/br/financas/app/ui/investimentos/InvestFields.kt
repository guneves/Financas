package br.financas.app.ui.investimentos

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.data.AccountDto
import br.financas.app.rules.FixedIncome
import br.financas.app.rules.PortfolioAccount
import br.financas.app.ui.components.AppTextField
import br.financas.app.ui.components.Field
import br.financas.app.ui.components.SelectField
import br.financas.app.ui.components.SelectOption
import br.financas.app.ui.theme.LocalPalette

/** As contas de GET /api/accounts como as regras da carteira as leem. */
fun portfolioAccountsOf(accounts: List<AccountDto>): List<PortfolioAccount.Account> =
    accounts.map { PortfolioAccount.Account(it.id, it.type, it.currency, it.archivedAt) }

/**
 * O campo da conta (o useEffect de CashLinkField): com a lista de contas chegada, marca a falta de
 * conta da carteira e, ligado sem conta, poe a primeira. Devolve o mesmo valor quando nada muda.
 */
fun settleCashLink(value: PortfolioAccount.CashLink, accounts: List<AccountDto>?): PortfolioAccount.CashLink {
    if (accounts == null) return value
    val all = portfolioAccountsOf(accounts)
    val missing = PortfolioAccount.portfolioAccounts(all).isEmpty()
    val defaultId = PortfolioAccount.pickPortfolioAccountId(all)
    var next = value.copy(missing = missing)
    if (next.enabled && next.accountId.isEmpty() && defaultId.isNotEmpty()) next = next.copy(accountId = defaultId)
    return next
}

/**
 * CashLinkField: "Conta da carteira" (as Corretora ativas em reais; a conta gravada numa operacao
 * antiga continua na lista, como "(arquivada)" ou "Conta arquivada") e "Não descontar de nenhuma
 * conta". [movementType] BUY, SELL ou REDEMPTION escolhe a dica.
 */
@Composable
fun CashLinkField(
    value: PortfolioAccount.CashLink,
    onChange: (PortfolioAccount.CashLink) -> Unit,
    accounts: List<AccountDto>?,
    movementType: String,
    savedAccountId: String = "",
    allAccounts: List<AccountDto>? = null,
) {
    val palette = LocalPalette.current
    val list = accounts.orEmpty()
    val portfolio = PortfolioAccount.portfolioAccounts(portfolioAccountsOf(list)).mapNotNull { account -> list.firstOrNull { it.id == account.id } }
    val defaultId = portfolio.firstOrNull()?.id.orEmpty()
    val missing = accounts != null && portfolio.isEmpty()
    val savedIsMissing = savedAccountId.isNotEmpty() && accounts != null && portfolio.none { it.id == savedAccountId }
    val options = buildList {
        portfolio.forEach { add(SelectOption(it.id, it.name)) }
        if (savedIsMissing) {
            val saved = allAccounts?.firstOrNull { it.id == savedAccountId }
            val name = if (saved != null) saved.name + if (saved.isArchived) " " + stringResource(R.string.inv_cash_archived_suffix) else "" else stringResource(R.string.inv_cash_archived_account)
            add(SelectOption(savedAccountId, name))
        }
    }
    val canLink = options.isNotEmpty()
    val hint = stringResource(
        when (movementType) {
            "SELL" -> R.string.inv_cash_hint_sell
            "REDEMPTION" -> R.string.inv_cash_hint_redemption
            else -> R.string.inv_cash_hint_buy
        },
    )
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        if (value.enabled && canLink) {
            Field(stringResource(R.string.inv_cash_account), hint = hint) {
                SelectField(
                    value = value.accountId,
                    options = options,
                    onSelect = { onChange(value.copy(accountId = it)) },
                    placeholder = stringResource(R.string.inv_select_placeholder),
                )
            }
        }
        if (missing) {
            Text(stringResource(R.string.inv_cash_missing), color = palette.warning, fontSize = 13.sp)
        }
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = 48.dp)
                .clickable(enabled = canLink || !value.enabled) {
                    onChange(value.copy(enabled = !value.enabled, accountId = value.accountId.ifEmpty { defaultId }))
                },
        ) {
            Checkbox(
                checked = !value.enabled,
                onCheckedChange = null,
                enabled = canLink || !value.enabled,
                colors = CheckboxDefaults.colors(checkedColor = palette.accent, checkmarkColor = palette.onAccent),
            )
            Column(Modifier.padding(start = 4.dp)) {
                Text(stringResource(R.string.inv_cash_none), color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                Text(stringResource(R.string.inv_cash_none_hint), color = palette.muted, fontSize = 12.sp)
            }
        }
    }
}

/** Uma opcao de [AssetPickerField]: o valor, o rotulo (ticker), a linha de baixo e o valor ao lado. */
data class PickerOption(val value: String, val label: String, val meta: String = "", val aside: String = "")

/**
 * O AssetPicker da web: um campo de busca e a lista de opcoes que casam (a busca e de quem chama).
 * Escolhida uma opcao, mostra o rotulo dela; tocar de novo reabre a busca.
 */
@Composable
fun AssetPickerField(
    query: String,
    onQuery: (String) -> Unit,
    selected: PickerOption?,
    options: List<PickerOption>,
    onPick: (PickerOption) -> Unit,
    placeholder: String,
    emptyMessage: String,
    open: Boolean,
    onOpen: () -> Unit,
    showSearch: Boolean = true,
) {
    val palette = LocalPalette.current
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (selected != null && !open) {
            Surface(
                onClick = onOpen,
                shape = RoundedCornerShape(14.dp),
                color = palette.surface,
                border = BorderStroke(1.dp, palette["zinc-300"]),
                modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp),
            ) {
                Row(Modifier.padding(horizontal = 16.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(selected.label, color = palette.text, fontWeight = FontWeight.SemiBold)
                        if (selected.meta.isNotEmpty()) Text(selected.meta, color = palette.muted, fontSize = 12.sp)
                    }
                    if (selected.aside.isNotEmpty()) Text(selected.aside, color = palette["zinc-700"], fontSize = 13.sp)
                }
            }
            return@Column
        }
        if (showSearch) AppTextField(value = query, onValueChange = onQuery, placeholder = placeholder)
        OptionList(options, onPick, emptyMessage)
    }
}

@Composable
private fun OptionList(options: List<PickerOption>, onPick: (PickerOption) -> Unit, emptyMessage: String) {
    val palette = LocalPalette.current
    Surface(shape = RoundedCornerShape(14.dp), color = palette.surface, border = BorderStroke(1.dp, palette.border)) {
        Column(Modifier.fillMaxWidth()) {
            if (options.isEmpty()) {
                Text(emptyMessage, color = palette.muted, fontSize = 13.sp, modifier = Modifier.padding(14.dp))
            }
            options.take(12).forEach { option ->
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 48.dp)
                        .clickable { onPick(option) }
                        .padding(horizontal = 14.dp, vertical = 8.dp),
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(option.label, color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                        if (option.meta.isNotEmpty()) Text(option.meta, color = palette.muted, fontSize = 12.sp)
                    }
                    if (option.aside.isNotEmpty()) Text(option.aside, color = palette["zinc-700"], fontSize = 13.sp)
                }
            }
        }
    }
}

/**
 * Um campo de texto livre com sugestoes embaixo (o <datalist> da web): as que contem o texto, ate
 * seis; tocar numa preenche o campo.
 */
@Composable
fun SuggestField(value: String, onChange: (String) -> Unit, suggestions: List<String>, placeholder: String?) {
    val palette = LocalPalette.current
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        AppTextField(value = value, onValueChange = onChange, placeholder = placeholder)
        val needle = value.trim().lowercase()
        val matches = suggestions.filter { it.lowercase().contains(needle) && !it.equals(value.trim(), ignoreCase = true) }.take(6)
        if (matches.isNotEmpty()) {
            Surface(shape = RoundedCornerShape(14.dp), color = palette.surface, border = BorderStroke(1.dp, palette.border)) {
                Column(Modifier.fillMaxWidth()) {
                    matches.forEach { name ->
                        Text(
                            name,
                            color = palette.text,
                            fontSize = 14.sp,
                            modifier = Modifier
                                .fillMaxWidth()
                                .heightIn(min = 44.dp)
                                .clickable { onChange(name) }
                                .padding(horizontal = 14.dp, vertical = 12.dp),
                        )
                    }
                }
            }
        }
    }
}

/**
 * FixedIncomeFields: tipo do titulo ([types] vazio = o tipo e fixo, a compra do Tesouro),
 * rentabilidade, indexador, a taxa e o IR (so leitura, segue o tipo).
 */
@Composable
fun FixedIncomeFieldsView(value: FixedIncome.Form, onChange: (FixedIncome.Form) -> Unit, types: List<FixedIncome.Choice>) {
    val palette = LocalPalette.current
    val mode = FixedIncome.rateModeOf(value.rateType, value.indexer)
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (types.isNotEmpty()) {
            Field(stringResource(R.string.inv_fi_type)) {
                SelectField(
                    value = value.fixedIncomeType,
                    options = types.map { SelectOption(it.value, it.label) },
                    onSelect = { onChange(value.copy(fixedIncomeType = it)) },
                    placeholder = stringResource(R.string.inv_select_placeholder),
                )
            }
        }
        Field(stringResource(R.string.inv_fi_rate_mode)) {
            SelectField(
                value = mode,
                options = FixedIncome.RATE_MODES.map { SelectOption(it.value, it.label) },
                onSelect = {
                    val (rateType, indexer) = FixedIncome.rateFieldsForMode(it)
                    onChange(value.copy(rateType = rateType, indexer = indexer, rate = ""))
                },
            )
        }
        if (mode == "POS") {
            Field(stringResource(R.string.inv_fi_indexer)) {
                SelectField(
                    value = value.indexer,
                    options = FixedIncome.INDEXERS.map { SelectOption(it.value, it.label) },
                    onSelect = { onChange(value.copy(indexer = it, rate = "")) },
                )
            }
        }
        Field(FixedIncome.rateFieldLabel(value.rateType, value.indexer)) {
            AppTextField(
                value = value.rate,
                onValueChange = { onChange(value.copy(rate = it)) },
                placeholder = FixedIncome.ratePlaceholder(value.rateType, value.indexer),
                keyboardType = KeyboardType.Decimal,
            )
        }
        Field(stringResource(R.string.inv_fi_tax)) {
            val text = when {
                value.fixedIncomeType.isEmpty() -> R.string.inv_fi_tax_by_type
                FixedIncome.isTaxFreeFixedIncomeType(value.fixedIncomeType) -> R.string.inv_fi_tax_free
                else -> R.string.inv_fi_tax_regressive
            }
            Text(stringResource(text), color = palette["zinc-700"], fontSize = 14.sp)
        }
    }
}
