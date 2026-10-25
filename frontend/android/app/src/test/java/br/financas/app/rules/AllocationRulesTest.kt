// O que Alocacao.jsx e ImpostoRenda.jsx fazem inline (sem teste do lado web).
package br.financas.app.rules

import br.financas.app.core.formatCurrency
import org.junit.Assert.assertEquals
import org.junit.Test
import java.math.BigDecimal

class AllocationRulesTest {
    private fun money(text: String) = BigDecimal(text)

    @Test
    fun gapTexts() {
        assertEquals("Faltam R\$ 1.000,00", AllocationRules.gapText(money("1000"), ::formatCurrency))
        assertEquals("R\$ 250,50 acima", AllocationRules.gapText(money("-250.5"), ::formatCurrency))
        assertEquals("Na meta", AllocationRules.gapText(money("0.004"), ::formatCurrency))
        assertEquals("", AllocationRules.gapText(null, ::formatCurrency))
        assertEquals("Faltam ***", AllocationRules.gapText(money("10")) { "***" })
    }

    @Test
    fun driftBadge() {
        assertEquals(AllocationRules.Drift("Sem meta", false), AllocationRules.drift(null))
        assertEquals(AllocationRules.Drift("Na meta", false), AllocationRules.drift(money("0")))
        assertEquals(AllocationRules.Drift("+2,5% p.p.", false), AllocationRules.drift(money("2.5")))
        assertEquals(AllocationRules.Drift("−5,0% p.p.", true), AllocationRules.drift(money("-5")))
    }

    @Test
    fun contributionTyped() {
        assertEquals(money("1500.5"), AllocationRules.contribution("1500,5"))
        assertEquals(BigDecimal.ZERO, AllocationRules.contribution(""))
        assertEquals(BigDecimal.ZERO, AllocationRules.contribution("abc"))
        assertEquals(BigDecimal.ZERO, AllocationRules.contribution("-10"))
    }

    @Test
    fun sectorColorsSkipTheUnassigned() {
        assertEquals(listOf(0, -1, 1, 2), AllocationRules.sectorColorIndices(listOf("Bancos", null, "Energia", "Saúde")))
        assertEquals(listOf(0, 1, -1), AllocationRules.sectorColorIndices(listOf("A", "B", "C"), colors = 2))
    }

    @Test
    fun activeTaxMonths() {
        val months = listOf(
            AllocationRules.TaxMonth("2026-01", null, null, null, null, null),
            AllocationRules.TaxMonth("2026-02", money("100"), null, null, null, null),
            AllocationRules.TaxMonth("2026-03", money("0"), null, null, null, money("5")),
            AllocationRules.TaxMonth("2026-04", null, money("10"), null, null, null),
        )
        assertEquals(listOf("2026-02", "2026-03", "2026-04"), AllocationRules.activeMonths(months) { it }.map { it.month })
        assertEquals(true, AllocationRules.hasEtfs(months) { it })
        assertEquals(false, AllocationRules.hasEtfs(months.take(3)) { it })
        assertEquals("mar/2026", AllocationRules.monthName("2026-03"))
        assertEquals(listOf(2026, 2025, 2024), AllocationRules.yearOptions(2025, listOf(2024, 2025), 2026))
        assertEquals(listOf(2026, 2025), AllocationRules.yearOptions(2025, emptyList(), 2026))
    }
}
