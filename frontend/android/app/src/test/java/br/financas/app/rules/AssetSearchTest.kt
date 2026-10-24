// Porte: mudou um, muda o outro, com um teste de cada lado.
// Os casos de frontend/src/lib/assetSearch.test.js, na mesma ordem; o nome do teste do node vai
// no comentario de cada um.
package br.financas.app.rules

import br.financas.app.rules.AssetSearch.normalizeSearchText
import org.junit.Assert.assertEquals
import org.junit.Test

class AssetSearchTest {
    private data class Option(val value: String, val label: String, val name: String? = null)

    private val options = listOf(
        Option("1", "ITSA4", "Itaúsa"),
        Option("2", "ITUB4", "Itaú Unibanco"),
        Option("3", "BBAS3", "Banco do Brasil"),
        Option("4", "XPBR31", "Petrobras BDR"),
        Option("5", "PETR4", "Petrobras PN"),
    )

    private fun search(list: List<Option>?, query: String?, limit: Int = 50): List<String> =
        AssetSearch.filterAssetOptions(list, query, limit, label = { it.label }, name = { it.name }).map { it.value }

    // node: 'the search matches ticker or name, without accents, ticker first'
    @Test
    fun theSearchMatchesTickerOrNameWithoutAccentsTickerFirst() {
        assertEquals(listOf("1", "2"), search(options, "itau"))
        assertEquals(listOf("5", "4"), search(options, "petr"))
        assertEquals(listOf("3", "2"), search(options, " banco "))
        assertEquals(listOf("1", "2", "3", "4", "5"), search(options, ""))
        assertEquals(emptyList<String>(), search(options, "zzz"))
    }

    // node: 'the four ranks: ticker starts, ticker contains, name starts, name contains'
    @Test
    fun theFourRanks() {
        val ranked = listOf(
            Option("name-contains", "AAAA3", "Grupo Vale"),
            Option("name-starts", "BBBB3", "Vale do Rio"),
            Option("ticker-contains", "XVALE3", ""),
            Option("ticker-starts", "VALE3", "Mineradora"),
        )
        assertEquals(listOf("ticker-starts", "ticker-contains", "name-starts", "name-contains"), search(ranked, "vale"))
    }

    // node: 'a tie keeps the order given'
    @Test
    fun aTieKeepsTheOrderGiven() {
        assertEquals(listOf("b", "a"), search(listOf(Option("b", "TAEE11"), Option("a", "TAEE4")), "taee"))
    }

    // node: 'the limit cuts after ranking, with or without text'
    @Test
    fun theLimitCutsAfterRanking() {
        assertEquals(listOf("1", "2"), search(options, "", 2))
        assertEquals(listOf("5"), search(options, "petr", 1))
    }

    // node: 'missing name, missing list and an accented query'
    @Test
    fun missingNameMissingListAndAnAccentedQuery() {
        assertEquals(listOf("x"), search(listOf(Option("x", "KNRI11")), "knri"))
        assertEquals(emptyList<String>(), search(null, "a"))
        assertEquals(listOf("1", "2"), search(options, "ITAÚ"))
    }

    // node: 'normalizeSearchText: accents, case and spaces'
    @Test
    fun normalizeSearchTextAccentsCaseAndSpaces() {
        assertEquals("TESOURO IPCA+", normalizeSearchText("  Tesouro   IPCA+ "))
        assertEquals("ACAO OMEGA", normalizeSearchText("Ação Ômega"))
        assertEquals("", normalizeSearchText(null))
    }
}
