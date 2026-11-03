// A tela "A receber" (pages/lancamentos/AReceber.jsx): o que la e inline, sem teste no node — o
// filtro dos pendentes, o total em aberto de cada pessoa, o "Tudo pago" so com dois ou mais e os
// numeros do resumo —, aqui com testes (ReceivablesTest.kt). O agrupamento e Sharing.groupReceivables.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.data.IncomeChoiceDto
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

    /** O que POST /api/receivables/settle leva para estes itens; [incomeId] = a receita que pagou (053). */
    fun settleBody(items: List<ReceivableDto>, settled: Boolean, incomeId: String? = null): Map<String, Any?> {
        val body = Sharing.settlePayload(items.map { Sharing.ReceivableRef(it.kind, it.id) }, settled).toMutableMap()
        if (settled && !incomeId.isNullOrEmpty()) body["income_id"] = incomeId
        return body
    }

    private fun total(items: List<ReceivableDto>) = items.fold(BigDecimal.ZERO) { acc, it -> acc + (it.othersAmount ?: BigDecimal.ZERO) }

    /**
     * As receitas que podem ter pago estes itens (lib/sharing.js paymentChoices): a que ja paga
     * algum deles no topo, com a parte deles livre de novo na sobra.
     */
    fun paymentChoices(candidates: List<IncomeChoiceDto>, items: List<ReceivableDto>): List<IncomeChoiceDto> {
        val freed = linkedMapOf<String, Pair<IncomeChoiceDto, BigDecimal>>()
        items.forEach { item ->
            val paid = item.paidBy ?: return@forEach
            val before = freed[paid.id]?.second ?: BigDecimal.ZERO
            freed[paid.id] = paid to before + (item.othersAmount ?: BigDecimal.ZERO)
        }
        val choices = candidates.map { income ->
            income.copy(room = (income.room ?: BigDecimal.ZERO) + (freed[income.id]?.second ?: BigDecimal.ZERO))
        }.toMutableList()
        freed.forEach { (id, pair) -> if (choices.none { it.id == id }) choices.add(0, pair.first.copy(room = pair.second)) }
        return choices
    }

    /** A ja escolhida (comum a todos) ou a primeira no dia do item ou depois em que cabe o total; "" = nenhuma. */
    fun suggestedPayment(choices: List<IncomeChoiceDto>, items: List<ReceivableDto>): String {
        val current = items.map { it.paidBy?.id.orEmpty() }
        if (current.isNotEmpty() && current[0].isNotEmpty() && current.all { it == current[0] }) return current[0]
        val needed = total(items)
        val first = items.map { it.date.orEmpty() }.minOrNull().orEmpty()
        return choices
            .filter { it.date.orEmpty() >= first && (it.room ?: BigDecimal.ZERO) >= needed }
            .minByOrNull { it.date.orEmpty() }?.id.orEmpty()
    }

    /** O total do que se marca, para o texto do sheet. */
    fun payingTotal(items: List<ReceivableDto>): BigDecimal = total(items)
}
