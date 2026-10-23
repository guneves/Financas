// A fila nativa (outbox/OutboxStore.java) vista pelas regras do saldo com pendentes
// (rules/OutboxPending.kt). Cada linha guarda o item no formato que lib/outbox.js escreve
// (buildItem() em outboxRules.js): { client_id, user_id, kind, payload, status, last_error,
// created_at }, com o payload igual ao corpo da rota. Aqui o texto JSON vira PendingItem.
// Testes: OutboxItemsTest.kt. Puro: nada de Android (o JSON e lido com kotlinx).
package br.financas.app.rules

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import java.math.BigDecimal

object OutboxItems {

    /**
     * Um item guardado (o texto JSON de OutboxStore) como PendingItem; null quando nao e um item
     * (texto quebrado, sem client_id ou sem kind). Um valor que nao e numero (nem texto de numero,
     * como Number() aceita no JS) fica ausente: vale 0 nas regras, e o item nao mexe em saldo.
     */
    fun parse(text: String): PendingItem? {
        val element = try {
            Json.parseToJsonElement(text)
        } catch (error: Exception) {
            return null
        }
        val item = element as? JsonObject ?: return null
        val clientId = string(item["client_id"])?.takeIf { it.isNotEmpty() } ?: return null
        val kind = string(item["kind"])?.takeIf { it.isNotEmpty() } ?: return null
        val payload = item["payload"] as? JsonObject ?: JsonObject(emptyMap())
        return PendingItem(
            clientId = clientId,
            kind = kind,
            status = string(item["status"])?.takeIf { it.isNotEmpty() } ?: OutboxPending.PENDING,
            createdAt = string(item["created_at"]),
            payload = PendingPayload(
                amount = number(payload["amount"]),
                totalAmount = number(payload["total_amount"]),
                accountId = string(payload["account_id"]),
                transferAccountId = string(payload["transfer_account_id"]),
                date = string(payload["date"]),
                category = string(payload["category"]),
                description = string(payload["description"]),
            ),
        )
    }

    /** O user_id do item ("" quando ausente), para mostrar so os do usuario da sessao. */
    fun userOf(text: String): String? {
        val item = try {
            Json.parseToJsonElement(text) as? JsonObject
        } catch (error: Exception) {
            null
        } ?: return null
        return string(item["user_id"]) ?: ""
    }

    /**
     * Os itens do usuario da sessao, como a web (useOutbox: so os de user_id igual; sem login,
     * nenhum). Itens ilegiveis ficam de fora.
     */
    fun forUser(texts: List<String>, userId: String?): List<PendingItem> {
        if (userId.isNullOrEmpty()) return emptyList()
        return texts.filter { userOf(it) == userId }.mapNotNull(::parse)
    }

    private fun string(element: JsonElement?): String? =
        if (element is JsonPrimitive && element !is JsonNull) element.content else null

    private fun number(element: JsonElement?): BigDecimal? {
        val text = string(element)?.trim() ?: return null
        if (text.isEmpty()) return null
        return try {
            BigDecimal(text)
        } catch (error: NumberFormatException) {
            null
        }
    }
}
