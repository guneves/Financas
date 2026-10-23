// Port: mudou um, muda o outro, com um teste de cada lado.
// O caminho de createEntry() de frontend/src/lib/outbox.js: o que vai para a fila e o que nao vai.
// Diferenca nativa: o item entra na fila antes do POST e sai numa resposta definitiva.
package br.financas.app.ui.newentry

import br.financas.app.data.ApiException
import kotlinx.coroutines.test.runTest
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException
import java.math.BigDecimal

class EntrySaverTest {
    private val payload = linkedMapOf<String, Any?>(
        "amount" to BigDecimal("42.9"),
        "date" to "2026-10-22",
        "category_id" to "mercado",
        "category" to "Mercado",
        "description" to "Pão",
        "type" to "EXPENSE",
        "account_id" to "a1",
    )

    /** A fila em memoria: o que esta guardado, o que foi tirado, quantas vezes agendou. */
    private class FakeQueue : EntryQueue {
        val stored = linkedMapOf<String, JSONObject>()
        val removed = mutableListOf<String>()
        var schedules = 0

        override fun put(item: JSONObject) {
            stored[item.getString("client_id")] = item
        }

        override fun remove(clientId: String) {
            stored.remove(clientId)
            removed.add(clientId)
        }

        override fun schedule() {
            schedules += 1
        }
    }

    private class Fake(
        var online: Boolean = true,
        var user: String? = "u1",
        var answer: suspend (String, String) -> String = { _, _ -> "{\"id\":\"t1\"}" },
    ) {
        val posts = mutableListOf<Pair<String, JSONObject>>()
        val queue = FakeQueue()
        var ids = 0

        /** O que estava na fila no instante do POST (o item ja guardado antes do envio). */
        val storedDuringPost = mutableListOf<Set<String>>()

        fun saver() = EntrySaver(
            hasNetwork = { online },
            post = { path, body ->
                posts.add(path to JSONObject(body))
                storedDuringPost.add(queue.stored.keys.toSet())
                answer(path, body)
            },
            queue = queue,
            userId = { user },
            now = { 0L },
            newClientId = { ids += 1; "gerado-$ids-0000" },
        )
    }

    @Test
    fun savedOnTheServerLeavesNothingQueued() = runTest {
        val fake = Fake()
        val result = fake.saver().create("EXPENSE", payload)
        assertTrue(result is SaveResult.Saved)
        assertEquals(1, fake.posts.size)
        assertEquals("/api/transactions", fake.posts[0].first)
        val body = fake.posts[0].second
        assertEquals("gerado-1-0000", body.getString("client_id"))
        assertEquals("a1", body.getString("account_id"))
        assertEquals(42.9, body.getDouble("amount"), 0.0)
        assertEquals(1, fake.ids)
        // Guardado antes do POST, tirado depois do 2xx, sem agendar envio.
        assertEquals(listOf(setOf("gerado-1-0000")), fake.storedDuringPost)
        assertTrue(fake.queue.stored.isEmpty())
        assertEquals(listOf("gerado-1-0000"), fake.queue.removed)
        assertEquals(0, fake.queue.schedules)
    }

    @Test
    fun theItemKeptBeforeThePostIsTheWebItem() = runTest {
        val fake = Fake(answer = { _, _ -> throw ApiException.Network(IOException("morreu")) })
        fake.saver().create("EXPENSE", payload)
        val item = fake.queue.stored.getValue("gerado-1-0000")
        assertEquals("gerado-1-0000", item.getJSONObject("payload").getString("client_id"))
        assertEquals("EXPENSE", item.getString("kind"))
        assertEquals("u1", item.getString("user_id"))
        assertEquals("pending", item.getString("status"))
        assertEquals("", item.getString("last_error"))
        assertEquals("1970-01-01T00:00:00.000Z", item.getString("created_at"))
        assertFalse(item.has("edited"))
    }

    @Test
    fun withoutANetworkItIsQueuedAtOnce() = runTest {
        val fake = Fake(online = false)
        val result = fake.saver().create("TRANSFER", linkedMapOf("amount" to BigDecimal("500"), "account_id" to "a1", "transfer_account_id" to "a2"))
        assertTrue(result is SaveResult.Queued)
        assertTrue(fake.posts.isEmpty())
        assertEquals(setOf("gerado-1-0000"), fake.queue.stored.keys)
        assertEquals("TRANSFER", fake.queue.stored.getValue("gerado-1-0000").getString("kind"))
        assertEquals(1, fake.queue.schedules)
        assertTrue(fake.queue.removed.isEmpty())
    }

    @Test
    fun aRequestThatNeverArrivedStaysWithTheSameClientIdAndIsScheduled() = runTest {
        val fake = Fake(answer = { _, _ -> throw ApiException.Network(IOException("timeout")) })
        val result = fake.saver().create("CARD", linkedMapOf("card_id" to "itau", "total_amount" to BigDecimal("120"), "installments" to 3))
        assertTrue(result is SaveResult.Queued)
        assertEquals(1, fake.posts.size)
        assertEquals(1, fake.ids)
        assertEquals(setOf(fake.posts[0].second.getString("client_id")), fake.queue.stored.keys)
        assertEquals("/api/cc-expenses/purchases", fake.posts[0].first)
        assertEquals(1, fake.queue.schedules)
        assertTrue(fake.queue.removed.isEmpty())
    }

    @Test
    fun aRedirectIsAPortalNotTheServer() = runTest {
        // Portal de Wi-Fi: 302. O cliente nao segue; o pedido nao chegou a API.
        val fake = Fake(answer = { _, _ -> throw ApiException.Http(302, null) })
        assertTrue(fake.saver().create("EXPENSE", payload) is SaveResult.Queued)
        assertEquals(setOf("gerado-1-0000"), fake.queue.stored.keys)
        assertEquals(1, fake.queue.schedules)
    }

    @Test
    fun aRefusalIsShownAndLeavesTheQueue() = runTest {
        val fake = Fake(answer = { _, _ -> throw ApiException.Http(400, "Categoria esta arquivada.") })
        assertEquals(SaveResult.Refused(400, "Categoria esta arquivada."), fake.saver().create("EXPENSE", payload))
        assertTrue(fake.queue.stored.isEmpty())
        assertEquals(listOf("gerado-1-0000"), fake.queue.removed)
        assertEquals(0, fake.queue.schedules)

        val conflict = Fake(answer = { _, _ -> throw ApiException.Http(409, null) })
        assertEquals(SaveResult.Refused(409, null), conflict.saver().create("EXPENSE", payload))
        assertTrue(conflict.queue.stored.isEmpty())
    }

    @Test
    fun aServerErrorIsAnAnswerToo() = runTest {
        // Um 5xx chegou ao servidor: como na web, aparece e nao fica na fila.
        val fake = Fake(answer = { _, _ -> throw ApiException.Http(502, null) })
        assertTrue(fake.saver().create("EXPENSE", payload) is SaveResult.Refused)
        assertTrue(fake.queue.stored.isEmpty())
        assertEquals(0, fake.queue.schedules)
    }

    @Test
    fun anExpiredSessionLeavesTheQueue() = runTest {
        val fake = Fake(answer = { _, _ -> throw ApiException.Unauthorized("Token expirado") })
        assertEquals(SaveResult.SessionExpired("Token expirado"), fake.saver().create("EXPENSE", payload))
        assertTrue(fake.queue.stored.isEmpty())
        assertEquals(0, fake.queue.schedules)
    }

    @Test
    fun withoutAUserNothingIsKept() = runTest {
        // Um item sem user_id nunca seria enviado (o remetente so manda os do usuario logado).
        for (user in listOf(null, "")) {
            val offline = Fake(online = false, user = user)
            assertEquals(SaveResult.SessionExpired(null), offline.saver().create("EXPENSE", payload))
            assertTrue(offline.queue.stored.isEmpty())
            assertEquals(0, offline.queue.schedules)
            val online = Fake(user = user)
            assertTrue(online.saver().create("EXPENSE", payload) is SaveResult.SessionExpired)
            assertTrue(online.posts.isEmpty())
        }
    }

    @Test
    fun aSuccessThatIsNotTheEntryStaysQueued() = runTest {
        // Portal de Wi-Fi: 200 com HTML. Nao prova que chegou; o client_id torna o reenvio seguro.
        val html = Fake(answer = { _, _ -> "<html>login</html>" })
        assertTrue(html.saver().create("EXPENSE", payload) is SaveResult.Queued)
        assertEquals(setOf(html.posts[0].second.getString("client_id")), html.queue.stored.keys)
        assertEquals(1, html.queue.schedules)
        // Uma compra no cartao devolve a lista de parcelas; um objeto nao serve.
        val card = Fake(answer = { _, _ -> "{\"id\":\"x\"}" })
        assertTrue(card.saver().create("CARD", linkedMapOf("card_id" to "itau")) is SaveResult.Queued)
        val rows = Fake(answer = { _, _ -> "[{\"id\":\"x\",\"matched_inbox\":true}]" })
        val saved = rows.saver().create("CARD", linkedMapOf("card_id" to "itau"))
        assertTrue(saved is SaveResult.Saved)
        assertTrue((saved as SaveResult.Saved).data is JSONArray)
        assertTrue(rows.queue.stored.isEmpty())
    }

    @Test
    fun theWorkerAlreadySentItAndRemovedIt() = runTest {
        // O envio em segundo plano pegou o item no meio do nosso POST e ja o tirou: o nosso 2xx
        // tira de novo, sem erro.
        lateinit var fake: Fake
        fake = Fake(answer = { _, _ ->
            fake.queue.stored.clear()
            "{\"id\":\"t1\"}"
        })
        assertTrue(fake.saver().create("EXPENSE", payload) is SaveResult.Saved)
        assertTrue(fake.queue.stored.isEmpty())
    }

    @Test
    fun anExistingClientIdIsKept() = runTest {
        val fake = Fake(online = false)
        val withId = LinkedHashMap(payload).apply { put("client_id", "ja-existia-123") }
        fake.saver().create("EXPENSE", withId)
        assertEquals(setOf("ja-existia-123"), fake.queue.stored.keys)
        assertEquals(0, fake.ids)
    }

    @Test
    fun anAbsentKeyIsNotSent() = runTest {
        val fake = Fake()
        val noAccount = LinkedHashMap(payload).apply { put("account_id", null) }
        fake.saver().create("EXPENSE", noAccount)
        assertFalse(fake.posts[0].second.has("account_id"))
        assertNull(fake.posts[0].second.opt("account_id"))
    }

    @Test(expected = IllegalArgumentException::class)
    fun anUnknownKindIsAProgrammingError() = runTest {
        Fake().saver().create("BUY", payload)
    }
}
