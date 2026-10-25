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
    var inboxCount by mutableStateOf(0)
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

    fun settle(key: String, items: List<ReceivableDto>, settled: Boolean) {
        if (savingKey.isNotEmpty() || items.isEmpty()) return
        savingKey = key
        actionError = ""
        graph.appScope.launch {
            val result = repo.settle(Receivables.settleBody(items, settled))
            savingKey = ""
            val error = planWriteError(app, result, R.string.areceber_failed)
            when {
                error == null -> {
                    ShellEvents.emitDataChanged()
                    val message = app.getString(if (settled) R.string.areceber_settled else R.string.areceber_reopened)
                    if (cleared) Toast.makeText(app, message, Toast.LENGTH_SHORT).show() else {
                        _notices.tryEmit(message)
                        refreshAll()
                    }
                }
                cleared -> Toast.makeText(app, error, Toast.LENGTH_LONG).show()
                else -> actionError = error
            }
        }
    }
}
