// Port: mudou um, muda o outro, com um teste de cada lado.
// Par: frontend/src/lib/outboxRules.js (testes em outboxRules.test.js), so as regras do saldo
// com pendentes: pendingAccountDeltas, applyPendingToAccounts, pendingAsTransactions e
// countByStatus (e o sendOrder, o toCents e o amountOf que elas usam). As regras de envio
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

/** Uma conta de GET /api/accounts, so o que applyPendingToAccounts le e escreve. */
data class PendingAccount(
    val id: String,
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

object OutboxPending {
    const val PENDING = "pending"
    const val NEEDS_ATTENTION = "needs_attention"

    /**
     * Ordem de envio: a ordem em que foram lancados (sort estavel, como o do JS). Sem
     * created_at o JS compara "undefined"; aqui tambem.
     */
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
            .filter { it.kind != "CARD" }
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

    /** Quantos itens em cada estado; pending e needs_attention sempre presentes (0). */
    fun countByStatus(items: List<PendingItem>): Map<String, Int> {
        val counts = linkedMapOf(PENDING to 0, NEEDS_ATTENTION to 0)
        items.forEach { counts[it.status] = (counts[it.status] ?: 0) + 1 }
        return counts
    }
}
