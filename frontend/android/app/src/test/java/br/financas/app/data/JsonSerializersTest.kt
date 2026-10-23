package br.financas.app.data

import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import kotlinx.serialization.builtins.ListSerializer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

class JsonSerializersTest {

    @Serializable
    private data class Holder(val value: Money? = null, val flag: Flag = false)

    private fun money(json: String): BigDecimal? = ApiJson.decodeFromString(Holder.serializer(), """{"value": $json}""").value

    @Test
    fun readsAmountsFromTheirTextNeverThroughDouble() {
        assertEquals(BigDecimal("1234.56"), money("1234.56"))
        assertEquals(BigDecimal("1234.56"), money("\"1234.56\""))
        // 0.1 como Double seria 0.1000000000000000055511151231257827...
        assertEquals(BigDecimal("0.1"), money("0.1"))
        assertEquals(0, BigDecimal("0.1").compareTo(money("0.1")))
        assertEquals(BigDecimal("-35.9"), money("-35.9"))
        assertEquals(BigDecimal("0"), money("0"))
    }

    @Test
    fun readsLargeValuesExactly() {
        assertEquals(BigDecimal("999999999999.99"), money("999999999999.99"))
        assertEquals(BigDecimal("123456789012345678901234567890.12"), money("123456789012345678901234567890.12"))
        // O json do Python escreve floats grandes em notacao cientifica.
        assertEquals(0, BigDecimal("10000000000000000").compareTo(money("1e+16")))
        assertEquals(0, BigDecimal("1E+308").compareTo(money("1e308")))
    }

    @Test
    fun nullAndMissingStayNull() {
        assertNull(money("null"))
        assertNull(ApiJson.decodeFromString(Holder.serializer(), "{}").value)
    }

    @Test(expected = SerializationException::class)
    fun refusesTextThatIsNotANumber() {
        money("\"abc\"")
    }

    @Test(expected = SerializationException::class)
    fun refusesAnEmptyString() {
        money("\"\"")
    }

    @Test
    fun writesThePlainNumberUnquoted() {
        val text = ApiJson.encodeToString(Holder.serializer(), Holder(BigDecimal("1E+3"), true))
        assertEquals("""{"value":1000,"flag":true}""", text)
        val decimal = ApiJson.encodeToString(Holder.serializer(), Holder(BigDecimal("1234.50")))
        assertTrue(decimal, decimal.contains("\"value\":1234.50"))
    }

    @Test
    fun flagsAcceptBooleansAndZeroOne() {
        fun flag(json: String) = ApiJson.decodeFromString(Holder.serializer(), """{"flag": $json}""").flag
        assertTrue(flag("true"))
        assertTrue(flag("1"))
        assertFalse(flag("false"))
        assertFalse(flag("0"))
        // null num campo com padrao: o padrao (coerceInputValues).
        assertFalse(flag("null"))
    }

    @Test
    fun aListOfAmounts() {
        val values = ApiJson.decodeFromString(ListSerializer(Holder.serializer()), """[{"value": 1.10}, {"value": 2}]""")
        assertEquals(listOf(BigDecimal("1.10"), BigDecimal("2")), values.map { it.value })
    }
}
