// blockedRecurringMessage: os casos de frontend/src/lib/transactions.test.js
// ('blockedRecurringMessage: a recorrencia numa conta arquivada'). budgetStatus: o comentario de
// components/BudgetProgress.jsx e a regra de budget_status() (services/budgets.py). O resto: os
// textos de pages/Dashboard.jsx.
package br.financas.app.rules

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

class HomeRulesTest {
    private fun money(text: String) = BigDecimal(text)

    private val nbsp = " "

    // node: 'blockedRecurringMessage: a recorrencia numa conta arquivada'
    @Test
    fun blockedRecurringMessageNamesTheArchivedAccount() {
        assertEquals("", HomeRules.blockedRecurringMessage(emptyList()))
        val one = HomeRules.blockedRecurringMessage(listOf(BlockedRecurring("Aluguel", "Velha")))
        assertTrue(one, Regex("\"Aluguel\" \\(Velha\\).*arquivada").containsMatchIn(one))
        val two = HomeRules.blockedRecurringMessage(listOf(BlockedRecurring("Aluguel", "Velha"), BlockedRecurring("", "Outra")))
        assertTrue(two, two.startsWith("2 recorrências"))
        assertTrue(two, two.contains("\"Sem descrição\" (Outra)"))
    }

    @Test
    fun theBudgetStatusOfTheMonthFollowsTheServer() {
        // 799,99 de 1.000,00 da 79,999% -> 80,00% -> "Perto do limite" (BudgetProgress.jsx).
        assertEquals(HomeRules.WARNING, HomeRules.budgetStatus(money("799.99"), money("1000")))
        assertEquals(HomeRules.OK, HomeRules.budgetStatus(money("799.94"), money("1000")))
        assertEquals(HomeRules.OVER, HomeRules.budgetStatus(money("1000.01"), money("1000")))
        assertEquals(HomeRules.WARNING, HomeRules.budgetStatus(money("1000"), money("1000")))
        assertEquals(HomeRules.OK, HomeRules.budgetStatus(money("0"), money("0")))
        assertEquals(HomeRules.OVER, HomeRules.budgetStatus(money("5"), money("0")))
        assertEquals(HomeRules.OK, HomeRules.budgetStatus(null, null))
    }

    @Test
    fun theFlaggedCategoriesComeOverFirstThenByPercent() {
        fun line(id: String, status: String, percent: String?) =
            BudgetLine(id, "C$id", null, money("1"), money("1"), percent?.let(::money), status)
        val flagged = HomeRules.budgetFlagged(
            listOf(
                line("a", "OK", "10"),
                line("b", "WARNING", "95"),
                line("c", "OVER", "120"),
                line("d", "WARNING", "85"),
                line("e", "OVER", "150"),
                line("f", "NEEDS_INCOME", null),
            ),
        )
        assertEquals(listOf("e", "c", "b", "d"), flagged.map { it.id })
        assertEquals("Alimentação › Mercado", HomeRules.budgetCategoryName(BudgetLine("x", "Mercado", "Alimentação", null, null, null, "OK")))
        assertEquals("Mercado", HomeRules.budgetCategoryName(BudgetLine("x", "Mercado", null, null, null, null, "OK")))
    }

    @Test
    fun theBudgetStripTexts() {
        assertEquals("Restam R$${nbsp}120,00", HomeRules.budgetRemainingText(money("120")))
        assertEquals("Passou R$${nbsp}30,50 do planejado", HomeRules.budgetRemainingText(money("-30.5")))
        assertEquals("+2 categoria(s) perto do limite ou acima", HomeRules.budgetMoreFlagged(2))
        assertEquals("A categoria com orçamento está no plano.", HomeRules.budgetAllOk(1))
        assertEquals("As 3 categorias com orçamento estão no plano.", HomeRules.budgetAllOk(3))
        assertEquals(0.5f, HomeRules.barFraction(money("50")))
        assertEquals(1f, HomeRules.barFraction(money("130")))
        assertEquals(0f, HomeRules.barFraction(null))
        assertEquals(0, money("75").compareTo(HomeRules.budgetPercent(money("750"), money("1000"))))
        assertEquals(0, HomeRules.budgetPercent(money("10"), money("0")).signum())
    }

    @Test
    fun theDashboardTexts() {
        assertEquals("Outubro de 2026", HomeRules.sentenceCase("outubro de 2026"))
        assertEquals("", HomeRules.sentenceCase(""))
        assertEquals(
            "Saldo estimado: 1 lançamento guardado neste aparelho ainda não chegou ao servidor.",
            HomeRules.estimateText(1),
        )
        assertEquals(
            "Saldo estimado: 3 lançamentos guardados neste aparelho ainda não chegaram ao servidor.",
            HomeRules.estimateText(3),
        )
        assertEquals("Fatura de novembro de 2026", HomeRules.nextInvoiceLabel(listOf("2026-11")))
        assertEquals("Próximas faturas", HomeRules.nextInvoiceLabel(listOf("2026-11", "2026-12")))
        assertEquals("Próxima fatura", HomeRules.nextInvoiceLabel(emptyList()))
        assertEquals("Pagar fatura", HomeRules.payableTitle(1))
        assertEquals("Pagar faturas", HomeRules.payableTitle(2))
        assertEquals("A fatura fechada que vence a seguir.", HomeRules.payableDescription(1))
        assertEquals("2 faturas fechadas, a próxima de cada cartão.", HomeRules.payableDescription(2))
        assertEquals("Pagar fatura vencida", HomeRules.overdueTitle(1))
        assertEquals("Pagar 3 faturas vencidas", HomeRules.overdueTitle(3))
        assertEquals("Fatura paga — R$${nbsp}450,00 debitado.", HomeRules.paidNotice(1, money("450")))
        assertEquals("2 faturas pagas — R$${nbsp}1.450,10 debitado.", HomeRules.paidNotice(2, money("1450.1")))
        assertEquals("3 lançamento(s) recorrente(s) gerado(s).", HomeRules.recurringNotice(3))
        assertEquals("Nada pendente: todos os lançamentos recorrentes já estão em dia.", HomeRules.recurringNotice(0))
        assertEquals("03/11", HomeRules.closingDayMonth("2026-11-03"))
    }
}
