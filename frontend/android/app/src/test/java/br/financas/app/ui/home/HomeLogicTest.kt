package br.financas.app.ui.home

import br.financas.app.data.AccountDto
import br.financas.app.data.ApiJson
import br.financas.app.data.AttentionDto
import br.financas.app.data.HomeDto
import br.financas.app.data.HomeMonthDto
import br.financas.app.data.HomeSummaryDto
import br.financas.app.data.NextInvoiceDto
import br.financas.app.rules.PendingItem
import br.financas.app.rules.PendingPayload
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

class HomeLogicTest {
    private fun money(text: String) = BigDecimal(text)

    private val nbsp = " "

    private val home = HomeDto(
        month = "2026-10",
        consolidatedBalance = money("1500"),
        accounts = listOf(
            AccountDto(id = "main", name = "Itaú", type = "CHECKING", isDefault = true, balance = money("1000"), balanceBrl = money("1000")),
            AccountDto(id = "save", name = "Poupança", type = "SAVINGS", balance = money("500"), balanceBrl = money("500")),
            AccountDto(id = "corr", name = "Corretora", type = "BROKERAGE", balance = money("9000"), balanceBrl = money("9000")),
            AccountDto(id = "old", name = "Antiga", archivedAt = "2026-01-01", balance = money("0"), balanceBrl = money("0")),
            AccountDto(id = "usd", name = "Wise", currency = "USD", balance = money("10"), balanceBrl = null),
        ),
        summary = HomeSummaryDto(income = money("3000"), expense = money("1000"), result = money("2000")),
        flow = listOf(
            HomeMonthDto("2026-09", income = money("2000"), balance = money("1200")),
            HomeMonthDto("2026-10", income = money("3000"), expense = money("1000"), net = money("2000"), balance = money("1500")),
        ),
    )

    private fun expense(amount: String, account: String = "main", status: String = "pending") = PendingItem(
        clientId = "c-$amount",
        kind = "EXPENSE",
        status = status,
        payload = PendingPayload(amount = money(amount), accountId = account, date = "2026-10-12"),
    )

    @Test
    fun withoutPendingItemsTheServerNumbersStay() {
        val view = HomeLogic.view(home, emptyList())
        assertEquals(0, money("1500").compareTo(view.consolidatedBalance))
        assertFalse(view.estimated)
        assertEquals(5, view.accounts.size)
    }

    @Test
    fun aPendingExpenseLowersItsAccountTheBalanceAndTheMonth() {
        val view = HomeLogic.view(home, listOf(expense("100")))
        assertTrue(view.estimated)
        assertEquals(0, money("1400").compareTo(view.consolidatedBalance))
        val main = view.accounts.first { it.id == "main" }
        assertEquals(0, money("900").compareTo(main.balanceBrl))
        assertTrue(main.estimated)
        assertEquals(0, money("1100").compareTo(view.summary.expense))
        assertEquals(0, money("1400").compareTo(view.flow.last().balance))
        // Um recusado nao conta.
        assertFalse(HomeLogic.view(home, listOf(expense("100", status = "needs_attention"))).estimated)
        assertEquals(1, HomeLogic.pendingInBalance(listOf(expense("1"), expense("2", status = "needs_attention"))))
        // Operacao e provento na fila nao fazem do saldo uma estimativa.
        assertEquals(1, HomeLogic.pendingInBalance(listOf(expense("3"), expense("4").copy(kind = "INVESTMENT"), expense("5").copy(kind = "PROCEED"))))
    }

    @Test
    fun theStripHasTheActiveBankingAccountsOnly() {
        val view = HomeLogic.view(home, emptyList())
        // A Conta global fica fora do "Saldo em conta" e do sheet de pagamento (2026-10-30).
        assertEquals(listOf("main", "save"), HomeLogic.stripAccounts(view.accounts).map { it.id })
        assertEquals(listOf("main", "save", "corr"), HomeLogic.activeAccounts(view.accounts).map { it.id })
        assertTrue(HomeLogic.hasGlobalAccount(view.accounts))
        assertFalse(HomeLogic.hasGlobalAccount(view.accounts.filter { !it.isGlobal }))
        // Sem cambio hoje: null ("sem câmbio hoje").
        assertNull(view.accounts.first { it.id == "usd" }.balanceBrl)
    }

    private fun invoice(card: String, month: Int, payable: Boolean, total: String) = NextInvoiceDto(
        cardId = card, cardName = card, invoiceMonth = month, invoiceYear = 2026, payable = payable, closed = payable, total = money(total),
    )

    @Test
    fun theNextInvoicesGiveTheMonthsAndThePayableRequest() {
        val invoices = listOf(invoice("nu", 11, true, "300"), invoice("itau", 12, false, "200"), invoice("bb", 11, true, "50.5"))
        assertEquals(listOf("2026-11", "2026-12"), HomeLogic.nextInvoiceMonths(invoices))
        val request = HomeLogic.payableRequest(invoices)!!
        assertEquals("Pagar faturas", request.title)
        assertEquals("2 faturas fechadas, a próxima de cada cartão.", request.description)
        assertEquals(listOf("nu", "bb"), request.invoices.map { it.cardId })
        assertEquals(0, money("350.5").compareTo(request.total))
        assertNull(HomeLogic.payableRequest(listOf(invoice("itau", 12, false, "200"))))
        assertNull(HomeLogic.payableRequest(listOf(invoice("nu", 11, true, "0"))))
    }

    @Test
    fun theOverdueRequestPaysEveryOverdueInvoice() {
        val json = """
            {"today":"2026-10-20","items":[{"key":"fatura-vencida:nu|2026-10","kind":"INVOICE_OVERDUE","tone":"danger",
             "total":420.5,"item_count":4,"invoices":[
               {"card_id":"nu","card_name":"Nubank","invoice_month":10,"invoice_year":2026,"due_date":"2026-10-10","total":400.5,"count":3},
               {"card_id":"bb","card_name":"Ourocard","invoice_month":10,"invoice_year":2026,"due_date":"2026-10-15","total":20,"count":1}]}]}
        """.trimIndent()
        val item = ApiJson.decodeFromString(AttentionDto.serializer(), json).items.single()
        val request = HomeLogic.overdueRequest(item)!!
        assertEquals("Pagar 2 faturas vencidas", request.title)
        assertEquals("2 faturas · a mais antiga venceu em 10/10/2026", request.description)
        assertEquals(listOf(10, 10), request.invoices.map { it.invoiceMonth })
        assertEquals(0, money("420.5").compareTo(request.total))
        assertNull(HomeLogic.overdueRequest(null))
    }

    @Test
    fun thePaySheetAccountLabelsAndShortfall() {
        val view = HomeLogic.view(home, emptyList())
        val main = view.accounts.first { it.id == "main" }
        val corr = view.accounts.first { it.id == "corr" }
        assertEquals("Itaú (padrão) · R$${nbsp}1.000,00", HomeLogic.accountOptionLabel(main, hidden = false))
        assertEquals("Itaú (padrão)", HomeLogic.accountOptionLabel(main, hidden = true))
        assertEquals("Corretora", HomeLogic.accountOptionLabel(corr, hidden = false))
        assertTrue(HomeLogic.shortfall(main, money("1000.01")))
        assertFalse(HomeLogic.shortfall(main, money("1000")))
        assertFalse(HomeLogic.shortfall(corr, money("99999")))
        assertFalse(HomeLogic.shortfall(null, money("1")))
        assertEquals("O saldo de Itaú (R$${nbsp}1.000,00) não cobre a fatura; a conta ficará negativa.", HomeLogic.shortfallText(main, false))
        assertEquals("O saldo de Itaú não cobre a fatura; a conta ficará negativa.", HomeLogic.shortfallText(main, true))
    }

    @Test
    fun theHomeResponseIsReadWithExactMoney() {
        val json = """
            {"today":"2026-10-20","month":"2026-10","consolidated_balance":1234.56,
             "accounts":[{"id":"a","name":"Itaú","type":"CHECKING","is_default":true,"balance":1234.56,"balance_brl":1234.56}],
             "summary":{"income":0.1,"expense":0.2,"result":-0.1,"invested":0,"redeemed":0,"investment_net":0,
                        "others_paid":0,"others_received":0,"others_net":0},
             "flow":[{"month":"2026-10","income":0.1,"expense":0.2,"invested":0,"redeemed":0,"others_paid":0,
                      "others_received":0,"net":-0.1,"balance":1234.56}],
             "next_invoices":[{"card_id":"nu","card_name":"Nubank","invoice_month":11,"invoice_year":2026,
                               "due_date":"2026-11-10","closing_date":"2026-11-03","closed":false,"payable":false,
                               "total":99.9,"item_count":2}],
             "next_invoices_total":99.9,"next_closing_date":"2026-11-03","novo_campo":1}
        """.trimIndent()
        val home = ApiJson.decodeFromString(HomeDto.serializer(), json)
        assertEquals(BigDecimal("0.1"), home.summary.income)
        assertEquals(BigDecimal("1234.56"), home.consolidatedBalance)
        assertEquals("2026-11-03", home.nextClosingDate)
        assertEquals(11, home.nextInvoices.single().invoiceMonth)
        assertFalse(home.nextInvoices.single().payable)
        assertEquals(BigDecimal("-0.1"), home.flow.single().net)
    }

    @Test
    fun theDismissedKeysSurviveAsJson() {
        val keys = listOf("fatura-vencida:nu|2026-10", "recorrencias:3@x2")
        assertEquals(keys, AttentionDismissals.decode(AttentionDismissals.encode(keys)))
        assertEquals(listOf("a"), AttentionDismissals.decode("""["a", 3, null]"""))
        assertTrue(AttentionDismissals.decode("quebrado").isEmpty())
        assertTrue(AttentionDismissals.decode(null).isEmpty())
    }

    @Test
    fun anActionMessageOutlivesARefetch() {
        // "Lançar" com recorrencia bloqueada: a releitura limpa so o erro da leitura.
        assertEquals("bloqueada", HomeLogic.bannerDetail("bloqueada", ""))
        assertEquals("bloqueada", HomeLogic.bannerDetail("bloqueada", "falhou a leitura"))
        assertEquals("falhou a leitura", HomeLogic.bannerDetail("", "falhou a leitura"))
        assertEquals("", HomeLogic.bannerDetail("", ""))
    }
}
