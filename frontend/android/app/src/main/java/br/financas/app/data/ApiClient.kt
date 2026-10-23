package br.financas.app.data

import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import okhttp3.Call
import okhttp3.Callback
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** O que as telas nativas precisam da sessao (outbox/Session.java), sem depender do Android. */
data class SessionInfo(val baseUrl: String, val token: String, val userId: String)

/**
 * Por que um pedido nao deu certo. Tres casos que a tela trata diferente:
 * - [Network]: o pedido nao chegou (sem rede, Tailscale fora, tempo esgotado). Leitura mostra o
 *   cache; criacao vai para a fila (outbox).
 * - [Unauthorized]: sem login ou 401. Para tudo, pede para entrar de novo (como o outbox).
 * - [Http]: o servidor respondeu e recusou. [serverMessage] e o "error" do JSON, em portugues,
 *   mostrado como chegou; null quando a resposta nao trouxe mensagem.
 * - [BadResponse]: 2xx que nao e o JSON esperado (portal de Wi-Fi, proxy). Nunca vai para o cache.
 */
sealed class ApiException(message: String, cause: Throwable? = null) : Exception(message, cause) {

    class Network(cause: Throwable?) : ApiException("Sem conexao com o servidor", cause)

    class Unauthorized(val serverMessage: String?) : ApiException(serverMessage ?: "Sessao expirada")

    class Http(val status: Int, val serverMessage: String?) :
        ApiException(serverMessage ?: "Erro $status do servidor")

    class BadResponse(cause: Throwable?) : ApiException("Resposta inesperada do servidor", cause)
}

/** Uma leitura da API: o corpo da resposta, como texto (o ReadCache guarda esse texto). */
fun interface Fetcher {
    suspend fun get(path: String): String
}

/**
 * O cliente HTTP das telas nativas. O endereco e o token vem da sessao que a WebView entregou
 * (outbox/Session.java, lida a cada pedido): nada de segundo login nem outro lugar para o token.
 *
 * Um 401 (ou nenhuma sessao) chama [onUnauthorized] — o AppGraph liga isso ao mesmo aviso do
 * outbox (LoginNotifier) — e vira [ApiException.Unauthorized].
 */
class ApiClient(
    private val session: () -> SessionInfo?,
    private val http: OkHttpClient = defaultHttpClient(),
    private val onUnauthorized: () -> Unit = {},
    private val io: CoroutineDispatcher = Dispatchers.IO,
) : Fetcher {

    override suspend fun get(path: String): String = send("GET", path, null)

    /** Um pedido com corpo JSON (PATCH, DELETE, POST fora da fila). Devolve o corpo da resposta. */
    suspend fun send(method: String, path: String, jsonBody: String?): String = withContext(io) {
        // Session.load decifra o token com a chave do Keystore: fora da thread da tela.
        val current = session()
        if (current == null) {
            onUnauthorized()
            throw ApiException.Unauthorized(null)
        }
        val url = try {
            (current.baseUrl.trimEnd('/') + path).toHttpUrl()
        } catch (error: IllegalArgumentException) {
            // Endereco guardado invalido: para a tela e o mesmo que nao alcancar o servidor.
            throw ApiException.Network(error)
        }
        val upper = method.uppercase()
        val body = jsonBody?.toRequestBody(JSON_MEDIA_TYPE)
            ?: if (upper in METHODS_WITH_BODY) "{}".toRequestBody(JSON_MEDIA_TYPE) else null
        val request = Request.Builder()
            .url(url)
            .header("Authorization", "Bearer " + current.token)
            .header("Accept", "application/json")
            .method(upper, body)
            .build()
        val (status, text) = execute(http.newCall(request))
        when {
            status in 200..299 -> text
            status == 401 -> {
                onUnauthorized()
                throw ApiException.Unauthorized(serverMessage(text))
            }
            else -> throw ApiException.Http(status, serverMessage(text))
        }
    }

    private suspend fun execute(call: Call): Pair<Int, String> =
        suspendCancellableCoroutine { continuation ->
            continuation.invokeOnCancellation { call.cancel() }
            call.enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    if (continuation.isActive) continuation.resumeWithException(ApiException.Network(e))
                }

                override fun onResponse(call: Call, response: Response) {
                    val result = try {
                        response.use { it.code to (it.body?.string() ?: "") }
                    } catch (error: IOException) {
                        if (continuation.isActive) continuation.resumeWithException(ApiException.Network(error))
                        return
                    }
                    if (continuation.isActive) continuation.resume(result)
                }
            })
        }

    companion object {
        private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
        private val METHODS_WITH_BODY = setOf("POST", "PUT", "PATCH")

        /** Leituras esperam ate 45 s, como na web (lib/api.js); conectar, 15 s, como o outbox. */
        const val READ_TIMEOUT_SECONDS = 45L
        const val CONNECT_TIMEOUT_SECONDS = 15L

        /**
         * Uma criacao do "+ Novo" espera 6 s, como na web (lib/outbox.js, CREATE_TIMEOUT_MS):
         * sem resposta nesse prazo vai para a fila, e o client_id torna o reenvio seguro.
         */
        const val CREATE_TIMEOUT_SECONDS = 6L

        fun creationHttpClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(CREATE_TIMEOUT_SECONDS, TimeUnit.SECONDS)
            .readTimeout(CREATE_TIMEOUT_SECONDS, TimeUnit.SECONDS)
            .writeTimeout(CREATE_TIMEOUT_SECONDS, TimeUnit.SECONDS)
            .callTimeout(CREATE_TIMEOUT_SECONDS, TimeUnit.SECONDS)
            .followRedirects(false)
            .followSslRedirects(false)
            .build()

        fun defaultHttpClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(CONNECT_TIMEOUT_SECONDS, TimeUnit.SECONDS)
            .readTimeout(READ_TIMEOUT_SECONDS, TimeUnit.SECONDS)
            .callTimeout(READ_TIMEOUT_SECONDS, TimeUnit.SECONDS)
            // Um redirecionamento (portal de Wi-Fi) nunca passa por resposta da API: chega como
            // 3xx e vira ApiException.Http, como no outbox.
            .followRedirects(false)
            .followSslRedirects(false)
            .build()

        /** A mensagem do servidor: "error" do JSON, senao "message" (o 401); senao null. */
        fun serverMessage(body: String?): String? {
            if (body.isNullOrBlank()) return null
            val parsed = try {
                ApiJson.parseToJsonElement(body)
            } catch (error: Exception) {
                return null
            }
            if (parsed !is JsonObject) return null
            for (key in listOf("error", "message")) {
                val value = parsed[key]
                if (value is JsonPrimitive && value.isString && value.content.isNotBlank()) return value.content
            }
            return null
        }
    }
}
