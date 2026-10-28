package br.financas.app.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import java.math.BigDecimal

/** Uma compra (ou estorno) de uma fatura de GET /api/cc-invoices (serialize_purchase). */
@Serializable
data class InvoicePurchaseDto(
    val id: String,
    @SerialName("client_id") val clientId: String? = null,
    val kind: String = "PURCHASE",
    val description: String? = null,
    val category: String? = null,
    @SerialName("category_id") val categoryId: String? = null,
    @SerialName("purchase_date") val purchaseDate: String? = null,
    val amount: Money = BigDecimal.ZERO,
    @SerialName("installment_info") val installmentInfo: String? = null,
    @SerialName("installment_current") val installmentCurrent: Int = 1,
    @SerialName("installment_total") val installmentTotal: Int = 1,
    @SerialName("attachment_count") val attachmentCount: Int = 0,
    @SerialName("share_mode") val shareMode: String? = null,
    @SerialName("share_person") val sharePerson: String? = null,
    @SerialName("share_others_amount") val shareOthersAmount: Money? = null,
    @SerialName("installments_open") val installmentsOpen: Int = 0,
    @SerialName("installments_paid") val installmentsPaid: Int = 0,
) {
    val isRefund: Boolean get() = kind == "REFUND"
}

/** Uma fatura em aberto de um cartao, com as flags do servidor (services/card_invoices.py). */
@Serializable
data class CardInvoiceDto(
    @SerialName("invoice_month") val invoiceMonth: Int,
    @SerialName("invoice_year") val invoiceYear: Int,
    val key: String = "",
    @SerialName("closing_date") val closingDate: String? = null,
    @SerialName("due_date") val dueDate: String? = null,
    val closed: Boolean = false,
    @SerialName("past_due") val pastDue: Boolean = false,
    val payable: Boolean = false,
    val next: Boolean = false,
    val nearest: Boolean = false,
    val future: Boolean = false,
    val total: Money = BigDecimal.ZERO,
    @SerialName("item_count") val itemCount: Int = 0,
    val purchases: List<InvoicePurchaseDto> = emptyList(),
)

@Serializable
data class InvoiceCardDto(
    @SerialName("card_id") val cardId: String,
    @SerialName("card_name") val cardName: String = "",
    @SerialName("due_day") val dueDay: Int? = null,
    @SerialName("closing_day") val closingDay: Int? = null,
    @SerialName("autopay_account_id") val autopayAccountId: String? = null,
    @SerialName("credit_enabled") val creditEnabled: Boolean = true,
    val total: Money = BigDecimal.ZERO,
    val invoices: List<CardInvoiceDto> = emptyList(),
)

@Serializable
data class NearestInvoiceRefDto(
    @SerialName("card_id") val cardId: String,
    @SerialName("invoice_month") val invoiceMonth: Int,
    @SerialName("invoice_year") val invoiceYear: Int,
)

/** Uma compra no debito (049): uma despesa da conta do cartao, sem fatura. */
@Serializable
data class DebitPurchaseDto(
    val id: String,
    val date: String? = null,
    val description: String? = null,
    val category: String? = null,
    @SerialName("category_id") val categoryId: String? = null,
    val amount: Money = BigDecimal.ZERO,
    @SerialName("account_id") val accountId: String? = null,
    @SerialName("attachment_count") val attachmentCount: Int = 0,
    @SerialName("share_mode") val shareMode: String? = null,
    @SerialName("share_person") val sharePerson: String? = null,
    @SerialName("share_others_amount") val shareOthersAmount: Money? = null,
)

/** As compras no debito de um cartao (services/debit_purchases.py), da mais nova para a mais antiga. */
@Serializable
data class DebitCardDto(
    @SerialName("card_id") val cardId: String,
    @SerialName("card_name") val cardName: String = "",
    @SerialName("credit_enabled") val creditEnabled: Boolean = true,
    @SerialName("account_id") val accountId: String? = null,
    @SerialName("account_name") val accountName: String? = null,
    @SerialName("month_total") val monthTotal: Money = BigDecimal.ZERO,
    val purchases: List<DebitPurchaseDto> = emptyList(),
)

/** GET /api/cc-invoices: os cartoes (por nome) com as faturas em aberto e as compras no debito. */
@Serializable
data class CcInvoicesDto(
    val today: String? = null,
    val nearest: NearestInvoiceRefDto? = null,
    @SerialName("open_total") val openTotal: Money = BigDecimal.ZERO,
    val cards: List<InvoiceCardDto> = emptyList(),
    @SerialName("debit_cards") val debitCards: List<DebitCardDto> = emptyList(),
)

/** Uma parcela de GET /api/cc-expenses/candidates?id= (todas as da compra, pagas inclusive). */
@Serializable
data class PurchaseInstallmentDto(
    val id: String,
    val amount: Money = BigDecimal.ZERO,
    @SerialName("installment_info") val installmentInfo: String? = null,
    val status: String? = null,
    @SerialName("share_mode") val shareMode: String? = null,
    @SerialName("share_person") val sharePerson: String? = null,
    @SerialName("share_others_amount") val shareOthersAmount: Money? = null,
)

/** A resposta de POST /api/cc-expenses/refunds: a fatura em que o estorno entrou. */
@Serializable
data class RefundCreatedDto(
    val id: String? = null,
    @SerialName("invoice_month") val invoiceMonth: Int? = null,
    @SerialName("invoice_year") val invoiceYear: Int? = null,
)
