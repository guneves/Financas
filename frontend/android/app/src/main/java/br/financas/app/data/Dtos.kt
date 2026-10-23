package br.financas.app.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

/**
 * Uma conta de GET /api/accounts (backend/routes/accounts.py, serialize_account +
 * with_balance_in_brl). balance_brl e null quando a conta e em moeda estrangeira e nao ha
 * cambio hoje ("sem cambio hoje" na tela).
 */
@Serializable
data class AccountDto(
    val id: String,
    val name: String,
    /** CHECKING, SAVINGS, BROKERAGE (Corretora), CASH ou OTHER. */
    val type: String = "CHECKING",
    val institution: String? = null,
    @SerialName("initial_balance") val initialBalance: Money? = null,
    val currency: String = "BRL",
    @SerialName("is_default") val isDefault: Flag = false,
    @SerialName("archived_at") val archivedAt: String? = null,
    val metadata: JsonObject? = null,
    val balance: Money? = null,
    @SerialName("balance_brl") val balanceBrl: Money? = null,
    @SerialName("fx_rate") val fxRate: Money? = null,
    @SerialName("created_at") val createdAt: String? = null,
) {
    val isBrokerage: Boolean get() = type == TYPE_BROKERAGE
    val isArchived: Boolean get() = !archivedAt.isNullOrEmpty()

    companion object {
        const val TYPE_BROKERAGE = "BROKERAGE"
    }
}

/**
 * Uma categoria de GET /api/categories, na ordem do servidor (nome do pai, depois os filhos).
 * parent_name vem do JOIN; kind e INCOME, EXPENSE ou BOTH.
 */
@Serializable
data class CategoryDto(
    val id: String,
    val name: String,
    val kind: String = "EXPENSE",
    @SerialName("parent_id") val parentId: String? = null,
    @SerialName("parent_name") val parentName: String? = null,
    val color: String? = null,
    val icon: String? = null,
    @SerialName("archived_at") val archivedAt: String? = null,
) {
    val isArchived: Boolean get() = !archivedAt.isNullOrEmpty()
}

/**
 * Um cartao de GET /api/credit-cards (a linha de credit_cards). credit_enabled = 0 e um
 * cartao so de debito (041): due_day/closing_day dele (1) nunca sao lidos.
 */
@Serializable
data class CreditCardDto(
    val id: String,
    val name: String,
    @SerialName("due_day") val dueDay: Int? = null,
    @SerialName("closing_day") val closingDay: Int? = null,
    @SerialName("credit_enabled") val creditEnabled: Flag = true,
    @SerialName("debit_account_id") val debitAccountId: String? = null,
    @SerialName("autopay_account_id") val autopayAccountId: String? = null,
    @SerialName("autopay_start_date") val autopayStartDate: String? = null,
    @SerialName("archived_at") val archivedAt: String? = null,
) {
    val isArchived: Boolean get() = !archivedAt.isNullOrEmpty()
}
