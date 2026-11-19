// Porte: mudou um, muda o outro, com um teste de cada lado.
// Este arquivo e o port de frontend/src/lib/autoDecisions.js (decisionTitle, decisionDetail,
// undoToast, canUndo, noUndoLabel); AutoDecisionsTest.kt copia os casos de autoDecisions.test.js.
package br.financas.app.rules

import br.financas.app.core.formatCurrency
import br.financas.app.core.formatDateBR
import br.financas.app.data.AutoDecisionDto
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import java.math.BigDecimal

/**
 * "Decidido sozinho" no celular (Ajustes): o texto de cada decisao automatica (058) e o que o
 * "Desfazer" faz. O servidor decide o que se desfaz aqui (`undoable`).
 */
object AutoDecisions {

    private val TITLES = mapOf(
        "pluggy_category" to "Categoria da Pluggy",
        "auto_confirm" to "Saiu do Revisar sozinho",
        "transfer_guess" to "Aporte/resgate com o banco adivinhado",
        "fx_fallback" to "Câmbio do último dia útil disponível",
        "conflict_changed" to "Valor do banco aplicado",
        "conflict_vanished" to "Removido: sumiu do banco e o saldo confirma",
        "investment_custody" to "Custódia da corretora: o app já tinha",
        "investment_proceed_link" to "Provento da corretora ligado ao calculado",
        "investment_closed_fund" to "Fundo do banco já encerrado",
        "investment_custody_in" to "Título vindo de outra corretora, pelo custo",
        "investment_rate_deduced" to "Título sem indexador: pré-fixado",
    )

    @JvmStatic
    fun decisionTitle(kind: String?): String = TITLES[kind] ?: "Decisão automática"

    private fun text(detail: JsonObject, key: String): String? =
        (detail[key] as? JsonPrimitive)?.takeIf { it.isString }?.content?.takeIf { it.isNotEmpty() }

    private fun number(detail: JsonObject, key: String): BigDecimal? =
        (detail[key] as? JsonPrimitive)?.takeIf { !it.isString }?.content?.toBigDecimalOrNull()

    /** O primeiro elemento de uma lista [nome, id] (a categoria). */
    private fun firstOf(detail: JsonObject, key: String): String? =
        ((detail[key] as? JsonArray)?.firstOrNull() as? JsonPrimitive)?.content?.takeIf { it.isNotEmpty() }

    private fun cents(value: BigDecimal?): String = value?.let { formatCurrency(it.movePointLeft(2)) } ?: ""

    /** Uma linha do que mudou, sem nada que o servidor nao mandou. */
    @JvmStatic
    fun decisionDetail(kind: String?, detail: JsonObject): String = when (kind) {
        "pluggy_category" -> {
            val before = firstOf(detail, "before")
            val after = firstOf(detail, "after")
            if (before != null && after != null) "$before → $after" else ""
        }
        "auto_confirm" -> firstOf(detail, "category")?.let { "Ficou em $it" } ?: ""
        "conflict_changed" -> "${cents(number(detail, "before_cents"))} → ${cents(number(detail, "after_cents"))}"
        "conflict_vanished" -> ((detail["row"] as? JsonObject)?.let { text(it, "description") }) ?: ""
        "fx_fallback" -> text(detail, "rate_date")?.let { "PTAX de ${formatDateBR(it, it)}" } ?: ""
        "investment_custody", "investment_proceed_link" -> text(detail, "code") ?: ""
        "investment_closed_fund" -> text(detail, "name") ?: ""
        "investment_custody_in" -> listOfNotNull(
            text(detail, "name"),
            number(detail, "cost")?.let { formatCurrency(it) },
        ).joinToString(" · ")
        "investment_rate_deduced" -> listOfNotNull(
            text(detail, "name"),
            number(detail, "fixedAnnualRate")?.let { "${it.stripTrailingZeros().toPlainString().replace('.', ',')}% a.a." },
        ).joinToString(" · ")
        else -> ""
    }

    @JvmStatic
    fun decisionDetail(decision: AutoDecisionDto): String = decisionDetail(decision.kind, decision.detail)

    /** O que o "Desfazer" fez, para o aviso. */
    @JvmStatic
    fun undoToast(kind: String?): String = when (kind) {
        "pluggy_category" -> "A categoria voltou."
        "conflict_changed" -> "O valor voltou; a Conferência aponta a diferença."
        "conflict_vanished" -> "O lançamento voltou."
        "investment_custody", "investment_proceed_link", "investment_closed_fund" -> "Voltou a esperar você na Conferência."
        else -> "Voltou para o Revisar."
    }

    /** O servidor diz o que se desfaz aqui; ja desfeita, nao. */
    @JvmStatic
    fun canUndo(decision: AutoDecisionDto): Boolean =
        decision.id.isNotEmpty() && decision.undoneAt.isNullOrEmpty() && decision.undoable

    /** O que aparece no lugar do "Desfazer". */
    @JvmStatic
    fun noUndoLabel(decision: AutoDecisionDto): String =
        if (!decision.undoneAt.isNullOrEmpty()) "Desfeito" else "Apague no Extrato para desfazer"
}
