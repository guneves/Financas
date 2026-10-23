package br.financas.app.data

import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.JsonUnquotedLiteral
import java.math.BigDecimal

/**
 * O corpo JSON de um pedido a partir dos mapas que as regras montam (rules/InboxRules.kt): as
 * chaves na ordem do mapa, null como null, dinheiro (BigDecimal) como numero em notacao simples
 * — nunca passando por Double. Um numero nao finito vira null, como no JSON.stringify do JS.
 */
object JsonBody {

    fun encode(body: Map<String, Any?>): String = element(body).toString()

    @OptIn(ExperimentalSerializationApi::class)
    fun element(value: Any?): JsonElement = when (value) {
        null -> JsonNull
        is JsonElement -> value
        is String -> JsonPrimitive(value)
        is Boolean -> JsonPrimitive(value)
        is BigDecimal -> JsonUnquotedLiteral(value.toPlainString())
        is Double -> if (value.isFinite()) JsonPrimitive(value) else JsonNull
        is Float -> if (value.isFinite()) JsonPrimitive(value) else JsonNull
        is Number -> JsonPrimitive(value)
        is Map<*, *> -> {
            val entries = LinkedHashMap<String, JsonElement>()
            for ((key, item) in value) entries[key.toString()] = element(item)
            JsonObject(entries)
        }
        is Iterable<*> -> JsonArray(value.map { element(it) })
        else -> JsonPrimitive(value.toString())
    }
}
