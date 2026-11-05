// Porte: mudou um, muda o outro, com um teste de cada lado.
// Par: frontend/src/lib/investmentPrefill.js (investmentPrefill.test.js) e heldReasonLabel/heldLaunch
// de frontend/src/lib/openFinance.js; aqui InvestmentPrefillTest.kt, os mesmos casos.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.core.Js
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import java.math.BigDecimal

/**
 * O "Lançar" de uma operacao da corretora que espera (Fase 3): o `prefill` de
 * GET /api/open-finance (investments.held[].prefill, kind `operation`) vira o formulario de
 * "Registrar operação". O `op_key` volta no metadata (`open_finance_op_key`): e o que deixa a
 * operacao passar pela Corretora da Pluggy e marca a linha como gravada. O cupom e o resgate
 * (kind `proceed`/`redemption`) se lancam na web.
 */
object InvestmentPrefill {
    const val OP_KEY_METADATA = "open_finance_op_key"

    /** O prefill do servidor, so o que o formulario le. */
    data class Prefill(
        val kind: String?,
        val assetClass: String? = null,
        val treasury: Boolean = false,
        val tickerOrName: String? = null,
        val quantity: BigDecimal? = null,
        val averagePrice: BigDecimal? = null,
        val cashAccountId: String? = null,
        val metadata: JsonObject? = null,
    )

    private fun JsonObject?.text(key: String): String? = (this?.get(key) as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
    private fun JsonObject?.number(key: String): Double? = (this?.get(key) as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull
    private fun JsonObject?.flag(key: String): Boolean = (this?.get(key) as? JsonPrimitive)?.booleanOrNull ?: false

    private fun numberText(value: Double?): String = if (value == null) "" else Js.numberToString(value)
    private fun numberText(value: BigDecimal): String = value.stripTrailingZeros().toPlainString()

    /** O formulario de "Registrar operação" ja preenchido, ou null (so `operation` abre o formulario). */
    fun launchForm(prefill: Prefill?, today: String): Operations.LaunchForm? {
        if (prefill == null || prefill.kind != "operation") return null
        val metadata = prefill.metadata
        val quantity = prefill.quantity ?: BigDecimal.ZERO
        val sell = quantity.signum() < 0
        val fixedIncome = prefill.assetClass == "FIXED_INCOME"
        val otherCosts = BigDecimal.valueOf(metadata.number("other_costs") ?: 0.0)
        val average = prefill.averagePrice ?: BigDecimal.ZERO
        val price = when {
            fixedIncome -> average - otherCosts
            sell -> metadata.number("sale_price")?.let { BigDecimal.valueOf(it) } ?: average
            else -> average
        }
        val accountId = prefill.cashAccountId.orEmpty()
        val assetType = if (prefill.treasury) Operations.TREASURY else prefill.assetClass ?: "STOCKS"
        val fixedForm = if (fixedIncome) {
            FixedIncome.fixedIncomeFormFromMetadata(
                FixedIncome.Metadata(
                    fixedIncomeType = metadata.text("fixed_income_type"),
                    rateType = metadata.text("rate_type"),
                    indexer = metadata.text("indexer"),
                    cdiPercentage = metadata.number("cdi_percentage"),
                    annualRate = metadata.number("annual_rate"),
                    isTaxFree = metadata.flag("is_tax_free"),
                ),
            )
        } else {
            FixedIncome.emptyFixedIncomeForm()
        }
        return Operations.LaunchForm(
            mode = if (sell) "SELL" else "BUY",
            assetType = assetType,
            tickerOrName = prefill.tickerOrName.orEmpty(),
            date = metadata.text("purchase_date") ?: metadata.text("sale_date") ?: today,
            quantity = if (fixedIncome) "1" else numberText(quantity.abs()),
            price = if (price.signum() > 0) numberText(price) else "",
            otherCosts = if (otherCosts.signum() > 0) numberText(otherCosts) else "",
            treasuryUnits = numberText(metadata.number("treasury_units")),
            fixedIncome = fixedForm,
            cashLink = PortfolioAccount.CashLink(enabled = accountId.isNotEmpty(), accountId = accountId, missing = false),
            opKey = metadata.text(OP_KEY_METADATA).orEmpty(),
        )
    }

    /** O pedaco do metadata que leva o op_key (nada sem ele). */
    fun opKeyMetadata(opKey: String): Map<String, Any?> = if (opKey.isEmpty()) emptyMap() else mapOf(OP_KEY_METADATA to opKey)

    private val HELD_REASONS = mapOf(
        "type" to "fundo, custódia ou outro tipo: lance você",
        "unknown_asset" to "ativo fora da lista da B3",
        "incomplete" to "a corretora mandou sem quantidade ou preço",
    )

    private val HELD_FIELDS = mapOf(
        "position" to "a posição do título",
        "type" to "o tipo do investimento",
        "subtype" to "o tipo do título",
        "name" to "o nome do título",
        "rateType" to "o indexador",
        "rate" to "a taxa (% do CDI)",
        "fixedAnnualRate" to "a taxa ao ano",
        "dueDate" to "o vencimento",
        "tesouro_prices" to "os preços do Tesouro",
        "buy" to "a compra do título no app",
        "quantity" to "a quantidade de cotas",
        "lot" to "as cotas da compra",
        "amount" to "o valor",
        "tradeDate" to "a data",
    )

    /** Por que a operacao espera, em portugues (heldReasonLabel da web). */
    fun heldReasonLabel(reason: String?): String {
        val text = reason.orEmpty()
        if (text.startsWith("corporate_action")) return "antes de um evento corporativo do ativo"
        if (text.startsWith("refused")) return text.split(": ").drop(1).joinToString(": ").ifEmpty { "recusada" }
        val parts = text.split(":")
        if (parts.size >= 2 && (parts[0] == "missing" || parts[0] == "unmapped") && parts[1].isNotEmpty()) {
            val label = HELD_FIELDS[parts[1]] ?: parts[1]
            return if (parts[0] == "missing") "falta $label" else "$label sem um significado só"
        }
        return HELD_REASONS[text] ?: text
    }

    /** O "Lançar" do celular: so a operacao (o formulario), com o op_key. */
    fun launchable(opKey: String?, prefill: Prefill?): Boolean = !opKey.isNullOrEmpty() && prefill?.kind == "operation"
}
