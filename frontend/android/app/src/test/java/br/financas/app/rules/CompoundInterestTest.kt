// Porte: mudou um, muda o outro, com um teste de cada lado.
// Os casos de frontend/src/lib/compoundInterest.test.js, na mesma ordem; o nome do teste do node
// vai no comentario de cada um.
package br.financas.app.rules

import br.financas.app.rules.CompoundInterest.DEFAULT_FORM
import br.financas.app.rules.CompoundInterest.FormError
import br.financas.app.rules.CompoundInterest.Input
import br.financas.app.rules.CompoundInterest.Reading
import br.financas.app.rules.CompoundInterest.Result
import br.financas.app.rules.CompoundInterest.annualFromMonthly
import br.financas.app.rules.CompoundInterest.calculate
import br.financas.app.rules.CompoundInterest.compoundSchedule
import br.financas.app.rules.CompoundInterest.durationText
import br.financas.app.rules.CompoundInterest.futureValue
import br.financas.app.rules.CompoundInterest.monthlyFromAnnual
import br.financas.app.rules.CompoundInterest.parseNumber
import br.financas.app.rules.CompoundInterest.periodLabel
import br.financas.app.rules.CompoundInterest.readForm
import br.financas.app.rules.CompoundInterest.realAnnualRate
import br.financas.app.rules.CompoundInterest.yearlyRows
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs
import kotlin.math.pow

class CompoundInterestTest {
    private fun close(actual: Double?, expected: Double, digits: Int = 6) =
        assertTrue("$actual != $expected", actual != null && abs(actual - expected) < 10.0.pow(-digits))

    private fun ok(reading: Reading): Input = (reading as Reading.Ok).input

    private fun error(reading: Reading): String = (reading as? FormError)?.message ?: ""

    private fun result(form: CompoundInterest.Form): Result = calculate(form) as Result

    // node: 'numbers from the Brazilian keyboard and from an input number'
    @Test
    fun numbersFromTheBrazilianKeyboardAndFromAnInputNumber() {
        assertEquals(1234.56, parseNumber("1.234,56")!!, 0.0)
        assertEquals(1234.56, parseNumber("1234.56")!!, 0.0)
        assertEquals(0.5, parseNumber("0,5")!!, 0.0)
        assertNull(parseNumber(""))
        assertNull(parseNumber("abc"))
    }

    // node: 'annual and monthly rates are equivalent, never proportional'
    @Test
    fun annualAndMonthlyRatesAreEquivalent() {
        close(monthlyFromAnnual(12.0), 0.948879293, 8)
        close(annualFromMonthly(1.0), 12.682503013, 8)
        close(annualFromMonthly(monthlyFromAnnual(10.65)), 10.65, 10)
    }

    // node: 'Fisher real rate'
    @Test
    fun fisherRealRate() {
        close(realAnnualRate(10.0, 4.0), 5.769230769, 8)
        close(realAnnualRate(4.0, 4.0), 0.0, 12)
    }

    // node: 'a lump sum at 1% a month for 12 months'
    @Test
    fun aLumpSumAtOnePercentAMonth() {
        val rows = compoundSchedule(initial = 1000.0, monthly = 0.0, months = 12, monthlyRatePercent = 1.0)
        assertEquals(13, rows.size)
        close(rows[12].balance, 1126.825030132, 8)
        close(rows[12].interest, 126.825030132, 8)
        assertEquals(1000.0, rows[12].invested, 0.0)
    }

    // node: 'contributions at the end and at the start of the month match the closed form'
    @Test
    fun contributionsMatchTheClosedForm() {
        val end = compoundSchedule(0.0, 100.0, 12, 1.0)
        close(end[12].balance, 1268.250301, 6)
        close(end[1].balance, 100.0, 10)
        val start = compoundSchedule(0.0, 100.0, 12, 1.0, timing = "start")
        close(start[12].balance, 1280.932804, 6)
        close(start[1].balance, 101.0, 10)

        val rate = monthlyFromAnnual(9.0)
        close(compoundSchedule(2500.0, 750.0, 360, rate).last().balance, futureValue(2500.0, 750.0, 360, rate), 4)
        close(
            compoundSchedule(2500.0, 750.0, 360, rate, timing = "start").last().balance,
            futureValue(2500.0, 750.0, 360, rate, timing = "start"),
            4,
        )
    }

    // node: 'a zero rate only adds the contributions'
    @Test
    fun aZeroRateOnlyAddsTheContributions() {
        val rows = compoundSchedule(100.0, 50.0, 24, 0.0)
        assertEquals(1300.0, rows.last().balance, 0.0)
        assertEquals(0.0, rows.last().interest, 0.0)
        assertEquals(1300.0, futureValue(100.0, 50.0, 24, 0.0), 0.0)
    }

    // node: "inflation deflates to today's money"
    @Test
    fun inflationDeflatesToTodaysMoney() {
        val rows = compoundSchedule(1000.0, 0.0, 24, 0.0, inflationPercent = 10.0)
        close(rows[12].real, 1000 / 1.1, 8)
        close(rows[24].real, 1000 / 1.21, 8)
        assertNull(compoundSchedule(1.0, 0.0, 1, 1.0)[1].real)
    }

    // node: 'yearly rows, the last one partial'
    @Test
    fun yearlyRowsTheLastOnePartial() {
        val schedule = compoundSchedule(0.0, 100.0, 30, 1.0)
        val years = yearlyRows(schedule)
        assertEquals(listOf(1 to 12, 2 to 12, 3 to 6), years.map { it.year to it.months })
        assertEquals(1200.0, years[1].investedInYear, 0.0)
        close(years[0].interestInYear, years[0].interest, 10)
        close(years[2].balance, schedule[30].balance, 10)
        close(years.sumOf { it.interestInYear }, schedule[30].interest, 8)
    }

    // node: 'the form: units, defaults and errors'
    @Test
    fun theFormUnitsDefaultsAndErrors() {
        val months = ok(readForm(DEFAULT_FORM.copy(period = "18", periodUnit = "month", rate = "1", rateUnit = "month")))
        assertEquals(18, months.months)
        close(months.annualRatePercent, 12.682503013, 8)
        assertEquals(18, ok(readForm(DEFAULT_FORM.copy(period = "1,5"))).months)
        assertEquals(0.0, ok(readForm(DEFAULT_FORM.copy(initial = "", monthly = ""))).initial, 0.0)
        assertNull(ok(readForm(DEFAULT_FORM.copy(inflation = ""))).inflationPercent)

        assertTrue(error(readForm(DEFAULT_FORM.copy(period = ""))).contains("período"))
        assertTrue(error(readForm(DEFAULT_FORM.copy(period = "1,3"))).contains("meses inteiros"))
        assertEquals("", error(readForm(DEFAULT_FORM.copy(period = "7", periodUnit = "month"))))
        assertTrue(error(readForm(DEFAULT_FORM.copy(period = "101"))).contains("100 anos"))
        assertTrue(error(readForm(DEFAULT_FORM.copy(rate = "-100"))).contains("−100%"))
        assertTrue(error(readForm(DEFAULT_FORM.copy(monthly = "-1"))).contains("negativos"))
    }

    // node: 'calculate: totals, income at the end and the real rate'
    @Test
    fun calculateTotalsIncomeAtTheEndAndTheRealRate() {
        val form = CompoundInterest.Form("10000", "1000", "1", "month", "1", "year", "end", "4")
        val r = result(form)
        close(r.final, 10000 * 1.01.pow(12) + 1000 * (1.01.pow(12) - 1) / 0.01, 6)
        assertEquals(22000.0, r.invested, 0.0)
        close(r.interest, r.final - 22000, 8)
        close(r.monthlyIncomeAtEnd, r.final * 0.01, 8)
        close(r.real, r.final / 1.04, 6)
        close(r.realAnnualRatePercent, (1.01.pow(12) / 1.04 - 1) * 100, 8)
        assertNull(result(DEFAULT_FORM.copy(inflation = "")).realAnnualRatePercent)
        assertTrue(calculate(DEFAULT_FORM.copy(period = "0")) is FormError)
    }

    // node: 'period labels'
    @Test
    fun periodLabels() {
        assertEquals("Hoje", periodLabel(0))
        assertEquals("Ano 2", periodLabel(24))
        assertEquals("Mês 7", periodLabel(7))
    }

    // node: 'duration text'
    @Test
    fun durationTextCases() {
        assertEquals("1 ano", durationText(12))
        assertEquals("10 anos", durationText(120))
        assertEquals("1 mês", durationText(1))
        assertEquals("2 anos e 6 meses", durationText(30))
    }
}
