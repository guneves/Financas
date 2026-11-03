package br.financas.app.ui.areceber

import android.app.Application
import android.widget.Toast
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import br.financas.app.R
import br.financas.app.data.ApiException
import br.financas.app.data.AppGraph
import br.financas.app.data.IncomeChoiceDto
import br.financas.app.data.Load
import br.financas.app.data.ReceivableDto
import br.financas.app.rules.Receivables
import br.financas.app.ui.nav.ShellEvents
import br.financas.app.ui.planejar.ScreenLoad
import br.financas.app.ui.planejar.planWriteError
import br.financas.app.ui.theme.ShellPrefs
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch

/**
 * A receber nativo (06-a-receber.md): GET /api/receivables (pendentes) ou ?include_settled=1
 * (todos), por pessoa. "Pago" so marca share_settled_at: nenhum saldo muda, e nada vai para a fila.
 * "Pago" pergunta com que entrada (052, o PaidBySheet da web): a parte dos outros deixa de ser
 * receita nela. Num item pago, tocar troca a entrada; o desfazer volta para pendente.
 */
class AReceberViewModel(application: Application) : AndroidViewModel(application) {

    private val app = application
    private val graph = AppGraph.from(application)
    private val repo = graph.planejamento

    var all by mutableStateOf(false)
        private set
    val list = ScreenLoad<List<ReceivableDto>>()
    var hidden by mutableStateOf(ShellPrefs.valuesHidden(application) ?: false)
        private set
    var actionError by mutableStateOf("")
        private set

    /** O botao que esta girando: item:<id> ou person:<nome>. */
    var savingKey by mutableStateOf("")
        private set

    private val _notices = MutableSharedFlow<String>(extraBufferCapacity = 8)
    val notices: SharedFlow<String> = _notices.asSharedFlow()

    private var readJob: Job? = null
    private var cleared = false

    override fun onCleared() {
        cleared = true
        super.onCleared()
    }

    val view: Receivables.View get() = Receivables.view(list.value.orEmpty(), all)

    fun refreshAll() {
        hidden = ShellPrefs.valuesHidden(app) ?: hidden
        read()
    }

    private fun read() {
        readJob?.cancel()
        val includeSettled = all
        readJob = viewModelScope.launch { list.collect(app, repo.receivables(includeSettled), R.string.areceber_load_failed) }
    }

    fun chooseView(showAll: Boolean) {
        if (showAll == all) return
        all = showAll
        list.loaded = false
        read()
    }

    fun toggleHidden() {
        hidden = !hidden
        ShellPrefs.saveValuesHidden(app, hidden)
    }

    fun dismissActionError() {
        actionError = ""
    }

    // ---- Com que entrada pagou ----

    /** Os itens no sheet "Com que entrada pagou?"; null = fechado. */
    var paying by mutableStateOf<List<ReceivableDto>?>(null)
        private set

    /** As entradas do sheet; null = carregando. */
    var choices by mutableStateOf<List<IncomeChoiceDto>?>(null)
        private set

    /** O id escolhido; "" = nenhuma (abate no mes marcado). */
    var choice by mutableStateOf("")
        private set
    var payError by mutableStateOf("")
        private set
    private var chosenByOwner = false
    private var payJob: Job? = null

    fun openPay(items: List<ReceivableDto>) {
        if (items.isEmpty() || savingKey.isNotEmpty()) return
        paying = items
        choices = null
        choice = ""
        payError = ""
        chosenByOwner = false
        val since = items.map { it.date.orEmpty() }.minOrNull().orEmpty()
        payJob?.cancel()
        payJob = viewModelScope.launch {
            repo.receivableIncomes(since).collect { load ->
                val rows = when (load) {
                    is Load.Cached -> load.value
                    is Load.Fresh -> load.value
                    is Load.Failed -> {
                        if (load.cached == null) payError = app.getString(R.string.areceber_pay_load_failed)
                        load.cached?.value ?: choices.orEmpty()
                    }
                }
                val listed = Receivables.paymentChoices(rows, items)
                choices = listed
                if (!chosenByOwner) choice = Receivables.suggestedPayment(listed, items)
            }
        }
    }

    fun choose(id: String) {
        chosenByOwner = true
        choice = id
    }

    fun closePay() {
        if (savingKey == PAY_KEY) return
        payJob?.cancel()
        paying = null
    }

    fun confirmPay() {
        val items = paying ?: return
        if (choices == null) return
        settle(PAY_KEY, items, true, choice.ifEmpty { null })
    }

    fun settle(key: String, items: List<ReceivableDto>, settled: Boolean, incomeId: String? = null) {
        if (savingKey.isNotEmpty() || items.isEmpty()) return
        savingKey = key
        actionError = ""
        payError = ""
        graph.appScope.launch {
            val result = repo.settle(Receivables.settleBody(items, settled, incomeId))
            savingKey = ""
            val error = planWriteError(app, result, R.string.areceber_failed)
            when {
                error == null -> {
                    if (key == PAY_KEY) paying = null
                    ShellEvents.emitDataChanged()
                    val message = app.getString(
                        when {
                            !settled -> R.string.areceber_reopened
                            incomeId != null -> R.string.areceber_settled_income
                            else -> R.string.areceber_settled
                        },
                    )
                    if (cleared) Toast.makeText(app, message, Toast.LENGTH_SHORT).show() else {
                        _notices.tryEmit(message)
                        refreshAll()
                    }
                }
                cleared -> Toast.makeText(app, error, Toast.LENGTH_LONG).show()
                key == PAY_KEY -> payError = error
                else -> actionError = error
            }
        }
    }

    private companion object {
        const val PAY_KEY = "pay"
    }
}
