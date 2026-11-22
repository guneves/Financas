// Porte: mudou um, muda o outro, com um teste de cada lado.
// Par: frontend/src/lib/review.js (review.test.js): as compras no cartao na linha do tempo do
// Extrato (a confirmacao e automatica desde 2026-11-22: sem "É meu" nem "É repasse"). Aqui: ReviewRulesTest.kt (os
// casos de review.test.js, e os do que so o celular tem: o que nao gravou sozinho se resolve aqui,
// sem a tela Aprovar).
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.data.AccountDto
import br.financas.app.data.CardStatementDto
import br.financas.app.data.InboxItemDto
import br.financas.app.data.TransactionDto
import java.math.BigDecimal

object ReviewRules {
    const val CARD_KIND = "card"
    const val TABLE_CARD = "cc_expenses"

    /** O link antigo da web para o Revisar (a pilula saiu, dono 2026-11-22): abre o Extrato. */
    const val REVIEW_PATH = "/lancamentos/extrato?review=1"

    // ---- As compras no cartao no Extrato ----

    /** Uma compra (GET /api/cc-expenses/statement) no formato de uma linha do extrato. */
    fun cardStatementRow(purchase: CardStatementDto): TransactionDto = TransactionDto(
        id = purchase.id,
        type = purchase.type,
        amount = purchase.amount,
        date = purchase.date,
        description = purchase.description,
        category = purchase.category,
        categoryId = purchase.categoryId,
        createdAt = purchase.createdAt,
        needsReview = purchase.needsReview,
        twin = purchase.twin,
        kind = CARD_KIND,
        clientId = purchase.clientId,
        cardName = purchase.cardName,
        installments = purchase.installments,
    )

    fun isCardRow(row: TransactionDto?): Boolean = row?.kind == CARD_KIND

    /** A chave da linha na lista: a do lancamento, ou a da compra (nunca colide). */
    fun statementKey(row: TransactionDto): String =
        if (isCardRow(row)) "card:${row.clientId?.takeIf { it.isNotEmpty() } ?: row.id}" else row.id

    /** A compra sai (-1), o estorno volta (+1). Nao mexe em saldo de conta. */
    fun cardAmountSign(row: TransactionDto): Int = if (row.type == "REFUND") 1 else -1

    /** A etiqueta da compra: "Cartão" ou "Estorno", com " · 4x" quando parcelada. */
    fun cardTag(row: TransactionDto): String {
        val parts = row.installments?.takeIf { it > 1 }?.let { " · ${it}x" }.orEmpty()
        return (if (row.type == "REFUND") "Estorno" else "Cartão") + parts
    }

    /**
     * Os lancamentos e as compras numa lista so, do mais novo para o mais antigo (a data; no mesmo
     * dia, o gravado por ultimo primeiro). [until]: com o extrato paginado, so as compras ate a data
     * mais antiga ja carregada. Sem compras, a mesma lista.
     */
    fun mergeStatement(transactions: List<TransactionDto>, purchases: List<CardStatementDto>?, until: String = ""): List<TransactionDto> {
        val cards = purchases.orEmpty()
            .filter { until.isEmpty() || it.date.orEmpty() >= until }
            .map(::cardStatementRow)
        if (cards.isEmpty()) return transactions
        // sortedWith e estavel: empate fica na ordem de chegada, como o sort do JS.
        return (transactions + cards).sortedWith { a, b ->
            val byDate = b.date.orEmpty().compareTo(a.date.orEmpty())
            if (byDate != 0) byDate else b.createdAt.orEmpty().compareTo(a.createdAt.orEmpty())
        }
    }

    /** A data mais antiga de uma lista ja ordenada (a ultima), ou "" se vazia. */
    fun oldestDate(rows: List<TransactionDto>): String = rows.lastOrNull()?.date.orEmpty()

    /** O [until] do merge: paginado (ainda ha mais), a data mais antiga carregada; senao, tudo. */
    fun statementUntil(rows: List<TransactionDto>, hasMore: Boolean): String = if (hasMore) oldestDate(rows) else ""

    fun waitingNoticeText(count: Int): String = when {
        count <= 0 -> ""
        count == 1 -> "1 movimento a Pluggy atualizou e não identificou (outra moeda ainda sem a cotação do dia)."
        else -> "$count movimentos a Pluggy atualizou e não identificou (outra moeda ainda sem a cotação do dia)."
    }

    // ---- O que nao gravou sozinho (sem a tela Aprovar: resolve-se aqui) ----

    /** O que o dono resolve num item que espera: a conta que falta, o valor em reais, ou nada. */
    enum class WaitingFix { ACCOUNT, TRANSFER_ACCOUNT, AMOUNT, NONE }

    /**
     * O que falta no item, na ordem em que a tela pergunta: a outra ponta da transferencia (a
     * conta de origem ou a de destino), o valor em reais (outra moeda). Um item que espera outra
     * coisa (com Gravar sozinho desligado: cartao, credito ou debito) nao se resolve no celular.
     */
    fun waitingFixes(item: InboxItemDto): List<WaitingFix> {
        val fixes = mutableListOf<WaitingFix>()
        if ("account" in item.needs) fixes += WaitingFix.ACCOUNT
        if ("transfer_account" in item.needs) fixes += WaitingFix.TRANSFER_ACCOUNT
        if ("amount" in item.needs) fixes += WaitingFix.AMOUNT
        return fixes
    }

    /** Falta algo que o celular nao pergunta (cartao, credito ou debito). */
    fun waitingNeedsComputer(item: InboxItemDto): Boolean =
        item.needs.any { it !in setOf("account", "transfer_account", "amount") }

    /** Uma transferencia com uma ponta so pode virar despesa (saiu) ou receita (entrou). */
    fun waitingCanBeSingle(item: InboxItemDto): Boolean =
        item.entryType == "TRANSFER" && (item.accountId != null || item.transferAccountId != null) && !waitingNeedsComputer(item)

    /**
     * O tipo que "Não é entre minhas contas" grava: a ponta que o banco viu decide. Uma transferencia
     * e guardada como saida (OUT) mesmo quando so o destino e conhecido: um salario por TED e receita.
     */
    fun singleType(item: InboxItemDto): String =
        if (item.direction == "IN" || (item.entryType == "TRANSFER" && item.accountId == null && item.transferAccountId != null)) "INCOME" else "EXPENSE"

    fun waitingTitle(item: InboxItemDto): String =
        item.description?.takeIf { it.isNotEmpty() } ?: InboxRules.entryTypeLabel(item.entryType)

    /** "17/10/2026 às 22:30 · Itaú → ?" : quando e de onde. */
    fun waitingLine(item: InboxItemDto): String {
        val whenText = InboxRules.whenText(item.occurredAt)
        val place = when {
            item.entryType == "TRANSFER" -> "${item.accountName ?: "?"} → ${item.transferAccountName ?: "?"}"
            item.cardName != null -> item.cardName
            else -> item.accountName.orEmpty()
        }
        return listOf(whenText, place).filter { it.isNotEmpty() }.joinToString(" · ")
    }

    /** Por que espera, em uma frase (o primeiro need; sem need, o motivo do item). */
    fun waitingReason(item: InboxItemDto): String =
        item.needs.firstOrNull()?.let(InboxRules::needText) ?: InboxRules.reasonText(item.rule).ifEmpty { "Espera você decidir." }

    /**
     * POST /api/inbox/<id>/approve com o que o dono escolheu ({version, remember: false, account_id
     * / transfer_account_id, amount, transfer_amount}). Nada lembrado: como o gravar sozinho.
     */
    fun waitingApproveBody(
        item: InboxItemDto,
        accountId: String?,
        transferAccountId: String?,
        amount: BigDecimal?,
        transferAmount: BigDecimal? = null,
    ): Map<String, Any?> {
        val body = linkedMapOf<String, Any?>()
        if (item.version != null) body["version"] = item.version
        body["remember"] = false
        if (!accountId.isNullOrEmpty()) body["account_id"] = accountId
        if (!transferAccountId.isNullOrEmpty()) body["transfer_account_id"] = transferAccountId
        if (amount != null) body["amount"] = amount
        if (transferAmount != null) body["transfer_amount"] = transferAmount
        return body
    }

    /**
     * A moeda do destino quando a transferencia e entre moedas (o Pix de reais para a conta global,
     * 047) e o item ainda nao sabe quanto entrou nele (`transfer_amount`): o servidor recusa sem
     * isso. As contas sao as escolhidas, senao as do item; sem saber a moeda de uma delas, null.
     */
    fun waitingTransferCurrency(item: InboxItemDto, accounts: List<AccountDto>, accountId: String?, transferAccountId: String?): String? {
        if (item.entryType != "TRANSFER" || item.transferAmount != null) return null
        val origin = accounts.firstOrNull { it.id == (accountId?.takeIf { id -> id.isNotEmpty() } ?: item.accountId) } ?: return null
        val destination = accounts.firstOrNull { it.id == (transferAccountId?.takeIf { id -> id.isNotEmpty() } ?: item.transferAccountId) } ?: return null
        val to = GlobalAccount.currencyOf(destination)
        return if (GlobalAccount.currencyOf(origin) == to) null else to
    }

    /** "Não é entre minhas contas": grava como despesa ou receita na conta que avisou. */
    fun waitingSingleBody(item: InboxItemDto): Map<String, Any?> {
        val body = linkedMapOf<String, Any?>()
        if (item.version != null) body["version"] = item.version
        body["remember"] = false
        body["entry_type"] = singleType(item)
        return body
    }

    /** As contas da outra ponta: as ativas, menos a que ja esta no item (origem e destino diferem). */
    fun waitingAccountOptions(accounts: List<AccountDto>, item: InboxItemDto): List<AccountDto> =
        accounts.filter { !it.isArchived && it.id != item.accountId && it.id != item.transferAccountId }

    /** O que falta escolher antes de gravar (o botao fica apagado): "" quando esta tudo. */
    fun waitingMissing(
        item: InboxItemDto,
        accountId: String?,
        transferAccountId: String?,
        amount: BigDecimal?,
        transferCurrency: String? = null,
        transferAmount: BigDecimal? = null,
    ): String {
        val fixes = waitingFixes(item)
        if (WaitingFix.ACCOUNT in fixes && accountId.isNullOrEmpty()) return InboxRules.needText("account")
        if (WaitingFix.TRANSFER_ACCOUNT in fixes && transferAccountId.isNullOrEmpty()) return InboxRules.needText("transfer_account")
        if (WaitingFix.AMOUNT in fixes && (amount == null || amount.signum() <= 0)) return "Informe o valor em reais."
        if (transferCurrency != null && (transferAmount == null || transferAmount.signum() <= 0)) return "Informe quanto entrou em $transferCurrency."
        return ""
    }
}
