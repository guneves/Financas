// Port: mudou um, muda o outro, com um teste de cada lado.
// Os casos de frontend/src/lib/recurring.test.js, na mesma ordem.
package br.financas.app.rules

import br.financas.app.rules.Recurring.accountOptions
import br.financas.app.rules.Recurring.editPatch
import br.financas.app.rules.Recurring.frequencyLabel
import org.junit.Assert.assertEquals
import org.junit.Test
import java.math.BigDecimal

class RecurringTest {
    private val accounts = listOf("nubank" to "Nubank", "itau" to "Itaú")

    // node: 'a recurrence in an archived account can pick another one'
    @Test
    fun aRecurrenceInAnArchivedAccountCanPickAnotherOne() {
        val options = accountOptions("velha", accounts)
        assertEquals(listOf("velha", "nubank", "itau"), options.map { it.id })
        assertEquals("Conta arquivada", options[0].label)
        assertEquals(true, options[0].disabled)
        assertEquals(mapOf("account_id" to "nubank"), editPatch(BigDecimal(100), "velha", "100", "nubank"))
    }

    // node: 'the edit sends only what changed'
    @Test
    fun theEditSendsOnlyWhatChanged() {
        assertEquals(listOf("nubank", "itau"), accountOptions("itau", accounts).map { it.id })
        assertEquals(emptyMap<String, Any?>(), editPatch(BigDecimal(100), "itau", "100", "itau"))
        assertEquals(0, BigDecimal("120.5").compareTo(editPatch(BigDecimal(100), "itau", "120,50", "itau")["amount"] as BigDecimal))
        val both = editPatch(BigDecimal(100), "itau", "1.200", "nubank")
        assertEquals(0, BigDecimal(1200).compareTo(both["amount"] as BigDecimal))
        assertEquals("nubank", both["account_id"])
    }

    // node: 'a recurrence without an account shows no archived option'
    @Test
    fun aRecurrenceWithoutAnAccountShowsNoArchivedOption() {
        assertEquals(listOf("nubank", "itau"), accountOptions(null, accounts).map { it.id })
        assertEquals(emptyMap<String, Any?>(), editPatch(BigDecimal(10), null, "10", ""))
    }

    // node: 'frequencyLabel: a frequencia e o intervalo'
    @Test
    fun frequencyLabelAFrequenciaEOIntervalo() {
        assertEquals("Mensal", frequencyLabel("MONTHLY", 1))
        assertEquals("Semanal", frequencyLabel("WEEKLY", null))
        assertEquals("Anual", frequencyLabel("YEARLY", 1))
        assertEquals("A cada 3 meses", frequencyLabel("MONTHLY", 3))
        assertEquals("A cada 2 semanas", frequencyLabel("WEEKLY", 2))
        assertEquals("A cada 5 anos", frequencyLabel("YEARLY", 5))
        assertEquals("DAILY", frequencyLabel("DAILY", 1))
        assertEquals("A cada 4 meses", frequencyLabel("DAILY", 4))
    }
}
