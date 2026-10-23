// Port: mudou um, muda o outro, com um teste de cada lado.
// O que o Inicio (pages/Dashboard.jsx) decide no cliente e nao e o fluxo (rules/HomeFlow.kt) nem
// os avisos (rules/AttentionRules.kt):
// - blockedRecurringMessage: frontend/src/lib/transactions.js (transactions.test.js);
// - budgetStatus: components/BudgetProgress.jsx, a regra de budget_status() do servidor
//   (services/budgets.py) para o total do mes — aqui em decimal exato, como no servidor;
// - os textos do Dashboard.jsx que dependem de numero (faturas, orcamento, pagamento, recorrentes).
// Testes: HomeRulesTest.kt. Puro: nada de Android nem de Compose.
package br.financas.app.rules

import br.financas.app.core.formatCurrency
import br.financas.app.core.monthLabel
import java.math.BigDecimal
import java.math.RoundingMode

/** Uma recorrencia que /api/recurring/run nao lancou (conta arquivada). */
data class BlockedRecurring(val description: String?, val accountName: String?)

/** Uma categoria da faixa "Orçamento do mês" (GET /api/budgets?month=, `items`). */
data class BudgetLine(
    val id: String,
    val categoryName: String?,
    val parentName: String?,
    val spent: BigDecimal?,
    val available: BigDecimal?,
    val percent: BigDecimal?,
    val status: String,
)

object HomeRules {
    const val OK = "OK"
    const val WARNING = "WARNING"
    const val OVER = "OVER"
    const val NEEDS_INCOME = "NEEDS_INCOME"

    /** Quantas categorias "perto do limite ou acima" a faixa mostra. */
    const val BUDGET_FLAGGED_SHOWN = 4

    private val WARNING_PERCENT = BigDecimal(80)
    private val HUNDRED = BigDecimal(100)

    /** O aviso de /api/recurring/run com `blocked` (transactions.js); "" sem nenhuma. */
    fun blockedRecurringMessage(blocked: List<BlockedRecurring>): String {
        if (blocked.isEmpty()) return ""
        val names = blocked.joinToString(", ") {
            "\"${it.description?.takeIf { text -> text.isNotEmpty() } ?: "Sem descrição"}\" (${it.accountName})"
        }
        return if (blocked.size == 1) {
            "A recorrência $names está numa conta arquivada e não foi lançada. Edite a recorrência e escolha outra conta."
        } else {
            "${blocked.size} recorrências estão em contas arquivadas e não foram lançadas: $names. Edite cada uma e escolha outra conta."
        }
    }

    /**
     * O status do total do mes: estourou quando o gasto passa do disponivel; perto do limite a
     * partir de 80% (percentual arredondado a centesimos, HALF_UP, como o servidor).
     */
    fun budgetStatus(spent: BigDecimal?, available: BigDecimal?): String {
        val used = spent ?: BigDecimal.ZERO
        val total = available ?: BigDecimal.ZERO
        if (used > total) return OVER
        if (total.signum() <= 0) return OK
        val percent = used.multiply(HUNDRED).divide(total, 2, RoundingMode.HALF_UP)
        return if (percent >= WARNING_PERCENT) WARNING else OK
    }

    /** As categorias que pedem atencao: estouradas primeiro, depois as perto, do maior %. */
    fun budgetFlagged(items: List<BudgetLine>): List<BudgetLine> {
        val rank = mapOf(OVER to 0, WARNING to 1)
        return items
            .filter { it.status == OVER || it.status == WARNING }
            .sortedWith(
                compareBy<BudgetLine> { rank[it.status] ?: 2 }
                    .thenByDescending { it.percent ?: BigDecimal.ZERO },
            )
    }

    /** "Pai › Categoria", ou so o nome sem pai. */
    fun budgetCategoryName(line: BudgetLine): String =
        if (!line.parentName.isNullOrEmpty()) "${line.parentName} › ${line.categoryName}" else line.categoryName.orEmpty()

    /** "Restam R$ X" ou, passado do planejado, "Passou R$ X do planejado". */
    fun budgetRemainingText(remaining: BigDecimal?): String {
        val value = remaining ?: BigDecimal.ZERO
        return if (value.signum() < 0) "Passou ${formatCurrency(value.negate())} do planejado" else "Restam ${formatCurrency(value)}"
    }

    fun budgetMoreFlagged(extra: Int): String = "+$extra categoria(s) perto do limite ou acima"

    fun budgetAllOk(count: Int): String =
        if (count == 1) "A categoria com orçamento está no plano." else "As $count categorias com orçamento estão no plano."

    /** A barra: o % de 0 a 100. */
    fun barFraction(percent: BigDecimal?): Float {
        val value = (percent ?: BigDecimal.ZERO).max(BigDecimal.ZERO).min(HUNDRED)
        return value.divide(HUNDRED, 4, RoundingMode.HALF_UP).toFloat()
    }

    /** O % do total da faixa (gasto / disponivel); 0 sem disponivel. */
    fun budgetPercent(spent: BigDecimal?, available: BigDecimal?): BigDecimal {
        val total = available ?: BigDecimal.ZERO
        if (total.signum() <= 0) return BigDecimal.ZERO
        return (spent ?: BigDecimal.ZERO).multiply(HUNDRED).divide(total, 4, RoundingMode.HALF_UP)
    }

    /** "setembro de 2026" -> "Setembro de 2026". */
    fun sentenceCase(text: String): String =
        if (text.isEmpty()) text else text.substring(0, 1).uppercase() + text.substring(1)

    /** O aviso "Saldo estimado" com os lancamentos guardados no aparelho. */
    fun estimateText(count: Int): String =
        if (count == 1) {
            "Saldo estimado: 1 lançamento guardado neste aparelho ainda não chegou ao servidor."
        } else {
            "Saldo estimado: $count lançamentos guardados neste aparelho ainda não chegaram ao servidor."
        }

    /** O rotulo do quadro da proxima fatura, pelos meses das proximas faturas (AAAA-MM). */
    fun nextInvoiceLabel(months: List<String>): String = when {
        months.size == 1 -> "Fatura de ${monthLabel(months[0])}"
        months.size > 1 -> "Próximas faturas"
        else -> "Próxima fatura"
    }

    fun payableTitle(count: Int): String = if (count == 1) "Pagar fatura" else "Pagar faturas"

    fun payableDescription(count: Int): String =
        if (count == 1) "A fatura fechada que vence a seguir." else "$count faturas fechadas, a próxima de cada cartão."

    fun overdueTitle(count: Int): String = if (count == 1) "Pagar fatura vencida" else "Pagar $count faturas vencidas"

    /** O toast depois de pagar: "Fatura paga — R$ X debitado." */
    fun paidNotice(count: Int, total: BigDecimal?): String =
        "${if (count == 1) "Fatura paga" else "$count faturas pagas"} — ${formatCurrency(total)} debitado."

    /** O toast de "Lançar"; [created] 0 e o "nada pendente" (tom info). */
    fun recurringNotice(created: Int): String =
        if (created > 0) "$created lançamento(s) recorrente(s) gerado(s)."
        else "Nada pendente: todos os lançamentos recorrentes já estão em dia."

    /** O selo do quadro da fatura: a data do fechamento como dd/mm. */
    fun closingDayMonth(date: String?): String = br.financas.app.core.formatDateBR(date).take(5)
}
