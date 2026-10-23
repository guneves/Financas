package br.financas.app.data

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

class ApiClientTest {

    private lateinit var server: MockWebServer
    private var unauthorizedCalls = 0
    private var session: SessionInfo? = null

    private val http = OkHttpClient.Builder()
        .callTimeout(5, TimeUnit.SECONDS)
        .followRedirects(false)
        .build()

    private fun client() = ApiClient(
        session = { session },
        http = http,
        onUnauthorized = { unauthorizedCalls += 1 },
        io = Dispatchers.IO,
    )

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        // A barra no fim do endereco guardado nao dobra no caminho.
        session = SessionInfo(server.url("/").toString(), "token-123", "u1")
    }

    @After
    fun tearDown() {
        try {
            server.shutdown()
        } catch (ignored: Exception) {
        }
    }

    private inline fun <reified E : ApiException> failure(block: () -> Unit): E {
        try {
            block()
        } catch (error: ApiException) {
            if (error is E) return error
            fail("Esperava ${E::class.simpleName}, veio $error")
        }
        fail("Esperava ${E::class.simpleName}, o pedido deu certo")
        throw IllegalStateException()
    }

    @Test
    fun aSuccessfulReadReturnsTheBodyAndSendsTheToken() = runBlocking {
        server.enqueue(MockResponse().setBody("""[{"id":"a"}]"""))
        val body = client().get("/api/accounts?include_archived=1")
        assertEquals("""[{"id":"a"}]""", body)
        val request = server.takeRequest()
        assertEquals("/api/accounts?include_archived=1", request.path)
        assertEquals("GET", request.method)
        assertEquals("Bearer token-123", request.getHeader("Authorization"))
        assertEquals(0, unauthorizedCalls)
    }

    @Test
    fun a401IsUnauthorizedAndCallsTheHandler() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(401).setBody("""{"message": "Token invalido ou expirado."}"""))
        val error = failure<ApiException.Unauthorized> { runBlocking { client().get("/api/accounts") } }
        assertEquals("Token invalido ou expirado.", error.serverMessage)
        assertEquals(1, unauthorizedCalls)
    }

    @Test
    fun noSessionIsUnauthorizedWithoutARequest() = runBlocking {
        session = null
        val error = failure<ApiException.Unauthorized> { runBlocking { client().get("/api/accounts") } }
        assertNull(error.serverMessage)
        assertEquals(1, unauthorizedCalls)
        assertEquals(0, server.requestCount)
    }

    @Test
    fun aRefusalKeepsTheServerMessageAsIs() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(400).setBody("""{"error": "Conta nao encontrada."}"""))
        val error = failure<ApiException.Http> { runBlocking { client().send("PATCH", "/api/accounts/x", """{"name":"a"}""") } }
        assertEquals(400, error.status)
        assertEquals("Conta nao encontrada.", error.serverMessage)
        assertEquals(0, unauthorizedCalls)
        val request = server.takeRequest()
        assertEquals("PATCH", request.method)
        assertEquals("""{"name":"a"}""", request.body.readUtf8())
    }

    @Test
    fun aServerErrorWithoutJsonHasNoMessage() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(502).setBody("<html>Bad gateway</html>"))
        val error = failure<ApiException.Http> { runBlocking { client().get("/api/accounts") } }
        assertEquals(502, error.status)
        assertNull(error.serverMessage)
    }

    @Test
    fun aRedirectIsNotFollowed() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(302).setHeader("Location", "http://portal.invalid/"))
        val error = failure<ApiException.Http> { runBlocking { client().get("/api/accounts") } }
        assertEquals(302, error.status)
    }

    @Test
    fun noServerIsANetworkFailure() = runBlocking {
        server.shutdown()
        failure<ApiException.Network> { runBlocking { client().get("/api/accounts") } }
        assertEquals(0, unauthorizedCalls)
    }

    @Test
    fun aBrokenBaseUrlIsANetworkFailure() = runBlocking {
        session = SessionInfo("nao e um endereco", "t", "u1")
        failure<ApiException.Network> { runBlocking { client().get("/api/accounts") } }
        Unit
    }

    @Test
    fun aPostWithoutBodySendsAnEmptyObject() = runBlocking {
        server.enqueue(MockResponse().setBody("{}"))
        client().send("POST", "/api/recurring/run", null)
        assertEquals("{}", server.takeRequest().body.readUtf8())
    }

    @Test
    fun serverMessageReadsErrorThenMessage() {
        assertEquals("a", ApiClient.serverMessage("""{"error": "a", "message": "b"}"""))
        assertEquals("b", ApiClient.serverMessage("""{"message": "b"}"""))
        assertNull(ApiClient.serverMessage("""{"error": ""}"""))
        assertNull(ApiClient.serverMessage("""[1]"""))
        assertNull(ApiClient.serverMessage("nao e json"))
        assertNull(ApiClient.serverMessage(""))
        assertNull(ApiClient.serverMessage(null))
        assertTrue(ApiException.Http(500, null).message!!.contains("500"))
    }
}
