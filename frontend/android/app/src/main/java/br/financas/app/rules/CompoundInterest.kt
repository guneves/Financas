// Porte: mudou um, muda o outro, com um teste de cada lado.
// Par: frontend/src/lib/compoundInterest.js (compoundInterest.test.js); aqui
// CompoundInterestTest.kt, os mesmos casos na mesma ordem.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.core.Js
import kotlin.math.floor
import kotlin.math.pow

/**
 * Calculadora de juros compostos (Investimentos › Calculadora). Uma simulacao, nunca um valor
 * gravado: Double como na web (16-investimentos-alocacao-ir-calculadora.md).
 *
 *   VF = VP·(1+i)^n + PMT·((1+i)^n − 1)/i        aporte no fim do mes (postecipado)
 *   VF = VP·(1+i)^n + PMT·((1+i)^n − 1)/i·(1+i)  aporte no inicio do mes (antecipado)
 *
 * A taxa anual vira mensal pela taxa equivalente, (1+ia) = (1+im)^12 — a mesma de
 * services/goals.py —, nunca pela proporcional ia/12. A inflacao entra por Fisher.
 */
object CompoundInterest {
    const val MAX_MONTHS = 1200 // 100 anos
    const val MAX_RATE_PERCENT = 1000

    /** O formulario como texto, como o dono digita. Unidades: "year" | "month"; timing "end" | "start". */
    data class Form(
        val initial: String = "1000",
        val monthly: String = "500",
        val rate: String = "10",
        val rateUnit: String = "year",
        val period: String = "10",
        val periodUnit: String = "year",
        val timing: String = "end",
        val inflation: String = "",
    )

    val DEFAULT_FORM = Form()

    /** O formulario em numeros. */
    data class Input(
        val initial: Double,
        val monthly: Double,
        val months: Int,
        val monthlyRatePercent: Double,
        val annualRatePercent: Double,
        val timing: String,
        val inflationPercent: Double?,
    )

    /** [readForm]: os numeros, ou o erro. */
    sealed interface Reading {
        data class Ok(val input: Input) : Reading
    }

    /** [calculate]: o resultado, ou o erro. */
    sealed interface Calculation

    /** O formulario recusado, com o texto para a tela (o `{ error }` da web). */
    data class FormError(val message: String) : Reading, Calculation

    /** Uma linha da serie, no fim do mes (a 0 e o valor inicial); [real] em reais de hoje. */
    data class Row(
        val month: Int,
        val balance: Double,
        val invested: Double,
        val interest: Double,
        val interestInMonth: Double,
        val real: Double?,
    )

    data class YearRow(
        val year: Int,
        val months: Int,
        val balance: Double,
        val invested: Double,
        val interest: Double,
        val investedInYear: Double,
        val interestInYear: Double,
        val real: Double?,
    )

    data class Result(
        val input: Input,
        val schedule: List<Row>,
        val years: List<YearRow>,
        val final: Double,
        val invested: Double,
        val interest: Double,
        val real: Double?,
        val monthlyIncomeAtEnd: Double,
        val realAnnualRatePercent: Double?,
    ) : Calculation

    /** "1.234,56" do teclado brasileiro ou "1234.56". Vazio ou ilegivel e null. */
    fun parseNumber(value: String?): Double? {
        if (value == null) return null
        val text = Js.trim(value)
        if (text.isEmpty()) return null
        val normalized = if (text.contains(',')) text.replace(".", "").replaceFirst(",", ".") else text
        return Js.number(normalized)?.takeIf { it.isFinite() }
    }

    fun monthlyFromAnnual(annualPercent: Double): Double = ((1 + annualPercent / 100).pow(1.0 / 12) - 1) * 100

    fun annualFromMonthly(monthlyPercent: Double): Double = ((1 + monthlyPercent / 100).pow(12) - 1) * 100

    /** Taxa real anual (Fisher), em %. */
    fun realAnnualRate(annualPercent: Double, inflationPercent: Double): Double =
        ((1 + annualPercent / 100) / (1 + inflationPercent / 100) - 1) * 100

    fun readForm(form: Form): Reading {
        val initial = parseNumber(form.initial) ?: 0.0
        val monthly = parseNumber(form.monthly) ?: 0.0
        val rate = parseNumber(form.rate) ?: 0.0
        val period = parseNumber(form.period)
        val inflation = parseNumber(form.inflation)

        if (initial < 0 || monthly < 0) return FormError("Valor inicial e aporte não podem ser negativos.")
        if (rate <= -100) return FormError("A taxa precisa ser maior que −100%.")
        if (rate > MAX_RATE_PERCENT) return FormError("A taxa pode ir até $MAX_RATE_PERCENT%.")
        if (inflation != null && (inflation <= -100 || inflation > MAX_RATE_PERCENT)) {
            return FormError("Inflação fora do intervalo aceito.")
        }
        if (period == null || period <= 0) return FormError("Informe o período.")
        val months = if (form.periodUnit == "month") period else period * 12
        // Number.isInteger do JS: Infinity nao e inteiro.
        if (!months.isFinite() || floor(months) != months) {
            return FormError(
                if (form.periodUnit == "month") {
                    "O período em meses precisa ser inteiro."
                } else {
                    "Esse período não fecha em meses inteiros: informe em meses."
                },
            )
        }
        if (months > MAX_MONTHS) return FormError("O período pode ir até 100 anos.")

        return Reading.Ok(
            Input(
                initial = initial,
                monthly = monthly,
                months = months.toInt(),
                monthlyRatePercent = if (form.rateUnit == "month") rate else monthlyFromAnnual(rate),
                annualRatePercent = if (form.rateUnit == "month") annualFromMonthly(rate) else rate,
                timing = if (form.timing == "start") "start" else "end",
                inflationPercent = inflation,
            ),
        )
    }

    /** Mes a mes: saldo, total aportado e juros acumulados no fim do mes. A linha 0 e o valor inicial. */
    fun compoundSchedule(
        initial: Double,
        monthly: Double,
        months: Int,
        monthlyRatePercent: Double,
        timing: String = "end",
        inflationPercent: Double? = null,
    ): List<Row> {
        val rate = monthlyRatePercent / 100
        val deflator = inflationPercent?.let { (1 + it / 100).pow(1.0 / 12) }
        val rows = mutableListOf(Row(0, initial, initial, 0.0, 0.0, if (deflator != null) initial else null))
        var balance = initial
        var invested = initial
        for (month in 1..months) {
            if (timing == "start") {
                balance += monthly
                invested += monthly
            }
            val interestInMonth = balance * rate
            balance += interestInMonth
            if (timing != "start") {
                balance += monthly
                invested += monthly
            }
            rows.add(
                Row(
                    month = month,
                    balance = balance,
                    invested = invested,
                    interest = balance - invested,
                    interestInMonth = interestInMonth,
                    real = deflator?.let { balance / it.pow(month) },
                ),
            )
        }
        return rows
    }

    fun compoundSchedule(input: Input): List<Row> =
        compoundSchedule(input.initial, input.monthly, input.months, input.monthlyRatePercent, input.timing, input.inflationPercent)

    /** A forma fechada do valor futuro, para conferir a serie. */
    fun futureValue(initial: Double, monthly: Double, months: Int, monthlyRatePercent: Double, timing: String = "end"): Double {
        val rate = monthlyRatePercent / 100
        val growth = (1 + rate).pow(months)
        val annuity = if (rate == 0.0) months.toDouble() else (growth - 1) / rate
        return initial * growth + monthly * annuity * (if (timing == "start") 1 + rate else 1.0)
    }

    /** Um resumo por ano (o ultimo pode ser parcial): saldo no fim, aportes e juros do ano. */
    fun yearlyRows(schedule: List<Row>): List<YearRow> {
        val years = mutableListOf<YearRow>()
        val last = schedule.size - 1
        var end = 12
        while (end - 12 < last) {
            val to = schedule[minOf(end, last)]
            val from = schedule[end - 12]
            years.add(
                YearRow(
                    year = end / 12,
                    months = to.month - from.month,
                    balance = to.balance,
                    invested = to.invested,
                    interest = to.interest,
                    investedInYear = to.invested - from.invested,
                    interestInYear = to.interest - from.interest,
                    real = to.real,
                ),
            )
            end += 12
        }
        return years
    }

    /** Tudo o que a tela mostra, a partir do formulario; o erro de [readForm] quando ha. */
    fun calculate(form: Form): Calculation {
        val input = when (val reading = readForm(form)) {
            is FormError -> return reading
            is Reading.Ok -> reading.input
        }
        val schedule = compoundSchedule(input)
        val final = schedule.last()
        return Result(
            input = input,
            schedule = schedule,
            years = yearlyRows(schedule),
            final = final.balance,
            invested = final.invested,
            interest = final.interest,
            real = final.real,
            // Quanto o saldo final renderia no mes seguinte, a mesma taxa.
            monthlyIncomeAtEnd = final.balance * (input.monthlyRatePercent / 100),
            realAnnualRatePercent = input.inflationPercent?.let { realAnnualRate(input.annualRatePercent, it) },
        )
    }

    /** "Hoje", "Ano 3" ou "Mês 7" para o eixo e a tabela. */
    /**
     * Os pontos do grafico (chartPoints de Calculadora.jsx, inline la): ate 5 anos um por mes;
     * acima, um por ano, mais o ultimo. Devolve as linhas do [schedule] escolhidas.
     */
    fun chartPoints(schedule: List<Row>): List<Row> {
        val last = schedule.size - 1
        val step = if (last > 60) 12 else 1
        return schedule.filter { it.month % step == 0 || it.month == last }
    }

    fun periodLabel(month: Int): String = when {
        month == 0 -> "Hoje"
        month % 12 == 0 -> "Ano ${month / 12}"
        else -> "Mês $month"
    }

    /** "1 ano", "10 anos", "7 meses", "2 anos e 6 meses". */
    fun durationText(months: Int): String {
        val years = months / 12
        val rest = months % 12
        val parts = mutableListOf<String>()
        if (years != 0) parts.add("$years ${if (years == 1) "ano" else "anos"}")
        if (rest != 0) parts.add("$rest ${if (rest == 1) "mês" else "meses"}")
        return parts.joinToString(" e ")
    }
}
