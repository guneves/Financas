// Porte: mudou um, muda o outro, com um teste de cada lado.
// Par: o que pages/investimentos/Alocacao.jsx faz inline (gapText, DriftBadge + DRIFT_WARNING, a
// leitura do "Quanto vai aportar?") e o que ImpostoRenda.jsx faz inline (activeMonths, hasEtfs,
// monthName), sem teste do lado web. Aqui AllocationRulesTest.kt. A divisao do aporte e a
// apuracao do IR sao do servidor: nada disso e recalculado aqui.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.core.formatPercent
import java.math.BigDecimal

object AllocationRules {
    /** Desvio (p.p.) que pede atencao; abaixo disso, no plano. */
    val DRIFT_WARNING: BigDecimal = BigDecimal(5)

    private val CENT = BigDecimal("0.01")

    /** "Faltam R$ x" / "R$ x acima" / "Na meta", de gap = meta - atual; sem gap, "". [money] formata (e mascara). */
    fun gapText(gap: BigDecimal?, money: (BigDecimal) -> String): String = when {
        gap == null -> ""
        gap.abs() < CENT -> "Na meta"
        gap.signum() > 0 -> "Faltam ${money(gap)}"
        else -> "${money(gap.abs())} acima"
    }

    /** O selo do desvio: sem meta, na meta, ou "+x,x p.p." (aviso a partir de 5 p.p.). */
    data class Drift(val label: String, val warning: Boolean)

    fun drift(diff: BigDecimal?): Drift = when {
        diff == null -> Drift("Sem meta", false)
        diff.abs() < CENT -> Drift("Na meta", false)
        else -> Drift("${formatPercent(diff, 1, signed = true)} p.p.", diff.abs() >= DRIFT_WARNING)
    }

    /** O "Quanto vai aportar?": Number(texto com virgula) || 0 — ilegivel ou vazio vale 0. */
    fun contribution(raw: String?): BigDecimal {
        val text = (raw ?: "").trim().replaceFirst(',', '.')
        val value = text.toBigDecimalOrNull() ?: return BigDecimal.ZERO
        return if (value.signum() > 0) value else BigDecimal.ZERO
    }

    /**
     * As cores dos setores (withColors): SERIES na ordem do servidor, pulando o "Sem setor" (null),
     * que fica com OTHER_COLOR; o que passa da paleta tambem. -1 = OTHER_COLOR.
     */
    fun sectorColorIndices(sectors: List<String?>, colors: Int = 8): List<Int> {
        var index = 0
        return sectors.map { sector ->
            if (sector == null) {
                -1
            } else {
                val color = if (index < colors) index else -1
                index += 1
                color
            }
        }
    }

    // ---- IR: os meses de DARF ----

    /** Um mes da renda variavel, so o que a lista le. */
    data class TaxMonth(
        val month: String,
        val stockSales: BigDecimal?,
        val etfSales: BigDecimal?,
        val reitSales: BigDecimal?,
        val darf: BigDecimal?,
        val darfCarried: BigDecimal?,
    )

    private fun truthy(value: BigDecimal?) = value != null && value.signum() != 0

    /** Os meses com alguma venda ou DARF (os outros nao aparecem). */
    fun <T> activeMonths(months: List<T>, view: (T) -> TaxMonth): List<T> = months.filter { item ->
        val month = view(item)
        truthy(month.stockSales) || truthy(month.etfSales) || truthy(month.reitSales) || truthy(month.darf) || truthy(month.darfCarried)
    }

    /** A coluna de ETFs e BDRs so aparece quando houve venda deles. */
    fun <T> hasEtfs(months: List<T>, view: (T) -> TaxMonth): Boolean = months.any { truthy(view(it).etfSales) }

    private val MONTH_NAMES = listOf("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")

    /** "2026-03" -> "mar/2026". */
    fun monthName(key: String): String {
        val parts = key.split("-")
        val month = parts.getOrNull(1)?.toIntOrNull()
        return "${month?.let { MONTH_NAMES.getOrNull(it - 1) } ?: "undefined"}/${parts.getOrNull(0).orEmpty()}"
    }

    /** As opcoes do ano: o escolhido, os que tem dado e o atual, do mais novo ao mais velho. */
    fun yearOptions(chosen: Int, available: List<Int>, current: Int): List<Int> =
        (listOf(chosen) + available.ifEmpty { listOf(chosen) } + current).distinct().sortedDescending()
}
