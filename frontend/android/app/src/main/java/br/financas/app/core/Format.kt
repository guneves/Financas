// Port: mudou um, muda o outro, com um teste de cada lado.
// Este arquivo e o port de frontend/src/lib/format.js (testes: format.test.js e FormatTest.kt).
//
// Formatadores do pt-BR montados a mao, sem NumberFormat nem DateTimeFormatter de localidade: a
// saida tem de ser a do Intl do navegador (espaco inquebravel U+00A0 depois do "R$", sinal de
// menos U+2212), qualquer que seja a versao dos dados de localidade da JVM ou do Android.
// Dinheiro e BigDecimal, arredondado HALF_UP (o Intl arredonda "para longe do zero", o mesmo).
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.core

import java.math.BigDecimal
import java.math.RoundingMode
import java.time.LocalDate

/** Sinal de menos de verdade (U+2212), como em format.js. */
const val MINUS: String = "−"

/** O espaco depois do "R$" no Intl do pt-BR: inquebravel, sinal e numero nunca se separam. */
const val NBSP: String = " "

private val MONTHS_LONG = listOf(
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)

// O "month: 'short'" do pt-BR sem o ponto ("out.", que shortMonthLabel tira).
private val MONTHS_SHORT = listOf(
    "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez",
)

// O que o Intl escreve para uma data invalida (new Date(NaN).toLocaleDateString()).
private const val INVALID_DATE = "Invalid Date"

/** "R$ 1.234,56"; negativo "−R$ 1.234,56"; null vale 0. Duas casas, HALF_UP. */
fun formatCurrency(value: BigDecimal?): String = currency(value ?: BigDecimal.ZERO, 2, 2)

/**
 * Valor com sinal explicito, para listas de entradas e saidas: "+R$ 8.500,00", "−R$ 1.048,22".
 * `sign` (1, -1 ou 0) vale quando o valor vem sempre positivo e o sentido esta no tipo do
 * lancamento; null usa o sinal do valor. Zero sai sem sinal (um valor que so arredonda para zero,
 * como 0,004, ainda leva o sinal, como no JS).
 */
fun formatSignedCurrency(value: BigDecimal?, sign: Int? = null): String {
    val number = value ?: BigDecimal.ZERO
    val amount = number.abs()
    val direction = sign ?: number.signum()
    val body = formatCurrency(amount)
    if (direction == 0 || amount.signum() == 0) return body
    return (if (direction > 0) "+" else MINUS) + body
}

/** Preco unitario de ativo: de 2 a 6 casas ("R$ 0,000001"). */
fun formatUnitCurrency(value: BigDecimal?): String = currency(value ?: BigDecimal.ZERO, 2, 6)

/** Quantidade de cotas: "1.022", "62,7", "0,33333333" — ate 8 casas, separadores do pt-BR. */
fun formatQuantity(value: BigDecimal?): String {
    val number = value ?: BigDecimal.ZERO
    return signPrefix(number) + grouped(number.abs(), 0, 8)
}

/** "12,50%", com virgula. `signed` poe "+" nos positivos (rentabilidade). */
fun formatPercent(value: BigDecimal?, digits: Int = 2, signed: Boolean = false): String {
    // O Intl recusa (RangeError) casas fora de 0..100.
    require(digits in 0..100) { "digits fora de 0..100: $digits" }
    val number = value ?: BigDecimal.ZERO
    val text = signPrefix(number) + grouped(number.abs(), digits, digits)
    return (if (signed && number.signum() > 0) "+" else "") + text + "%"
}

/**
 * 'AAAA-MM-DD' (os 10 primeiros caracteres) -> LocalDate, com as regras de new Date(y, m - 1, d)
 * do JS: um dia ou mes alem do fim rola para a frente ("2026-02-30" -> 02/03/2026) e um ano de 0
 * a 99 vira 19xx. Vazio, ano/mes/dia ausente ou zero -> null; uma data que o JS deixaria
 * invalida (fora do alcance do Date) tambem -> null.
 */
fun parseLocalDate(value: String?): LocalDate? {
    if (value.isNullOrEmpty()) return null
    val parts = value.take(10).split("-")
    val year = Js.number(parts.getOrNull(0))
    val month = Js.number(parts.getOrNull(1))
    val day = Js.number(parts.getOrNull(2))
    if (!Js.truthy(year) || !Js.truthy(month) || !Js.truthy(day)) return null
    return Js.makeDate(year!!, month!! - 1, day!!)
}

/** 'AAAA-MM-DD' -> "dd/MM/aaaa" (o ano sem zeros a esquerda, como o Intl); invalida -> fallback. */
fun formatDateBR(value: String?, fallback: String = "-"): String {
    val date = parseLocalDate(value) ?: return fallback
    return "${pad2(date.dayOfMonth)}/${pad2(date.monthValue)}/${date.year}"
}

/** LocalDate -> 'AAAA-MM-DD' (o ano como o JS escreve getFullYear(), sem completar com zeros). */
fun getLocalDateString(date: LocalDate = LocalDate.now()): String =
    "${date.year}-${pad2(date.monthValue)}-${pad2(date.dayOfMonth)}"

/** 'AAAA-MM' — a chave de mes que o backend usa em orcamentos. */
fun monthKey(date: LocalDate = LocalDate.now()): String = "${date.year}-${pad2(date.monthValue)}"

/** 'AAAA-MM' -> "outubro de 2026"; um mes alem de 12 rola o ano; chave invalida volta como veio. */
fun monthLabel(key: String?): String {
    val text = key ?: ""
    val parts = text.split("-")
    val year = Js.number(parts.getOrNull(0))
    val month = Js.number(parts.getOrNull(1))
    if (!Js.truthy(year) || !Js.truthy(month)) return text
    val date = Js.makeDate(year!!, month!! - 1, 1.0) ?: return INVALID_DATE
    return "${MONTHS_LONG[date.monthValue - 1]} de ${date.year}"
}

private val SHORT_ISO = Regex("^\\d{4}-\\d{2}")
private val SHORT_MM_YY = Regex("^\\d{2}/\\d{2}$")

/** Rotulo curto de mes para eixos e legendas: 'AAAA-MM' ou 'MM/AA' -> 'out/25'. */
fun shortMonthLabel(key: String?): String {
    val text = key ?: ""
    val year: Double
    val month: Double?
    if (SHORT_ISO.containsMatchIn(text)) {
        val parts = text.split("-")
        year = Js.number(parts[0])!!
        month = Js.number(parts.getOrNull(1))
    } else if (SHORT_MM_YY.matches(text)) {
        val parts = text.split("/")
        month = Js.number(parts[0])
        year = 2000 + Js.number(parts[1])!!
    } else {
        return text
    }
    val date = if (month == null) null else Js.makeDate(year, month - 1, 1.0)
    // O JS tira o ano do numero digitado, nao da data (um mes 13 nao muda o ano do rotulo).
    val name = if (date == null) INVALID_DATE else MONTHS_SHORT[date.monthValue - 1]
    return "$name/${Js.numberToString(year).drop(2)}"
}

/** 'AAAA-MM' deslocado `offset` meses: shiftMonth("2026-12", 1) = "2027-01". */
fun shiftMonth(key: String?, offset: Int): String {
    val parts = (key ?: "null").split("-")
    val year = Js.number(parts.getOrNull(0))
    val month = Js.number(parts.getOrNull(1))
    if (year == null || month == null) return "0NaN-NaN"
    val index = year * 12 + (month - 1) + offset
    val yearText = Js.numberToString(Math.floor(index / 12))
    val monthText = Js.numberToString((index % 12) + 1)
    return "${yearText.padStart(4, '0')}-${monthText.padStart(2, '0')}"
}

/** E-mail mascarado para a tela: "fulano@gmail.com" -> "fu•••@g•••.com". */
fun maskEmail(email: String?): String {
    val text = Js.trim(email ?: "")
    val at = text.lastIndexOf('@')
    if (at < 1) return if (text.isNotEmpty()) "${text.take(2)}•••" else ""
    val local = text.substring(0, at)
    val domain = text.substring(at + 1)
    val dot = domain.indexOf('.')
    val name = if (dot > 0) domain.substring(0, dot) else domain
    val suffix = if (dot > 0) domain.substring(dot) else ""
    val keep = if (local.length > 2) 2 else 1
    return "${local.take(keep)}•••@${name.take(1)}•••$suffix"
}

private fun currency(value: BigDecimal, minFraction: Int, maxFraction: Int): String =
    signPrefix(value) + "R$" + NBSP + grouped(value.abs(), minFraction, maxFraction)

// O sinal sai do valor antes do arredondamento: o Intl escreve "−R$ 0,00" para -0,004.
private fun signPrefix(value: BigDecimal): String = if (value.signum() < 0) MINUS else ""

// Valor nao negativo -> "1.234.567,89": HALF_UP em maxFraction casas, zeros finais cortados ate
// minFraction, milhar com ponto a partir de quatro digitos (o pt-BR do Intl agrupa "1.022").
private fun grouped(value: BigDecimal, minFraction: Int, maxFraction: Int): String {
    var rounded = value.setScale(maxFraction, RoundingMode.HALF_UP)
    if (rounded.scale() > minFraction) {
        val stripped = rounded.stripTrailingZeros()
        // Os zeros cortados sao exatos: setScale de volta a minFraction nao arredonda nada.
        rounded = if (stripped.scale() < minFraction) rounded.setScale(minFraction) else stripped
    }
    val plain = rounded.toPlainString()
    val point = plain.indexOf('.')
    val integer = if (point < 0) plain else plain.substring(0, point)
    val fraction = if (point < 0) "" else plain.substring(point + 1)
    val groupedInteger = StringBuilder()
    integer.forEachIndexed { index, char ->
        if (index > 0 && (integer.length - index) % 3 == 0) groupedInteger.append('.')
        groupedInteger.append(char)
    }
    return if (fraction.isEmpty()) groupedInteger.toString() else "$groupedInteger,$fraction"
}

private fun pad2(value: Int): String = value.toString().padStart(2, '0')

/**
 * As conversoes do JS que format.js usa sem dizer: Number(texto), String(numero), o trim e o
 * construtor new Date(y, m, d). Double aqui e so o Number do JS lendo pedacos de data e de chave
 * de mes, nunca dinheiro.
 */
internal object Js {
    // \s e o trim() do JS: estes, e nao os de Char.isWhitespace do Kotlin.
    private const val WHITESPACE =
        "\t\n\u000B\u000C\r            " +
            "      　﻿"

    val whitespaceClass: String = "[" + WHITESPACE.map { "\\u%04X".format(it.code) }.joinToString("") + "]"

    private val DECIMAL = Regex("^[+-]?(\\d+\\.?\\d*|\\.\\d+)([eE][+-]?\\d+)?$")
    private val RADIX = Regex("^0([xXoObB])([0-9a-fA-F]+)$")

    // Os limites do Date do JS: 100 milhoes de dias para cada lado de 1970-01-01.
    private const val MAX_EPOCH_DAYS = 100_000_000L

    fun trim(text: String): String = text.trim { it in WHITESPACE }

    /** Number(texto): null quando o JS daria NaN (inclusive para um pedaco ausente, undefined). */
    fun number(text: String?): Double? {
        if (text == null) return null
        val body = trim(text)
        if (body.isEmpty()) return 0.0
        when (body) {
            "Infinity", "+Infinity" -> return Double.POSITIVE_INFINITY
            "-Infinity" -> return Double.NEGATIVE_INFINITY
        }
        if (DECIMAL.matches(body)) return body.toDouble()
        val radix = RADIX.matchEntire(body) ?: return null
        val base = when (radix.groupValues[1].lowercaseChar()) { 'x' -> 16; 'o' -> 8; else -> 2 }
        return runCatching { java.math.BigInteger(radix.groupValues[2], base).toDouble() }.getOrNull()
    }

    fun truthy(value: Double?): Boolean = value != null && value != 0.0

    /**
     * new Date(year, monthIndex, day) no fuso local: ToIntegerOrInfinity em cada parte, ano de 0
     * a 99 -> 19xx, mes e dia rolando. null quando o JS daria uma data invalida.
     */
    fun makeDate(year: Double, monthIndex: Double, day: Double): LocalDate? {
        if (!year.isFinite() || !monthIndex.isFinite() || !day.isFinite()) return null
        var y = truncate(year)
        if (y in 0.0..99.0) y += 1900
        val m = truncate(monthIndex)
        val d = truncate(day)
        val limit = 1e12
        if (Math.abs(y) > limit || Math.abs(m) > limit || Math.abs(d) > limit) return null
        return try {
            val years = y.toLong() + Math.floorDiv(m.toLong(), 12L)
            val months = Math.floorMod(m.toLong(), 12L)
            val epochDay = daysFromCivil(years, months + 1) + d.toLong() - 1
            if (Math.abs(epochDay) > MAX_EPOCH_DAYS) null else LocalDate.ofEpochDay(epochDay)
        } catch (e: ArithmeticException) {
            null
        } catch (e: java.time.DateTimeException) {
            null
        }
    }

    // Dias de 1970-01-01 ate o dia 1 de (ano, mes) — o calendario gregoriano proleptico do JS.
    private fun daysFromCivil(year: Long, month: Long): Long {
        val y = if (month <= 2) year - 1 else year
        val era = Math.floorDiv(y, 400L)
        val yoe = y - era * 400
        val mp = (month + 9) % 12
        val doy = (153 * mp + 2) / 5
        val doe = yoe * 365 + yoe / 4 - yoe / 100 + doy
        return era * 146097 + doe - 719468
    }

    private fun truncate(value: Double): Double = if (value < 0) Math.ceil(value) else Math.floor(value)

    /** String(numero) do JS: "2026", "0.5", "NaN", "1e+21". */
    fun numberToString(value: Double): String {
        if (value.isNaN()) return "NaN"
        if (value.isInfinite()) return if (value > 0) "Infinity" else "-Infinity"
        if (value == 0.0) return "0"
        val abs = Math.abs(value)
        // Double.toString da JVM (17+) da o menor numero de digitos que volta ao mesmo double,
        // como o JS; falta so o jeito de escrever.
        val shortest = BigDecimal(value.toString())
        if (abs >= 1e-6 && abs < 1e21) return shortest.stripTrailingZeros().toPlainString()
        val digits = shortest.unscaledValue().abs().toString().trimEnd('0').ifEmpty { "0" }
        val exponent = shortest.precision() - shortest.scale() - 1
        val mantissa = if (digits.length == 1) digits else "${digits[0]}.${digits.substring(1)}"
        val sign = if (value < 0) "-" else ""
        return "$sign${mantissa}e${if (exponent >= 0) "+" else "-"}${Math.abs(exponent)}"
    }
}
