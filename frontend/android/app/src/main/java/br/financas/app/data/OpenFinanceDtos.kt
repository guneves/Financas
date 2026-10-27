package br.financas.app.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** GET /api/open-finance (043): as conexoes com o estado e o saldo do banco ao lado do do app. */
@Serializable
data class OpenFinanceDto(
    val configured: Boolean = false,
    @SerialName("first_sync_days") val firstSyncDays: Int? = null,
    val items: List<OpenFinanceItemDto> = emptyList(),
    /** So na resposta do "Atualizar" (POST .../sync). */
    val result: OpenFinanceSyncResultDto? = null,
)

@Serializable
data class OpenFinanceItemDto(
    val id: String = "",
    @SerialName("connector_name") val connectorName: String? = null,
    val status: String? = null,
    @SerialName("execution_status") val executionStatus: String? = null,
    @SerialName("error_message") val errorMessage: String? = null,
    @SerialName("needs_owner") val needsOwner: Boolean = false,
    @SerialName("last_sync_at") val lastSyncAt: String? = null,
    @SerialName("last_sync_error") val lastSyncError: String? = null,
    val accounts: List<OpenFinanceAccountDto> = emptyList(),
)

@Serializable
data class OpenFinanceAccountDto(
    val id: String = "",
    val type: String? = null,
    val name: String? = null,
    val number: String? = null,
    @SerialName("pluggy_balance") val pluggyBalance: Money? = null,
    @SerialName("app_balance") val appBalance: Money? = null,
    @SerialName("target_name") val targetName: String? = null,
    @SerialName("account_id") val accountId: String? = null,
    @SerialName("card_id") val cardId: String? = null,
    @SerialName("unmapped_count") val unmappedCount: Int = 0,
    /** A conferencia (services/open_finance_check.py): null sem mapeamento ou sem busca. */
    val check: OpenFinanceCheckDto? = null,
)

@Serializable
data class OpenFinanceCheckDto(
    val from: String? = null,
    @SerialName("bank_only") val bankOnly: List<OpenFinanceCheckRowDto> = emptyList(),
    @SerialName("app_only") val appOnly: List<OpenFinanceCheckRowDto> = emptyList(),
    @SerialName("bank_only_count") val bankOnlyCount: Int = 0,
    @SerialName("app_only_count") val appOnlyCount: Int = 0,
    @SerialName("awaiting_count") val awaitingCount: Int = 0,
)

@Serializable
data class OpenFinanceCheckRowDto(
    val date: String = "",
    val amount: Money? = null,
    val description: String? = null,
)

/** GET/PATCH /api/open-finance/settings: no servidor, o celular e o computador concordam. */
@Serializable
data class OpenFinanceSettingsDto(
    @SerialName("first_sync_days") val firstSyncDays: Int = 30,
    @SerialName("sync_hours") val syncHours: Int = 6,
    @SerialName("include_pending") val includePending: Boolean = false,
    @SerialName("auto_sync_available") val autoSyncAvailable: Boolean = true,
)

@Serializable
data class OpenFinanceSyncResultDto(
    val status: String? = null,
    val counts: Map<String, Int> = emptyMap(),
    val removed: Int = 0,
)
