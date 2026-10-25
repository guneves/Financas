// Port: mudou um, muda o outro, com um teste de cada lado.
// Par: frontend/src/lib/outboxRules.js — KIND_LABELS, isEditableKind, itemAmount, itemDate e
// itemTitle (o que components/PendingSheet.jsx mostra em cada linha). Testes: outboxRules.test.js
// e PendingRowsTest.kt, os mesmos casos. Puro: nada de Android (o JSON e lido com kotlinx).
package br.financas.app.rules

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import java.math.BigDecimal

/** Uma linha de Pendentes: o item da fila (OutboxStore) como a folha o mostra. */
data class PendingRow(
    val clientId: String,
    val kind: String,
    val status: String,
    val title: String,
    val kindLabel: String,
    val date: String?,
    val installments: Int,
    val amount: BigDecimal,
    val lastError: String?,
    val createdAt: String?,
) {
    val refused: Boolean get() = status == OutboxPending.NEEDS_ATTENTION
    val editable: Boolean get() = PendingRows.isEditableKind(kind)
}

object PendingRows {
    val KIND_LABELS: Map<String, String> = mapOf(
        "EXPENSE" to "Despesa",
        "INCOME" to "Receita",
        "TRANSFER" to "Transferência",
        "CARD" to "Compra no cartão",
        "INVESTMENT" to "Operação",
        "PROCEED" to "Provento",
    )

    /** So os do "+ Novo" reabrem no formulario (Corrigir); operacao e provento so se descartam. */
    fun isEditableKind(kind: String): Boolean = kind in setOf("EXPENSE", "INCOME", "TRANSFER", "CARD")

    /** O texto guardado como linha; null quando nao e um item (sem client_id ou kind). */
    fun parse(text: String): PendingRow? {
        val item = try {
            Json.parseToJsonElement(text) as? JsonObject
        } catch (error: Exception) {
            null
        } ?: return null
        val clientId = string(item["client_id"])?.takeIf { it.isNotEmpty() } ?: return null
        val kind = string(item["kind"])?.takeIf { it.isNotEmpty() } ?: return null
        val payload = item["payload"] as? JsonObject ?: JsonObject(emptyMap())
        return PendingRow(
            clientId = clientId,
            kind = kind,
            status = string(item["status"])?.takeIf { it.isNotEmpty() } ?: OutboxPending.PENDING,
            title = title(kind, payload, string(item["title"])),
            kindLabel = KIND_LABELS[kind] ?: kind,
            date = date(kind, payload),
            installments = if (kind == "CARD") number(payload["installments"])?.toInt() ?: 1 else 1,
            amount = amount(kind, payload),
            lastError = string(item["last_error"])?.takeIf { it.isNotEmpty() },
            createdAt = string(item["created_at"]),
        )
    }

    /** As linhas do usuario da sessao (nenhuma sem login), na ordem de envio (created_at). */
    fun forUser(texts: List<String>, userId: String?): List<PendingRow> {
        if (userId.isNullOrEmpty()) return emptyList()
        return texts.filter { OutboxItems.userOf(it) == userId }
            .mapNotNull(::parse)
            .sortedBy { it.createdAt.orEmpty() }
    }

    /** O "Descartar o lançamento pendente?" da web. */
    fun discardMessage(row: PendingRow, money: (BigDecimal) -> String): String =
        "${row.kindLabel} de ${money(row.amount)} ainda não foi enviada. Descartar apaga do aparelho; ela não chega ao servidor."

    /** "Despesa · 12/10/2026 · 3x". */
    fun detail(row: PendingRow, date: (String?) -> String): String =
        "${row.kindLabel} · ${date(row.date)}" + if (row.kind == "CARD" && row.installments > 1) " · ${row.installments}x" else ""

    /** O aviso de "Sincronizar agora" (null = nada a dizer), pelo `stopped` e `attention` do envio. */
    fun syncWarning(stopped: String?, attention: Int): String? = when {
        stopped == "login" -> "Entre novamente para enviar os lançamentos pendentes."
        stopped == "offline" -> "O servidor não respondeu. Os lançamentos continuam guardados neste aparelho."
        attention > 0 -> "O servidor recusou um ou mais lançamentos. Veja o motivo em cada um."
        else -> null
    }

    fun sentNotice(sent: Int): String? = when {
        sent <= 0 -> null
        sent == 1 -> "1 lançamento enviado."
        else -> "$sent lançamentos enviados."
    }

    private fun title(kind: String, payload: JsonObject, itemTitle: String?): String = when (kind) {
        "INVESTMENT" -> string(payload["ticker_or_name"])?.takeIf { it.isNotEmpty() } ?: KIND_LABELS.getValue("INVESTMENT")
        "PROCEED" -> itemTitle?.takeIf { it.isNotEmpty() } ?: KIND_LABELS.getValue("PROCEED")
        else -> string(payload["description"])?.takeIf { it.isNotEmpty() } ?: KIND_LABELS[kind] ?: kind
    }

    private fun date(kind: String, payload: JsonObject): String? {
        val metadata = payload["metadata"] as? JsonObject
        return when (kind) {
            "CARD" -> string(payload["purchase_date"])
            "PROCEED" -> string(payload["payment_date"])
            "INVESTMENT" -> string(metadata?.get("purchase_date"))?.takeIf { it.isNotEmpty() } ?: string(metadata?.get("sale_date"))
            else -> string(payload["date"])
        }
    }

    private fun amount(kind: String, payload: JsonObject): BigDecimal {
        val value = when (kind) {
            "CARD" -> number(payload["total_amount"])
            "PROCEED" -> number(payload["gross_amount"])
            "INVESTMENT" -> {
                val quantity = number(payload["quantity"])
                val sale = quantity != null && quantity.signum() < 0
                val metadata = payload["metadata"] as? JsonObject
                val price = if (sale) number(metadata?.get("sale_price")) else number(payload["average_price"])
                if (quantity == null || price == null) null else quantity.abs().multiply(price)
            }
            else -> number(payload["amount"])
        }
        return value ?: BigDecimal.ZERO
    }

    private fun string(element: JsonElement?): String? =
        if (element is JsonPrimitive && element !is JsonNull) element.content else null

    private fun number(element: JsonElement?): BigDecimal? {
        val text = string(element)?.trim()?.takeIf { it.isNotEmpty() } ?: return null
        return try {
            BigDecimal(text)
        } catch (error: NumberFormatException) {
            null
        }
    }
}
