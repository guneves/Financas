// Porte: mudou um, muda o outro, com um teste de cada lado.
// Os casos de frontend/src/lib/investmentPrefill.test.js e os de heldReasonLabel/heldLaunch de
// openFinance.test.js; o nome do teste do node vai no comentario de cada um.
package br.financas.app.rules

import br.financas.app.rules.InvestmentPrefill.OP_KEY_METADATA
import br.financas.app.rules.InvestmentPrefill.Prefill
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

class InvestmentPrefillTest {
    private fun metadata(text: String): JsonObject = Json.parseToJsonElement(text).jsonObject
    private val today = "2026-11-04"

    // node: 'an equity buy that waits opens the buy form with its cash in the Corretora'
    @Test
    fun anEquityBuyThatWaitsOpensTheBuyFormWithItsCashInTheCorretora() {
        val form = InvestmentPrefill.launchForm(
            Prefill("operation", "STOCKS", false, "PETR4", BigDecimal("10"), BigDecimal("30"), "corretora",
                metadata("""{"purchase_date":"2026-10-20","other_costs":2.5,"$OP_KEY_METADATA":"pluggy-inv:1"}""")),
            today,
        )!!
        assertEquals("BUY", form.mode)
        assertEquals("STOCKS", form.assetType)
        assertEquals(listOf("PETR4", "10", "30", "2.5", "2026-10-20"), listOf(form.tickerOrName, form.quantity, form.price, form.otherCosts, form.date))
        assertEquals(PortfolioAccount.CashLink(true, "corretora", false), form.cashLink)
        assertEquals("pluggy-inv:1", form.opKey)
        val body = Operations.buyPayload(form, null, existing = false)
        assertEquals("pluggy-inv:1", (body["metadata"] as Map<*, *>)[OP_KEY_METADATA])
    }

    // node: 'a sale opens the sell form at the sale price'
    @Test
    fun aSaleOpensTheSellFormAtTheSalePrice() {
        val form = InvestmentPrefill.launchForm(
            Prefill("operation", "STOCKS", false, "BOVA11", BigDecimal("-5"), BigDecimal("130"), "corretora",
                metadata("""{"sale_date":"2026-10-22","sale_price":131,"other_costs":0}""")),
            today,
        )!!
        assertEquals(listOf("SELL", "5", "131", "2026-10-22", ""), listOf(form.mode, form.quantity, form.price, form.date, form.otherCosts))
    }

    // node: 'a fixed income buy keeps what Pluggy knew and never takes the Corretora'
    @Test
    fun aFixedIncomeBuyKeepsWhatPluggyKnewAndNeverTakesTheCorretora() {
        val form = InvestmentPrefill.launchForm(
            Prefill("operation", "FIXED_INCOME", false, "CDB BANCO X", BigDecimal.ONE, BigDecimal("1500"), null,
                metadata("""{"fixed_income_type":"LCI","purchase_date":"2026-10-20","other_costs":0,"$OP_KEY_METADATA":"k"}""")),
            today,
        )!!
        assertEquals(listOf("FIXED_INCOME", "1", "1500"), listOf(form.assetType, form.quantity, form.price))
        assertEquals("LCI", form.fixedIncome.fixedIncomeType)
        assertEquals("", form.fixedIncome.rate)
        assertFalse(form.cashLink.enabled)
    }

    // node: 'a Tesouro buy opens as Tesouro with its titles'
    @Test
    fun aTesouroBuyOpensAsTesouroWithItsTitles() {
        val form = InvestmentPrefill.launchForm(
            Prefill("operation", "FIXED_INCOME", true, "Tesouro IPCA+ 2045", BigDecimal.ONE, BigDecimal("850"), null,
                metadata("""{"fixed_income_type":"TESOURO","treasury_units":0.85,"purchase_date":"2026-10-20"}""")),
            today,
        )!!
        assertEquals("TESOURO", form.assetType)
        assertEquals("0.85", form.treasuryUnits)
    }

    // node: 'only operations open the form'
    @Test
    fun onlyOperationsOpenTheForm() {
        assertNull(InvestmentPrefill.launchForm(null, today))
        assertNull(InvestmentPrefill.launchForm(Prefill("proceed"), today))
        assertEquals(emptyMap<String, Any?>(), InvestmentPrefill.opKeyMetadata(""))
        assertEquals(mapOf(OP_KEY_METADATA to "k"), InvestmentPrefill.opKeyMetadata("k"))
        assertTrue(InvestmentPrefill.launchable("k", Prefill("operation")))
        assertFalse(InvestmentPrefill.launchable("", Prefill("operation")))
        assertFalse(InvestmentPrefill.launchable("k", Prefill("redemption")))
    }

    // node: 'fixed income waits for the field Pluggy did not give exactly' (openFinance.test.js)
    @Test
    fun fixedIncomeWaitsForTheFieldPluggyDidNotGiveExactly() {
        assertEquals("falta o indexador", InvestmentPrefill.heldReasonLabel("missing:rateType"))
        assertEquals("o indexador sem um significado só", InvestmentPrefill.heldReasonLabel("unmapped:rateType"))
        assertEquals("falta a compra do título no app", InvestmentPrefill.heldReasonLabel("missing:buy"))
        assertEquals("falta novo", InvestmentPrefill.heldReasonLabel("missing:novo"))
        assertEquals("fundo, custódia ou outro tipo: lance você", InvestmentPrefill.heldReasonLabel("type"))
        assertEquals("antes de um evento corporativo do ativo", InvestmentPrefill.heldReasonLabel("corporate_action: x"))
        assertEquals("Venda maior.", InvestmentPrefill.heldReasonLabel("refused: Venda maior."))
    }
}
