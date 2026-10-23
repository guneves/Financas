// Port: mudou um, muda o outro, com um teste de cada lado.
// Este arquivo e o port de parseMoneyInput() e moneyInputValue() de frontend/src/lib/monthlyPlan.js
// (testes: monthlyPlan.test.js e MoneyInputTest.kt).
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.core

import java.math.BigDecimal

/** O que parseMoneyInput leu: vazio (o null do JS), invalido (o NaN) ou um valor. */
sealed interface MoneyInput {
    data object Empty : MoneyInput
    data object Invalid : MoneyInput

    /** O valor como digitado, sem arredondar e sem zeros finais (1.500,00 = 1500, como o Number). */
    data class Amount(val value: BigDecimal) : MoneyInput
}

private val IGNORED = Regex(Js.whitespaceClass + "|R\\$")
private val DOT_THOUSANDS = Regex("^[1-9]\\d{0,2}(\\.\\d{3})+$")
private val GROUPED_DOT = Regex("^\\d{1,3}(\\.\\d{3})*$")
private val GROUPED_COMMA = Regex("^\\d{1,3}(,\\d{3})*$")
private val DIGITS = Regex("^\\d*$")

/**
 * "1.234,56", "1234,56", "1234.56", "1,234.56" -> 1234.56; "3.000" -> 3000.
 * Com virgula e ponto, o ultimo dos dois e o decimal e o outro separa milhar (em grupos de tres).
 * So ponto: grupos de tres depois de um digito que nao e zero sao milhar, como se escreve em reais
 * ("1.500"); senao e decimal ("0.500" -> 0,5). So virgula: decimal; mais de uma, milhar
 * ("1,234,567"). Vazio -> Empty; invalido (milhar fora do lugar, "1.2.3", sinal) -> Invalid.
 */
fun parseMoneyInput(value: String?): MoneyInput {
    // O trim() do JS tira o mesmo que o \s, e o \s sai de qualquer jeito: basta o replace.
    val text = IGNORED.replace(value ?: "", "")
    if (text.isEmpty()) return MoneyInput.Empty
    val lastComma = text.lastIndexOf(',')
    val lastDot = text.lastIndexOf('.')
    var integer = text
    var fraction = ""
    var groupSeparator = ""
    fun splitAt(index: Int) {
        integer = text.substring(0, index)
        fraction = text.substring(index + 1)
    }
    if (lastComma >= 0 && lastDot >= 0) {
        splitAt(maxOf(lastComma, lastDot))
        groupSeparator = if (lastComma > lastDot) "." else ","
    } else if (lastComma >= 0) {
        if (text.indexOf(',') == lastComma) splitAt(lastComma) else groupSeparator = ","
    } else if (lastDot >= 0) {
        if (DOT_THOUSANDS.matches(text)) groupSeparator = "."
        else if (text.indexOf('.') == lastDot) splitAt(lastDot)
        else return MoneyInput.Invalid
    }
    if (groupSeparator.isNotEmpty()) {
        val grouped = if (groupSeparator == ".") GROUPED_DOT else GROUPED_COMMA
        if (!grouped.matches(integer)) return MoneyInput.Invalid
        integer = integer.replace(groupSeparator, "")
    }
    if (!DIGITS.matches(integer) || !DIGITS.matches(fraction) || (integer.isEmpty() && fraction.isEmpty())) {
        return MoneyInput.Invalid
    }
    return MoneyInput.Amount(numberValue(BigDecimal("${integer.ifEmpty { "0" }}.${fraction.ifEmpty { "0" }}")))
}

/**
 * Valor guardado -> texto do campo, no formato que o teclado do celular digita: 1500.5 -> "1500,5".
 * Le o BigDecimal como o JS le um Number (sem zeros finais: 1500.50 -> "1500,5"); null -> "".
 */
fun moneyInputValue(value: BigDecimal?): String {
    if (value == null) return ""
    return numberValue(value).toPlainString().replaceFirst('.', ',')
}

/** O mesmo para um valor que chegou como texto ("1500.50" -> "1500,50", como String(v) no JS). */
fun moneyInputValue(value: String?): String {
    if (value.isNullOrEmpty()) return ""
    return value.replaceFirst('.', ',')
}

// O valor de um Number: sem zeros finais e sem expoente (1.5E+3 vira 1500).
private fun numberValue(value: BigDecimal): BigDecimal {
    val stripped = value.stripTrailingZeros()
    return if (stripped.scale() < 0) stripped.setScale(0) else stripped
}
