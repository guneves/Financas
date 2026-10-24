// Porte: mudou um, muda o outro, com um teste de cada lado.
// Os casos de frontend/src/lib/portfolioAccount.test.js, na mesma ordem; o nome do teste do
// node vai no comentario de cada um.
package br.financas.app.rules

import br.financas.app.rules.PortfolioAccount.Account
import br.financas.app.rules.PortfolioAccount.CashLink
import br.financas.app.rules.PortfolioAccount.CashLinkError
import br.financas.app.rules.PortfolioAccount.NO_PORTFOLIO_ACCOUNT_MESSAGE
import br.financas.app.rules.PortfolioAccount.PICK_ACCOUNT_MESSAGE
import br.financas.app.rules.PortfolioAccount.cashLinkFromMetadata
import br.financas.app.rules.PortfolioAccount.cashLinkMetadata
import br.financas.app.rules.PortfolioAccount.emptyCashLink
import br.financas.app.rules.PortfolioAccount.pickPortfolioAccountId
import br.financas.app.rules.PortfolioAccount.portfolioAccounts
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class PortfolioAccountTest {
    private val accounts = listOf(
        Account("corrente", "CHECKING", "BRL"),
        Account("antiga", "BROKERAGE", "BRL", archivedAt = "2026-01-01"),
        Account("dolar", "BROKERAGE", "USD"),
        Account("btg", "BROKERAGE", "BRL"),
        Account("xp", "BROKERAGE", "BRL"),
    )

    private fun refused(message: String, block: () -> Unit) =
        assertEquals(message, assertThrows(CashLinkError::class.java) { block() }.message)

    // node: 'only active brokerage accounts in reais are the portfolio, in list order'
    @Test
    fun onlyActiveBrokerageAccountsInReaisAreThePortfolioInListOrder() {
        assertEquals(listOf("btg", "xp"), portfolioAccounts(accounts).map { it.id })
        assertEquals("btg", pickPortfolioAccountId(accounts))
        assertEquals("", pickPortfolioAccountId(listOf(accounts[0])))
        assertEquals("", pickPortfolioAccountId(null))
    }

    // node: 'a new operation comes out of an account by default'
    @Test
    fun aNewOperationComesOutOfAnAccountByDefault() {
        assertEquals(true, emptyCashLink().enabled)
        assertEquals(mapOf("cash_account_id" to "btg"), cashLinkMetadata(emptyCashLink().copy(accountId = "btg")))
    }

    // node: 'the flag sends null, never an absent key the backend would fill in'
    @Test
    fun theFlagSendsNullNeverAnAbsentKey() {
        assertEquals(mapOf("cash_account_id" to null), cashLinkMetadata(CashLink(false, "btg", false)))
    }

    // node: 'a new operation without a portfolio account is refused, even with the flag'
    @Test
    fun aNewOperationWithoutAPortfolioAccountIsRefusedEvenWithTheFlag() {
        refused(NO_PORTFOLIO_ACCOUNT_MESSAGE) { cashLinkMetadata(CashLink(true, "", true)) }
        refused(NO_PORTFOLIO_ACCOUNT_MESSAGE) { cashLinkMetadata(CashLink(false, "", true)) }
    }

    // node: 'editing an old operation is not blocked by the missing account'
    @Test
    fun editingAnOldOperationIsNotBlockedByTheMissingAccount() {
        assertEquals(mapOf("cash_account_id" to null), cashLinkMetadata(CashLink(false, "", true), editing = true))
    }

    // node: 'linked with no account chosen asks for one'
    @Test
    fun linkedWithNoAccountChosenAsksForOne() {
        refused(PICK_ACCOUNT_MESSAGE) { cashLinkMetadata(CashLink(true, "", false)) }
    }

    // node: 'reading the saved link back'
    @Test
    fun readingTheSavedLinkBack() {
        assertEquals(CashLink(true, "btg", false), cashLinkFromMetadata(mapOf("cash_account_id" to " btg ")))
        assertEquals(false, cashLinkFromMetadata(emptyMap()).enabled)
    }
}
