// Port: mudou um, muda o outro, com um teste de cada lado.
// O caminho de createEntry() de frontend/src/lib/outbox.js: o que vai para a fila e o que nao vai.
package br.financas.app.ui.newentry

import br.financas.app.data.ApiException
import kotlinx.coroutines.test.runTest
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

    private class Fake(
        var online: Boolean = true,
        var answer: suspend (String, String) -> String = { _, _ -> "{\"id\":\"t1\"}" },
    ) {
        val posts = mutableListOf<Pair<String, JSONObject>>()
        val queued = mutableListOf<JSONObject>()
        var ids = 0

        fun saver() = EntrySaver(
            hasNetwork = { online },
            post = { path, body ->
                posts.add(path to JSONObject(body))
                answer(path, body)
            },
            enqueue = { queued.add(it) },
            userId = { "u1" },
            now = { 0L },
            newClientId = { ids += 1; "gerado-$ids-0000" },
        )
    }

    @Test
    fun savedOnTheServer() = runTest {
        val fake = Fake()
        val result = fake.saver().create("EXPENSE", payload)
        assertTrue(result is SaveResult.Saved)
        assertEquals(1, fake.posts.size)
        assertEquals("/api/transactions", fake.posts[0].first)
        val body = fake.posts[0].second
        assertEquals("gerado-1-0000", body.getString("client_id"))
        assertEquals("a1", body.getString("account_id"))
        assertEquals(42.9, body.getDouble("amount"), 0.0)
        assertTrue(fake.queued.isEmpty())
        assertEquals(1, fake.ids)
    }

    @Test
    fun withoutANetworkItIsQueuedAtOnce() = runTest {
        val fake = Fake(online = false)
        val result = fake.saver().create("TRANSFER", linkedMapOf("amount" to BigDecimal("500"), "account_id" to "a1", "transfer_account_id" to "a2"))
        assertTrue(result is SaveResult.Queued)
        assertTrue(fake.posts.isEmpty())
        assertEquals(1, fake.queued.size)
        val item = fake.queued[0]
        assertEquals("gerado-1-0000", item.getString("client_id"))
        assertEquals("gerado-1-0000", item.getJSONObject("payload").getString("client_id"))
        assertEquals("TRANSFER", item.getString("kind"))
        assertEquals("u1", item.getString("user_id"))
        assertEquals("pending", item.getString("status"))
        assertEquals("1970-01-01T00:00:00.000Z", item.getString("created_at"))
    }

    @Test
    fun aRequestThatNeverArrivedIsQueuedWithTheSameClientId() = runTest {
        val fake = Fake(answer = { _, _ -> throw ApiException.Network(IOException("timeout")) })
        val result = fake.saver().create("CARD", linkedMapOf("card_id" to "itau", "total_amount" to BigDecimal("120"), "installments" to 3))
        assertTrue(result is SaveResult.Queued)
        assertEquals(1, fake.posts.size)
        assertEquals(1, fake.ids)
        assertEquals(fake.posts[0].second.getString("client_id"), fake.queued[0].getString("client_id"))
        assertEquals("/api/cc-expenses/purchases", fake.posts[0].first)
    }

    @Test
    fun aRefusalIsShownAndNeverQueued() = runTest {
        val fake = Fake(answer = { _, _ -> throw ApiException.Http(400, "Categoria esta arquivada.") })
        val result = fake.saver().create("EXPENSE", payload)
        assertEquals(SaveResult.Refused(400, "Categoria esta arquivada."), result)
        assertTrue(fake.queued.isEmpty())

        val conflict = Fake(answer = { _, _ -> throw ApiException.Http(409, null) })
        assertEquals(SaveResult.Refused(409, null), conflict.saver().create("EXPENSE", payload))
        assertTrue(conflict.queued.isEmpty())
    }

    @Test
    fun aServerErrorIsAnAnswerToo() = runTest {
        // Um 5xx chegou ao servidor: como na web, aparece e nao vai para a fila.
        val fake = Fake(answer = { _, _ -> throw ApiException.Http(502, null) })
        assertTrue(fake.saver().create("EXPENSE", payload) is SaveResult.Refused)
        assertTrue(fake.queued.isEmpty())
    }

    @Test
    fun anExpiredSessionIsNotQueued() = runTest {
        val fake = Fake(answer = { _, _ -> throw ApiException.Unauthorized("Token expirado") })
        assertEquals(SaveResult.SessionExpired("Token expirado"), fake.saver().create("EXPENSE", payload))
        assertTrue(fake.queued.isEmpty())
    }

    @Test
    fun aSuccessThatIsNotTheEntryIsQueued() = runTest {
        // Portal de Wi-Fi: 200 com HTML. Nao prova que chegou; o client_id torna o reenvio seguro.
        val html = Fake(answer = { _, _ -> "<html>login</html>" })
        assertTrue(html.saver().create("EXPENSE", payload) is SaveResult.Queued)
        assertEquals(html.posts[0].second.getString("client_id"), html.queued[0].getString("client_id"))
        // Uma compra no cartao devolve a lista de parcelas; um objeto nao serve.
        val card = Fake(answer = { _, _ -> "{\"id\":\"x\"}" })
        assertTrue(card.saver().create("CARD", linkedMapOf("card_id" to "itau")) is SaveResult.Queued)
        val rows = Fake(answer = { _, _ -> "[{\"id\":\"x\",\"matched_inbox\":true}]" })
        val saved = rows.saver().create("CARD", linkedMapOf("card_id" to "itau"))
        assertTrue(saved is SaveResult.Saved)
        assertTrue((saved as SaveResult.Saved).data is org.json.JSONArray)
    }

    @Test
    fun anExistingClientIdIsKept() = runTest {
        val fake = Fake(online = false)
        val withId = LinkedHashMap(payload).apply { put("client_id", "ja-existia-123") }
        fake.saver().create("EXPENSE", withId)
        assertEquals("ja-existia-123", fake.queued[0].getString("client_id"))
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
