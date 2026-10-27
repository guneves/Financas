package br.financas.app.data

import br.financas.app.rules.ApproveReadyResult
import br.financas.app.rules.ApproveReadySkip
import br.financas.app.rules.InboxHint
import br.financas.app.rules.InboxItem
import br.financas.app.rules.InboxRecurring
import br.financas.app.rules.InboxSource
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

/**
 * Uma fonte do item (`sources[]` de serialize_item, backend/services/inbox.py): a notificacao
 * lida no celular, so os campos (nunca o texto). [date] e o de uma fonte que nao e notificacao.
 */
@Serializable
data class InboxSourceDto(
    val source: String? = null,
    val id: String? = null,
    val role: String? = null,
    val app: String? = null,
    @SerialName("app_label") val appLabel: String? = null,
    val kind: String? = null,
    val amount: Money? = null,
    @SerialName("occurred_at") val occurredAt: String? = null,
    val date: String? = null,
    @SerialName("card_last4") val cardLast4: String? = null,
    @SerialName("card_name") val cardName: String? = null,
    val counterparty: String? = null,
    @SerialName("counterparty_bank") val counterpartyBank: String? = null,
    // Open Finance (043).
    @SerialName("connector_name") val connectorName: String? = null,
    @SerialName("bank_name") val bankName: String? = null,
    @SerialName("account_name") val accountName: String? = null,
    val description: String? = null,
    @SerialName("installment_number") val installmentNumber: Int? = null,
    @SerialName("total_installments") val totalInstallments: Int? = null,
) {
    /** O que as regras (rules/InboxRules.kt) leem. */
    val rule: InboxSource
        get() = InboxSource(
            source = source,
            id = id,
            role = role,
            app = app,
            appLabel = appLabel,
            kind = kind,
            occurredAt = occurredAt,
            cardLast4 = cardLast4,
            cardName = cardName,
            counterparty = counterparty,
            connectorName = connectorName,
            bankName = bankName,
            accountName = accountName,
            description = description,
            installmentNumber = installmentNumber,
            totalInstallments = totalInstallments,
        )
}

/** A ocorrencia de recorrencia que aprovar da como feita (034), `item.recurring`. */
@Serializable
data class InboxRecurringDto(
    @SerialName("recurring_id") val recurringId: String? = null,
    val date: String? = null,
    val description: String? = null,
    val category: String? = null,
    @SerialName("category_id") val categoryId: String? = null,
    val amount: Money? = null,
    val type: String? = null,
    val frequency: String? = null,
    /** So `false` diz "valor diferente do previsto"; ausente nao diz nada. */
    @SerialName("exact_amount") val exactAmount: Boolean? = null,
    val settled: Flag = false,
) {
    val rule: InboxRecurring
        get() = InboxRecurring(
            description = description,
            category = category,
            date = date,
            amount = amount,
            exactAmount = exactAmount,
            settled = settled,
        )
}

/** Um lancamento parecido ja gravado (candidate_details): "É este" aponta para ele. */
@Serializable
data class InboxCandidateDto(
    /** transactions ou cc_expenses: vai de volta no approve ({table, id}). */
    val table: String? = null,
    val id: String? = null,
    val kind: String? = null,
    val date: String? = null,
    val amount: Money? = null,
    val description: String? = null,
    val category: String? = null,
    @SerialName("installment_info") val installmentInfo: String? = null,
    @SerialName("card_name") val cardName: String? = null,
    @SerialName("account_name") val accountName: String? = null,
    @SerialName("transfer_account_name") val transferAccountName: String? = null,
)

/** O lancamento que um item decidido virou (so a data: "lançado em dd/mm/aaaa"). */
@Serializable
data class InboxTargetDto(
    val table: String? = null,
    val id: String? = null,
    val date: String? = null,
)

/**
 * Um item de Aprovar (serialize_item). [version] vai em toda decisao: com a velha, 409. Os itens
 * decididos trazem [target].
 */
@Serializable
data class InboxItemDto(
    val id: String,
    val version: Int? = null,
    val state: String? = null,
    val reason: String? = null,
    @SerialName("entry_type") val entryType: String? = null,
    val direction: String? = null,
    val amount: Money? = null,
    val currency: String? = null,
    val installments: Int? = null,
    @SerialName("occurred_at") val occurredAt: String? = null,
    @SerialName("source_occurred_at") val sourceOccurredAt: String? = null,
    val description: String? = null,
    val category: String? = null,
    @SerialName("category_id") val categoryId: String? = null,
    @SerialName("account_id") val accountId: String? = null,
    @SerialName("account_name") val accountName: String? = null,
    @SerialName("card_id") val cardId: String? = null,
    @SerialName("card_name") val cardName: String? = null,
    @SerialName("transfer_account_id") val transferAccountId: String? = null,
    @SerialName("transfer_account_name") val transferAccountName: String? = null,
    val needs: List<String> = emptyList(),
    val confirm: List<String> = emptyList(),
    val edited: List<JsonElement> = emptyList(),
    val ready: Flag = false,
    val ambiguous: Flag = false,
    val recurring: InboxRecurringDto? = null,
    @SerialName("recurring_off") val recurringOff: Flag = false,
    val candidates: List<InboxCandidateDto> = emptyList(),
    val sources: List<InboxSourceDto> = emptyList(),
    val target: InboxTargetDto? = null,
) {
    /** O que as regras (rules/InboxRules.kt) leem. */
    val rule: InboxItem
        get() = InboxItem(
            id = id,
            version = version,
            state = state,
            reason = reason,
            entryType = entryType,
            direction = direction,
            amount = amount,
            occurredAt = occurredAt,
            description = description,
            category = category,
            categoryId = categoryId,
            accountId = accountId,
            accountName = accountName,
            cardId = cardId,
            cardName = cardName,
            transferAccountId = transferAccountId,
            transferAccountName = transferAccountName,
            installments = installments,
            needs = needs,
            confirm = confirm,
            ready = ready,
            ambiguous = ambiguous,
            recurring = recurring?.rule,
            recurringOff = recurringOff,
            sources = sources.map { it.rule },
        )

    val isPending: Boolean get() = state == STATE_PENDING

    companion object {
        const val STATE_PENDING = "PENDING"
        const val STATE_DENIED = "DENIED"
    }
}

/** GET /api/inbox?view=pending|decided. */
@Serializable
data class InboxListDto(
    val items: List<InboxItemDto> = emptyList(),
    @SerialName("pending_count") val pendingCount: Int = 0,
)

/** GET /api/inbox/count, e o pending_count que toda decisao devolve junto do item. */
@Serializable
data class InboxCountDto(@SerialName("pending_count") val pendingCount: Int? = null)

/** POST /api/inbox/<id>/split: o item que ficou e o novo. */
@Serializable
data class InboxSplitDto(
    val item: InboxItemDto,
    @SerialName("new_item") val newItem: InboxItemDto? = null,
    @SerialName("pending_count") val pendingCount: Int? = null,
)

@Serializable
data class ApproveReadySkipDto(val id: String? = null, val reason: String? = null, val error: String? = null)

/** POST /api/inbox/approve-ready. */
@Serializable
data class ApproveReadyDto(
    val approved: List<String> = emptyList(),
    val skipped: List<ApproveReadySkipDto> = emptyList(),
    @SerialName("pending_count") val pendingCount: Int? = null,
) {
    val rule: ApproveReadyResult
        get() = ApproveReadyResult(approved = approved, skipped = skipped.map { ApproveReadySkip(it.id, it.reason, it.error) })
}

/** Uma escolha lembrada (GET /api/inbox/hints). */
@Serializable
data class InboxHintDto(
    val id: String,
    @SerialName("hint_key") val hintKey: String? = null,
    val label: String? = null,
    @SerialName("entry_type") val entryType: String? = null,
    @SerialName("account_id") val accountId: String? = null,
    @SerialName("card_id") val cardId: String? = null,
    @SerialName("transfer_account_id") val transferAccountId: String? = null,
    val uses: Int = 0,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("account_name") val accountName: String? = null,
    @SerialName("card_name") val cardName: String? = null,
    @SerialName("transfer_account_name") val transferAccountName: String? = null,
) {
    val rule: InboxHint
        get() = InboxHint(
            hintKey = hintKey,
            label = label,
            entryType = entryType,
            accountName = accountName,
            cardName = cardName,
            transferAccountName = transferAccountName,
        )
}

/** GET/PATCH /api/inbox/settings: "Sempre perguntar a conta/cartão". */
@Serializable
data class InboxSettingsDto(@SerialName("always_ask") val alwaysAsk: Flag = false)
