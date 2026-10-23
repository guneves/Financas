package br.financas.app.core

import org.junit.Assert.assertEquals
import org.junit.Test
import java.math.BigDecimal

/**
 * Os casos de parseMoneyInput / moneyInputValue em frontend/src/lib/monthlyPlan.test.js, na mesma
 * ordem e com as mesmas entradas. Mudou um lado, muda o outro.
 */
class MoneyInputTest {
    private fun amount(text: String) = MoneyInput.Amount(BigDecimal(text))

    // monthlyPlan.test.js: "parseMoneyInput aceita virgula do teclado do celular e ponto do desktop"
    @Test
    fun parseMoneyInputAcceptsPhoneCommaAndDesktopDot() {
        assertEquals(amount("1234.56"), parseMoneyInput("1.234,56"))
        assertEquals(amount("1234.5"), parseMoneyInput("1234,5"))
        assertEquals(amount("1234.56"), parseMoneyInput("1234.56"))
        assertEquals(amount("3000"), parseMoneyInput("R$ 3.000"))
        assertEquals(amount("1234567"), parseMoneyInput("1.234.567"))
        assertEquals(amount("1.5"), parseMoneyInput("1.5"))
        assertEquals(MoneyInput.Empty, parseMoneyInput("  "))
        assertEquals(MoneyInput.Invalid, parseMoneyInput("12a"))
    }

    // monthlyPlan.test.js: "parseMoneyInput: o ultimo separador e o decimal, e milhar so em grupos de tres"
    @Test
    fun parseMoneyInputLastSeparatorIsDecimalAndThousandsOnlyInGroupsOfThree() {
        assertEquals(amount("1234.56"), parseMoneyInput("1,234.56"))
        assertEquals(amount("1234567.8"), parseMoneyInput("1,234,567.8"))
        assertEquals(amount("1234567"), parseMoneyInput("1,234,567"))
        assertEquals(amount("0.5"), parseMoneyInput("0.500"))
        assertEquals(amount("0.5"), parseMoneyInput("0,50"))
        assertEquals(amount("1500"), parseMoneyInput("1.500"))
        assertEquals(amount("1500"), parseMoneyInput("1.500,00"))
        assertEquals(amount("42.9"), parseMoneyInput("42,9"))
        assertEquals(amount("5"), parseMoneyInput("5,"))
        assertEquals(amount("0.5"), parseMoneyInput(",5"))
        assertEquals(MoneyInput.Invalid, parseMoneyInput("1.2.3"))
        assertEquals(MoneyInput.Invalid, parseMoneyInput("12.34,5.6"))
        assertEquals(MoneyInput.Invalid, parseMoneyInput("1,23.4,5"))
        assertEquals(MoneyInput.Invalid, parseMoneyInput("12,34.56"))
        assertEquals(MoneyInput.Invalid, parseMoneyInput(","))
        assertEquals(MoneyInput.Invalid, parseMoneyInput("-5"))
    }

    // monthlyPlan.test.js: "moneyInputValue devolve o valor com virgula"
    @Test
    fun moneyInputValueReturnsTheValueWithComma() {
        assertEquals("1500,5", moneyInputValue(BigDecimal("1500.5")))
        assertEquals("", moneyInputValue(null as BigDecimal?))
    }

    // Sem caso no JS: saidas tiradas do monthlyPlan.js no node 24 (espaco inquebravel e fino, sinal
    // "+", zero, texto com zeros finais).
    @Test
    fun nativeOnlyEdgesMatchNode() {
        assertEquals(amount("1234.56"), parseMoneyInput("R$ 1.234,56"))
        assertEquals(amount("1234.56"), parseMoneyInput("1 234,56"))
        assertEquals(amount("1234"), parseMoneyInput(" 1234"))
        assertEquals(MoneyInput.Invalid, parseMoneyInput("+5"))
        assertEquals(MoneyInput.Empty, parseMoneyInput(null))
        assertEquals("0", moneyInputValue(BigDecimal.ZERO))
        assertEquals("1500", moneyInputValue(BigDecimal("1500.00")))
        assertEquals("0,1", moneyInputValue(BigDecimal("0.1")))
        assertEquals("1500,50", moneyInputValue("1500.50"))
        assertEquals("", moneyInputValue(""))
    }
}
