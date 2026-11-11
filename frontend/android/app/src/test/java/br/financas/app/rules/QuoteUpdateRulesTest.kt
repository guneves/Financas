// Os casos de lib/quoteUpdate.test.js.
package br.financas.app.rules

import br.financas.app.data.QuoteAssetDto
import br.financas.app.data.QuoteUpdateDto
import br.financas.app.rules.QuoteUpdateRules.FailureGroup
import org.junit.Assert.assertEquals
import org.junit.Test

class QuoteUpdateRulesTest {
    @Test
    fun semFalhaNaoHaAviso() {
        val result = QuoteUpdateDto(
            updatedCount = 1,
            updatedAssets = listOf(QuoteAssetDto(ticker = "PETR4")),
            cachedAssets = listOf(QuoteAssetDto(ticker = "VALE3")),
            staleAssets = listOf(QuoteAssetDto(ticker = "IVVB11")),
        )
        assertEquals(0, QuoteUpdateRules.failureCount(result))
        assertEquals(emptyList<FailureGroup>(), QuoteUpdateRules.failureGroups(result))
        assertEquals(emptyList<FailureGroup>(), QuoteUpdateRules.failureGroups(null))
    }

    @Test
    fun falhasAgrupadasPorMotivoNaOrdem() {
        val result = QuoteUpdateDto(
            updatedAssets = listOf(QuoteAssetDto(ticker = "PETR4")),
            failedAssets = listOf(
                QuoteAssetDto(ticker = "AAPL34", error = "Tempo limite"),
                QuoteAssetDto(ticker = "XPML11", error = "Cotacao nao encontrada"),
                QuoteAssetDto(ticker = "BOVA11", error = "Tempo limite"),
                QuoteAssetDto(name = "CDB Banco X"),
            ),
        )
        assertEquals(4, QuoteUpdateRules.failureCount(result))
        assertEquals(
            listOf(
                FailureGroup("Tempo limite", listOf("AAPL34", "BOVA11")),
                FailureGroup("Cotacao nao encontrada", listOf("XPML11")),
                FailureGroup("sem detalhe", listOf("CDB Banco X")),
            ),
            QuoteUpdateRules.failureGroups(result),
        )
    }
}
