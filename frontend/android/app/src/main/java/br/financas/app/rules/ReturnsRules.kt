// Porte: mudou um, muda o outro, com um teste de cada lado.
// Par: o que pages/investimentos/Rentabilidade.jsx faz inline (comparisonItems, comparisonHint,
// toneOf, signedPercent, percentAxis, BENCHMARK_COLORS, DEFAULT_VISIBLE e o texto do periodo),
// sem teste do lado web. Aqui ReturnsRulesTest.kt. Os numeros sao todos do servidor; so o cartao
// do CDI e montado aqui, com a diferenca arredondada a 2 casas.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.core.formatPercent
import br.financas.app.core.shortMonthLabel
import java.math.BigDecimal
import java.math.RoundingMode

object ReturnsRules {
    /** Os periodos (6M..5A e "Tudo" = desde a primeira operacao, ate 60 meses). */
    val PERIODS = listOf("6" to "6M", "12" to "1A", "24" to "2A", "36" to "3A", "60" to "5A", "all" to "Tudo")
    const val DEFAULT_PERIOD = "12"

    /** Os indices ligados de fabrica. */
    val DEFAULT_VISIBLE = setOf("CDI", "IPCA", "IBOV")

    /** A cor de cada indice segue o indice, nunca a posicao: o nome do token. */
    val BENCHMARK_COLORS = mapOf(
        "CDI" to "zinc-400",
        "IPCA" to "series-3",
        "IBOV" to "series-1",
        "IFIX" to "series-2",
        "IDIV" to "series-6",
    )

    const val PORTFOLIO_COLOR = "series-0"

    val MONTH_NAMES = listOf("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")

    /** Um cartao de comparacao: o CDI (montado aqui) ou um benchmark do servidor. */
    data class Comparison(
        val code: String,
        val label: String,
        val available: Boolean,
        val complete: Boolean,
        val monthsCovered: Int? = null,
        val monthsTotal: Int? = null,
        val periodPercent: BigDecimal? = null,
        val differencePp: BigDecimal? = null,
        val note: String? = null,
    )

    const val CDI_NOTE = "O BCB não respondeu o CDI."

    /** O CDI primeiro, depois os indices do servidor na ordem dele. */
    fun comparisonItems(
        twrPercent: BigDecimal?,
        cdiAvailable: Boolean,
        cdiPercent: BigDecimal?,
        benchmarks: List<Comparison>,
    ): List<Comparison> {
        val difference = if (twrPercent != null && cdiPercent != null) (twrPercent - cdiPercent).setScale(2, RoundingMode.HALF_UP) else null
        val cdi = Comparison(
            code = "CDI",
            label = "CDI",
            available = cdiAvailable,
            complete = cdiAvailable,
            periodPercent = cdiPercent,
            differencePp = difference,
            note = if (cdiAvailable) null else CDI_NOTE,
        )
        return listOf(cdi) + benchmarks
    }

    /** A linha de baixo do cartao: indisponivel, meses cobertos, a diferenca da carteira ou "no período". */
    fun comparisonHint(item: Comparison): String = when {
        !item.available -> "indisponível"
        !item.complete -> "${item.monthsCovered} de ${item.monthsTotal} meses"
        item.differencePp != null -> {
            val sign = if (item.differencePp.signum() > 0) "+" else ""
            // toLocaleString com 2 casas: o negativo leva o "-" comum, como no JS.
            "carteira $sign${ptBrNumber(item.differencePp.toDouble(), 2, 2)} p.p."
        }
        else -> "no período"
    }

    /** O tom de um percentual: ganho, perda, zero ou sem dado. */
    enum class Tone { GAIN, LOSS, NEUTRAL, MUTED }

    fun toneOf(value: BigDecimal?): Tone = when {
        value == null -> Tone.MUTED
        value.signum() > 0 -> Tone.GAIN
        value.signum() < 0 -> Tone.LOSS
        else -> Tone.NEUTRAL
    }

    /** "+1,23%"; sem dado "—". */
    fun signedPercent(value: BigDecimal?): String = if (value == null) "—" else formatPercent(value, 2, signed = true)

    /** O eixo: "1,5%", ate 1 casa. */
    fun percentAxis(value: Double): String = "${ptBrNumber(value, 0, 1)}%"

    /** "set/25 a out/26 (desde a 1ª operação) · TWR, valor bruto". */
    fun periodHint(start: String?, end: String?, startsAfterWindow: Boolean): String {
        if (start == null && end == null) return "TWR, valor bruto"
        val since = if (startsAfterWindow) " (desde a 1ª operação)" else ""
        return "${shortMonthLabel(start)} a ${shortMonthLabel(end)}$since · TWR, valor bruto"
    }

    /** Os indices visiveis no grafico: os disponiveis entre os escolhidos, na ordem dos cartoes. */
    fun shown(items: List<Comparison>, visible: Set<String>): List<Comparison> =
        items.filter { it.available && it.code in visible }

    /** Liga/desliga um indice. */
    fun toggle(visible: Set<String>, code: String): Set<String> = if (code in visible) visible - code else visible + code
}
