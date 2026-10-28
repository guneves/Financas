// O que o Inicio nativo calcula sobre as respostas, sem Android nem Compose (HomeLogicTest.kt):
// GET /api/home com os pendentes da fila por cima (rules/OutboxPending.applyPendingToHome), as
// contas da faixa, os pedidos de pagamento de fatura e o que o sheet de pagamento mostra. A
// mesma coisa que pages/Dashboard.jsx e components/PayInvoiceSheet.jsx fazem na web.
package br.financas.app.ui.home

import br.financas.app.core.formatCurrency
import br.financas.app.data.AccountDto
import br.financas.app.data.AttentionItemDto
import br.financas.app.data.HomeDto
import br.financas.app.data.NextInvoiceDto
import br.financas.app.rules.AttentionRules
import br.financas.app.rules.HomeData
import br.financas.app.rules.HomeMonth
import br.financas.app.rules.HomeRules
import br.financas.app.rules.HomeSummary
import br.financas.app.rules.OutboxPending
import br.financas.app.rules.PendingAccount
import br.financas.app.rules.PendingItem
import java.math.BigDecimal

/** Uma conta como o Inicio a mostra: o saldo em reais ja com os pendentes (null = sem cambio hoje). */
data class HomeAccount(
    val id: String,
    val name: String,
    val type: String,
    val archived: Boolean,
    val isDefault: Boolean,
    val balanceBrl: BigDecimal?,
    val estimated: Boolean,
    /** A Conta global e a conta em outra moeda: aqui em reais, como as outras. */
    val currency: String = "BRL",
) {
    val isBrokerage: Boolean get() = type == AccountDto.TYPE_BROKERAGE
    val isGlobal: Boolean get() = currency.uppercase() != "BRL"
}

/** GET /api/home com os pendentes por cima: o que o hero, o resumo e os graficos leem. */
data class HomeView(
    val consolidatedBalance: BigDecimal,
    /** Todas as contas (arquivadas e Corretora inclusive), na ordem do servidor. */
    val accounts: List<HomeAccount>,
    val summary: HomeSummary,
    val flow: List<HomeMonth>,
    val estimated: Boolean,
)

/** Uma fatura a pagar: um POST /api/cc-expenses/pay-invoice cada. */
data class PayInvoice(val cardId: String, val invoiceMonth: Int, val invoiceYear: Int, val total: BigDecimal)

/** O sheet "Pagar fatura": titulo, descricao, as faturas (em ordem) e o total. */
data class PayRequest(
    val title: String,
    val description: String,
    val invoices: List<PayInvoice>,
    val total: BigDecimal,
)

object HomeLogic {
    /** O texto do modo privado (MASKED_CURRENCY de lib/privacy.js). */
    const val MASKED_CURRENCY = "R$ ••••••"

    private fun pendingAccount(account: AccountDto) = PendingAccount(
        id = account.id,
        type = account.type,
        balance = account.balance,
        balanceBrl = account.balanceBrl,
        currency = account.currency,
        isDefault = account.isDefault,
    )

    fun homeData(home: HomeDto) = HomeData(
        consolidatedBalance = home.consolidatedBalance,
        accounts = home.accounts.map(::pendingAccount),
        summary = home.summary.rule,
        flow = home.flow.map { it.rule },
    )

    /**
     * O Inicio com os lancamentos guardados no aparelho (useHome() na web): as contas, o saldo
     * em contas e cada mes do fluxo, por applyPendingToHome. So os pendentes do usuario da sessao
     * chegam aqui (rules/OutboxItems.forUser).
     */
    fun view(home: HomeDto, pending: List<PendingItem>): HomeView {
        val data = OutboxPending.applyPendingToHome(homeData(home), pending)
        val overlay = data.accounts.associateBy { it.id }
        return HomeView(
            consolidatedBalance = data.consolidatedBalance,
            accounts = home.accounts.map { account ->
                val adjusted = overlay[account.id]
                HomeAccount(
                    id = account.id,
                    name = account.name,
                    type = account.type,
                    archived = account.isArchived,
                    isDefault = account.isDefault,
                    balanceBrl = adjusted?.balanceBrl ?: account.balanceBrl,
                    estimated = adjusted?.balanceEstimated ?: false,
                    currency = account.currency,
                )
            },
            summary = data.summary,
            flow = data.flow,
            estimated = data.balanceEstimated,
        )
    }

    /** A caixa de erro: o de uma acao vence o da leitura (e nenhuma releitura o apaga). */
    fun bannerDetail(actionError: String, loadError: String): String = actionError.ifEmpty { loadError }

    /** As contas ativas (o activeAccounts() da web): as do sheet de pagamento. */
    fun activeAccounts(accounts: List<HomeAccount>): List<HomeAccount> = accounts.filter { !it.archived }

    /** A faixa do hero: as contas ativas da area bancaria (a Corretora fica em Investimentos). */
    fun stripAccounts(accounts: List<HomeAccount>): List<HomeAccount> =
        activeAccounts(accounts).filter { !it.isBrokerage }

    /**
     * Quantos pendentes mexem no saldo (o aviso "Saldo estimado"): despesa, receita e
     * transferencia; compra no cartao, operacao e provento nao.
     */
    fun pendingInBalance(items: List<PendingItem>): Int =
        items.count { it.status == OutboxPending.PENDING && it.kind in OutboxPending.ACCOUNT_KINDS }

    /** Os meses (AAAA-MM) das proximas faturas, sem repetir, em ordem. */
    fun nextInvoiceMonths(invoices: List<NextInvoiceDto>): List<String> =
        invoices.map { AttentionRules.invoiceMonthKey(it.invoiceYear, it.invoiceMonth) }.distinct().sorted()

    /** As proximas faturas ja fechadas: so elas podem ser pagas, uma por cartao. */
    fun payableInvoices(invoices: List<NextInvoiceDto>): List<PayInvoice> =
        invoices.filter { it.payable }.map { PayInvoice(it.cardId, it.invoiceMonth, it.invoiceYear, it.total) }

    /** "Pagar" do aviso de fatura fechada (e do quadro): null quando nao ha o que pagar. */
    fun payableRequest(invoices: List<NextInvoiceDto>): PayRequest? {
        val payable = payableInvoices(invoices)
        val total = payable.fold(BigDecimal.ZERO) { acc, it -> acc + it.total }
        if (payable.isEmpty() || total.signum() <= 0) return null
        return PayRequest(
            title = HomeRules.payableTitle(payable.size),
            description = HomeRules.payableDescription(payable.size),
            invoices = payable,
            total = total,
        )
    }

    /** "Pagar" do aviso de fatura vencida: todas as vencidas; null sem nenhuma. */
    fun overdueRequest(item: AttentionItemDto?): PayRequest? {
        if (item == null || item.kind != AttentionRules.INVOICE_OVERDUE) return null
        val invoices = item.invoices.mapNotNull { invoice ->
            val cardId = invoice.cardId ?: return@mapNotNull null
            val month = invoice.invoiceMonth ?: return@mapNotNull null
            val year = invoice.invoiceYear ?: return@mapNotNull null
            PayInvoice(cardId, month, year, invoice.total ?: BigDecimal.ZERO)
        }
        if (invoices.isEmpty()) return null
        return PayRequest(
            title = HomeRules.overdueTitle(invoices.size),
            description = AttentionRules.overdueDetail(item.rule.invoices),
            invoices = invoices,
            total = item.total ?: BigDecimal.ZERO,
        )
    }

    /**
     * Uma conta na lista "Debitar da conta": "<nome> (padrão) · R$ saldo". Sem o saldo no modo
     * privado, na Corretora (o saldo dela so aparece em Investimentos) e sem cambio hoje.
     */
    fun accountOptionLabel(account: HomeAccount, hidden: Boolean): String {
        val name = account.name + if (account.isDefault) " (padrão)" else ""
        val balance = account.balanceBrl
        return if (hidden || account.isBrokerage || balance == null) name else "$name · ${formatCurrency(balance)}"
    }

    /** O saldo da conta escolhida nao cobre a fatura? Corretora e sem cambio nao se comparam. */
    fun shortfall(account: HomeAccount?, total: BigDecimal): Boolean {
        if (account == null || account.isBrokerage) return false
        val balance = account.balanceBrl ?: return false
        return balance < total
    }

    fun shortfallText(account: HomeAccount, hidden: Boolean): String {
        val amount = if (hidden || account.balanceBrl == null) "" else " (${formatCurrency(account.balanceBrl)})"
        return "O saldo de ${account.name}$amount não cobre a fatura; a conta ficará negativa."
    }
}
