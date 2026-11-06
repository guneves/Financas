package br.financas.app.data

import br.financas.app.outbox.DeviceKey
import okhttp3.Interceptor
import okhttp3.Response

/**
 * Poe a chave de acesso remoto (outbox/DeviceKey.java, o X-Device-Key do proxy da porta 8443) em
 * todo pedido do OkHttp: as telas (ApiClient) e o login (AuthRepository). [key] e lida a cada
 * pedido, entao uma chave trocada vale ja no proximo. Sem chave, o pedido sai sem o cabecalho.
 */
class DeviceKeyInterceptor(private val key: () -> String?) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val value = DeviceKey.normalize(key())
        val request = chain.request()
        if (value.isEmpty()) return chain.proceed(request)
        return chain.proceed(request.newBuilder().header(DeviceKey.HEADER, value).build())
    }
}

/** O 401 do proxy de autenticacao (chave ausente ou errada), nao o do app. */
internal fun Response.isProxyAuthRequired(): Boolean =
    DeviceKey.isProxyAuthRequired(code, header(DeviceKey.PROXY_AUTH_HEADER))
