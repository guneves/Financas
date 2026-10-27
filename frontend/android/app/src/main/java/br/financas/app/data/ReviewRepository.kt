package br.financas.app.data

import kotlinx.coroutines.flow.Flow
import kotlinx.serialization.SerializationException
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json

/**
 * Revisar e as compras no cartao do Extrato (045) sobre a API, os pedidos da web
 * (lib/reviewQueue.js, ReviewPanel.jsx, Extrato.jsx): as leituras com a copia guardada, a
 * confirmacao so com o servidor (nunca na fila; tudo ou nada).
 */
class ReviewRepository(
    private val reader: CachedReader,
    private val sender: Sender,
    private val json: Json = ApiJson,
) {
    fun queue(): Flow<Load<ReviewQueueDto>> = reader.read(REVIEW_PATH, ReviewQueueDto.serializer())

    /** As compras no cartao com os filtros do extrato (os mesmos de GET /api/transactions). */
    fun cardStatement(filters: Map<String, String>): Flow<Load<List<CardStatementDto>>> =
        reader.read(cardStatementPath(filters), ListSerializer(CardStatementDto.serializer()))

    /** POST /api/review {items: [{table, id, category_id?}]} (rules/ReviewRules.reviewPayload). */
    suspend fun confirm(items: List<Map<String, Any?>>): InboxWrite<ReviewConfirmedDto> =
        when (val result = sendWrite(sender, "POST", REVIEW_PATH, JsonBody.encode(mapOf("items" to items)))) {
            is InboxWrite.Done -> decode(result.value)?.let { InboxWrite.Done(it) } ?: InboxWrite.Offline
            is InboxWrite.Conflict -> result
            is InboxWrite.Refused -> result
            is InboxWrite.Offline -> result
            is InboxWrite.SessionExpired -> result
        }

    private fun decode(body: String): ReviewConfirmedDto? = try {
        json.decodeFromString(ReviewConfirmedDto.serializer(), body)
    } catch (error: SerializationException) {
        null
    } catch (error: IllegalArgumentException) {
        null
    }

    companion object {
        const val REVIEW_PATH = "/api/review"
        const val CARD_STATEMENT_PATH = "/api/cc-expenses/statement"

        fun cardStatementPath(filters: Map<String, String>): String =
            CARD_STATEMENT_PATH + LancamentosRepository.query(filters.filterValues { it.isNotBlank() })
    }
}
