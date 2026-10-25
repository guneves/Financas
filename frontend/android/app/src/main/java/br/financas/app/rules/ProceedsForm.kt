// Porte: mudou um, muda o outro, com um teste de cada lado.
// Par: o formulario de pages/Proventos.jsx (blankForm, parseNumberInput, buildPayload, handleEdit,
// receiptsChartData), inline na web, sem teste de la. Aqui ProceedsFormTest.kt. As regras de que
// ativo recebe que tipo e de que campos cada tipo pede sao ProceedsRules (o par testado).
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.core.Js
import java.math.BigDecimal

object ProceedsForm {
    /** Um campo recusado, com o texto para a tela. */
    class FormError(message: String) : IllegalArgumentException(message)

    /** "Repetir": o intervalo em meses ("" = nao repetir). */
    val REPEAT_OPTIONS = listOf("" to "Não repetir", "1" to "Todo mês", "3" to "A cada 3 meses", "6" to "A cada 6 meses", "12" to "Todo ano")

    /** O formulario como o dono digita (datas AAAA-MM-DD). */
    data class Form(
        val assetId: String = "",
        val proceedsType: String = "DIVIDEND",
        val declaredDate: String = "",
        val recordDate: String = "",
        val exDate: String = "",
        val paymentDate: String = "",
        val amountPerUnit: String = "",
        val eligibleQuantity: String = "",
        val grossAmount: String = "",
        val taxAmount: String = "",
        val notes: String = "",
        val repeatEvery: String = "",
        val repeatCount: String = "",
    )

    fun blankForm(today: String): Form = Form(recordDate = today, paymentDate = today)

    /** Um numero do formulario: vazio = ausente (null); ilegivel = [Invalid]. */
    sealed interface Number {
        data object Blank : Number
        data object Invalid : Number
        data class Value(val value: BigDecimal) : Number
    }

    fun parse(raw: String?): Number {
        val text = Js.trim(raw ?: "")
        if (text.isEmpty()) return Number.Blank
        val normalized = if (text.contains(',')) text.replace(".", "").replaceFirst(",", ".") else text
        return normalized.toBigDecimalOrNull()?.let { Number.Value(it) } ?: Number.Invalid
    }

    private fun Number.valueOrNull(): BigDecimal? = (this as? Number.Value)?.value

    /**
     * O corpo de POST/PATCH /api/investment-proceeds (buildPayload). [asset] decide o layout (FIXED
     * para cupom e amortizacao de renda fixa/Tesouro, MARKET para o resto); [editing] nunca manda
     * `repeat`. Vazio vai como null: o servidor completa (quantidade na data com, IR automatico).
     */
    fun payload(form: Form, asset: ProceedsRules.Asset?, editing: Boolean): Map<String, Any?> {
        val amountPerUnit = parse(form.amountPerUnit)
        val eligibleQuantity = parse(form.eligibleQuantity)
        val grossAmount = parse(form.grossAmount)
        val taxAmount = parse(form.taxAmount)
        if (form.assetId.isEmpty()) throw FormError("Selecione o ativo na lista.")
        val taxField = ProceedsRules.proceedsTaxField(form.proceedsType)
        if (ProceedsRules.proceedsLayout(form.proceedsType, asset) == "FIXED") {
            if (form.paymentDate.isEmpty()) throw FormError("Informe a data de pagamento.")
            val gross = grossAmount.valueOrNull()
            if (gross == null || gross.signum() <= 0) throw FormError("Informe o valor bruto do pagamento.")
            if (taxField != null && taxAmount == Number.Invalid) throw FormError("Informe um IR válido.")
            val count = repeatCount(form.repeatCount)
            if (!editing && form.repeatEvery.isNotEmpty() && (count == null || count < 1 || count > 120)) {
                throw FormError("Informe quantos pagamentos (de 1 a 120).")
            }
            val body = linkedMapOf<String, Any?>(
                "asset_id" to form.assetId,
                "proceeds_type" to form.proceedsType,
                "declared_date" to null,
                "record_date" to form.paymentDate,
                "ex_date" to null,
                "payment_date" to form.paymentDate,
                "amount_per_unit" to null,
                "eligible_quantity" to null,
                "gross_amount" to gross,
                "tax_amount" to if (taxField != null) taxAmount.valueOrNull() else null,
                "notes" to form.notes,
            )
            if (!editing && form.repeatEvery.isNotEmpty()) {
                body["repeat"] = linkedMapOf("every_months" to form.repeatEvery.toInt(), "count" to count)
            }
            return body
        }
        if (form.recordDate.isEmpty()) throw FormError("Informe a data com.")
        if (form.paymentDate.isEmpty()) throw FormError("Informe a data de pagamento.")
        if (amountPerUnit == Number.Invalid || eligibleQuantity == Number.Invalid || grossAmount == Number.Invalid ||
            (taxField != null && taxAmount == Number.Invalid)
        ) {
            throw FormError("Informe valores numéricos válidos.")
        }
        return linkedMapOf(
            "asset_id" to form.assetId,
            "proceeds_type" to form.proceedsType,
            "declared_date" to form.declaredDate.ifEmpty { null },
            "record_date" to form.recordDate,
            "ex_date" to form.exDate.ifEmpty { null },
            "payment_date" to form.paymentDate,
            "amount_per_unit" to amountPerUnit.valueOrNull(),
            "eligible_quantity" to eligibleQuantity.valueOrNull(),
            "gross_amount" to grossAmount.valueOrNull(),
            "tax_amount" to if (taxField != null) taxAmount.valueOrNull() else null,
            "notes" to form.notes,
        )
    }

    // O Number(form.repeat_count) com Number.isInteger: "3", " 3 ", "3.0"; vazio ou fracao, null.
    private fun repeatCount(raw: String): Int? {
        val number = Js.trim(raw).toBigDecimalOrNull() ?: return null
        val whole = number.stripTrailingZeros()
        if (whole.scale() > 0) return null
        return whole.toInt()
    }

    private fun text(value: BigDecimal?): String = value?.stripTrailingZeros()?.toPlainString()?.replace('.', ',') ?: ""

    /** O formulario de um provento gravado (handleEdit); sem `repeat`. */
    fun editForm(
        assetId: String?,
        proceedsType: String?,
        declaredDate: String?,
        recordDate: String?,
        exDate: String?,
        paymentDate: String?,
        amountPerUnit: BigDecimal?,
        eligibleQuantity: BigDecimal?,
        grossAmount: BigDecimal?,
        taxAmount: BigDecimal?,
        notes: String?,
        today: String,
    ): Form = Form(
        assetId = assetId.orEmpty(),
        proceedsType = proceedsType?.takeIf { it.isNotEmpty() } ?: "DIVIDEND",
        declaredDate = declaredDate.orEmpty(),
        recordDate = recordDate?.takeIf { it.isNotEmpty() } ?: today,
        exDate = exDate.orEmpty(),
        paymentDate = paymentDate?.takeIf { it.isNotEmpty() } ?: today,
        amountPerUnit = text(amountPerUnit),
        eligibleQuantity = text(eligibleQuantity),
        grossAmount = text(grossAmount),
        taxAmount = text(taxAmount),
        notes = notes.orEmpty(),
    )

    /** "Excluir este provento?": o texto, com o aviso de que um automatico nao volta. */
    fun deleteMessage(ticker: String?, paymentDate: String, automatic: Boolean): String =
        "${ticker?.takeIf { it.isNotEmpty() } ?: "Ativo"}, pago em $paymentDate." +
            if (automatic) " Ele foi calculado automaticamente e não volta nas próximas atualizações." else ""

    /** O toast do "Atualizar" (handleSync); null quando o servidor mandou uma mensagem (vai para o aviso). */
    fun syncToast(created: Int, updated: Int, removed: Int): String =
        if (created + updated + removed > 0) {
            "Proventos atualizados: $created novo(s), $updated corrigido(s), $removed removido(s)."
        } else {
            "Proventos já estavam em dia."
        }

    /** As barras de Recebimentos: as linhas do servidor em ordem de chave (mes AAAA-MM ou ano). */
    fun <T> chartRows(rows: List<T>, key: (T) -> String): List<T> = rows.sortedBy(key)
}
