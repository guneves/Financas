package br.financas.app.data

import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

class ReviewRepositoryTest {

    private class MemoryCache : ReadCache {
        val entries = mutableMapOf<String, CachedBody>()
        override fun get(key: String) = entries[key]
        override fun put(key: String, body: String) = CachedBody(body, 100L).also { entries[key] = it }
        override fun clear() = entries.clear()
    }

    private class FakeServer(var answer: (String, String, String?) -> String = { _, _, _ -> "{}" }) : Fetcher, Sender {
        val calls = mutableListOf<Triple<String, String, String?>>()
        override suspend fun get(path: String): String = send("GET", path, null)
        override suspend fun send(method: String, path: String, jsonBody: String?): String {
            calls += Triple(method, path, jsonBody)
            return answer(method, path, jsonBody)
        }
    }

    private fun TestScope.repository(server: FakeServer) = ReviewRepository(
        CachedReader(server, MemoryCache(), { "u1" }, io = UnconfinedTestDispatcher(testScheduler)),
        server,
    )

    @Test
    fun theQueueDecodesTransactionsAndCardPurchases() = runTest {
        val server = FakeServer { _, _, _ ->
            """{"items":[
                {"table":"cc_expenses","id":"e1","date":"2026-10-27","amount":120.5,"type":"CARD","description":"Mercado",
                 "category":"Alimentação","category_id":"food","card_name":"Itaú Visa","installments":3},
                {"table":"transactions","id":"t1","date":"2026-10-26","amount":30,"type":"TRANSFER",
                 "account_name":"Itaú","transfer_account_name":"BTG","category":null,"category_id":null}
               ],"count":2,"waiting":1}"""
        }
        val queue = (repository(server).queue().toList().single() as Load.Fresh).value
        assertEquals(2, queue.count)
        assertEquals(1, queue.waiting)
        assertEquals(BigDecimal("120.5"), queue.items[0].amount)
        assertEquals(3, queue.items[0].installments)
        assertEquals("BTG", queue.items[1].transferAccountName)
        assertEquals(Triple("GET", "/api/review", null), server.calls.single())
    }

    @Test
    fun confirmPostsTheItemsAndReadsTheCount() = runTest {
        val server = FakeServer { _, _, _ -> """{"reviewed":2,"count":5}""" }
        val result = repository(server).confirm(listOf(mapOf("table" to "transactions", "id" to "t1"), mapOf("table" to "cc_expenses", "id" to "e1", "category_id" to "fun")))
        assertEquals(ReviewConfirmedDto(2, 5), (result as InboxWrite.Done).value)
        assertEquals(
            Triple("POST", "/api/review", """{"items":[{"table":"transactions","id":"t1"},{"table":"cc_expenses","id":"e1","category_id":"fun"}]}"""),
            server.calls.single(),
        )
    }

    @Test
    fun anUnknownIdIsRefusedAndAPortalIsOffline() = runTest {
        val refused = FakeServer { _, _, _ -> throw ApiException.Http(404, "Lancamento nao encontrado.") }
        val result = repository(refused).confirm(listOf(mapOf("table" to "transactions", "id" to "x")))
        assertEquals(InboxWrite.Refused(404, "Lancamento nao encontrado."), result)
        val portal = FakeServer { _, _, _ -> "<html>" }
        assertEquals(InboxWrite.Offline, repository(portal).confirm(listOf(mapOf("table" to "transactions", "id" to "x"))))
    }

    @Test
    fun theCardStatementTakesTheExtratoFilters() = runTest {
        val server = FakeServer { _, _, _ ->
            """[{"kind":"card","id":"e1","client_id":"c1","date":"2026-10-27","type":"REFUND","amount":20,"installments":1,
                 "card_name":"BTG black","needs_review":1,"created_at":"2026-10-27 10:00:00"}]"""
        }
        val rows = (repository(server).cardStatement(linkedMapOf("q" to "uber", "type" to "", "review" to "1")).toList().single() as Load.Fresh).value
        assertEquals("/api/cc-expenses/statement?q=uber&review=1", server.calls.single().second)
        assertEquals("REFUND", rows.single().type)
        assertTrue(rows.single().needsReview)
        assertEquals("/api/cc-expenses/statement", ReviewRepository.cardStatementPath(emptyMap()))
    }
}
