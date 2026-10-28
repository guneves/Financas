// Os mesmos casos de frontend/src/lib/globalAccount.test.js (port: GlobalAccount.kt).
package br.financas.app.rules

import br.financas.app.core.NBSP
import br.financas.app.core.formatForeignCurrency
import br.financas.app.core.formatSignedForeignCurrency
import br.financas.app.data.AccountDto
import br.financas.app.data.TransactionDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

class GlobalAccountTest {
    private val wise = "wise"
    private val btg = "btg"
    private val names = mapOf(wise to "Wise", btg to "BTG conta corrente")

    private fun tx(id: String, type: String, account: String, amount: String, to: String? = null, received: String? = null) =
        TransactionDto(
            id = id, type = type, accountId = account, transferAccountId = to, amount = BigDecimal(amount),
            transferAmount = received?.let(::BigDecimal),
        )

    @Test
    fun soAContaEmOutraMoedaEGlobal() {
        assertTrue(GlobalAccount.isGlobal(AccountDto(id = "a", name = "W", currency = "USD")))
        assertTrue(GlobalAccount.isGlobal(AccountDto(id = "a", name = "W", currency = "usd")))
        assertFalse(GlobalAccount.isGlobal(AccountDto(id = "a", name = "B", currency = "BRL")))
        assertFalse(GlobalAccount.isGlobal(null))
        val accounts = listOf(
            AccountDto(id = "a", name = "A", currency = "BRL"),
            AccountDto(id = "b", name = "B", currency = "USD"),
            AccountDto(id = "c", name = "C", currency = "USD", archivedAt = "2026-10-01"),
        )
        assertEquals(listOf("b"), GlobalAccount.globalAccounts(accounts).map { it.id })
    }

    @Test
    fun oPixDeReaisEntraEmDolarSemODolarAConferir() {
        val rows = listOf(
            tx("1", "TRANSFER", btg, "253.53", to = wise, received = "46.10"),
            tx("2", "TRANSFER", btg, "101.43", to = wise),
            tx("3", "EXPENSE", wise, "9.99"),
            tx("4", "INCOME", wise, "0.50"),
            tx("5", "TRANSFER", wise, "10", to = btg),
            tx("6", "EXPENSE", btg, "70"),
        )
        val statement = GlobalAccount.statement(rows, wise, names)
        assertEquals(listOf("1", "2", "3", "4", "5"), statement.map { it.transaction.id })
        assertEquals(listOf(1, 1, -1, 1, -1), statement.map { it.direction })
        assertEquals(listOf(false, true, false, false, false), statement.map { it.pending })
        assertNull(statement[1].native)
        assertEquals(listOf("BTG conta corrente", "BTG conta corrente", null, null, "BTG conta corrente"), statement.map { it.counterpart })
        val totals = GlobalAccount.totals(statement)
        assertEquals(BigDecimal("46.60"), totals.incoming)
        assertEquals(BigDecimal("19.99"), totals.outgoing)
        assertEquals(1, totals.pending)
        assertEquals(BigDecimal("5.4996"), GlobalAccount.impliedRate(statement[0]))
        assertNull(GlobalAccount.impliedRate(statement[1]))
    }

    @Test
    fun aLinhaEmReaisOSaldoConvertidoOuNadaSemCambio() {
        assertEquals(BigDecimal("559.46"), GlobalAccount.brlHint(AccountDto(id = "w", name = "W", currency = "USD", balanceBrl = BigDecimal("559.46"))))
        assertNull(GlobalAccount.brlHint(AccountDto(id = "w", name = "W", currency = "USD", balanceBrl = null)))
        assertNull(GlobalAccount.brlHint(AccountDto(id = "b", name = "B", currency = "BRL", balanceBrl = BigDecimal("10"))))
    }

    @Test
    fun formatadorEmDolar() {
        assertEquals("US$${NBSP}46,10", formatForeignCurrency(BigDecimal("46.1")))
        assertEquals("US$${NBSP}1.234,50", formatForeignCurrency(BigDecimal("1234.5")))
        assertEquals("−US$${NBSP}9,99", formatSignedForeignCurrency(BigDecimal("9.99"), -1))
        assertEquals("+US$${NBSP}46,10", formatSignedForeignCurrency(BigDecimal("46.1"), 1))
        assertEquals("US$${NBSP}0,00", formatSignedForeignCurrency(BigDecimal.ZERO, 1))
        assertEquals("€${NBSP}1.234,50", formatForeignCurrency(BigDecimal("1234.5"), "EUR"))
    }

    @Test
    fun aPixFromReaisCarriesBothAmounts() {
        // "Pix para ca" (pages/ContaGlobal.jsx): as mesmas frases e o mesmo pedido da web.
        val wise = AccountDto(id = "wise", name = "Wise", currency = "USD")
        val accounts = listOf(
            AccountDto(id = "btg", name = "BTG conta corrente"),
            wise,
            AccountDto(id = "corretora", name = "BTG Corretora", type = "BROKERAGE"),
        )
        assertEquals(listOf("btg"), GlobalAccount.pixSources(accounts).map { it.id })
        val empty = GlobalAccount.PixForm(date = "2026-10-06")
        assertEquals("Escolha a conta em reais de onde saiu o Pix.", GlobalAccount.pixMissing(empty, "USD"))
        val from = empty.copy(accountId = "btg")
        assertEquals("Informe quanto saiu em reais.", GlobalAccount.pixMissing(from, "USD"))
        assertEquals("Informe quanto entrou em USD.", GlobalAccount.pixMissing(from.copy(amount = "253,53"), "USD"))
        assertEquals("Informe quanto entrou em USD.", GlobalAccount.pixMissing(from.copy(amount = "253,53", transferAmount = "0"), "USD"))
        val ready = from.copy(amount = "253,53", transferAmount = "46,10")
        assertEquals("", GlobalAccount.pixMissing(ready, "USD"))
        assertEquals(
            """{"account_id":"btg","transfer_account_id":"wise","amount":253.53,"transfer_amount":46.1,"date":"2026-10-06","description":"Pix para Wise","client_id":"c1"}""",
            br.financas.app.data.JsonBody.encode(GlobalAccount.pixBody(ready, wise, "c1")),
        )
        assertEquals("Câmbio", GlobalAccount.pixBody(ready.copy(description = " Câmbio "), wise, "c1")["description"])
    }
}
