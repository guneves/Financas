package br.financas.app.ui.metas

import android.app.Application
import android.widget.Toast
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import br.financas.app.R
import br.financas.app.core.moneyInputValue
import br.financas.app.data.AppGraph
import br.financas.app.data.GoalDto
import br.financas.app.data.InboxWrite
import br.financas.app.rules.Goals
import br.financas.app.ui.components.ConfirmRequest
import br.financas.app.ui.nav.NativeScreensPlugin
import br.financas.app.ui.planejar.ScreenLoad
import br.financas.app.ui.planejar.planWriteError
import br.financas.app.ui.theme.ShellPrefs
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch

/** O sheet aberto: a meta editada (null = nova) e o formulario. */
data class GoalSheet(val goal: GoalDto?, val form: Goals.GoalForm)

/**
 * Metas nativo (10-metas.md): GET /api/goals, tudo calculado no servidor a cada leitura (atual,
 * falta, previsao, aporte necessario). A copia guardada abre na hora enquanto o servidor monta a
 * carteira. Criar, editar e remover so com o servidor.
 */
class MetasViewModel(application: Application) : AndroidViewModel(application) {

    private val app = application
    private val graph = AppGraph.from(application)
    private val repo = graph.planejamento

    val goals = ScreenLoad<List<GoalDto>>()
    var hidden by mutableStateOf(ShellPrefs.valuesHidden(application) ?: false)
        private set
    var actionError by mutableStateOf("")
        private set
    var sheet by mutableStateOf<GoalSheet?>(null)
        private set
    var sheetBusy by mutableStateOf(false)
        private set
    var sheetError by mutableStateOf("")
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

    fun refreshAll() {
        hidden = ShellPrefs.valuesHidden(app) ?: hidden
        viewModelScope.launch { goals.collect(app, repo.goals(), R.string.metas_load_failed) }
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

    // ---- O sheet ----

    fun openNew() {
        sheet = GoalSheet(null, Goals.GoalForm())
        sheetError = ""
    }

    /** formFromGoal(): cada abertura parte da meta gravada, com virgula (o teclado do celular). */
    fun openEdit(goal: GoalDto) {
        sheet = GoalSheet(
            goal,
            Goals.GoalForm(
                name = goal.name,
                kind = goal.kind,
                assetClass = goal.assetClass ?: "STOCKS",
                targetAmount = moneyInputValue(goal.targetAmount),
                monthlyContribution = goal.monthlyContribution?.takeIf { it.signum() != 0 }?.let { moneyInputValue(it) }.orEmpty(),
                annualReturnPercent = moneyInputValue(goal.annualReturnPercent),
                targetDate = goal.targetDate.orEmpty(),
            ),
        )
        sheetError = ""
    }

    fun changeForm(form: Goals.GoalForm) {
        sheet = sheet?.copy(form = form)
    }

    fun closeSheet() {
        if (!sheetBusy) sheet = null
    }

    fun save() {
        val current = sheet ?: return
        if (sheetBusy) return
        val body = Goals.payload(current.form)
        sheetBusy = true
        sheetError = ""
        graph.appScope.launch {
            val goal = current.goal
            val result = if (goal == null) repo.createGoal(body) else repo.updateGoal(goal.id, body)
            sheetBusy = false
            val error = planWriteError(app, result, R.string.metas_save_failed)
            when {
                error == null -> {
                    sheet = null
                    changed(app.getString(if (goal == null) R.string.metas_created else R.string.metas_updated))
                }
                cleared -> Toast.makeText(app, error, Toast.LENGTH_LONG).show()
                else -> sheetError = error
            }
        }
    }

    fun askRemove(goal: GoalDto) {
        confirm = ConfirmRequest(
            title = app.getString(R.string.metas_remove_title, goal.name),
            message = app.getString(R.string.metas_remove_message),
            confirmLabel = app.getString(R.string.orc_remove),
        ) {
            actionError = ""
            graph.appScope.launch {
                val result: InboxWrite<Unit> = repo.deleteGoal(goal.id)
                val error = planWriteError(app, result, R.string.metas_remove_failed)
                when {
                    error == null -> changed(app.getString(R.string.metas_removed))
                    cleared -> Toast.makeText(app, error, Toast.LENGTH_LONG).show()
                    else -> actionError = error
                }
            }
        }
    }

    private fun changed(message: String) {
        // Os alertas de meta do Orcamento dependem das metas: a WebView rele tudo.
        NativeScreensPlugin.emitDataChanged()
        if (cleared) Toast.makeText(app, message, Toast.LENGTH_SHORT).show() else _notices.tryEmit(message)
        if (!cleared) refreshAll()
    }
}
