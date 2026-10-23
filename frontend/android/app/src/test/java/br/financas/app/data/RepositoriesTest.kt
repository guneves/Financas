package br.financas.app.data

import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

class RepositoriesTest {

    /** Cache em memoria, com relogio controlado. */
    private class MemoryCache(var now: Long = 100L) : ReadCache {
        val entries = mutableMapOf<String, CachedBody>()
        override fun get(key: String) = entries[key]
        override fun put(key: String, body: String) = CachedBody(body, now).also { entries[key] = it }
        override fun clear() = entries.clear()
    }

    /** O servidor de mentira: responde o que a vez pede e anota os caminhos. */
    private class FakeFetcher(var answer: () -> String) : Fetcher {
        val paths = mutableListOf<String>()
        override suspend fun get(path: String): String {
            paths += path
            return answer()
        }
    }

    private val accountsJson = """[{"id":"a1","name":"Nubank","is_default":true,"balance":10.5}]"""
    private val newerJson = """[{"id":"a1","name":"Nubank","is_default":true,"balance":20}]"""

    private fun TestScope.reader(fetcher: Fetcher, cache: ReadCache, user: String? = "u1") =
        CachedReader(fetcher, cache, { user }, io = UnconfinedTestDispatcher(testScheduler))

    @Test
    fun withoutCacheOnlyTheFreshCopyArrivesAndIsStored() = runTest {
        val cache = MemoryCache(now = 500L)
        val fetcher = FakeFetcher { accountsJson }
        val loads = AccountsRepository(reader(fetcher, cache)).accounts().toList()

        assertEquals(1, loads.size)
        val fresh = loads[0] as Load.Fresh
        assertEquals(BigDecimal("10.5"), fresh.value.single().balance)
        assertEquals(500L, fresh.storedAt)
        assertEquals(accountsJson, cache.entries["u1 /api/accounts"]?.body)
        assertEquals(listOf("/api/accounts"), fetcher.paths)
    }

    @Test
    fun theCachedCopyComesFirstThenTheFreshOne() = runTest {
        val cache = MemoryCache(now = 100L)
        cache.put("u1 /api/accounts", accountsJson)
        cache.now = 900L
        val loads = AccountsRepository(reader(FakeFetcher { newerJson }, cache)).accounts().toList()

        assertEquals(2, loads.size)
        val cached = loads[0] as Load.Cached
        assertEquals(BigDecimal("10.5"), cached.value.single().balance)
        assertEquals(100L, cached.storedAt)
        val fresh = loads[1] as Load.Fresh
        assertEquals(BigDecimal("20"), fresh.value.single().balance)
        assertEquals(900L, fresh.storedAt)
        assertEquals(CachedBody(newerJson, 900L), cache.entries["u1 /api/accounts"])
    }

    @Test
    fun aFailureKeepsTheCachedCopy() = runTest {
        val cache = MemoryCache()
        cache.put("u1 /api/accounts", accountsJson)
        val loads = AccountsRepository(reader(FakeFetcher { throw ApiException.Network(null) }, cache))
            .accounts().toList()

        assertEquals(2, loads.size)
        assertTrue(loads[0] is Load.Cached)
        val failed = loads[1] as Load.Failed
        assertTrue(failed.error is ApiException.Network)
        assertEquals(loads[0], failed.cached)
        assertEquals(accountsJson, cache.entries["u1 /api/accounts"]?.body)
    }

    @Test
    fun aFailureWithoutCacheHasNothingToShow() = runTest {
        val loads = CardsRepository(reader(FakeFetcher { throw ApiException.Http(500, null) }, MemoryCache()))
            .cards().toList()

        val failed = loads.single() as Load.Failed
        assertEquals(500, (failed.error as ApiException.Http).status)
        assertNull(failed.cached)
    }

    @Test
    fun anUnexpectedBodyIsAnErrorAndNeverReplacesTheCache() = runTest {
        val cache = MemoryCache()
        cache.put("u1 /api/accounts", accountsJson)
        val loads = AccountsRepository(reader(FakeFetcher { "<html>portal do Wi-Fi</html>" }, cache))
            .accounts().toList()

        val failed = loads.last() as Load.Failed
        assertTrue(failed.error is ApiException.BadResponse)
        assertEquals(accountsJson, cache.entries["u1 /api/accounts"]?.body)
    }

    @Test
    fun aDamagedCachedCopyIsSkipped() = runTest {
        val cache = MemoryCache()
        cache.put("u1 /api/accounts", "{quebrado")
        val loads = AccountsRepository(reader(FakeFetcher { accountsJson }, cache)).accounts().toList()

        assertEquals(1, loads.size)
        assertTrue(loads[0] is Load.Fresh)
    }

    @Test
    fun anotherUserNeverSeesTheCachedCopy() = runTest {
        val cache = MemoryCache()
        cache.put("u1 /api/accounts", accountsJson)
        val loads = AccountsRepository(reader(FakeFetcher { throw ApiException.Network(null) }, cache, user = "u2"))
            .accounts().toList()

        val failed = loads.single() as Load.Failed
        assertNull(failed.cached)
    }

    @Test
    fun anUnauthorizedReadKeepsTheCopyAndSaysSo() = runTest {
        val cache = MemoryCache()
        cache.put("u1 /api/credit-cards", """[{"id":"k1","name":"Itaú","due_day":10,"credit_enabled":1}]""")
        val loads = CardsRepository(reader(FakeFetcher { throw ApiException.Unauthorized("Token expirado.") }, cache))
            .cards().toList()

        val failed = loads.last() as Load.Failed
        assertEquals("Token expirado.", (failed.error as ApiException.Unauthorized).serverMessage)
        assertEquals("Itaú", failed.cached?.value?.single()?.name)
    }

    @Test
    fun pathsAreTheWebOnes() = runTest {
        val fetcher = FakeFetcher { "[]" }
        val reader = reader(fetcher, MemoryCache())
        AccountsRepository(reader).accounts().toList()
        AccountsRepository(reader).accounts(includeArchived = true).toList()
        CategoriesRepository(reader).categories().toList()
        CategoriesRepository(reader).categories(includeArchived = true).toList()
        CardsRepository(reader).cards().toList()
        assertEquals(
            listOf(
                "/api/accounts",
                "/api/accounts?include_archived=1",
                "/api/categories",
                "/api/categories?include_archived=1",
                "/api/credit-cards",
            ),
            fetcher.paths,
        )
    }
}
