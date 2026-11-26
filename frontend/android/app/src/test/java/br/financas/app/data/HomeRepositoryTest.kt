package br.financas.app.data

import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.IOException

/** O puxar para atualizar do Inicio: POST /api/open-finance/refresh (dono 2026-11-26). */
class HomeRepositoryTest {

    private class MemoryCache : ReadCache {
        override fun get(key: String): CachedBody? = null
        override fun put(key: String, body: String) = CachedBody(body, 1L)
        override fun clear() = Unit
    }

    private class FakeServer(var answer: () -> String) : Fetcher, Sender {
        val calls = mutableListOf<Triple<String, String, String?>>()
        override suspend fun get(path: String): String = send("GET", path, null)
        override suspend fun send(method: String, path: String, jsonBody: String?): String {
            calls += Triple(method, path, jsonBody)
            return answer()
        }
    }

    private fun kotlinx.coroutines.test.TestScope.repository(server: FakeServer) = HomeRepository(
        CachedReader(server, MemoryCache(), { "u1" }, io = UnconfinedTestDispatcher(testScheduler)),
        server,
    )

    @Test
    fun itAsksTheServerForWhatPluggyAlreadyHas() = runTest {
        val server = FakeServer { """{"pulled":2,"failed":0}""" }
        val result = repository(server).refreshBanks()
        assertEquals(InboxWrite.Done(2), result)
        assertEquals(listOf(Triple("POST", "/api/open-finance/refresh", "{}")), server.calls)
    }

    @Test
    fun nothingNewIsZero() = runTest {
        assertEquals(InboxWrite.Done(0), repository(FakeServer { """{"pulled":0,"failed":1}""" }).refreshBanks())
    }

    @Test
    fun anOldServerWithoutTheRouteIsRefusedNotACrash() = runTest {
        val server = FakeServer { throw ApiException.Http(404, "Not Found") }
        assertEquals(InboxWrite.Refused(404, "Not Found"), repository(server).refreshBanks())
    }

    @Test
    fun noNetworkIsOffline() = runTest {
        val server = FakeServer { throw ApiException.Network(IOException("sem rede")) }
        assertEquals(InboxWrite.Offline, repository(server).refreshBanks())
    }

    @Test
    fun anUnexpectedBodyCountsAsNothingPulled() {
        assertEquals(0, HomeRepository.pulledOf("<html>portal</html>"))
        assertEquals(0, HomeRepository.pulledOf("""{"other":1}"""))
        assertEquals(0, HomeRepository.pulledOf("[]"))
        assertEquals(3, HomeRepository.pulledOf("""{"pulled":3}"""))
    }
}
