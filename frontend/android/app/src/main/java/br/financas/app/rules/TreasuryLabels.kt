// Porte: mudou um, muda o outro, com um teste de cada lado.
// Par: frontend/src/lib/treasury.js, so os textos (treasuryRateText, treasuryRateLabel,
// treasuryMarketRateText, isMarketValued, parseTreasuryUnits); o resgate e do servidor
// (POST /api/investments/redemptions). Aqui TreasuryLabelsTest.kt, os casos de
// treasury.test.js na mesma ordem.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.core.Js

/**
 * Tesouro Direto na Posicao: a posicao agrupada por titulo (services/treasury.py) traz `treasury`
 * (vencimento, titulos, taxa media, PU) e o metadata com a taxa da compra (ou a media).
 */
object TreasuryLabels {
    /** O bloco `treasury` de uma posicao, so o que os textos leem. */
    data class Treasury(
        val averageRate: Double? = null,
        val lotCount: Int? = null,
        val marketRate: Double? = null,
        val titleType: String? = null,
        val valuation: String? = null,
    )

    /** Uma posicao do Tesouro: o metadata (taxa) e o bloco `treasury` (pode faltar). */
    data class Position(val metadata: FixedIncome.Metadata = FixedIncome.Metadata(), val treasury: Treasury? = null)

    private fun percentNumber(fraction: Double): String = ptBrNumber(fraction * 100, 2, 2)

    /** "IPCA + 6,23% a.a.", "Pré 12,10% a.a.", "100,00% do CDI" de uma taxa (fracao). */
    fun treasuryRateText(rate: Double?, metadata: FixedIncome.Metadata = FixedIncome.Metadata()): String {
        if (rate == null || !rate.isFinite()) return ""
        return when {
            metadata.rateType == "PRE" -> "Pré ${percentNumber(rate)}% a.a."
            metadata.indexer == "IPCA" -> "IPCA + ${percentNumber(rate)}% a.a."
            metadata.indexer == "CDI_PLUS" -> "CDI + ${percentNumber(rate)}% a.a."
            else -> "${percentNumber(rate)}% do CDI"
        }
    }

    /** A taxa da linha: "Taxa média" quando a posicao junta mais de uma compra. */
    fun treasuryRateLabel(position: Position?): String {
        val treasury = position?.treasury ?: Treasury()
        val metadata = position?.metadata ?: FixedIncome.Metadata()
        val cdi = metadata.indexer == "CDI" || (metadata.indexer.isNullOrEmpty() && metadata.rateType != "PRE")
        val rate = treasury.averageRate ?: if (cdi) metadata.cdiPercentage else metadata.annualRate
        val text = treasuryRateText(rate, metadata)
        if (text.isEmpty()) return ""
        return if ((treasury.lotCount ?: 0) > 1) "Taxa média $text" else "Taxa $text"
    }

    /** A taxa de mercado do dia no mesmo formato; nunca no Selic (o arquivo da o agio, nao a.a.). */
    fun treasuryMarketRateText(position: Position?): String {
        val treasury = position?.treasury ?: Treasury()
        val rate = treasury.marketRate
        if (rate == null || (treasury.titleType ?: "").contains("SELIC")) return ""
        val metadata = position?.metadata ?: FixedIncome.Metadata()
        if (metadata.rateType == "PRE") return "Pré ${percentNumber(rate)}% a.a."
        return "IPCA + ${percentNumber(rate)}% a.a."
    }

    fun isMarketValued(position: Position?): Boolean = position?.treasury?.valuation == "MARKET"

    /**
     * "0,85" (ou "0.85") -> 0.85; vazio -> null; invalido ou <= 0 -> NaN. A quantidade de titulos
     * que o extrato da corretora mostra, na compra e na edicao.
     */
    fun parseTreasuryUnits(raw: String?): Double? {
        val text = Js.trim(raw ?: "")
        if (text.isEmpty()) return null
        val normalized = if (text.contains(',')) text.replace(".", "").replaceFirst(",", ".") else text
        val units = Js.number(normalized) ?: Double.NaN
        return if (units.isFinite() && units > 0) units else Double.NaN
    }
}
