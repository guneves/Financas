// Par: o que pages/Dashboard.jsx (CategoryList, o "Ritmo de gastos") e DeltaBadge de
// components/ui.jsx escrevem inline sobre os numeros de GET /api/home/panels. Os numeros sao do
// servidor (services/home_panels.py); aqui so o texto e a cor. Puro: HomePanelsRulesTest.
package br.financas.app.rules

import br.financas.app.core.shortMonthLabel
import java.math.BigDecimal
import java.math.RoundingMode

object HomePanelsRules {

    /** A cor do DeltaBadge: verde (bom), rosa (ruim) ou neutra (arredonda para 0%). */
    enum class DeltaTone { GOOD, BAD, FLAT }

    /** "12,3%": o modulo com no maximo uma casa, como o toLocaleString do DeltaBadge. */
    fun deltaText(value: Double): String {
        val rounded = BigDecimal.valueOf(Math.abs(value)).setScale(1, RoundingMode.HALF_UP).stripTrailingZeros()
        return rounded.toPlainString().replace('.', ',') + "%"
    }

    /** [inverse]: subir e ruim (gasto). */
    fun deltaTone(value: Double, inverse: Boolean = true): DeltaTone {
        if (Math.abs(value) < 0.05) return DeltaTone.FLAT
        val up = value >= 0
        return if (up != inverse) DeltaTone.GOOD else DeltaTone.BAD
    }

    fun deltaUp(value: Double): Boolean = value >= 0

    /**
     * O indice da cor de uma categoria na lista (SERIES[i]), ou -1 = a cor de "outros": a partir
     * da sexta, quando ha mais de seis.
     */
    fun categoryColorIndex(index: Int, size: Int): Int = if (index < 5 || size <= 6) index else -1

    /** "62% conta", "cartão" ou "conta": de onde saiu o gasto da categoria. */
    fun channelLabel(cash: BigDecimal, credit: BigDecimal, value: BigDecimal): String = when {
        credit.signum() > 0 && cash.signum() > 0 -> {
            val share = if (value.signum() > 0) cash.multiply(BigDecimal(100)).divide(value, 0, RoundingMode.HALF_UP) else BigDecimal.ZERO
            "${share.toPlainString()}% conta"
        }
        credit.signum() > 0 -> "cartão"
        else -> "conta"
    }

    /** A fatia de [value] em [total], de 0 a 1, para a barra da categoria. */
    fun share(value: BigDecimal, total: BigDecimal): Float =
        if (total.signum() > 0) value.divide(total, 4, RoundingMode.HALF_UP).toFloat().coerceIn(0f, 1f) else 0f

    /** "Média de 3 meses" ou, com um mes so, "Mês de set/26". */
    fun paceAverageLabel(monthKeys: List<String>): String =
        if (monthKeys.size > 1) "Média de ${monthKeys.size} meses" else "Mês de ${shortMonthLabel(monthKeys.firstOrNull())}"

    /** -1 abaixo, 0 na media (menos de meio centavo), 1 acima. */
    fun paceDirection(currentToDate: BigDecimal, averageToDate: BigDecimal): Int {
        val difference = currentToDate - averageToDate
        return if (difference.abs() < BigDecimal("0.005")) 0 else difference.signum()
    }

    /** " · 2/3" para a linha da compra; nada numa compra a vista. */
    fun installmentSuffix(info: String?): String = if (!info.isNullOrEmpty() && info != "1/1") " · $info" else ""

    /** O rotulo do eixo do ritmo: so os dias 1, 6, 11... (o interval={4} da web). */
    fun paceAxisLabel(day: Int): String = if ((day - 1) % 5 == 0) day.toString() else ""

    /** A barra de progresso do parcelamento: pagas / total. */
    fun paidFraction(paid: Int, total: Int): Float = if (total > 0) (paid.toFloat() / total).coerceIn(0f, 1f) else 0f

    /** "Em destaque, a fatura de outubro de 2026." / "... a próxima fatura de cada cartão." */
    fun projectionNote(nextMonths: List<String>, monthLabel: (String) -> String): String = when {
        nextMonths.isEmpty() -> ""
        nextMonths.size == 1 -> "Em destaque, a fatura de ${monthLabel(nextMonths[0])}."
        else -> "Em destaque, a próxima fatura de cada cartão."
    }
}
