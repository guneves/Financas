package br.financas.app.data

import kotlinx.coroutines.flow.Flow
import kotlinx.serialization.DeserializationStrategy
import kotlinx.serialization.SerializationException
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

/** Um pedido com corpo (o ApiClient.send no app; um falso nos testes). */
fun interface Sender {
    suspend fun send(method: String, path: String, jsonBody: String?): String
}

/**
 * O resultado de uma escrita so com o servidor (o nome vem de Aprovar). Nada vai para a fila: toda decisao precisa da resposta
 * do servidor (a versao do item e o 409 contam com isso).
 */
sealed interface InboxWrite<out T> {
    /** O servidor fez; [value] e a resposta lida. */
    data class Done<T>(val value: T) : InboxWrite<T>

    /** 409: outro aparelho mexeu no item (ou ja decidiu). A tela diz CONFLICT_MESSAGE e rele. */
    data class Conflict(val message: String?) : InboxWrite<Nothing>

    /** O servidor recusou (400, 404...): a mensagem dele, como chegou; null sem mensagem. */
    data class Refused(val status: Int, val message: String?) : InboxWrite<Nothing>

    /** O pedido nao chegou (ou nao se sabe se chegou): nada decidido daqui; reler antes de tentar. */
    data object Offline : InboxWrite<Nothing>

    /** 401 ou sem sessao. */
    data class SessionExpired(val message: String?) : InboxWrite<Nothing>
}

/**
 * Uma escrita so com o servidor (Aprovar, e o Inicio: pagar fatura, lancar recorrencias): o
 * corpo da resposta, ou por que nao deu. Um redirecionamento nunca e a API (portal de Wi-Fi): o
 * pedido nao chegou.
 */
suspend fun sendWrite(sender: Sender, method: String, path: String, body: String?): InboxWrite<String> = try {
    InboxWrite.Done(sender.send(method, path, body))
} catch (error: ApiException.Network) {
    InboxWrite.Offline
} catch (error: ApiException.BadResponse) {
    InboxWrite.Offline
} catch (error: ApiException.Unauthorized) {
    InboxWrite.SessionExpired(error.serverMessage)
} catch (error: ApiException.Http) {
    when {
        error.status in 300..399 -> InboxWrite.Offline
        error.status == 409 -> InboxWrite.Conflict(error.serverMessage)
        else -> InboxWrite.Refused(error.status, error.serverMessage)
    }
}

/**
 * Os itens dos avisos do celular sobre a API (a tela Aprovar saiu do celular; o que nao grava
 * sozinho se resolve em Revisar, no Extrato): as leituras com a copia guardada primeiro
 * (CachedReader), as escritas so com o servidor, sempre com a `version` do item no corpo.
 */
class InboxRepository(
    private val reader: CachedReader,
    private val sender: Sender,
    private val json: Json = ApiJson,
) {

    fun list(view: String): Flow<Load<InboxListDto>> = reader.read(listPath(view), InboxListDto.serializer())

    fun count(): Flow<Load<InboxCountDto>> = reader.read(COUNT_PATH, InboxCountDto.serializer())

    fun item(id: String): Flow<Load<InboxItemDto>> = reader.read(itemPath(id), InboxItemDto.serializer())

    fun hints(): Flow<Load<List<InboxHintDto>>> = reader.read(HINTS_PATH, ListSerializer(InboxHintDto.serializer()))

    fun settings(): Flow<Load<InboxSettingsDto>> = reader.read(SETTINGS_PATH, InboxSettingsDto.serializer())

    /** PATCH /api/inbox/<id>: escolha rapida, "Não é esta" ou a correcao da edicao. */
    suspend fun update(id: String, body: Map<String, Any?>): InboxWrite<InboxDecision> =
        decision("PATCH", itemPath(id), body)

    /** POST /api/inbox/<id>/approve: {version, remember}, com `candidate` no "É este" ou a correcao. */
    suspend fun approve(id: String, body: Map<String, Any?>): InboxWrite<InboxDecision> =
        decision("POST", itemPath(id) + "/approve", body)

    suspend fun deny(id: String, version: Int?): InboxWrite<InboxDecision> =
        decision("POST", itemPath(id) + "/deny", versionBody(version))

    suspend fun restore(id: String, version: Int?): InboxWrite<InboxDecision> =
        decision("POST", itemPath(id) + "/restore", versionBody(version))

    /** POST /api/inbox/<id>/split: {version, source, source_id}. */
    suspend fun split(id: String, body: Map<String, Any?>): InboxWrite<InboxSplitDto> =
        write("POST", itemPath(id) + "/split", body, InboxSplitDto.serializer())

    /** "Aprovar prontos": so os ids que a tela mostra como prontos. */
    suspend fun approveReady(ids: List<String>): InboxWrite<ApproveReadyDto> =
        write("POST", APPROVE_READY_PATH, mapOf("ids" to ids), ApproveReadyDto.serializer())

    /** Esquece uma escolha lembrada. Nenhum lancamento muda. */
    suspend fun forgetHint(id: String): InboxWrite<Unit> =
        when (val result = raw("DELETE", "$HINTS_PATH/${encode(id)}", null)) {
            is InboxWrite.Done -> InboxWrite.Done(Unit)
            is InboxWrite.Conflict -> result
            is InboxWrite.Refused -> result
            is InboxWrite.Offline -> result
            is InboxWrite.SessionExpired -> result
        }

    suspend fun setAlwaysAsk(value: Boolean): InboxWrite<InboxSettingsDto> =
        write("PATCH", SETTINGS_PATH, mapOf("always_ask" to value), InboxSettingsDto.serializer())

    /** "Gravar sozinho" (045): ligado, o servidor grava na hora o que esperava. */
    suspend fun setAutoRecord(value: Boolean): InboxWrite<InboxSettingsDto> =
        write("PATCH", SETTINGS_PATH, mapOf("auto_record" to value), InboxSettingsDto.serializer())

    // O item decidido vem com o pending_count no mesmo objeto.
    private suspend fun decision(method: String, path: String, body: Map<String, Any?>): InboxWrite<InboxDecision> =
        when (val result = raw(method, path, JsonBody.encode(body))) {
            is InboxWrite.Done -> {
                val item = decode(result.value, InboxItemDto.serializer())
                val count = decode(result.value, InboxCountDto.serializer())
                if (item == null) InboxWrite.Offline else InboxWrite.Done(InboxDecision(item, count?.pendingCount))
            }
            is InboxWrite.Conflict -> result
            is InboxWrite.Refused -> result
            is InboxWrite.Offline -> result
            is InboxWrite.SessionExpired -> result
        }

    private suspend fun <T> write(
        method: String,
        path: String,
        body: Map<String, Any?>,
        deserializer: DeserializationStrategy<T>,
    ): InboxWrite<T> = when (val result = raw(method, path, JsonBody.encode(body))) {
        // Um 2xx que nao e a resposta esperada (portal, proxy) nao prova nada: como sem rede.
        is InboxWrite.Done -> decode(result.value, deserializer)?.let { InboxWrite.Done(it) } ?: InboxWrite.Offline
        is InboxWrite.Conflict -> result
        is InboxWrite.Refused -> result
        is InboxWrite.Offline -> result
        is InboxWrite.SessionExpired -> result
    }

    private suspend fun raw(method: String, path: String, body: String?): InboxWrite<String> =
        sendWrite(sender, method, path, body)

    private fun <T> decode(body: String, deserializer: DeserializationStrategy<T>): T? = try {
        json.decodeFromString(deserializer, body)
    } catch (error: SerializationException) {
        null
    } catch (error: IllegalArgumentException) {
        null
    }

    companion object {
        const val VIEW_PENDING = "pending"
        const val VIEW_DECIDED = "decided"
        const val COUNT_PATH = "/api/inbox/count"
        const val HINTS_PATH = "/api/inbox/hints"
        const val SETTINGS_PATH = "/api/inbox/settings"
        const val APPROVE_READY_PATH = "/api/inbox/approve-ready"

        fun listPath(view: String): String = "/api/inbox?view=${encode(view)}"

        fun itemPath(id: String): String = "/api/inbox/${encode(id)}"

        // { version: item.version }: sem versao a chave nao vai, como no JS.
        fun versionBody(version: Int?): Map<String, Any?> =
            if (version != null) linkedMapOf("version" to version) else linkedMapOf()

        private fun encode(part: String): String =
            URLEncoder.encode(part, StandardCharsets.UTF_8.name()).replace("+", "%20")
    }
}

/** A resposta de uma decisao: o item como ficou e quantos esperam agora. */
data class InboxDecision(val item: InboxItemDto, val pendingCount: Int?)
