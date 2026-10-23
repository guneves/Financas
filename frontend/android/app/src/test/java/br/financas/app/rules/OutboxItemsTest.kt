// A fila nativa (o JSON que lib/outbox.js escreve, buildItem() em outboxRules.js) vista pelas
// regras do saldo com pendentes.
package br.financas.app.rules

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

class OutboxItemsTest {
    // O formato de buildItem(): client_id, user_id, kind, payload (o corpo da rota), status,
    // last_error, created_at.
    private val expense = """
        {"client_id":"c1","user_id":"u1","kind":"EXPENSE",
         "payload":{"amount":25.9,"account_id":"main","date":"2026-10-12","category":"Mercado",
                    "category_id":"cat1","description":"Feira","client_id":"c1"},
         "status":"pending","last_error":"","created_at":"2026-10-12T10:00:00.000Z"}
    """.trimIndent()

    private val card = """
        {"client_id":"c2","user_id":"u1","kind":"CARD",
         "payload":{"total_amount":"300.00","card_id":"k","installments":3,"purchase_date":"2026-10-12"},
         "status":"needs_attention","created_at":"2026-10-12T11:00:00.000Z"}
    """.trimIndent()

    private val transfer = """
        {"client_id":"c3","user_id":"u2","kind":"TRANSFER",
         "payload":{"amount":100,"account_id":"a","transfer_account_id":"b","date":"2026-10-13"},
         "status":"pending","created_at":"2026-10-13T08:00:00.000Z"}
    """.trimIndent()

    @Test
    fun anExpenseItemBecomesAPendingItem() {
        val item = OutboxItems.parse(expense)!!
        assertEquals("c1", item.clientId)
        assertEquals("EXPENSE", item.kind)
        assertEquals(OutboxPending.PENDING, item.status)
        assertEquals("2026-10-12T10:00:00.000Z", item.createdAt)
        assertEquals(0, BigDecimal("25.9").compareTo(item.payload.amount))
        assertEquals("main", item.payload.accountId)
        assertEquals("2026-10-12", item.payload.date)
        assertEquals("Mercado", item.payload.category)
        assertEquals("Feira", item.payload.description)
    }

    @Test
    fun aCardPurchaseReadsTheTotalEvenAsText() {
        val item = OutboxItems.parse(card)!!
        assertEquals("CARD", item.kind)
        assertEquals(OutboxPending.NEEDS_ATTENTION, item.status)
        assertEquals(0, BigDecimal("300").compareTo(item.payload.totalAmount))
        assertNull(item.payload.amount)
    }

    @Test
    fun brokenItemsAreLeftOut() {
        assertNull(OutboxItems.parse("não é json"))
        assertNull(OutboxItems.parse("[]"))
        assertNull(OutboxItems.parse("""{"kind":"EXPENSE"}"""))
        assertNull(OutboxItems.parse("""{"client_id":"x"}"""))
        // Um valor que nao e numero fica ausente (vale 0 nas regras).
        assertNull(OutboxItems.parse("""{"client_id":"x","kind":"EXPENSE","payload":{"amount":"abc"}}""")!!.payload.amount)
        // Sem status, pendente (o buildItem sempre escreve um).
        assertEquals(OutboxPending.PENDING, OutboxItems.parse("""{"client_id":"x","kind":"INCOME"}""")!!.status)
    }

    @Test
    fun onlyTheSessionUsersItemsCount() {
        val all = listOf(expense, card, transfer, "lixo")
        assertEquals(listOf("c1", "c2"), OutboxItems.forUser(all, "u1").map { it.clientId })
        assertEquals(listOf("c3"), OutboxItems.forUser(all, "u2").map { it.clientId })
        assertTrue(OutboxItems.forUser(all, null).isEmpty())
        assertTrue(OutboxItems.forUser(all, "").isEmpty())
    }

    @Test
    fun theParsedItemsFeedThePendingBalance() {
        val items = OutboxItems.forUser(listOf(expense, card), "u1")
        val deltas = OutboxPending.pendingAccountDeltas(items, "main")
        // A despesa tira da conta; a compra no cartao (e recusada) nao mexe em nada.
        assertEquals(mapOf("main" to -2590L), deltas)
    }
}
