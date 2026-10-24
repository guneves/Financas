package br.financas.app.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

/**
 * Um lancamento de GET /api/transactions (serialize_transaction, com attachment_count). So os
 * campos que o Extrato le (04-extrato.md, "Data").
 */
@Serializable
data class TransactionDto(
    val id: String,
    val type: String = "EXPENSE",
    val amount: Money = java.math.BigDecimal.ZERO,
    val date: String? = null,
    val description: String? = null,
    val category: String? = null,
    @SerialName("category_id") val categoryId: String? = null,
    @SerialName("account_id") val accountId: String? = null,
    @SerialName("transfer_account_id") val transferAccountId: String? = null,
    @SerialName("source_type") val sourceType: String? = null,
    @SerialName("source_id") val sourceId: String? = null,
    @SerialName("attachment_count") val attachmentCount: Int = 0,
    @SerialName("share_mode") val shareMode: String? = null,
    @SerialName("share_person") val sharePerson: String? = null,
    @SerialName("share_others_amount") val shareOthersAmount: Money? = null,
    @SerialName("created_at") val createdAt: String? = null,
    /** Linha da fila (nunca vem do servidor): "Pendente de envio" / "Recusado pelo servidor". */
    val pending: Boolean = false,
    @SerialName("pending_status") val pendingStatus: String? = null,
)

/** Os totais do filtro inteiro (services/transaction_pages.py, statement_totals). */
@Serializable
data class StatementTotalsDto(
    val income: Money = java.math.BigDecimal.ZERO,
    val expense: Money = java.math.BigDecimal.ZERO,
    val investment: Money = java.math.BigDecimal.ZERO,
)

/** Uma pagina de GET /api/transactions?limit=N (com cursor nas seguintes). */
@Serializable
data class TransactionPageDto(
    val items: List<TransactionDto> = emptyList(),
    @SerialName("next_cursor") val nextCursor: String? = null,
    val count: Int = 0,
    val totals: StatementTotalsDto = StatementTotalsDto(),
    @SerialName("day_totals") val dayTotals: Map<String, Money> = emptyMap(),
)

/** Um comprovante (GET .../attachments). */
@Serializable
data class AttachmentDto(
    val id: String,
    @SerialName("original_name") val originalName: String = "",
    @SerialName("content_type") val contentType: String? = null,
    @SerialName("size_bytes") val sizeBytes: Long = 0,
    @SerialName("created_at") val createdAt: String? = null,
)

/** Uma coluna da exportacao (GET /api/exports/columns). */
@Serializable
data class ExportColumnDto(val key: String, val label: String)

@Serializable
data class ExportColumnsDto(val transactions: List<ExportColumnDto> = emptyList())

/**
 * Uma movimentacao de GET /api/investments?order=created_at&ascending=false. metadata fica como
 * JSON: as datas e os precos dela sao lidos com tolerancia (rules/InvestmentStatement.kt).
 */
@Serializable
data class InvestmentMovementDto(
    val id: String,
    @SerialName("asset_class") val assetClass: String? = null,
    @SerialName("ticker_or_name") val tickerOrName: String? = null,
    val quantity: Money? = null,
    @SerialName("average_price") val averagePrice: Money? = null,
    @SerialName("current_price") val currentPrice: Money? = null,
    @SerialName("fee_amount") val feeAmount: Money? = null,
    @SerialName("realized_fee_amount") val realizedFeeAmount: Money? = null,
    @SerialName("realized_net_proceeds") val realizedNetProceeds: Money? = null,
    @SerialName("created_at") val createdAt: String? = null,
    val metadata: JsonObject? = null,
)

@Serializable
data class ProceedAssetDto(val ticker: String? = null, val name: String? = null)

/** Um provento de GET /api/investment-proceeds. */
@Serializable
data class InvestmentProceedDto(
    val id: String,
    @SerialName("proceeds_type") val proceedsType: String? = null,
    @SerialName("payment_date") val paymentDate: String? = null,
    @SerialName("net_amount") val netAmount: Money? = null,
    @SerialName("tax_amount") val taxAmount: Money? = null,
    @SerialName("eligible_quantity") val eligibleQuantity: Money? = null,
    @SerialName("amount_per_unit") val amountPerUnit: Money? = null,
    @SerialName("sync_key") val syncKey: String? = null,
    val asset: ProceedAssetDto? = null,
)
