package br.financas.app.data

import br.financas.app.rules.AttentionInvoice
import br.financas.app.rules.AttentionItem
import br.financas.app.rules.BlockedRecurring
import br.financas.app.rules.BudgetLine
import br.financas.app.rules.HomeMonth
import br.financas.app.rules.HomeSummary
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import java.math.BigDecimal

/** Um mes do `flow` de GET /api/home (services/home.py, monthly_flow), em reais. */
@Serializable
data class HomeMonthDto(
    val month: String,
    val income: Money = BigDecimal.ZERO,
    val expense: Money = BigDecimal.ZERO,
    val invested: Money = BigDecimal.ZERO,
    val redeemed: Money = BigDecimal.ZERO,
    @SerialName("others_paid") val othersPaid: Money = BigDecimal.ZERO,
    @SerialName("others_received") val othersReceived: Money = BigDecimal.ZERO,
    val net: Money = BigDecimal.ZERO,
    val balance: Money = BigDecimal.ZERO,
) {
    val rule: HomeMonth
        get() = HomeMonth(month, income, expense, invested, redeemed, othersPaid, othersReceived, net, balance)
}

/** O `summary` de GET /api/home: o mes atual do fluxo. */
@Serializable
data class HomeSummaryDto(
    val income: Money = BigDecimal.ZERO,
    val expense: Money = BigDecimal.ZERO,
    val result: Money = BigDecimal.ZERO,
    val invested: Money = BigDecimal.ZERO,
    val redeemed: Money = BigDecimal.ZERO,
    @SerialName("investment_net") val investmentNet: Money = BigDecimal.ZERO,
    @SerialName("others_paid") val othersPaid: Money = BigDecimal.ZERO,
    @SerialName("others_received") val othersReceived: Money = BigDecimal.ZERO,
    @SerialName("others_net") val othersNet: Money = BigDecimal.ZERO,
) {
    val rule: HomeSummary
        get() = HomeSummary(income, expense, result, invested, redeemed, investmentNet, othersPaid, othersReceived, othersNet)
}

/** A proxima fatura de um cartao (services/card_invoices.py, invoice_summary). */
@Serializable
data class NextInvoiceDto(
    @SerialName("card_id") val cardId: String,
    @SerialName("card_name") val cardName: String? = null,
    @SerialName("invoice_month") val invoiceMonth: Int,
    @SerialName("invoice_year") val invoiceYear: Int,
    @SerialName("due_date") val dueDate: String? = null,
    @SerialName("closing_date") val closingDate: String? = null,
    val closed: Flag = false,
    val payable: Flag = false,
    val total: Money = BigDecimal.ZERO,
    @SerialName("item_count") val itemCount: Int = 0,
)

/**
 * GET /api/home?months=12 (services/home.py, build_home): o saldo em contas (sem a Corretora),
 * todas as contas (arquivadas e Corretora inclusive, com balance_brl), o mes atual, os 12 meses
 * do fluxo e a proxima fatura de cada cartao.
 */
@Serializable
data class HomeDto(
    val today: String? = null,
    val month: String? = null,
    @SerialName("consolidated_balance") val consolidatedBalance: Money = BigDecimal.ZERO,
    val accounts: List<AccountDto> = emptyList(),
    val summary: HomeSummaryDto = HomeSummaryDto(),
    val flow: List<HomeMonthDto> = emptyList(),
    @SerialName("next_invoices") val nextInvoices: List<NextInvoiceDto> = emptyList(),
    @SerialName("next_invoices_total") val nextInvoicesTotal: Money = BigDecimal.ZERO,
    @SerialName("next_closing_date") val nextClosingDate: String? = null,
)

/** Uma fatura do aviso de fatura vencida (ou fechada). */
@Serializable
data class AttentionInvoiceDto(
    @SerialName("card_id") val cardId: String? = null,
    @SerialName("card_name") val cardName: String? = null,
    @SerialName("invoice_month") val invoiceMonth: Int? = null,
    @SerialName("invoice_year") val invoiceYear: Int? = null,
    @SerialName("due_date") val dueDate: String? = null,
    val total: Money? = null,
    val count: Int? = null,
) {
    val rule: AttentionInvoice
        get() = AttentionInvoice(cardId, cardName, invoiceMonth, invoiceYear, dueDate, total)
}

/**
 * Um aviso de GET /api/attention (services/attention.py): `key` nomeia o caso (a dispensa por
 * aparelho guarda essa chave, byte a byte), `kind` o tipo, `tone` a cor; o resto sao numeros.
 */
@Serializable
data class AttentionItemDto(
    val key: String,
    val kind: String,
    val tone: String = "",
    val total: Money? = null,
    @SerialName("item_count") val itemCount: Int? = null,
    val invoices: List<AttentionInvoiceDto> = emptyList(),
    @SerialName("account_id") val accountId: String? = null,
    @SerialName("account_name") val accountName: String? = null,
    @SerialName("first_due") val firstDue: String? = null,
    val balance: Money? = null,
    val missing: Money? = null,
    val count: Int? = null,
    @SerialName("category_name") val categoryName: String? = null,
    val spent: Money? = null,
    val available: Money? = null,
) {
    val rule: AttentionItem
        get() = AttentionItem(
            key = key,
            kind = kind,
            tone = tone,
            total = total,
            itemCount = itemCount,
            invoices = invoices.map { it.rule },
            accountName = accountName,
            balance = balance,
            missing = missing,
            firstDue = firstDue,
            count = count,
            categoryName = categoryName,
            spent = spent,
            available = available,
        )
}

@Serializable
data class AttentionDto(
    val today: String? = null,
    val items: List<AttentionItemDto> = emptyList(),
)

/** Uma categoria do orcamento do mes (services/budgets.py, serialize_budget). */
@Serializable
data class BudgetItemDto(
    val id: String,
    @SerialName("category_name") val categoryName: String? = null,
    @SerialName("parent_name") val parentName: String? = null,
    val spent: Money? = null,
    val available: Money? = null,
    val percent: Money? = null,
    val status: String = "OK",
) {
    val rule: BudgetLine
        get() = BudgetLine(id, categoryName, parentName, spent, available, percent, status)
}

@Serializable
data class BudgetTotalsDto(
    val available: Money? = null,
    val spent: Money? = null,
    val remaining: Money? = null,
)

/** GET /api/budgets?month=AAAA-MM: so o que a faixa "Orçamento do mês" le. */
@Serializable
data class BudgetMonthDto(
    val month: String? = null,
    val items: List<BudgetItemDto> = emptyList(),
    val totals: BudgetTotalsDto = BudgetTotalsDto(),
)

@Serializable
data class BlockedRecurringDto(
    val description: String? = null,
    @SerialName("account_name") val accountName: String? = null,
) {
    val rule: BlockedRecurring get() = BlockedRecurring(description, accountName)
}

/** A resposta de POST /api/recurring/run: quantos lancou e as que a conta arquivada bloqueou. */
@Serializable
data class RecurringRunDto(
    val created: Int = 0,
    val blocked: List<BlockedRecurringDto> = emptyList(),
)
