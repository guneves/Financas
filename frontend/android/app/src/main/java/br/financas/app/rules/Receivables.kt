// A tela "A receber" (pages/lancamentos/AReceber.jsx): o que la e inline, sem teste no node — o
// filtro dos pendentes, o total em aberto de cada pessoa, o "Tudo pago" so com dois ou mais e os
// numeros do resumo —, aqui com testes (ReceivablesTest.kt). O agrupamento e Sharing.groupReceivables.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.data.ReceivableDto
import java.math.BigDecimal

object Receivables {

    /** Uma pessoa na tela: os itens da vista, os em aberto, o total em aberto e se mostra "Tudo pago". */
    data class PersonGroup(
        val person: String,
        val items: List<ReceivableDto>,
        val open: List<ReceivableDto>,
        val openTotal: BigDecimal,
    ) {
        /** "Tudo pago" so com mais de um item em aberto. */
        val showSettleAll: Boolean get() = open.size > 1
    }

    /** O resumo: so quando ha algo pendente (em qualquer vista). */
    data class Summary(val total: BigDecimal, val people: Int, val items: Int)

    data class View(val summary: Summary?, val groups: List<PersonGroup>)

    private fun pending(items: List<ReceivableDto>) = items.filter { it.settledAt.isNullOrEmpty() }

    private fun group(items: List<ReceivableDto>) =
        Sharing.groupReceivables(items.map { Sharing.Receivable(it, it.person, it.othersAmount) })

    /** [all] = "Todos" (os pagos inclusive); senao so os pendentes. */
    fun view(items: List<ReceivableDto>, all: Boolean): View {
        val open = pending(items)
        val openGroups = group(open)
        val summary = if (open.isEmpty()) null else Summary(openGroups.fold(BigDecimal.ZERO) { acc, it -> acc + it.total }, openGroups.size, open.size)
        val groups = group(if (all) items else open).map { shown ->
            val stillOpen = pending(shown.items)
            PersonGroup(shown.person, shown.items, stillOpen, group(stillOpen).firstOrNull()?.total ?: BigDecimal.ZERO)
        }
        return View(summary, groups)
    }

    /** O que POST /api/receivables/settle leva para estes itens. */
    fun settleBody(items: List<ReceivableDto>, settled: Boolean): Map<String, Any?> =
        Sharing.settlePayload(items.map { Sharing.ReceivableRef(it.kind, it.id) }, settled)
}
