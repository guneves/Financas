package br.financas.app.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Um item de Revisar (GET /api/review, services/review.py): o que a notificacao ou a Pluggy
 * gravou sozinha e espera o dono dizer "é meu" e a categoria. [table] e [id] voltam no POST.
 * Uma compra no cartao (cc_expenses) e uma linha so, com o total e as parcelas.
 */
@Serializable
data class ReviewItemDto(
    val table: String,
    val id: String,
    val date: String? = null,
    val amount: Money = java.math.BigDecimal.ZERO,
    /** EXPENSE, INCOME, TRANSFER (transactions) ou CARD, REFUND (cc_expenses). */
    val type: String = "EXPENSE",
    val description: String? = null,
    val category: String? = null,
    @SerialName("category_id") val categoryId: String? = null,
    @SerialName("account_name") val accountName: String? = null,
    @SerialName("transfer_account_name") val transferAccountName: String? = null,
    @SerialName("card_name") val cardName: String? = null,
    val installments: Int? = null,
    @SerialName("created_at") val createdAt: String? = null,
)

/** GET /api/review: a fila, quantos e quantos movimentos nao gravaram sozinhos (`waiting`). */
@Serializable
data class ReviewQueueDto(
    val items: List<ReviewItemDto> = emptyList(),
    val count: Int = 0,
    val waiting: Int = 0,
)

/** POST /api/review: quantos foram confirmados e quantos ainda esperam. */
@Serializable
data class ReviewConfirmedDto(val reviewed: Int = 0, val count: Int = 0)

/**
 * Uma compra no cartao do Extrato (GET /api/cc-expenses/statement, services/card_statement.py):
 * uma linha por compra (client_id), o total e as parcelas. Nao mexe em saldo de conta.
 */
@Serializable
data class CardStatementDto(
    val id: String,
    @SerialName("client_id") val clientId: String? = null,
    val date: String? = null,
    /** CARD (compra) ou REFUND (estorno). */
    val type: String = "CARD",
    val amount: Money = java.math.BigDecimal.ZERO,
    val installments: Int = 1,
    @SerialName("card_id") val cardId: String? = null,
    @SerialName("card_name") val cardName: String? = null,
    val category: String? = null,
    @SerialName("category_id") val categoryId: String? = null,
    val description: String? = null,
    @SerialName("needs_review") val needsReview: Flag = false,
    @SerialName("created_at") val createdAt: String? = null,
)
