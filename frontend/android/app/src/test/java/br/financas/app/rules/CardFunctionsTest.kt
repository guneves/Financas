// Porte: mudou um, muda o outro, com um teste de cada lado.
// Os mesmos casos de frontend/src/lib/cardFunctions.test.js, na mesma ordem; o nome
// do teste do node vai no comentario de cada um.
package br.financas.app.rules

import br.financas.app.rules.CardFunctions.cardFormPayload
import br.financas.app.rules.CardFunctions.cardFunctionLabel
import br.financas.app.rules.CardFunctions.cardFunctionOf
import br.financas.app.rules.CardFunctions.cardMethods
import br.financas.app.rules.CardFunctions.creditCards
import br.financas.app.rules.CardFunctions.dayOf
import br.financas.app.rules.CardFunctions.debitPurchasePayload
import br.financas.app.rules.CardFunctions.hasCredit
import br.financas.app.rules.CardFunctions.hasDebit
import br.financas.app.rules.CardFunctions.resolveCardMethod
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal
import java.time.LocalDate

class CardFunctionsTest {
    private val itau = Card(id = "i", name = "Itaú", creditEnabled = true, debitAccountId = null)
    private val btg = Card(id = "b", name = "BTG", creditEnabled = true, debitAccountId = "conta-btg")
    private val flash = Card(id = "f", name = "Flash", creditEnabled = false, debitAccountId = "conta-flash")

    private fun assertMatches(pattern: String, text: String?) =
        assertTrue("\"$text\" contem /$pattern/", text != null && Regex(pattern).containsMatchIn(text))

    // node: 'the functions of each card'
    @Test
    fun theFunctionsOfEachCard() {
        assertEquals(true, hasCredit(itau))
        assertEquals(false, hasDebit(itau))
        assertEquals(false, hasCredit(flash))
        assertEquals(true, hasDebit(flash))
        // Um cartao de antes da 041 (sem as colunas) e credito.
        assertEquals(true, hasCredit(Card(id = "x", name = "Velho")))
        assertEquals(listOf("CREDIT", "BOTH", "DEBIT"), listOf(itau, btg, flash).map(::cardFunctionOf))
        assertEquals(listOf("Crédito", "Crédito e débito", "Débito"), listOf(itau, btg, flash).map(::cardFunctionLabel))
    }

    // node: 'a debit-only card is out of the credit lists'
    @Test
    fun aDebitOnlyCardIsOutOfTheCreditLists() {
        assertEquals(listOf("i", "b"), creditCards(listOf(itau, btg, flash)).map { it.id })
        assertEquals(emptyList<Card>(), creditCards(null))
    }

    // node: 'the purchase method follows the card'
    @Test
    fun thePurchaseMethodFollowsTheCard() {
        assertEquals(listOf("CREDIT", "DEBIT"), cardMethods(btg))
        assertEquals(listOf("DEBIT"), cardMethods(flash))
        assertEquals("DEBIT", resolveCardMethod(btg, "DEBIT"))
        assertEquals("CREDIT", resolveCardMethod(itau, "DEBIT"))
        assertEquals("DEBIT", resolveCardMethod(flash, "CREDIT"))
        assertEquals("CREDIT", resolveCardMethod(null, "DEBIT"))
    }

    // node: 'the Ajustes form becomes the API body'
    @Test
    fun theAjustesFormBecomesTheApiBody() {
        val nubank = cardFormPayload(
            CardForm(name = " Nubank ", functions = "CREDIT", dueDay = "10", closingDay = "3", autopayAccountId = ""),
        ).payload
        assertEquals(
            linkedMapOf("name" to "Nubank", "credit_enabled" to true, "debit_account_id" to null, "due_day" to 10, "closing_day" to 3, "autopay_account_id" to null),
            nubank,
        )
        assertEquals(listOf("name", "credit_enabled", "debit_account_id", "due_day", "closing_day", "autopay_account_id"), nubank!!.keys.toList())

        assertEquals(
            mapOf("name" to "Flash", "credit_enabled" to false, "debit_account_id" to "conta-flash", "autopay_account_id" to null),
            cardFormPayload(
                CardForm(name = "Flash", functions = "DEBIT", debitAccountId = "conta-flash", dueDay = "", closingDay = "", autopayAccountId = "x"),
            ).payload,
        )
        // No JS os dias vem como numero (15, 8); Number() le "15" e 15 igual.
        val both = cardFormPayload(
            CardForm(name = "BTG", functions = "BOTH", debitAccountId = "conta-btg", dueDay = "15", closingDay = "8"),
        ).payload
        assertEquals(
            mapOf("name" to "BTG", "credit_enabled" to true, "debit_account_id" to "conta-btg", "due_day" to 15, "closing_day" to 8),
            both,
        )
        // Sem o campo de debito automatico no formulario, a chave nao vai no corpo.
        assertTrue(!both!!.containsKey("autopay_account_id"))
    }

    // node: 'what the form still needs'
    @Test
    fun whatTheFormStillNeeds() {
        assertMatches("nome", cardFormPayload(CardForm(name = "")).error)
        assertMatches("débito", cardFormPayload(CardForm(name = "Flash", functions = "DEBIT")).error)
        assertMatches("vencimento", cardFormPayload(CardForm(name = "Itaú", functions = "CREDIT", dueDay = "32", closingDay = "3")).error)
        assertMatches("vencimento", cardFormPayload(CardForm(name = "BTG", functions = "BOTH", debitAccountId = "c", dueDay = "", closingDay = "")).error)
    }

    // node: 'a debit purchase is an expense in the card account'
    @Test
    fun aDebitPurchaseIsAnExpenseInTheCardAccount() {
        val payload = debitPurchasePayload(
            flash,
            DebitPurchase(amount = BigDecimal("46.81"), date = LocalDate.parse("2026-10-21"), categoryId = "cat", category = "Alimentação", description = "Padaria"),
        )
        assertEquals(
            mapOf("amount" to BigDecimal("46.81"), "date" to "2026-10-21", "category_id" to "cat", "category" to "Alimentação", "description" to "Padaria", "type" to "EXPENSE", "account_id" to "conta-flash"),
            payload,
        )
    }

    // Sem par no node: o Number() do JS que dayOf() reproduz (casos que o JS nao testa).
    @Test
    fun dayOfReadsLikeJsNumber() {
        assertEquals(10, dayOf(" 10 "))
        assertEquals(10, dayOf("10.0"))
        assertEquals(10, dayOf("1e1"))
        assertEquals(10, dayOf("0x0A"))
        assertEquals(31, dayOf("+31"))
        assertNull(dayOf("0"))
        assertNull(dayOf(""))
        assertNull(dayOf("10.5"))
        assertNull(dayOf("-0x1"))
        assertNull(dayOf("10 dias"))
        assertNull(dayOf("Infinity"))
        assertNull(dayOf(null))
    }
}
