package br.financas.app.rules

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

/** Os casos de outboxRules.test.js para itemTitle, itemAmount, itemDate e isEditableKind. */
class PendingRowsTest {
    private fun item(kind: String, payload: String, extra: String = "") =
        """{"client_id":"id-$kind-${payload.hashCode()}","user_id":"u1","kind":"$kind","payload":$payload,"status":"pending","created_at":"2026-10-12T10:00:00.000Z"$extra}"""

    @Test
    fun investmentAndProceedTitleAmountAndDate() {
        val buy = PendingRows.parse(item("INVESTMENT", """{"ticker_or_name":"PETR4","quantity":10,"average_price":30.5,"metadata":{"purchase_date":"2026-10-12"}}"""))!!
        val sale = PendingRows.parse(item("INVESTMENT", """{"ticker_or_name":"BOVA11","quantity":-2,"average_price":100,"metadata":{"sale_date":"2026-10-13","sale_price":120}}"""))!!
        val proceed = PendingRows.parse(item("PROCEED", """{"asset_id":"a1","gross_amount":80,"payment_date":"2026-11-03"}""", ""","title":"CDB X""""))!!
        assertEquals(listOf("PETR4", "BOVA11", "CDB X"), listOf(buy, sale, proceed).map { it.title })
        assertEquals(listOf(0, 0, 0), listOf(buy, sale, proceed).zip(listOf("305", "240", "80")).map { (row, value) -> row.amount.compareTo(BigDecimal(value)) })
        assertEquals(listOf("2026-10-12", "2026-10-13", "2026-11-03"), listOf(buy, sale, proceed).map { it.date })
        assertEquals("Provento", PendingRows.parse(item("PROCEED", """{"gross_amount":1}"""))!!.title)
        assertEquals("Pao", PendingRows.parse(item("EXPENSE", """{"description":"Pao","amount":3}"""))!!.title)
        assertEquals(
            listOf(true, true, true, true, false, false),
            listOf("EXPENSE", "INCOME", "TRANSFER", "CARD", "INVESTMENT", "PROCEED").map(PendingRows::isEditableKind),
        )
    }

    @Test
    fun cardRowShowsTotalDateAndInstallments() {
        val card = PendingRows.parse(item("CARD", """{"total_amount":"300.00","purchase_date":"2026-10-12","installments":3}""", ""","last_error":"Cartão arquivado.","status":"needs_attention""""))!!
        assertEquals(0, card.amount.compareTo(BigDecimal("300")))
        assertEquals("Compra no cartão", card.title)
        assertTrue(card.refused)
        assertEquals("Cartão arquivado.", card.lastError)
        assertEquals("Compra no cartão · 12/10/2026 · 3x", PendingRows.detail(card) { br.financas.app.core.formatDateBR(it) })
    }

    @Test
    fun onlyTheSessionUsersItemsInSendOrder() {
        val later = item("EXPENSE", """{"amount":1}""").replace("2026-10-12T10", "2026-10-13T10")
        val earlier = item("INCOME", """{"amount":2}""")
        val other = item("EXPENSE", """{"amount":3}""").replace("\"u1\"", "\"u2\"")
        val rows = PendingRows.forUser(listOf(later, earlier, other, "{quebrado"), "u1")
        assertEquals(listOf("INCOME", "EXPENSE"), rows.map { it.kind })
        assertEquals(emptyList<PendingRow>(), PendingRows.forUser(listOf(earlier), null))
    }

    @Test
    fun syncTexts() {
        assertEquals("Entre novamente para enviar os lançamentos pendentes.", PendingRows.syncWarning("login", 0))
        assertEquals("O servidor recusou um ou mais lançamentos. Veja o motivo em cada um.", PendingRows.syncWarning("", 2))
        assertNull(PendingRows.syncWarning("", 0))
        assertEquals("2 lançamentos enviados.", PendingRows.sentNotice(2))
        assertNull(PendingRows.sentNotice(0))
    }
}
