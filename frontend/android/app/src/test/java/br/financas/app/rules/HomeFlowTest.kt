// Port: mudou um, muda o outro, com um teste de cada lado.
// Os casos de frontend/src/lib/homeFlow.test.js e chartFormat.test.js, na mesma ordem; o nome do
// teste do node vai no comentario de cada um.
package br.financas.app.rules

import br.financas.app.rules.HomeFlow.compactAxis
import br.financas.app.rules.HomeFlow.flowPoint
import br.financas.app.rules.HomeFlow.flowSummary
import br.financas.app.rules.HomeFlow.savingsRateText
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal
import java.math.RoundingMode

class HomeFlowTest {
    private fun money(text: String) = BigDecimal(text)

    // O month() do node: todos os campos em 0, com os valores dados por cima.
    private fun month(
        key: String,
        income: String = "0",
        expense: String = "0",
        invested: String = "0",
        redeemed: String = "0",
        othersPaid: String = "0",
        othersReceived: String = "0",
        net: String = "0",
        balance: String = "0",
    ) = HomeMonth(
        month = key,
        income = money(income),
        expense = money(expense),
        invested = money(invested),
        redeemed = money(redeemed),
        othersPaid = money(othersPaid),
        othersReceived = money(othersReceived),
        net = money(net),
        balance = money(balance),
    )

    private fun assertMoney(expected: String, actual: BigDecimal) =
        assertEquals("esperado $expected, veio $actual", 0, money(expected).compareTo(actual))

    // node: 'o ponto do grafico: saidas abaixo do zero, investimento e outras pessoas liquidos'
    @Test
    fun theChartPointPutsOutflowsBelowZero() {
        val point = flowPoint(
            month(
                "2026-10", income = "1000", expense = "250.5", invested = "300", redeemed = "100",
                othersPaid = "40", othersReceived = "10", net = "519.5", balance = "5000",
            ),
        )
        assertEquals("2026-10", point.key)
        assertEquals("out/26", point.label)
        assertMoney("1000", point.income)
        assertMoney("-250.5", point.expense)
        assertMoney("-200", point.investment)
        assertMoney("-30", point.others)
        assertMoney("519.5", point.net)
        assertMoney("5000", point.balance)
    }

    // node: 'mes vazio nao vira -0; resgate maior que aporte fica acima do zero'
    @Test
    fun anEmptyMonthIsZeroAndARedemptionGoesAbove() {
        val empty = flowPoint(month("2026-01"))
        assertEquals(0, empty.expense.signum())
        assertEquals(0, empty.investment.signum())
        assertEquals(0, empty.others.signum())
        assertMoney("250.25", flowPoint(month("2026-02", invested = "100", redeemed = "350.25")).investment)
        assertMoney("80.1", flowPoint(month("2026-02", othersReceived = "80.1")).others)
    }

    // node: 'as medias contam so os meses com movimento'
    @Test
    fun theAveragesCountOnlyMonthsWithMovement() {
        val summary = flowSummary(
            listOf(
                flowPoint(month("2026-08")),
                flowPoint(month("2026-09", income = "1000", expense = "400")),
                flowPoint(month("2026-10", income = "2000", expense = "600", invested = "500")),
            ),
        )
        assertMoney("1500", summary.avgIncome)
        assertMoney("500", summary.avgExpense)
        assertMoney("250", summary.avgInvestment)
        assertMoney("66.667", summary.savingsRate!!.setScale(3, RoundingMode.HALF_UP))
        assertTrue(summary.hasData)
        assertTrue(summary.hasInvestment)
        assertFalse(summary.hasOthers)
    }

    // node: 'so outras pessoas ja e um mes com movimento; resgate deixa a media negativa'
    @Test
    fun othersAloneIsMovementAndARedemptionMakesTheAverageNegative() {
        val summary = flowSummary(
            listOf(
                flowPoint(month("2026-09", othersPaid = "30")),
                flowPoint(month("2026-10", redeemed = "200")),
            ),
        )
        assertTrue(summary.hasData)
        assertTrue(summary.hasOthers)
        assertMoney("-100", summary.avgInvestment)
        assertMoney("0", summary.avgIncome)
        assertNull(summary.savingsRate)
    }

    // node: 'sem nenhum movimento: nada a mostrar, e a divisao e por um mes'
    @Test
    fun withoutMovementThereIsNothingToShow() {
        val summary = flowSummary(listOf(flowPoint(month("2026-10"))))
        assertFalse(summary.hasData)
        assertMoney("0", summary.avgIncome)
        assertNull(summary.savingsRate)
        assertFalse(flowSummary(emptyList()).hasData)
    }

    // node: 'despesa maior que a receita: taxa negativa'
    @Test
    fun spendingMoreThanTheIncomeIsANegativeRate() {
        val summary = flowSummary(listOf(flowPoint(month("2026-10", income = "1000", expense = "1500"))))
        assertMoney("-50", summary.savingsRate!!)
    }

    // node: 'a taxa de poupanca com uma casa no maximo'
    @Test
    fun theSavingsRateHasAtMostOneDecimal() {
        assertEquals("—", savingsRateText(null))
        assertEquals("66,7%", savingsRateText(BigDecimal(200).divide(BigDecimal(3), 10, RoundingMode.HALF_UP)))
        assertEquals("-50%", savingsRateText(money("-50")))
        assertEquals("12,3%", savingsRateText(money("12.25")))
        assertEquals("1.234,6%", savingsRateText(money("1234.56")))
        assertEquals("0%", savingsRateText(money("0")))
    }

    // node (chartFormat.test.js): 'eixo compacto: mil e milhao abreviados, sem o R$'
    @Test
    fun theCompactAxisAbbreviatesThousandsAndMillions() {
        assertEquals("0", compactAxis(money("0")))
        assertEquals("0", compactAxis(null))
        assertEquals("950", compactAxis(money("950")))
        assertEquals("1.000", compactAxis(money("999.6")))
        assertEquals("1,5 mil", compactAxis(money("1500")))
        assertEquals("2 mil", compactAxis(money("2000")))
        assertEquals("13 mil", compactAxis(money("12500")))
        assertEquals("1,3 mi", compactAxis(money("1250000")))
        assertEquals("−1,5 mil", compactAxis(money("-1500")))
        assertEquals("−300", compactAxis(money("-300")))
    }
}
