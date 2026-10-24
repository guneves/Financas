// Porte: mudou um, muda o outro, com um teste de cada lado.
// Par: as regras do Extrato da web — as inline de pages/lancamentos/Extrato.jsx (isEditableHere,
// isInvoicePayment, isInvestmentCash, canShare, originLabel, dayLabel, TypeBadge, amountText,
// groupByDay, os filtros), isInvestmentOutflow/isInvestmentInflow de lib/transactions.js e
// transactionEditForm/transactionEditPayload de lib/transactionEdit.js (transactionEdit.test.js).
// Aqui: ExtratoRulesTest.kt (os casos de transactionEdit.test.js, e novos para o que a web nao testa).
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.data.TransactionDto
import java.math.BigDecimal
import java.time.LocalDate
import java.time.temporal.ChronoUnit

/** Os filtros do extrato (o EMPTY_FILTERS da web); todo campo e texto, vazio = sem filtro. */
data class ExtratoFilters(
    val q: String = "",
    val from: String = "",
    val to: String = "",
    val type: String = "",
    val accountId: String = "",
    val categoryId: String = "",
    val minAmount: String = "",
    val maxAmount: String = "",
)

/** Um dia do extrato: as linhas e o total (entrou menos saiu). */
data class StatementDay(val date: String, val items: List<TransactionDto>, val total: BigDecimal)

/** O formulario de edicao (transactionEditForm). */
data class TransactionEditForm(
    val amount: String,
    val date: String,
    val categoryId: String,
    val description: String,
    val type: String,
    val accountId: String,
    val transferAccountId: String,
    val share: ShareForm,
)

object ExtratoRules {
    const val TRANSFER = "TRANSFER"
    const val INCOME = "INCOME"
    const val EXPENSE = "EXPENSE"

    val INVESTMENT_SOURCE_TYPES = listOf("INVESTMENT_TRANSACTION", "INVESTMENT_PROCEED")
    private val DERIVED_SOURCE_TYPES = listOf("INVESTMENT_TRANSACTION", "INVESTMENT_PROCEED", "CC_INVOICE_PAYMENT", "CC_AUTOPAY")
    private val INVOICE_PAYMENT_TYPES = listOf("CC_INVOICE_PAYMENT", "CC_AUTOPAY")

    /** Linhas criadas por outra tela (carteira, fatura) e pendentes da fila nao se editam aqui. */
    fun isEditableHere(row: TransactionDto): Boolean = !row.pending && row.sourceType !in DERIVED_SOURCE_TYPES

    /** O pagamento de uma fatura nao se edita, mas se desfaz (037). */
    fun isInvoicePayment(row: TransactionDto): Boolean = !row.pending && row.sourceType in INVOICE_PAYMENT_TYPES

    /** O aporte/resgate de uma operacao sai junto com ela (DELETE da operacao). */
    fun isInvestmentCash(row: TransactionDto): Boolean =
        !row.pending && row.sourceType == "INVESTMENT_TRANSACTION" && !row.sourceId.isNullOrEmpty()

    /** "De quem é?" so em despesa e receita comuns. */
    fun canShare(row: TransactionDto): Boolean = row.type != TRANSFER && row.sourceType !in INVESTMENT_SOURCE_TYPES

    // Investimento pela origem da linha (039), nunca pela categoria. A transferencia para a
    // Corretora continua uma transferencia no Extrato (a decisao do dono, como hoje na web).
    private fun isInvestmentRow(row: TransactionDto): Boolean = row.sourceType in INVESTMENT_SOURCE_TYPES

    fun isInvestmentOutflow(row: TransactionDto): Boolean = row.type == EXPENSE && isInvestmentRow(row)

    fun isInvestmentInflow(row: TransactionDto): Boolean = row.type == INCOME && isInvestmentRow(row)

    /** De onde veio uma linha que nao se edita aqui. */
    fun originLabel(row: TransactionDto): String = when {
        row.pending -> if (row.pendingStatus == "needs_attention") "Recusado pelo servidor" else "Pendente de envio"
        row.sourceType == "INVESTMENT_TRANSACTION" -> "Pela carteira"
        row.sourceType == "INVESTMENT_PROCEED" -> "Provento"
        row.sourceType == "CC_AUTOPAY" -> "Débito automático"
        else -> "Pela fatura"
    }

    /** A etiqueta so do que nao e receita nem despesa comum; null nas outras. */
    fun typeBadge(row: TransactionDto): String? = when {
        row.type == TRANSFER -> "Transferência"
        isInvestmentOutflow(row) -> "Investimento"
        isInvestmentInflow(row) -> "Resgate"
        else -> null
    }

    /** O sinal do valor na lista: transferencia sem sinal, receita +, o resto -. */
    fun amountSign(row: TransactionDto): Int = when (row.type) {
        TRANSFER -> 0
        INCOME -> 1
        else -> -1
    }

    /** A primeira linha da linha: a descricao, senao a categoria. */
    fun title(row: TransactionDto): String = row.description?.takeIf { it.isNotEmpty() } ?: row.category.orEmpty()

    private val WEEKDAYS = listOf("seg.", "ter.", "qua.", "qui.", "sex.", "sáb.", "dom.")
    private val MONTHS = listOf("jan.", "fev.", "mar.", "abr.", "mai.", "jun.", "jul.", "ago.", "set.", "out.", "nov.", "dez.")

    /**
     * "Hoje", "Ontem" ou "Ter., 22 de set." (o toLocaleDateString do pt-BR com a primeira letra
     * maiuscula, como o first-letter:uppercase da web); o ano so quando nao e o atual.
     */
    fun dayLabel(date: String?, today: LocalDate, relative: Boolean = true): String {
        if (date.isNullOrEmpty()) return "Sem data"
        val value = runCatching { LocalDate.parse(date.take(10)) }.getOrNull() ?: return "Sem data"
        // O extrato de investimentos nao diz "Hoje"/"Ontem" (ExtratoInvestimentos.jsx).
        if (relative) {
            when (ChronoUnit.DAYS.between(value, today)) {
                0L -> return "Hoje"
                1L -> return "Ontem"
            }
        }
        val text = buildString {
            append(WEEKDAYS[value.dayOfWeek.value - 1])
            append(", ").append(value.dayOfMonth).append(" de ").append(MONTHS[value.monthValue - 1])
            if (value.year != today.year) append(" de ").append(value.year)
        }
        return text.replaceFirstChar { it.uppercase() }
    }

    /**
     * Os dias na ordem da lista. O total de cada dia vem do servidor ([dayTotals], o dia inteiro,
     * de todas as paginas); um dia sem total do servidor (so pendentes da fila) soma as linhas.
     */
    fun groupByDay(rows: List<TransactionDto>, dayTotals: Map<String, BigDecimal>): List<StatementDay> {
        val groups = mutableListOf<Pair<String, MutableList<TransactionDto>>>()
        for (row in rows) {
            val date = row.date.orEmpty()
            val last = groups.lastOrNull()
            if (last == null || last.first != date) groups.add(date to mutableListOf(row)) else last.second.add(row)
        }
        return groups.map { (date, items) ->
            val total = dayTotals[date] ?: items.fold(BigDecimal.ZERO) { acc, row ->
                when (row.type) {
                    INCOME -> acc + row.amount
                    EXPENSE -> acc - row.amount
                    else -> acc
                }
            }
            StatementDay(date, items, total)
        }
    }

    // ---- Filtros ----

    /** Os parametros do GET, nas chaves e na ordem da web; valores em reais lidos como o campo. */
    fun filterParams(filters: ExtratoFilters): Map<String, String> {
        val params = linkedMapOf(
            "q" to filters.q.trim(),
            "from" to filters.from,
            "to" to filters.to,
            "type" to filters.type,
            "account_id" to filters.accountId,
            "category_id" to filters.categoryId,
            "min_amount" to amountParam(filters.minAmount),
            "max_amount" to amountParam(filters.maxAmount),
        )
        return params.filterValues { it.isNotBlank() }
    }

    // "45,90" -> "45.90"; um valor que nao se le vai como foi digitado (o servidor recusa e diz).
    private fun amountParam(text: String): String {
        val trimmed = text.trim()
        if (trimmed.isEmpty()) return ""
        return when (val parsed = br.financas.app.core.parseMoneyInput(trimmed)) {
            is br.financas.app.core.MoneyInput.Amount -> parsed.value.toPlainString()
            else -> trimmed
        }
    }

    fun hasActiveFilters(filters: ExtratoFilters): Boolean = filterParams(filters).isNotEmpty()

    /** Os filtros atras do botao "Filtros" (tudo menos a busca). */
    fun countHiddenFilters(filters: ExtratoFilters): Int = (filterParams(filters) - "q").size

    // ---- Editar ----

    fun transactionEditForm(row: TransactionDto): TransactionEditForm = TransactionEditForm(
        amount = br.financas.app.core.moneyInputValue(row.amount),
        date = row.date.orEmpty(),
        categoryId = row.categoryId.orEmpty(),
        description = row.description.orEmpty(),
        type = row.type,
        accountId = row.accountId.orEmpty(),
        transferAccountId = if (row.type == TRANSFER) row.transferAccountId.orEmpty() else "",
        share = Sharing.shareFormFrom(ShareItem(row.shareMode, row.sharePerson, row.shareOthersAmount)),
    )

    /**
     * O PATCH parcial (transactionEditPayload): valor, data e descricao sempre; as contas so
     * quando mudaram; tipo e categoria (pelo id, so quando mudou) fora de transferencia; a divisao
     * so quando mudou e a linha se divide ([sharing]).
     */
    fun transactionEditPayload(row: TransactionDto, form: TransactionEditForm, amount: BigDecimal, sharing: Boolean = false): Map<String, Any?> {
        val payload = linkedMapOf<String, Any?>(
            "amount" to amount,
            "date" to form.date,
            "description" to form.description,
        )
        if (form.accountId.isNotEmpty() && form.accountId != row.accountId.orEmpty()) payload["account_id"] = form.accountId
        if (row.type == TRANSFER) {
            if (form.transferAccountId.isNotEmpty() && form.transferAccountId != row.transferAccountId.orEmpty()) {
                payload["transfer_account_id"] = form.transferAccountId
            }
        } else {
            payload["type"] = form.type
            if (form.categoryId != row.categoryId.orEmpty()) payload["category_id"] = form.categoryId
        }
        val original = Sharing.shareFormFrom(ShareItem(row.shareMode, row.sharePerson, row.shareOthersAmount))
        if (sharing && form.share != original) payload.putAll(Sharing.sharePayload(form.share))
        return payload
    }

    // ---- Comprovantes (components/AttachmentsSheet.jsx) ----

    private val TYPE_LABELS = mapOf(
        "application/pdf" to "PDF",
        "image/jpeg" to "JPG",
        "image/png" to "PNG",
        "image/gif" to "GIF",
        "image/webp" to "WEBP",
        "image/heic" to "HEIC",
    )

    /** "512 B", "120 kB", "2,4 MB" (o formatSize da web). */
    fun fileSize(bytes: Long): String {
        if (bytes < 1024) return "$bytes B"
        if (bytes < 1024L * 1024) return "${BigDecimal(bytes).divide(BigDecimal(1024), 0, java.math.RoundingMode.HALF_UP)} kB"
        val mb = BigDecimal(bytes).divide(BigDecimal(1024L * 1024), 1, java.math.RoundingMode.HALF_UP)
        return "${mb.toPlainString().replace('.', ',')} MB"
    }

    /** A linha de baixo de um comprovante: o tipo e o tamanho ("PDF · 120 kB"). */
    fun attachmentDetail(contentType: String?, bytes: Long): String =
        "${TYPE_LABELS[contentType] ?: "Arquivo"} · ${fileSize(bytes)}"

    /** A descricao do sheet de um lancamento: "<descricao> · dd/mm/aaaa · ±R$ valor". */
    fun attachmentDescription(row: TransactionDto): String = listOf(
        title(row),
        br.financas.app.core.formatDateBR(row.date),
        br.financas.app.core.formatSignedCurrency(row.amount, amountSign(row)),
    ).joinToString(" · ")

    // ---- Cabecalho ----

    /**
     * As projecoes do servidor (sem a fila) com os pendentes do aparelho por cima: o mesmo que o
     * saldo em contas ganhou com eles ([viewBalance] - [serverBalance], de applyPendingToHome).
     */
    fun projectionWithPending(projection: BigDecimal, serverBalance: BigDecimal, viewBalance: BigDecimal): BigDecimal =
        projection + (viewBalance - serverBalance)
}
