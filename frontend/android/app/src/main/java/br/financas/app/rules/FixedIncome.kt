// Porte: mudou um, muda o outro, com um teste de cada lado.
// Par: frontend/src/lib/fixedIncome.js (fixedIncome.test.js); aqui FixedIncomeTest.kt,
// os mesmos casos na mesma ordem.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.core.Js
import java.math.BigDecimal
import java.math.RoundingMode
import java.text.DecimalFormat
import java.text.DecimalFormatSymbols
import java.util.Locale

/**
 * Renda fixa: tipo do titulo e forma de remuneracao. O metadata do lancamento guarda
 * fixed_income_type ('CDB', 'LCI', ...), rate_type ('POS' | 'PRE'), indexer ('CDI' | 'CDI_PLUS' |
 * 'IPCA', so pos-fixado), cdi_percentage (fracao do CDI, 1.10 = 110%) e annual_rate (fracao, 0.065
 * = 6,5% a.a., CDI+, IPCA+ e pre). Lancamentos antigos so tem cdi_percentage: pos-fixado em CDI.
 */
object FixedIncome {
    /** Um item de seletor (FIXED_INCOME_TYPES, RATE_MODES, INDEXERS). */
    data class Choice(val value: String, val label: String)

    /** O que estas regras leem do metadata de um titulo. */
    data class Metadata(
        val fixedIncomeType: String? = null,
        val rateType: String? = null,
        val indexer: String? = null,
        val cdiPercentage: Double? = null,
        val annualRate: Double? = null,
        val isTaxFree: Boolean = false,
    )

    /** Os campos do formulario (a taxa como o dono digita). */
    data class Form(
        val fixedIncomeType: String,
        val rateType: String,
        val indexer: String,
        val rate: String,
    )

    /** Uma taxa recusada pelo formulario, com o texto para a tela. */
    class RateError(message: String) : IllegalArgumentException(message)

    const val TREASURY_TYPE = "TESOURO"

    val FIXED_INCOME_TYPES = listOf(
        Choice("CDB", "CDB"),
        Choice("LCI", "LCI"),
        Choice("LCA", "LCA"),
        Choice("LIG", "LIG"),
        Choice("LC", "LC"),
        Choice("LF", "LF"),
        Choice("RDB", "RDB"),
        Choice("DEBENTURE", "Debênture"),
        Choice("DEBENTURE_INCENTIVADA", "Debênture incentivada"),
        Choice("CRI", "CRI"),
        Choice("CRA", "CRA"),
        Choice("CCB", "CCB"),
        // Tesouro Direto: na tela e uma categoria propria; no banco continua FIXED_INCOME.
        Choice(TREASURY_TYPE, "Tesouro Direto"),
    )

    /** Os titulos vendidos hoje no Tesouro Direto: sugestoes do nome. */
    val TREASURY_TITLES = listOf(
        "Tesouro Selic",
        "Tesouro Prefixado",
        "Tesouro Prefixado com Juros Semestrais",
        "Tesouro IPCA+",
        "Tesouro IPCA+ com Juros Semestrais",
        "Tesouro Renda+ Aposentadoria Extra",
        "Tesouro Educa+",
    )

    private val IPCA_LIKE = Regex("IPCA|RENDA ?\\+|EDUCA ?\\+")

    /** A rentabilidade (RATE_MODES) pelo nome do titulo do Tesouro, ou null. */
    fun treasuryRateMode(name: String?): String? {
        val text = (name ?: "").uppercase()
        if (text.contains("SELIC")) return "POS"
        if (IPCA_LIKE.containsMatchIn(text)) return "IPCA"
        if (text.contains("PREFIXADO")) return "PRE"
        return null
    }

    /** Isentos de IR para pessoa fisica pela especie (a lista de services/fixed_income.py). */
    val TAX_FREE_FIXED_INCOME_TYPES = listOf("LCI", "LCA", "LIG", "CRI", "CRA", "DEBENTURE_INCENTIVADA")

    fun isTaxFreeFixedIncomeType(type: String?): Boolean = type in TAX_FREE_FIXED_INCOME_TYPES

    /** IPCA+ aparece ao lado de pos e pre, mas no metadata e rate_type POS com indexer IPCA. */
    val RATE_MODES = listOf(
        Choice("POS", "Pós-fixado (CDI)"),
        Choice("IPCA", "IPCA+"),
        Choice("PRE", "Pré-fixado"),
    )

    val INDEXERS = listOf(
        Choice("CDI", "% do CDI"),
        Choice("CDI_PLUS", "CDI+"),
    )

    fun rateModeOf(rateType: String?, indexer: String?): String = when {
        rateType == "PRE" -> "PRE"
        indexer == "IPCA" -> "IPCA"
        else -> "POS"
    }

    /** (rate_type, indexer) de um modo. */
    fun rateFieldsForMode(mode: String?): Pair<String, String> = when (mode) {
        "PRE" -> "PRE" to "CDI"
        "IPCA" -> "POS" to "IPCA"
        else -> "POS" to "CDI"
    }

    fun rateFieldLabel(rateType: String?, indexer: String?): String = when {
        rateType == "PRE" -> "Taxa (% a.a.)"
        indexer == "CDI_PLUS" -> "CDI + (% a.a.)"
        indexer == "IPCA" -> "IPCA + (% a.a.)"
        else -> "% do CDI"
    }

    fun ratePlaceholder(rateType: String?, indexer: String?): String = when {
        rateType == "PRE" -> "Ex: 12,5"
        indexer == "CDI_PLUS" -> "Ex: 1,5"
        indexer == "IPCA" -> "Ex: 6,5"
        else -> "Ex: 110"
    }

    fun emptyFixedIncomeForm(): Form = Form(fixedIncomeType = "CDB", rateType = "POS", indexer = "CDI", rate = "")

    // String(Number((valor * 100).toFixed(4))): o toFixed do JS arredonda o valor exato, meio para cima.
    private fun formatRateInput(fraction: Double): String {
        if (!fraction.isFinite()) return ""
        val fixed = BigDecimal(fraction * 100).setScale(4, RoundingMode.HALF_UP).toDouble()
        return Js.numberToString(fixed)
    }

    /** O metadata salvo como formulario (a edicao). */
    fun fixedIncomeFormFromMetadata(metadata: Metadata = Metadata()): Form {
        // Debenture marcada isenta antes do tipo "incentivada" existir.
        val type = if (metadata.fixedIncomeType == "DEBENTURE" && metadata.isTaxFree) {
            "DEBENTURE_INCENTIVADA"
        } else {
            metadata.fixedIncomeType ?: ""
        }
        val rateType = if (metadata.rateType == "PRE") "PRE" else "POS"
        val indexer = if (rateType == "PRE") "CDI" else metadata.indexer.takeUnless { it.isNullOrEmpty() } ?: "CDI"
        val rate = if (rateType == "POS" && indexer == "CDI") metadata.cdiPercentage else metadata.annualRate
        return Form(type, rateType, indexer, if (rate != null) formatRateInput(rate) else "")
    }

    // "1.234,5" do teclado brasileiro ou "1234.5": o Number() do JS (NaN quando nao le).
    private fun parseRate(value: String?): Double {
        val raw = Js.trim(value ?: "")
        val normalized = if (raw.contains(',')) raw.replace(".", "").replaceFirst(",", ".") else raw
        return Js.number(normalized) ?: Double.NaN
    }

    /**
     * O formulario como chaves do metadata, so as presentes (o que o JSON.stringify da web manda:
     * as `undefined` somem). Uma taxa invalida e [RateError].
     */
    fun fixedIncomeMetadataFromForm(form: Form): Map<String, Any?> {
        val rate = parseRate(form.rate)
        val isCdi = form.rateType == "POS" && form.indexer == "CDI"
        if (!rate.isFinite() || rate < 0 || (isCdi && rate == 0.0) || Js.trim(form.rate).isEmpty()) {
            throw RateError(if (isCdi) "Informe um percentual do CDI válido." else "Informe uma taxa válida.")
        }
        val metadata = LinkedHashMap<String, Any?>()
        if (form.fixedIncomeType.isNotEmpty()) metadata["fixed_income_type"] = form.fixedIncomeType
        metadata["rate_type"] = form.rateType
        if (form.rateType == "POS") metadata["indexer"] = form.indexer
        if (isCdi) metadata["cdi_percentage"] = rate / 100 else metadata["annual_rate"] = rate / 100
        metadata["is_tax_free"] = isTaxFreeFixedIncomeType(form.fixedIncomeType)
        return metadata
    }

    /** Chaves que [fixedIncomeMetadataFromForm] controla; limpas antes de regravar. */
    val FIXED_INCOME_METADATA_KEYS = listOf(
        "fixed_income_type", "rate_type", "indexer", "cdi_percentage", "annual_rate", "is_tax_free",
    )

    /** "CDB · 110% do CDI", "IPCA + 6,5% a.a.", "Pré 12,5% a.a." */
    fun describeFixedIncome(metadata: Metadata = Metadata()): String {
        val typeLabel = FIXED_INCOME_TYPES.firstOrNull { it.value == metadata.fixedIncomeType }?.label
        val percent = { fraction: Double -> ptBrNumber(fraction * 100, 0, 2) }
        val rateLabel = when {
            metadata.rateType == "PRE" -> metadata.annualRate?.let { "Pré ${percent(it)}% a.a." }
            metadata.indexer == "CDI_PLUS" -> metadata.annualRate?.let { "CDI + ${percent(it)}% a.a." }
            metadata.indexer == "IPCA" -> metadata.annualRate?.let { "IPCA + ${percent(it)}% a.a." }
            else -> metadata.cdiPercentage?.let { "${percent(it)}% do CDI" }
        }
        return listOfNotNull(typeLabel, rateLabel).filter { it.isNotEmpty() }.joinToString(" · ")
    }
}

/**
 * O `toLocaleString('pt-BR', {minimumFractionDigits, maximumFractionDigits})` da web: milhar com
 * ponto, decimal com virgula, meio para cima sobre o numero mais curto que o double escreve (como o
 * ICU). So para texto de tela.
 */
internal fun ptBrNumber(value: Double, minDigits: Int, maxDigits: Int): String {
    if (!value.isFinite()) return if (value.isNaN()) "NaN" else if (value > 0) "∞" else "-∞"
    val rounded = BigDecimal(value.toString()).setScale(maxDigits, RoundingMode.HALF_UP)
    val format = DecimalFormat("#,##0", DecimalFormatSymbols(Locale.forLanguageTag("pt-BR"))).apply {
        minimumFractionDigits = minDigits
        maximumFractionDigits = maxDigits
        roundingMode = RoundingMode.HALF_UP
    }
    return format.format(rounded)
}
