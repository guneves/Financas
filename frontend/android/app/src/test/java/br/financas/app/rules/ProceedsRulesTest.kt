// Porte: mudou um, muda o outro, com um teste de cada lado.
// Os casos de frontend/src/lib/proceedsRules.test.js, na mesma ordem; o nome do teste do node vai
// no comentario de cada um.
package br.financas.app.rules

import br.financas.app.rules.ProceedsRules.Asset
import br.financas.app.rules.ProceedsRules.assetCategory
import br.financas.app.rules.ProceedsRules.assetsForProceedsType
import br.financas.app.rules.ProceedsRules.categoryLabel
import br.financas.app.rules.ProceedsRules.changesPositions
import br.financas.app.rules.ProceedsRules.proceedsLayout
import br.financas.app.rules.ProceedsRules.proceedsTaxField
import br.financas.app.rules.ProceedsRules.proceedsTypeFitsAsset
import br.financas.app.rules.ProceedsRules.treasuryProduct
import br.financas.app.rules.ProceedsRules.typeForAsset
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ProceedsRulesTest {
    private fun asset(id: String, ticker: String, category: String) = Asset(id, ticker, ticker, category)

    private val assets = listOf(
        asset("petr", "PETR4", "ACAO"),
        asset("bova", "BOVA11", "ETF"),
        asset("xpbr", "XPBR31", "BDR"),
        asset("mxrf", "MXRF11", "FII"),
        asset("cdb", "CDB BANCO X", "RENDA_FIXA"),
        asset("selic", "TESOURO SELIC 2029", "TESOURO"),
        asset("ntnb", "TESOURO IPCA+ COM JUROS SEMESTRAIS 2035", "TESOURO"),
        asset("renda", "TESOURO RENDA+ APOSENTADORIA EXTRA 2065", "TESOURO"),
        asset("tit", "TITULO PUBLICO X", "TESOURO"),
        asset("btc", "BTC", "CRIPTO"),
    )

    private fun ids(list: List<Asset>) = list.map { it.id }

    // node: 'each proceeds type lists only the assets that can pay it'
    @Test
    fun eachProceedsTypeListsOnlyTheAssetsThatCanPayIt() {
        assertEquals(listOf("petr"), ids(assetsForProceedsType(assets, "JCP")))
        assertEquals(listOf("petr", "bova", "xpbr", "mxrf"), ids(assetsForProceedsType(assets, "DIVIDEND")))
        assertEquals(listOf("cdb", "ntnb", "tit"), ids(assetsForProceedsType(assets, "INTEREST")))
        assertEquals(listOf("petr", "mxrf", "cdb", "renda", "tit"), ids(assetsForProceedsType(assets, "AMORTIZATION")))
    }

    // node: 'an edit keeps its own asset even when it no longer fits'
    @Test
    fun anEditKeepsItsOwnAsset() {
        assertEquals(listOf("petr", "mxrf"), ids(assetsForProceedsType(assets, "JCP", "mxrf")))
    }

    // node: 'the treasury product comes from the title name'
    @Test
    fun theTreasuryProductComesFromTheTitleName() {
        assertEquals("BULLET", treasuryProduct("Tesouro Selic 2029"))
        assertEquals("BULLET", treasuryProduct("Tesouro Prefixado 2031"))
        assertEquals("BULLET", treasuryProduct("Tesouro IPCA+ 2045"))
        assertEquals("COUPON", treasuryProduct("Tesouro Prefixado com Juros Semestrais 2035"))
        assertEquals("COUPON", treasuryProduct("NTN-B 2035"))
        assertEquals("BULLET", treasuryProduct("NTN-B Principal 2035"))
        assertEquals("COUPON", treasuryProduct("NTN-F 2031"))
        assertEquals("INSTALLMENTS", treasuryProduct("Tesouro Educa+ 2030"))
        assertNull(treasuryProduct("Título do governo"))
    }

    // node: 'a category falls back to the class for an old response'
    @Test
    fun aCategoryFallsBackToTheClass() {
        assertEquals("ACAO", assetCategory(Asset("a", assetClass = "STOCKS")))
        assertEquals("RENDA_FIXA", assetCategory(Asset("a", assetClass = "FIXED_INCOME")))
        assertEquals("ETF", assetCategory(Asset("a", assetClass = "STOCKS", category = "ETF")))
        assertEquals("Tesouro Direto", categoryLabel(Asset("a", category = "TESOURO")))
        assertEquals(false, proceedsTypeFitsAsset("JCP", Asset("a", assetClass = "REIT")))
    }

    // node: 'the form layout and the tax field follow the type and the asset'
    @Test
    fun theFormLayoutAndTheTaxFieldFollowTheTypeAndTheAsset() {
        assertEquals("FIXED", proceedsLayout("INTEREST", assets[4]))
        assertEquals("FIXED", proceedsLayout("AMORTIZATION", assets[7]))
        assertEquals("MARKET", proceedsLayout("AMORTIZATION", assets[3]))
        assertEquals("MARKET", proceedsLayout("DIVIDEND", assets[0]))
        assertNull(proceedsTaxField("AMORTIZATION"))
        assertTrue(proceedsTaxField("JCP")!!.hint.contains("15%"))
        assertTrue(proceedsTaxField("INTEREST")!!.hint.contains("regressiva"))
        assertTrue(proceedsTaxField("DIVIDEND")!!.hint.contains("sem IR"))
    }

    // node: 'changing asset keeps the type when it fits, else picks the first that does'
    @Test
    fun changingAssetKeepsTheTypeWhenItFits() {
        assertEquals("JCP", typeForAsset(assets[0], "JCP"))
        assertEquals("DIVIDEND", typeForAsset(assets[3], "JCP"))
        assertEquals("AMORTIZATION", typeForAsset(assets[4], "DIVIDEND"))
        assertEquals("INTEREST", typeForAsset(assets[6], "DIVIDEND"))
        assertEquals("JCP", typeForAsset(null, "JCP"))
    }

    // node: 'changesPositions: operacoes e eventos sim, cotacoes nao'
    @Test
    fun changesPositionsOperationsAndEventsYesQuotesNo() {
        assertEquals(true, changesPositions("/api/investments"))
        assertEquals(true, changesPositions("/api/investments/abc"))
        assertEquals(true, changesPositions("/api/investments/by-asset/abc?asset_class=STOCKS"))
        assertEquals(true, changesPositions("/api/corporate-actions"))
        assertEquals(true, changesPositions("/api/investments/redemptions"))
        assertEquals(true, changesPositions("/api/investments/by-assets"))
        assertEquals(false, changesPositions("/api/investments/update-prices"))
        assertEquals(false, changesPositions("/api/investments/price-by-asset/abc"))
        assertEquals(false, changesPositions("/api/investment-proceeds"))
        assertEquals(false, changesPositions(""))
    }
}
