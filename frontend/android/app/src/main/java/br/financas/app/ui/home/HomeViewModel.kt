package br.financas.app.ui.home

import android.app.Application
import android.widget.Toast
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import br.financas.app.R
import br.financas.app.core.monthKey
import br.financas.app.data.ApiException
import br.financas.app.data.AppGraph
import br.financas.app.data.AttentionItemDto
import br.financas.app.data.BudgetMonthDto
import br.financas.app.data.HomeDto
import br.financas.app.data.HomePanelsDto
import br.financas.app.data.InboxWrite
import br.financas.app.data.Load
import br.financas.app.outbox.OutboxStore
import br.financas.app.rules.AttentionRules
import br.financas.app.rules.HomeRules
import br.financas.app.rules.OutboxItems
import br.financas.app.rules.PendingItem
import br.financas.app.ui.nav.ShellEvents
import br.financas.app.ui.theme.ShellPrefs
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Um toast da tela; [info] = o tom informativo da web (o resto e sucesso). */
data class HomeNotice(val message: String, val info: Boolean = false)

/**
 * O estado do Inicio nativo, o mesmo de pages/Dashboard.jsx: GET /api/home (com os pendentes da
 * fila por cima), GET /api/attention, GET /api/budgets?month= — leituras independentes, uma que
 * falha nao esconde as outras —, as dispensas deste aparelho, o modo privado e as duas acoes
 * (pagar fatura, lancar recorrencias), que rodam no escopo do app (AppGraph.appScope): um
 * pagamento ja enviado termina e avisa mesmo com a tela fechada.
 */
class HomeViewModel(application: Application) : AndroidViewModel(application) {

    private val app: Application = application
    private val graph = AppGraph.from(application)
    private val repo = graph.home
    private val dismissals = AttentionDismissals(application)

    /** A ultima resposta de /api/home (null ate a primeira chegar: o esqueleto). */
    var home by mutableStateOf<HomeDto?>(null)
        private set

    /** Os itens da fila nativa do usuario da sessao (os que mexem no saldo entram por cima). */
    var pending by mutableStateOf<List<PendingItem>>(emptyList())
        private set

    var attention by mutableStateOf<List<AttentionItemDto>>(emptyList())
        private set

    var budget by mutableStateOf<BudgetMonthDto?>(null)
        private set

    /** Categorias, ritmo, proximas faturas e parcelamentos (GET /api/home/panels); null ate chegar. */
    var panels by mutableStateOf<HomePanelsDto?>(null)
        private set

    var dismissed by mutableStateOf<List<String>>(emptyList())
        private set

    var hidden by mutableStateOf(false)
        private set


    /** O erro da leitura de /api/home; uma leitura nova que chega o limpa. */
    var loadError by mutableStateOf("")
        private set

    /**
     * O erro (ou o aviso de bloqueadas) de uma acao: "Lançar", pagar. Fica ate a proxima acao —
     * uma releitura nunca o apaga (na web o mesmo estado so muda no erro seguinte).
     */
    var actionError by mutableStateOf("")
        private set

    /** O detalhe da caixa "Movimentações indisponíveis no momento.", se houver. */
    val dataError: String get() = HomeLogic.bannerDetail(actionError, loadError)

    /** A ultima leitura de /api/home nao chegou ao servidor: o que se ve e a copia guardada. */
    var offline by mutableStateOf(false)
        private set

    /** Quando a copia mostrada foi guardada ("atualizado às HH:MM"); null = do servidor. */
    var cachedAt by mutableStateOf<Long?>(null)
        private set

    var refreshing by mutableStateOf(false)
        private set

    var sessionExpired by mutableStateOf(false)
        private set

    var payRequest by mutableStateOf<PayRequest?>(null)
        private set

    var paying by mutableStateOf(false)
        private set

    var payError by mutableStateOf("")
        private set

    var runningRecurring by mutableStateOf(false)
        private set

    var bellOpen by mutableStateOf(false)
        private set

    private val _notices = MutableSharedFlow<HomeNotice>(extraBufferCapacity = 8)

    /** Os toasts da tela (o toast() da web). */
    val notices: SharedFlow<HomeNotice> = _notices.asSharedFlow()

    private var homeJob: Job? = null
    private var cleared = false

    /** O Inicio com os pendentes por cima; null ate a primeira resposta. */
    val view: HomeView? get() = home?.let { HomeLogic.view(it, pending) }

    /** Os avisos que este aparelho nao dispensou (o sino mostra todos). */
    val shownAttention: List<AttentionItemDto>
        get() = AttentionRules.undismissedItems(attention, dismissed) { it.key }

    val pendingInBalance: Int get() = HomeLogic.pendingInBalance(pending)

    init {
        dismissed = dismissals.load()
        hidden = ShellPrefs.valuesHidden(app) ?: false
    }

    override fun onCleared() {
        cleared = true
        super.onCleared()
    }

    /** Tudo de novo: ao abrir, ao voltar para a tela e depois de uma escrita. */
    fun refreshAll() {
        // A web pode ter trocado o olho ou dispensado algo enquanto a tela estava fechada.
        hidden = ShellPrefs.valuesHidden(app) ?: hidden
        readHome()
        readAttention()
        readBudget()
        readPanels()
        readPending()
    }

    /** Puxar para atualizar: o giro fica ate /api/home responder. */
    fun pullRefresh() {
        refreshing = true
        refreshAll()
    }

    private fun readHome() {
        homeJob?.cancel()
        homeJob = viewModelScope.launch {
            try {
                repo.home().collect { load ->
                    when (load) {
                        is Load.Cached -> if (home == null) {
                            home = load.value
                            cachedAt = load.storedAt
                        }
                        is Load.Fresh -> {
                            home = load.value
                            cachedAt = null
                            offline = false
                            sessionExpired = false
                            loadError = ""
                        }
                        is Load.Failed -> homeFailed(load)
                    }
                }
            } finally {
                refreshing = false
            }
        }
    }

    private fun homeFailed(load: Load.Failed<HomeDto>) {
        val hadData = home != null
        // Sem nada na tela nem no disco: o Inicio vazio (R$ 0,00) com a caixa de erro, como a web.
        if (!hadData && load.cached == null) home = HomeDto()
        when (val cause = load.error) {
            is ApiException.Network, is ApiException.BadResponse -> {
                offline = true
                if (!hadData && load.cached == null) loadError = app.getString(R.string.data_offline)
            }
            is ApiException.Unauthorized -> expire(cause.serverMessage)
            is ApiException.Http ->
                if (cause.status in 300..399) {
                    offline = true
                } else {
                    loadError = cause.serverMessage ?: app.getString(R.string.home_load_failed)
                }
        }
    }

    private fun readAttention() {
        viewModelScope.launch {
            repo.attention().collect { load ->
                when (load) {
                    is Load.Cached -> if (attention.isEmpty()) attention = load.value.items
                    is Load.Fresh -> attention = load.value.items
                    is Load.Failed -> Unit
                }
            }
        }
    }

    private fun readBudget() {
        viewModelScope.launch {
            repo.budget(monthKey()).collect { load ->
                when (load) {
                    is Load.Cached -> if (budget == null) budget = load.value
                    is Load.Fresh -> budget = load.value
                    is Load.Failed -> Unit
                }
            }
        }
    }

    private fun readPanels() {
        viewModelScope.launch {
            repo.panels().collect { load ->
                when (load) {
                    is Load.Cached -> if (panels == null) panels = load.value
                    is Load.Fresh -> panels = load.value
                    is Load.Failed -> Unit
                }
            }
        }
    }

    /** A fila nativa (OutboxStore), so os itens do usuario da sessao, como useOutbox() na web. */
    fun readPending() {
        viewModelScope.launch {
            pending = withContext(Dispatchers.IO) {
                val texts = OutboxStore.get(app).all().map { it.toString() }
                OutboxItems.forUser(texts, graph.sessionUserId())
            }
        }
    }


    private fun expire(message: String?) {
        sessionExpired = true
        loadError = message ?: app.getString(R.string.data_session_expired)
    }

    // ---- O olho ----

    /** Troca o modo privado: a tela redesenha so os valores; a web le ao voltar (ShellPrefs). */
    fun toggleHidden() {
        hidden = !hidden
        ShellPrefs.saveValuesHidden(app, hidden)
    }

    // ---- Precisa de atencao ----

    /** O X: dispensa neste aparelho os avisos que estao na tela; o sino continua com eles. */
    fun dismissShown() {
        val keys = shownAttention.map { it.key }
        if (keys.isEmpty()) return
        dismissed = dismissals.add(dismissed, keys)
        notice(HomeNotice(app.getString(R.string.home_attention_dismissed), info = true))
    }

    fun openBell() {
        bellOpen = true
    }

    fun closeBell() {
        bellOpen = false
    }

    // ---- Pagar fatura ----

    fun openPayOverdue() {
        val request = HomeLogic.overdueRequest(attention.firstOrNull { it.kind == AttentionRules.INVOICE_OVERDUE }) ?: return
        payError = ""
        payRequest = request
    }

    fun openPayPayable() {
        val request = HomeLogic.payableRequest(home?.nextInvoices.orEmpty()) ?: return
        payError = ""
        payRequest = request
    }

    fun closePay() {
        if (!paying) payRequest = null
    }

    /**
     * Um pedido por fatura, em sequencia, como a web. [accountId] "" = "Conta de cada cartão" (o
     * servidor escolhe). Uma recusa para no meio: as anteriores podem ter sido pagas, entao tudo
     * e relido de qualquer jeito.
     */
    fun confirmPay(accountId: String) {
        val request = payRequest ?: return
        if (paying) return
        paying = true
        payError = ""
        graph.appScope.launch {
            var failure: String? = null
            for (invoice in request.invoices) {
                val result = repo.payInvoice(invoice.cardId, invoice.invoiceMonth, invoice.invoiceYear, accountId)
                failure = when (result) {
                    is InboxWrite.Done -> null
                    is InboxWrite.Offline -> app.getString(R.string.home_offline_action)
                    is InboxWrite.SessionExpired -> {
                        sessionExpired = true
                        result.message ?: app.getString(R.string.data_session_expired)
                    }
                    is InboxWrite.Conflict -> result.message ?: app.getString(R.string.home_pay_failed)
                    is InboxWrite.Refused -> result.message ?: app.getString(R.string.home_pay_failed)
                }
                if (failure != null) break
            }
            paying = false
            if (failure == null) {
                payRequest = null
                notice(HomeNotice(HomeRules.paidNotice(request.invoices.size, request.total)))
            } else if (cleared) {
                Toast.makeText(app, failure, Toast.LENGTH_LONG).show()
            } else {
                payError = failure
            }
            ShellEvents.emitDataChanged()
            if (!cleared) refreshAll()
        }
    }

    // ---- Lancar recorrencias ----

    fun runRecurring() {
        if (runningRecurring) return
        runningRecurring = true
        actionError = ""
        graph.appScope.launch {
            when (val result = repo.runRecurring()) {
                is InboxWrite.Done -> {
                    val created = result.value.created
                    notice(HomeNotice(HomeRules.recurringNotice(created), info = created <= 0))
                    val blocked = HomeRules.blockedRecurringMessage(result.value.blocked.map { it.rule })
                    if (blocked.isNotEmpty()) fail(blocked)
                    ShellEvents.emitDataChanged()
                    if (!cleared) refreshAll()
                }
                is InboxWrite.Offline -> fail(app.getString(R.string.home_offline_action))
                is InboxWrite.SessionExpired -> {
                    sessionExpired = true
                    fail(result.message ?: app.getString(R.string.data_session_expired))
                }
                is InboxWrite.Conflict -> fail(result.message ?: app.getString(R.string.home_recurring_failed))
                is InboxWrite.Refused -> fail(result.message ?: app.getString(R.string.home_recurring_failed))
            }
            runningRecurring = false
        }
    }

    private fun notice(notice: HomeNotice) {
        if (cleared) Toast.makeText(app, notice.message, Toast.LENGTH_SHORT).show() else _notices.tryEmit(notice)
    }

    private fun fail(message: String) {
        if (cleared) Toast.makeText(app, message, Toast.LENGTH_LONG).show() else actionError = message
    }
}
