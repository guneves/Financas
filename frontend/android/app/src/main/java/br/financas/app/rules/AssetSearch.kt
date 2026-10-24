// Porte: mudou um, muda o outro, com um teste de cada lado.
// Par: frontend/src/lib/assetSearch.js (assetSearch.test.js); aqui AssetSearchTest.kt,
// os mesmos casos na mesma ordem.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.core.Js
import java.text.Normalizer

/**
 * Busca de um ativo da carteira enquanto se digita (AssetPicker): ticker ou nome, sem acento nem
 * caixa. Quem comeca com o texto vem antes de quem so o contem, e o ticker antes do nome — como a
 * busca do catalogo da B3 (market_catalog.search).
 */
object AssetSearch {
    private val MARKS = Regex("[̀-ͯ]")
    private val SPACES = Regex(Js.whitespaceClass + "+")

    /** NFD sem as marcas, caixa alta, espacos juntos e sem borda (o `normalizeSearchText` da web). */
    fun normalizeSearchText(value: String?): String {
        val decomposed = Normalizer.normalize(value ?: "", Normalizer.Form.NFD)
        return Js.trim(MARKS.replace(decomposed, "").uppercase().replace(SPACES, " "))
    }

    /**
     * As opcoes que casam com [query], ordenadas: ticker comeca, ticker contem, nome comeca, nome
     * contem; empate fica na ordem dada. Sem texto, todas na ordem dada. No maximo [limit].
     * [label] e o ticker da opcao, [name] o nome (pode faltar).
     */
    fun <T> filterAssetOptions(
        options: List<T>?,
        query: String?,
        limit: Int = 50,
        label: (T) -> String?,
        name: (T) -> String?,
    ): List<T> {
        val list = options ?: emptyList()
        val needle = normalizeSearchText(query)
        if (needle.isEmpty()) return list.take(maxOf(limit, 0))
        data class Ranked<T>(val rank: Int, val index: Int, val option: T)
        val ranked = mutableListOf<Ranked<T>>()
        list.forEachIndexed { index, option ->
            val ticker = normalizeSearchText(label(option))
            val fullName = normalizeSearchText(name(option))
            val rank = when {
                ticker.startsWith(needle) -> 0
                ticker.contains(needle) -> 1
                fullName.startsWith(needle) -> 2
                fullName.contains(needle) -> 3
                else -> return@forEachIndexed
            }
            ranked.add(Ranked(rank, index, option))
        }
        return ranked
            .sortedWith(compareBy<Ranked<T>>({ it.rank }, { it.index }))
            .take(maxOf(limit, 0))
            .map { it.option }
    }
}
