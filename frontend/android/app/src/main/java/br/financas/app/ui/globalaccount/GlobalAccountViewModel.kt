package br.financas.app.ui.globalaccount

import android.app.Application
import android.widget.Toast
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import br.financas.app.R
import br.financas.app.data.AccountDto
import br.financas.app.data.AppGraph
import br.financas.app.data.TransactionPageDto
import br.financas.app.rules.GlobalAccount
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
 * Conta global nativa (17-conta-global.md): pages/ContaGlobal.jsx em Compose. GET /api/accounts
 * (a conta em outra moeda, balance e balance_brl) e GET /api/transactions?account_id=<ela> (o
 * extrato dela, primeira pagina). "E meu" e POST /api/review. Registrar um Pix para ca fica no
 * computador (precisa do valor nas duas moedas).
 */
class GlobalAccountViewModel(application: Application) : AndroidViewModel(application) {

    private val app = application
    private val graph = AppGraph.from(application)

    val accounts = ScreenLoad<List<AccountDto>>()
    val page = ScreenLoad<TransactionPageDto>()
    var hidden by mutableStateOf(ShellPrefs.valuesHidden(application) ?: false)
        private set
    var actionError by mutableStateOf("")
        private set
    var savingKey by mutableStateOf("")
        private set
    var selectedId by mutableStateOf<String?>(null)
        private set

    private val _notices = MutableSharedFlow<String>(extraBufferCapacity = 8)
    val notices: SharedFlow<String> = _notices.asSharedFlow()

    private var readJob: Job? = null
    private var cleared = false

    override fun onCleared() {
        cleared = true
        super.onCleared()
    }

    val globals: List<AccountDto> get() = GlobalAccount.globalAccounts(accounts.value.orEmpty())

    val account: AccountDto? get() = globals.firstOrNull { it.id == selectedId } ?: globals.firstOrNull()

    val statement: List<GlobalAccount.Row>
        get() {
            val current = account ?: return emptyList()
            val names = accounts.value.orEmpty().associate { it.id to it.name }
            return GlobalAccount.statement(page.value?.items.orEmpty(), current.id, names)
        }

    fun refreshAll() {
        hidden = ShellPrefs.valuesHidden(app) ?: hidden
        readJob?.cancel()
        readJob = viewModelScope.launch {
            accounts.collect(app, graph.accounts.accounts(), R.string.global_load_failed)
            val current = account ?: return@launch
            page.collect(app, graph.lancamentos.firstPage(mapOf("account_id" to current.id)), R.string.global_load_failed)
        }
    }

    fun choose(id: String) {
        if (id == account?.id) return
        selectedId = id
        page.loaded = false
        page.value = null
        refreshAll()
    }

    fun toggleHidden() {
        hidden = !hidden
        ShellPrefs.saveValuesHidden(app, hidden)
    }

    fun dismissActionError() {
        actionError = ""
    }

    fun confirm(key: String, rows: List<GlobalAccount.Row>) {
        if (savingKey.isNotEmpty() || rows.isEmpty()) return
        savingKey = key
        actionError = ""
        graph.appScope.launch {
            val result = graph.review.confirm(rows.map { mapOf("table" to "transactions", "id" to it.transaction.id) })
            savingKey = ""
            val error = planWriteError(app, result, R.string.global_confirm_failed)
            when {
                error == null -> {
                    ShellEvents.emitDataChanged()
                    val message = if (rows.size > 1) app.getString(R.string.global_confirmed_n, rows.size) else app.getString(R.string.global_confirmed)
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
