package br.financas.app.ui.inbox

import android.app.Application
import android.widget.Toast
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import br.financas.app.R
import br.financas.app.data.AccountDto
import br.financas.app.data.ApiException
import br.financas.app.data.AppGraph
import br.financas.app.data.CategoryDto
import br.financas.app.data.CreditCardDto
import br.financas.app.data.InboxCandidateDto
import br.financas.app.data.InboxDecision
import br.financas.app.data.InboxHintDto
import br.financas.app.data.InboxItemDto
import br.financas.app.data.InboxListDto
import br.financas.app.data.InboxRepository
import br.financas.app.data.InboxSourceDto
import br.financas.app.data.InboxWrite
import br.financas.app.data.Load
import br.financas.app.rules.CategoryOption
import br.financas.app.rules.EntryOptions
import br.financas.app.rules.InboxDraft
import br.financas.app.rules.InboxRules
import br.financas.app.ui.components.ConfirmRequest
import br.financas.app.ui.nav.ShellEvents
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch

/**
 * O estado de Aprovar nativo, o mesmo de pages/lancamentos/Aprovar.jsx: as duas listas, as
 * escolhas lembradas, o ajuste "Sempre perguntar", a caixa de erro e o botao ocupado.
 *
 * Leituras: a copia guardada primeiro (so na primeira vez: depois a lista na tela vale mais que
 * a do disco), depois o servidor. Sem conexao a lista guardada fica, so para ler.
 * Escritas: so com o servidor, nunca na fila, sempre com a `version` do item; rodam no escopo do
 * app (AppGraph.appScope), entao uma decisao ja enviada termina e avisa mesmo com a tela fechada.
 */
class InboxViewModel(application: Application) : AndroidViewModel(application) {

    private val app: Application = application
    private val graph = AppGraph.from(application)
    private val repo = graph.inbox

    var view by mutableStateOf(InboxRepository.VIEW_PENDING)
        private set
    var pending by mutableStateOf<List<InboxItemDto>?>(null)
        private set
    var decided by mutableStateOf<List<InboxItemDto>?>(null)
        private set
    var pendingCount by mutableStateOf(0)
        private set
    var hints by mutableStateOf<List<InboxHintDto>>(emptyList())
        private set
    var alwaysAsk by mutableStateOf<Boolean?>(null)
        private set
    var accounts by mutableStateOf<List<AccountDto>>(emptyList())
        private set
    var cards by mutableStateOf<List<CreditCardDto>>(emptyList())
        private set
    var categoryOptions by mutableStateOf<List<CategoryOption>>(emptyList())
        private set

    /** O erro da leitura da lista ("Não foi possível ler o que espera aprovação."). */
    var listError by mutableStateOf("")
        private set

    /** O erro de uma acao (inclusive o 409), ate o dono fechar. */
    var error by mutableStateOf("")
        private set

    /** A ultima leitura nao chegou ao servidor: a lista e a guardada, so para ler. */
    var offline by mutableStateOf(false)
        private set

    /** Quando a copia mostrada foi guardada (o "lista de HH:MM" sem conexao); null = do servidor. */
    var cachedAt by mutableStateOf<Long?>(null)
        private set

    /** "<id>:<acao>" do botao com o giro (o busyKey da web). */
    var busyKey by mutableStateOf("")
        private set

    /** O item no sheet "Corrigir antes de aprovar". */
    var editing by mutableStateOf<InboxItemDto?>(null)
        private set

    /** "save" ou "approve": qual botao do sheet esta no ar. */
    var editSaving by mutableStateOf("")
        private set

    var settingsSaving by mutableStateOf(false)
        private set

    var sessionExpired by mutableStateOf(false)
        private set

    /** A confirmacao aberta (separar uma fonte, esquecer uma escolha). */
    var confirm by mutableStateOf<ConfirmRequest?>(null)
        private set

    /** O item que a notificacao abriu: a lista rola ate ele. */
    var focusId by mutableStateOf<String?>(null)
        private set

    private val _notices = MutableSharedFlow<String>(extraBufferCapacity = 8)

    /** Os toasts da tela (o toast() da web). */
    val notices: SharedFlow<String> = _notices.asSharedFlow()

    private val reading = mutableMapOf<String, Job>()
    private var cleared = false

    val items: List<InboxItemDto>? get() = if (isPendingView) pending else decided
    val isPendingView: Boolean get() = view == InboxRepository.VIEW_PENDING

    /** "Aprovar prontos (n)": so na vista de pendentes. */
    val readyIds: List<String>
        get() = if (isPendingView) InboxRules.readyIds(pending.orEmpty().map { it.rule }).filterNotNull() else emptyList()

    /** O seletor de cartao so tem os de credito; o de conta, so as ativas. */
    val pickerCards: List<CreditCardDto> get() = InboxLogic.pickerCards(cards)
    val pickerAccounts: List<AccountDto> get() = InboxLogic.activeAccounts(accounts)

    override fun onCleared() {
        cleared = true
        super.onCleared()
    }

    fun changeView(next: String) {
        if (next == view) return
        view = next
        refresh(next)
    }

    /** Tudo de novo: a lista da vista, as escolhas lembradas, o ajuste e os seletores. */
    fun refreshAll() {
        refresh(view)
        refreshHints()
        refreshSettings()
        refreshPickers()
    }

    /** Rele uma lista (a cada 20 s a de pendentes, com a tela aberta). */
    fun refresh(target: String = view, force: Boolean = false) {
        val running = reading[target]
        if (running?.isActive == true) {
            // Depois de uma escrita, uma leitura de antes dela nao pode vencer a lista nova.
            if (!force) return
            running.cancel()
        }
        reading[target] = viewModelScope.launch {
            repo.list(target).collect { load -> onList(target, load) }
        }
    }

    private fun listFor(target: String): List<InboxItemDto>? =
        if (target == InboxRepository.VIEW_PENDING) pending else decided

    private fun setList(target: String, items: List<InboxItemDto>) {
        if (target == InboxRepository.VIEW_PENDING) pending = items else decided = items
    }

    private fun onList(target: String, load: Load<InboxListDto>) {
        when (load) {
            is Load.Cached -> if (listFor(target) == null) {
                setList(target, load.value.items)
                pendingCount = load.value.pendingCount
                cachedAt = load.storedAt
            }
            is Load.Fresh -> {
                setList(target, load.value.items)
                pendingCount = load.value.pendingCount
                offline = false
                cachedAt = null
                listError = ""
                sessionExpired = false
            }
            is Load.Failed -> {
                // Sem nada na tela nem no disco: a lista vazia, para sair do esqueleto.
                if (listFor(target) == null && load.cached == null && load.error !is ApiException.Network) {
                    setList(target, emptyList())
                }
                readFailed(load.error)
            }
        }
    }

    private fun readFailed(cause: ApiException) {
        when (cause) {
            is ApiException.Network -> offline = true
            is ApiException.Unauthorized -> expire(cause.serverMessage)
            is ApiException.Http ->
                if (cause.status in 300..399) offline = true
                else listError = cause.serverMessage ?: app.getString(R.string.inbox_load_failed)
            is ApiException.BadResponse -> offline = true
        }
    }

    private fun expire(message: String?) {
        sessionExpired = true
        listError = message ?: app.getString(R.string.data_session_expired)
        // A WebView rele, recebe o 401 e mostra o login (ainda e ela que faz o login).
        ShellEvents.emitDataChanged()
    }

    private fun refreshHints() {
        viewModelScope.launch {
            repo.hints().collect { load ->
                when (load) {
                    is Load.Cached -> if (hints.isEmpty()) hints = load.value
                    is Load.Fresh -> hints = load.value
                    is Load.Failed -> Unit
                }
            }
        }
    }

    private fun refreshSettings() {
        viewModelScope.launch {
            repo.settings().collect { load ->
                when (load) {
                    is Load.Cached -> if (alwaysAsk == null) alwaysAsk = load.value.alwaysAsk
                    is Load.Fresh -> alwaysAsk = load.value.alwaysAsk
                    is Load.Failed -> Unit
                }
            }
        }
    }

    private fun refreshPickers() {
        viewModelScope.launch {
            graph.accounts.accounts().collect { load -> valueOf(load)?.let { accounts = it } }
        }
        viewModelScope.launch {
            graph.cards.cards().collect { load -> valueOf(load)?.let { cards = it } }
        }
        viewModelScope.launch {
            graph.categories.categories().collect { load ->
                valueOf(load)?.let { categoryOptions = EntryOptions.buildCategoryOptions(it.filter { category: CategoryDto -> !category.isArchived }) }
            }
        }
    }

    private fun <T> valueOf(load: Load<T>): T? = when (load) {
        is Load.Cached -> load.value
        is Load.Fresh -> load.value
        is Load.Failed -> null
    }

    // ---- O item da notificacao ----

    /** A notificacao "Novo para aprovar" abriu a tela neste item. */
    fun focus(id: String?) {
        if (id.isNullOrEmpty()) return
        focusId = id
        if (!isPendingView) changeView(InboxRepository.VIEW_PENDING)
        viewModelScope.launch {
            repo.item(id).collect { load ->
                // Ainda pendente e fora da lista lida (ela pode ser de antes da notificacao): entra.
                if (load is Load.Fresh && load.value.isPending) {
                    pending = InboxLogic.applyDecision(pending ?: return@collect, load.value, pendingView = true)
                }
            }
        }
    }

    /** A lista ja rolou ate o item. */
    fun focusDone() {
        focusId = null
    }

    // ---- As acoes ----

    fun dismissError() {
        error = ""
    }

    fun dismissConfirm() {
        confirm = null
    }

    fun approve(item: InboxItemDto, remember: Boolean) = decide(
        InboxLogic.busyKey(item.id, "approve"),
        R.string.inbox_toast_approved,
    ) { repo.approve(item.id, InboxLogic.approveBody(item, remember)) }

    /** "É este": o movimento e esse lancamento que ja existe. */
    fun match(item: InboxItemDto, candidate: InboxCandidateDto, remember: Boolean) = decide(
        InboxLogic.busyKey(item.id, "match:${candidate.id}"),
        R.string.inbox_toast_matched,
    ) { repo.approve(item.id, InboxLogic.matchBody(item, candidate, remember)) }

    fun deny(item: InboxItemDto) = decide(
        InboxLogic.busyKey(item.id, "deny"),
        R.string.inbox_toast_denied,
    ) { repo.deny(item.id, item.version) }

    fun restore(item: InboxItemDto) = decide(
        InboxLogic.busyKey(item.id, "restore"),
        R.string.inbox_toast_restored,
    ) { repo.restore(item.id, item.version) }

    /**
     * Uma escolha no cartao do item (credito/debito, cartao, conta) ou "Não é esta": o item que
     * volta substitui o da lista, com a versao nova, e "Aprovar" logo depois nao cai num 409.
     * [onFinished] fecha os seletores, deu certo ou nao (como a web).
     */
    fun quick(item: InboxItemDto, body: Map<String, Any?>, onFinished: () -> Unit = {}) {
        write(
            key = InboxLogic.busyKey(item.id, "quick"),
            block = { repo.update(item.id, body) },
            onDone = ::applyDecision,
            success = null,
            onFinished = onFinished,
        )
    }

    fun toggleRecurring(item: InboxItemDto) {
        quick(item, InboxRules.recurringToggle(item.rule, item.recurringOff))
    }

    fun askSplit(item: InboxItemDto, source: InboxSourceDto) {
        val label = InboxRules.sourceLabel(source.rule)
        confirm = ConfirmRequest(
            title = app.getString(R.string.inbox_split_title),
            message = app.getString(R.string.inbox_split_message, label),
            confirmLabel = app.getString(R.string.inbox_split_confirm),
        ) {
            write(
                key = InboxLogic.busyKey(item.id, "split"),
                block = { repo.split(item.id, InboxLogic.splitBody(item, source)) },
                onDone = { result ->
                    applyDecision(InboxDecision(result.item, result.pendingCount))
                    result.newItem?.let { pending = InboxLogic.applyDecision(pending, it, pendingView = true) }
                },
                success = { app.getString(R.string.inbox_toast_split) },
            )
        }
    }

    fun approveReady() {
        val ids = readyIds
        if (ids.isEmpty()) return
        write(
            key = InboxLogic.BUSY_READY,
            block = { repo.approveReady(ids) },
            onDone = { result ->
                pending = pending?.filter { it.id !in result.approved }
                result.pendingCount?.let { pendingCount = it }
            },
            success = { result -> InboxRules.approveReadySummary(result.rule) },
        )
    }

    fun askForgetHint(hint: InboxHintDto) {
        confirm = ConfirmRequest(
            title = app.getString(R.string.inbox_forget_title),
            message = app.getString(R.string.inbox_forget_message, InboxRules.hintText(hint.rule)),
            confirmLabel = app.getString(R.string.inbox_forget_confirm),
        ) {
            write(
                key = "hint:${hint.id}",
                block = { repo.forgetHint(hint.id) },
                onDone = { hints = hints.filter { it.id != hint.id } },
                success = { app.getString(R.string.inbox_toast_hint_forgotten) },
            )
        }
    }

    fun setAlwaysAsk(value: Boolean) {
        if (settingsSaving) return
        settingsSaving = true
        write(
            key = "settings",
            block = { repo.setAlwaysAsk(value) },
            onDone = { result -> alwaysAsk = result.alwaysAsk },
            success = {
                app.getString(if (value) R.string.inbox_toast_always_ask_on else R.string.inbox_toast_always_ask_off)
            },
            fallbackError = R.string.inbox_save_failed,
            onFinished = { settingsSaving = false },
        )
    }

    fun openEdit(item: InboxItemDto) {
        editing = item
    }

    fun closeEdit() {
        if (editSaving.isEmpty()) editing = null
    }

    /** "Salvar e decidir depois" (PATCH) ou "Salvar e aprovar" (approve), so com o que mudou. */
    fun saveEdit(item: InboxItemDto, draft: InboxDraft, andApprove: Boolean) {
        if (editSaving.isNotEmpty()) return
        val changes = InboxRules.changesFromDraft(item.rule, draft)
        editSaving = if (andApprove) "approve" else "save"
        write(
            key = InboxLogic.busyKey(item.id, "edit"),
            block = { if (andApprove) repo.approve(item.id, changes) else repo.update(item.id, changes) },
            onDone = { decision ->
                applyDecision(decision)
                editing = null
            },
            success = {
                app.getString(if (andApprove) R.string.inbox_toast_edit_approved else R.string.inbox_toast_edit_saved)
            },
            onFinished = { editSaving = "" },
        )
    }

    private fun decide(key: String, successText: Int, block: suspend () -> InboxWrite<InboxDecision>) {
        write(key = key, block = block, onDone = ::applyDecision, success = { app.getString(successText) })
    }

    private fun applyDecision(decision: InboxDecision) {
        pending = InboxLogic.applyDecision(pending, decision.item, pendingView = true)
        decided = InboxLogic.applyDecision(decided, decision.item, pendingView = false)
        decision.pendingCount?.let { pendingCount = it }
    }

    /**
     * Uma escrita, o run() da web: o giro no botao, a caixa de erro limpa, o pedido; deu certo,
     * o toast e a WebView avisada (o contador da aba); 409, CONFLICT_MESSAGE e a lista relida.
     */
    private fun <T> write(
        key: String,
        block: suspend () -> InboxWrite<T>,
        onDone: (T) -> Unit,
        success: ((T) -> String?)?,
        fallbackError: Int = R.string.inbox_action_failed,
        onFinished: () -> Unit = {},
    ) {
        busyKey = key
        error = ""
        graph.appScope.launch {
            val result = try {
                block()
            } catch (failure: Exception) {
                InboxWrite.Refused(0, failure.message)
            }
            when (result) {
                is InboxWrite.Done -> {
                    onDone(result.value)
                    success?.invoke(result.value)?.let(::notice)
                    ShellEvents.emitDataChanged()
                    refreshAfterWrite()
                }
                is InboxWrite.Conflict -> {
                    fail(InboxRules.CONFLICT_MESSAGE)
                    refreshAfterWrite()
                }
                is InboxWrite.Refused -> fail(result.message?.takeIf { it.isNotBlank() } ?: app.getString(fallbackError))
                is InboxWrite.Offline -> {
                    offline = true
                    fail(app.getString(R.string.inbox_offline_action))
                    refresh(view)
                }
                is InboxWrite.SessionExpired -> {
                    sessionExpired = true
                    fail(result.message ?: app.getString(R.string.data_session_expired))
                    ShellEvents.emitDataChanged()
                }
            }
            if (busyKey == key) busyKey = ""
            onFinished()
        }
    }

    // A web invalida tudo depois de uma escrita: as duas listas e as escolhas lembradas.
    private fun refreshAfterWrite() {
        if (cleared) return
        refresh(InboxRepository.VIEW_PENDING, force = true)
        if (decided != null) refresh(InboxRepository.VIEW_DECIDED, force = true)
        refreshHints()
    }

    private fun notice(message: String) {
        if (cleared) Toast.makeText(app, message, Toast.LENGTH_SHORT).show() else _notices.tryEmit(message)
    }

    private fun fail(message: String) {
        if (cleared) Toast.makeText(app, message, Toast.LENGTH_LONG).show() else error = message
    }
}
