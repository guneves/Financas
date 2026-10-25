package br.financas.app.ui.investimentos

import android.app.Application
import android.content.Context
import android.widget.Toast
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import br.financas.app.R
import br.financas.app.core.formatCurrency
import br.financas.app.core.getLocalDateString
import br.financas.app.core.moneyInputValue
import br.financas.app.data.AccountDto
import br.financas.app.data.AppGraph
import br.financas.app.data.InboxWrite
import br.financas.app.data.InvestmentHistoryDto
import br.financas.app.data.InvestimentosRepository
import br.financas.app.data.PortfolioAssetDto
import br.financas.app.data.PortfolioDto
import br.financas.app.data.QuoteUpdateDto
import br.financas.app.outbox.OutboxRules
import br.financas.app.rules.Operations
import br.financas.app.rules.PortfolioAccount
import br.financas.app.rules.PortfolioView
import br.financas.app.ui.components.ConfirmRequest
import br.financas.app.ui.nav.NativeScreensPlugin
import br.financas.app.ui.planejar.ScreenLoad
import br.financas.app.ui.theme.ShellPrefs
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch
import java.math.BigDecimal

/** O sheet "Resgate parcial": a posicao, o valor, a data e a conta. */
data class RedeemSheet(
    val asset: PortfolioAssetDto,
    val amount: String,
    val date: String,
    val cashLink: PortfolioAccount.CashLink,
)

/**
 * Investimentos › Posicao nativo (12-investimentos-posicao.md): a carteira do servidor (copia
 * guardada primeiro), o resumo, a rosca, a evolucao, as abas e os grupos. Cotacoes, resgate e
 * exclusoes so com o servidor; "Registrar operação" e "Vender" abrem o sheet compartilhado, que
 * guarda a compra na fila sem conexao.
 */
class PosicaoViewModel(application: Application) : AndroidViewModel(application) {

    private val app = application
    private val graph = AppGraph.from(application)
    private val repo = graph.investimentos

    val portfolio = ScreenLoad<PortfolioDto>()
    val accounts = ScreenLoad<List<AccountDto>>()
    val history = ScreenLoad<InvestmentHistoryDto>()

    var hidden by mutableStateOf(ShellPrefs.valuesHidden(application) ?: false)
        private set
    var tab by mutableStateOf(PortfolioView.Tab.VARIAVEL)
        private set
    var openGroups by mutableStateOf<Set<String>>(emptySet())
        private set
    var months by mutableStateOf(PeriodStore.load(application, PATRIMONIO_PERIOD, 12, PERIODS.map { it.first.toInt() }))
        private set
    var selectedMonth by mutableStateOf<Int?>(null)
        private set
    var dataError by mutableStateOf("")
        private set
    var updatingPrices by mutableStateOf(false)
        private set
    var updatingAssetId by mutableStateOf("")
        private set
    var quoteResult by mutableStateOf<QuoteUpdateDto?>(null)
        private set
    var confirm by mutableStateOf<ConfirmRequest?>(null)
        private set

    var quoteFor by mutableStateOf<PortfolioAssetDto?>(null)
        private set
    var quoteText by mutableStateOf("")
        private set
    var quoteError by mutableStateOf("")
        private set
    var quoteSaving by mutableStateOf(false)
        private set

    var redeem by mutableStateOf<RedeemSheet?>(null)
        private set
    var redeemError by mutableStateOf("")
        private set
    var redeemSaving by mutableStateOf(false)
        private set

    var detailFor by mutableStateOf<PortfolioAssetDto?>(null)
        private set

    private val _notices = MutableSharedFlow<String>(extraBufferCapacity = 8)
    val notices: SharedFlow<String> = _notices.asSharedFlow()

    val launchSheet = LaunchSheetState(application, viewModelScope) { message -> launchFinished(message) }
    val export = InvestExportState(application, viewModelScope, InvestimentosRepository.PORTFOLIO_EXPORT_PATH, "carteira") { it.portfolio }

    private var cleared = false
    private var historyJob: Job? = null

    override fun onCleared() {
        cleared = true
        super.onCleared()
    }

    val assets: List<PortfolioAssetDto> get() = portfolio.value?.assets.orEmpty()

    fun refreshAll() {
        hidden = ShellPrefs.valuesHidden(app) ?: hidden
        viewModelScope.launch {
            portfolio.collect(app, repo.portfolio(), R.string.inv_load_failed)
            launchSheet.assets = assets
        }
        viewModelScope.launch {
            accounts.collect(app, graph.accounts.accounts(), R.string.inv_load_failed)
            launchSheet.accountsChanged(accounts.value)
        }
        readHistory()
        ProceedsSync.onOpen(app) { reread() }
    }

    private fun reread() {
        if (!cleared) refreshAll()
        NativeScreensPlugin.emitDataChanged()
    }

    private fun readHistory() {
        historyJob?.cancel()
        // O periodo anterior fica na tela enquanto o novo chega (keepPreviousData).
        historyJob = viewModelScope.launch { history.collect(app, repo.history(months), R.string.inv_history_failed) }
    }

    fun toggleHidden() {
        hidden = !hidden
        ShellPrefs.saveValuesHidden(app, hidden)
    }

    fun selectTab(next: PortfolioView.Tab) {
        tab = next
    }

    fun toggleGroup(key: String) {
        openGroups = if (key in openGroups) openGroups - key else openGroups + key
    }

    fun changeMonths(next: Int) {
        months = next
        selectedMonth = null
        PeriodStore.save(app, PATRIMONIO_PERIOD, next)
        readHistory()
    }

    fun selectMonth(index: Int) {
        selectedMonth = if (selectedMonth == index) null else index
    }

    fun dismissError() {
        dataError = ""
    }

    fun dismissConfirm() {
        confirm = null
    }

    fun closeQuoteResult() {
        quoteResult = null
    }

    // ---- Cotacoes ----

    /** "Atualizar cotações" (todas) ou a de uma posicao. Sem conexao, o aviso: precisa dos provedores. */
    fun updatePrices(asset: PortfolioAssetDto? = null) {
        if (updatingPrices) return
        updatingPrices = true
        val scoped = asset?.let { it.assetId ?: it.id }.orEmpty()
        updatingAssetId = scoped
        val body: Map<String, Any?> = if (asset != null) mapOf("asset_id" to scoped, "asset_class" to asset.assetClass) else emptyMap()
        viewModelScope.launch {
            val result = repo.updatePrices(body)
            updatingPrices = false
            updatingAssetId = ""
            when (result) {
                is InboxWrite.Done -> {
                    quoteResult = result.value
                    // So refaz as telas se alguma cotacao mudou (refreshQuotes).
                    if (result.value.updatedCount > 0) reread()
                }
                else -> dataError = investWriteError(app, result, R.string.inv_quotes_failed).orEmpty()
            }
        }
    }

    fun openQuote(asset: PortfolioAssetDto) {
        quoteFor = asset
        quoteText = moneyInputValue(asset.currentPrice)
        quoteError = ""
    }

    fun changeQuote(text: String) {
        quoteText = text
    }

    fun closeQuote() {
        if (!quoteSaving) quoteFor = null
    }

    fun saveQuote() {
        val asset = quoteFor ?: return
        if (quoteSaving) return
        val price = Operations.parseNumberInput(quoteText)
        if (price == null || price.signum() < 0) {
            quoteError = app.getString(R.string.inv_quote_invalid)
            return
        }
        quoteSaving = true
        quoteError = ""
        graph.appScope.launch {
            val result = repo.updatePriceByAsset(asset.assetId ?: asset.id, asset.assetClass.orEmpty(), price)
            quoteSaving = false
            val error = investWriteError(app, result, R.string.inv_quote_failed)
            when {
                error == null -> {
                    quoteFor = null
                    notice(app.getString(R.string.inv_quote_saved, asset.name.orEmpty()))
                    reread()
                }
                cleared -> Toast.makeText(app, error, Toast.LENGTH_LONG).show()
                else -> quoteError = error
            }
        }
    }

    // ---- Resgate parcial ----

    fun openRedeem(asset: PortfolioAssetDto) {
        redeem = RedeemSheet(asset, "", getLocalDateString(), settleCashLink(PortfolioAccount.emptyCashLink(), accounts.value))
        redeemError = ""
    }

    fun changeRedeem(next: RedeemSheet) {
        redeem = next
    }

    fun closeRedeem() {
        if (!redeemSaving) redeem = null
    }

    /** POST /api/investments/redemptions: o servidor divide pelas compras (PEPS) e grava. */
    fun saveRedeem() {
        val sheet = redeem ?: return
        if (redeemSaving) return
        val amount = Operations.parseNumberInput(sheet.amount)
        val limit = sheet.asset.currentValue ?: BigDecimal.ZERO
        if (amount == null || amount.signum() <= 0 || amount > limit) {
            redeemError = app.getString(R.string.inv_redeem_range, br.financas.app.ui.lancamentos.moneyOrMasked(limit, hidden))
            return
        }
        if (sheet.date.isEmpty()) {
            redeemError = app.getString(R.string.inv_redeem_date)
            return
        }
        val cash = try {
            PortfolioAccount.cashLinkMetadata(sheet.cashLink)
        } catch (refused: PortfolioAccount.CashLinkError) {
            redeemError = refused.message.orEmpty()
            return
        }
        val body = linkedMapOf<String, Any?>("position_id" to sheet.asset.id, "amount" to amount, "date" to sheet.date)
        body.putAll(cash)
        // Um toque duplo (ou um reenvio) nao grava dois resgates (042).
        body["client_id"] = OutboxRules.newClientId()
        redeemSaving = true
        redeemError = ""
        graph.appScope.launch {
            val result = repo.redeem(body)
            redeemSaving = false
            val error = investWriteError(app, result, R.string.inv_redeem_failed)
            when {
                error == null -> {
                    redeem = null
                    notice(app.getString(R.string.inv_redeem_saved, formatCurrency(amount)))
                    ProceedsSync.afterWrite(app, "/api/investments/redemptions") { reread() }
                    reread()
                }
                cleared -> Toast.makeText(app, error, Toast.LENGTH_LONG).show()
                else -> redeemError = error
            }
        }
    }

    // ---- Detalhes e exclusao ----

    fun openDetail(asset: PortfolioAssetDto) {
        detailFor = asset
    }

    fun closeDetail() {
        detailFor = null
    }

    fun askDelete(asset: PortfolioAssetDto) {
        val view = positionOf(asset)
        val singleBuy = asset.assetClass == "FIXED_INCOME" && view.lotCount <= 1
        val name = asset.name.orEmpty()
        confirm = ConfirmRequest(
            title = app.getString(if (singleBuy) R.string.inv_delete_contribution_title else R.string.inv_delete_position_title, name),
            message = app.getString(if (singleBuy) R.string.inv_delete_contribution_message else R.string.inv_delete_position_message),
            confirmLabel = app.getString(R.string.inv_delete),
        ) {
            dataError = ""
            graph.appScope.launch {
                val assetClass = asset.assetClass.orEmpty()
                val result = when (val target = PortfolioView.deleteTarget(view, asset.assetId, asset.assetIds)) {
                    is PortfolioView.DeleteTarget.Assets -> repo.deleteByAssets(target.assetIds, assetClass)
                    is PortfolioView.DeleteTarget.Movement -> repo.deleteMovement(target.id)
                    is PortfolioView.DeleteTarget.Asset -> repo.deleteByAsset(target.assetId, assetClass)
                }
                val error = investWriteError(app, result, R.string.inv_delete_failed)
                when {
                    error == null -> {
                        ProceedsSync.afterWrite(app, "/api/investments") { reread() }
                        reread()
                    }
                    cleared -> Toast.makeText(app, error, Toast.LENGTH_LONG).show()
                    else -> dataError = error
                }
            }
        }
    }

    private fun notice(message: String) {
        if (cleared) Toast.makeText(app, message, Toast.LENGTH_SHORT).show() else _notices.tryEmit(message)
    }

    /** A compra ou venda gravou (ou ficou na fila): a tela rele. */
    fun launchFinished(message: String) {
        notice(message)
        reread()
    }

    companion object {
        const val PATRIMONIO_PERIOD = "patrimonioPeriod"

        /** 6M..5A: o backend limita o historico a 60 meses. */
        val PERIODS = listOf("6" to "6M", "12" to "1A", "24" to "2A", "36" to "3A", "60" to "5A")

        fun positionOf(asset: PortfolioAssetDto) = PortfolioView.Position(
            id = asset.id,
            assetClass = asset.assetClass,
            category = asset.category,
            categoryLabel = asset.categoryLabel,
            marketKind = asset.marketKind,
            rateKind = asset.rateKind,
            fixedIncomeType = Operations.metaText(asset.metadata, "fixed_income_type"),
            currentValue = asset.currentValue,
            lotCount = asset.lots.size,
            hasTreasury = asset.treasury != null,
        )
    }
}

/** Os periodos lembrados por aparelho (o @financeMVP:...Period da web), um por tela. */
object PeriodStore {
    private const val PREFS = "financas_native_invest"

    fun load(context: Context, key: String, fallback: Int, allowed: List<Int>): Int {
        val saved = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getInt(key, fallback)
        return if (saved in allowed) saved else fallback
    }

    fun save(context: Context, key: String, value: Int) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putInt(key, value).apply()
    }

    fun loadText(context: Context, key: String, fallback: String, allowed: List<String>): String {
        val saved = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(key, fallback) ?: fallback
        return if (saved in allowed) saved else fallback
    }

    fun saveText(context: Context, key: String, value: String) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString(key, value).apply()
    }

    fun loadSet(context: Context, key: String, fallback: Set<String>): Set<String> =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getStringSet(key, null)?.toSet() ?: fallback

    fun saveSet(context: Context, key: String, value: Set<String>) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putStringSet(key, value).apply()
    }
}
