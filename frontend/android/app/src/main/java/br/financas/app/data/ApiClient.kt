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
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
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

/** Um arquivo baixado da API: os bytes, o Content-Type e o nome do Content-Disposition. */
class Downloaded(val status: Int, val bytes: ByteArray, val contentType: String?, val fileName: String?)

/** Uma leitura da API: o corpo da resposta, como texto (o ReadCache guarda esse texto). */
fun interface Fetcher {
    suspend fun get(path: String): String
}

/**
 * O cliente HTTP das telas nativas. O endereco e o token vem da sessao do login nativo
 * (outbox/Session.java, lida a cada pedido): nenhum outro lugar para o token.
 *
 * Um 401 (ou nenhuma sessao) chama [onUnauthorized] com o token que o pedido usou (null sem
 * sessao) — o AppGraph apaga a sessao se ainda for aquela e a casca volta ao login — e vira
 * [ApiException.Unauthorized].
 */
class ApiClient(
    private val session: () -> SessionInfo?,
    private val http: OkHttpClient = defaultHttpClient(),
    private val onUnauthorized: (token: String?) -> Unit = {},
    private val io: CoroutineDispatcher = Dispatchers.IO,
) : Fetcher, FileApi {

    override suspend fun get(path: String): String = send("GET", path, null)

    /** Um pedido com corpo JSON (PATCH, DELETE, POST fora da fila). Devolve o corpo da resposta. */
    suspend fun send(method: String, path: String, jsonBody: String?): String = withContext(io) {
        // Session.load decifra o token com a chave do Keystore: fora da thread da tela.
        val current = session()
        if (current == null) {
            onUnauthorized(null)
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
                onUnauthorized(current.token)
                throw ApiException.Unauthorized(serverMessage(text))
            }
            else -> throw ApiException.Http(status, serverMessage(text))
        }
    }

    /**
     * Um arquivo num POST multipart (o campo [field], como o FormData da web): os comprovantes.
     * Devolve o corpo da resposta.
     */
    override suspend fun upload(path: String, field: String, fileName: String, mimeType: String, bytes: ByteArray): String =
        withContext(io) {
            val body = MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .addFormDataPart(field, fileName, bytes.toRequestBody(mimeType.toMediaTypeOrNull()))
                .build()
            val request = authorized(path)?.post(body)?.build() ?: throw ApiException.Unauthorized(null)
            val (status, text) = execute(http.newCall(request))
            check(status, text, tokenOf(request))
            text
        }

    /** Os bytes de um GET (comprovante, exportacao), com o tipo e o nome que o servidor mandou. */
    override suspend fun download(path: String): Downloaded = withContext(io) {
        val request = authorized(path)?.get()?.build() ?: throw ApiException.Unauthorized(null)
        val call = http.newCall(request)
        val result = suspendCancellableCoroutine<Downloaded> { continuation ->
            continuation.invokeOnCancellation { call.cancel() }
            call.enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    if (continuation.isActive) continuation.resumeWithException(ApiException.Network(e))
                }

                override fun onResponse(call: Call, response: Response) {
                    val value = try {
                        response.use {
                            Downloaded(
                                status = it.code,
                                bytes = it.body?.bytes() ?: ByteArray(0),
                                contentType = it.header("Content-Type"),
                                fileName = fileNameOf(it.header("Content-Disposition")),
                            )
                        }
                    } catch (error: IOException) {
                        if (continuation.isActive) continuation.resumeWithException(ApiException.Network(error))
                        return
                    }
                    if (continuation.isActive) continuation.resume(value)
                }
            })
        }
        if (result.status !in 200..299) check(result.status, String(result.bytes, Charsets.UTF_8), tokenOf(request))
        result
    }

    // O pedido com o endereco e o token da sessao; null (e o aviso de login) sem sessao.
    private fun authorized(path: String): Request.Builder? {
        val current = session()
        if (current == null) {
            onUnauthorized(null)
            return null
        }
        val url = try {
            (current.baseUrl.trimEnd('/') + path).toHttpUrl()
        } catch (error: IllegalArgumentException) {
            throw ApiException.Network(error)
        }
        return Request.Builder()
            .url(url)
            .header("Authorization", "Bearer " + current.token)
    }

    // O token do cabecalho do pedido (o que o 401 recusou).
    private fun tokenOf(request: Request): String? = request.header("Authorization")?.removePrefix("Bearer ")

    private fun check(status: Int, text: String, token: String?) {
        when {
            status in 200..299 -> Unit
            status == 401 -> {
                onUnauthorized(token)
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

        /**
         * Uma escrita que nao e criacao (pagar fatura, lancar recorrencias): sem prazo de resposta,
         * como na web (lib/api.js: edicao e exclusao nao tem timeout) — uma que estourasse o prazo
         * podia ter passado, e a tela diria "sem conexao" de algo feito. So a conexao tem prazo:
         * sem conectar, o pedido nao saiu.
         */
        fun writeHttpClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(CONNECT_TIMEOUT_SECONDS, TimeUnit.SECONDS)
            .readTimeout(0, TimeUnit.SECONDS)
            .writeTimeout(0, TimeUnit.SECONDS)
            .callTimeout(0, TimeUnit.SECONDS)
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

        private val FILENAME_STAR = Regex("filename\\*=(?:UTF-8'')?([^;]+)", RegexOption.IGNORE_CASE)
        private val FILENAME = Regex("filename=\"?([^\";]+)\"?", RegexOption.IGNORE_CASE)

        /** O nome do arquivo do Content-Disposition (filename*= UTF-8 primeiro); null sem nome. */
        fun fileNameOf(disposition: String?): String? {
            if (disposition.isNullOrBlank()) return null
            FILENAME_STAR.find(disposition)?.let { match ->
                val raw = match.groupValues[1].trim().trim('"')
                return runCatching { java.net.URLDecoder.decode(raw, "UTF-8") }.getOrDefault(raw).ifBlank { null }
            }
            return FILENAME.find(disposition)?.groupValues?.get(1)?.trim()?.ifBlank { null }
        }

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
