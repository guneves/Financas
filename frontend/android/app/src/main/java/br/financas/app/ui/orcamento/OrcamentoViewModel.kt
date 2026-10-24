package br.financas.app.ui.orcamento

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
import br.financas.app.core.monthKey
import br.financas.app.core.monthLabel
import br.financas.app.core.moneyInputValue
import br.financas.app.core.parseMoneyInput
import br.financas.app.core.shiftMonth
import br.financas.app.data.AppGraph
import br.financas.app.data.PlanBudgetDto
import br.financas.app.data.BudgetLinesDto
import br.financas.app.data.CategoryDto
import br.financas.app.data.InboxWrite
import br.financas.app.data.MonthlyPlanDto
import br.financas.app.data.PlanFlagDto
import br.financas.app.data.PlanRowDto
import br.financas.app.rules.AttentionRules
import br.financas.app.rules.LivePlanTotals
import br.financas.app.rules.MonthlyPlan
import br.financas.app.ui.components.ConfirmRequest
import br.financas.app.ui.home.AttentionDismissals
import br.financas.app.ui.nav.NativeScreensPlugin
import br.financas.app.ui.planejar.ScreenLoad
import br.financas.app.ui.planejar.planWriteError
import br.financas.app.ui.theme.ShellPrefs
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch
import java.math.BigDecimal

/**
 * Os alertas do plano dispensados neste aparelho (lib/planFlags.js), pela chave
 * MonthlyPlan.planFlagKey. A lista nativa e separada da da WebView, como as do Inicio.
 */
class PlanFlagDismissals(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun load(): List<String> = AttentionDismissals.decode(prefs.getString(KEY, null))

    fun add(current: List<String>, key: String): List<String> {
        val next = AttentionRules.addDismissed(current, listOf(key))
        prefs.edit().putString(KEY, AttentionDismissals.encode(next)).apply()
        return next
    }

    private companion object {
        const val PREFS = "financas_plan_flags"
        const val KEY = "dismissed"
    }
}

/** O sheet "Plano do mês": a renda como digitada e os dois % (null = em branco). */
data class PlanForm(val income: String, val invest: BigDecimal?, val spend: BigDecimal?)

/** O formulario "Adicionar categoria ao mês" (fica aberto depois de salvar). */
data class BudgetForm(val categoryId: String = "", val percent: BigDecimal = BigDecimal.ZERO, val note: String = "", val rollover: Boolean = false)

/**
 * Orcamento nativo (08-orcamento.md): GET /api/monthly-plan do mes mostrado (renda, Investir,
 * Gastar, Saldo do plano, Disponivel por dia, categorias e alertas, tudo do servidor). Aqui so a
 * previa dos % enquanto se mexe (rules/MonthlyPlan.kt); toda escrita so com o servidor.
 */
class OrcamentoViewModel(application: Application) : AndroidViewModel(application) {

    private val app = application
    private val graph = AppGraph.from(application)
    private val repo = graph.planejamento
    private val dismissals = PlanFlagDismissals(application)

    var month by mutableStateOf(monthKey())
        private set
    val plan = ScreenLoad<MonthlyPlanDto>()
    var categories by mutableStateOf<List<CategoryDto>>(emptyList())
        private set
    var hidden by mutableStateOf(ShellPrefs.valuesHidden(application) ?: false)
        private set
    var dismissed by mutableStateOf(dismissals.load())
        private set
    var actionError by mutableStateOf("")
        private set
    var busy by mutableStateOf(false)
        private set

    var sheet by mutableStateOf<PlanForm?>(null)
        private set
    var sheetBusy by mutableStateOf(false)
        private set
    var sheetError by mutableStateOf("")
        private set

    var addOpen by mutableStateOf(false)
        private set
    var addForm by mutableStateOf(BudgetForm())
        private set

    var editingId by mutableStateOf("")
        private set
    var editValue by mutableStateOf(BigDecimal.ZERO)
        private set

    var openLines by mutableStateOf<Set<String>>(emptySet())
        private set
    var lines by mutableStateOf<Map<String, ScreenLoad<BudgetLinesDto>>>(emptyMap())
        private set

    var confirm by mutableStateOf<ConfirmRequest?>(null)
        private set

    private val _notices = MutableSharedFlow<String>(extraBufferCapacity = 8)
    val notices: SharedFlow<String> = _notices.asSharedFlow()

    private var planJob: Job? = null
    private var cleared = false

    override fun onCleared() {
        cleared = true
        super.onCleared()
    }

    // ---- O que a tela mostra ----

    /** O plano do mes mostrado; uma copia de antes de 038 (sem `invest`) nao serve. */
    val data: MonthlyPlanDto?
        get() = plan.value?.takeIf { it.invest != null && (it.month == month || !plan.loaded) }
    val row: PlanRowDto? get() = data?.plan
    val hasFigures: Boolean get() = row != null && row?.needsIncome == false
    val items: List<PlanBudgetDto> get() = data?.categories?.items.orEmpty()
    val spendAmount: BigDecimal? get() = data?.spend?.amount
    val assignedPercent: BigDecimal? get() = data?.categories?.totals?.assignedPercent

    /** Ativas e sem orcamento neste mes, "Pai › Filho". */
    val availableCategories: List<CategoryDto>
        get() {
            val budgeted = items.mapNotNull { it.categoryId }.toSet()
            return categories.filter { !it.isArchived && it.id !in budgeted }
        }

    val newCategoryRoom: BigDecimal get() = MonthlyPlan.percentRoom(assignedPercent)

    /** Um mes convertido acima de 100% pode baixar a categoria, nao subir. */
    fun editRoom(item: PlanBudgetDto): BigDecimal {
        val own = item.plannedPercent ?: BigDecimal.ZERO
        return own.max(MonthlyPlan.percentRoom((assignedPercent ?: BigDecimal.ZERO).subtract(own)))
    }

    val sortedFlags: List<PlanFlagDto> get() = MonthlyPlan.sortFlags(data?.flags)

    /** Os alertas menos os dispensados neste aparelho; a barra do Gastar le todos. */
    val shownFlags: List<PlanFlagDto> get() = MonthlyPlan.visibleFlags(sortedFlags, month, dismissed)

    fun categoryLabel(category: CategoryDto): String =
        if (category.parentName.isNullOrEmpty()) category.name else "${category.parentName} › ${category.name}"

    fun itemLabel(item: PlanBudgetDto): String =
        if (item.parentName.isNullOrEmpty()) item.categoryName.orEmpty() else "${item.parentName} › ${item.categoryName.orEmpty()}"

    // ---- Leituras ----

    fun refreshAll() {
        hidden = ShellPrefs.valuesHidden(app) ?: hidden
        readPlan()
        viewModelScope.launch {
            graph.categories.categories(includeArchived = true).collect { load ->
                when (load) {
                    is br.financas.app.data.Load.Cached -> if (categories.isEmpty()) categories = load.value
                    is br.financas.app.data.Load.Fresh -> categories = load.value
                    is br.financas.app.data.Load.Failed -> Unit
                }
            }
        }
        openLines.forEach(::readLines)
    }

    private fun readPlan() {
        planJob?.cancel()
        val shown = month
        // O mes de antes fica na tela ate o novo chegar (keepPreviousData).
        planJob = viewModelScope.launch {
            plan.collect(app, repo.monthlyPlan(shown), R.string.orc_load_failed) { it.invest != null && it.month.ifEmpty { shown } == shown }
        }
    }

    fun shift(offset: Int) {
        month = shiftMonth(month, offset)
        plan.loaded = false
        editingId = ""
        openLines = emptySet()
        lines = emptyMap()
        readPlan()
    }

    fun toggleHidden() {
        hidden = !hidden
        ShellPrefs.saveValuesHidden(app, hidden)
    }

    fun dismissFlag(flag: PlanFlagDto) {
        dismissed = dismissals.add(dismissed, MonthlyPlan.planFlagKey(flag, month))
    }

    fun dismissActionError() {
        actionError = ""
    }

    fun dismissConfirm() {
        confirm = null
    }

    // ---- O sheet "Plano do mês" ----

    fun openSheet() {
        val current = row
        sheet = when {
            current == null -> PlanForm("", BigDecimal.ZERO, BigDecimal.ZERO)
            // Plano antigo: os % ficam em branco para o servidor converter os reais de antes.
            current.needsIncome -> PlanForm(moneyInputValue(current.incomeAmount), null, null)
            else -> PlanForm(moneyInputValue(current.incomeAmount), current.investPercent, current.spendPercent)
        }
        sheetError = ""
    }

    fun changeSheet(form: PlanForm) {
        sheet = form
    }

    fun closeSheet() {
        if (!sheetBusy) sheet = null
    }

    val needsIncome: Boolean get() = row?.needsIncome == true

    fun totals(form: PlanForm): LivePlanTotals {
        val legacy = row?.legacy
        return MonthlyPlan.livePlanTotals(
            income = parseMoneyInput(form.income),
            invest = form.invest?.let { MoneyInput.Amount(it) } ?: MoneyInput.Empty,
            spend = form.spend?.let { MoneyInput.Amount(it) } ?: MoneyInput.Empty,
            legacyInvest = legacy?.investAmount,
            legacySpend = legacy?.spendAmount,
            hasLegacy = needsIncome && legacy != null,
        )
    }

    fun savePlan() {
        val form = sheet ?: return
        if (sheetBusy) return
        val totals = totals(form)
        if (totals.blocked != null) {
            sheetError = totals.blocked
            return
        }
        val income = (parseMoneyInput(form.income) as? MoneyInput.Amount)?.value ?: return
        val shown = month
        val body: Map<String, Any?> = if (totals.convert) {
            linkedMapOf("month" to shown, "income_amount" to income)
        } else {
            linkedMapOf("month" to shown, "income_amount" to income, "invest_percent" to form.invest, "spend_percent" to form.spend)
        }
        sheetBusy = true
        sheetError = ""
        graph.appScope.launch {
            val result = repo.savePlan(body)
            sheetBusy = false
            val error = planWriteError(app, result, R.string.orc_plan_save_failed)
            if (error == null) {
                sheet = null
                changed(app.getString(R.string.orc_plan_saved, monthLabel(shown)))
            } else {
                failed(error) { sheetError = it }
            }
        }
    }

    fun askRemovePlan() {
        val shown = month
        confirm = ConfirmRequest(
            title = app.getString(R.string.orc_plan_remove_title, monthLabel(shown)),
            message = app.getString(R.string.orc_plan_remove_message),
            confirmLabel = app.getString(R.string.orc_remove),
        ) {
            sheetBusy = true
            graph.appScope.launch {
                val result = repo.removePlan(shown)
                sheetBusy = false
                val error = planWriteError(app, result, R.string.orc_plan_remove_failed)
                if (error == null) {
                    sheet = null
                    changed(app.getString(R.string.orc_plan_removed))
                } else {
                    failed(error) { sheetError = it }
                }
            }
        }
    }

    // ---- Categorias do mes ----

    fun toggleAdd() {
        addOpen = !addOpen
    }

    fun changeAdd(form: BudgetForm) {
        addForm = form
    }

    fun createBudget() {
        val form = addForm
        if (busy || form.categoryId.isEmpty()) return
        val body = linkedMapOf<String, Any?>(
            "category_id" to form.categoryId,
            "month" to month,
            "planned_percent" to form.percent,
            "rollover" to form.rollover,
        )
        if (form.note.isNotEmpty()) body["note"] = form.note
        write(R.string.orc_budget_create_failed, { repo.createBudget(body) }) {
            // O formulario fica aberto: montar o mes costuma ser varias categorias seguidas.
            addForm = BudgetForm()
            changed(null)
        }
    }

    fun startEdit(item: PlanBudgetDto) {
        editingId = item.id
        editValue = item.plannedPercent ?: BigDecimal.ZERO
    }

    fun changeEdit(value: BigDecimal) {
        editValue = value
    }

    fun cancelEdit() {
        editingId = ""
    }

    fun saveEdit(item: PlanBudgetDto) {
        val shown = month
        val value = editValue
        write(R.string.orc_budget_update_failed, { repo.updateBudget(item.id, shown, mapOf("planned_percent" to value)) }) {
            editingId = ""
            changed(null)
        }
    }

    fun toggleRollover(item: PlanBudgetDto) {
        val shown = month
        write(R.string.orc_budget_update_failed, { repo.updateBudget(item.id, shown, mapOf("rollover" to !item.rollover)) }) { changed(null) }
    }

    fun askRemoveBudget(item: PlanBudgetDto) {
        val shown = month
        confirm = ConfirmRequest(
            title = app.getString(R.string.orc_budget_remove_title, item.categoryName.orEmpty()),
            message = app.getString(R.string.orc_budget_remove_message, monthLabel(shown)),
            confirmLabel = app.getString(R.string.orc_remove),
        ) {
            write(R.string.orc_budget_remove_failed, { repo.deleteBudget(item.id, shown) }) { changed(null) }
        }
    }

    fun copyPrevious() {
        val shown = month
        write(R.string.orc_copy_failed, { repo.copyBudgets(shown) }) { result ->
            changed(null)
            if (result.created == 0 && result.skipped == 0) {
                actionError = app.getString(R.string.orc_copy_nothing, monthLabel(shiftMonth(shown, -1)))
            }
        }
    }

    // ---- Lancamentos de uma categoria ----

    fun toggleLines(item: PlanBudgetDto) {
        if (item.id in openLines) {
            openLines = openLines - item.id
        } else {
            openLines = openLines + item.id
            readLines(item.id)
        }
    }

    private fun readLines(budgetId: String) {
        val load = lines[budgetId] ?: ScreenLoad<BudgetLinesDto>().also { lines = lines + (budgetId to it) }
        val shown = month
        viewModelScope.launch { load.collect(app, repo.budgetLines(budgetId, shown), R.string.orc_lines_failed) }
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
            if (error == null) done((result as InboxWrite.Done<T>).value) else failed(error) { actionError = it }
        }
    }

    private fun failed(error: String, show: (String) -> Unit) {
        if (cleared) Toast.makeText(app, error, Toast.LENGTH_LONG).show() else show(error)
    }

    private fun changed(message: String?) {
        NativeScreensPlugin.emitDataChanged()
        if (message != null) {
            if (cleared) Toast.makeText(app, message, Toast.LENGTH_SHORT).show() else _notices.tryEmit(message)
        }
        if (!cleared) refreshAll()
    }
}
