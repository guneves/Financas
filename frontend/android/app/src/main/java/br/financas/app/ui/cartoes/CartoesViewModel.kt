package br.financas.app.ui.cartoes

import android.app.Application
import android.widget.Toast
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import br.financas.app.R
import br.financas.app.core.MoneyInput
import br.financas.app.core.formatCurrency
import br.financas.app.core.formatDateBR
import br.financas.app.core.getLocalDateString
import br.financas.app.core.moneyInputValue
import br.financas.app.core.parseMoneyInput
import br.financas.app.data.AccountDto
import br.financas.app.data.ApiException
import br.financas.app.data.AppGraph
import br.financas.app.data.AttachmentOwner
import br.financas.app.data.CardInvoiceDto
import br.financas.app.data.CategoryDto
import br.financas.app.data.CcInvoicesDto
import br.financas.app.data.CreditCardDto
import br.financas.app.data.DebitCardDto
import br.financas.app.data.DebitPurchaseDto
import br.financas.app.data.HomeDto
import br.financas.app.data.InboxWrite
import br.financas.app.data.InvoiceCardDto
import br.financas.app.data.InvoicePurchaseDto
import br.financas.app.data.Load
import br.financas.app.data.storedTimeLabel
import br.financas.app.rules.CardRules
import br.financas.app.rules.CategoryOption
import br.financas.app.rules.EntryOptions
import br.financas.app.rules.ExtratoRules
import br.financas.app.rules.OutboxItems
import br.financas.app.rules.PendingItem
import br.financas.app.rules.PurchaseRef
import br.financas.app.rules.ShareForm
import br.financas.app.rules.Sharing
import br.financas.app.ui.components.ConfirmRequest
import br.financas.app.ui.home.HomeLogic
import br.financas.app.ui.lancamentos.AttachmentsState
import br.financas.app.ui.lancamentos.EditTarget
import br.financas.app.ui.lancamentos.PurchaseEditState
import br.financas.app.ui.lancamentos.normalizedShare
import br.financas.app.ui.lancamentos.writeErrorOf
import br.financas.app.ui.nav.ShellEvents
import br.financas.app.ui.theme.ShellPrefs
import br.financas.app.outbox.OutboxStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.math.BigDecimal
import java.util.UUID

/** Uma fatura aguardando o "Pagar" do sheet. */
data class PayTarget(val card: InvoiceCardDto, val invoice: CardInvoiceDto)

/** O sheet "Registrar estorno": aberto por uma compra (cartao travado) ou pelo topo. */
data class RefundForm(
    val purchase: InvoicePurchaseDto?,
    val cardId: String,
    val amount: String,
    val description: String,
    val date: String,
    /** Um por abertura do sheet: o POST repetido devolve o mesmo estorno (idempotente). */
    val clientId: String,
    /** O valor que o sheet propos; trocado pela soma das parcelas se o dono nao mexeu. */
    val estimate: String,
)

/** O sheet "De quem é esta compra?": a compra, o total e a divisao atual (null ate carregar). */
data class ShareTarget(val purchase: InvoicePurchaseDto, val start: CardRules.ShareStart?, val form: ShareForm)

/**
 * Cartoes nativo (05-cartoes.md): as faturas de GET /api/cc-invoices (o servidor soma, marca
 * fechada, atrasada, a proxima e a que se paga), o saldo e as projecoes de /api/home; pagar,
 * estorno, "De quem é?", excluir e comprovantes, tudo so com o servidor.
 */
class CartoesViewModel(application: Application) : AndroidViewModel(application) {

    private val app = application
    private val graph = AppGraph.from(application)
    private val repo = graph.lancamentos

    var data by mutableStateOf<CcInvoicesDto?>(null)
        private set
    var home by mutableStateOf<HomeDto?>(null)
        private set
    var accounts by mutableStateOf<List<AccountDto>>(emptyList())
        private set
    var cards by mutableStateOf<List<CreditCardDto>?>(null)
        private set
    var categories by mutableStateOf<List<CategoryDto>>(emptyList())
        private set
    var pending by mutableStateOf<List<PendingItem>>(emptyList())
        private set
    var hidden by mutableStateOf(ShellPrefs.valuesHidden(application) ?: false)
        private set

    var offline by mutableStateOf(false)
        private set
    var offlineText by mutableStateOf("")
        private set
    var loadError by mutableStateOf("")
        private set
    var actionError by mutableStateOf("")
        private set

    /** Sobrescritas do dono (abrir/fechar); sem entrada, so a fatura "Próxima" fica aberta. */
    var toggled by mutableStateOf<Map<String, Boolean>>(emptyMap())
        private set
    var futureOpen by mutableStateOf<Set<String>>(emptySet())
        private set

    var paying by mutableStateOf<PayTarget?>(null)
        private set
    var payAccountId by mutableStateOf("")
        private set
    var payBusy by mutableStateOf(false)
        private set
    var payError by mutableStateOf("")
        private set

    var refund by mutableStateOf<RefundForm?>(null)
        private set
    var refundBusy by mutableStateOf(false)
        private set
    var refundError by mutableStateOf("")
        private set

    var share by mutableStateOf<ShareTarget?>(null)
        private set
    var shareBusy by mutableStateOf(false)
        private set
    var shareError by mutableStateOf("")
        private set

    /** O bloco "No débito" aberto/fechado por cartao; sem entrada, aberto so no cartao sem fatura. */
    var debitToggled by mutableStateOf<Map<String, Boolean>>(emptyMap())
        private set

    var confirm by mutableStateOf<ConfirmRequest?>(null)
        private set

    val attachments = AttachmentsState(app, repo, viewModelScope, confirm = { confirm = it }, onChanged = ::refreshAll)
    val edit = PurchaseEditState(app, repo, graph.appScope, isCleared = { cleared }, onSaved = { changed(it) })

    private val _notices = MutableSharedFlow<String>(extraBufferCapacity = 8)
    val notices: SharedFlow<String> = _notices.asSharedFlow()

    private var cleared = false

    override fun onCleared() {
        cleared = true
        super.onCleared()
    }

    // ---- O que a tela mostra ----

    /** So os cartoes de credito (041): um so de debito nao tem fatura. */
    val creditCards: List<CreditCardDto> get() = cards.orEmpty().filter { it.creditEnabled }

    val invoiceCards: List<InvoiceCardDto> get() = data?.cards.orEmpty().filter { it.creditEnabled }

    val nearest: Pair<InvoiceCardDto, CardInvoiceDto>? get() = CardRules.nearest(invoiceCards)

    val header: Triple<BigDecimal, BigDecimal, BigDecimal>?
        get() {
            val home = home ?: return null
            val balance = HomeLogic.view(home, pending).consolidatedBalance
            val projections = home.projections
            return Triple(
                balance,
                ExtratoRules.projectionWithPending(projections?.nextMonth ?: home.consolidatedBalance, home.consolidatedBalance, balance),
                ExtratoRules.projectionWithPending(projections?.global ?: home.consolidatedBalance, home.consolidatedBalance, balance),
            )
        }

    fun invoiceKey(card: InvoiceCardDto, invoice: CardInvoiceDto) = "${card.cardId}|${invoice.key}"

    fun isExpanded(card: InvoiceCardDto, invoice: CardInvoiceDto): Boolean {
        val key = invoiceKey(card, invoice)
        return toggled[key] ?: invoice.nearest
    }

    fun toggle(card: InvoiceCardDto, invoice: CardInvoiceDto) {
        val key = invoiceKey(card, invoice)
        toggled = toggled + (key to !isExpanded(card, invoice))
    }

    fun toggleFuture(cardId: String) {
        futureOpen = if (cardId in futureOpen) futureOpen - cardId else futureOpen + cardId
    }

    fun accountName(id: String?): String? = accounts.firstOrNull { it.id == id }?.name

    val debitCards: List<DebitCardDto> get() = data?.debitCards.orEmpty()

    /** Os cartoes so com compras no debito (sem fatura em aberto): um painel cada. */
    val debitOnlyCards: List<DebitCardDto> get() = CardRules.debitOnlyCards(invoiceCards, debitCards)

    fun isDebitOpen(cardId: String, withoutInvoices: Boolean): Boolean = debitToggled[cardId] ?: withoutInvoices

    fun toggleDebit(cardId: String, withoutInvoices: Boolean) {
        debitToggled = debitToggled + (cardId to !isDebitOpen(cardId, withoutInvoices))
    }

    /** As categorias de despesa, para o sheet de edicao. */
    val expenseCategoryOptions: List<CategoryOption>
        get() = EntryOptions.filterCategoryOptions(EntryOptions.buildCategoryOptions(categories), "EXPENSE")

    /** As contas do sheet de pagamento, com os pendentes por cima (o HomeAccount do Inicio). */
    val payAccounts get() = home?.let { HomeLogic.activeAccounts(HomeLogic.view(it, pending).accounts) }.orEmpty()

    // ---- Leituras ----

    fun refreshAll() {
        hidden = ShellPrefs.valuesHidden(app) ?: hidden
        readInvoices()
        readHome()
        readAccounts()
        readCards()
        readCategories()
        readPending()
    }

    private fun readCategories() {
        viewModelScope.launch {
            graph.categories.categories().collect { load ->
                when (load) {
                    is Load.Cached -> if (categories.isEmpty()) categories = load.value
                    is Load.Fresh -> categories = load.value
                    is Load.Failed -> if (categories.isEmpty()) categories = load.cached?.value.orEmpty()
                }
            }
        }
    }

    private fun readInvoices() {
        viewModelScope.launch {
            repo.ccInvoices().collect { load ->
                when (load) {
                    is Load.Cached -> if (data == null) {
                        data = load.value
                        offlineText = app.getString(R.string.lanc_offline, storedTimeLabel(load.storedAt))
                    }
                    is Load.Fresh -> {
                        data = load.value
                        offline = false
                        loadError = ""
                    }
                    is Load.Failed -> {
                        if (data == null) data = load.cached?.value
                        when (val error = load.error) {
                            is ApiException.Network, is ApiException.BadResponse -> {
                                offline = true
                                if (load.cached == null) offlineText = app.getString(R.string.lanc_offline_no_copy)
                            }
                            is ApiException.Unauthorized -> loadError = error.serverMessage ?: app.getString(R.string.data_session_expired)
                            is ApiException.Http -> loadError = error.serverMessage ?: app.getString(R.string.lanc_load_failed)
                        }
                        if (data == null) data = CcInvoicesDto()
                    }
                }
            }
        }
    }

    private fun readHome() {
        viewModelScope.launch {
            graph.home.home().collect { load ->
                when (load) {
                    is Load.Cached -> if (home == null) home = load.value
                    is Load.Fresh -> home = load.value
                    is Load.Failed -> if (home == null) home = load.cached?.value
                }
            }
        }
    }

    private fun readAccounts() {
        viewModelScope.launch {
            graph.accounts.accounts(includeArchived = true).collect { load ->
                when (load) {
                    is Load.Cached -> if (accounts.isEmpty()) accounts = load.value
                    is Load.Fresh -> accounts = load.value
                    is Load.Failed -> Unit
                }
            }
        }
    }

    private fun readCards() {
        viewModelScope.launch {
            graph.cards.cards().collect { load ->
                when (load) {
                    is Load.Cached -> if (cards == null) cards = load.value
                    is Load.Fresh -> cards = load.value
                    is Load.Failed -> if (cards == null) cards = load.cached?.value ?: emptyList()
                }
            }
        }
    }

    private fun readPending() {
        viewModelScope.launch {
            pending = withContext(Dispatchers.IO) {
                OutboxItems.forUser(OutboxStore.get(app).all().map { it.toString() }, graph.sessionUserId())
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

    // ---- Pagar ----

    fun openPay(card: InvoiceCardDto, invoice: CardInvoiceDto) {
        if (!invoice.closed) return
        payError = ""
        payAccountId = CardRules.suggestedPayAccountId(accounts, card.autopayAccountId)
        paying = PayTarget(card, invoice)
    }

    fun openPayNearest() {
        val (card, invoice) = nearest ?: return
        openPay(card, invoice)
    }

    fun choosePayAccount(id: String) {
        payAccountId = id
    }

    fun closePay() {
        if (!payBusy) paying = null
    }

    /** Um pedido so: o servidor lanca o pagamento e baixa a fatura juntos. */
    fun confirmPay() {
        val target = paying ?: return
        if (payBusy) return
        payBusy = true
        payError = ""
        val accountId = payAccountId.ifEmpty { null }
        graph.appScope.launch {
            val result = repo.payInvoice(target.card.cardId, target.invoice.invoiceMonth, target.invoice.invoiceYear, accountId)
            payBusy = false
            val error = writeErrorOf(app, result, R.string.cartoes_pay_failed)
            if (error == null) {
                paying = null
                changed(CardRules.paidNotice(target.card.cardName, target.invoice, accountId?.let { accountName(it) }))
            } else if (cleared) {
                Toast.makeText(app, error, Toast.LENGTH_LONG).show()
            } else {
                payError = error
            }
        }
    }

    // ---- Estorno ----

    fun openRefund(purchase: InvoicePurchaseDto?, cardId: String?) {
        val estimate = purchase?.let { moneyInputValue(CardRules.refundPrefillAmount(PurchaseRef(it.amount, it.installmentTotal), emptyList())) }.orEmpty()
        refund = RefundForm(
            purchase = purchase,
            cardId = cardId ?: creditCards.firstOrNull()?.id.orEmpty(),
            amount = estimate,
            description = purchase?.let { "Estorno · ${it.description.orEmpty()}" }.orEmpty(),
            date = getLocalDateString(),
            clientId = UUID.randomUUID().toString(),
            estimate = estimate,
        )
        refundError = ""
        // Parcelada: o total e a soma das parcelas (a primeira leva o centavo da divisao).
        if (purchase != null && purchase.installmentTotal > 1) {
            viewModelScope.launch {
                val result = repo.candidates(purchase.id)
                if (result is InboxWrite.Done) {
                    val total = moneyInputValue(CardRules.refundPrefillAmount(PurchaseRef(purchase.amount, purchase.installmentTotal), result.value))
                    val current = refund
                    if (current != null && current.purchase?.id == purchase.id && current.amount == current.estimate) {
                        refund = current.copy(amount = total, estimate = total)
                    }
                }
            }
        }
    }

    fun changeRefund(form: RefundForm) {
        refund = form
    }

    fun closeRefund() {
        if (!refundBusy) refund = null
    }

    fun saveRefund() {
        val form = refund ?: return
        val amount = (parseMoneyInput(form.amount) as? MoneyInput.Amount)?.value
        if (amount == null || amount.signum() <= 0) {
            refundError = app.getString(R.string.cartoes_refund_invalid)
            return
        }
        refundBusy = true
        refundError = ""
        val body = linkedMapOf<String, Any?>(
            "card_id" to form.cardId,
            "amount" to amount,
            "purchase_date" to form.date,
            "description" to form.description.trim(),
        )
        form.purchase?.category?.takeIf { it.isNotEmpty() }?.let { body["category"] = it }
        form.purchase?.id?.let { body["refund_of"] = it }
        body["client_id"] = form.clientId
        graph.appScope.launch {
            val result = repo.createRefund(body)
            refundBusy = false
            val error = writeErrorOf(app, result, R.string.cartoes_refund_failed)
            if (error == null) {
                val created = (result as InboxWrite.Done).value
                refund = null
                changed(CardRules.refundNotice(amount, created.invoiceMonth, created.invoiceYear))
            } else if (cleared) {
                Toast.makeText(app, error, Toast.LENGTH_LONG).show()
            } else {
                refundError = error
            }
        }
    }

    // ---- De quem e ----

    fun openShare(purchase: InvoicePurchaseDto) {
        shareError = ""
        share = ShareTarget(purchase, null, Sharing.shareFormFrom(null))
        viewModelScope.launch {
            when (val result = repo.candidates(purchase.id)) {
                is InboxWrite.Done -> {
                    val start = CardRules.shareStart(result.value)
                    if (share?.purchase?.id == purchase.id) share = ShareTarget(purchase, start, start.form.copy(shareOthersAmount = moneyInputValue(start.form.shareOthersAmount)))
                }
                else -> if (share?.purchase?.id == purchase.id) shareError = writeErrorOf(app, result, R.string.cartoes_share_load_failed).orEmpty()
            }
        }
    }

    fun changeShare(form: ShareForm) {
        share = share?.copy(form = form)
    }

    fun closeShare() {
        if (!shareBusy) share = null
    }

    fun saveShare() {
        val target = share ?: return
        val start = target.start ?: return
        val form = normalizedShare(target.form)
        val message = Sharing.shareFormError(form, start.total)
        if (message.isNotEmpty()) {
            shareError = message
            return
        }
        shareBusy = true
        shareError = ""
        graph.appScope.launch {
            val result = repo.updateShare(target.purchase.id, Sharing.sharePayload(form))
            shareBusy = false
            val error = writeErrorOf(app, result, R.string.cartoes_share_failed)
            if (error == null) {
                share = null
                changed(app.getString(if (form.shareMode.isNullOrEmpty()) R.string.cartoes_share_cleared else R.string.cartoes_share_marked))
            } else if (cleared) {
                Toast.makeText(app, error, Toast.LENGTH_LONG).show()
            } else {
                shareError = error
            }
        }
    }

    fun shareDescription(target: ShareTarget): String {
        val start = target.start ?: return target.purchase.description.orEmpty()
        val total = formatCurrency(start.total)
        val amount = if (start.installments > 1) "$total em ${start.installments} parcelas" else total
        return "${target.purchase.description.orEmpty()} · $amount"
    }

    // ---- Editar categoria e descricao ----

    fun openEdit(purchase: InvoicePurchaseDto, cardName: String) {
        val installment = if (purchase.installmentTotal > 1) " · parcela ${purchase.installmentCurrent}/${purchase.installmentTotal}" else ""
        edit.open(
            EditTarget(
                id = purchase.id,
                debit = false,
                refund = purchase.isRefund,
                subtitle = "$cardName · ${formatCurrency(purchase.amount)}$installment",
                currentDescription = purchase.description,
                currentCategoryId = purchase.categoryId,
                currentCategory = purchase.category,
                installments = purchase.installmentTotal,
                description = purchase.description.orEmpty(),
                categoryId = purchase.categoryId.orEmpty(),
            ),
        )
    }

    fun openDebitEdit(purchase: DebitPurchaseDto, cardName: String) {
        edit.open(
            EditTarget(
                id = purchase.id,
                debit = true,
                refund = false,
                subtitle = "$cardName · ${formatCurrency(purchase.amount)} · ${formatDateBR(purchase.date)}",
                currentDescription = purchase.description,
                currentCategoryId = purchase.categoryId,
                currentCategory = purchase.category,
                installments = 1,
                description = purchase.description.orEmpty(),
                categoryId = purchase.categoryId.orEmpty(),
            ),
        )
    }

    // ---- Excluir e comprovantes ----

    fun askDelete(purchase: InvoicePurchaseDto) {
        val name = purchase.description.orEmpty()
        confirm = if (purchase.isRefund) {
            ConfirmRequest(
                title = app.getString(R.string.cartoes_delete_refund_title, name),
                message = app.getString(R.string.cartoes_delete_refund_message),
                confirmLabel = app.getString(R.string.cartoes_delete_refund_confirm),
            ) { delete(purchase, R.string.cartoes_delete_refund_failed) }
        } else {
            ConfirmRequest(
                title = app.getString(R.string.cartoes_delete_title, name),
                message = CardRules.deletePurchaseMessage(purchase.installmentsOpen, purchase.installmentsPaid),
                confirmLabel = app.getString(R.string.cartoes_delete_confirm),
            ) { delete(purchase, R.string.cartoes_delete_failed) }
        }
    }

    private fun delete(purchase: InvoicePurchaseDto, failure: Int) {
        actionError = ""
        graph.appScope.launch {
            val error = writeErrorOf(app, repo.deletePurchase(purchase.id), failure)
            if (error == null) {
                changed(null)
            } else if (cleared) {
                Toast.makeText(app, error, Toast.LENGTH_LONG).show()
            } else {
                actionError = error
            }
        }
    }

    fun openAttachments(purchase: InvoicePurchaseDto) {
        val amount = if (purchase.installmentTotal > 1) "${purchase.installmentTotal}x de ${formatCurrency(purchase.amount)}" else formatCurrency(purchase.amount)
        attachments.open(
            AttachmentOwner.purchase(purchase.id),
            listOf(purchase.description.orEmpty(), formatDateBR(purchase.purchaseDate), amount).joinToString(" · "),
        )
    }

    fun openDebitAttachments(purchase: DebitPurchaseDto) {
        attachments.open(
            AttachmentOwner.transaction(purchase.id),
            listOf(purchase.description.orEmpty(), formatDateBR(purchase.date), formatCurrency(purchase.amount)).joinToString(" · "),
        )
    }

    private fun changed(message: String?) {
        ShellEvents.emitDataChanged()
        if (message != null) {
            if (cleared) Toast.makeText(app, message, Toast.LENGTH_SHORT).show() else _notices.tryEmit(message)
        }
        if (!cleared) refreshAll()
    }
}
