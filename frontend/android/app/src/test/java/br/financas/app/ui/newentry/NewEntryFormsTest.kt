// Port: mudou um, muda o outro, com um teste de cada lado.
// Os handlers do NewEntrySheet.jsx (sem teste do lado web): validacao, corpo do POST, rotulos
// dos toasts e a abertura de um item da fila.
package br.financas.app.ui.newentry

import br.financas.app.core.NBSP
import br.financas.app.data.CategoryDto
import br.financas.app.data.CreditCardDto
import br.financas.app.rules.EntryOptions
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

class NewEntryFormsTest {
    private val options = EntryOptions.buildCategoryOptions(
        listOf(
            CategoryDto(id = "mercado", name = "Mercado", kind = "EXPENSE"),
            CategoryDto(id = "salario", name = "Salário", kind = "INCOME"),
            CategoryDto(id = "lazer-outros", name = "Outros", kind = "EXPENSE", parentId = "lazer", parentName = "Lazer"),
            CategoryDto(id = "outros", name = "Outros", kind = "BOTH"),
        ),
    )
    private val itau = CreditCardDto(id = "itau", name = "Itaú", dueDay = 10, creditEnabled = true)
    private val btg = CreditCardDto(id = "btg", name = "BTG", dueDay = 5, creditEnabled = true, debitAccountId = "conta-btg")
    private val flash = CreditCardDto(id = "flash", name = "Flash", creditEnabled = false, debitAccountId = "conta-flash")
    private val cards = listOf(itau, btg, flash)

    private fun ready(submission: Submission): Submission.Ready {
        assertTrue("esperava envio, veio $submission", submission is Submission.Ready)
        return submission as Submission.Ready
    }

    private fun brl(text: String) = "R$" + NBSP + text

    @Test
    fun theTypeAskedOrDespesa() {
        assertEquals("CARD", EntryType.initial("CARD"))
        assertEquals("INCOME", EntryType.initial("INCOME"))
        assertEquals("EXPENSE", EntryType.initial(""))
        assertEquals("EXPENSE", EntryType.initial(null))
        assertEquals("EXPENSE", EntryType.initial("BUY"))
    }

    @Test
    fun aBankAmountMustBePositive() {
        for (amount in listOf("", "  ", "abc", "0", "0,00", "-5", "12a", "1.2.3")) {
            val form = BankForm(amount = amount, categoryId = "mercado", description = "Pão", date = "2026-10-22")
            assertEquals(amount, NewEntryForms.BANK_AMOUNT_ERROR, NewEntryForms.validate(NewEntryForms.prepareBank(form, options, "a1")))
        }
    }

    @Test
    fun theRequiredFieldsOfABankEntry() {
        val base = BankForm(amount = "10", categoryId = "mercado", description = "Pão", date = "2026-10-22")
        assertEquals("Selecione um item na lista: Categoria.", NewEntryForms.validate(NewEntryForms.prepareBank(base.copy(categoryId = ""), options, "a1")))
        assertEquals("Preencha este campo: Descrição.", NewEntryForms.validate(NewEntryForms.prepareBank(base.copy(description = ""), options, "a1")))
        assertEquals("Preencha este campo: Data.", NewEntryForms.validate(NewEntryForms.prepareBank(base.copy(date = ""), options, "a1")))
        assertNull(NewEntryForms.validate(NewEntryForms.prepareBank(base, options, "a1")))
    }

    @Test
    fun aDespesaPayloadAndLabel() {
        val form = BankForm(amount = "12,50", date = "2026-10-22", categoryId = "mercado", description = "Pão de Açúcar", accountId = "a2")
        val submission = ready(NewEntryForms.prepareBank(form, options, "a1"))
        assertEquals("EXPENSE", submission.kind)
        assertEquals(
            listOf("amount", "date", "category_id", "category", "description", "type", "account_id"),
            submission.payload.keys.toList(),
        )
        assertEquals(BigDecimal("12.5"), submission.payload["amount"])
        assertEquals("Mercado", submission.payload["category"])
        assertEquals("a2", submission.payload["account_id"])
        assertEquals("Despesa de " + brl("12,50"), submission.label)
        assertEquals(NewEntryForms.BANK_FALLBACK, submission.fallbackError)
    }

    @Test
    fun aReceitaAndTheDefaultAccount() {
        val form = BankForm(amount = "1.234,56", date = "2026-10-22", categoryId = "salario", description = "Salário", type = "INCOME")
        val submission = ready(NewEntryForms.prepareBank(form, options, "a1"))
        assertEquals("INCOME", submission.kind)
        assertEquals("INCOME", submission.payload["type"])
        assertEquals(BigDecimal("1234.56"), submission.payload["amount"])
        assertEquals("a1", submission.payload["account_id"])
        assertEquals("Receita de " + brl("1.234,56"), submission.label)
        // Sem lista de contas: a conta nao vai e o servidor usa a padrao.
        val none = ready(NewEntryForms.prepareBank(form, options, ""))
        assertNull(none.payload["account_id"])
        assertFalse(NewEntryForms.payloadJson(none.payload).has("account_id"))
    }

    @Test
    fun theBodyIsTheWebJson() {
        val form = BankForm(amount = "42,90", date = "2026-10-22", categoryId = "mercado", description = "Pão", accountId = "a1")
        val json = NewEntryForms.payloadJson(ready(NewEntryForms.prepareBank(form, options, "a1")).payload)
        assertTrue(json.toString(), json.toString().contains("\"amount\":42.9"))
        assertEquals("2026-10-22", json.getString("date"))
        val whole = NewEntryForms.payloadJson(ready(NewEntryForms.prepareBank(form.copy(amount = "R$ 3.000"), options, "a1")).payload)
        assertTrue(whole.toString(), whole.toString().contains("\"amount\":3000"))
        assertFalse(whole.toString().contains("3000."))
    }

    @Test
    fun aTransfer() {
        val base = TransferForm(amount = "500", date = "2026-10-22", accountId = "a1", transferAccountId = "a2")
        val submission = ready(NewEntryForms.prepareTransfer(base))
        assertEquals("TRANSFER", submission.kind)
        assertEquals(listOf("amount", "date", "account_id", "transfer_account_id", "description"), submission.payload.keys.toList())
        assertEquals("", submission.payload["description"])
        assertEquals("Transferência de " + brl("500,00"), submission.label)
        assertEquals(NewEntryForms.TRANSFER_FALLBACK, submission.fallbackError)

        assertEquals(NewEntryForms.TRANSFER_AMOUNT_ERROR, NewEntryForms.validate(NewEntryForms.prepareTransfer(base.copy(amount = "0"))))
        assertEquals(NewEntryForms.SAME_ACCOUNT_ERROR, NewEntryForms.validate(NewEntryForms.prepareTransfer(base.copy(transferAccountId = "a1"))))
        assertEquals("Selecione um item na lista: Para.", NewEntryForms.validate(NewEntryForms.prepareTransfer(base.copy(transferAccountId = ""))))
        assertEquals("Selecione um item na lista: De.", NewEntryForms.validate(NewEntryForms.prepareTransfer(base.copy(accountId = ""))))
    }

    @Test
    fun aCreditPurchaseInInstallments() {
        val form = CardEntryForm(cardId = "itau", categoryId = "lazer-outros", description = "Cinema", totalAmount = "120", purchaseDate = "2026-10-22", installments = "3")
        val submission = ready(NewEntryForms.prepareCard(form, cards, options))
        assertEquals("CARD", submission.kind)
        assertEquals(
            listOf("card_id", "category_id", "category", "description", "total_amount", "purchase_date", "installments"),
            submission.payload.keys.toList(),
        )
        assertEquals(3, submission.payload["installments"])
        assertEquals(BigDecimal("120"), submission.payload["total_amount"])
        assertEquals("Outros", submission.payload["category"])
        assertEquals("Compra no cartão de " + brl("120,00") + " em 3x", submission.label)
        assertEquals(NewEntryForms.CARD_FALLBACK, submission.fallbackError)
        assertEquals("Compra no cartão de " + brl("120,00"), ready(NewEntryForms.prepareCard(form.copy(installments = "1"), cards, options)).label)
    }

    @Test
    fun aCardPurchaseWithBadValues() {
        val form = CardEntryForm(cardId = "itau", categoryId = "mercado", description = "Pão", totalAmount = "10", purchaseDate = "2026-10-22", installments = "1")
        for (bad in listOf(
            form.copy(cardId = ""),
            form.copy(cardId = "nao-existe"),
            form.copy(totalAmount = "0"),
            form.copy(totalAmount = ""),
            form.copy(installments = "0"),
            form.copy(installments = ""),
            form.copy(installments = "49"),
            form.copy(installments = "1.5"),
            form.copy(purchaseDate = ""),
            form.copy(purchaseDate = "abc"),
            form.copy(purchaseDate = "2026-00-10"),
        )) {
            assertEquals(bad.toString(), NewEntryForms.CARD_ERROR, NewEntryForms.validate(NewEntryForms.prepareCard(bad, cards, options)))
        }
        assertNull(NewEntryForms.validate(NewEntryForms.prepareCard(form.copy(installments = "48"), cards, options)))
        assertEquals("Selecione um item na lista: Categoria.", NewEntryForms.validate(NewEntryForms.prepareCard(form.copy(categoryId = ""), cards, options)))
        assertEquals("Preencha este campo: Descrição.", NewEntryForms.validate(NewEntryForms.prepareCard(form.copy(description = ""), cards, options)))
    }

    @Test
    fun aDebitPurchaseIsAnExpenseInTheCardAccount() {
        val form = CardEntryForm(cardId = "btg", method = "DEBIT", categoryId = "mercado", description = "Padaria", totalAmount = "46,81", purchaseDate = "2026-10-21", installments = "")
        val submission = ready(NewEntryForms.prepareCard(form, cards, options))
        assertEquals("EXPENSE", submission.kind)
        assertEquals("conta-btg", submission.payload["account_id"])
        assertEquals("EXPENSE", submission.payload["type"])
        assertEquals("2026-10-21", submission.payload["date"])
        assertEquals(BigDecimal("46.81"), submission.payload["amount"])
        assertEquals("Mercado", submission.payload["category"])
        assertFalse(submission.payload.containsKey("installments"))
        assertEquals("Compra no débito de " + brl("46,81"), submission.label)
        assertEquals(NewEntryForms.DEBIT_FALLBACK, submission.fallbackError)
        // O mesmo cartao no credito vai para a fatura.
        assertEquals("CARD", ready(NewEntryForms.prepareCard(form.copy(method = "CREDIT", installments = "1"), cards, options)).kind)
    }

    @Test
    fun aDebitOnlyCardSavesOnlyAsDespesa() {
        val form = CardEntryForm(cardId = "flash", method = "CREDIT", categoryId = "mercado", description = "Almoço", totalAmount = "35", purchaseDate = "2026-10-22", installments = "3")
        val submission = ready(NewEntryForms.prepareCard(form, cards, options))
        assertEquals("EXPENSE", submission.kind)
        assertEquals("conta-flash", submission.payload["account_id"])
    }

    @Test
    fun theToasts() {
        val label = "Despesa de " + brl("12,50")
        assertEquals("Despesa de " + brl("12,50") + " registrada.", NewEntryForms.savedNotice(label).message)
        assertEquals("success", NewEntryForms.savedNotice(label).tone)
        val queued = NewEntryForms.queuedNotice(label)
        assertEquals(
            "Sem conexão: despesa de " + brl("12,50") + " guardada neste aparelho. Ela é enviada quando o servidor responder.",
            queued.message,
        )
        assertEquals("info", queued.tone)
        assertEquals(6000, queued.durationMs)
        assertTrue(NewEntryForms.queuedNotice("Compra no débito de x").message.startsWith("Sem conexão: compra no débito de x"))
        assertEquals("Transferência de x pendente atualizada.", NewEntryForms.updatedNotice("Transferência de x").message)
        assertEquals("info", NewEntryForms.updatedNotice("x").tone)
        assertEquals(4000, NewEntryForms.updatedNotice("x").durationMs)
        assertEquals(6000, NewEntryForms.matchedNotice("x").durationMs)
    }

    @Test
    fun aPendingItemReopensInItsForm() {
        val expense = NewEntryForms.formsFromItem(
            "EXPENSE",
            JSONObject("""{"amount":42.9,"date":"2026-10-21","category":"Outros","description":"Pão","type":"EXPENSE","account_id":"a1","client_id":"abc12345"}"""),
            options,
        )
        assertEquals("EXPENSE", expense.type)
        assertEquals("42,9", expense.bank!!.amount)
        // Item de antes do id: o nome acha a categoria da raiz.
        assertEquals("outros", expense.bank!!.categoryId)
        assertEquals("", expense.categoryName)
        assertEquals("a1", expense.bank!!.accountId)

        val early = NewEntryForms.formsFromItem("INCOME", JSONObject("""{"amount":1500.0,"category":"Salário","date":"2026-10-21"}"""), emptyList())
        assertEquals("INCOME", early.bank!!.type)
        assertEquals("1500", early.bank!!.amount)
        assertEquals("", early.bank!!.categoryId)
        assertEquals("Salário", early.categoryName)

        val transfer = NewEntryForms.formsFromItem("TRANSFER", JSONObject("""{"amount":500,"date":"2026-10-22","account_id":"a1","transfer_account_id":"a2","description":""}"""), options)
        assertEquals("TRANSFER", transfer.type)
        assertEquals("500", transfer.transfer!!.amount)
        assertEquals("a2", transfer.transfer!!.transferAccountId)

        val card = NewEntryForms.formsFromItem("CARD", JSONObject("""{"card_id":"itau","category_id":"mercado","total_amount":120,"purchase_date":"2026-10-22","installments":3,"description":"Cinema"}"""), options)
        assertEquals("CARD", card.type)
        assertEquals("3", card.card!!.installments)
        assertEquals("120", card.card!!.totalAmount)
        assertEquals("mercado", card.card!!.categoryId)
        assertEquals("CREDIT", card.card!!.method)
    }
}
