package br.financas.app.ui.investimentos

import android.app.Application
import android.widget.Toast
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import br.financas.app.R
import br.financas.app.core.formatDateBR
import br.financas.app.core.getLocalDateString
import br.financas.app.data.AccountDto
import br.financas.app.data.AppGraph
import br.financas.app.data.ContributionsDto
import br.financas.app.data.CorporateActionDto
import br.financas.app.data.InboxWrite
import br.financas.app.data.InvestimentosRepository
import br.financas.app.data.OperationDto
import br.financas.app.data.PortfolioDto
import br.financas.app.outbox.OutboxRules
import br.financas.app.rules.Operations
import br.financas.app.rules.PortfolioAccount
import br.financas.app.ui.components.ConfirmRequest
import br.financas.app.ui.nav.NativeScreensPlugin
import br.financas.app.ui.planejar.ScreenLoad
import br.financas.app.ui.theme.ShellPrefs
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch

/** O sheet "Editar operação": a operacao e o formulario. */
data class EditSheet(val movement: OperationDto, val form: Operations.EditForm)

/** O sheet "Registrar evento corporativo". */
data class CorporateForm(
    val assetId: String,
    val actionType: String = "SPLIT",
    val exDate: String,
    val ratioFrom: String = "1",
    val ratioTo: String = "2",
    val bonusUnitCost: String = "",
    val notes: String = "",
)

/**
 * Investimentos › Operacoes nativo (13-investimentos-operacoes.md): a lista de operacoes, o
 * resumo realizado do servidor (realized_result), Aportes e resgates, os eventos corporativos e o
 * "Registrar operação". Editar, excluir e os eventos so com o servidor; a compra e a venda novas
 * vao para a fila sem conexao.
 */
class OperacoesViewModel(application: Application) : AndroidViewModel(application) {

    private val app = application
    private val graph = AppGraph.from(application)
    private val repo = graph.investimentos

    val operations = ScreenLoad<List<OperationDto>>()
    val portfolio = ScreenLoad<PortfolioDto>()
    val accounts = ScreenLoad<List<AccountDto>>()
    val allAccounts = ScreenLoad<List<AccountDto>>()
    val events = ScreenLoad<List<CorporateActionDto>>()
    val contributions = ScreenLoad<ContributionsDto>()

    var hidden by mutableStateOf(ShellPrefs.valuesHidden(application) ?: false)
        private set
    var dataError by mutableStateOf("")
        private set
    var confirm by mutableStateOf<ConfirmRequest?>(null)
        private set
    var queued by mutableStateOf(0)
        private set

    var aportesOpen by mutableStateOf(true)
        private set
    var aportesMonths by mutableStateOf(12)
        private set
    var aportesClass by mutableStateOf("")
        private set
    var aportesSelected by mutableStateOf<Int?>(null)
        private set

    var edit by mutableStateOf<EditSheet?>(null)
        private set
    var editError by mutableStateOf("")
        private set
    var editSaving by mutableStateOf(false)
        private set

    var corporate by mutableStateOf<CorporateForm?>(null)
        private set
    var corporateError by mutableStateOf("")
        private set
    var corporateSaving by mutableStateOf(false)
        private set
    var eventsError by mutableStateOf("")
        private set

    private val _notices = MutableSharedFlow<String>(extraBufferCapacity = 8)
    val notices: SharedFlow<String> = _notices.asSharedFlow()

    val launchSheet = LaunchSheetState(application, viewModelScope) { message -> launchFinished(message) }
    val export = InvestExportState(application, viewModelScope, InvestimentosRepository.MOVEMENTS_EXPORT_PATH, "operacoes") { it.movements }

    private var cleared = false
    private var aportesJob: Job? = null

    override fun onCleared() {
        cleared = true
        super.onCleared()
    }

    fun refreshAll() {
        hidden = ShellPrefs.valuesHidden(app) ?: hidden
        queued = queuedCount(app, "INVESTMENT")
        viewModelScope.launch { operations.collect(app, repo.operations(), R.string.inv_operations_failed) }
        viewModelScope.launch {
            portfolio.collect(app, repo.portfolio(), R.string.inv_load_failed)
            launchSheet.assets = portfolio.value?.assets.orEmpty()
        }
        viewModelScope.launch {
            accounts.collect(app, graph.accounts.accounts(), R.string.inv_load_failed)
            launchSheet.accountsChanged(accounts.value)
        }
        viewModelScope.launch { events.collect(app, repo.corporateActions(), R.string.inv_events_failed) }
        readAportes()
        ProceedsSync.onOpen(app) { reread() }
    }

    private fun reread() {
        if (!cleared) refreshAll()
        NativeScreensPlugin.emitDataChanged()
    }

    fun toggleHidden() {
        hidden = !hidden
        ShellPrefs.saveValuesHidden(app, hidden)
    }

    fun dismissError() {
        dataError = ""
    }

    fun dismissEventsError() {
        eventsError = ""
    }

    fun dismissConfirm() {
        confirm = null
    }

    // ---- Aportes e resgates ----

    private fun readAportes() {
        if (!aportesOpen) return
        aportesJob?.cancel()
        aportesJob = viewModelScope.launch { contributions.collect(app, repo.contributions(aportesMonths, aportesClass), R.string.inv_aportes_failed) }
    }

    fun toggleAportes() {
        aportesOpen = !aportesOpen
        readAportes()
    }

    fun changeAportesMonths(months: Int) {
        aportesMonths = months
        aportesSelected = null
        readAportes()
    }

    fun changeAportesClass(assetClass: String) {
        aportesClass = assetClass
        aportesSelected = null
        readAportes()
    }

    fun selectAportesMonth(index: Int) {
        aportesSelected = if (aportesSelected == index) null else index
    }

    // ---- Editar e excluir ----

    fun openEdit(movement: OperationDto) {
        edit = EditSheet(movement, Operations.editForm(movementOf(movement), movement.tickerOrName.orEmpty(), Operations.fixedIncomeMetadata(movement.metadata)))
        editError = ""
        // A conta gravada que nao e (mais) uma Corretora ativa: o nome dela vem da lista completa.
        val saved = Operations.cashAccountOf(movement.metadata)
        if (saved.isNotEmpty() && accounts.value?.none { it.id == saved } == true) {
            viewModelScope.launch { allAccounts.collect(app, graph.accounts.accounts(includeArchived = true), R.string.inv_load_failed) }
        }
    }

    fun changeEdit(form: Operations.EditForm) {
        edit = edit?.copy(form = form)
    }

    fun closeEdit() {
        if (!editSaving) edit = null
    }

    fun saveEdit() {
        val sheet = edit ?: return
        if (editSaving) return
        val body = try {
            Operations.editPayload(sheet.form, sheet.movement.metadata)
        } catch (refused: IllegalArgumentException) {
            editError = app.getString(R.string.inv_edit_error, refused.message.orEmpty())
            return
        }
        editSaving = true
        editError = ""
        graph.appScope.launch {
            val result = repo.updateMovement(sheet.movement.id, body)
            editSaving = false
            val error = investWriteError(app, result, R.string.inv_edit_failed)
            when {
                error == null -> {
                    edit = null
                    notice(app.getString(R.string.inv_edit_saved))
                    // A cotacao vai por tras (refreshQuotes); a tela nao espera por ela.
                    graph.appScope.launch { repo.updatePrices(mapOf("investment_id" to sheet.movement.id)) }
                    ProceedsSync.afterWrite(app, "/api/investments/${sheet.movement.id}") { reread() }
                    reread()
                }
                cleared -> Toast.makeText(app, error, Toast.LENGTH_LONG).show()
                else -> editError = app.getString(R.string.inv_edit_error, error)
            }
        }
    }

    fun askDelete(movement: OperationDto) {
        confirm = ConfirmRequest(
            title = app.getString(R.string.inv_delete_movement_title),
            message = app.getString(R.string.inv_delete_movement_message),
            confirmLabel = app.getString(R.string.inv_delete),
        ) {
            dataError = ""
            graph.appScope.launch {
                val result = repo.deleteMovement(movement.id)
                val error = investWriteError(app, result, R.string.inv_delete_movement_failed)
                when {
                    error == null -> {
                        notice(app.getString(R.string.inv_delete_movement_done))
                        ProceedsSync.afterWrite(app, "/api/investments/${movement.id}") { reread() }
                        reread()
                    }
                    cleared -> Toast.makeText(app, error, Toast.LENGTH_LONG).show()
                    else -> dataError = error
                }
            }
        }
    }

    // ---- Eventos corporativos ----

    /** Um ativo por asset_id, so acoes e FIIs, pelo ticker. */
    val eligibleAssets: List<Pair<String, String>>
        get() {
            val seen = LinkedHashMap<String, String>()
            portfolio.value?.assets.orEmpty().forEach { asset ->
                val id = asset.assetId ?: asset.id
                if (asset.assetClass in listOf("STOCKS", "REIT") && id !in seen) seen[id] = asset.ticker ?: asset.name.orEmpty()
            }
            return seen.toList().sortedBy { it.second }
        }

    fun openCorporate() {
        corporate = CorporateForm(assetId = eligibleAssets.firstOrNull()?.first.orEmpty(), exDate = getLocalDateString())
        corporateError = ""
    }

    fun changeCorporate(form: CorporateForm) {
        corporate = form
    }

    fun changeCorporateType(type: String) {
        val (from, to) = Operations.DEFAULT_RATIOS[type] ?: ("1" to "2")
        corporate = corporate?.copy(actionType = type, ratioFrom = from, ratioTo = to)
    }

    fun closeCorporate() {
        if (!corporateSaving) corporate = null
    }

    fun saveCorporate() {
        val form = corporate ?: return
        if (corporateSaving) return
        val body = LinkedHashMap(Operations.corporateActionPayload(form.assetId, form.actionType, form.exDate, form.ratioFrom, form.ratioTo, form.bonusUnitCost, form.notes))
        // Um toque duplo nao registra o evento duas vezes (042).
        body["client_id"] = OutboxRules.newClientId()
        corporateSaving = true
        corporateError = ""
        graph.appScope.launch {
            val result = repo.createCorporateAction(body)
            corporateSaving = false
            val error = investWriteError(app, result, R.string.inv_corporate_failed)
            when {
                error == null -> {
                    corporate = null
                    val ticker = eligibleAssets.firstOrNull { it.first == form.assetId }?.second ?: app.getString(R.string.inv_corporate_the_asset)
                    val refreshed = (result as? InboxWrite.Done)?.value?.priceRefreshed == true
                    notice(
                        app.getString(R.string.inv_corporate_saved, ticker, formatDateBR(form.exDate)) +
                            if (refreshed) "" else " " + app.getString(R.string.inv_corporate_no_quote),
                    )
                    ProceedsSync.afterWrite(app, "/api/corporate-actions") { reread() }
                    reread()
                }
                cleared -> Toast.makeText(app, error, Toast.LENGTH_LONG).show()
                else -> corporateError = error
            }
        }
    }

    fun askUndo(action: CorporateActionDto) {
        confirm = ConfirmRequest(
            title = app.getString(R.string.inv_corporate_undo_title, action.label.orEmpty(), action.ticker.orEmpty()),
            message = app.getString(if (action.actionType == "BONUS") R.string.inv_corporate_undo_bonus else R.string.inv_corporate_undo_message),
            confirmLabel = app.getString(R.string.inv_corporate_undo),
        ) {
            eventsError = ""
            graph.appScope.launch {
                val result = repo.deleteCorporateAction(action.id)
                val error = investWriteError(app, result, R.string.inv_corporate_undo_failed)
                when {
                    error == null -> {
                        notice(app.getString(R.string.inv_corporate_undone))
                        ProceedsSync.afterWrite(app, "/api/corporate-actions/${action.id}") { reread() }
                        reread()
                    }
                    cleared -> Toast.makeText(app, error, Toast.LENGTH_LONG).show()
                    else -> eventsError = error
                }
            }
        }
    }

    private fun notice(message: String) {
        if (cleared) Toast.makeText(app, message, Toast.LENGTH_SHORT).show() else _notices.tryEmit(message)
    }

    fun launchFinished(message: String) {
        notice(message)
        reread()
    }

    /** A conta gravada da operacao em edicao fora da lista ativa (para o CashLinkField). */
    fun cashLinkChange(value: PortfolioAccount.CashLink) {
        edit?.let { changeEdit(it.form.copy(cashLink = value)) }
    }

    companion object {
        val APORTES_PERIODS = listOf("6" to "6m", "12" to "12m", "24" to "24m", "60" to "5a")

        fun movementOf(movement: OperationDto) = Operations.Movement(
            id = movement.id,
            assetClass = movement.assetClass,
            quantity = movement.quantity,
            averagePrice = movement.averagePrice,
            currentPrice = movement.currentPrice,
            feeAmount = movement.feeAmount,
            createdAt = movement.createdAt,
            metadata = movement.metadata,
            realizedProfit = movement.realizedProfit,
            realizedFeeAmount = movement.realizedFeeAmount,
            realizedNetProceeds = movement.realizedNetProceeds,
            realizedMetadata = movement.realizedMetadata,
            realizedProfitabilityPercent = movement.realizedProfitabilityPercent,
            assetCategory = movement.assetCategory,
        )
    }
}
