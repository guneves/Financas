package br.financas.app.ui.recorrentes

import android.app.Application
import android.widget.Toast
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import br.financas.app.R
import br.financas.app.core.MoneyInput
import br.financas.app.core.formatDateBR
import br.financas.app.core.getLocalDateString
import br.financas.app.core.moneyInputValue
import br.financas.app.core.parseMoneyInput
import br.financas.app.data.AccountDto
import br.financas.app.data.AppGraph
import br.financas.app.data.CategoryDto
import br.financas.app.data.InboxWrite
import br.financas.app.data.Load
import br.financas.app.data.RecurringDto
import br.financas.app.data.RecurringForecastDto
import br.financas.app.data.RecurringListDto
import br.financas.app.rules.HomeRules
import br.financas.app.rules.Recurring
import br.financas.app.ui.components.ConfirmRequest
import br.financas.app.ui.nav.ShellEvents
import br.financas.app.ui.planejar.ScreenLoad
import br.financas.app.ui.planejar.planWriteError
import br.financas.app.ui.theme.ShellPrefs
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch

/** O formulario "Nova recorrência", como digitado. */
data class RecurringForm(
    val description: String = "",
    val amount: String = "",
    val type: String = "EXPENSE",
    val categoryId: String = "",
    val accountId: String = "",
    val frequency: String = "MONTHLY",
    val intervalCount: String = "1",
    val startDate: String = getLocalDateString(),
    val endDate: String = "",
)

/** "Editar valor e conta": o valor como digitado e a conta escolhida. */
data class RecurringEdit(val id: String, val amount: String, val accountId: String)

/**
 * Recorrentes nativo (09-recorrentes.md): GET /api/recurring e a projecao de 90 dias, tudo do
 * servidor (o calendario nunca e calculado no aparelho). Lancar, criar, editar, pausar e excluir
 * so com o servidor.
 */
class RecorrentesViewModel(application: Application) : AndroidViewModel(application) {

    private val app = application
    private val graph = AppGraph.from(application)
    private val repo = graph.planejamento

    val list = ScreenLoad<RecurringListDto>()
    val forecast = ScreenLoad<RecurringForecastDto>()
    var categories by mutableStateOf<List<CategoryDto>>(emptyList())
        private set
    var accounts by mutableStateOf<List<AccountDto>>(emptyList())
        private set
    var hidden by mutableStateOf(ShellPrefs.valuesHidden(application) ?: false)
        private set
    var actionError by mutableStateOf("")
        private set
    var busy by mutableStateOf(false)
        private set

    var formOpen by mutableStateOf(false)
        private set
    var form by mutableStateOf(RecurringForm())
        private set
    var edit by mutableStateOf<RecurringEdit?>(null)
        private set
    var confirm by mutableStateOf<ConfirmRequest?>(null)
        private set

    private val _notices = MutableSharedFlow<String>(extraBufferCapacity = 8)
    val notices: SharedFlow<String> = _notices.asSharedFlow()

    private var cleared = false

    override fun onCleared() {
        cleared = true
        super.onCleared()
    }

    val items: List<RecurringDto> get() = list.value?.items.orEmpty()

    /** O mesmo do servidor (pending_count do topo): o que venceu e nao foi lancado. */
    val pendingCount: Int get() = list.value?.pendingCount ?: items.sumOf { it.pendingCount }

    fun categoryLabel(category: CategoryDto): String =
        if (category.parentName.isNullOrEmpty()) category.name else "${category.parentName} › ${category.name}"

    fun title(item: RecurringDto): String = item.description?.takeIf { it.isNotEmpty() } ?: item.category.orEmpty()

    /** "Despesa · Moradia · Mensal · próxima em 05/11/2026 · até 31/12/2027". */
    fun detail(item: RecurringDto): String {
        val type = app.getString(if (item.type == "INCOME") R.string.rec_type_income else R.string.rec_type_expense)
        val freq = Recurring.frequencyLabel(item.frequency, item.intervalCount)
        val whenText = when {
            item.status == "PAUSED" && !item.pausedAt.isNullOrEmpty() -> app.getString(R.string.rec_paused_since, formatDateBR(item.pausedAt))
            !item.nextRunDate.isNullOrEmpty() -> app.getString(R.string.rec_next_on, formatDateBR(item.nextRunDate))
            else -> app.getString(R.string.rec_no_next)
        }
        val end = if (item.endDate.isNullOrEmpty()) "" else app.getString(R.string.rec_until, formatDateBR(item.endDate))
        return "$type · ${item.category.orEmpty()} · $freq · $whenText$end"
    }

    // ---- Leituras ----

    fun refreshAll() {
        hidden = ShellPrefs.valuesHidden(app) ?: hidden
        viewModelScope.launch { list.collect(app, repo.recurring(), R.string.rec_load_failed) }
        viewModelScope.launch { forecast.collect(app, repo.forecast(), R.string.rec_load_failed) }
        collectList(graph.categories.categories()) { categories = it }
        collectList(graph.accounts.accounts()) { accounts = it }
    }

    private fun <T> collectList(flow: Flow<Load<List<T>>>, assign: (List<T>) -> Unit) {
        viewModelScope.launch {
            flow.collect { load ->
                when (load) {
                    is Load.Cached -> assign(load.value)
                    is Load.Fresh -> assign(load.value)
                    is Load.Failed -> Unit
                }
            }
        }
    }

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

    // ---- Lancar pendentes ----

    fun run() {
        write(R.string.rec_run_failed, { repo.runRecurring() }) { result ->
            val message = if (result.created > 0) app.getString(R.string.rec_run_done, result.created, formatDateBR(result.through))
            else app.getString(R.string.rec_run_nothing)
            // Uma recorrencia numa conta arquivada nao lanca (o servidor a devolve em blocked).
            val blocked = HomeRules.blockedRecurringMessage(result.blocked.map { it.rule })
            changed(message)
            if (blocked.isNotEmpty()) actionError = blocked
        }
    }

    // ---- Nova recorrencia ----

    fun toggleForm() {
        formOpen = !formOpen
    }

    fun changeForm(next: RecurringForm) {
        form = next
    }

    fun create() {
        val current = form
        val amount = (parseMoneyInput(current.amount) as? MoneyInput.Amount)?.value
        val body = linkedMapOf<String, Any?>(
            "description" to current.description,
            // Vazio ou invalido vai null: o servidor recusa com a mensagem dele ("Valor ...").
            "amount" to amount,
            "type" to current.type,
            "category_id" to current.categoryId,
            "account_id" to current.accountId.ifEmpty { null },
            "frequency" to current.frequency,
            // Number(form.interval_count || 1): vazio e 1, o que nao for inteiro vai null (o servidor recusa).
            "interval_count" to (if (current.intervalCount.isBlank()) 1 else current.intervalCount.trim().toIntOrNull()),
            "start_date" to current.startDate,
            "end_date" to current.endDate.ifEmpty { null },
        )
        write(R.string.rec_create_failed, { repo.createRecurring(body) }) {
            form = RecurringForm()
            formOpen = false
            changed(null)
        }
    }

    // ---- Editar, pausar, excluir ----

    fun startEdit(item: RecurringDto) {
        edit = RecurringEdit(item.id, moneyInputValue(item.amount), item.accountId.orEmpty())
    }

    fun changeEdit(next: RecurringEdit) {
        edit = next
    }

    fun cancelEdit() {
        edit = null
    }

    fun accountOptions(item: RecurringDto): List<Recurring.AccountOption> =
        Recurring.accountOptions(item.accountId, accounts.map { it.id to it.name })

    fun saveEdit(item: RecurringDto) {
        val draft = edit ?: return
        val patch = Recurring.editPatch(item.amount, item.accountId, draft.amount, draft.accountId)
        if (patch.isEmpty()) {
            edit = null
            return
        }
        write(R.string.rec_update_failed, { repo.updateRecurring(item.id, patch) }) {
            edit = null
            changed(null)
        }
    }

    fun toggleActive(item: RecurringDto) {
        write(R.string.rec_update_failed, { repo.updateRecurring(item.id, mapOf("active" to !item.active)) }) { changed(null) }
    }

    fun askDelete(item: RecurringDto) {
        confirm = ConfirmRequest(
            title = app.getString(R.string.rec_delete_title, title(item)),
            message = app.getString(R.string.rec_delete_message),
            confirmLabel = app.getString(R.string.rec_delete_confirm),
        ) {
            write(R.string.rec_delete_failed, { repo.deleteRecurring(item.id) }) { result ->
                changed(
                    if (result.keptTransactions > 0) app.getString(R.string.rec_deleted_kept, result.keptTransactions)
                    else app.getString(R.string.rec_deleted),
                )
            }
        }
    }

    // ---- Comum ----

    private fun <T> write(failure: Int, call: suspend () -> InboxWrite<T>, done: (T) -> Unit) {
        if (busy) return
        busy = true
        actionError = ""
        graph.appScope.launch {
            val result = call()
            busy = false
            val error = planWriteError(app, result, failure)
            when {
                error == null -> done((result as InboxWrite.Done<T>).value)
                cleared -> Toast.makeText(app, error, Toast.LENGTH_LONG).show()
                else -> actionError = error
            }
        }
    }

    private fun changed(message: String?) {
        ShellEvents.emitDataChanged()
        if (message != null) {
            if (cleared) Toast.makeText(app, message, Toast.LENGTH_SHORT).show() else _notices.tryEmit(message)
        }
        if (!cleared) refreshAll()
    }
}
