// Port: mudou um, muda o outro, com um teste de cada lado.
// Os casos de frontend/src/lib/outboxRules.test.js que tocam sendOrder, pendingAccountDeltas,
// applyPendingToAccounts, pendingAsTransactions e countByStatus, na mesma ordem; o nome do
// teste do node vai no comentario de cada um. Os de envio (endpointFor, buildItem, outcomeOf,
// deliveredDiffers...) estao em outbox/OutboxRulesTest.java.
package br.financas.app.rules

import br.financas.app.rules.OutboxPending.NEEDS_ATTENTION
import br.financas.app.rules.OutboxPending.PENDING
import br.financas.app.rules.OutboxPending.applyPendingToAccounts
import br.financas.app.rules.OutboxPending.countByStatus
import br.financas.app.rules.OutboxPending.pendingAccountDeltas
import br.financas.app.rules.OutboxPending.pendingAsTransactions
import br.financas.app.rules.OutboxPending.sendOrder
import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

class OutboxPendingTest {
    private var counter = 0

    // O item() do node: client_id unico, pendente, criado em 2026-10-12T10:00:00.000Z.
    private fun item(
        kind: String,
        payload: PendingPayload = PendingPayload(),
        clientId: String = "id-${counter++}",
        status: String = PENDING,
        createdAt: String = "2026-10-12T10:00:00.000Z",
    ) = PendingItem(clientId = clientId, kind = kind, payload = payload, status = status, createdAt = createdAt)

    private fun money(text: String) = BigDecimal(text)

    // node: 'a fila sai na ordem em que foi lancada'
    @Test
    fun theQueueGoesOutInTheOrderItWasEntered() {
        val late = item("EXPENSE", PendingPayload(amount = money("1")), clientId = "b", createdAt = "2026-10-12T12:00:00.000Z")
        val early = item("EXPENSE", PendingPayload(amount = money("2")), clientId = "a", createdAt = "2026-10-12T09:00:00.000Z")
        assertEquals(listOf("a", "b"), sendOrder(listOf(late, early)).map { it.clientId })
    }

    // node: 'despesa tira da conta, receita poe'
    @Test
    fun anExpenseTakesFromTheAccountAnIncomeAdds() {
        val deltas = pendingAccountDeltas(
            listOf(
                item("EXPENSE", PendingPayload(amount = money("25.9"), accountId = "main")),
                item("INCOME", PendingPayload(amount = money("100"), accountId = "main")),
                item("EXPENSE", PendingPayload(amount = money("10"), accountId = "other")),
            ),
        )
        assertEquals(7410L, deltas["main"])
        assertEquals(-1000L, deltas["other"])
    }

    // node: 'transferencia mexe nas duas contas e deixa o consolidado onde estava'
    @Test
    fun aTransferMovesBothAccountsAndKeepsTheTotal() {
        val accounts = listOf(
            PendingAccount(id = "main", balance = money("1000"), isDefault = true),
            PendingAccount(id = "savings", balance = money("50")),
        )
        val result = applyPendingToAccounts(
            accounts,
            listOf(item("TRANSFER", PendingPayload(amount = money("300"), accountId = "main", transferAccountId = "savings"))),
        )
        assertEquals(0, money("700").compareTo(result[0].balance))
        assertEquals(0, money("350").compareTo(result[1].balance))
        fun total(list: List<PendingAccount>) = list.fold(BigDecimal.ZERO) { acc, account -> acc + account.balance!! }
        assertEquals(0, total(accounts).compareTo(total(result)))
    }

    // node: 'compra no cartao pendente nao toca em nenhuma conta'
    @Test
    fun aPendingCardPurchaseTouchesNoAccount() {
        val accounts = listOf(PendingAccount(id = "main", balance = money("1000"), isDefault = true))
        val result = applyPendingToAccounts(
            accounts,
            listOf(item("CARD", PendingPayload(totalAmount = money("900")))),
        )
        assertSame(accounts, result)
    }

    // node: 'lancamento sem conta cai na conta padrao, como no servidor'
    @Test
    fun anEntryWithoutAccountFallsOnTheDefaultAccount() {
        val accounts = listOf(
            PendingAccount(id = "a", balance = money("10")),
            PendingAccount(id = "main", balance = money("100"), isDefault = true),
        )
        val result = applyPendingToAccounts(accounts, listOf(item("EXPENSE", PendingPayload(amount = money("30")))))
        assertEquals(0, money("10").compareTo(result[0].balance))
        assertEquals(0, money("70").compareTo(result[1].balance))
        assertEquals(true, result[1].balanceEstimated)
    }

    // node: 'item recusado pelo servidor nao entra no saldo estimado'
    @Test
    fun anItemRefusedByTheServerStaysOutOfTheEstimate() {
        val accounts = listOf(PendingAccount(id = "main", balance = money("100"), isDefault = true))
        val result = applyPendingToAccounts(
            accounts,
            listOf(item("EXPENSE", PendingPayload(amount = money("30"), accountId = "main"), status = NEEDS_ATTENTION)),
        )
        assertSame(accounts, result)
    }

    // node: 'centavos nao se perdem na soma'
    @Test
    fun centsAreNotLostInTheSum() {
        val accounts = listOf(
            PendingAccount(id = "main", balance = money("0.3"), balanceBrl = money("0.3"), currency = "BRL", isDefault = true),
        )
        val result = applyPendingToAccounts(
            accounts,
            listOf(
                item("EXPENSE", PendingPayload(amount = money("0.1"), accountId = "main")),
                item("EXPENSE", PendingPayload(amount = money("0.2"), accountId = "main")),
            ),
        )
        assertEquals(0, BigDecimal.ZERO.compareTo(result[0].balance))
        assertEquals(0, BigDecimal.ZERO.compareTo(result[0].balanceBrl))
    }

    // node: 'conta em moeda estrangeira: o saldo convertido nao e estimado sem cotacao'
    @Test
    fun aForeignCurrencyAccountKeepsItsConvertedBalance() {
        val accounts = listOf(PendingAccount(id = "usd", balance = money("100"), balanceBrl = money("550"), currency = "USD"))
        val result = applyPendingToAccounts(accounts, listOf(item("EXPENSE", PendingPayload(amount = money("10"), accountId = "usd"))))
        assertEquals(0, money("90").compareTo(result[0].balance))
        assertEquals(0, money("550").compareTo(result[0].balanceBrl))
    }

    // node: 'sem pendentes a lista de contas volta a mesma (nada a recalcular)'
    @Test
    fun withoutPendingItemsTheSameListComesBack() {
        val accounts = listOf(PendingAccount(id = "main", balance = money("1")))
        assertSame(accounts, applyPendingToAccounts(accounts, emptyList()))
    }

    // node: 'linhas do extrato: mais recente primeiro, sem a compra no cartao'
    @Test
    fun statementRowsNewestFirstWithoutTheCardPurchase() {
        val rows = pendingAsTransactions(
            listOf(
                item("EXPENSE", PendingPayload(amount = money("5"), date = "2026-10-12", category = "Mercado", description = "Pao"), clientId = "a", createdAt = "2026-10-12T09:00:00.000Z"),
                item("CARD", PendingPayload(totalAmount = money("90")), clientId = "b", createdAt = "2026-10-12T09:30:00.000Z"),
                item("TRANSFER", PendingPayload(amount = money("7"), date = "2026-10-12", accountId = "x", transferAccountId = "y"), clientId = "c", createdAt = "2026-10-12T10:00:00.000Z"),
            ),
            defaultAccountId = "main",
        )
        assertEquals(listOf("pending:c", "pending:a"), rows.map { it.id })
        assertEquals("main", rows[1].accountId)
        assertEquals("TRANSFER", rows[0].type)
        assertEquals("y", rows[0].transferAccountId)
        assertTrue(rows.all { it.pending })
    }

    // node: 'contagem por estado'
    @Test
    fun countByState() {
        assertEquals(
            mapOf(PENDING to 2, NEEDS_ATTENTION to 1),
            countByStatus(listOf(item("EXPENSE"), item("EXPENSE"), item("EXPENSE", status = NEEDS_ATTENTION))),
        )
    }
}
