// As regras inline de Operacoes.jsx, helpers.js, InvestmentLaunchModal.jsx e
// CorporateActionsPanel.jsx (sem teste do lado web): os casos sao o comportamento da web hoje.
package br.financas.app.rules

import br.financas.app.rules.Operations.LaunchForm
import br.financas.app.rules.Operations.Movement
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal
import java.time.ZoneId

class OperationsTest {
    private fun money(text: String) = BigDecimal(text)
    private fun meta(text: String) = Json.parseToJsonElement(text) as JsonObject
    private val zone = ZoneId.of("America/Sao_Paulo")

    private fun movement(
        quantity: String,
        average: String = "10",
        current: String = "12",
        assetClass: String = "STOCKS",
        metadata: String = "{}",
        realized: String? = null,
    ) = Movement(
        id = "m1",
        assetClass = assetClass,
        quantity = money(quantity),
        averagePrice = money(average),
        currentPrice = money(current),
        createdAt = "2026-10-22T17:03:00Z",
        metadata = meta(metadata),
        realizedProfit = realized?.let(::money),
        realizedNetProceeds = realized?.let { money("99") },
    )

    @Test
    fun numbersTypedWithCommaOrDot() {
        assertEquals(money("1234.5"), Operations.parseNumberInput("1.234,5"))
        assertEquals(money("1234.5"), Operations.parseNumberInput(" 1234.5 "))
        assertEquals(BigDecimal.ZERO, Operations.parseNumberInput(""))
        assertNull(Operations.parseNumberInput("abc"))
        assertEquals(BigDecimal.ZERO, Operations.parseAmount("abc"))
    }

    @Test
    fun unitPriceTotalAndFeesOfEachKind() {
        val buy = movement("10", metadata = """{"purchase_date":"2026-10-01","other_costs":2.5}""")
        assertEquals(money("10"), Operations.unitPrice(buy))
        assertEquals(0, money("100").compareTo(Operations.totalValue(buy)))
        assertEquals(money("2.5"), Operations.fees(buy))
        val sale = movement("-4", metadata = """{"sale_price":15}""")
        assertEquals(money("15"), Operations.unitPrice(sale))
        assertEquals(0, money("60").compareTo(Operations.totalValue(sale)))
        val redemption = movement("-1", current = "500", assetClass = "FIXED_INCOME", metadata = """{"is_redemption":true}""")
        assertEquals(money("500"), Operations.unitPrice(redemption))
        // realized_fee_amount ?? fee_amount ?? metadata.other_costs
        assertEquals(money("1"), Operations.fees(buy.copy(feeAmount = money("1"))))
        assertEquals(money("3"), Operations.fees(buy.copy(feeAmount = money("1"), realizedFeeAmount = money("3"))))
    }

    @Test
    fun describeReadsKindDateAndStatement() {
        val buy = Operations.describe(movement("10", metadata = """{"purchase_date":"2026-10-01","cash_account_id":"c1"}"""), zone)
        assertEquals("Compra de 10", buy.kindLabel)
        assertEquals("01/10/2026", buy.dateLabel)
        assertTrue(buy.inStatement)
        assertFalse(buy.isSale)
        // Sem data digitada: o created_at com a hora local.
        val noDate = Operations.describe(movement("0.333333333"), zone)
        assertEquals("22/10/2026 às 14:03", noDate.dateLabel)
        assertEquals("Compra de 0,333333", noDate.kindLabel)
        val sale = Operations.describe(movement("-4", metadata = """{"sale_price":15,"other_costs":1}"""), zone)
        assertEquals("Venda de 4", sale.kindLabel)
        assertEquals(0, money("59").compareTo(sale.netProceeds))
        val redemption = Operations.describe(movement("-1", current = "500", assetClass = "FIXED_INCOME", metadata = """{"is_redemption":true}"""), zone)
        assertEquals("Resgate de R\$ 500,00", redemption.kindLabel)
        assertEquals("Aporte de 1", Operations.describe(movement("1", assetClass = "FIXED_INCOME"), zone).kindLabel)
        val bonus = Operations.describe(movement("2", metadata = """{"corporate_action_id":"ca1","corporate_adjustments":[{"x":1}]}"""), zone)
        assertTrue(bonus.isBonus)
        assertTrue(bonus.adjusted)
        assertEquals("Bonificação de 2", bonus.kindLabel)
        // Com resultado realizado, o liquido e o do servidor.
        assertEquals(money("99"), Operations.describe(movement("-4", realized = "5"), zone).netProceeds)
    }

    @Test
    fun realizedDetailNamesTheMethod() {
        val average = movement("-1", realized = "1").copy(realizedProfitabilityPercent = money("-11.9"), realizedMetadata = meta("""{"cost_method":"AVERAGE"}"""))
        assertEquals("−11,90% · custo médio", Operations.realizedDetail(average))
        val fifo = average.copy(realizedProfitabilityPercent = money("3"), realizedMetadata = meta("""{"cost_method":"FIFO","allocations":[1,2]}"""))
        assertEquals("+3,00% · FIFO, 2 lotes", Operations.realizedDetail(fifo))
        assertEquals("+3,00% · custo médio", Operations.realizedDetail(fifo.copy(realizedMetadata = null)))
    }

    @Test
    fun editKeepsTheSignAndRewritesDates() {
        val sale = movement("-4", metadata = """{"sale_date":"2026-10-01","sale_price":15,"other_costs":1,"cash_account_id":"c1","note":"x"}""")
        val form = Operations.editForm(sale, "PETR4", FixedIncome.Metadata())
        assertEquals("4", form.quantity)
        assertTrue(form.isSale)
        assertEquals("15", form.salePrice)
        assertEquals("2026-10-01", form.movementDate)
        val body = Operations.editPayload(form.copy(quantity = "3", movementDate = "2026-10-05"), sale.metadata)
        assertEquals(money("-3"), body["quantity"])
        @Suppress("UNCHECKED_CAST")
        val metadata = body["metadata"] as Map<String, Any?>
        assertEquals("2026-10-05", metadata["sale_date"])
        assertEquals(money("15"), metadata["sale_price"])
        assertEquals("c1", metadata["cash_account_id"])
        assertEquals(JsonPrimitive("x"), metadata["note"])
        assertFalse(metadata.containsKey("purchase_date"))
        // "Nao descontar" na edicao manda null.
        val unlinked = Operations.editPayload(form.copy(cashLink = form.cashLink.copy(enabled = false)), sale.metadata)
        @Suppress("UNCHECKED_CAST")
        assertTrue((unlinked["metadata"] as Map<String, Any?>).containsKey("cash_account_id"))
    }

    @Test
    fun editRefusesBadNumbers() {
        val buy = Operations.editForm(movement("10"), "PETR4", FixedIncome.Metadata())
        assertEquals("Informe um preço/valor válido.", assertThrows(Operations.FormError::class.java) { Operations.editPayload(buy.copy(averagePrice = "x"), null) }.message)
        assertEquals("Informe custos válidos.", assertThrows(Operations.FormError::class.java) { Operations.editPayload(buy.copy(otherCosts = "-1"), null) }.message)
        assertEquals("Informe uma quantidade válida.", assertThrows(Operations.FormError::class.java) { Operations.editPayload(buy.copy(quantity = "0"), null) }.message)
        val sale = Operations.editForm(movement("-1"), "PETR4", FixedIncome.Metadata())
        assertEquals("Informe um preço de venda válido.", assertThrows(Operations.FormError::class.java) { Operations.editPayload(sale, null) }.message)
    }

    @Test
    fun editOfARedemptionKeepsItsQuantityNegative() {
        val redemption = movement("-1", assetClass = "FIXED_INCOME", metadata = """{"is_redemption":true,"redemption_date":"2026-09-01"}""")
        val form = Operations.editForm(redemption, "CDB X", FixedIncome.Metadata())
        val body = Operations.editPayload(form, redemption.metadata)
        assertEquals(money("-1"), body["quantity"])
        @Suppress("UNCHECKED_CAST")
        val metadata = body["metadata"] as Map<String, Any?>
        assertEquals(true, metadata["is_redemption"])
        assertEquals("2026-09-01", metadata["redemption_date"])
    }

    @Test
    fun screenTypesMapToStoredClasses() {
        assertEquals("STOCKS", Operations.movementAssetClass("ETF"))
        assertEquals("FIXED_INCOME", Operations.movementAssetClass("TESOURO"))
        assertEquals("OTHER", Operations.movementAssetClass("BITCOIN"))
        assertEquals("REIT", Operations.movementAssetClass("REIT"))
        assertEquals("BITCOIN", Operations.assetTypeOf("OTHER", "CRIPTO", null))
        assertEquals("ETF", Operations.assetTypeOf("STOCKS", "ETF", "ETF"))
        assertEquals("TESOURO", Operations.assetTypeOf("FIXED_INCOME", null, "TESOURO"))
        assertEquals("STOCKS", Operations.assetTypeOf(null, null, null))
    }

    @Test
    fun liveTotalOfEachMode() {
        assertEquals(0, money("102").compareTo(Operations.launchTotal(LaunchForm(quantity = "10", price = "10", otherCosts = "2"))))
        assertEquals(0, money("98").compareTo(Operations.launchTotal(LaunchForm(mode = "SELL", quantity = "10", price = "10", otherCosts = "2"))))
        assertEquals(BigDecimal.ZERO, Operations.launchTotal(LaunchForm(mode = "SELL", quantity = "1", price = "1", otherCosts = "5")))
        // Renda fixa: o valor aplicado mais custos, sem quantidade.
        assertEquals(0, money("1002").compareTo(Operations.launchTotal(LaunchForm(assetType = "FIXED_INCOME", quantity = "7", price = "1000", otherCosts = "2"))))
    }

    @Test
    fun buyBodyLikeTheWeb() {
        val form = LaunchForm(tickerOrName = " petr4 ", date = "2026-10-22", quantity = "3", price = "10", otherCosts = "1", cashLink = PortfolioAccount.CashLink(true, "c1", false))
        val body = Operations.buyPayload(form, null, existing = false)
        assertEquals("STOCKS", body["asset_class"])
        assertEquals("PETR4", body["ticker_or_name"])
        assertEquals(money("3"), body["quantity"])
        assertEquals(0, money("10.333333").compareTo(body["average_price"] as BigDecimal))
        assertEquals(money("10"), body["current_price"])
        assertEquals(mapOf("purchase_date" to "2026-10-22", "other_costs" to money("1"), "cash_account_id" to "c1"), body["metadata"])
        // Ativo ja na carteira: a cotacao dele.
        assertEquals(money("31"), Operations.buyPayload(form, money("31"), existing = true)["current_price"])
    }

    @Test
    fun treasuryBuyCarriesRateAndUnits() {
        val base = Operations.changeAssetType(LaunchForm(date = "2026-10-22", cashLink = PortfolioAccount.CashLink(false, "", false)), "TESOURO")
        val named = Operations.changeFixedIncomeName(base, "Tesouro IPCA+ 2035")
        assertEquals("IPCA", named.fixedIncome.indexer)
        val form = named.copy(price = "1000", treasuryUnits = "0,85", fixedIncome = named.fixedIncome.copy(rate = "6,5"))
        val body = Operations.buyPayload(form, null, existing = false)
        assertEquals("FIXED_INCOME", body["asset_class"])
        assertEquals(BigDecimal.ONE, body["quantity"])
        @Suppress("UNCHECKED_CAST")
        val metadata = body["metadata"] as Map<String, Any?>
        assertEquals("TESOURO", metadata["fixed_income_type"])
        assertEquals(0.85, metadata["treasury_units"])
        assertTrue(metadata.containsKey("cash_account_id"))
        assertNull(metadata["cash_account_id"])
        assertEquals("Informe uma quantidade de títulos válida.", assertThrows(Operations.FormError::class.java) { Operations.buyPayload(form.copy(treasuryUnits = "x"), null, false) }.message)
    }

    @Test
    fun buyRefusals() {
        val ok = LaunchForm(tickerOrName = "PETR4", quantity = "1", price = "10", cashLink = PortfolioAccount.CashLink(false, "", false))
        assertEquals("Informe o ativo do lançamento.", assertThrows(Operations.FormError::class.java) { Operations.buyPayload(ok.copy(tickerOrName = " "), null, false) }.message)
        assertEquals("Informe um preço válido.", assertThrows(Operations.FormError::class.java) { Operations.buyPayload(ok.copy(price = ""), null, false) }.message)
        assertEquals("Informe uma quantidade válida.", assertThrows(Operations.FormError::class.java) { Operations.buyPayload(ok.copy(quantity = "0"), null, false) }.message)
        // Sem conta da carteira, a operacao nova e recusada (cashLinkMetadata).
        assertThrows(PortfolioAccount.CashLinkError::class.java) { Operations.buyPayload(ok.copy(cashLink = PortfolioAccount.CashLink(true, "", true)), null, false) }
    }

    @Test
    fun catalogCheckOnlyForTypedTickersOutsideTheWallet() {
        val typed = LaunchForm(tickerOrName = "abcd3")
        assertTrue(Operations.needsCatalogCheck(typed, listOf("PETR4")))
        assertFalse(Operations.needsCatalogCheck(typed, listOf("ABCD3")))
        assertFalse(Operations.needsCatalogCheck(typed.copy(tickerConfirmed = true), emptyList()))
        assertFalse(Operations.needsCatalogCheck(typed.copy(assetType = "OTHER"), emptyList()))
        assertEquals("ABCD3 não está na lista da B3. Selecione um ativo pela busca.", Operations.notInCatalogMessage("ABCD3"))
    }

    @Test
    fun sellBodyAndRefusals() {
        val asset = Operations.SaleAsset("STOCKS", "PETR4", money("10"), money("20"), money("25"))
        val form = LaunchForm(mode = "SELL", date = "2026-10-22", quantity = "4", price = "25,5", cashLink = PortfolioAccount.CashLink(true, "c1", false))
        val body = Operations.sellPayload(form, asset)
        assertEquals(money("-4"), body["quantity"])
        assertEquals(money("20"), body["average_price"])
        assertEquals(mapOf("sale_date" to "2026-10-22", "sale_price" to money("25.5"), "other_costs" to BigDecimal.ZERO, "cash_account_id" to "c1"), body["metadata"])
        assertEquals("Selecione o ativo para venda.", assertThrows(Operations.FormError::class.java) { Operations.sellPayload(form, null) }.message)
        assertEquals("A quantidade informada é maior do que a posição disponível.", assertThrows(Operations.FormError::class.java) { Operations.sellPayload(form.copy(quantity = "11"), asset) }.message)
        assertEquals("Informe o preço da venda.", assertThrows(Operations.FormError::class.java) { Operations.sellPayload(form.copy(price = ""), asset) }.message)
    }

    @Test
    fun changingModeOrTypeResetsTheAsset() {
        val form = LaunchForm(assetType = "REIT", tickerOrName = "HGLG11", quantity = "5", price = "100")
        val sell = Operations.changeMode(form, "SELL")
        assertEquals(listOf("STOCKS", "", "1", ""), listOf(sell.assetType, sell.tickerOrName, sell.quantity, sell.price))
        assertEquals("REIT", Operations.changeMode(form, "BUY").assetType)
        assertEquals("BTC", Operations.changeAssetType(form, "BITCOIN").tickerOrName)
        assertEquals("", Operations.changeAssetType(form, "FIXED_INCOME").tickerOrName)
    }

    @Test
    fun corporateActionBody() {
        val split = Operations.corporateActionPayload("a1", "SPLIT", "2026-10-01", "1", "2", "5", "")
        assertEquals(mapOf("asset_id" to "a1", "action_type" to "SPLIT", "ex_date" to "2026-10-01", "ratio_from" to money("1"), "ratio_to" to money("2")), split)
        val bonus = Operations.corporateActionPayload("a1", "BONUS", "2026-10-01", "10", "1,5", "", "aviso")
        assertEquals(money("1.5"), bonus["ratio_to"])
        assertFalse(bonus.containsKey("bonus_unit_cost"))
        assertEquals("aviso", bonus["notes"])
        // Ilegivel vai como null (o NaN do JSON).
        val bad = Operations.corporateActionPayload("a1", "BONUS", "2026-10-01", "x", "1", "y", "")
        assertTrue(bad.containsKey("ratio_from"))
        assertNull(bad["ratio_from"])
        assertNull(bad["bonus_unit_cost"])
        assertEquals("1 para 2", Operations.ratioLabel(money("1"), money("2")))
        assertEquals("1,5 para 0,333333", Operations.ratioLabel(money("1.5"), money("0.3333333")))
    }
}
