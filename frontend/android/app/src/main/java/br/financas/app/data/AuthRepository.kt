package br.financas.app.data

import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.TimeUnit

/** O usuario da resposta do login. */
@Serializable
data class AuthUserDto(
    val id: String,
    val email: String? = null,
    val username: String? = null,
)

/** POST /api/auth/login -> { user, access_token }. */
@Serializable
data class LoginResponseDto(
    val user: AuthUserDto,
    @SerialName("access_token") val accessToken: String,
)

/** O fim de um login: entrou, o servidor recusou (a mensagem como veio) ou nao chegou. */
sealed class LoginResult {
    data class Done(val userId: String, val token: String, val username: String?) : LoginResult()
    data class Refused(val message: String?) : LoginResult()
    object Offline : LoginResult()
}

/**
 * O login nativo (mobile-docs/native/screens/00-shell.md): POST /api/auth/login sem token, no
 * endereco do servidor deste APK. O cadastro fica fechado no celular (o servidor so abre com
 * ALLOW_SIGNUP). Sem prazo curto: um login que nao chegou e repetido pelo dono.
 */
class AuthRepository(
    private val http: OkHttpClient = defaultHttpClient(),
    private val io: CoroutineDispatcher = Dispatchers.IO,
) {
    suspend fun login(baseUrl: String, email: String, password: String): LoginResult = withContext(io) {
        val url = try {
            (baseUrl.trimEnd('/') + LOGIN_PATH).toHttpUrl()
        } catch (error: IllegalArgumentException) {
            return@withContext LoginResult.Offline
        }
        val body = JsonBody.encode(mapOf("email" to email.trim(), "password" to password))
        val request = Request.Builder()
            .url(url)
            .header("Accept", "application/json")
            .post(body.toRequestBody(JSON))
            .build()
        val (status, text) = try {
            http.newCall(request).execute().use { it.code to (it.body?.string() ?: "") }
        } catch (error: IOException) {
            return@withContext LoginResult.Offline
        }
        if (status !in 200..299) {
            // Um 3xx e um portal de Wi-Fi, nao o servidor.
            if (status in 300..399) return@withContext LoginResult.Offline
            return@withContext LoginResult.Refused(ApiClient.serverMessage(text))
        }
        val parsed = try {
            ApiJson.decodeFromString(LoginResponseDto.serializer(), text)
        } catch (error: SerializationException) {
            return@withContext LoginResult.Offline
        } catch (error: IllegalArgumentException) {
            return@withContext LoginResult.Offline
        }
        if (parsed.accessToken.isEmpty() || parsed.user.id.isEmpty()) return@withContext LoginResult.Offline
        LoginResult.Done(parsed.user.id, parsed.accessToken, parsed.user.username)
    }

    companion object {
        const val LOGIN_PATH = "/api/auth/login"
        private val JSON = "application/json; charset=utf-8".toMediaType()

        fun defaultHttpClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(ApiClient.CONNECT_TIMEOUT_SECONDS, TimeUnit.SECONDS)
            .readTimeout(ApiClient.READ_TIMEOUT_SECONDS, TimeUnit.SECONDS)
            .callTimeout(ApiClient.READ_TIMEOUT_SECONDS, TimeUnit.SECONDS)
            .followRedirects(false)
            .followSslRedirects(false)
            .build()
    }
}
