package br.financas.app.data

import kotlinx.serialization.builtins.ListSerializer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

/** Respostas no formato das rotas (backend/routes/accounts.py, cards.py), com campos a mais. */
class DtosTest {

    @Test
    fun decodesAccountsWithUnknownKeysAndNulls() {
        val body = """
            [
              {"id": "acct:u1", "user_id": "u1", "name": "Nubank", "type": "CHECKING",
               "institution": "Nubank", "initial_balance": 1500.0, "currency": "BRL",
               "is_default": true, "archived_at": null, "metadata": {},
               "created_at": "2026-01-02T10:00:00.000Z", "updated_at": "2026-01-02T10:00:00.000Z",
               "balance": 2345.67, "balance_brl": 2345.67, "campo_novo": [1, 2]},
              {"id": "a2", "user_id": "u1", "name": "Corretora", "type": "BROKERAGE",
               "institution": null, "initial_balance": 0, "currency": "BRL", "is_default": false,
               "archived_at": null, "metadata": {"portfolio_since": "2026-10-17T00:00:00Z"},
               "balance": 0.1, "balance_brl": 0.1},
              {"id": "a3", "name": "Conta em dolar", "type": "CHECKING", "currency": "USD",
               "is_default": false, "archived_at": "2026-05-01T00:00:00Z",
               "balance": 100.5, "balance_brl": null, "fx_rate": null}
            ]
        """.trimIndent()
        val accounts = ApiJson.decodeFromString(ListSerializer(AccountDto.serializer()), body)

        assertEquals(3, accounts.size)
        val nubank = accounts[0]
        assertEquals("Nubank", nubank.name)
        assertTrue(nubank.isDefault)
        assertEquals(BigDecimal("2345.67"), nubank.balance)
        assertEquals(BigDecimal("1500.0"), nubank.initialBalance)
        assertFalse(nubank.isArchived)

        val brokerage = accounts[1]
        assertTrue(brokerage.isBrokerage)
        assertNull(brokerage.institution)
        assertEquals(BigDecimal("0.1"), brokerage.balanceBrl)
        assertEquals("2026-10-17T00:00:00Z", brokerage.metadata?.get("portfolio_since")?.toString()?.trim('"'))

        val dollar = accounts[2]
        assertTrue(dollar.isArchived)
        assertEquals("USD", dollar.currency)
        assertNull(dollar.balanceBrl)
        assertNull(dollar.fxRate)
        assertNull(dollar.initialBalance)
    }

    @Test
    fun decodesCategoriesInServerOrder() {
        val body = """
            [
              {"id": "c1", "user_id": "u1", "name": "Alimentação", "kind": "EXPENSE", "parent_id": null,
               "color": null, "icon": null, "archived_at": null, "parent_name": null,
               "created_at": "x", "updated_at": "x"},
              {"id": "c2", "user_id": "u1", "name": "Outros", "kind": "EXPENSE", "parent_id": "c1",
               "parent_name": "Alimentação", "archived_at": null},
              {"id": "c3", "name": "Salário", "kind": "INCOME"},
              {"id": "c4", "name": "Reembolso", "kind": "BOTH", "archived_at": "2026-02-01"}
            ]
        """.trimIndent()
        val categories = ApiJson.decodeFromString(ListSerializer(CategoryDto.serializer()), body)

        assertEquals(listOf("c1", "c2", "c3", "c4"), categories.map { it.id })
        assertEquals("Alimentação", categories[1].parentName)
        assertEquals("c1", categories[1].parentId)
        assertNull(categories[0].parentId)
        assertEquals("INCOME", categories[2].kind)
        assertTrue(categories[3].isArchived)
    }

    @Test
    fun decodesCardsWithBothFunctionsAndDebitOnly() {
        val body = """
            [
              {"id": "k1", "user_id": "u1", "name": "Itaú", "due_day": 10, "closing_day": 3,
               "created_at": "x", "autopay_account_id": "acct:u1", "autopay_start_date": "2026-01-01",
               "archived_at": null, "debit_account_id": "acct:u1", "credit_enabled": 1},
              {"id": "k2", "user_id": "u1", "name": "Flash", "due_day": 1, "closing_day": 1,
               "autopay_account_id": null, "autopay_start_date": null, "archived_at": null,
               "debit_account_id": "a9", "credit_enabled": 0},
              {"id": "k3", "name": "Antigo", "due_day": 5, "closing_day": 28}
            ]
        """.trimIndent()
        val cards = ApiJson.decodeFromString(ListSerializer(CreditCardDto.serializer()), body)

        assertEquals(10, cards[0].dueDay)
        assertEquals(3, cards[0].closingDay)
        assertTrue(cards[0].creditEnabled)
        assertEquals("acct:u1", cards[0].debitAccountId)
        assertFalse(cards[1].creditEnabled)
        assertEquals("a9", cards[1].debitAccountId)
        // Antes de 041 nao havia a coluna: credito ligado.
        assertTrue(cards[2].creditEnabled)
        assertNull(cards[2].debitAccountId)
    }
}
