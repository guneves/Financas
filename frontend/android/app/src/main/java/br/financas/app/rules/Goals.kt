// Port: mudou um, muda o outro, com um teste de cada lado.
// Este arquivo e o port de frontend/src/lib/goals.js (testes: goals.test.js e GoalsTest.kt): os
// textos da previsao e o selo de cada meta. Todo valor vem do servidor (services/goals.py).
// Tambem o corpo do sheet (payloadFromForm de pages/Metas.jsx), que aqui limpa os campos que o
// tipo esconde.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.core.MoneyInput
import br.financas.app.core.parseMoneyInput
import java.math.BigDecimal

object Goals {

    private val MONTHS_SHORT = listOf("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")

    /** 'AAAA-MM' -> 'out/2028'. */
    fun shortMonthYear(key: String): String {
        val parts = key.split("-")
        val year = parts.getOrNull(0)?.toIntOrNull() ?: return key
        val month = parts.getOrNull(1)?.toIntOrNull()?.takeIf { it in 1..12 } ?: return key
        return "${MONTHS_SHORT[month - 1]}/$year"
    }

    private fun plural(count: Int, one: String, many: String) = "$count ${if (count == 1) one else many}"

    fun forecastText(reached: Boolean, kind: String, estimatedMonth: String?): String = when {
        reached -> "Alcançada"
        kind == INCOME -> "—"
        estimatedMonth.isNullOrEmpty() -> "Sem previsão"
        else -> shortMonthYear(estimatedMonth)
    }

    fun forecastHint(reached: Boolean, kind: String, estimatedMonth: String?, estimatedMonths: Int?): String {
        if (reached || kind == INCOME) return ""
        if (estimatedMonth.isNullOrEmpty()) return "Informe um aporte mensal"
        val total = estimatedMonths ?: 0
        val parts = listOfNotNull(
            (total / 12).takeIf { it > 0 }?.let { plural(it, "ano", "anos") },
            (total % 12).takeIf { it > 0 }?.let { plural(it, "mês", "meses") },
        )
        return if (parts.isEmpty()) "" else "em ${parts.joinToString(" e ")}"
    }

    enum class BadgeTone { SUCCESS, WARNING, NEUTRAL }

    data class GoalBadge(val label: String, val tone: BadgeTone)

    /** Alcancada vence o prazo; sem data (onTrack null), nenhum selo. */
    fun badge(reached: Boolean, onTrack: Boolean?): GoalBadge? = when {
        reached -> GoalBadge("Alcançada", BadgeTone.SUCCESS)
        onTrack == false -> GoalBadge("Fora do prazo", BadgeTone.WARNING)
        onTrack == true -> GoalBadge("No prazo", BadgeTone.NEUTRAL)
        else -> null
    }

    /** As classes de uma meta "Classe" (CLASSES de Metas.jsx), na ordem do seletor. */
    val CLASSES = listOf("STOCKS", "REIT", "FIXED_INCOME", "OTHER")

    /** getClassLabel() de pages/investimentos/helpers.js. */
    fun classLabel(assetClass: String?): String = when (assetClass) {
        "STOCKS" -> "Ações"
        "FIXED_INCOME" -> "Renda Fixa"
        "REIT" -> "Fundos Imobiliários"
        "OTHER" -> "Outros"
        else -> assetClass.orEmpty()
    }

    const val INCOME = "MONTHLY_INCOME"
    const val ASSET_CLASS = "ASSET_CLASS"

    /** O formulario do sheet, como digitado. */
    data class GoalForm(
        val name: String = "",
        val kind: String = "NET_WORTH",
        val assetClass: String = "STOCKS",
        val targetAmount: String = "",
        val monthlyContribution: String = "",
        val annualReturnPercent: String = "",
        val targetDate: String = "",
    )

    /**
     * O corpo de POST/PATCH /api/goals. Vazio -> null (o aporte vazio e 0); o que nao for numero
     * vai como texto e o servidor recusa com a mensagem dele. Diferente da web: a meta de renda
     * manda aporte 0 e rentabilidade e data null (o servidor ja os ignora para ela).
     */
    fun payload(form: GoalForm): Map<String, Any?> {
        val income = form.kind == INCOME
        return linkedMapOf(
            "name" to form.name,
            "kind" to form.kind,
            "asset_class" to if (form.kind == ASSET_CLASS) form.assetClass else null,
            "target_amount" to number(form.targetAmount),
            "monthly_contribution" to if (income) BigDecimal.ZERO else (number(form.monthlyContribution) ?: BigDecimal.ZERO),
            "annual_return_percent" to if (income) null else number(form.annualReturnPercent),
            "target_date" to if (income) null else form.targetDate.ifEmpty { null },
        )
    }

    // "1.234,56" ou "8,5" -> numero (parseMoneyInput; um "-" na frente vale, a rentabilidade pode
    // ser negativa); vazio -> null; invalido -> o texto, que o servidor recusa.
    private fun number(text: String): Any? {
        val trimmed = text.trim()
        if (trimmed.isEmpty()) return null
        val negative = trimmed.startsWith("-")
        return when (val parsed = parseMoneyInput(if (negative) trimmed.drop(1) else trimmed)) {
            is MoneyInput.Amount -> if (negative) parsed.value.negate() else parsed.value
            else -> trimmed
        }
    }
}
