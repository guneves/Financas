// Porte: mudou um, muda o outro, com um teste de cada lado.
// Os casos de frontend/src/lib/treasury.test.js, na mesma ordem; o nome do teste do node vai no
// comentario de cada um. (Os do resgate PEPS foram para o servidor com a regra:
// backend/tests/test_investment_redemptions.py.)
package br.financas.app.rules

import br.financas.app.rules.FixedIncome.Metadata
import br.financas.app.rules.TreasuryLabels.Position
import br.financas.app.rules.TreasuryLabels.Treasury
import br.financas.app.rules.TreasuryLabels.isMarketValued
import br.financas.app.rules.TreasuryLabels.parseTreasuryUnits
import br.financas.app.rules.TreasuryLabels.treasuryMarketRateText
import br.financas.app.rules.TreasuryLabels.treasuryRateLabel
import br.financas.app.rules.TreasuryLabels.treasuryRateText
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class TreasuryLabelsTest {
    // node: 'rate texts follow the indexer'
    @Test
    fun rateTextsFollowTheIndexer() {
        assertEquals("IPCA + 6,23% a.a.", treasuryRateText(0.0623, Metadata(rateType = "POS", indexer = "IPCA")))
        assertEquals("Pré 12,10% a.a.", treasuryRateText(0.121, Metadata(rateType = "PRE")))
        assertEquals("100,00% do CDI", treasuryRateText(1.0, Metadata(rateType = "POS", indexer = "CDI")))
        assertEquals("", treasuryRateText(null, Metadata()))
    }

    // node: 'a grouped position says "Taxa média"'
    @Test
    fun aGroupedPositionSaysTaxaMedia() {
        val metadata = Metadata(rateType = "POS", indexer = "IPCA", annualRate = 0.0623)
        assertEquals("Taxa média IPCA + 6,23% a.a.", treasuryRateLabel(Position(metadata, Treasury(averageRate = 0.0623, lotCount = 2))))
        assertEquals("Taxa IPCA + 6,50% a.a.", treasuryRateLabel(Position(metadata, Treasury(averageRate = 0.065, lotCount = 1))))
        assertEquals("Taxa IPCA + 6,23% a.a.", treasuryRateLabel(Position(metadata)))
    }

    // node: 'the market rate of the day, never for Selic'
    @Test
    fun theMarketRateOfTheDayNeverForSelic() {
        val metadata = Metadata(rateType = "POS", indexer = "IPCA")
        assertEquals("IPCA + 6,20% a.a.", treasuryMarketRateText(Position(metadata, Treasury(marketRate = 0.062, titleType = "TESOURO IPCA+"))))
        assertEquals("", treasuryMarketRateText(Position(metadata, Treasury(marketRate = 0.0007, titleType = "TESOURO SELIC"))))
        // Sem par no node: isMarketValued so le o `valuation`.
        assertTrue(isMarketValued(Position(metadata, Treasury(valuation = "MARKET"))))
        assertEquals(false, isMarketValued(Position(metadata, Treasury(valuation = "CURVE"))))
    }

    // node: 'parseTreasuryUnits: virgula ou ponto, vazio e invalido'
    @Test
    fun parseTreasuryUnitsCommaOrDotEmptyAndInvalid() {
        assertEquals(0.85, parseTreasuryUnits("0,85")!!, 0.0)
        assertEquals(42.79, parseTreasuryUnits("42.79")!!, 0.0)
        assertEquals(1042.79, parseTreasuryUnits("1.042,79")!!, 0.0)
        assertNull(parseTreasuryUnits("  "))
        assertTrue(parseTreasuryUnits("0")!!.isNaN())
        assertTrue(parseTreasuryUnits("abc")!!.isNaN())
    }
}
