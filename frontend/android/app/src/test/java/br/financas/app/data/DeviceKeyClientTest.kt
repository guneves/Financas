package br.financas.app.data

import br.financas.app.outbox.DeviceKey
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import java.util.concurrent.TimeUnit

/** A chave de acesso remoto (X-Device-Key) e o 401 do proxy nos clientes OkHttp. */
class DeviceKeyClientTest {

    private lateinit var server: MockWebServer
    private var key: String? = "chave-1"
    private var unauthorizedCalls = 0
    private var proxyCalls = 0

    private val http = OkHttpClient.Builder().callTimeout(5, TimeUnit.SECONDS).followRedirects(false).build()

    private fun client() = ApiClient(
        session = { SessionInfo(server.url("/").toString(), "token-123", "u1") },
        http = http,
        onUnauthorized = { unauthorizedCalls += 1 },
        io = Dispatchers.IO,
        deviceKey = { key },
        onProxyAuth = { proxyCalls += 1 },
    )

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
    }

    @After
    fun tearDown() {
        try {
            server.shutdown()
        } catch (ignored: Exception) {
        }
    }

    private fun proxy401() = MockResponse().setResponseCode(401).setHeader("X-Proxy-Auth", "required")

    @Test
    fun everyKindOfRequestCarriesTheKey() = runBlocking {
        server.enqueue(MockResponse().setBody("[]"))
        server.enqueue(MockResponse().setBody("{}"))
        server.enqueue(MockResponse().setBody("{}"))
        server.enqueue(MockResponse().setBody("bytes"))
        val api = client()
        api.get("/api/accounts")
        api.send("PATCH", "/api/accounts/1", "{}")
        api.upload("/api/attachments", "file", "a.pdf", "application/pdf", ByteArray(3))
        api.download("/api/attachments/1")
        repeat(4) {
            val request = server.takeRequest()
            assertEquals("chave-1", request.getHeader(DeviceKey.HEADER))
            assertEquals("Bearer token-123", request.getHeader("Authorization"))
        }
    }

    @Test
    fun aChangedKeyCountsOnTheNextRequest() = runBlocking {
        server.enqueue(MockResponse().setBody("[]"))
        server.enqueue(MockResponse().setBody("[]"))
        val api = client()
        api.get("/api/accounts")
        key = "chave-2"
        api.get("/api/accounts")
        assertEquals("chave-1", server.takeRequest().getHeader(DeviceKey.HEADER))
        assertEquals("chave-2", server.takeRequest().getHeader(DeviceKey.HEADER))
    }

    @Test
    fun withoutAKeyTheHeaderIsAbsent() = runBlocking {
        key = null
        server.enqueue(MockResponse().setBody("[]"))
        client().get("/api/accounts")
        assertNull(server.takeRequest().getHeader(DeviceKey.HEADER))
    }

    @Test
    fun theProxy401AsksForTheKeyAndKeepsTheLogin() = runBlocking {
        server.enqueue(proxy401())
        try {
            client().get("/api/accounts")
            fail("Esperava ProxyAuth")
        } catch (error: ApiException.ProxyAuth) {
            // Um Network: a leitura mostra o cache, a criacao vai para a fila.
            assertTrue((error as ApiException) is ApiException.Network)
            assertEquals(DeviceKey.MESSAGE, error.message)
        }
        assertEquals(1, proxyCalls)
        assertEquals(0, unauthorizedCalls)
    }

    @Test
    fun theProxy401OnUploadAndDownloadToo() = runBlocking {
        server.enqueue(proxy401())
        server.enqueue(proxy401())
        val api = client()
        try {
            api.upload("/api/attachments", "file", "a.pdf", "application/pdf", ByteArray(3))
            fail("Esperava ProxyAuth")
        } catch (error: ApiException.ProxyAuth) {
        }
        try {
            api.download("/api/attachments/1")
            fail("Esperava ProxyAuth")
        } catch (error: ApiException.ProxyAuth) {
        }
        assertEquals(2, proxyCalls)
        assertEquals(0, unauthorizedCalls)
    }

    @Test
    fun theApp401IsStillASessionExpiry() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(401).setBody("""{"message":"Token expirado"}"""))
        try {
            client().get("/api/accounts")
            fail("Esperava Unauthorized")
        } catch (error: ApiException.Unauthorized) {
        }
        assertEquals(1, unauthorizedCalls)
        assertEquals(0, proxyCalls)
    }

    @Test
    fun theLoginCarriesTheKey() = runBlocking {
        server.enqueue(MockResponse().setBody("""{"user":{"id":"u1"},"access_token":"tok"}"""))
        val result = AuthRepository(deviceKey = { "chave-1" }).login(server.url("/").toString(), "a@b.c", "x")
        assertEquals(LoginResult.Done("u1", "tok", null), result)
        assertEquals("chave-1", server.takeRequest().getHeader(DeviceKey.HEADER))
    }

    @Test
    fun theLoginRefusedByTheProxyAsksForTheKey() = runBlocking {
        server.enqueue(proxy401())
        val result = AuthRepository(deviceKey = { "errada" }).login(server.url("/").toString(), "a@b.c", "x")
        assertEquals(LoginResult.KeyNeeded, result)
    }
}
