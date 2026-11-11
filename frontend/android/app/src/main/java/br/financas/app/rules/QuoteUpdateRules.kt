package br.financas.app.rules

import br.financas.app.data.QuoteUpdateDto

/**
 * "Atualizar cotações" (Posição) mostra só as falhas (dono 2026-11-11; lib/quoteUpdate.js): o que
 * atualizou não vira aviso, e sem falha o painel nem aparece. Uma linha por motivo: um tempo limite
 * do provedor não se repete ticker a ticker.
 */
object QuoteUpdateRules {
    data class FailureGroup(val error: String, val names: List<String>)

    fun failureCount(result: QuoteUpdateDto?): Int = result?.failedAssets?.size ?: 0

    fun failureGroups(result: QuoteUpdateDto?): List<FailureGroup> =
        result?.failedAssets.orEmpty()
            .groupBy { it.error?.takeIf(String::isNotEmpty) ?: "sem detalhe" }
            .map { (error, assets) -> FailureGroup(error, assets.map { it.ticker?.takeIf(String::isNotEmpty) ?: it.name.orEmpty() }) }
}
