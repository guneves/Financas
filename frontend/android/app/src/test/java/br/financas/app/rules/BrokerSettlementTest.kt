package br.financas.app.rules

import br.financas.app.data.ApiJson
import br.financas.app.data.SettlementDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

/** A Conta investimento (ContaInvestimento.jsx): a dica de "Saldo hoje", a cor do em transito e o rotulo da data. */
class BrokerSettlementTest {

    @Test
    fun hintWithoutPluggyIsTheAccountName() {
        assertEquals(BrokerSettlement.Hint.Account("BTG"), BrokerSettlement.hint(false, null, null, "BTG"))
        assertEquals(BrokerSettlement.Hint.Account(""), BrokerSettlement.hint(false, null, null, null))
    }

    @Test
    fun hintMatchesBelowOneCent() {
        assertEquals(BrokerSettlement.Hint.Matches, BrokerSettlement.hint(true, BigDecimal("100"), BigDecimal("0.004"), "BTG"))
        assertEquals(BrokerSettlement.Hint.Matches, BrokerSettlement.hint(true, BigDecimal("100"), BigDecimal("-0.009"), "BTG"))
        // Sem diferenca calculada (o app sem saldo naquele dia) vale 0, como na web.
        assertEquals(BrokerSettlement.Hint.Matches, BrokerSettlement.hint(true, BigDecimal("100"), null, "BTG"))
    }

    @Test
    fun hintShowsTheBrokerBalanceFromOneCent() {
        assertEquals(
            BrokerSettlement.Hint.Broker(BigDecimal("120.00"), BigDecimal("-0.01")),
            BrokerSettlement.hint(true, BigDecimal("120.00"), BigDecimal("-0.01"), "BTG"),
        )
        assertEquals(
            BrokerSettlement.Hint.Broker(BigDecimal("120.00"), BigDecimal("15.50")),
            BrokerSettlement.hint(true, BigDecimal("120.00"), BigDecimal("15.50"), "BTG"),
        )
    }

    @Test
    fun transitToneFollowsTheSignAndPrivacy() {
        assertEquals(BrokerSettlement.Tone.GAIN, BrokerSettlement.transitTone(BigDecimal("10"), false))
        assertEquals(BrokerSettlement.Tone.LOSS, BrokerSettlement.transitTone(BigDecimal("-10"), false))
        assertEquals(BrokerSettlement.Tone.NEUTRAL, BrokerSettlement.transitTone(BigDecimal("0.00"), false))
        assertEquals(BrokerSettlement.Tone.NEUTRAL, BrokerSettlement.transitTone(null, false))
        assertEquals(BrokerSettlement.Tone.NEUTRAL, BrokerSettlement.transitTone(BigDecimal("-10"), true))
    }

    @Test
    fun onlyAProceedIsAPayment() {
        assertTrue(BrokerSettlement.isPayment("proceed"))
        assertFalse(BrokerSettlement.isPayment("operation"))
        assertFalse(BrokerSettlement.isPayment("other"))
        assertFalse(BrokerSettlement.isPayment(null))
    }

    @Test
    fun decodesTheSettlementResponse() {
        val body = """
            {"account_id": "a1", "account_name": "BTG", "today": "2026-10-28", "settled": 1000.5,
             "in_transit": [
               {"id": "t1", "date": "2026-10-29", "description": "Compra PETR4", "amount": -350.25,
                "kind": "operation", "investment_id": "inv1"},
               {"id": "proceed:p1", "date": "2026-11-05", "description": "Dividendos ITSA4", "amount": 12.3,
                "kind": "proceed", "investment_id": null}
             ],
             "in_transit_total": -337.95, "expected": 662.55,
             "pluggy": {"balance": 1000.5, "balance_at": "2026-10-28T09:00:00Z", "as_of": "2026-10-28",
                        "app_balance": 1000.5, "difference": 0.0}}
        """.trimIndent()
        val view = ApiJson.decodeFromString(SettlementDto.serializer(), body)
        assertEquals("BTG", view.accountName)
        assertEquals(0, BigDecimal("1000.5").compareTo(view.settled))
        assertEquals(2, view.inTransit.size)
        assertEquals("inv1", view.inTransit[0].investmentId)
        assertNull(view.inTransit[1].investmentId)
        assertEquals(0, BigDecimal("-337.95").compareTo(view.inTransitTotal))
        assertEquals(0, BigDecimal.ZERO.compareTo(view.pluggy?.difference))

        val bare = ApiJson.decodeFromString(SettlementDto.serializer(), """{"account_id": "a1", "settled": 0, "in_transit": [], "pluggy": null}""")
        assertNull(bare.pluggy)
        assertTrue(bare.inTransit.isEmpty())
    }
}
