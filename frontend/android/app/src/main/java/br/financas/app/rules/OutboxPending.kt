// Port: mudou um, muda o outro, com um teste de cada lado.
// Par: frontend/src/lib/outboxRules.js (testes em outboxRules.test.js), so as regras do saldo
// com pendentes: pendingAccountDeltas, applyPendingToAccounts, pendingAsTransactions,
// applyPendingToHome e countByStatus (e o sendOrder, o toCents e o amountOf que elas usam). As regras de envio
// estao em outbox/OutboxRules.java. Aqui: OutboxPendingTest.kt, os mesmos casos na mesma ordem.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import java.math.BigDecimal
import java.math.RoundingMode

/**
 * O que estas regras leem do payload de um item da fila (o corpo que a rota recebe).
 * `amount` e o valor de despesa/receita/transferencia; `totalAmount` o da compra no cartao.
 * null e o campo ausente do JS.
 */
data class PendingPayload(
    val amount: BigDecimal? = null,
    val totalAmount: BigDecimal? = null,
    val accountId: String? = null,
    val transferAccountId: String? = null,
    val date: String? = null,
    val category: String? = null,
    val description: String? = null,
)

/** Um item da fila (OutboxStore): kind EXPENSE, INCOME, TRANSFER ou CARD; status pending ou needs_attention. */
data class PendingItem(
    val clientId: String,
    val kind: String,
    val payload: PendingPayload = PendingPayload(),
    val status: String = OutboxPending.PENDING,
    val createdAt: String? = null,
)

/** Uma conta de GET /api/accounts (ou de /api/home), so o que estas regras leem e escrevem. */
data class PendingAccount(
    val id: String,
    /** BROKERAGE e a Corretora: fica fora do saldo em contas e do fluxo do Inicio. */
    val type: String? = null,
    val balance: BigDecimal? = null,
    val balanceBrl: BigDecimal? = null,
    /** null = sem moeda (o JS trata como reais, como "BRL"). */
    val currency: String? = null,
    val isDefault: Boolean = false,
    val balanceEstimated: Boolean = false,
)

/** Um pendente como linha do extrato (pendingAsTransactions); source_type e sempre null. */
data class PendingTransaction(
    val id: String,
    val clientId: String,
    val pending: Boolean = true,
    val pendingStatus: String,
    val amount: BigDecimal,
    val date: String?,
    val category: String,
    val description: String,
    val type: String,
    val accountId: String?,
    val transferAccountId: String?,
    val sourceType: String? = null,
    val createdAt: String?,
)

/** Um mes do `flow` de GET /api/home, em reais. */
data class HomeMonth(
    val month: String,
    val income: BigDecimal = BigDecimal.ZERO,
    val expense: BigDecimal = BigDecimal.ZERO,
    val invested: BigDecimal = BigDecimal.ZERO,
    val redeemed: BigDecimal = BigDecimal.ZERO,
    val othersPaid: BigDecimal = BigDecimal.ZERO,
    val othersReceived: BigDecimal = BigDecimal.ZERO,
    val net: BigDecimal = BigDecimal.ZERO,
    val balance: BigDecimal = BigDecimal.ZERO,
)

/** O `summary` de GET /api/home: o ultimo mes do fluxo com o resultado e os liquidos. */
data class HomeSummary(
    val income: BigDecimal = BigDecimal.ZERO,
    val expense: BigDecimal = BigDecimal.ZERO,
    val result: BigDecimal = BigDecimal.ZERO,
    val invested: BigDecimal = BigDecimal.ZERO,
    val redeemed: BigDecimal = BigDecimal.ZERO,
    val investmentNet: BigDecimal = BigDecimal.ZERO,
    val othersPaid: BigDecimal = BigDecimal.ZERO,
    val othersReceived: BigDecimal = BigDecimal.ZERO,
    val othersNet: BigDecimal = BigDecimal.ZERO,
)

/** O que applyPendingToHome le e escreve de GET /api/home. */
data class HomeData(
    val consolidatedBalance: BigDecimal,
    val accounts: List<PendingAccount>,
    val summary: HomeSummary,
    val flow: List<HomeMonth>,
    val balanceEstimated: Boolean = false,
)

object OutboxPending {
    const val PENDING = "pending"
    const val NEEDS_ATTENTION = "needs_attention"

    /**
     * Ordem de envio: a ordem em que foram lancados (sort estavel, como o do JS). Sem
     * created_at o JS compara "undefined"; aqui tambem.
     */
    /**
     * Os que mexem em conta. Uma operacao ou provento pendente (INVESTMENT, PROCEED) nao mexe: o
     * lancamento ligado na Corretora so existe depois que o servidor grava. ACCOUNT_KINDS do JS.
     */
    val ACCOUNT_KINDS = setOf("EXPENSE", "INCOME", "TRANSFER")

    fun sendOrder(items: List<PendingItem>): List<PendingItem> =
        items.sortedBy { it.createdAt ?: "undefined" }

    /**
     * Centavos inteiros, metade para cima, em decimal exato (o mesmo que OutboxRules.cents).
     * Difere do toCents do JS (Math.round sobre ponto flutuante) so com 3+ casas: 1.005 da 101
     * aqui e 100 la; e num negativo com meio centavo exato (-0.005: -1 aqui, 0 la).
     */
    internal fun toCents(value: BigDecimal?): Long =
        (value ?: BigDecimal.ZERO).movePointRight(2).setScale(0, RoundingMode.HALF_UP).longValueExact()

    private fun fromCents(cents: Long): BigDecimal = BigDecimal.valueOf(cents, 2)

    /** O valor do item: total_amount na compra no cartao, amount nos outros; ausente = 0. */
    internal fun amountOf(item: PendingItem): BigDecimal =
        (if (item.kind == "CARD") item.payload.totalAmount else item.payload.amount) ?: BigDecimal.ZERO

    /**
     * Quanto cada conta muda quando os itens pendentes chegarem ao servidor, em centavos.
     * Despesa sai, receita entra, transferencia sai de uma e entra na outra (o consolidado
     * nao muda). Compra no cartao nao toca em conta: vira fatura. Item recusado
     * (needs_attention) nao conta. Uma conta cujos pendentes se anulam (despesa 10 e receita
     * 10) fica no mapa com 0, como no JS; applyPendingToAccounts a deixa como esta.
     */
    fun pendingAccountDeltas(items: List<PendingItem>, defaultAccountId: String = ""): Map<String, Long> {
        val deltas = LinkedHashMap<String, Long>()
        fun add(accountId: String?, cents: Long) {
            if (accountId.isNullOrEmpty() || cents == 0L) return
            deltas[accountId] = (deltas[accountId] ?: 0L) + cents
        }
        items.forEach { item ->
            if (item.status != PENDING) return@forEach
            val cents = toCents(amountOf(item))
            if (cents <= 0) return@forEach
            val account = item.payload.accountId.takeUnless { it.isNullOrEmpty() } ?: defaultAccountId
            when (item.kind) {
                "EXPENSE" -> add(account, -cents)
                "INCOME" -> add(account, cents)
                "TRANSFER" -> {
                    add(item.payload.accountId, -cents)
                    add(item.payload.transferAccountId, cents)
                }
            }
        }
        return deltas
    }

    /**
     * As contas com o saldo ja contando os pendentes (balance_estimated). balance_brl so e
     * ajustado quando a conta e em reais e tem um: sem a cotacao, o pendente nao tem como ser
     * convertido. Nada a mudar devolve a mesma lista (a mesma instancia), como no JS.
     */
    fun applyPendingToAccounts(accounts: List<PendingAccount>, items: List<PendingItem>): List<PendingAccount> {
        if (items.isEmpty()) return accounts
        val defaultAccountId = accounts.firstOrNull { it.isDefault }?.id ?: ""
        val deltas = pendingAccountDeltas(items, defaultAccountId)
        if (deltas.isEmpty()) return accounts
        return accounts.map { account ->
            val cents = deltas[account.id]
            if (cents == null || cents == 0L) return@map account
            val inReais = account.currency.isNullOrEmpty() || account.currency == "BRL"
            account.copy(
                balance = fromCents(toCents(account.balance) + cents),
                balanceEstimated = true,
                balanceBrl = if (inReais && account.balanceBrl != null) {
                    fromCents(toCents(account.balanceBrl) + cents)
                } else {
                    account.balanceBrl
                },
            )
        }
    }

    /**
     * Os pendentes como linhas do extrato, o mais recente primeiro (a compra no cartao nao e
     * linha de extrato). Recusados aparecem tambem: o dono precisa ve-los para resolver.
     */
    fun pendingAsTransactions(items: List<PendingItem>, defaultAccountId: String = ""): List<PendingTransaction> =
        sendOrder(items)
            .filter { it.kind in ACCOUNT_KINDS }
            .map { item ->
                val payload = item.payload
                PendingTransaction(
                    id = "pending:${item.clientId}",
                    clientId = item.clientId,
                    pendingStatus = item.status,
                    amount = amountOf(item),
                    date = payload.date,
                    category = payload.category.takeUnless { it.isNullOrEmpty() }
                        ?: if (item.kind == "TRANSFER") "Transferência" else "",
                    description = payload.description ?: "",
                    type = item.kind,
                    accountId = payload.accountId.takeUnless { it.isNullOrEmpty() }
                        ?: defaultAccountId.takeUnless { it.isEmpty() },
                    transferAccountId = if (item.kind == "TRANSFER") payload.transferAccountId else null,
                    createdAt = item.createdAt,
                )
            }
            .reversed()

    /**
     * GET /api/home com os pendentes por cima (o servidor nao ve a fila do aparelho), em
     * centavos: as contas (applyPendingToAccounts); o saldo em contas + o que muda nas contas
     * em reais que nao sao Corretora; em cada mes do fluxo a despesa/receita inteira (um
     * pendente nunca e dividido; "Pagamento Fatura..." nao e despesa), transferencia banco ->
     * Corretora e aporte, Corretora -> banco resgate, banco -> banco nada, linha numa
     * Corretora de fora, compra no cartao nunca; o saldo de fim de mes anda do mes do
     * pendente em diante; summary e o ultimo mes de novo. Nada a mudar devolve o mesmo objeto.
     */
    fun applyPendingToHome(home: HomeData, items: List<PendingItem>): HomeData {
        val waiting = items.filter { it.status == PENDING && it.kind in ACCOUNT_KINDS }
        if (waiting.isEmpty()) return home
        val accounts = home.accounts
        val defaultAccountId = accounts.firstOrNull { it.isDefault }?.id ?: ""
        fun isPortfolio(id: String?) = accounts.any { it.id == id && it.type == "BROKERAGE" }

        val nextAccounts = applyPendingToAccounts(accounts, waiting)
        val deltas = pendingAccountDeltas(waiting, defaultAccountId)
        var consolidated = toCents(home.consolidatedBalance)
        accounts.forEach { account ->
            val cents = deltas[account.id] ?: 0L
            val inReais = account.currency.isNullOrEmpty() || account.currency == "BRL"
            if (cents != 0L && inReais && account.type != "BROKERAGE" && account.balanceBrl != null) {
                consolidated += cents
            }
        }

        val months = home.flow.map {
            longArrayOf(
                toCents(it.income), toCents(it.expense), toCents(it.invested), toCents(it.redeemed),
                toCents(it.othersPaid), toCents(it.othersReceived), toCents(it.balance),
            )
        }
        val income = 0; val expense = 1; val invested = 2; val redeemed = 3
        val othersPaid = 4; val othersReceived = 5; val balance = 6
        waiting.forEach { item ->
            val cents = toCents(amountOf(item))
            if (cents <= 0) return@forEach
            val payload = item.payload
            val key = (payload.date ?: "").take(7)
            val field: Int?
            val cash: Long
            if (item.kind == "TRANSFER") {
                val fromPortfolio = isPortfolio(payload.accountId)
                val toPortfolio = isPortfolio(payload.transferAccountId)
                if (fromPortfolio == toPortfolio) return@forEach
                field = if (toPortfolio) invested else redeemed
                cash = if (toPortfolio) -cents else cents
            } else {
                val account = payload.accountId.takeUnless { it.isNullOrEmpty() } ?: defaultAccountId
                if (isPortfolio(account)) return@forEach
                cash = if (item.kind == "INCOME") cents else -cents
                val invoicePayment = (payload.category ?: "").startsWith("Pagamento Fatura")
                field = when {
                    item.kind == "INCOME" -> income
                    invoicePayment -> null
                    else -> expense
                }
            }
            home.flow.forEachIndexed { index, month ->
                if (month.month == key && field != null) months[index][field] += cents
                if (month.month >= key) months[index][balance] += cash
            }
        }

        val flow = home.flow.mapIndexed { index, month ->
            val m = months[index]
            month.copy(
                income = fromCents(m[income]),
                expense = fromCents(m[expense]),
                invested = fromCents(m[invested]),
                redeemed = fromCents(m[redeemed]),
                othersPaid = fromCents(m[othersPaid]),
                othersReceived = fromCents(m[othersReceived]),
                net = fromCents(m[income] - m[expense] - m[invested] + m[redeemed] + m[othersReceived] - m[othersPaid]),
                balance = fromCents(m[balance]),
            )
        }
        val last = months.lastOrNull()
        val summary = if (last == null) home.summary else HomeSummary(
            income = fromCents(last[income]),
            expense = fromCents(last[expense]),
            result = fromCents(last[income] - last[expense]),
            invested = fromCents(last[invested]),
            redeemed = fromCents(last[redeemed]),
            investmentNet = fromCents(last[invested] - last[redeemed]),
            othersPaid = fromCents(last[othersPaid]),
            othersReceived = fromCents(last[othersReceived]),
            othersNet = fromCents(last[othersReceived] - last[othersPaid]),
        )
        return home.copy(
            accounts = nextAccounts,
            consolidatedBalance = fromCents(consolidated),
            flow = flow,
            summary = summary,
            balanceEstimated = nextAccounts !== accounts,
        )
    }

    /** Quantos itens em cada estado; pending e needs_attention sempre presentes (0). */
    fun countByStatus(items: List<PendingItem>): Map<String, Int> {
        val counts = linkedMapOf(PENDING to 0, NEEDS_ATTENTION to 0)
        items.forEach { counts[it.status] = (counts[it.status] ?: 0) + 1 }
        return counts
    }
}
