// Porte: mudou um, muda o outro, com um teste de cada lado.
// Os quatro primeiros sao os casos de frontend/src/lib/transactionEdit.test.js, na mesma ordem;
// os outros cobrem as regras inline de pages/lancamentos/Extrato.jsx, que nao tem teste na web.
package br.financas.app.rules

import br.financas.app.data.TransactionDto
import br.financas.app.rules.ExtratoRules.transactionEditForm
import br.financas.app.rules.ExtratoRules.transactionEditPayload
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal
import java.time.LocalDate

class ExtratoRulesTest {
    private fun money(text: String) = BigDecimal(text)

    private val transfer = TransactionDto(
        id = "t", type = "TRANSFER", amount = money("500"), date = "2026-10-10", description = "Reserva",
        accountId = "nubank", transferAccountId = "poupanca", category = "Transferencia",
    )

    // node: 'a transfer edit can change the destination account'
    @Test
    fun aTransferEditCanChangeTheDestinationAccount() {
        val form = transactionEditForm(transfer)
        assertEquals("poupanca", form.transferAccountId)
        val payload = transactionEditPayload(transfer, form.copy(transferAccountId = "itau"), money("500"))
        assertEquals("itau", payload["transfer_account_id"])
        assertFalse(payload.containsKey("account_id"))
        assertFalse(payload.containsKey("type"))
        assertFalse(payload.containsKey("category_id"))
    }

    // node: 'the accounts go only when they changed'
    @Test
    fun theAccountsGoOnlyWhenTheyChanged() {
        val form = transactionEditForm(transfer)
        val payload = transactionEditPayload(transfer, form, money("500"))
        assertEquals(listOf("amount" to money("500"), "date" to "2026-10-10", "description" to "Reserva"), payload.toList())
        val moved = transactionEditPayload(transfer, form.copy(accountId = "itau"), money("500"))
        assertEquals("itau", moved["account_id"])
        assertFalse(moved.containsKey("transfer_account_id"))
    }

    // node: 'a despesa sends its type and the category id only when changed'
    @Test
    fun aDespesaSendsItsTypeAndTheCategoryIdOnlyWhenChanged() {
        val expense = TransactionDto(
            id = "e", type = "EXPENSE", amount = money("30"), date = "2026-10-11", description = "Almoço",
            accountId = "nubank", categoryId = "alimentacao-outros", category = "Outros",
        )
        val form = transactionEditForm(expense)
        assertEquals("", form.transferAccountId)
        assertEquals(
            listOf("amount" to money("30"), "date" to "2026-10-11", "description" to "Almoço", "type" to "EXPENSE"),
            transactionEditPayload(expense, form, money("30")).toList(),
        )
        assertEquals("lazer", transactionEditPayload(expense, form.copy(categoryId = "lazer"), money("30"))["category_id"])
        assertFalse(transactionEditPayload(expense, form.copy(transferAccountId = "x"), money("30")).containsKey("transfer_account_id"))
    }

    // node: 'the share goes only when it changed'
    @Test
    fun theShareGoesOnlyWhenItChanged() {
        val expense = TransactionDto(id = "e", type = "EXPENSE", amount = money("100"), date = "2026-10-11", accountId = "a", categoryId = "c")
        val form = transactionEditForm(expense)
        assertFalse(transactionEditPayload(expense, form, money("100"), sharing = true).containsKey("share_mode"))
        val split = form.copy(share = ShareForm(shareMode = "SPLIT", shareOthersAmount = "40", sharePerson = "Ana"))
        assertEquals("SPLIT", transactionEditPayload(expense, split, money("100"), sharing = true)["share_mode"])
        assertFalse(transactionEditPayload(expense, split, money("100"), sharing = false).containsKey("share_mode"))
    }

    @Test
    fun theFormAmountOpensWithAComma() {
        assertEquals("45,9", transactionEditForm(transfer.copy(amount = money("45.90"))).amount)
    }

    @Test
    fun derivedRowsAreLockedAndSayWhereTheyCameFrom() {
        val payment = TransactionDto(id = "p", type = "EXPENSE", sourceType = "CC_INVOICE_PAYMENT", sourceId = "x")
        val autopay = payment.copy(sourceType = "CC_AUTOPAY")
        val aporte = TransactionDto(id = "a", type = "EXPENSE", sourceType = "INVESTMENT_TRANSACTION", sourceId = "mov")
        val provento = TransactionDto(id = "v", type = "INCOME", sourceType = "INVESTMENT_PROCEED", sourceId = "prov")
        val pending = TransactionDto(id = "pending:1", type = "EXPENSE", pending = true, pendingStatus = "pending")
        val plain = TransactionDto(id = "n", type = "EXPENSE", sourceType = "RECURRING_TRANSACTION")
        assertFalse(ExtratoRules.isEditableHere(payment))
        assertFalse(ExtratoRules.isEditableHere(aporte))
        assertFalse(ExtratoRules.isEditableHere(pending))
        assertTrue(ExtratoRules.isEditableHere(plain))
        assertTrue(ExtratoRules.isInvoicePayment(autopay))
        assertFalse(ExtratoRules.isInvoicePayment(pending))
        assertTrue(ExtratoRules.isInvestmentCash(aporte))
        assertFalse(ExtratoRules.isInvestmentCash(aporte.copy(sourceId = null)))
        assertEquals("Pela fatura", ExtratoRules.originLabel(payment))
        assertEquals("Débito automático", ExtratoRules.originLabel(autopay))
        assertEquals("Pela carteira", ExtratoRules.originLabel(aporte))
        assertEquals("Provento", ExtratoRules.originLabel(provento))
        assertEquals("Pendente de envio", ExtratoRules.originLabel(pending))
        assertEquals("Recusado pelo servidor", ExtratoRules.originLabel(pending.copy(pendingStatus = "needs_attention")))
    }

    @Test
    fun badgesAndSignsFollowTheTypeAndTheOrigin() {
        val aporte = TransactionDto(id = "a", type = "EXPENSE", sourceType = "INVESTMENT_TRANSACTION")
        val resgate = aporte.copy(type = "INCOME")
        val transfer = TransactionDto(id = "t", type = "TRANSFER")
        // "Investimento" como nome de categoria nao faz de uma despesa um aporte (039).
        val category = TransactionDto(id = "c", type = "EXPENSE", category = "Investimento")
        assertEquals("Investimento", ExtratoRules.typeBadge(aporte))
        assertEquals("Resgate", ExtratoRules.typeBadge(resgate))
        assertEquals("Transferência", ExtratoRules.typeBadge(transfer))
        assertNull(ExtratoRules.typeBadge(category))
        assertEquals(0, ExtratoRules.amountSign(transfer))
        assertEquals(1, ExtratoRules.amountSign(resgate))
        assertEquals(-1, ExtratoRules.amountSign(category))
        assertFalse(ExtratoRules.canShare(transfer))
        assertFalse(ExtratoRules.canShare(aporte))
        assertTrue(ExtratoRules.canShare(category))
    }

    @Test
    fun dayLabelsAreTodayYesterdayOrTheWeekday() {
        val today = LocalDate.of(2026, 10, 24)
        assertEquals("Hoje", ExtratoRules.dayLabel("2026-10-24", today))
        assertEquals("Ontem", ExtratoRules.dayLabel("2026-10-23", today))
        assertEquals("Ter., 22 de set.", ExtratoRules.dayLabel("2026-09-22", today))
        assertEquals("Sáb., 27 de dez. de 2025", ExtratoRules.dayLabel("2025-12-27", today))
        assertEquals("Sem data", ExtratoRules.dayLabel("", today))
    }

    @Test
    fun daysUseTheServerTotalAndSumOnlyWhatTheServerDoesNotKnow() {
        val rows = listOf(
            TransactionDto(id = "p", type = "EXPENSE", amount = money("12.30"), date = "2026-10-25", pending = true),
            TransactionDto(id = "a", type = "INCOME", amount = money("100"), date = "2026-10-24"),
            TransactionDto(id = "b", type = "TRANSFER", amount = money("50"), date = "2026-10-24"),
        )
        val days = ExtratoRules.groupByDay(rows, mapOf("2026-10-24" to money("-60")))
        assertEquals(listOf("2026-10-25" to 1, "2026-10-24" to 2), days.map { it.date to it.items.size })
        assertEquals(0, money("-12.30").compareTo(days[0].total))
        assertEquals(0, money("-60").compareTo(days[1].total))
    }

    @Test
    fun filtersSendOnlyWhatIsSetAndReadAmountsLikeTheField() {
        val filters = ExtratoFilters(q = " uber ", minAmount = "45,90", accountId = "nubank")
        assertEquals(
            listOf("q" to "uber", "account_id" to "nubank", "min_amount" to "45.9"),
            ExtratoRules.filterParams(filters).toList(),
        )
        assertTrue(ExtratoRules.hasActiveFilters(filters))
        assertEquals(2, ExtratoRules.countHiddenFilters(filters))
        assertFalse(ExtratoRules.hasActiveFilters(ExtratoFilters(q = "  ")))
    }

    @Test
    fun receiptsShowTypeAndSizeLikeTheWeb() {
        assertEquals("512 B", ExtratoRules.fileSize(512))
        assertEquals("120 kB", ExtratoRules.fileSize(122_880))
        assertEquals("2,4 MB", ExtratoRules.fileSize(2_516_582))
        assertEquals("PDF · 2 kB", ExtratoRules.attachmentDetail("application/pdf", 2048))
        assertEquals("Arquivo · 10 B", ExtratoRules.attachmentDetail(null, 10))
        val row = TransactionDto(id = "x", type = "EXPENSE", amount = money("45.9"), date = "2026-10-05", description = "Mercado")
        assertEquals("Mercado · 05/10/2026 · −R$ 45,90", ExtratoRules.attachmentDescription(row))
    }

    @Test
    fun projectionsCarryThePendingItemsOfTheBalance() {
        // O servidor: saldo 1.000, projecao 630; um pendente de R$ 45,90 levou o saldo a 954,10.
        val value = ExtratoRules.projectionWithPending(money("630"), money("1000"), money("954.10"))
        assertEquals(0, money("584.10").compareTo(value))
    }
}
