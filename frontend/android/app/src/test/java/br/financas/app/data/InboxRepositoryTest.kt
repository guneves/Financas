package br.financas.app.data

import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

class InboxRepositoryTest {

    private class MemoryCache(var now: Long = 100L) : ReadCache {
        val entries = mutableMapOf<String, CachedBody>()
        override fun get(key: String) = entries[key]
        override fun put(key: String, body: String) = CachedBody(body, now).also { entries[key] = it }
        override fun clear() = entries.clear()
    }

    /** O servidor de mentira: anota cada pedido e responde o que o teste manda. */
    private class FakeServer(var answer: (String, String, String?) -> String = { _, _, _ -> "{}" }) : Fetcher, Sender {
        val calls = mutableListOf<Triple<String, String, String?>>()
        override suspend fun get(path: String): String = send("GET", path, null)
        override suspend fun send(method: String, path: String, jsonBody: String?): String {
            calls += Triple(method, path, jsonBody)
            return answer(method, path, jsonBody)
        }
    }

    private val itemJson = """
        {"id":"i1","version":3,"state":"PENDING","entry_type":"CARD","direction":"OUT","amount":45.9,
         "installments":1,"occurred_at":"2026-10-17T22:30:00-03:00","card_id":"c1","card_name":"Itaú Visa",
         "needs":[],"confirm":["card"],"guessed":["card"],"edited":["amount"],"ready":false,"ambiguous":false,
         "recurring":null,"recurring_off":false,
         "candidates":[{"table":"cc_expenses","id":"e1","kind":"card_purchase","date":"2026-10-17","amount":45.9,
                        "installment_info":"1/1","card_name":"Itaú Visa"}],
         "sources":[{"source":"notification","id":"d1","role":"SOURCE","app":"com.itau","app_label":"Itaú",
                     "kind":"CREDIT_PURCHASE","amount":45.9,"occurred_at":"2026-10-17T22:30:00-03:00","card_last4":"1234"}],
         "pending_count":4,"target":null}
    """.trimIndent()

    private fun TestScope.repository(server: FakeServer, cache: ReadCache = MemoryCache()) = InboxRepository(
        CachedReader(server, cache, { "u1" }, io = UnconfinedTestDispatcher(testScheduler)),
        server,
    )

    @Test
    fun theListReadsTheViewAndDecodesMoneyAsBigDecimal() = runTest {
        val server = FakeServer { _, _, _ -> """{"items":[$itemJson],"pending_count":4}""" }
        val loads = repository(server).list(InboxRepository.VIEW_PENDING).toList()

        val fresh = loads.single() as Load.Fresh
        val item = fresh.value.items.single()
        assertEquals(4, fresh.value.pendingCount)
        assertEquals(BigDecimal("45.9"), item.amount)
        assertEquals(3, item.version)
        assertEquals(listOf("card"), item.confirm)
        assertEquals(1, item.edited.size)
        assertEquals("e1", item.candidates.single().id)
        assertEquals("1234", item.sources.single().cardLast4)
        assertEquals(listOf(Triple("GET", "/api/inbox?view=pending", null)), server.calls)
    }

    @Test
    fun theDecidedListIsCachedPerViewAndComesFirstNextTime() = runTest {
        val cache = MemoryCache()
        cache.put("u1 /api/inbox?view=decided", """{"items":[],"pending_count":2}""")
        val server = FakeServer { _, _, _ -> throw ApiException.Network(null) }
        val loads = repository(server, cache).list(InboxRepository.VIEW_DECIDED).toList()

        assertEquals(2, (loads[0] as Load.Cached).value.pendingCount)
        val failed = loads[1] as Load.Failed
        assertTrue(failed.error is ApiException.Network)
        assertEquals(loads[0], failed.cached)
    }

    @Test
    fun hintsSettingsCountAndOneItem() = runTest {
        val server = FakeServer { _, path, _ ->
            when (path) {
                "/api/inbox/hints" -> """[{"id":"h1","hint_key":"k","label":"Itaú","entry_type":"CARD","uses":2,
                    "created_at":"2026-10-17T12:00:00.000Z","card_name":"Itaú Visa"}]"""
                "/api/inbox/settings" -> """{"always_ask":true}"""
                "/api/inbox/count" -> """{"pending_count":7}"""
                else -> itemJson
            }
        }
        val repo = repository(server)
        val hint = (repo.hints().toList().single() as Load.Fresh).value.single()
        assertEquals(2, hint.uses)
        assertEquals("Itaú Visa", hint.rule.cardName)
        assertTrue((repo.settings().toList().single() as Load.Fresh).value.alwaysAsk)
        assertEquals(7, (repo.count().toList().single() as Load.Fresh).value.pendingCount)
        assertEquals("i1", (repo.item("i1").toList().single() as Load.Fresh).value.id)
        assertEquals("/api/inbox/i1", server.calls.last().second)
    }

    @Test
    fun aDecisionSendsTheBodyAndReturnsTheItemAndTheCount() = runTest {
        val server = FakeServer { _, _, _ -> itemJson }
        val result = repository(server).approve("i1", linkedMapOf("version" to 3, "remember" to true))

        val done = result as InboxWrite.Done
        assertEquals("i1", done.value.item.id)
        assertEquals(4, done.value.pendingCount)
        assertEquals(Triple("POST", "/api/inbox/i1/approve", """{"version":3,"remember":true}"""), server.calls.single())
    }

    @Test
    fun theEditSendsMoneyAsAPlainNumberAndNullsAsNull() = runTest {
        val server = FakeServer { _, _, _ -> itemJson }
        repository(server).update(
            "i1",
            linkedMapOf("version" to 3, "amount" to BigDecimal("1234.56"), "category" to null, "installments" to 3L),
        )
        assertEquals(
            Triple("PATCH", "/api/inbox/i1", """{"version":3,"amount":1234.56,"category":null,"installments":3}"""),
            server.calls.single(),
        )
    }

    @Test
    fun denyAndRestoreSendOnlyTheVersion() = runTest {
        val server = FakeServer { _, _, _ -> itemJson }
        val repo = repository(server)
        repo.deny("i1", 3)
        repo.restore("i1", null)
        assertEquals(Triple("POST", "/api/inbox/i1/deny", """{"version":3}"""), server.calls[0])
        // Sem versao, a chave nao vai (o undefined do JS).
        assertEquals(Triple("POST", "/api/inbox/i1/restore", "{}"), server.calls[1])
    }

    @Test
    fun a409IsAConflictNeverARefusal() = runTest {
        val server = FakeServer { _, _, _ -> throw ApiException.Http(409, "Este item ja foi decidido (talvez em outro aparelho).") }
        val result = repository(server).deny("i1", 3)
        assertEquals(InboxWrite.Conflict("Este item ja foi decidido (talvez em outro aparelho)."), result)
    }

    @Test
    fun aServerRefusalKeepsItsMessage() = runTest {
        val server = FakeServer { _, _, _ -> throw ApiException.Http(400, "Escolha o cartão.") }
        assertEquals(InboxWrite.Refused(400, "Escolha o cartão."), repository(server).approve("i1", mapOf("version" to 3)))
    }

    @Test
    fun noConnectionARedirectOrAStrangeAnswerIsOfflineAndNothingIsQueued() = runTest {
        val repo = repository(FakeServer { _, _, _ -> throw ApiException.Network(null) })
        assertEquals(InboxWrite.Offline, repo.approve("i1", mapOf("version" to 3)))
        assertEquals(InboxWrite.Offline, repository(FakeServer { _, _, _ -> throw ApiException.Http(302, null) }).deny("i1", 1))
        assertEquals(InboxWrite.Offline, repository(FakeServer { _, _, _ -> "<html>portal</html>" }).deny("i1", 1))
    }

    @Test
    fun a401IsSessionExpired() = runTest {
        val result = repository(FakeServer { _, _, _ -> throw ApiException.Unauthorized("Token expirado") }).deny("i1", 1)
        assertEquals(InboxWrite.SessionExpired("Token expirado"), result)
    }

    @Test
    fun splitApproveReadyHintAndSettings() = runTest {
        val server = FakeServer { method, path, _ ->
            when {
                path.endsWith("/split") -> """{"item":$itemJson,"new_item":${itemJson.replace("\"i1\"", "\"i2\"")},"pending_count":5}"""
                path == "/api/inbox/approve-ready" ->
                    """{"approved":["i1"],"skipped":[{"id":"i2","reason":"needs_decision"}],"pending_count":1}"""
                method == "DELETE" -> """{"deleted":true}"""
                else -> """{"always_ask":false}"""
            }
        }
        val repo = repository(server)

        val split = (repo.split("i1", linkedMapOf("version" to 3, "source" to "notification", "source_id" to "d1")) as InboxWrite.Done).value
        assertEquals("i2", split.newItem?.id)
        assertEquals(5, split.pendingCount)
        assertEquals("""{"version":3,"source":"notification","source_id":"d1"}""", server.calls[0].third)

        val ready = (repo.approveReady(listOf("i1", "i2")) as InboxWrite.Done).value
        assertEquals(listOf("i1"), ready.approved)
        assertEquals("1 aprovado, 1 ficou para você decidir.", br.financas.app.rules.InboxRules.approveReadySummary(ready.rule))
        assertEquals("""{"ids":["i1","i2"]}""", server.calls[1].third)

        assertEquals(InboxWrite.Done(Unit), repo.forgetHint("h 1"))
        assertEquals(Triple("DELETE", "/api/inbox/hints/h%201", null), server.calls[2])

        assertFalse((repo.setAlwaysAsk(false) as InboxWrite.Done).value.alwaysAsk)
        assertEquals(Triple("PATCH", "/api/inbox/settings", """{"always_ask":false}"""), server.calls[3])
    }

    @Test
    fun theDtoGivesTheRulesWhatTheyRead() {
        val item = ApiJson.decodeFromString(InboxItemDto.serializer(), itemJson)
        val rule = item.rule
        assertEquals("CARD", rule.entryType)
        assertEquals(listOf("card"), rule.confirm)
        assertEquals("Itaú", rule.sources?.single()?.appLabel)
        assertNull(rule.recurring)
        assertEquals("Itaú Visa", br.financas.app.rules.InboxRules.targetText(rule))
    }
}
