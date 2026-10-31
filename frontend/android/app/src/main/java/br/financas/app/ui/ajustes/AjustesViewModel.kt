package br.financas.app.ui.ajustes

import android.app.Application
import android.widget.Toast
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import br.financas.app.BuildConfig
import br.financas.app.R
import br.financas.app.core.MoneyInput
import br.financas.app.core.moneyInputValue
import br.financas.app.data.AccountDto
import br.financas.app.data.AppGraph
import br.financas.app.data.CategoryDto
import br.financas.app.data.CreditCardDto
import br.financas.app.data.InboxWrite
import br.financas.app.data.Load
import br.financas.app.data.MeDto
import br.financas.app.data.OpenFinanceDto
import br.financas.app.data.OpenFinanceItemDto
import br.financas.app.data.OpenFinanceSettingsDto
import br.financas.app.notify.NotifyAccess
import br.financas.app.notify.NotifyEvents
import br.financas.app.notify.NotifySettings
import br.financas.app.outbox.Outbox
import br.financas.app.outbox.Session
import br.financas.app.rules.ApkUpdateTexts
import br.financas.app.rules.CardForm
import br.financas.app.rules.CardFunctions
import br.financas.app.rules.NotifyTexts
import br.financas.app.rules.OpenFinanceRules
import br.financas.app.rules.Settings
import br.financas.app.ui.components.ConfirmRequest
import br.financas.app.ui.nav.ShellEvents
import br.financas.app.ui.planejar.ScreenLoad
import br.financas.app.ui.planejar.planWriteError
import br.financas.app.ui.theme.ShellPrefs
import br.financas.app.update.ApkUpdater
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

/** As secoes de Ajustes do celular, na ordem da web (Regras e Integrações ficam no computador). */
enum class AjustesSection(val anchor: String) {
    CONTAS("contas"),
    CARTOES("cartoes"),
    CATEGORIAS("categorias"),
    OPEN_FINANCE("open-finance"),
    APARENCIA("aparencia"),
    PERFIL("perfil"),
    NOTIFICACOES("notificacoes"),
    VERSAO("versao");

    companion object {
        fun of(anchor: String?): AjustesSection? = entries.firstOrNull { it.anchor == anchor }
    }
}

/** "Nova conta" e o sheet de edicao: os campos como digitados. */
data class AccountForm(val name: String = "", val type: String = "CHECKING", val institution: String = "", val initialBalance: String = "")

/** O formulario de cartao (novo e edicao); [editing] e o cartao editado. */
data class CardFormState(
    val name: String = "",
    val functions: String = CardFunctions.CREDIT,
    val dueDay: String = "",
    val closingDay: String = "",
    val autopayAccountId: String = "",
    val debitAccountId: String = "",
)

data class CategoryForm(val name: String = "", val kind: String = "EXPENSE", val parentId: String = "")

/**
 * Ajustes nativo (11-ajustes.md): as secoes marcadas "early" e "mid" — Contas, Cartões,
 * Categorias, Aprovar, Aparência, Perfil, Notificações dos bancos e Versão do app (so o APK).
 * Regras de importação e Integrações ficam no computador. Toda escrita so com o servidor (writeApi),
 * nunca na fila; Notificações e Versão falam com o aparelho (NotifyAccess, ApkUpdater).
 */
class AjustesViewModel(application: Application) : AndroidViewModel(application) {

    private val app = application
    private val graph = AppGraph.from(application)
    private val repo = graph.ajustes

    var section by mutableStateOf<AjustesSection?>(null)
        private set

    val accounts = ScreenLoad<List<AccountDto>>()
    val cards = ScreenLoad<List<CreditCardDto>>()
    val categories = ScreenLoad<List<CategoryDto>>()
    val me = ScreenLoad<MeDto>()
    val openFinance = ScreenLoad<OpenFinanceDto>()
    val openFinanceSettings = ScreenLoad<OpenFinanceSettingsDto>()
    /** O item da Pluggy que esta em "Atualizar" (o botao dele gira). */
    var syncingItemId by mutableStateOf<String?>(null)
        private set

    var hidden by mutableStateOf(ShellPrefs.valuesHidden(application) ?: false)
        private set
    var theme by mutableStateOf(ShellPrefs.themePreference(application))
        private set

    var error by mutableStateOf("")
        private set
    var busy by mutableStateOf(false)
        private set
    var confirm by mutableStateOf<ConfirmRequest?>(null)
        private set

    // Contas
    var accountFormOpen by mutableStateOf(false)
        private set
    var accountForm by mutableStateOf(AccountForm())
        private set
    var editingAccount by mutableStateOf<AccountDto?>(null)
        private set
    var editAccountForm by mutableStateOf(AccountForm())
        private set

    // Cartoes
    var cardFormOpen by mutableStateOf(false)
        private set
    var cardForm by mutableStateOf(CardFormState())
        private set
    var editingCard by mutableStateOf<CreditCardDto?>(null)
        private set
    var editCardForm by mutableStateOf(CardFormState())
        private set
    var savingAutopayId by mutableStateOf<String?>(null)
        private set

    // Categorias
    var categoryFormOpen by mutableStateOf(false)
        private set
    var categoryForm by mutableStateOf(CategoryForm())
        private set
    var editingCategoryId by mutableStateOf("")
        private set
    var categoryEdit by mutableStateOf(CategoryForm())
        private set

    // Perfil
    var username by mutableStateOf<String?>(null)
        private set
    var profileMessage by mutableStateOf<Pair<Boolean, String>?>(null)
        private set

    // Notificacoes
    var notify by mutableStateOf<NotifyTexts.NotifyStatus?>(null)
        private set
    var captured by mutableStateOf<List<CapturedRow>>(emptyList())
        private set
    var notifyBusy by mutableStateOf("")
        private set

    // Versao
    var apk by mutableStateOf<ApkUpdateTexts.ApkState?>(null)
        private set
    var apkCheck by mutableStateOf<ApkUpdateTexts.Message?>(null)
        private set
    var apkInstall by mutableStateOf<ApkUpdateTexts.Message?>(null)
        private set
    var apkBusy by mutableStateOf("")
        private set
    private var installAfterPermission = false

    private val _notices = MutableSharedFlow<String>(extraBufferCapacity = 8)
    val notices: SharedFlow<String> = _notices.asSharedFlow()

    private var cleared = false

    // O leitor guardou uma notificacao (ou o Android o ligou/desligou) com Ajustes aberta.
    private val notifyListener = NotifyEvents.Listener {
        android.os.Handler(android.os.Looper.getMainLooper()).post { if (!cleared) readNotify() }
    }

    init {
        NotifyEvents.setListener(notifyListener)
    }

    override fun onCleared() {
        cleared = true
        NotifyEvents.setListener(null)
        super.onCleared()
    }

    /** Uma notificacao capturada, como a lista mostra. */
    data class CapturedRow(val key: String, val app: String, val postedAt: Long, val title: String, val text: String, val summary: Boolean, val active: Boolean)

    // ---- Navegacao entre secoes ----

    fun openSection(anchor: String) {
        AjustesSection.of(anchor)?.let { open(it) }
    }

    fun open(next: AjustesSection) {
        error = ""
        section = next
        refreshSection()
    }

    fun closeSection() {
        section = null
        error = ""
    }


    // ---- Leituras ----

    fun refreshAll() {
        hidden = ShellPrefs.valuesHidden(app) ?: hidden
        theme = ShellPrefs.themePreference(app)
        refreshSection()
    }

    private fun refreshSection() {
        when (section) {
            null -> Unit
            AjustesSection.CONTAS -> readAccounts()
            AjustesSection.CARTOES -> {
                readCards()
                readAccounts()
            }
            AjustesSection.CATEGORIAS -> readCategories()
            AjustesSection.OPEN_FINANCE -> readOpenFinance()
            AjustesSection.PERFIL -> readMe()
            AjustesSection.NOTIFICACOES -> readNotify()
            AjustesSection.VERSAO -> {
                if (apk == null && apkBusy.isEmpty()) checkApk()
                // Voltou da tela "Instalar apps desconhecidos": baixa sozinho, como a web.
                if (installAfterPermission) {
                    installAfterPermission = false
                    installApk()
                }
            }
            AjustesSection.APARENCIA -> Unit
        }
    }

    private fun readAccounts() {
        viewModelScope.launch { accounts.collect(app, graph.accounts.accounts(includeArchived = true), R.string.ajustes_accounts_failed) }
    }

    private fun readCards() {
        viewModelScope.launch { cards.collect(app, graph.cards.cards(), R.string.ajustes_cards_failed) }
    }

    private fun readCategories() {
        viewModelScope.launch { categories.collect(app, graph.categories.categories(includeArchived = true), R.string.ajustes_categories_failed) }
    }

    private fun readMe() {
        viewModelScope.launch {
            me.collect(app, repo.me(), R.string.ajustes_profile_failed)
            if (username == null) username = me.value?.user?.username.orEmpty()
        }
    }

    private fun readOpenFinance() {
        viewModelScope.launch { openFinance.collect(app, repo.openFinance(), R.string.ajustes_open_finance_failed) }
        viewModelScope.launch {
            openFinanceSettings.collect(app, repo.openFinanceSettings(), R.string.ajustes_open_finance_failed)
        }
    }

    /** Releia as listas que o "+ Novo" e Aprovar guardam (contas ativas, cartoes, categorias). */
    private fun refreshShared() {
        drain(graph.accounts.accounts(includeArchived = false))
        drain(graph.accounts.accounts(includeArchived = true))
        drain(graph.cards.cards())
        drain(graph.categories.categories(includeArchived = false))
        drain(graph.categories.categories(includeArchived = true))
    }

    // Le ate o fim: a resposta nova fica guardada para quem abrir depois.
    private fun <T> drain(flow: Flow<Load<T>>) {
        viewModelScope.launch { flow.collect { } }
    }

    fun toggleHidden() {
        hidden = !hidden
        ShellPrefs.saveValuesHidden(app, hidden)
    }

    fun dismissError() {
        error = ""
    }

    fun dismissConfirm() {
        confirm = null
    }

    // ---- Contas ----

    val activeAccounts: List<AccountDto> get() = accounts.value.orEmpty().filter { !it.isArchived }
    val archivedAccounts: List<AccountDto> get() = accounts.value.orEmpty().filter { it.isArchived }

    /** A conta da carteira: a primeira Corretora ativa em reais (pickPortfolioAccountId). */
    val portfolioAccountId: String
        get() = br.financas.app.rules.PortfolioAccount.pickPortfolioAccountId(
            activeAccounts.map { br.financas.app.rules.PortfolioAccount.Account(it.id, it.type, it.currency, it.archivedAt) },
        )

    fun toggleAccountForm() {
        accountFormOpen = !accountFormOpen
    }

    fun changeAccountForm(form: AccountForm) {
        accountForm = form
    }

    fun createAccount() {
        val form = accountForm
        val balance = when (val parsed = Settings.parseBalanceInput(form.initialBalance)) {
            is MoneyInput.Amount -> parsed.value
            MoneyInput.Empty -> java.math.BigDecimal.ZERO
            MoneyInput.Invalid -> {
                error = app.getString(R.string.ajustes_balance_invalid)
                return
            }
        }
        val body = Settings.newAccountBody(form.name, form.type, form.institution, balance)
        write(R.string.ajustes_account_create_failed, { repo.createAccount(body) }) {
            accountForm = AccountForm()
            accountFormOpen = false
            changed(app.getString(R.string.ajustes_account_created, form.name))
        }
    }

    fun openEditAccount(account: AccountDto) {
        editingAccount = account
        editAccountForm = AccountForm(
            name = account.name,
            institution = account.institution.orEmpty(),
            initialBalance = moneyInputValue(account.initialBalance ?: java.math.BigDecimal.ZERO),
        )
        error = ""
    }

    fun changeEditAccount(form: AccountForm) {
        editAccountForm = form
    }

    fun closeEditAccount() {
        if (!busy) editingAccount = null
    }

    fun saveEditAccount() {
        val account = editingAccount ?: return
        val form = editAccountForm
        val balance = when (val parsed = Settings.parseBalanceInput(form.initialBalance)) {
            is MoneyInput.Amount -> parsed.value
            MoneyInput.Empty -> java.math.BigDecimal.ZERO
            MoneyInput.Invalid -> {
                error = app.getString(R.string.ajustes_balance_invalid)
                return
            }
        }
        val body = linkedMapOf<String, Any?>("name" to form.name, "institution" to form.institution, "initial_balance" to balance)
        write(R.string.ajustes_account_update_failed, { repo.updateAccount(account.id, body) }) {
            editingAccount = null
            changed(app.getString(R.string.ajustes_account_updated, form.name))
        }
    }

    fun makeDefault(account: AccountDto) {
        write(R.string.ajustes_default_failed, { repo.updateAccount(account.id, mapOf("is_default" to true)) }) {
            changed(app.getString(R.string.ajustes_default_done, account.name))
        }
    }

    fun askLink(account: AccountDto) {
        confirm = ConfirmRequest(
            app.getString(R.string.ajustes_link_title, account.name),
            app.getString(R.string.ajustes_link_message),
            app.getString(R.string.ajustes_link_confirm),
        ) {
            write(R.string.ajustes_link_failed, { repo.updateAccount(account.id, mapOf("type" to "BROKERAGE")) }) {
                changed(app.getString(R.string.ajustes_link_done, account.name))
            }
        }
    }

    fun askUnlink(account: AccountDto) {
        confirm = ConfirmRequest(
            app.getString(R.string.ajustes_unlink_title, account.name),
            app.getString(R.string.ajustes_unlink_message),
            app.getString(R.string.ajustes_unlink_confirm),
        ) {
            write(R.string.ajustes_unlink_failed, { repo.updateAccount(account.id, mapOf("type" to "CHECKING")) }) {
                changed(app.getString(R.string.ajustes_unlink_done, account.name))
            }
        }
    }

    fun askArchiveAccount(account: AccountDto) {
        confirm = ConfirmRequest(
            app.getString(R.string.ajustes_archive_title, account.name),
            app.getString(R.string.ajustes_archive_message),
            app.getString(R.string.ajustes_archive_confirm),
        ) {
            write(R.string.ajustes_archive_failed, { repo.archiveAccount(account.id) }) {
                changed(app.getString(R.string.ajustes_archive_done, account.name))
            }
        }
    }

    fun reactivateAccount(account: AccountDto) {
        write(R.string.ajustes_reactivate_failed, { repo.updateAccount(account.id, mapOf("archived_at" to null)) }) {
            changed(app.getString(R.string.ajustes_reactivate_done, account.name))
        }
    }

    // ---- Cartoes ----

    /** As contas do debito: as do banco (a Corretora e da carteira). */
    val debitAccounts: List<AccountDto> get() = activeAccounts.filter { !it.isBrokerage }

    fun accountName(id: String?): String =
        activeAccounts.firstOrNull { it.id == id }?.name ?: app.getString(R.string.ajustes_archived_account)

    fun toggleCardForm() {
        cardFormOpen = !cardFormOpen
    }

    fun changeCardForm(form: CardFormState) {
        cardForm = form
    }

    /** O vencimento digitado preenche o fechamento (7 dias antes). */
    fun changeDueDay(text: String) {
        cardForm = cardForm.copy(dueDay = text, closingDay = Settings.suggestedClosingDay(text))
    }

    private fun payloadOf(form: CardFormState, withAutopay: Boolean) = CardFunctions.cardFormPayload(
        CardForm(
            name = form.name,
            functions = form.functions,
            debitAccountId = form.debitAccountId,
            dueDay = form.dueDay,
            closingDay = form.closingDay,
            autopayAccountId = if (withAutopay) form.autopayAccountId else null,
            autopayAccountIdSet = withAutopay,
        ),
    )

    fun createCard() {
        val result = payloadOf(cardForm, withAutopay = true)
        val payload = result.payload
        if (payload == null) {
            error = result.error.orEmpty()
            return
        }
        write(R.string.ajustes_card_create_failed, { repo.createCard(payload) }) {
            cardForm = CardFormState()
            cardFormOpen = false
            changed(app.getString(R.string.ajustes_card_created, payload["name"].toString()))
        }
    }

    fun openEditCard(card: CreditCardDto) {
        // Um cartao so debito guarda 1 nas datas (041): o formulario abre vazio.
        val credit = card.creditEnabled
        editingCard = card
        editCardForm = CardFormState(
            name = card.name,
            functions = CardFunctions.cardFunctionOf(br.financas.app.rules.Card(card.id, card.name, card.creditEnabled, card.debitAccountId)),
            dueDay = if (credit) card.dueDay?.toString().orEmpty() else "",
            closingDay = if (credit) card.closingDay?.toString().orEmpty() else "",
            debitAccountId = card.debitAccountId.orEmpty(),
        )
        error = ""
    }

    fun changeEditCard(form: CardFormState) {
        editCardForm = form
    }

    fun closeEditCard() {
        if (!busy) editingCard = null
    }

    /** As contas do debito na edicao: a atual, mesmo arquivada, fica como opcao. */
    fun editDebitAccounts(card: CreditCardDto): List<Pair<String, String>> {
        val list = debitAccounts.map { it.id to it.name }
        val current = card.debitAccountId
        return if (!current.isNullOrEmpty() && list.none { it.first == current }) listOf(current to accountName(current)) + list else list
    }

    fun saveEditCard() {
        val card = editingCard ?: return
        // Sem autopay_account_id: o debito automatico se muda na lista; tirar o credito o desliga no servidor.
        val result = payloadOf(editCardForm, withAutopay = false)
        val payload = result.payload
        if (payload == null) {
            error = result.error.orEmpty()
            return
        }
        write(R.string.ajustes_card_update_failed, { repo.updateCard(card.id, payload) }) {
            editingCard = null
            changed(app.getString(R.string.ajustes_card_updated, payload["name"].toString()))
        }
    }

    fun setAutopay(card: CreditCardDto, accountId: String) {
        if (savingAutopayId != null) return
        savingAutopayId = card.id
        error = ""
        graph.appScope.launch {
            val result = repo.updateCard(card.id, mapOf("autopay_account_id" to accountId.ifEmpty { null }))
            savingAutopayId = null
            val failure = planWriteError(app, result, R.string.ajustes_autopay_failed)
            if (failure == null) {
                val account = activeAccounts.firstOrNull { it.id == accountId }
                changed(Settings.autopayNotice(card.name, card.dueDay, account?.name))
            } else {
                failed(failure)
            }
        }
    }

    fun askDeleteCard(card: CreditCardDto) {
        confirm = ConfirmRequest(
            app.getString(R.string.ajustes_card_delete_title, card.name),
            app.getString(R.string.ajustes_card_delete_message),
            app.getString(R.string.ajustes_card_delete_confirm),
        ) {
            write(R.string.ajustes_card_delete_failed, { repo.deleteCard(card.id) }) {
                changed(app.getString(R.string.ajustes_card_deleted, card.name))
            }
        }
    }

    // ---- Categorias ----

    val rootCategories: List<CategoryDto> get() = categories.value.orEmpty().filter { !it.isArchived && it.parentId.isNullOrEmpty() }

    fun toggleCategoryForm() {
        categoryFormOpen = !categoryFormOpen
    }

    fun changeCategoryForm(form: CategoryForm) {
        categoryForm = form
    }

    fun createCategory() {
        val form = categoryForm
        val body = linkedMapOf<String, Any?>("name" to form.name, "kind" to form.kind)
        if (form.parentId.isNotEmpty()) body["parent_id"] = form.parentId
        write(R.string.ajustes_category_create_failed, { repo.createCategory(body) }) {
            categoryForm = CategoryForm()
            categoryFormOpen = false
            changed(null)
        }
    }

    fun startCategoryEdit(category: CategoryDto) {
        editingCategoryId = category.id
        categoryEdit = CategoryForm(name = category.name, kind = category.kind)
    }

    fun changeCategoryEdit(form: CategoryForm) {
        categoryEdit = form
    }

    fun cancelCategoryEdit() {
        editingCategoryId = ""
    }

    fun saveCategoryEdit(category: CategoryDto) {
        val form = categoryEdit
        write(R.string.ajustes_category_update_failed, { repo.updateCategory(category.id, mapOf("name" to form.name, "kind" to form.kind)) }) {
            editingCategoryId = ""
            changed(null)
        }
    }

    fun askArchiveCategory(category: CategoryDto) {
        confirm = ConfirmRequest(
            app.getString(R.string.ajustes_category_archive_title, category.name),
            app.getString(R.string.ajustes_category_archive_message),
            app.getString(R.string.ajustes_archive_confirm),
        ) {
            write(R.string.ajustes_category_archive_failed, { repo.archiveCategory(category.id) }) { changed(null) }
        }
    }

    fun reactivateCategory(category: CategoryDto) {
        write(R.string.ajustes_category_reactivate_failed, { repo.updateCategory(category.id, mapOf("archived_at" to null)) }) { changed(null) }
    }

    // ---- Avisos do celular ----

    // ---- Open Finance (043): o estado e "Atualizar"; conectar e mapear ficam no computador ----

    fun syncOpenFinance(item: OpenFinanceItemDto) {
        if (busy) return
        syncingItemId = item.id
        write(R.string.ajustes_open_finance_sync_failed, { repo.syncOpenFinance(item.id) }, onFail = { syncingItemId = null }) { body ->
            syncingItemId = null
            openFinance.value = body
            notice(
                OpenFinanceRules.syncSummary(
                    body.result?.counts, body.result?.removed, body.result?.autoRecorded, body.result?.investments,
                ),
            )
        }
    }

    private fun saveOpenFinanceSettings(body: Map<String, Any?>, message: String) {
        write(R.string.ajustes_open_finance_settings_failed, { repo.updateOpenFinanceSettings(body) }) { saved ->
            openFinanceSettings.value = saved
            notice(message)
        }
    }

    /** "Busca automatica" (0 desliga) e "Trazer pendentes": no servidor, como na web. */
    fun setOpenFinanceSyncHours(hours: Int) = saveOpenFinanceSettings(
        mapOf("sync_hours" to hours),
        if (hours == 0) app.getString(R.string.ajustes_open_finance_auto_off)
        else app.getString(R.string.ajustes_open_finance_auto_on, hours),
    )

    fun setOpenFinanceIncludePending(value: Boolean) = saveOpenFinanceSettings(
        mapOf("include_pending" to value),
        app.getString(if (value) R.string.ajustes_open_finance_pending_on else R.string.ajustes_open_finance_pending_off),
    )

    // ---- Aparencia ----

    /** Grava em ShellPrefs e a Activity se refaz no tema novo ([onApplied]): telas e barras do sistema. */
    fun chooseTheme(preference: String, onApplied: () -> Unit) {
        if (preference == theme) return
        ShellPrefs.saveThemePreference(app, preference)
        theme = preference
        onApplied()
    }

    // ---- Perfil ----

    fun changeUsername(text: String) {
        username = text
    }

    val canSaveUsername: Boolean get() = Settings.canSaveUsername(username.orEmpty(), me.value?.user?.username)

    fun saveUsername() {
        val trimmed = username.orEmpty().trim()
        profileMessage = null
        if (busy) return
        busy = true
        graph.appScope.launch {
            val result = repo.saveUsername(trimmed)
            busy = false
            val failure = planWriteError(app, result, R.string.ajustes_username_failed)
            if (failure == null) {
                profileMessage = true to app.getString(R.string.ajustes_username_saved)
                username = trimmed
                ShellEvents.emitDataChanged()
                readMe()
            } else {
                profileMessage = false to failure
            }
        }
    }

    fun dismissProfileMessage() {
        profileMessage = null
    }

    /**
     * "Sair": apaga a sessao do APK (o envio da fila para; os itens ficam, de cada usuario) e as
     * copias guardadas; [onDone] leva ao login.
     */
    fun signOut(onDone: () -> Unit) {
        Outbox.signOut(app)
        graph.cache.clear()
        onDone()
    }
    // ---- Notificacoes dos bancos ----

    private fun readNotify() {
        viewModelScope.launch {
            val (status, rows) = withContext(Dispatchers.IO) {
                parseStatus(NotifyAccess.status(app)) to parseCaptured(NotifyAccess.latestItems(app, LATEST))
            }
            notify = status
            captured = rows
        }
    }

    fun reloadNotify() = readNotify()

    fun openAccessSettings() = NotifyAccess.openAccessSettings(app)

    fun openAppDetails() = NotifyAccess.openAppDetails(app)

    fun setCapture(on: Boolean) {
        if (notify?.captureOn == on) return
        NotifySettings.setCapture(app, on, System.currentTimeMillis())
        readNotify()
        notice(app.getString(if (on) R.string.ajustes_capture_on else R.string.ajustes_capture_off))
    }

    fun export(json: Boolean) {
        val name = if (json) "export-json" else "export-text"
        if (notifyBusy.isNotEmpty()) return
        notifyBusy = name
        viewModelScope.launch {
            val outcome = withContext(Dispatchers.IO) {
                try {
                    Result.success(NotifyAccess.export(app, json).optInt("count"))
                } catch (error: NotifyAccess.ExportException) {
                    Result.failure(error)
                }
            }
            notifyBusy = ""
            outcome.onSuccess { count -> notice(app.getString(R.string.ajustes_export_done, NotifyTexts.countLabel(count.toLong()))) }
            outcome.onFailure { error = it.message ?: app.getString(R.string.ajustes_failed) }
        }
    }

    fun askClearCapture() {
        val status = notify ?: return
        confirm = ConfirmRequest(
            app.getString(R.string.ajustes_clear_title),
            app.getString(
                R.string.ajustes_clear_message,
                NotifyTexts.countLabel(status.total.toLong()),
                app.getString(if (status.captureOn) R.string.ajustes_capture_word_on else R.string.ajustes_capture_word_off),
            ),
            app.getString(R.string.ajustes_clear_confirm),
        ) {
            viewModelScope.launch {
                val next = withContext(Dispatchers.IO) { parseStatus(NotifyAccess.clear(app)) }
                notify = next
                captured = emptyList()
                notice(app.getString(R.string.ajustes_cleared))
            }
        }
    }

    // ---- Versao do app (so o APK) ----

    val apkVersion: String get() = BuildConfig.VERSION_NAME

    private fun baseUrl(): String? = Session.load(app)?.baseUrl?.trimEnd('/')?.takeIf { it.startsWith("https://") }

    fun checkApk() {
        val base = baseUrl()
        if (base == null) {
            apkCheck = ApkUpdateTexts.Message(ApkUpdateTexts.Tone.DANGER, app.getString(R.string.ajustes_apk_no_server))
            return
        }
        if (apkBusy.isNotEmpty()) return
        apkBusy = "check"
        viewModelScope.launch {
            val outcome = withContext(Dispatchers.IO) {
                try {
                    Result.success(ApkUpdater.latestState(app, base))
                } catch (error: Exception) {
                    Result.failure<JSONObject>(Exception(ApkUpdater.failureMessage(error, app.getString(R.string.ajustes_apk_check_failed))))
                }
            }
            apkBusy = ""
            outcome.onSuccess { state ->
                apk = parseApk(state)
                apkCheck = if (apk?.newer == true) null else ApkUpdateTexts.Message(ApkUpdateTexts.Tone.SUCCESS, app.getString(R.string.ajustes_apk_latest))
            }
            outcome.onFailure { apkCheck = ApkUpdateTexts.Message(ApkUpdateTexts.Tone.DANGER, it.message.orEmpty()) }
        }
    }

    fun installApk() {
        val base = baseUrl() ?: return
        if (apkBusy.isNotEmpty()) return
        val early = ApkUpdater.installPrecheck(app)
        if (early != null) {
            val status = early.optString("status")
            installAfterPermission = status == "needs-permission"
            apkInstall = ApkUpdateTexts.installStatusMessage(status)
            return
        }
        apkBusy = "install"
        // A vez do download ja e nossa (installPrecheck): o escopo do app garante que installNow
        // roda e a solta, mesmo se a tela fechar no meio.
        graph.appScope.launch {
            val result = withContext(Dispatchers.IO) {
                try {
                    ApkUpdater.installNow(app, base).optString("status") to null
                } catch (error: Exception) {
                    "error" to ApkUpdater.failureMessage(error, app.getString(R.string.ajustes_apk_install_failed))
                }
            }
            apkBusy = ""
            apkInstall = ApkUpdateTexts.installStatusMessage(result.first, result.second)
        }
    }

    // ---- Comum ----

    private fun <T> write(failure: Int, call: suspend () -> InboxWrite<T>, onFail: () -> Unit = {}, done: (T) -> Unit) {
        if (busy) return
        busy = true
        error = ""
        graph.appScope.launch {
            val result = call()
            busy = false
            val message = planWriteError(app, result, failure)
            if (message == null) {
                @Suppress("UNCHECKED_CAST")
                done((result as InboxWrite.Done<T>).value)
            } else {
                onFail()
                failed(message)
            }
        }
    }

    private fun failed(message: String) {
        if (cleared) Toast.makeText(app, message, Toast.LENGTH_LONG).show() else error = message
    }

    private fun notice(message: String) {
        if (cleared) Toast.makeText(app, message, Toast.LENGTH_SHORT).show() else _notices.tryEmit(message)
    }

    private fun changed(message: String?) {
        ShellEvents.emitDataChanged()
        if (message != null) notice(message)
        if (!cleared) {
            refreshShared()
            refreshSection()
        }
    }

    companion object {
        private const val LATEST = 20

        /** NotifyAccess.status() lido. */
        fun parseStatus(json: JSONObject): NotifyTexts.NotifyStatus {
            val apps = json.optJSONArray("apps") ?: JSONArray()
            return NotifyTexts.NotifyStatus(
                granted = json.optBoolean("granted"),
                captureOn = json.optBoolean("captureOn"),
                captureSince = json.optLong("captureSince"),
                connectedAt = json.optLong("connectedAt"),
                disconnectedAt = json.optLong("disconnectedAt"),
                acceptsShell = json.optBoolean("acceptsShell"),
                sdk = json.optInt("sdk"),
                installer = if (json.isNull("installer")) null else json.optString("installer"),
                apps = (0 until apps.length()).mapNotNull { index ->
                    apps.optJSONObject(index)?.let {
                        NotifyTexts.AppStatus(it.optString("package"), it.optString("label"), it.optBoolean("installed"), it.optLong("count"), it.optLong("lastPostedAt"))
                    }
                },
                total = json.optInt("total"),
            )
        }

        fun parseCaptured(items: JSONArray): List<CapturedRow> = (0 until items.length()).mapNotNull { index ->
            items.optJSONObject(index)?.let {
                CapturedRow(
                    key = it.optString("dedupKey", index.toString()),
                    app = it.optString("app"),
                    postedAt = it.optLong("postedAt"),
                    title = if (it.isNull("title")) "" else it.optString("title"),
                    text = if (it.isNull("text")) "" else it.optString("text"),
                    summary = it.optBoolean("groupSummary"),
                    active = it.optString("via") == "active",
                )
            }
        }

        fun parseApk(json: JSONObject): ApkUpdateTexts.ApkState {
            val latest = json.optJSONObject("latest")?.let {
                ApkUpdateTexts.Latest(it.optLong("versionCode"), if (it.isNull("versionName")) null else it.optString("versionName"))
            }
            return ApkUpdateTexts.ApkState(json.optBoolean("newer"), latest)
        }
    }
}
