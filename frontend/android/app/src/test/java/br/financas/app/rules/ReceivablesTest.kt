// O que AReceber.jsx faz inline (sem par no node): ver Receivables.kt.
package br.financas.app.rules

import br.financas.app.data.IncomeChoiceDto
import br.financas.app.data.ReceivableDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

class ReceivablesTest {
    private fun item(id: String, person: String?, amount: String, settled: String? = null, kind: String = "TRANSACTION") =
        ReceivableDto(kind = kind, id = id, person = person, othersAmount = BigDecimal(amount), settledAt = settled)

    private val items = listOf(
        item("t1", "Ana", "40.10"),
        item("c1", "ana ", "30", kind = "CARD_PURCHASE"),
        item("t2", "Ana", "10", settled = "2026-10-20T12:00:00Z"),
        item("t3", "Bruno", "100", settled = "2026-10-21T12:00:00Z"),
        item("t4", "Carla", "5"),
    )

    @Test
    fun pendentesSoOsEmAberto() {
        val view = Receivables.view(items, all = false)
        assertEquals(listOf("Ana", "Carla"), view.groups.map { it.person })
        assertEquals(listOf("t1", "c1"), view.groups[0].items.map { it.id })
        assertEquals(0, BigDecimal("70.10").compareTo(view.groups[0].openTotal))
        assertTrue(view.groups[0].showSettleAll)
        assertFalse(view.groups[1].showSettleAll)
        val summary = view.summary!!
        assertEquals(0, BigDecimal("75.10").compareTo(summary.total))
        assertEquals(2, summary.people)
        assertEquals(3, summary.items)
    }

    @Test
    fun todosMostraOsPagosEOTotalSegueEmAberto() {
        val view = Receivables.view(items, all = true)
        // Bruno tem 100 pago: o grupo vem pelo total da lista toda, mas nada em aberto.
        assertEquals(listOf("Bruno", "Ana", "Carla"), view.groups.map { it.person })
        val bruno = view.groups[0]
        assertTrue(bruno.open.isEmpty())
        assertEquals(0, BigDecimal.ZERO.compareTo(bruno.openTotal))
        assertEquals(3, view.groups[1].items.size)
        assertEquals(0, BigDecimal("70.10").compareTo(view.groups[1].openTotal))
        // O resumo e so dos pendentes, nas duas vistas.
        assertEquals(3, view.summary!!.items)
    }

    @Test
    fun semPendentesSemResumo() {
        val view = Receivables.view(listOf(item("t3", "Bruno", "100", settled = "2026-10-21T12:00:00Z")), all = true)
        assertNull(view.summary)
        assertEquals(1, view.groups.size)
        assertTrue(Receivables.view(emptyList(), all = false).groups.isEmpty())
    }

    @Test
    fun settleBodySeparaPorTipo() {
        val body = Receivables.settleBody(items.take(2), true)
        assertEquals(listOf("t1"), body["transaction_ids"])
        assertEquals(listOf("c1"), body["cc_expense_ids"])
        assertEquals(true, body["settled"])
    }

    private val pix = IncomeChoiceDto(id = "pix", date = "2026-11-01", description = "Pix", amount = BigDecimal("300"), room = BigDecimal("300"))
    private val headset = ReceivableDto(kind = "CARD_PURCHASE", id = "c1", date = "2026-11-01", person = "Tio", othersAmount = BigDecimal("230.28"))

    @Test
    fun settleBodyLevaAReceita() {
        assertEquals("pix", Receivables.settleBody(listOf(headset), true, "pix")["income_id"])
        assertNull(Receivables.settleBody(listOf(headset), false, "pix")["income_id"])
    }

    @Test
    fun oPixDoTioESugerido() {
        val choices = Receivables.paymentChoices(
            listOf(
                IncomeChoiceDto(id = "old", date = "2026-10-30", amount = BigDecimal("900"), room = BigDecimal("900")),
                IncomeChoiceDto(id = "small", date = "2026-11-01", amount = BigDecimal("100"), room = BigDecimal("100")),
                pix,
                IncomeChoiceDto(id = "later", date = "2026-11-05", amount = BigDecimal("500"), room = BigDecimal("500")),
            ),
            listOf(headset),
        )
        assertEquals("pix", Receivables.suggestedPayment(choices, listOf(headset)))
        assertEquals("", Receivables.suggestedPayment(emptyList(), listOf(headset)))
    }

    @Test
    fun trocarAEntradaDevolveAParteDele() {
        val paid = headset.copy(settledAt = "2026-11-02T21:00:00Z", paidBy = pix.copy(room = null))
        val alone = Receivables.paymentChoices(emptyList(), listOf(paid))
        assertEquals(listOf("pix"), alone.map { it.id })
        assertEquals(0, BigDecimal("230.28").compareTo(alone[0].room))
        val listed = Receivables.paymentChoices(listOf(pix.copy(room = BigDecimal("69.72"))), listOf(paid))
        assertEquals(0, BigDecimal("300").compareTo(listed[0].room))
        assertEquals("pix", Receivables.suggestedPayment(listed, listOf(paid)))
    }
}
