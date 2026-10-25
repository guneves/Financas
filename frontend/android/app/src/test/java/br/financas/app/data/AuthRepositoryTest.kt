package br.financas.app.data

import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class AuthRepositoryTest {

    private lateinit var server: MockWebServer

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

    private fun base() = server.url("/").toString()

    @Test
    fun aLoginSendsEmailAndPasswordWithoutToken() = runBlocking {
        server.enqueue(MockResponse().setBody("""{"user":{"id":"u1","email":"a@b.c","username":"Ana","created_at":"x"},"access_token":"tok"}"""))
        val result = AuthRepository().login(base(), "  a@b.c ", "segredo")
        assertEquals(LoginResult.Done("u1", "tok", "Ana"), result)
        val request = server.takeRequest()
        assertEquals("POST", request.method)
        assertEquals("/api/auth/login", request.path)
        assertNull(request.getHeader("Authorization"))
        assertEquals("""{"email":"a@b.c","password":"segredo"}""", request.body.readUtf8())
    }

    @Test
    fun aRefusalKeepsTheServersText() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(401).setBody("""{"error":"Email ou senha invalidos."}"""))
        assertEquals(LoginResult.Refused("Email ou senha invalidos."), AuthRepository().login(base(), "a@b.c", "x"))
    }

    @Test
    fun aPortalOrABrokenAnswerIsOffline() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(302).setHeader("Location", "http://portal"))
        assertEquals(LoginResult.Offline, AuthRepository().login(base(), "a@b.c", "x"))
        server.enqueue(MockResponse().setBody("<html>"))
        assertEquals(LoginResult.Offline, AuthRepository().login(base(), "a@b.c", "x"))
    }

    @Test
    fun noServerIsOffline() = runBlocking {
        val gone = base()
        server.shutdown()
        assertTrue(AuthRepository().login(gone, "a@b.c", "x") is LoginResult.Offline)
    }
}
