// Porte: mudou um, muda o outro, com um teste de cada lado.
// Os casos de frontend/src/lib/fixedIncome.test.js, na mesma ordem; o nome do teste do node vai
// no comentario de cada um. A web compara objetos com chaves `undefined`; aqui o mapa so tem as
// presentes (o mesmo JSON).
package br.financas.app.rules

import br.financas.app.rules.FixedIncome.FIXED_INCOME_TYPES
import br.financas.app.rules.FixedIncome.Form
import br.financas.app.rules.FixedIncome.Metadata
import br.financas.app.rules.FixedIncome.RateError
import br.financas.app.rules.FixedIncome.TREASURY_TITLES
import br.financas.app.rules.FixedIncome.TREASURY_TYPE
import br.financas.app.rules.FixedIncome.describeFixedIncome
import br.financas.app.rules.FixedIncome.fixedIncomeFormFromMetadata
import br.financas.app.rules.FixedIncome.fixedIncomeMetadataFromForm
import br.financas.app.rules.FixedIncome.isTaxFreeFixedIncomeType
import br.financas.app.rules.FixedIncome.rateFieldLabel
import br.financas.app.rules.FixedIncome.rateFieldsForMode
import br.financas.app.rules.FixedIncome.rateModeOf
import br.financas.app.rules.FixedIncome.ratePlaceholder
import br.financas.app.rules.FixedIncome.treasuryRateMode
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class FixedIncomeTest {
    private fun form(type: String, mode: String, rate: String): Form {
        val (rateType, indexer) = rateFieldsForMode(mode)
        return Form(type, rateType, indexer, rate)
    }

    // node: 'Tesouro Direto is a fixed-income type, taxed by the regressive table'
    @Test
    fun tesouroDiretoIsAFixedIncomeType() {
        assertTrue(FIXED_INCOME_TYPES.any { it.value == TREASURY_TYPE && it.label == "Tesouro Direto" })
        assertEquals(false, isTaxFreeFixedIncomeType(TREASURY_TYPE))
        val metadata = fixedIncomeMetadataFromForm(form(TREASURY_TYPE, "IPCA", "6,5"))
        assertEquals(
            listOf("TESOURO", "POS", "IPCA", 0.065, false),
            listOf(metadata["fixed_income_type"], metadata["rate_type"], metadata["indexer"], metadata["annual_rate"], metadata["is_tax_free"]),
        )
    }

    // node: 'the treasury title name gives its rate mode'
    @Test
    fun theTreasuryTitleNameGivesItsRateMode() {
        assertEquals("POS", treasuryRateMode("Tesouro Selic 2029"))
        assertEquals("PRE", treasuryRateMode("Tesouro Prefixado com Juros Semestrais 2035"))
        assertEquals("IPCA", treasuryRateMode("Tesouro IPCA+ 2045"))
        assertEquals("IPCA", treasuryRateMode("Tesouro Renda+ Aposentadoria Extra 2065"))
        assertEquals("IPCA", treasuryRateMode("Tesouro Educa+ 2030"))
        assertNull(treasuryRateMode("Título X"))
        TREASURY_TITLES.forEach { assertNotNull(it, treasuryRateMode(it)) }
    }

    // node: 'the form refuses an empty, negative or unreadable rate, and a zero % of CDI'
    @Test
    fun theFormRefusesBadRates() {
        val cdiError = "Informe um percentual do CDI válido."
        val rateError = "Informe uma taxa válida."
        for (rate in listOf("", "  ", "-1", "abc", "0", "0,0")) {
            val error = assertThrows(rate, RateError::class.java) { fixedIncomeMetadataFromForm(Form("CDB", "POS", "CDI", rate)) }
            assertEquals(rate, cdiError, error.message)
        }
        for (rate in listOf("", "-0,5", "1,2,3")) {
            val error = assertThrows(rate, RateError::class.java) { fixedIncomeMetadataFromForm(Form("CDB", "PRE", "CDI", rate)) }
            assertEquals(rate, rateError, error.message)
        }
        assertEquals(0.0, fixedIncomeMetadataFromForm(Form("CDB", "PRE", "CDI", "0"))["annual_rate"])
    }

    // node: 'the form writes the rate in the key its mode reads, and the tax-free flag by type'
    @Test
    fun theFormWritesTheRateInTheKeyItsModeReads() {
        assertEquals(
            mapOf("fixed_income_type" to "LCI", "rate_type" to "POS", "indexer" to "CDI", "cdi_percentage" to 12.345, "is_tax_free" to true),
            fixedIncomeMetadataFromForm(Form("LCI", "POS", "CDI", "1.234,5")),
        )
        assertEquals(
            mapOf("rate_type" to "PRE", "annual_rate" to 0.125, "is_tax_free" to false),
            fixedIncomeMetadataFromForm(Form("", "PRE", "CDI", "12.5")),
        )
        assertEquals(0.015, fixedIncomeMetadataFromForm(Form("CDB", "POS", "CDI_PLUS", "1,5"))["annual_rate"])
    }

    // node: 'the saved metadata comes back as the form'
    @Test
    fun theSavedMetadataComesBackAsTheForm() {
        assertEquals(
            Form("CDB", "POS", "CDI", "110"),
            fixedIncomeFormFromMetadata(Metadata(fixedIncomeType = "CDB", rateType = "POS", indexer = "CDI", cdiPercentage = 1.1)),
        )
        assertEquals(
            Form("DEBENTURE_INCENTIVADA", "PRE", "CDI", "12.3456"),
            fixedIncomeFormFromMetadata(
                Metadata(fixedIncomeType = "DEBENTURE", isTaxFree = true, rateType = "PRE", indexer = "IPCA", annualRate = 0.123456),
            ),
        )
        assertEquals(Form("", "POS", "CDI", "95"), fixedIncomeFormFromMetadata(Metadata(cdiPercentage = 0.95)))
        assertEquals("", fixedIncomeFormFromMetadata(Metadata(rateType = "POS", indexer = "IPCA")).rate)
        assertEquals("", fixedIncomeFormFromMetadata().rate)
    }

    // node: 'rate modes, labels and placeholders'
    @Test
    fun rateModesLabelsAndPlaceholders() {
        assertEquals("PRE", rateModeOf("PRE", "IPCA"))
        assertEquals("IPCA", rateModeOf("POS", "IPCA"))
        assertEquals("POS", rateModeOf("POS", "CDI_PLUS"))
        assertEquals("PRE" to "CDI", rateFieldsForMode("PRE"))
        assertEquals("POS" to "CDI", rateFieldsForMode("POS"))
        assertEquals("Taxa (% a.a.)", rateFieldLabel("PRE", "CDI"))
        assertEquals("CDI + (% a.a.)", rateFieldLabel("POS", "CDI_PLUS"))
        assertEquals("IPCA + (% a.a.)", rateFieldLabel("POS", "IPCA"))
        assertEquals("% do CDI", rateFieldLabel("POS", "CDI"))
        assertEquals("Ex: 12,5", ratePlaceholder("PRE", "CDI"))
        assertEquals("Ex: 110", ratePlaceholder("POS", "CDI"))
    }

    // node: 'the one-line description of a title'
    @Test
    fun theOneLineDescriptionOfATitle() {
        assertEquals("CDB · 110% do CDI", describeFixedIncome(Metadata("CDB", "POS", "CDI", cdiPercentage = 1.1)))
        assertEquals("Tesouro Direto · IPCA + 6,5% a.a.", describeFixedIncome(Metadata("TESOURO", "POS", "IPCA", annualRate = 0.065)))
        assertEquals("Pré 12,35% a.a.", describeFixedIncome(Metadata(rateType = "PRE", annualRate = 0.12345)))
        assertEquals("LCA · CDI + 1,5% a.a.", describeFixedIncome(Metadata("LCA", "POS", "CDI_PLUS", annualRate = 0.015)))
        assertEquals("CDB", describeFixedIncome(Metadata("CDB", "PRE")))
        assertEquals("1.200% do CDI", describeFixedIncome(Metadata("XYZ", cdiPercentage = 12.0)))
        assertEquals("", describeFixedIncome())
    }
}
