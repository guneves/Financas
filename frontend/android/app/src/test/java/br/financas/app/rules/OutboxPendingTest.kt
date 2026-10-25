// Port: mudou um, muda o outro, com um teste de cada lado.
// Os casos de frontend/src/lib/outboxRules.test.js que tocam sendOrder, pendingAccountDeltas,
// applyPendingToAccounts, pendingAsTransactions, countByStatus e applyPendingToHome, na mesma ordem; o nome do
// teste do node vai no comentario de cada um. Os de envio (endpointFor, buildItem, outcomeOf,
// deliveredDiffers...) estao em outbox/OutboxRulesTest.java.
package br.financas.app.rules

import br.financas.app.rules.OutboxPending.NEEDS_ATTENTION
import br.financas.app.rules.OutboxPending.PENDING
import br.financas.app.rules.OutboxPending.applyPendingToAccounts
import br.financas.app.rules.OutboxPending.applyPendingToHome
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

    // /api/home com os pendentes por cima (proposta home-attention-invoices.md, B1).
    private val homeAccounts = listOf(
        PendingAccount(id = "banco", type = "CHECKING", currency = "BRL", isDefault = true, balance = money("1000"), balanceBrl = money("1000")),
        PendingAccount(id = "poupanca", type = "SAVINGS", currency = "BRL", balance = money("500"), balanceBrl = money("500")),
        PendingAccount(id = "corretora", type = "BROKERAGE", currency = "BRL", balance = money("7000"), balanceBrl = money("7000")),
        PendingAccount(id = "dolar", type = "CHECKING", currency = "USD", balance = money("10"), balanceBrl = money("50")),
    )

    private fun home() = HomeData(
        consolidatedBalance = money("1550"),
        accounts = homeAccounts,
        summary = HomeSummary(income = money("100"), expense = money("40"), result = money("60")),
        flow = listOf(
            HomeMonth(month = "2026-09", balance = money("1490")),
            HomeMonth(month = "2026-10", income = money("100"), expense = money("40"), net = money("60"), balance = money("1550")),
        ),
    )

    private fun assertMoney(expected: String, actual: BigDecimal) = assertEquals(0, money(expected).compareTo(actual))

    // node: 'operacao e provento pendentes: nao mexem em conta, nem no extrato, nem no Inicio'
    @Test
    fun pendingInvestmentItemsTouchNoAccountRowOrHome() {
        val buy = item("INVESTMENT", PendingPayload(accountId = null, date = null))
        val proceed = item("PROCEED")
        assertTrue(pendingAccountDeltas(listOf(buy, proceed), defaultAccountId = "main").isEmpty())
        assertTrue(pendingAsTransactions(listOf(buy, proceed), defaultAccountId = "main").isEmpty())
        val base = home()
        assertSame(base, applyPendingToHome(base, listOf(buy, proceed)))
    }

    // node: 'home: sem pendentes volta o mesmo objeto'
    @Test
    fun homeWithoutPendingItemsComesBackTheSame() {
        val base = home()
        assertSame(base, applyPendingToHome(base, emptyList()))
        assertSame(base, applyPendingToHome(base, listOf(item("CARD", PendingPayload(totalAmount = money("90"), date = "2026-10-12")))))
        assertSame(base, applyPendingToHome(base, listOf(item("EXPENSE", PendingPayload(amount = money("5"), date = "2026-10-12"), status = NEEDS_ATTENTION))))
    }

    // node: 'home: despesa pendente baixa a conta, o saldo em contas e entra no Saiu do mes'
    @Test
    fun homePendingExpenseLowersAccountBalanceAndMonth() {
        val result = applyPendingToHome(home(), listOf(
            item("EXPENSE", PendingPayload(amount = money("0.1"), date = "2026-10-12")),
            item("EXPENSE", PendingPayload(amount = money("0.2"), date = "2026-10-13")),
        ))
        assertMoney("1549.7", result.consolidatedBalance)
        assertMoney("999.7", result.accounts.first { it.id == "banco" }.balance!!)
        assertMoney("40.3", result.summary.expense)
        assertMoney("59.7", result.summary.result)
        assertMoney("59.7", result.flow[1].net)
        assertMoney("1549.7", result.flow[1].balance)
        assertMoney("1490", result.flow[0].balance)
        assertTrue(result.balanceEstimated)
    }

    // node: 'home: receita entra inteira; "Pagamento Fatura" mexe no saldo, nao no Saiu'
    @Test
    fun homeIncomeCountsInvoicePaymentOnlyMovesBalance() {
        val result = applyPendingToHome(home(), listOf(
            item("INCOME", PendingPayload(amount = money("30"), date = "2026-10-12", accountId = "poupanca")),
            item("EXPENSE", PendingPayload(amount = money("20"), date = "2026-10-12", category = "Pagamento Fatura Nubank")),
        ))
        assertMoney("130", result.summary.income)
        assertMoney("40", result.summary.expense)
        assertMoney("1560", result.consolidatedBalance)
        assertMoney("1560", result.flow[1].balance)
    }

    // node: 'home: transferencia para a Corretora e aporte, de volta resgate, entre bancos nada'
    @Test
    fun homeTransferToCorretoraIsAporteBackIsResgate() {
        val result = applyPendingToHome(home(), listOf(
            item("TRANSFER", PendingPayload(amount = money("300"), date = "2026-10-12", accountId = "banco", transferAccountId = "corretora")),
            item("TRANSFER", PendingPayload(amount = money("100"), date = "2026-10-13", accountId = "corretora", transferAccountId = "poupanca")),
            item("TRANSFER", PendingPayload(amount = money("50"), date = "2026-10-14", accountId = "banco", transferAccountId = "poupanca")),
        ))
        assertMoney("300", result.summary.invested)
        assertMoney("100", result.summary.redeemed)
        assertMoney("200", result.summary.investmentNet)
        assertMoney("40", result.summary.expense)
        assertMoney("1350", result.consolidatedBalance)
        assertMoney("1350", result.flow[1].balance)
    }

    // node: 'home: linha numa Corretora fica de fora; conta em dolar nao muda o saldo em contas'
    @Test
    fun homeCorretoraRowStaysOutDollarAccountKeepsTotal() {
        val result = applyPendingToHome(home(), listOf(
            item("EXPENSE", PendingPayload(amount = money("70"), date = "2026-10-12", accountId = "corretora")),
            item("EXPENSE", PendingPayload(amount = money("3"), date = "2026-10-12", accountId = "dolar")),
        ))
        assertMoney("43", result.summary.expense)
        assertMoney("1550", result.consolidatedBalance)
        assertMoney("6930", result.accounts.first { it.id == "corretora" }.balance!!)
    }

    // node: 'home: pendente de um mes anterior muda aquele mes e o saldo dali em diante'
    @Test
    fun homeEarlierMonthPendingMovesThatMonthAndLaterBalances() {
        val result = applyPendingToHome(home(), listOf(
            item("EXPENSE", PendingPayload(amount = money("10"), date = "2026-09-30")),
            item("INCOME", PendingPayload(amount = money("1"), date = "2026-08-01")),
            item("EXPENSE", PendingPayload(amount = money("99"), date = "2026-11-01")),
        ))
        assertMoney("10", result.flow[0].expense)
        assertMoney("1481", result.flow[0].balance)
        assertMoney("40", result.flow[1].expense)
        assertMoney("1541", result.flow[1].balance)
        assertMoney("1442", result.consolidatedBalance)
    }
}
