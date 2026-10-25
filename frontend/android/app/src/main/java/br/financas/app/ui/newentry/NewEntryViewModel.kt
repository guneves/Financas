package br.financas.app.ui.newentry

import android.app.Application
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
import br.financas.app.data.Load
import br.financas.app.outbox.Outbox
import br.financas.app.outbox.OutboxRules
import br.financas.app.outbox.OutboxSender
import br.financas.app.outbox.OutboxStore
import br.financas.app.outbox.OutboxWorker
import br.financas.app.rules.CategoryOption
import br.financas.app.rules.EntryOptions
import br.financas.app.rules.InboxNotice
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Uma lista do formulario: null enquanto nada chegou (nem a copia guardada). */
data class EntryLists(
    val accounts: List<AccountDto>? = null,
    val categories: List<CategoryDto>? = null,
    val cards: List<CreditCardDto>? = null,
    val accountsPending: Boolean = true,
    val categoriesPending: Boolean = true,
    val cardsPending: Boolean = true,
) {
    /** O "isPending" da web: alguma lista ainda sem nada e buscando. Salvar fica desligado. */
    val loading: Boolean get() = accountsPending || categoriesPending || cardsPending
}

/**
 * O estado do "+ Novo" nativo, o mesmo do NewEntrySheet.jsx: o tipo, um formulario por tipo
 * (trocar de tipo nao perde o que foi digitado), a caixa de erro e o Salvar.
 */
class NewEntryViewModel(application: Application) : AndroidViewModel(application) {

    private val app: Application = application
    private val graph = AppGraph.from(application)

    var type by mutableStateOf(EntryType.EXPENSE)
        private set
    var bank by mutableStateOf(BankForm())
        private set
    var transfer by mutableStateOf(TransferForm())
        private set
    var card by mutableStateOf(CardEntryForm())
        private set
    var error by mutableStateOf("")
        private set
    var saving by mutableStateOf(false)
        private set
    var lists by mutableStateOf(EntryLists())
        private set

    /** O client_id do item da fila aberto em Pendentes › Corrigir; null num lancamento novo. */
    var editingClientId by mutableStateOf<String?>(null)
        private set

    /** Preenchido quando a tela deve fechar: o aviso a mostrar. */
    var finished by mutableStateOf<EntryNotice?>(null)
        private set

    /** Um 401: a casca precisa saber (ela volta ao login). */
    var sessionExpired by mutableStateOf(false)
        private set

    private var started = false
    private var pendingCategoryName = ""
    private var listErrorShown = false

    /** A tela ja fechou (Cancelar, voltar, fundo): o resultado de um Salvar vai direto ao aviso. */
    private var cleared = false

    private val saver = EntrySaver(
        hasNetwork = { Outbox.hasRealNetwork(app) },
        post = { path, body -> graph.creationApi.send("POST", path, body) },
        queue = object : EntryQueue {
            override fun put(item: org.json.JSONObject) = OutboxStore.get(app).put(item)
            override fun remove(clientId: String) = OutboxStore.get(app).remove(clientId)
            override fun schedule() = OutboxWorker.schedule(app)
        },
        userId = { graph.sessionUserId() },
    )

    /**
     * A tela vai fechar: um Salvar ainda no ar avisa direto (EntryDelivery) em vez de esperar a
     * tela, que nao vai mais ler [finished]. Chamado pela Activity no finish().
     */
    fun detach() {
        cleared = true
    }

    override fun onCleared() {
        cleared = true
        super.onCleared()
    }

    val categoryOptions: List<CategoryOption>
        get() = EntryOptions.buildCategoryOptions(lists.categories ?: emptyList())

    val accounts: List<AccountDto> get() = lists.accounts ?: emptyList()
    val cards: List<CreditCardDto> get() = lists.cards ?: emptyList()
    val defaultAccountId: String get() = EntryOptions.pickDefaultAccountId(accounts)

    /** Uma vez por tela (girar o aparelho recria a Activity, nao o formulario). */
    fun start(requestedType: String?, clientId: String?) {
        if (started) return
        started = true
        type = EntryType.initial(requestedType)
        bank = BankForm(type = if (requestedType == EntryType.INCOME) EntryType.INCOME else EntryType.EXPENSE)
        if (!clientId.isNullOrEmpty()) {
            editingClientId = clientId
            viewModelScope.launch {
                val item = withContext(Dispatchers.IO) { OutboxStore.get(app).find(clientId) }
                val payload = item?.optJSONObject("payload")
                if (item != null && payload != null) {
                    val forms = NewEntryForms.formsFromItem(item.optString("kind"), payload, categoryOptions)
                    type = forms.type
                    forms.bank?.let { bank = it }
                    forms.transfer?.let { transfer = it }
                    forms.card?.let { card = it }
                    pendingCategoryName = forms.categoryName
                    applyDefaults()
                }
            }
        }
        loadLists()
    }

    private fun loadLists() {
        viewModelScope.launch {
            graph.accounts.accounts().collect { load ->
                lists = when (load) {
                    is Load.Cached -> lists.copy(accounts = load.value, accountsPending = false)
                    is Load.Fresh -> lists.copy(accounts = load.value, accountsPending = false)
                    is Load.Failed -> lists.copy(accountsPending = false).also { listFailed(load.error, lists.accounts == null) }
                }
                applyDefaults()
            }
        }
        viewModelScope.launch {
            graph.categories.categories().collect { load ->
                lists = when (load) {
                    is Load.Cached -> lists.copy(categories = load.value, categoriesPending = false)
                    is Load.Fresh -> lists.copy(categories = load.value, categoriesPending = false)
                    is Load.Failed -> lists.copy(categoriesPending = false).also { listFailed(load.error, lists.categories == null) }
                }
                applyDefaults()
            }
        }
        viewModelScope.launch {
            graph.cards.cards().collect { load ->
                lists = when (load) {
                    is Load.Cached -> lists.copy(cards = load.value, cardsPending = false)
                    is Load.Fresh -> lists.copy(cards = load.value, cardsPending = false)
                    is Load.Failed -> lists.copy(cardsPending = false).also { listFailed(load.error, lists.cards == null) }
                }
                applyDefaults()
            }
        }
    }

    // Sem a lista e sem copia guardada: a caixa de erro diz (uma vez). Com a copia, o
    // formulario segue valendo sem aviso, como na web.
    private fun listFailed(cause: ApiException, missing: Boolean) {
        if (!missing || listErrorShown) return
        listErrorShown = true
        if (cause is ApiException.Unauthorized) sessionExpired = true
        if (error.isEmpty()) {
            error = app.getString(
                if (cause is ApiException.Unauthorized) R.string.data_session_expired else R.string.newentry_lists_failed,
            )
        }
    }

    // Conta padrao e primeiro cartao assim que as listas chegam (ou ja estavam guardadas).
    private fun applyDefaults() {
        val defaultId = defaultAccountId
        if (bank.accountId.isEmpty() && defaultId.isNotEmpty()) bank = bank.copy(accountId = defaultId)
        if (transfer.accountId.isEmpty() && defaultId.isNotEmpty()) transfer = transfer.copy(accountId = defaultId)
        val firstCard = cards.firstOrNull()?.id.orEmpty()
        if (card.cardId.isEmpty() && firstCard.isNotEmpty()) card = card.copy(cardId = firstCard)
        if (pendingCategoryName.isNotEmpty() && lists.categories != null) {
            val id = EntryOptions.categoryIdForName(categoryOptions, pendingCategoryName)
            pendingCategoryName = ""
            if (id.isNotEmpty()) {
                if (type == EntryType.CARD && card.categoryId.isEmpty()) card = card.copy(categoryId = id)
                if (type != EntryType.CARD && bank.categoryId.isEmpty()) bank = bank.copy(categoryId = id)
            }
        }
    }

    fun changeType(next: String) {
        type = next
        error = ""
        if ((next == EntryType.EXPENSE || next == EntryType.INCOME) && bank.type != next) {
            // A categoria depende do tipo (receita x despesa); o resto do que foi digitado fica.
            bank = bank.copy(type = next, categoryId = "")
        }
    }

    fun updateBank(next: BankForm) {
        bank = next
    }

    fun updateTransfer(next: TransferForm) {
        transfer = next
    }

    fun updateCard(next: CardEntryForm) {
        card = next
    }

    fun dismissError() {
        error = ""
    }

    /** O Salvar fica desligado enquanto as listas chegam, sem 2 contas na transferencia, sem cartao. */
    val cannotSave: Boolean
        get() = lists.loading ||
            (type == EntryType.TRANSFER && accounts.size < 2) ||
            (type == EntryType.CARD && cards.isEmpty())

    fun save() {
        if (saving || cannotSave) return
        val options = categoryOptions
        val submission = when (type) {
            EntryType.TRANSFER -> NewEntryForms.prepareTransfer(transfer)
            EntryType.CARD -> NewEntryForms.prepareCard(card, cards, options)
            else -> NewEntryForms.prepareBank(bank, options, defaultAccountId)
        }
        if (submission is Submission.Invalid) {
            error = submission.message
            return
        }
        val ready = submission as Submission.Ready
        saving = true
        error = ""
        val clientId = editingClientId
        // No escopo do app, nao no da tela: fechar o sheet no meio do envio nao cancela o POST
        // (o servidor pode ja ter gravado); o resultado chega aqui ou, com a tela fechada, ao
        // aviso direto (EntryDelivery).
        graph.appScope.launch {
            try {
                if (clientId != null) {
                    updatePending(clientId, ready)
                    finish(NewEntryForms.updatedNotice(ready.label))
                } else {
                    handle(withContext(Dispatchers.IO) { saver.create(ready.kind, ready.payload) }, ready)
                }
            } catch (failure: Exception) {
                fail(failure.message?.takeIf { it.isNotBlank() } ?: ready.fallbackError)
            } finally {
                saving = false
            }
        }
    }

    private fun handle(result: SaveResult, ready: Submission.Ready) {
        when (result) {
            is SaveResult.Queued -> finish(NewEntryForms.queuedNotice(ready.label))
            is SaveResult.Saved -> {
                // O mesmo movimento esperava em Aprovar: o servidor fechou aquele item com este.
                val matched = InboxNotice.matchedInboxNotice(result.data, ready.label)
                finish(if (matched.isNotEmpty()) NewEntryForms.matchedNotice(matched) else NewEntryForms.savedNotice(ready.label))
            }
            is SaveResult.Refused -> fail(result.message ?: ready.fallbackError)
            is SaveResult.SessionExpired -> {
                if (cleared) {
                    EntryDelivery.dataChanged()
                    return
                }
                sessionExpired = true
                error = result.message ?: app.getString(R.string.data_session_expired)
            }
        }
    }

    private fun finish(notice: EntryNotice) {
        if (cleared) EntryDelivery.notice(app, notice) else finished = notice
    }

    private fun fail(message: String) {
        if (cleared) EntryDelivery.error(app, message) else error = message
    }

    // Pendentes › Corrigir: o mesmo client_id, de volta a pendente (OutboxRules.editedItem, o
    // updateItem() da web), e uma rodada de envio ja (o flush() da web).
    private suspend fun updatePending(clientId: String, ready: Submission.Ready) {
        withContext(Dispatchers.IO) {
            val store = OutboxStore.get(app)
            val current = store.find(clientId)
            if (current != null) {
                store.put(OutboxRules.editedItem(current, ready.kind, NewEntryForms.payloadJson(ready.payload)))
            }
        }
        Thread {
            val summary = OutboxSender.run(app, false)
            if ("offline" == summary.stopped) OutboxWorker.schedule(app)
        }.start()
    }
}
