// Port: mudou um, muda o outro, com um teste de cada lado.
// Este arquivo e o port do lado da entrada de frontend/src/lib/monthlyPlan.js (testes:
// monthlyPlan.test.js e MonthlyPlanTest.kt): o texto de cada alerta, a chave de dispensa, os
// limites dos controles de % e a previa em R$ enquanto se digita. parseMoneyInput() e
// moneyInputValue() estao em core/MoneyInput.kt.
//
// O servidor calcula todo R$ do plano (services/budgets.py, percent_of()); aqui so a previa, com
// a mesma conta: centavos x percentual (seis casas) em inteiros, meio-para-cima, sem Double.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.core.MoneyInput
import br.financas.app.core.formatCurrency
import br.financas.app.core.formatDecimal
import br.financas.app.core.monthLabel
import br.financas.app.data.PlanFlagDto
import java.math.BigDecimal
import java.math.BigInteger
import java.math.RoundingMode

/** O tom do AlertMessage/Badge de um alerta (FLAG_TONES). */
enum class FlagTone { DANGER, WARNING, SUCCESS, INFO }

/** O estado da barra do Gastar e de uma categoria (BUDGET_STATUS_LABELS/TONES). */
enum class BudgetStatus(val label: String) {
    OK("No plano"),
    WARNING("Perto do limite"),
    OVER("Estourou"),
    NEEDS_INCOME("Falta a renda");

    companion object {
        fun of(code: String?): BudgetStatus = entries.firstOrNull { it.name == code } ?: OK
    }
}

/** O que livePlanTotals devolve: os R$ e o "Sem destino" da linha ao vivo e o motivo de nao salvar. */
data class LivePlanTotals(
    val convert: Boolean,
    val investAmount: BigDecimal?,
    val spendAmount: BigDecimal?,
    val unallocatedPercent: BigDecimal?,
    val over: Boolean,
    /** null = pode salvar. */
    val blocked: String?,
)

object MonthlyPlan {

    /** Tom do backend -> tom do alerta. */
    val FLAG_TONES: Map<String, FlagTone> = mapOf(
        "loss" to FlagTone.DANGER,
        "warning" to FlagTone.WARNING,
        "gain" to FlagTone.SUCCESS,
        "info" to FlagTone.INFO,
    )

    fun flagTone(tone: String?): FlagTone = FLAG_TONES[tone] ?: FlagTone.INFO

    private fun days(count: Int) = if (count == 1) "1 dia" else "$count dias"

    fun flagText(flag: PlanFlagDto): String {
        val amount = formatCurrency(flag.amount)
        return when (flag.code) {
            "PLAN_OVER_INCOME" -> "Investir e gastar passam da renda do mês em $amount. Reduza um dos dois para o plano caber."
            "CATEGORIES_OVER_SPEND" ->
                "As categorias somam ${jsString(flag.percent).replace('.', ',')}% do Gastar: passam dele em $amount. Reduza alguma."
            "SPEND_OVER" -> "Os gastos passaram do plano em $amount."
            "SPEND_PACE" -> "No ritmo atual, o mês fecha com $amount de gastos — ${formatCurrency(flag.over)} acima do plano."
            "SPEND_NEAR" -> "Quase no limite: restam $amount para gastar no mês."
            "SPEND_KEPT" -> "Gastos dentro do plano: sobraram $amount."
            "INVEST_DONE" -> "Aporte do mês feito: $amount investidos."
            "INVEST_PENDING" -> {
                val left = flag.daysLeft ?: 0
                if (left > 0) "Faltam $amount para o aporte do mês (${days(left)} até o fim do mês)."
                else "Faltam $amount para o aporte do mês, e o mês termina hoje."
            }
            "INVEST_MISSED" -> "Faltaram $amount para o aporte planejado."
            "GOAL_SHORT" ->
                "Meta “${flag.goalName}”: precisa de $amount por mês até ${monthLabel(flag.targetMonth)}. O plano aporta ${formatCurrency(flag.missing)} a menos que isso."
            "GOAL_COVERED" ->
                "Meta “${flag.goalName}”: o aporte planejado cobre os $amount por mês até ${monthLabel(flag.targetMonth)}."
            else -> ""
        }
    }

    // Alertas que pedem acao primeiro; as boas noticias por ultimo (sort estavel, como o do JS).
    private val TONE_ORDER = mapOf("loss" to 0, "warning" to 1, "info" to 2, "gain" to 3)

    fun sortFlags(flags: List<PlanFlagDto>?): List<PlanFlagDto> =
        flags.orEmpty().sortedBy { TONE_ORDER[it.tone] ?: 9 }

    /** Codigo + mes (+ meta): o mesmo alerta nao volta neste mes; outro codigo, outra meta ou outro mes voltam. */
    fun planFlagKey(flag: PlanFlagDto, month: String): String {
        val key = "plan:$month:${flag.code}"
        return if (flag.goalId == null) key else "$key:${flag.goalId}"
    }

    fun visibleFlags(flags: List<PlanFlagDto>?, month: String, dismissedKeys: Collection<String> = emptyList()): List<PlanFlagDto> {
        val dismissed = dismissedKeys.toSet()
        return flags.orEmpty().filter { planFlagKey(it, month) !in dismissed }
    }

    /** Estado da barra do Gastar (as mesmas cores do orcamento por categoria). */
    fun spendStatus(flags: List<PlanFlagDto>?): BudgetStatus {
        val list = flags.orEmpty()
        if (list.any { it.code == "SPEND_OVER" }) return BudgetStatus.OVER
        if (list.any { it.code == "SPEND_PACE" || it.code == "SPEND_NEAR" }) return BudgetStatus.WARNING
        return BudgetStatus.OK
    }

    // ---- O plano em %, na tela ----

    private val MICRO = BigInteger.valueOf(1_000_000)
    private val HUNDRED_MICRO = BigInteger.valueOf(100_000_000)
    private val HUNDRED = BigDecimal(100)

    /** O Math.round() do JS (meio para +infinito) de um valor decimal exato. */
    private fun jsRound(value: BigDecimal): BigInteger = value.setScale(0, RoundingMode.FLOOR).let { floor ->
        if (value.subtract(floor) >= BigDecimal("0.5")) floor.toBigInteger() + BigInteger.ONE else floor.toBigInteger()
    }

    // 12,5 -> 12500000 (milionesimos de ponto percentual).
    private fun toMicro(percent: BigDecimal): BigInteger = jsRound(percent.movePointRight(6))

    private fun fromMicro(micro: BigInteger): BigDecimal = plain(BigDecimal(micro).movePointLeft(6))

    /** `percent`% de `amount`, em reais (duas casas). null quando falta um dos dois. */
    fun percentOf(amount: BigDecimal?, percent: BigDecimal?): BigDecimal? {
        if (amount == null || percent == null) return null
        val cents = jsRound(amount.movePointRight(2))
        val product = cents * toMicro(percent)
        // Meio para longe do zero sobre o valor absoluto, como o BigInt do JS.
        val quotient = BigDecimal(product).divide(BigDecimal(HUNDRED_MICRO), 0, RoundingMode.HALF_UP)
        val result = quotient.movePointLeft(2)
        return if (result.signum() == 0) BigDecimal.ZERO.setScale(2) else result
    }

    /** "20%", "33,33%", "12,5%": ate duas casas, sem zeros sobrando. null vale 0. */
    fun formatPlanPercent(value: BigDecimal?): String = "${formatDecimal(value ?: BigDecimal.ZERO, 2)}%"

    /** "Sem destino 15%", ou "Passa de 100% da renda em 5,5%"; null -> "". */
    fun unallocatedText(percent: BigDecimal?): String {
        if (percent == null) return ""
        if (percent.signum() < 0) return "Passa de 100% da renda em ${formatPlanPercent(percent.negate())}"
        return "Sem destino ${formatPlanPercent(percent)}"
    }

    /** "Recebido R$ 3.200,00 de R$ 5.000,00 esperados". */
    fun incomeReceivedText(received: BigDecimal?, planned: BigDecimal?): String =
        "Recebido ${formatCurrency(received)} de ${formatCurrency(planned)} esperados"

    const val BLOCKED_INCOME = "Informe a renda do mês."
    const val BLOCKED_PERCENTS = "Informe quanto da renda investir e gastar, em %."
    const val BLOCKED_OVER = "Investir e Gastar passam de 100% da renda."

    /**
     * A previa do sheet "Plano do mês", a cada tecla. [income] e o que parseMoneyInput leu; [invest]
     * e [spend] sao os controles (Empty = em branco). Num plano antigo sem renda ([legacyInvest] e
     * [legacySpend] presentes), os dois % em branco convertem os reais de antes (038).
     */
    fun livePlanTotals(
        income: MoneyInput,
        invest: MoneyInput,
        spend: MoneyInput,
        legacyInvest: BigDecimal? = null,
        legacySpend: BigDecimal? = null,
        hasLegacy: Boolean = false,
    ): LivePlanTotals {
        val incomeValue = (income as? MoneyInput.Amount)?.value
        val hasIncome = incomeValue != null && incomeValue.signum() > 0
        val convert = hasLegacy && invest == MoneyInput.Empty && spend == MoneyInput.Empty

        if (convert) {
            if (!hasIncome) return LivePlanTotals(true, null, null, null, false, BLOCKED_INCOME)
            val investAmount = legacyInvest ?: BigDecimal.ZERO
            val spendAmount = legacySpend ?: BigDecimal.ZERO
            val committed = jsRound(investAmount.add(spendAmount).movePointRight(2))
            val incomeCents = jsRound(incomeValue!!.movePointRight(2))
            val share = BigDecimal(committed * HUNDRED_MICRO).divide(BigDecimal(incomeCents), 0, RoundingMode.HALF_UP).toBigInteger()
            val unallocatedMicro = HUNDRED_MICRO - share
            // A conversao acima de 100% e aceita e vira alerta no plano (038).
            return LivePlanTotals(true, investAmount, spendAmount, fromMicro(unallocatedMicro), unallocatedMicro.signum() < 0, null)
        }

        val investValue = (invest as? MoneyInput.Amount)?.value?.takeIf { it.signum() >= 0 }
        val spendValue = (spend as? MoneyInput.Amount)?.value?.takeIf { it.signum() >= 0 }
        val investAmount = if (hasIncome && investValue != null) percentOf(incomeValue, investValue) else null
        val spendAmount = if (hasIncome && spendValue != null) percentOf(incomeValue, spendValue) else null
        var unallocated: BigDecimal? = null
        var over = false
        if (investValue != null && spendValue != null) {
            val micro = HUNDRED_MICRO - toMicro(investValue) - toMicro(spendValue)
            unallocated = fromMicro(micro)
            over = micro.signum() < 0
        }
        val blocked = when {
            !hasIncome -> BLOCKED_INCOME
            investValue == null || spendValue == null -> BLOCKED_PERCENTS
            over -> BLOCKED_OVER
            else -> null
        }
        return LivePlanTotals(false, investAmount, spendAmount, unallocated, over, blocked)
    }

    /** "Investir R$ 1.000,00 · Gastar R$ 3.500,00 · Sem destino 10%"; o que ainda nao da e "—". */
    fun livePlanText(totals: LivePlanTotals): String {
        fun money(value: BigDecimal?) = if (value == null) "—" else formatCurrency(value)
        val rest = totals.unallocatedPercent?.let { unallocatedText(it) } ?: "Sem destino —"
        return "Investir ${money(totals.investAmount)} · Gastar ${money(totals.spendAmount)} · $rest"
    }

    /** O R$ ao lado do % de uma categoria: % do Gastar em reais; null sem % valido ou sem Gastar. */
    fun categoryAmountPreview(spendAmount: BigDecimal?, percent: BigDecimal?): BigDecimal? {
        if (percent == null || percent.signum() < 0) return null
        return percentOf(spendAmount, percent)
    }

    // ---- Os controles deslizantes ----

    /** Os % andam de 1 em 1 ponto (PercentSlider). */
    val PERCENT_STEP: BigDecimal = BigDecimal.ONE

    private fun sixDecimals(value: BigDecimal): BigDecimal = plain(value.setScale(6, RoundingMode.HALF_UP))

    /** 100 - o que os outros ja levam, nunca abaixo de zero. null vale 0. */
    fun percentRoom(othersPercent: BigDecimal?, total: BigDecimal = HUNDRED): BigDecimal =
        sixDecimals(total.subtract(othersPercent ?: BigDecimal.ZERO)).max(BigDecimal.ZERO)

    /** O valor do controle dentro de [0, room]. null vale 0. */
    fun clampPercent(value: BigDecimal?, room: BigDecimal = HUNDRED): BigDecimal {
        val number = value ?: BigDecimal.ZERO
        return sixDecimals(number.max(BigDecimal.ZERO).min(room.max(BigDecimal.ZERO)))
    }

    private val EPSILON = BigDecimal("0.000000001")

    /** − e +: o proximo ponto inteiro na direcao, sem passar de room (33,33 + 1 -> 34; 66 + 1 com room 66,67 -> 66,67). */
    fun stepPercent(value: BigDecimal?, direction: Int, room: BigDecimal = HUNDRED): BigDecimal {
        val number = value ?: BigDecimal.ZERO
        val next = if (direction > 0) {
            number.add(EPSILON).setScale(0, RoundingMode.FLOOR).add(PERCENT_STEP)
        } else {
            number.subtract(EPSILON).setScale(0, RoundingMode.CEILING).subtract(PERCENT_STEP)
        }
        return clampPercent(next, room)
    }

    // O valor como o Number do JS: sem zeros finais e sem expoente.
    private fun plain(value: BigDecimal): BigDecimal {
        if (value.signum() == 0) return BigDecimal.ZERO
        val stripped = value.stripTrailingZeros()
        return if (stripped.scale() < 0) stripped.setScale(0) else stripped
    }

    // String(numero) do JS: 120.5 -> "120.5", 120 -> "120"; undefined -> "undefined".
    private fun jsString(value: BigDecimal?): String = value?.let { plain(it).toPlainString() } ?: "undefined"
}
