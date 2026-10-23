// Port: mudou um, muda o outro, com um teste de cada lado.
// Par: frontend/src/lib/homeFlow.js (homeFlow.test.js) — flowPoint, flowSummary, savingsRateText —
// e frontend/src/lib/chartFormat.js (chartFormat.test.js) — compactAxis. Aqui: HomeFlowTest.kt,
// os mesmos casos. Dinheiro em BigDecimal (o JS soma em ponto flutuante; os valores do servidor
// ja vem em centavos, entao so um empate exato numa media pode arredondar diferente).
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.core.formatQuantity
import java.math.BigDecimal
import java.math.RoundingMode

/** Um mes do fluxo como o grafico o desenha (o flowPoint do JS). */
data class FlowPoint(
    val key: String,
    val label: String,
    val income: BigDecimal,
    /** A despesa abaixo do zero. */
    val expense: BigDecimal,
    /** Aporte menos resgate, com o sinal trocado: abaixo do zero o mes investiu. */
    val investment: BigDecimal,
    val invested: BigDecimal,
    val redeemed: BigDecimal,
    /** Recebido de outras pessoas menos o pago por elas. */
    val others: BigDecimal,
    val othersPaid: BigDecimal,
    val othersReceived: BigDecimal,
    val net: BigDecimal,
    val balance: BigDecimal,
)

/** As medias de "Fluxo de caixa" (o flowSummary do JS). [savingsRate] null = sem receita. */
data class FlowSummary(
    val avgIncome: BigDecimal,
    val avgExpense: BigDecimal,
    val avgInvestment: BigDecimal,
    val savingsRate: BigDecimal?,
    val hasData: Boolean,
    val hasInvestment: Boolean,
    val hasOthers: Boolean,
)

object HomeFlow {
    private const val SCALE = 10
    private val HUNDRED = BigDecimal(100)
    private val THOUSAND = BigDecimal(1000)
    private val MILLION = BigDecimal(1_000_000)
    private val TEN_THOUSAND = BigDecimal(10_000)

    private fun cents(value: BigDecimal?): Long = OutboxPending.toCents(value)

    private fun fromCents(cents: Long): BigDecimal = BigDecimal.valueOf(cents, 2)

    /** O mes de GET /api/home como ponto do grafico; o rotulo e o curto ("out/26"). */
    fun flowPoint(month: HomeMonth): FlowPoint = FlowPoint(
        key = month.month,
        label = br.financas.app.core.shortMonthLabel(month.month),
        income = month.income,
        expense = fromCents(-cents(month.expense)),
        investment = fromCents(-(cents(month.invested) - cents(month.redeemed))),
        invested = month.invested,
        redeemed = month.redeemed,
        others = fromCents(cents(month.othersReceived) - cents(month.othersPaid)),
        othersPaid = month.othersPaid,
        othersReceived = month.othersReceived,
        net = month.net,
        balance = month.balance,
    )

    private fun hasInvestment(point: FlowPoint) = point.invested.signum() != 0 || point.redeemed.signum() != 0

    private fun hasOthers(point: FlowPoint) = point.othersPaid.signum() != 0 || point.othersReceived.signum() != 0

    /**
     * As medias contam so os meses com algum movimento (um mes antes de comecar a usar o app
     * puxaria a media para baixo). A taxa de poupanca e (receita - despesa) / receita: o que foi
     * investido conta como poupado.
     */
    fun flowSummary(points: List<FlowPoint>): FlowSummary {
        val active = points.filter {
            it.income.signum() != 0 || it.expense.signum() != 0 || hasInvestment(it) || hasOthers(it)
        }
        val income = points.fold(BigDecimal.ZERO) { acc, it -> acc + it.income }
        val expense = points.fold(BigDecimal.ZERO) { acc, it -> acc - it.expense }
        val investment = points.fold(BigDecimal.ZERO) { acc, it -> acc - it.investment }
        val months = BigDecimal(maxOf(active.size, 1))
        return FlowSummary(
            avgIncome = income.divide(months, SCALE, RoundingMode.HALF_UP),
            avgExpense = expense.divide(months, SCALE, RoundingMode.HALF_UP),
            avgInvestment = investment.divide(months, SCALE, RoundingMode.HALF_UP),
            savingsRate = if (income.signum() > 0) {
                (income - expense).multiply(HUNDRED).divide(income, SCALE, RoundingMode.HALF_UP)
            } else {
                null
            },
            hasData = active.isNotEmpty(),
            hasInvestment = points.any(::hasInvestment),
            hasOthers = points.any(::hasOthers),
        )
    }

    /**
     * "Taxa de poupança": uma casa no maximo, "—" sem receita. O toLocaleString do JS: hifen no
     * negativo (nao o U+2212 dos valores), e "-0" quando arredonda para zero.
     */
    fun savingsRateText(rate: BigDecimal?): String {
        if (rate == null) return "—"
        val sign = if (rate.signum() < 0) "-" else ""
        return sign + formatQuantity(rate.abs().setScale(1, RoundingMode.HALF_UP)) + "%"
    }

    /** O eixo de valores dos graficos: "1,5 mil", "13 mil", "1,3 mi", sem o "R$". */
    fun compactAxis(value: BigDecimal?): String {
        val number = value ?: BigDecimal.ZERO
        val absolute = number.abs()
        val sign = if (number.signum() < 0) "−" else ""
        val text = when {
            absolute >= MILLION ->
                formatQuantity(absolute.divide(MILLION).setScale(1, RoundingMode.HALF_UP)) + " mi"
            absolute >= THOUSAND -> {
                val digits = if (absolute >= TEN_THOUSAND) 0 else 1
                formatQuantity(absolute.divide(THOUSAND).setScale(digits, RoundingMode.HALF_UP)) + " mil"
            }
            else -> formatQuantity(absolute.setScale(0, RoundingMode.HALF_UP))
        }
        return sign + text
    }
}
