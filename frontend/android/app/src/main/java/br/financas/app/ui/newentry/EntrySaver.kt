// Port: mudou um, muda o outro, com um teste de cada lado.
// Par: createEntry() de frontend/src/lib/outbox.js (o envio de um lancamento do "+ Novo").
// Testes: EntrySaverTest.kt. Sem Android: a rede, a fila e o relogio entram por parametro.
package br.financas.app.ui.newentry

import br.financas.app.data.ApiException
import br.financas.app.outbox.OutboxRules
import org.json.JSONObject
import org.json.JSONTokener

/** O que aconteceu com um Salvar. */
sealed interface SaveResult {
    /** O servidor gravou (201) ou ja tinha gravado este client_id (200). [data]: a resposta lida. */
    data class Saved(val data: Any?) : SaveResult

    /** O pedido nao chegou (ou a resposta nao prova que chegou): o item esta na fila. */
    data class Queued(val item: JSONObject) : SaveResult

    /** O servidor respondeu e recusou: mostrar, nunca guardar na fila. null = sem mensagem. */
    data class Refused(val status: Int, val message: String?) : SaveResult

    /** 401 ou sem sessao: nada na fila; o dono entra de novo pela WebView. */
    data class SessionExpired(val message: String?) : SaveResult
}

/**
 * O caminho de um Salvar, o mesmo de createEntry() na web:
 * 1. o client_id e gerado uma vez, antes da primeira tentativa (e vai em todo reenvio);
 * 2. sem rede de verdade (so a VPN nao conta) -> fila na hora, sem pedido;
 * 3. senao POST (o [post] tem o prazo de 6 s); sem resposta ou tempo esgotado -> fila, com o
 *    mesmo client_id;
 * 4. qualquer resposta de erro do servidor -> [SaveResult.Refused], nunca fila;
 * 5. um 2xx que nao e o lancamento (portal de Wi-Fi, proxy: OutboxRules.isCreationResponse) ->
 *    fila: o client_id torna o reenvio seguro.
 *
 * [enqueue] grava o item no OutboxStore e agenda o OutboxWorker; [post] devolve o corpo de um
 * 2xx ou lanca ApiException (o ApiClient.send).
 */
class EntrySaver(
    private val hasNetwork: () -> Boolean,
    private val post: suspend (path: String, body: String) -> String,
    private val enqueue: (item: JSONObject) -> Unit,
    private val userId: () -> String?,
    private val now: () -> Long = System::currentTimeMillis,
    private val newClientId: () -> String = OutboxRules::newClientId,
) {

    suspend fun create(kind: String, payload: Map<String, Any?>): SaveResult {
        val path = OutboxRules.endpointFor(kind)
            ?: throw IllegalArgumentException("Tipo de lancamento desconhecido: $kind")
        val body = NewEntryForms.payloadJson(payload)
        if (body.optString("client_id", "").isEmpty()) body.put("client_id", newClientId())

        if (!hasNetwork()) return queue(kind, body)
        val text = try {
            post(path, body.toString())
        } catch (error: ApiException.Network) {
            return queue(kind, body)
        } catch (error: ApiException.BadResponse) {
            return queue(kind, body)
        } catch (error: ApiException.Unauthorized) {
            return SaveResult.SessionExpired(error.serverMessage)
        } catch (error: ApiException.Http) {
            return SaveResult.Refused(error.status, error.serverMessage)
        }
        val data = parse(text)
        if (!OutboxRules.isCreationResponse(kind, data)) return queue(kind, body)
        return SaveResult.Saved(data)
    }

    private fun queue(kind: String, body: JSONObject): SaveResult {
        val item = OutboxRules.buildItem(kind, body, userId() ?: "", now())
        enqueue(item)
        return SaveResult.Queued(item)
    }

    private fun parse(text: String): Any? {
        if (text.isBlank()) return null
        return try {
            JSONTokener(text).nextValue()
        } catch (error: Exception) {
            null
        }
    }
}
