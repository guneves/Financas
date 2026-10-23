// Port: mudou um, muda o outro, com um teste de cada lado.
// Par: frontend/src/lib/attentionRules.js (attentionRules.test.js): overdueDetail, attentionText,
// attentionLink, bellBadge, bellLabel, undismissedItems, addDismissed, isPastDue e
// invoiceMonthKey. Aqui: AttentionRulesTest.kt, os mesmos casos. As regras dos avisos (o que
// venceu, o que fechou, o debito sem saldo...) e as chaves sao do servidor (GET /api/attention,
// services/attention.py); aqui ficam o texto e as dispensas deste aparelho.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.core.formatCurrency
import br.financas.app.core.formatDateBR
import java.math.BigDecimal

/** Uma fatura do aviso INVOICE_OVERDUE (as `invoices` dele, em ordem de vencimento). */
data class AttentionInvoice(
    val cardId: String? = null,
    val cardName: String? = null,
    val invoiceMonth: Int? = null,
    val invoiceYear: Int? = null,
    val dueDate: String? = null,
    val total: BigDecimal? = null,
)

/** Um aviso de GET /api/attention: so os numeros (snake_case la, aqui os campos que o texto le). */
data class AttentionItem(
    val key: String,
    val kind: String,
    val tone: String = "",
    val total: BigDecimal? = null,
    val itemCount: Int? = null,
    val invoices: List<AttentionInvoice> = emptyList(),
    val accountName: String? = null,
    val balance: BigDecimal? = null,
    val missing: BigDecimal? = null,
    val firstDue: String? = null,
    val count: Int? = null,
    val categoryName: String? = null,
    val spent: BigDecimal? = null,
    val available: BigDecimal? = null,
)

/** Titulo e detalhe de um aviso; [detail] vazio = so o titulo. */
data class AttentionText(val title: String, val detail: String)

/** Para onde um aviso leva: a rota da web e o texto do link. */
data class AttentionLink(val route: String, val label: String)

object AttentionRules {
    const val INVOICE_OVERDUE = "INVOICE_OVERDUE"
    const val INVOICE_PAYABLE = "INVOICE_PAYABLE"
    const val AUTOPAY_SHORTFALL = "AUTOPAY_SHORTFALL"
    const val RECURRING = "RECURRING"
    const val OVER_BUDGET = "OVER_BUDGET"

    /** A lista guardada no aparelho nao cresce sem fim: fica com as mais recentes. */
    const val MAX_DISMISSED_KEYS = 200

    /** O mes da fatura (AAAA-MM), que e o mes do vencimento. */
    fun invoiceMonthKey(invoiceYear: Int?, invoiceMonth: Int?): String =
        "$invoiceYear-${invoiceMonth.toString().padStart(2, '0')}"

    /** Vencida so depois do dia do vencimento: no proprio dia ainda se paga em dia. */
    fun isPastDue(dueDateText: String?, todayText: String): Boolean =
        !dueDateText.isNullOrEmpty() && dueDateText < todayText

    /** "Nubank · venceu em 10/10/2026", ou a mais antiga quando sao varias. */
    fun overdueDetail(overdue: List<AttentionInvoice>): String =
        if (overdue.size == 1) {
            "${overdue[0].cardName} · venceu em ${formatDateBR(overdue[0].dueDate)}"
        } else {
            "${overdue.size} faturas · a mais antiga venceu em ${formatDateBR(overdue.firstOrNull()?.dueDate)}"
        }

    /**
     * Titulo e detalhe de um aviso (os cartoes do Inicio e o sino). O saldo da conta, e o que
     * falta (que o revela), passam por [privateMoney]: no modo privado e o que mascara.
     */
    fun attentionText(
        item: AttentionItem,
        privateMoney: (BigDecimal?) -> String = ::formatCurrency,
    ): AttentionText = when (item.kind) {
        INVOICE_OVERDUE -> AttentionText(
            title = "Fatura vencida: ${formatCurrency(item.total)}",
            detail = "${overdueDetail(item.invoices)} · ${item.itemCount} lançamento(s)",
        )
        INVOICE_PAYABLE -> AttentionText(
            title = "Fatura fechada: ${formatCurrency(item.total)}",
            detail = "O pagamento já está liberado.",
        )
        AUTOPAY_SHORTFALL -> AttentionText(
            title = "Débito automático sem saldo: faltam ${privateMoney(item.missing)}",
            detail = "${item.accountName} tem ${privateMoney(item.balance)} para ${formatCurrency(item.total)} " +
                "a debitar · o primeiro em ${formatDateBR(item.firstDue)}",
        )
        RECURRING -> AttentionText(
            title = "${item.count} ${if (item.count == 1) "recorrência vencida" else "recorrências vencidas"}",
            detail = "",
        )
        OVER_BUDGET -> AttentionText(
            title = "${item.categoryName} passou do orçamento",
            detail = "${formatCurrency(item.spent)} de ${formatCurrency(item.available)}",
        )
        else -> AttentionText("", "")
    }

    private val LINKS = mapOf(
        INVOICE_OVERDUE to AttentionLink("/lancamentos/cartoes", "Ver faturas"),
        INVOICE_PAYABLE to AttentionLink("/lancamentos/cartoes", "Ver faturas"),
        AUTOPAY_SHORTFALL to AttentionLink("/lancamentos/cartoes", "Ver faturas"),
        RECURRING to AttentionLink("/planejamento/recorrentes", "Ver recorrentes"),
        OVER_BUDGET to AttentionLink("/planejamento/orcamento", "Ver orçamento"),
    )

    /** Quantos tipos tem link (o ATTENTION_LINKS do JS). */
    val linkCount: Int get() = LINKS.size

    /** Para onde o aviso leva quando nao ha uma acao na propria tela; null = tipo desconhecido. */
    fun attentionLink(kind: String): AttentionLink? = LINKS[kind]

    /** O numero no sino: todos os avisos de agora; acima de 9, "9+"; sem aviso, "". */
    fun bellBadge(count: Int): String = when {
        count <= 0 -> ""
        count > 9 -> "9+"
        else -> count.toString()
    }

    fun bellLabel(count: Int): String =
        if (count > 0) "Precisa de atenção: $count ${if (count == 1) "aviso" else "avisos"}"
        else "Precisa de atenção: nenhum aviso"

    /** Os avisos que este aparelho nao dispensou (o Inicio); o sino mostra todos. */
    fun <T> undismissedItems(items: List<T>, dismissedKeys: List<String>, keyOf: (T) -> String): List<T> {
        val dismissed = dismissedKeys.toSet()
        return items.filter { keyOf(it) !in dismissed }
    }

    /** As chaves dispensadas com [keys] no fim (sem repetir), as [MAX_DISMISSED_KEYS] mais recentes. */
    fun addDismissed(dismissedKeys: List<String>, keys: List<String>): List<String> =
        (dismissedKeys.filter { it !in keys } + keys).takeLast(MAX_DISMISSED_KEYS)
}
