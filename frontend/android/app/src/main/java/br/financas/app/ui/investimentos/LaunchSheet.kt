package br.financas.app.ui.investimentos

import android.app.Application
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.core.formatCurrency
import br.financas.app.core.formatQuantity
import br.financas.app.core.getLocalDateString
import br.financas.app.core.monthLabel
import br.financas.app.data.AccountDto
import br.financas.app.data.AppGraph
import br.financas.app.data.ExemptionDto
import br.financas.app.data.InboxWrite
import br.financas.app.data.JsonBody
import br.financas.app.data.MarketTickerDto
import br.financas.app.data.PortfolioAssetDto
import br.financas.app.rules.AssetSearch
import br.financas.app.rules.FixedIncome
import br.financas.app.rules.Operations
import br.financas.app.rules.PortfolioAccount
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AlertTone
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.AppSheet
import br.financas.app.ui.components.AppTextField
import br.financas.app.ui.components.ButtonVariant
import br.financas.app.ui.components.DateField
import br.financas.app.ui.components.Field
import br.financas.app.ui.components.SegmentedChoice
import br.financas.app.ui.components.SelectField
import br.financas.app.ui.components.SelectOption
import br.financas.app.ui.lancamentos.moneyOrMasked
import br.financas.app.ui.nav.NativeScreensPlugin
import br.financas.app.ui.newentry.NewEntryForms
import br.financas.app.ui.newentry.SaveResult
import br.financas.app.ui.theme.LocalPalette
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.math.BigDecimal

/**
 * "Registrar operação" (InvestmentLaunchModal, 13-investimentos-operacoes.md): compra ou venda, de
 * Posicao e de Operacoes. A criacao leva client_id e vai pela fila quando o servidor nao responde
 * (como o "+ Novo"); o resto do formulario e o da web.
 *
 * [scope] e o da tela (busca, aviso de isencao); o Salvar roda no appScope e termina mesmo com a
 * tela fechada. [onFinished] recebe o aviso (gravado ou guardado) para o snackbar da tela.
 */
class LaunchSheetState(
    private val app: Application,
    private val scope: CoroutineScope,
    private val onFinished: (String) -> Unit,
) {
    private val graph = AppGraph.from(app)
    private val repo = graph.investimentos
    private val saver = investmentSaver(app)

    var open by mutableStateOf(false)
        private set
    var form by mutableStateOf(Operations.LaunchForm())
        private set
    var saving by mutableStateOf(false)
        private set
    var error by mutableStateOf("")
        private set
    var tickerOptions by mutableStateOf<List<MarketTickerDto>>(emptyList())
        private set
    var tickerOpen by mutableStateOf(false)
        private set
    var saleQuery by mutableStateOf("")
        private set
    var salePickerOpen by mutableStateOf(true)
        private set
    var exemption by mutableStateOf<ExemptionDto?>(null)
        private set

    /** As posicoes da carteira (venda, sugestoes) e as contas (CashLinkField): a tela atualiza. */
    var assets by mutableStateOf<List<PortfolioAssetDto>>(emptyList())
    var accounts by mutableStateOf<List<AccountDto>?>(null)

    private var searchJob: Job? = null
    private var exemptionJob: Job? = null

    /** Venda: as posicoes de renda variavel com quantidade, pelo nome. */
    val saleAssets: List<PortfolioAssetDto>
        get() = assets.filter { it.assetClass != "FIXED_INCOME" && (it.quantity ?: BigDecimal.ZERO).signum() > 0 }
            .sortedBy { it.name.orEmpty() }

    val selectedSaleAsset: PortfolioAssetDto? get() = saleAssets.firstOrNull { it.id == form.assetId }

    fun openBuy() {
        form = Operations.LaunchForm(date = getLocalDateString())
        start()
    }

    /** "Vender" de uma posicao: a venda ja nela, com a cotacao como preco. */
    fun openSell(asset: PortfolioAssetDto) {
        form = Operations.LaunchForm(
            mode = "SELL",
            assetType = Operations.assetTypeOf(asset.assetClass, asset.marketKind, asset.category),
            assetId = asset.id,
            tickerOrName = asset.ticker ?: asset.name.orEmpty(),
            price = Operations.saleUnitPrice(asset.currentPrice),
            date = getLocalDateString(),
        )
        salePickerOpen = false
        start()
        refreshExemption()
    }

    private fun start() {
        error = ""
        tickerOptions = emptyList()
        tickerOpen = false
        saleQuery = ""
        exemption = null
        if (form.mode == "BUY") salePickerOpen = true
        form = form.copy(cashLink = settleCashLink(form.cashLink, accounts))
        open = true
    }

    fun close() {
        if (!saving) open = false
    }

    /** As contas chegaram (ou mudaram): o campo da conta se acerta. */
    fun accountsChanged(next: List<AccountDto>?) {
        accounts = next
        if (open) form = form.copy(cashLink = settleCashLink(form.cashLink, next))
    }

    fun change(next: Operations.LaunchForm) {
        val sellChanged = next.quantity != form.quantity || next.price != form.price || next.date != form.date
        form = next
        if (next.mode == "SELL" && sellChanged) refreshExemption()
    }

    fun changeMode(mode: String) {
        error = ""
        form = Operations.changeMode(form, mode)
        saleQuery = ""
        salePickerOpen = true
        exemption = null
    }

    fun changeAssetType(type: String) {
        form = Operations.changeAssetType(form, type)
        tickerOptions = emptyList()
        tickerOpen = false
    }

    fun changeFixedIncomeName(name: String) {
        form = Operations.changeFixedIncomeName(form, name)
    }

    fun changeCashLink(value: PortfolioAccount.CashLink) {
        form = form.copy(cashLink = value)
    }

    // ---- O ticker da B3 (TickerAutocomplete) ----

    /** Digitar: caixa alta, sem ativo valido ate escolher da lista; a busca vai 180 ms depois. */
    fun typeTicker(text: String) {
        val ticker = Operations.normalizeAssetName(text)
        form = form.copy(tickerOrName = ticker, tickerConfirmed = false)
        tickerOpen = true
        searchJob?.cancel()
        val assetClass = Operations.movementAssetClass(form.assetType)
        val type = form.assetType
        searchJob = scope.launch {
            delay(SEARCH_DEBOUNCE_MS)
            val kind = if (type == Operations.ETF) Operations.ETF else ""
            val result = repo.searchTickers(ticker, assetClass, kind)
            val catalog = (result as? InboxWrite.Done)?.value.orEmpty().filter { type != "STOCKS" || it.kind != Operations.ETF }
            val known = catalog.map { it.ticker }.toSet()
            val wallet = walletTickers(assetClass, type).filter { it.ticker !in known && (ticker.isEmpty() || it.ticker.contains(ticker)) }
            tickerOptions = catalog + wallet
        }
    }

    fun pickTicker(option: MarketTickerDto) {
        searchJob?.cancel()
        form = form.copy(tickerOrName = option.ticker, tickerConfirmed = true)
        tickerOpen = false
    }

    // As posicoes da classe como opcao "Na carteira" (um papel antigo, fora do catalogo).
    private fun walletTickers(assetClass: String, type: String): List<MarketTickerDto> = assets
        .filter { it.assetClass == assetClass }
        .filter { (type != Operations.ETF || it.marketKind == Operations.ETF) && (type != "STOCKS" || it.marketKind != Operations.ETF) }
        .mapNotNull { asset ->
            val ticker = Operations.normalizeAssetName(asset.ticker ?: asset.name)
            if (ticker.isEmpty()) null else MarketTickerDto(ticker, asset.name ?: asset.ticker, "CARTEIRA", app.getString(R.string.inv_launch_in_wallet))
        }

    /** Nomes sugeridos na renda fixa (os titulos do tipo; no Tesouro, mais os que o Tesouro vende) e em Outros. */
    fun nameSuggestions(): List<String> {
        val treasury = form.assetType == Operations.TREASURY
        if (form.isFixedIncome) {
            val own = assets.filter { it.assetClass == "FIXED_INCOME" && (it.category == "TESOURO") == treasury }.map { it.ticker ?: it.name.orEmpty() }
            return (if (treasury) own + FixedIncome.TREASURY_TITLES else own).distinct()
        }
        return assets.filter { it.assetClass == form.assetType }.map { it.ticker ?: it.name.orEmpty() }.distinct()
    }

    // ---- Venda ----

    fun typeSaleQuery(text: String) {
        saleQuery = text
        salePickerOpen = true
    }

    fun reopenSalePicker() {
        salePickerOpen = true
    }

    fun pickSaleAsset(assetId: String) {
        val asset = saleAssets.firstOrNull { it.id == assetId }
        form = form.copy(
            assetId = assetId,
            assetType = asset?.let { Operations.assetTypeOf(it.assetClass, it.marketKind, it.category) } ?: form.assetType,
            tickerOrName = asset?.ticker ?: asset?.name.orEmpty(),
            price = Operations.saleUnitPrice(asset?.currentPrice).ifEmpty { form.price },
        )
        salePickerOpen = false
        refreshExemption()
    }

    fun saleOptions(hidden: Boolean): List<PickerOption> {
        val options = saleAssets.map { asset ->
            val quantity = asset.quantity ?: BigDecimal.ZERO
            val meta = listOfNotNull(
                asset.categoryLabel?.takeIf { it.isNotEmpty() },
                "${formatQuantity(quantity)} ${if (quantity.compareTo(BigDecimal.ONE) == 0) "cota" else "cotas"}",
                asset.name?.takeIf { it.isNotEmpty() && it != asset.ticker },
            ).joinToString(" · ")
            PickerOption(asset.id, asset.ticker ?: asset.name.orEmpty(), meta, moneyOrMasked(asset.currentValue, hidden))
        }
        val names = saleAssets.associate { it.id to it.name }
        return AssetSearch.filterAssetOptions(options, saleQuery, label = { it.label }, name = { names[it.value] })
    }

    /** O aviso da isencao da venda de acoes, 400 ms depois de parar de digitar (SaleExemptionNotice). */
    private fun refreshExemption() {
        exemptionJob?.cancel()
        val asset = selectedSaleAsset
        val month = form.date.take(7)
        val planned = Operations.launchQuantity(form) * Operations.parseAmount(form.price)
        if (asset == null || asset.assetClass != "STOCKS" || !Regex("^\\d{4}-\\d{2}$").matches(month) || planned.signum() <= 0) {
            exemption = null
            return
        }
        val ticker = asset.ticker ?: asset.name.orEmpty()
        exemptionJob = scope.launch {
            delay(EXEMPTION_DEBOUNCE_MS)
            val result = repo.saleExemption(month, planned.stripTrailingZeros().toPlainString(), ticker)
            exemption = (result as? InboxWrite.Done)?.value?.takeIf { it.month == month }
        }
    }

    // ---- Salvar ----

    fun save() {
        if (saving) return
        val current = form
        error = ""
        val body: Map<String, Any?> = try {
            if (current.mode == "BUY") {
                val ticker = Operations.normalizeAssetName(current.tickerOrName)
                val existing = assets.firstOrNull { Operations.normalizeAssetName(it.ticker ?: it.name) == ticker }
                Operations.buyPayload(current, existing?.currentPrice, existing != null)
            } else {
                val asset = selectedSaleAsset
                Operations.sellPayload(
                    current,
                    asset?.let { Operations.SaleAsset(it.assetClass.orEmpty(), it.ticker ?: it.name.orEmpty(), it.quantity ?: BigDecimal.ZERO, it.averagePrice, it.currentPrice) },
                )
            }
        } catch (refused: IllegalArgumentException) {
            error = refused.message.orEmpty()
            return
        }
        saving = true
        val ticker = body["ticker_or_name"] as? String ?: ""
        val buy = current.mode == "BUY"
        graph.appScope.launch {
            // O ticker digitado sem passar pela lista: confere no catalogo (so com o servidor; sem
            // ele, a fila manda e o servidor recusa se nao for da B3).
            if (buy && Operations.needsCatalogCheck(current, assets.map { it.ticker ?: it.name.orEmpty() })) {
                val known = repo.ticker(ticker)
                if (known is InboxWrite.Done && known.value == null || known is InboxWrite.Refused) {
                    saving = false
                    error = Operations.notInCatalogMessage(ticker)
                    return@launch
                }
            }
            val label = app.getString(if (buy) R.string.inv_launch_buy_label else R.string.inv_launch_sell_label, ticker)
            val result = saver.createJson("INVESTMENT", JSONObject(JsonBody.encode(body)), title = ticker)
            saving = false
            when (result) {
                is SaveResult.Saved -> {
                    open = false
                    val created = (result.data as? JSONArray)?.optJSONObject(0)?.optString("id").orEmpty()
                    if (buy && created.isNotEmpty()) {
                        graph.appScope.launch { repo.updatePrices(mapOf("investment_id" to created)) }
                    }
                    ProceedsSync.afterWrite(app, "/api/investments") { NativeScreensPlugin.emitDataChanged() }
                    NativeScreensPlugin.emitDataChanged()
                    onFinished(NewEntryForms.savedNotice(label).message)
                }
                is SaveResult.Queued -> {
                    open = false
                    NativeScreensPlugin.emitDataChanged()
                    onFinished(NewEntryForms.queuedNotice(label).message)
                }
                is SaveResult.Refused -> error = result.message ?: app.getString(R.string.inv_launch_failed)
                is SaveResult.SessionExpired -> error = result.message ?: app.getString(R.string.data_session_expired)
            }
        }
    }

    companion object {
        const val SEARCH_DEBOUNCE_MS = 180L
        const val EXEMPTION_DEBOUNCE_MS = 400L
    }
}

/** O texto do aviso da isencao de uma venda de acoes (SaleExemptionNotice); null sem aviso. */
fun exemptionNotice(app: Application, data: ExemptionDto, month: String): Pair<String, AlertTone> {
    val label = monthLabel(month)
    return when {
        !data.eligible -> app.getString(if (data.kind == "ETF_RF") R.string.inv_exemption_etf_rf else R.string.inv_exemption_etf) to AlertTone.INFO
        data.wouldExceed -> app.getString(
            R.string.inv_exemption_would_exceed,
            label,
            formatCurrency(data.salesAfter),
            formatCurrency(data.limit),
            formatCurrency(data.remaining),
        ) to AlertTone.WARNING
        !data.exempt -> app.getString(R.string.inv_exemption_over, label, formatCurrency(data.limit)) to AlertTone.INFO
        else -> app.getString(
            R.string.inv_exemption_room,
            label,
            formatCurrency(((data.limit ?: BigDecimal.ZERO) - (data.salesAfter ?: BigDecimal.ZERO)).max(BigDecimal.ZERO)),
        ) to AlertTone.INFO
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LaunchSheetView(state: LaunchSheetState, hidden: Boolean, app: Application) {
    if (!state.open) return
    val palette = LocalPalette.current
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val form = state.form
    val buy = form.mode == "BUY"
    val cancel = stringResource(R.string.lanc_cancel)
    val dismiss = stringResource(R.string.lanc_dismiss)
    AppSheet(
        title = stringResource(R.string.inv_launch_title),
        sheetState = sheetState,
        onDismiss = state::close,
        footer = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(stringResource(R.string.inv_launch_total), color = palette["zinc-600"], fontSize = 14.sp, modifier = Modifier.weight(1f))
                    Text(formatCurrency(Operations.launchTotal(form)), color = palette.text, fontWeight = FontWeight.ExtraBold, fontSize = 18.sp)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    AppButton(cancel, state::close, Modifier.weight(1f), variant = ButtonVariant.SECONDARY)
                    AppButton(
                        stringResource(if (buy) R.string.inv_launch_save_buy else R.string.inv_launch_save_sell),
                        state::save,
                        Modifier.weight(1f),
                        loading = state.saving,
                    )
                }
            }
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text(stringResource(R.string.inv_launch_description), color = palette["zinc-600"], fontSize = 14.sp)
            SegmentedChoice(
                items = listOf(SelectOption("BUY", stringResource(R.string.inv_launch_buy)), SelectOption("SELL", stringResource(R.string.inv_launch_sell))),
                value = form.mode,
                onChange = state::changeMode,
            )
            AlertMessage(state.error, AlertTone.DANGER, dismiss)
            Field(stringResource(R.string.inv_launch_asset_type)) {
                if (buy) {
                    SelectField(
                        value = form.assetType,
                        options = Operations.ASSET_TYPES.map { SelectOption(it.first, it.second) },
                        onSelect = state::changeAssetType,
                    )
                } else {
                    Text(Operations.ASSET_TYPES.firstOrNull { it.first == form.assetType }?.second.orEmpty(), color = palette["zinc-700"], fontSize = 15.sp)
                }
            }
            Field(stringResource(R.string.inv_launch_asset)) {
                when {
                    buy && form.assetType == Operations.BITCOIN ->
                        Text(stringResource(R.string.inv_launch_bitcoin), color = palette["zinc-700"], fontSize = 15.sp)
                    buy && form.usesCatalog -> Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        AppTextField(
                            value = form.tickerOrName,
                            onValueChange = state::typeTicker,
                            placeholder = stringResource(if (form.assetType == Operations.ETF) R.string.inv_launch_ticker_etf else R.string.inv_launch_ticker),
                        )
                        if (state.tickerOpen) {
                            val options = state.tickerOptions.map { PickerOption(it.ticker, it.ticker, it.name.orEmpty(), it.kindLabel.orEmpty()) }
                            AssetOptions(options, stringResource(R.string.inv_launch_no_ticker)) { picked ->
                                state.tickerOptions.firstOrNull { it.ticker == picked.value }?.let(state::pickTicker)
                            }
                        }
                    }
                    buy && form.isFixedIncome -> SuggestField(
                        form.tickerOrName,
                        state::changeFixedIncomeName,
                        state.nameSuggestions(),
                        stringResource(if (form.assetType == Operations.TREASURY) R.string.inv_launch_name_treasury else R.string.inv_launch_name_fixed),
                    )
                    buy -> SuggestField(form.tickerOrName, { state.change(form.copy(tickerOrName = it)) }, state.nameSuggestions(), stringResource(R.string.inv_launch_name_other))
                    else -> {
                        val options = state.saleOptions(hidden)
                        val selected = state.selectedSaleAsset?.let { asset -> state.saleOptions(hidden).firstOrNull { it.value == asset.id } ?: PickerOption(asset.id, asset.ticker ?: asset.name.orEmpty()) }
                        AssetPickerField(
                            query = state.saleQuery,
                            onQuery = state::typeSaleQuery,
                            selected = selected,
                            options = options,
                            onPick = { state.pickSaleAsset(it.value) },
                            placeholder = stringResource(R.string.inv_launch_sale_search),
                            emptyMessage = stringResource(R.string.inv_launch_sale_empty),
                            open = state.salePickerOpen || selected == null,
                            onOpen = state::reopenSalePicker,
                        )
                    }
                }
            }
            Field(stringResource(R.string.inv_launch_date)) {
                DateField(form.date, { state.change(form.copy(date = it)) }, stringResource(R.string.lanc_date_ok), cancel)
            }
            if (!(form.isFixedIncome && buy)) {
                Field(stringResource(R.string.inv_launch_quantity)) {
                    AppTextField(form.quantity, { state.change(form.copy(quantity = it)) }, keyboardType = KeyboardType.Decimal)
                }
            }
            Field(stringResource(if (form.isFixedIncome && buy) R.string.inv_launch_applied else R.string.inv_launch_price)) {
                AppTextField(form.price, { state.change(form.copy(price = it)) }, placeholder = "0,00", keyboardType = KeyboardType.Decimal)
            }
            Field(stringResource(R.string.inv_launch_costs)) {
                AppTextField(form.otherCosts, { state.change(form.copy(otherCosts = it)) }, placeholder = "0,00", keyboardType = KeyboardType.Decimal)
            }
            if (buy && form.assetType == Operations.TREASURY) {
                Field(stringResource(R.string.inv_launch_units), hint = stringResource(R.string.inv_launch_units_hint)) {
                    AppTextField(form.treasuryUnits, { state.change(form.copy(treasuryUnits = it)) }, placeholder = "Ex: 0,85", keyboardType = KeyboardType.Decimal)
                }
            }
            if (buy && form.isFixedIncome) {
                FixedIncomeFieldsView(
                    form.fixedIncome,
                    { state.change(form.copy(fixedIncome = it)) },
                    if (form.assetType == Operations.TREASURY) emptyList() else FixedIncome.FIXED_INCOME_TYPES.filter { it.value != FixedIncome.TREASURY_TYPE },
                )
            }
            if (!buy && state.saleAssets.isEmpty()) {
                AlertMessage(stringResource(R.string.inv_launch_no_sale_assets), AlertTone.WARNING, dismiss)
            }
            state.exemption?.let { data ->
                if (!buy && state.selectedSaleAsset?.assetClass == "STOCKS") {
                    val (text, tone) = exemptionNotice(app, data, form.date.take(7))
                    AlertMessage(text, tone, dismiss)
                }
            }
            CashLinkField(form.cashLink, state::changeCashLink, state.accounts, form.mode)
        }
    }
}

@Composable
private fun AssetOptions(options: List<PickerOption>, emptyMessage: String, onPick: (PickerOption) -> Unit) {
    AssetPickerField(
        query = "",
        onQuery = {},
        selected = null,
        options = options,
        onPick = onPick,
        placeholder = "",
        emptyMessage = emptyMessage,
        open = true,
        onOpen = {},
        showSearch = false,
    )
}
