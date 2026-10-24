package br.financas.app.ui.extrato

import android.app.Application
import android.content.Context
import android.widget.Toast
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import br.financas.app.R
import br.financas.app.core.MoneyInput
import br.financas.app.core.getLocalDateString
import br.financas.app.core.parseMoneyInput
import br.financas.app.data.AccountDto
import br.financas.app.data.ApiException
import br.financas.app.data.AppGraph
import br.financas.app.data.AttachmentOwner
import br.financas.app.data.CategoryDto
import br.financas.app.data.ExportColumnDto
import br.financas.app.data.HomeDto
import br.financas.app.data.InboxWrite
import br.financas.app.data.InvestmentMovementDto
import br.financas.app.data.InvestmentProceedDto
import br.financas.app.data.Load
import br.financas.app.data.StatementTotalsDto
import br.financas.app.data.TransactionDto
import br.financas.app.outbox.OutboxStore
import br.financas.app.rules.EntryOptions
import br.financas.app.rules.ExtratoFilters
import br.financas.app.rules.ExtratoRules
import br.financas.app.rules.InvestmentStatement
import br.financas.app.rules.OutboxItems
import br.financas.app.rules.OutboxPending
import br.financas.app.rules.PendingItem
import br.financas.app.rules.Sharing
import br.financas.app.rules.StatementEntry
import br.financas.app.rules.TransactionEditForm
import br.financas.app.ui.components.ConfirmRequest
import br.financas.app.ui.home.HomeLogic
import br.financas.app.ui.lancamentos.AttachmentsState
import br.financas.app.ui.lancamentos.NativeFiles
import br.financas.app.ui.lancamentos.normalizedShare
import br.financas.app.ui.lancamentos.writeErrorOf
import br.financas.app.ui.nav.NativeScreensPlugin
import br.financas.app.ui.theme.ShellPrefs
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.math.BigDecimal

/**
 * O que o Extrato guarda entre uma abertura e outra no mesmo processo: os filtros (na web moram
 * na URL e voltam com ela) e a vista escolhida por ultimo (a web guarda no localStorage).
 */
object ExtratoMemory {
    var filters: ExtratoFilters = ExtratoFilters()

    private const val PREFS = "financas_native_extrato"
    private const val VIEW = "view"

    fun view(context: Context): String =
        if (prefs(context).getString(VIEW, VIEW_CONTAS) == VIEW_INVESTIMENTOS) VIEW_INVESTIMENTOS else VIEW_CONTAS

    fun saveView(context: Context, view: String) {
        prefs(context).edit().putString(VIEW, view).apply()
    }

    private fun prefs(context: Context) = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    const val VIEW_CONTAS = "contas"
    const val VIEW_INVESTIMENTOS = "investimentos"
}

/** O formato e as colunas da exportacao (o ExportSheet da web). */
data class ExportChoice(val format: String = "xlsx", val columns: Set<String> = emptySet())

/**
 * O Extrato nativo (04-extrato.md), as duas vistas. Contas: GET /api/transactions em paginas de
 * 200 com os totais do servidor (services/transaction_pages.py), os pendentes da fila por cima da
 * primeira pagina sem filtro, o saldo e as projecoes de GET /api/home. Investimentos: as
 * operacoes e os proventos (rules/InvestmentStatement.kt). Editar e excluir so com o servidor.
 */
class ExtratoViewModel(application: Application) : AndroidViewModel(application) {

    private val app = application
    private val graph = AppGraph.from(application)
    private val repo = graph.lancamentos

    var view by mutableStateOf(ExtratoMemory.view(application))
        private set

    var hidden by mutableStateOf(ShellPrefs.valuesHidden(application) ?: false)
        private set

    // ---- Contas ----

    var filters by mutableStateOf(ExtratoMemory.filters)
        private set
    var filtersOpen by mutableStateOf(ExtratoRules.countHiddenFilters(ExtratoMemory.filters) > 0)
        private set

    /** As linhas do servidor ja carregadas (todas as paginas); null antes da primeira. */
    var rows by mutableStateOf<List<TransactionDto>?>(null)
        private set
    var totals by mutableStateOf(StatementTotalsDto())
        private set
    var dayTotals by mutableStateOf<Map<String, BigDecimal>>(emptyMap())
        private set
    var count by mutableStateOf(0)
        private set
    private var nextCursor: String? = null
    val hasMore: Boolean get() = nextCursor != null
    var loadingMore by mutableStateOf(false)
        private set
    /** A busca com estes filtros ainda nao voltou ("Filtrando…"). */
    var filtering by mutableStateOf(false)
        private set

    var home by mutableStateOf<HomeDto?>(null)
        private set
    var pending by mutableStateOf<List<PendingItem>>(emptyList())
        private set
    var accounts by mutableStateOf<List<AccountDto>>(emptyList())
        private set
    var categories by mutableStateOf<List<CategoryDto>>(emptyList())
        private set
    var inboxCount by mutableStateOf(0)
        private set

    var offline by mutableStateOf(false)
        private set
    var cachedAt by mutableStateOf<Long?>(null)
        private set
    var loadError by mutableStateOf("")
        private set
    var actionError by mutableStateOf("")
        private set
    var filterError by mutableStateOf("")
        private set

    var editing by mutableStateOf<TransactionDto?>(null)
        private set
    var editForm by mutableStateOf<TransactionEditForm?>(null)
        private set
    var editError by mutableStateOf("")
        private set
    var saving by mutableStateOf(false)
        private set

    var confirm by mutableStateOf<ConfirmRequest?>(null)
        private set

    val attachments = AttachmentsState(app, repo, viewModelScope, confirm = { confirm = it }, onChanged = ::refreshAll)

    // ---- Exportar ----

    var exportOpen by mutableStateOf(false)
        private set
    var exportColumns by mutableStateOf<List<ExportColumnDto>>(emptyList())
        private set
    var exportChoice by mutableStateOf(ExportChoice())
        private set
    var exporting by mutableStateOf(false)
        private set
    var exportError by mutableStateOf("")
        private set

    // ---- Investimentos ----

    var movements by mutableStateOf<List<InvestmentMovementDto>?>(null)
        private set
    var proceeds by mutableStateOf<List<InvestmentProceedDto>?>(null)
        private set
    var invKind by mutableStateOf(InvestmentStatement.KIND_ALL)
        private set
    var invQuery by mutableStateOf("")
        private set
    var invError by mutableStateOf("")
        private set

    private val _notices = MutableSharedFlow<String>(extraBufferCapacity = 8)
    val notices: SharedFlow<String> = _notices.asSharedFlow()

    private var listJob: Job? = null

    // Sobe a cada leitura nova da primeira pagina: uma pagina seguinte pedida antes dela e descartada.
    private var listGeneration = 0
    private var cleared = false
    private var proceedsSynced = false

    override fun onCleared() {
        cleared = true
        super.onCleared()
    }

    // ---- O que a tela mostra ----

    val filtersActive: Boolean get() = ExtratoRules.hasActiveFilters(filters)

    /** As linhas da lista: os pendentes da fila no topo (so sem filtro, como na web) e as do servidor. */
    val statementRows: List<TransactionDto>
        get() {
            val server = rows.orEmpty()
            if (filtersActive || pending.isEmpty()) return server
            val defaultId = accounts.firstOrNull { it.isDefault }?.id.orEmpty()
            val local = OutboxPending.pendingAsTransactions(pending, defaultId).map { item ->
                TransactionDto(
                    id = item.id, type = item.type, amount = item.amount, date = item.date, description = item.description,
                    category = item.category, accountId = item.accountId, transferAccountId = item.transferAccountId,
                    createdAt = item.createdAt, pending = true, pendingStatus = item.pendingStatus,
                )
            }
            return local + server
        }

    /** O saldo e as projecoes com os pendentes por cima (HomeLogic.view). */
    val header: Triple<BigDecimal, BigDecimal, BigDecimal>?
        get() {
            val data = home ?: return null
            val balance = HomeLogic.view(data, pending).consolidatedBalance
            val projections = data.projections
            val next = projections?.nextMonth ?: data.consolidatedBalance
            val global = projections?.global ?: data.consolidatedBalance
            return Triple(
                balance,
                ExtratoRules.projectionWithPending(next, data.consolidatedBalance, balance),
                ExtratoRules.projectionWithPending(global, data.consolidatedBalance, balance),
            )
        }

    /** Um pendente que nao e cartao nem transferencia mexe no saldo: o saldo e estimativa. */
    val balanceEstimated: Boolean
        get() = pending.any { it.status == OutboxPending.PENDING && it.kind != "CARD" && it.kind != "TRANSFER" }

    fun accountName(id: String?): String = accounts.firstOrNull { it.id == id }?.name ?: "—"

    val activeAccounts: List<AccountDto> get() = accounts.filter { !it.isArchived }

    val categoryOptions get() = EntryOptions.buildCategoryOptions(categories)

    val investmentEntries: List<StatementEntry>
        get() = InvestmentStatement.buildInvestmentStatement(
            movements.orEmpty(), proceeds.orEmpty(), today = getLocalDateString(), kind = invKind, query = invQuery,
        )

    // ---- Leituras ----

    fun refreshAll() {
        hidden = ShellPrefs.valuesHidden(app) ?: hidden
        readPending()
        readList()
        readHome()
        readAccounts()
        readCategories()
        readInboxCount()
        if (view == ExtratoMemory.VIEW_INVESTIMENTOS) readInvestments()
    }

    private fun readList() {
        listJob?.cancel()
        listGeneration += 1
        val params = ExtratoRules.filterParams(filters)
        filtering = true
        listJob = viewModelScope.launch {
            // A busca espera 250 ms depois da ultima tecla (o useDebouncedValue da web).
            if (rows != null) delay(DEBOUNCE_MS)
            repo.firstPage(params).collect { load ->
                when (load) {
                    is Load.Cached -> if (rows == null || filtering) {
                        applyPage(load.value.items, load.value, replace = true)
                        cachedAt = load.storedAt
                    }
                    is Load.Fresh -> {
                        applyPage(load.value.items, load.value, replace = true)
                        cachedAt = null
                        offline = false
                        loadError = ""
                        filterError = ""
                        filtering = false
                    }
                    is Load.Failed -> {
                        filtering = false
                        listFailed(load.error, hadCopy = load.cached != null)
                    }
                }
            }
        }
    }

    private fun applyPage(items: List<TransactionDto>, page: br.financas.app.data.TransactionPageDto, replace: Boolean) {
        rows = if (replace) {
            items
        } else {
            // Nunca a mesma linha duas vezes (a lista usa o id como chave).
            val seen = rows.orEmpty().map { it.id }.toHashSet()
            rows.orEmpty() + items.filter { it.id !in seen }
        }
        nextCursor = page.nextCursor
        count = page.count
        if (replace) {
            totals = page.totals
            dayTotals = page.dayTotals
        } else {
            dayTotals = dayTotals + page.dayTotals
        }
    }

    private fun listFailed(error: ApiException, hadCopy: Boolean) {
        if (rows == null) rows = emptyList()
        when (error) {
            is ApiException.Network, is ApiException.BadResponse -> {
                offline = true
                if (!hadCopy) loadError = app.getString(R.string.lanc_offline_no_copy)
            }
            is ApiException.Unauthorized -> loadError = error.serverMessage ?: app.getString(R.string.data_session_expired)
            is ApiException.Http -> if (error.status in 300..399) {
                offline = true
            } else if (filtersActive) {
                filterError = error.serverMessage ?: app.getString(R.string.extrato_filter_failed)
            } else {
                loadError = error.serverMessage ?: app.getString(R.string.lanc_load_failed)
            }
        }
    }

    /** "Carregar mais" (e o fim da rolagem): a pagina seguinte, so com rede. */
    fun loadMore() {
        val cursor = nextCursor ?: return
        if (loadingMore) return
        loadingMore = true
        val params = ExtratoRules.filterParams(filters)
        val generation = listGeneration
        viewModelScope.launch {
            try {
                val page = repo.nextPage(params, cursor)
                if (generation == listGeneration) applyPage(page.items, page, replace = false)
            } catch (error: ApiException) {
                actionError = app.getString(R.string.extrato_more_failed)
            } finally {
                loadingMore = false
            }
        }
    }

    private fun readHome() {
        viewModelScope.launch {
            graph.home.home().collect { load ->
                when (load) {
                    is Load.Cached -> if (home == null) home = load.value
                    is Load.Fresh -> home = load.value
                    is Load.Failed -> if (home == null) home = load.cached?.value
                }
            }
        }
    }

    private fun readAccounts() {
        viewModelScope.launch {
            graph.accounts.accounts(includeArchived = true).collect { load ->
                when (load) {
                    is Load.Cached -> if (accounts.isEmpty()) accounts = load.value
                    is Load.Fresh -> accounts = load.value
                    is Load.Failed -> Unit
                }
            }
        }
    }

    private fun readCategories() {
        viewModelScope.launch {
            graph.categories.categories().collect { load ->
                when (load) {
                    is Load.Cached -> if (categories.isEmpty()) categories = load.value
                    is Load.Fresh -> categories = load.value
                    is Load.Failed -> Unit
                }
            }
        }
    }

    private fun readInboxCount() {
        viewModelScope.launch {
            graph.inbox.count().collect { load ->
                when (load) {
                    is Load.Cached -> Unit
                    is Load.Fresh -> inboxCount = load.value.pendingCount ?: 0
                    is Load.Failed -> if (load.error is ApiException.Network) inboxCount = 0
                }
            }
        }
    }

    fun readPending() {
        viewModelScope.launch {
            pending = withContext(Dispatchers.IO) {
                val texts = OutboxStore.get(app).all().map { it.toString() }
                OutboxItems.forUser(texts, graph.sessionUserId())
            }
        }
    }

    private fun readInvestments() {
        if (!proceedsSynced) {
            // O useProceedsSync() da web: calcula os proventos novos; sem rede, nada.
            proceedsSynced = true
            viewModelScope.launch {
                if (repo.syncProceeds() is InboxWrite.Done) readProceeds()
            }
        }
        viewModelScope.launch {
            repo.investments().collect { load ->
                when (load) {
                    is Load.Cached -> if (movements == null) movements = load.value
                    is Load.Fresh -> {
                        movements = load.value
                        invError = ""
                    }
                    is Load.Failed -> {
                        if (movements == null) movements = load.cached?.value ?: emptyList()
                        if (load.error !is ApiException.Network) invError = app.getString(R.string.extrato_inv_load_failed)
                    }
                }
            }
        }
        readProceeds()
    }

    private fun readProceeds() {
        viewModelScope.launch {
            repo.proceeds().collect { load ->
                when (load) {
                    is Load.Cached -> if (proceeds == null) proceeds = load.value
                    is Load.Fresh -> proceeds = load.value
                    is Load.Failed -> if (proceeds == null) proceeds = load.cached?.value ?: emptyList()
                }
            }
        }
    }

    // ---- Vista, filtros, olho ----

    fun chooseView(next: String) {
        if (next == view) return
        view = next
        ExtratoMemory.saveView(app, next)
        // Trocar de extrato limpa os filtros do outro (como a web).
        changeFilters(ExtratoFilters())
        invQuery = ""
        invKind = InvestmentStatement.KIND_ALL
        if (next == ExtratoMemory.VIEW_INVESTIMENTOS) readInvestments()
    }

    /** A vista pedida por quem abriu (o ?ver= da web); null mantem a ultima. */
    fun requestView(requested: String?) {
        if (requested == ExtratoMemory.VIEW_CONTAS || requested == ExtratoMemory.VIEW_INVESTIMENTOS) {
            view = requested
            ExtratoMemory.saveView(app, requested)
        }
    }

    fun changeFilters(next: ExtratoFilters) {
        if (next == filters) return
        val before = ExtratoRules.filterParams(filters)
        filters = next
        ExtratoMemory.filters = next
        if (ExtratoRules.filterParams(next) != before) readList()
    }

    fun toggleFilters() {
        filtersOpen = !filtersOpen
    }

    fun clearFilters() = changeFilters(ExtratoFilters())

    fun toggleHidden() {
        hidden = !hidden
        ShellPrefs.saveValuesHidden(app, hidden)
    }

    fun dismissActionError() {
        actionError = ""
    }

    fun dismissConfirm() {
        confirm = null
    }

    fun changeInvKind(kind: String) {
        invKind = kind
    }

    fun changeInvQuery(query: String) {
        invQuery = query
    }

    // ---- Editar e excluir ----

    fun startEditing(row: TransactionDto) {
        editing = row
        editForm = ExtratoRules.transactionEditForm(row)
        editError = ""
    }

    fun changeEditForm(form: TransactionEditForm) {
        editForm = form
    }

    fun cancelEditing() {
        if (!saving) {
            editing = null
            editForm = null
        }
    }

    fun saveEdit() {
        val row = editing ?: return
        val form = editForm ?: return
        val amount = (parseMoneyInput(form.amount) as? MoneyInput.Amount)?.value
        if (amount == null || amount.signum() <= 0) {
            editError = app.getString(R.string.extrato_edit_invalid)
            return
        }
        val sharing = ExtratoRules.canShare(row)
        val share = normalizedShare(form.share)
        val shareError = if (sharing) Sharing.shareFormError(share, amount) else ""
        if (shareError.isNotEmpty()) {
            editError = shareError
            return
        }
        saving = true
        editError = ""
        val payload = ExtratoRules.transactionEditPayload(row, form.copy(share = share), amount, sharing)
        graph.appScope.launch {
            val result = repo.updateTransaction(row.id, payload)
            saving = false
            val error = writeErrorOf(app, result, R.string.extrato_edit_failed)
            if (error == null) {
                editing = null
                editForm = null
                changed(null)
            } else if (cleared) {
                Toast.makeText(app, error, Toast.LENGTH_LONG).show()
            } else {
                editError = error
            }
        }
    }

    fun askDelete(row: TransactionDto) {
        confirm = ConfirmRequest(
            title = app.getString(R.string.extrato_delete_title),
            message = app.getString(R.string.extrato_delete_message),
            confirmLabel = app.getString(R.string.extrato_delete_confirm),
        ) { write(R.string.extrato_delete_failed, null) { repo.deleteTransaction(row.id) } }
    }

    fun askUndoPayment(row: TransactionDto) {
        confirm = ConfirmRequest(
            title = app.getString(R.string.extrato_undo_title, ExtratoRules.title(row)),
            message = app.getString(R.string.extrato_undo_message),
            confirmLabel = app.getString(R.string.extrato_undo),
        ) { write(R.string.extrato_undo_failed, app.getString(R.string.extrato_undo_done)) { repo.undoPayment(row.id) } }
    }

    fun askDeleteInvestmentCash(row: TransactionDto) {
        val movementId = row.sourceId ?: return
        confirm = ConfirmRequest(
            title = app.getString(R.string.extrato_delete_operation_title, ExtratoRules.title(row)),
            message = app.getString(R.string.extrato_delete_operation_message),
            confirmLabel = app.getString(R.string.extrato_delete_operation),
        ) { write(R.string.extrato_operation_failed, app.getString(R.string.extrato_operation_deleted)) { repo.deleteInvestment(movementId) } }
    }

    fun askDeleteMovement(entry: StatementEntry) {
        val movementId = entry.movementId ?: return
        confirm = ConfirmRequest(
            title = app.getString(R.string.extrato_inv_delete_title, entry.kind.lowercase(), entry.title),
            message = app.getString(if (entry.inStatement) R.string.extrato_inv_delete_linked else R.string.extrato_inv_delete_alone),
            confirmLabel = app.getString(R.string.extrato_inv_delete_confirm),
        ) {
            write(R.string.extrato_operation_failed, app.getString(R.string.extrato_operation_deleted)) {
                repo.deleteInvestment(movementId).also { if (it is InboxWrite.Done) movements = movements?.filter { m -> m.id != movementId } }
            }
        }
    }

    private fun write(failure: Int, success: String?, action: suspend () -> InboxWrite<Unit>) {
        actionError = ""
        graph.appScope.launch {
            val error = writeErrorOf(app, action(), failure)
            if (error == null) {
                changed(success)
            } else if (cleared) {
                Toast.makeText(app, error, Toast.LENGTH_LONG).show()
            } else {
                actionError = error
            }
        }
    }

    private fun changed(message: String?) {
        // A WebView (Inicio, Cartoes da web) atualiza; o toast fica aqui se a tela esta aberta.
        NativeScreensPlugin.emitDataChanged()
        if (message != null) {
            if (cleared) Toast.makeText(app, message, Toast.LENGTH_SHORT).show() else _notices.tryEmit(message)
        }
        if (!cleared) refreshAll()
    }

    // ---- Comprovantes ----

    fun openAttachments(row: TransactionDto) {
        if (row.pending) return
        attachments.open(AttachmentOwner.transaction(row.id), ExtratoRules.attachmentDescription(row))
    }

    // ---- Exportar ----

    fun openExport() {
        exportOpen = true
        exportError = ""
        exportChoice = ExportChoiceStore.load(app)
        viewModelScope.launch {
            repo.exportColumns().collect { load ->
                when (load) {
                    is Load.Cached -> if (exportColumns.isEmpty()) exportColumns = load.value.transactions
                    is Load.Fresh -> exportColumns = load.value.transactions
                    is Load.Failed -> if (exportColumns.isEmpty()) {
                        exportColumns = load.cached?.value?.transactions.orEmpty()
                        if (exportColumns.isEmpty()) exportError = app.getString(R.string.extrato_export_columns_failed)
                    }
                }
                // Sem escolha guardada, todas as colunas.
                if (exportChoice.columns.isEmpty()) exportChoice = exportChoice.copy(columns = exportColumns.map { it.key }.toSet())
            }
        }
    }

    fun closeExport() {
        if (!exporting) exportOpen = false
    }

    fun changeExport(choice: ExportChoice) {
        exportChoice = choice
    }

    /** Baixa com os filtros da tela e entrega a folha de compartilhar do Android. */
    fun export() {
        val choice = exportChoice
        if (choice.columns.isEmpty()) {
            exportError = app.getString(R.string.extrato_export_pick_one)
            return
        }
        val all = exportColumns.map { it.key }
        // Todas as colunas: o parametro nem vai (como a web).
        val columns = if (choice.columns.containsAll(all)) null else all.filter { it in choice.columns }
        exporting = true
        exportError = ""
        ExportChoiceStore.save(app, choice)
        viewModelScope.launch {
            when (val result = repo.export(ExtratoRules.filterParams(filters), choice.format, columns)) {
                is InboxWrite.Done -> {
                    val name = result.value.fileName ?: "extrato-${getLocalDateString()}.${choice.format}"
                    val mime = result.value.contentType?.substringBefore(';') ?: NativeFiles.mimeOf(name)
                    val uri = NativeFiles.stage(app, result.value.bytes, name)
                    exportOpen = false
                    NativeFiles.share(app, uri, mime, name)
                }
                else -> exportError = writeErrorOf(app, result, R.string.extrato_export_failed).orEmpty()
            }
            exporting = false
        }
    }

    companion object {
        const val DEBOUNCE_MS = 250L
    }
}

/** O formato e as colunas lembrados por tela (o financeMVP:export:transactions da web). */
object ExportChoiceStore {
    private const val PREFS = "financas_native_export"

    fun load(context: Context): ExportChoice {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val format = if (prefs.getString("format", "xlsx") == "csv") "csv" else "xlsx"
        return ExportChoice(format, prefs.getStringSet("columns", emptySet()).orEmpty().toSet())
    }

    fun save(context: Context, choice: ExportChoice) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString("format", choice.format)
            .putStringSet("columns", choice.columns)
            .apply()
    }
}
