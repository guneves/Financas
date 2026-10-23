package br.financas.app.ui.home

import android.content.Context
import br.financas.app.rules.AttentionRules
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive

/**
 * Os avisos que o X de "Precisa de atenção" dispensou neste aparelho, pela chave do caso
 * (GET /api/attention, byte a byte): o mesmo caso nao volta ao Inicio, um novo volta, e o sino
 * mostra todos. A web guarda as dela no localStorage da WebView (lib/attention.js); as duas
 * listas sao separadas — dispensar no Inicio nativo nao esconde o cartao no Inicio da web
 * (?web=1), e vice-versa (03-inicio.md).
 */
class AttentionDismissals(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun load(): List<String> = decode(prefs.getString(KEY, null))

    /** Junta [keys] as dispensadas (as 200 mais recentes) e grava. Devolve a lista nova. */
    fun add(current: List<String>, keys: List<String>): List<String> {
        val next = AttentionRules.addDismissed(current, keys)
        prefs.edit().putString(KEY, encode(next)).apply()
        return next
    }

    companion object {
        private const val PREFS = "financas_attention"
        private const val KEY = "dismissed"

        fun encode(keys: List<String>): String = JsonArray(keys.map { JsonPrimitive(it) }).toString()

        /** O texto guardado como lista; o que nao for texto fica de fora, como na web. */
        fun decode(text: String?): List<String> {
            if (text.isNullOrEmpty()) return emptyList()
            val parsed = try {
                Json.parseToJsonElement(text)
            } catch (error: Exception) {
                return emptyList()
            }
            if (parsed !is JsonArray) return emptyList()
            return parsed.mapNotNull { element -> (element as? JsonPrimitive)?.takeIf { it.isString }?.content }
        }
    }
}
