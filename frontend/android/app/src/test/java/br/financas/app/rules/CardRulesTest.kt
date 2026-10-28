// Porte: mudou um, muda o outro, com um teste de cada lado.
// Os tres primeiros sao os casos de frontend/src/lib/cardPurchase.test.js, na mesma ordem; os
// outros cobrem as regras inline de pages/lancamentos/Cartoes.jsx e dos sheets, sem teste na web.
package br.financas.app.rules

import br.financas.app.data.AccountDto
import br.financas.app.data.CardInvoiceDto
import br.financas.app.data.DebitCardDto
import br.financas.app.data.DebitPurchaseDto
import br.financas.app.data.InvoiceCardDto
import br.financas.app.data.PurchaseInstallmentDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.math.BigDecimal

class CardRulesTest {
    private fun money(text: String) = BigDecimal(text)

    private fun assertMoney(expected: String, actual: BigDecimal) =
        assertEquals("$actual", 0, money(expected).compareTo(actual))

    // R$ 100 em 3x: 33,34 + 33,33 + 33,33 (o servidor poe o centavo na primeira).
    private val installments = listOf(
        PurchaseInstallmentDto(id = "a", amount = money("33.34"), installmentInfo = "1/3", status = "PAID"),
        PurchaseInstallmentDto(id = "b", amount = money("33.33"), installmentInfo = "2/3", status = "OPEN"),
        PurchaseInstallmentDto(id = "c", amount = money("33.33"), installmentInfo = "3/3", status = "OPEN"),
    )

    // node: 'the refund prefill is the purchase total, not one installment times the count'
    @Test
    fun theRefundPrefillIsThePurchaseTotal() {
        assertMoney("100", CardRules.refundPrefillAmount(PurchaseRef(money("33.33"), 3), installments))
        assertMoney("100", CardRules.refundPrefillAmount(PurchaseRef(money("33.34"), 3), installments))
    }

    // node: 'without the installments the prefill falls back to the estimate, in cents'
    @Test
    fun withoutTheInstallmentsThePrefillIsTheEstimate() {
        assertMoney("99.99", CardRules.refundPrefillAmount(PurchaseRef(money("33.33"), 3), emptyList()))
        assertMoney("0.3", CardRules.refundPrefillAmount(PurchaseRef(money("0.1"), 3), null))
        assertMoney("50", CardRules.refundPrefillAmount(PurchaseRef(money("50")), emptyList()))
    }

    // node: "a legacy purchase's installments are those within a cent and of the same count"
    @Test
    fun legacyInstallmentsAreWithinACentAndOfTheSameCount() {
        val other = PurchaseInstallmentDto(id = "x", amount = money("40"), installmentInfo = "1/3", status = "OPEN")
        val twelve = PurchaseInstallmentDto(id = "y", amount = money("33.33"), installmentInfo = "1/12", status = "OPEN")
        val found = CardRules.purchaseInstallments(installments + other + twelve, PurchaseRef(money("33.33"), 3))
        assertEquals(listOf("a", "b", "c"), found.map { it.id })
    }

    private fun invoice(
        total: String = "100",
        closed: Boolean = false,
        pastDue: Boolean = false,
        closing: String? = "2026-11-03",
        due: String? = "2026-11-10",
        nearest: Boolean = false,
    ) = CardInvoiceDto(
        invoiceMonth = 11, invoiceYear = 2026, key = "2026-11", closingDate = closing, dueDate = due,
        closed = closed, pastDue = pastDue, payable = closed && money(total).signum() >= 0, nearest = nearest, total = money(total),
    )

    @Test
    fun theStatusIsCreditPastDueClosedOrOpen() {
        assertEquals(InvoiceStatus.CREDIT, CardRules.invoiceStatus(invoice(total = "-5", closed = true, pastDue = true)))
        assertEquals(InvoiceStatus.PAST_DUE, CardRules.invoiceStatus(invoice(closed = true, pastDue = true)))
        assertEquals(InvoiceStatus.CLOSED, CardRules.invoiceStatus(invoice(closed = true)))
        assertEquals(InvoiceStatus.OPEN, CardRules.invoiceStatus(invoice()))
    }

    @Test
    fun thePaymentHintSaysWhyPagarIsThereOrNot() {
        assertEquals("O crédito do estorno abate a próxima fatura", CardRules.paymentHint(invoice(total = "-5"), null))
        assertEquals("Fecha em 03/11/2026 · pagamento liberado depois", CardRules.paymentHint(invoice(), null))
        assertEquals("Fecha em 03/11/2026", CardRules.paymentHint(invoice(), null, future = true))
        assertEquals("Pagamento liberado após o fechamento", CardRules.paymentHint(invoice(closing = null), null))
        assertEquals("Débito automático em 10/11/2026", CardRules.paymentHint(invoice(closed = true), "conta"))
        assertNull(CardRules.paymentHint(invoice(closed = true), null))
    }

    @Test
    fun theSuggestedAccountIsTheAutopayOneThenTheDefault() {
        val accounts = listOf(
            AccountDto(id = "velha", name = "Velha", archivedAt = "2026-01-01"),
            AccountDto(id = "itau", name = "Itaú"),
            AccountDto(id = "nubank", name = "Nubank", isDefault = true),
        )
        assertEquals("itau", CardRules.suggestedPayAccountId(accounts, "itau"))
        assertEquals("nubank", CardRules.suggestedPayAccountId(accounts, "velha"))
        assertEquals("nubank", CardRules.suggestedPayAccountId(accounts, null))
        assertEquals("itau", CardRules.suggestedPayAccountId(accounts.take(2), null))
        assertEquals("", CardRules.suggestedPayAccountId(emptyList(), null))
    }

    @Test
    fun theHeaderNamesTheNearestInvoiceTheServerFlagged() {
        val card = InvoiceCardDto(cardId = "c", cardName = "Nubank", invoices = listOf(invoice(), invoice(total = "250.5", nearest = true)))
        assertEquals(
            "Próxima fatura: Nubank 11/2026 · R$ 250,50 · R$ 350,50 em aberto nos cartões",
            CardRules.headerDescription(listOf(card), money("350.5")),
        )
        assertEquals("Faturas em aberto por cartão.", CardRules.headerDescription(emptyList(), BigDecimal.ZERO))
    }

    @Test
    fun deletingSaysWhatStays() {
        assertEquals("Todas as parcelas dela saem das faturas.", CardRules.deletePurchaseMessage(3, 0))
        assertEquals(
            "As 2 parcelas em aberto saem das faturas. A parcela já paga fica: saiu com o pagamento da fatura. " +
                "Para tirá-la também, desfaça esse pagamento no Extrato.",
            CardRules.deletePurchaseMessage(2, 1),
        )
        assertEquals("Excluir compra e parcelas", CardRules.deletePurchaseLabel(3))
        assertEquals("Excluir compra", CardRules.deletePurchaseLabel(1))
    }

    @Test
    fun theNoticesNameTheInvoice() {
        assertEquals("Estorno de R$ 30,00 lançado na fatura 12/2026.", CardRules.refundNotice(money("30"), 12, 2026))
        assertEquals("Estorno de R$ 30,00 lançado.", CardRules.refundNotice(money("30"), null, null))
        val paid = invoice(total = "120", closed = true)
        assertEquals("Fatura Nubank 11/2026 paga — R$ 120,00 saiu de Itaú.", CardRules.paidNotice("Nubank", paid, "Itaú"))
        assertEquals("Fatura Nubank 11/2026 paga — R$ 120,00 foi debitado.", CardRules.paidNotice("Nubank", paid, null))
    }

    @Test
    fun theShareSheetStartsFromEveryInstallmentInCents() {
        val rows = listOf(
            PurchaseInstallmentDto(id = "a", amount = money("33.34"), shareMode = "SPLIT", sharePerson = "Ana", shareOthersAmount = money("10.01")),
            PurchaseInstallmentDto(id = "b", amount = money("33.33"), shareMode = "SPLIT", sharePerson = "Ana", shareOthersAmount = money("10")),
            PurchaseInstallmentDto(id = "c", amount = money("33.33"), shareMode = "SPLIT", sharePerson = "Ana", shareOthersAmount = money("10")),
        )
        val start = CardRules.shareStart(rows)
        assertMoney("100", start.total)
        assertEquals(ShareForm("SPLIT", "Ana", "30.01"), start.form)
        assertEquals(3, start.installments)
        assertEquals(ShareForm("", "", ""), CardRules.shareStart(emptyList()).form)
    }

    @Test
    fun futureInvoicesFoldIntoOneRow() {
        val future = listOf(invoice(total = "33.33"), invoice(total = "33.34"))
        assertEquals("Próximas 2 faturas", CardRules.futureLabel(future))
        assertEquals("Fatura seguinte", CardRules.futureLabel(future.take(1)))
        assertMoney("66.67", CardRules.futureTotal(future))
    }

    // node (cardPurchaseEdit.test.js): 'sends only what changed'
    @Test
    fun theEditSendsOnlyWhatChanged() {
        assertEquals(mapOf("category_id" to "cat-b"), CardRules.purchaseEditPayload("Loja", "cat-a", "Loja", "cat-b").payload)
        assertEquals(mapOf("description" to "Cinema"), CardRules.purchaseEditPayload("Loja", "cat-a", " Cinema ", "cat-a").payload)
        assertNull(CardRules.purchaseEditPayload("Loja", "cat-a", "Loja ", "cat-a").payload)
        assertNull(CardRules.purchaseEditPayload("Loja", null, "Loja", "").payload)
    }

    // node: 'the description is required and bounded'
    @Test
    fun theEditNeedsADescription() {
        assertEquals("Informe a descrição da compra.", CardRules.purchaseEditPayload("Loja", "cat-a", "  ", "cat-a").error)
        assertEquals(true, CardRules.purchaseEditPayload("Loja", "cat-a", "x".repeat(501), "cat-a").error != null)
    }

    // node (cardGroups.test.js): 'a debit-only card with purchases comes after the credit cards'
    @Test
    fun aCardWithoutInvoicesShowsOnlyWithDebitPurchases() {
        val nubank = InvoiceCardDto(cardId = "nu", cardName = "Nubank")
        val btg = DebitCardDto(cardId = "nu", cardName = "Nubank", purchases = listOf(DebitPurchaseDto(id = "a")))
        val flash = DebitCardDto(cardId = "flash", cardName = "Flash", creditEnabled = false, accountName = "Flash", purchases = listOf(DebitPurchaseDto(id = "f")))
        val empty = DebitCardDto(cardId = "empty", creditEnabled = false, purchases = emptyList())
        assertEquals(listOf("flash"), CardRules.debitOnlyCards(listOf(nubank), listOf(btg, flash, empty)).map { it.cardId })
        assertEquals("nu", CardRules.debitOf(nubank, listOf(btg, flash))?.cardId)
        assertEquals("Débito · sai de Flash", CardRules.debitCardSubtitle(flash))
        assertEquals("No débito · sai de Flash · 1 compra", CardRules.debitSectionLabel(flash))
    }
}
