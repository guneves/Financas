package br.financas.app.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.math.BigDecimal
import java.time.LocalDate

/**
 * Os casos de frontend/src/lib/format.test.js, na mesma ordem e com as mesmas entradas; depois,
 * os casos que o JS nao testa, com as saidas tiradas do format.js no node 24 (Intl pt-BR).
 * Mudou um lado, muda o outro.
 */
class FormatTest {
    private fun bd(text: String) = BigDecimal(text)

    // format.test.js: "maskEmail mostra so algumas letras do e-mail"
    @Test
    fun maskEmailShowsOnlySomeLetters() {
        assertEquals("fu•••@g•••.com", maskEmail("fulano@gmail.com"))
        assertEquals("a•••@e•••.com.br", maskEmail("ab@empresa.com.br"))
        assertEquals("x•••@h•••", maskEmail("x@host"))
    }

    // format.test.js: "maskEmail nunca devolve o e-mail inteiro, nem quebra sem um"
    @Test
    fun maskEmailNeverReturnsTheWholeEmail() {
        assertEquals("", maskEmail(""))
        assertEquals("", maskEmail(null))
        assertEquals("se•••", maskEmail("semarroba"))
    }

    // format.test.js: "formatQuantity usa os separadores do pt-BR"
    @Test
    fun formatQuantityUsesPtBrSeparators() {
        assertEquals("1.022", formatQuantity(bd("1022")))
        assertEquals("62,7", formatQuantity(bd("62.7")))
        // 1 / 3 no JS e o double 0.3333333333333333.
        assertEquals("0,33333333", formatQuantity(bd("0.3333333333333333")))
        assertEquals("0,00012345", formatQuantity(bd("0.00012345")))
        assertEquals("−5", formatQuantity(bd("-5")))
        assertEquals("0", formatQuantity(null))
    }

    // ---- Sem caso no format.test.js: saidas do node 24 ----

    @Test
    fun nativeOnlyFormatCurrency() {
        assertEquals("R$ 0,00", formatCurrency(BigDecimal.ZERO))
        assertEquals("R$ 1.234,56", formatCurrency(bd("1234.56")))
        assertEquals("−R$ 1.234,56", formatCurrency(bd("-1234.56")))
        assertEquals("R$ 1.234.567,89", formatCurrency(bd("1234567.891")))
        assertEquals("R$ 0,01", formatCurrency(bd("0.005")))
        assertEquals("−R$ 0,00", formatCurrency(bd("-0.004")))
        assertEquals("−R$ 0,01", formatCurrency(bd("-0.005")))
        assertEquals("R$ 2,68", formatCurrency(bd("2.675")))
        assertEquals("R$ 1.000,00", formatCurrency(bd("1000")))
        assertEquals("R$ 1.000,00", formatCurrency(bd("999.995")))
        assertEquals("R$ 0,00", formatCurrency(null))
        assertEquals("R$ 12,50", formatCurrency(bd("12.5")))
        assertEquals("R$ 1.000.000.000.000.000,00", formatCurrency(bd("1000000000000000")))
    }

    @Test
    fun nativeOnlyFormatSignedCurrency() {
        assertEquals("+R$ 8.500,00", formatSignedCurrency(bd("8500")))
        assertEquals("−R$ 1.048,22", formatSignedCurrency(bd("-1048.22")))
        assertEquals("−R$ 100,00", formatSignedCurrency(bd("100"), -1))
        assertEquals("+R$ 100,00", formatSignedCurrency(bd("100"), 1))
        assertEquals("R$ 100,00", formatSignedCurrency(bd("100"), 0))
        assertEquals("R$ 0,00", formatSignedCurrency(BigDecimal.ZERO, 1))
        assertEquals("−R$ 0,00", formatSignedCurrency(bd("-0.001")))
        assertEquals("+R$ 0,00", formatSignedCurrency(bd("0.004"), 1))
    }

    @Test
    fun nativeOnlyFormatUnitCurrency() {
        assertEquals("R$ 0,000001", formatUnitCurrency(bd("0.000001")))
        assertEquals("R$ 12,50", formatUnitCurrency(bd("12.5")))
        assertEquals("R$ 1.234,123457", formatUnitCurrency(bd("1234.1234567")))
        assertEquals("−R$ 3,00", formatUnitCurrency(bd("-3")))
        assertEquals("R$ 0,00", formatUnitCurrency(bd("0.0000004")))
        assertEquals("−R$ 0,00", formatUnitCurrency(bd("-0.0000004")))
    }

    @Test
    fun nativeOnlyFormatQuantity() {
        assertEquals("1.234.567,12345679", formatQuantity(bd("1234567.123456789")))
        assertEquals("−0", formatQuantity(bd("-0.000000001")))
        assertEquals("0,5", formatQuantity(bd("0.5")))
    }

    @Test
    fun nativeOnlyFormatPercent() {
        assertEquals("12,50%", formatPercent(bd("12.5")))
        assertEquals("+12,50%", formatPercent(bd("12.5"), 2, signed = true))
        assertEquals("−3,5%", formatPercent(bd("-3.456"), 1, signed = true))
        assertEquals("+0,00%", formatPercent(bd("0.001"), 2, signed = true))
        assertEquals("−0,00%", formatPercent(bd("-0.001"), 2))
        assertEquals("1.235%", formatPercent(bd("1234.5"), 0))
        assertEquals("0,00%", formatPercent(BigDecimal.ZERO, 2, signed = true))
        assertEquals("3%", formatPercent(bd("2.5"), 0))
    }

    @Test
    fun nativeOnlyDates() {
        assertEquals("01/09/2026", formatDateBR("2026-09-01"))
        assertEquals("01/09/2026", formatDateBR("2026-9-1"))
        assertEquals("02/03/2026", formatDateBR("2026-02-30"))
        assertEquals("01/01/2027", formatDateBR("2026-13-01"))
        assertEquals("05/01/1926", formatDateBR("26-01-05"))
        assertEquals("-", formatDateBR("2026-01"))
        assertEquals("-", formatDateBR(""))
        assertEquals("-", formatDateBR("abc"))
        assertEquals("05/01/2026", formatDateBR("2026-01-05T10:00:00"))
        assertEquals("05/01/999", formatDateBR("0999-01-05"))
        assertEquals("-", formatDateBR("2026-00-10"))
        assertEquals("-", formatDateBR(" 2026-01-05"))
        assertEquals("", formatDateBR(null, ""))
        assertEquals(LocalDate.of(2026, 9, 1), parseLocalDate("2026-09-01"))
        assertNull(parseLocalDate(null))
        assertEquals("2026-01-05", getLocalDateString(LocalDate.of(2026, 1, 5)))
        assertEquals("2026-01", monthKey(LocalDate.of(2026, 1, 5)))
        assertEquals("999-01-05", getLocalDateString(LocalDate.of(999, 1, 5)))
        assertEquals("999-01", monthKey(LocalDate.of(999, 1, 5)))
    }

    @Test
    fun nativeOnlyMonthLabels() {
        assertEquals("outubro de 2026", monthLabel("2026-10"))
        assertEquals("janeiro de 2026", monthLabel("2026-01"))
        assertEquals("março de 2026", monthLabel("2026-03"))
        assertEquals("janeiro de 2027", monthLabel("2026-13"))
        assertEquals("maio de 1926", monthLabel("26-05"))
        assertEquals("2026", monthLabel("2026"))
        assertEquals("", monthLabel(""))
        assertEquals("", monthLabel(null))
        assertEquals("abc", monthLabel("abc"))
        assertEquals("2026-00", monthLabel("2026-00"))
        assertEquals("out/26", shortMonthLabel("2026-10"))
        assertEquals("mai/25", shortMonthLabel("2025-05"))
        assertEquals("out/25", shortMonthLabel("10/25"))
        assertEquals("out/26", shortMonthLabel("2026-10-05"))
        assertEquals("jan/26", shortMonthLabel("2026-13"))
        assertEquals("abc", shortMonthLabel("abc"))
        assertEquals("", shortMonthLabel(""))
        assertEquals("dez/26", shortMonthLabel("2026-00"))
        assertEquals("2026-1", shortMonthLabel("2026-1"))
    }

    @Test
    fun nativeOnlyShiftMonth() {
        assertEquals("2026-11", shiftMonth("2026-10", 1))
        assertEquals("2027-01", shiftMonth("2026-12", 1))
        assertEquals("2025-12", shiftMonth("2026-01", -1))
        assertEquals("2023-12", shiftMonth("2026-01", -25))
        assertEquals("00-1-00", shiftMonth("0000-01", -1))
        assertEquals("00-2-00", shiftMonth("0000-01", -13))
        assertEquals("0NaN-NaN", shiftMonth("2026", 0))
        assertEquals("0NaN-NaN", shiftMonth("abc", 1))
        assertEquals("2026-12", shiftMonth("2026-10-05", 2))
        assertEquals("10000-01", shiftMonth("9999-12", 1))
    }

    @Test
    fun nativeOnlyMaskEmail() {
        assertEquals("a•••@x•••.com", maskEmail("  ab@x.com "))
        assertEquals("@x•••", maskEmail("@x.com"))
        assertEquals("a•••@b•••", maskEmail("a@b"))
        assertEquals("a•••@.•••", maskEmail("a@.com"))
        assertEquals("x•••", maskEmail("x"))
        assertEquals("ab•••@e•••.com", maskEmail("abc@d@e.com"))
    }
}
