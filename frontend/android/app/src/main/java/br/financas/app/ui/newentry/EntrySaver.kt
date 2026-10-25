// Port: mudou um, muda o outro, com um teste de cada lado.
// Par: createEntry() de frontend/src/lib/outbox.js (o envio de um lancamento do "+ Novo").
// Testes: EntrySaverTest.kt. Sem Android: a rede, a fila e o relogio entram por parametro.
//
// Diferenca deliberada da web: aqui o item vai para a fila ANTES do POST (sem agendar o
// envio), e sai quando o servidor responde de forma definitiva. Um app morto no meio do POST
// deixa o item pendente com o mesmo client_id; o proximo envio e inofensivo (o servidor
// devolve o que ja gravou). Na web o item so entra depois da falha.
package br.financas.app.ui.newentry

import br.financas.app.data.ApiException
import br.financas.app.outbox.OutboxRules
import org.json.JSONObject
import org.json.JSONTokener

/** O que aconteceu com um Salvar. */
sealed interface SaveResult {
    /** O servidor gravou (201) ou ja tinha gravado este client_id (200). [data]: a resposta lida. */
    data class Saved(val data: Any?) : SaveResult

    /** O pedido nao chegou (ou a resposta nao prova que chegou): o item fica na fila. */
    data class Queued(val item: JSONObject) : SaveResult

    /** O servidor respondeu e recusou: mostrar, nunca guardar na fila. null = sem mensagem. */
    data class Refused(val status: Int, val message: String?) : SaveResult

    /** 401 ou sem sessao: nada na fila; o dono entra de novo pela WebView. */
    data class SessionExpired(val message: String?) : SaveResult
}

/** A fila nativa vista pelo Salvar (OutboxStore + OutboxWorker no app; um falso nos testes). */
interface EntryQueue {
    /** Grava (ou regrava) o item inteiro, pelo client_id. */
    fun put(item: JSONObject)

    /** Tira o item; nada acontece se ele ja saiu (o envio em segundo plano pode ter tirado). */
    fun remove(clientId: String)

    /** Agenda o envio em segundo plano (OutboxWorker), que manda quando houver rede. */
    fun schedule()
}

/**
 * O caminho de um Salvar, o de createEntry() na web, com o item guardado antes:
 * 1. o client_id e gerado uma vez, antes da primeira tentativa (e vai em todo reenvio);
 * 2. sem sessao -> [SaveResult.SessionExpired], nada guardado (um item sem user_id nunca sairia);
 * 3. o item vai para a fila, ainda sem agendar o envio;
 * 4. sem rede de verdade (so a VPN nao conta) -> agenda e pronto, sem pedido;
 * 5. senao POST (o [post] tem o prazo de 6 s); sem resposta, tempo esgotado ou um 3xx (portal de
 *    Wi-Fi) -> fica e agenda;
 * 6. qualquer outra resposta de erro do servidor (4xx, 5xx, 401) -> sai da fila e aparece;
 * 7. um 2xx que nao e o lancamento (OutboxRules.isCreationResponse) -> fica e agenda;
 * 8. o lancamento -> sai da fila.
 *
 * [post] devolve o corpo de um 2xx ou lanca ApiException (o ApiClient.send).
 */
class EntrySaver(
    private val hasNetwork: () -> Boolean,
    private val post: suspend (path: String, body: String) -> String,
    private val queue: EntryQueue,
    private val userId: () -> String?,
    private val now: () -> Long = System::currentTimeMillis,
    private val newClientId: () -> String = OutboxRules::newClientId,
) {

    suspend fun create(kind: String, payload: Map<String, Any?>): SaveResult =
        createJson(kind, NewEntryForms.payloadJson(payload))

    /**
     * O mesmo caminho com o corpo ja montado: as criacoes de Investimentos (INVESTMENT, PROCEED)
     * mandam `null` de proposito (cash_account_id null = "Não descontar"), que o payloadJson
     * tiraria. [title] vai no item, fora do corpo: o nome que Pendentes mostra.
     */
    suspend fun createJson(kind: String, body: JSONObject, title: String? = null): SaveResult {
        val path = OutboxRules.endpointFor(kind)
            ?: throw IllegalArgumentException("Tipo de lancamento desconhecido: $kind")
        if (body.optString("client_id", "").isEmpty()) body.put("client_id", newClientId())
        val user = userId()?.takeIf { it.isNotEmpty() } ?: return SaveResult.SessionExpired(null)

        val item = OutboxRules.buildItem(kind, body, user, now())
        if (!title.isNullOrEmpty()) item.put("title", title)
        val clientId = item.getString("client_id")
        queue.put(item)

        if (!hasNetwork()) return keep(item)
        val text = try {
            post(path, body.toString())
        } catch (error: ApiException.Network) {
            return keep(item)
        } catch (error: ApiException.BadResponse) {
            return keep(item)
        } catch (error: ApiException.Unauthorized) {
            queue.remove(clientId)
            return SaveResult.SessionExpired(error.serverMessage)
        } catch (error: ApiException.Http) {
            // Um 3xx nunca e a API (o cliente nao segue redirecionamento): portal de Wi-Fi ou
            // proxy, o pedido nao chegou ao servidor.
            if (error.status in 300..399) return keep(item)
            queue.remove(clientId)
            return SaveResult.Refused(error.status, error.serverMessage)
        }
        val data = parse(text)
        if (!OutboxRules.isCreationResponse(kind, data)) return keep(item)
        queue.remove(clientId)
        return SaveResult.Saved(data)
    }

    private fun keep(item: JSONObject): SaveResult {
        queue.schedule()
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
