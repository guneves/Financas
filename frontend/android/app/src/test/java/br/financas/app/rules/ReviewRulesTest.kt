// Porte: mudou um, muda o outro, com um teste de cada lado.
// Os nove primeiros sao os casos de frontend/src/lib/review.test.js, na mesma ordem; os outros
// cobrem o que so o celular tem (a categoria sugerida, o que nao gravou sozinho, o numero da aba).
package br.financas.app.rules

import br.financas.app.data.AccountDto
import br.financas.app.data.CardStatementDto
import br.financas.app.data.InboxItemDto
import br.financas.app.data.JsonBody
import br.financas.app.data.ReviewItemDto
import br.financas.app.data.TransactionDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

class ReviewRulesTest {
    private fun tx(id: String, date: String, createdAt: String = "${date}T10:00:00Z") =
        TransactionDto(id = id, type = "EXPENSE", date = date, createdAt = createdAt)

    private fun card(id: String, date: String, type: String = "CARD", installments: Int = 1) =
        CardStatementDto(id = id, clientId = "c-$id", date = date, createdAt = "${date}T12:00:00Z", type = type, installments = installments)

    private fun keys(rows: List<TransactionDto>) = rows.map(ReviewRules::statementKey)

    // node: 'card purchases are interleaved by date, newest first'
    @Test
    fun cardPurchasesAreInterleavedByDateNewestFirst() {
        val merged = ReviewRules.mergeStatement(
            listOf(tx("t2", "2026-10-12"), tx("t1", "2026-10-10")),
            listOf(card("p1", "2026-10-11"), card("p0", "2026-10-09")),
        )
        assertEquals(listOf("t2", "card:c-p1", "t1", "card:c-p0"), keys(merged))
        assertTrue(ReviewRules.isCardRow(merged[1]))
        assertFalse(ReviewRules.isCardRow(merged[0]))
    }

    // node: 'on the same day the later one comes first'
    @Test
    fun onTheSameDayTheLaterOneComesFirst() {
        val merged = ReviewRules.mergeStatement(listOf(tx("t1", "2026-10-10", "2026-10-10T09:00:00Z")), listOf(card("p1", "2026-10-10")))
        assertEquals(listOf("card:c-p1", "t1"), keys(merged))
    }

    // node: 'without purchases the list is the same object'
    @Test
    fun withoutPurchasesTheListIsTheSameObject() {
        val list = listOf(tx("t1", "2026-10-10"))
        assertSame(list, ReviewRules.mergeStatement(list, emptyList()))
        assertSame(list, ReviewRules.mergeStatement(list, null))
    }

    // node: 'a paged statement shows only purchases down to the oldest loaded day'
    @Test
    fun aPagedStatementShowsOnlyPurchasesDownToTheOldestLoadedDay() {
        val merged = ReviewRules.mergeStatement(
            listOf(tx("t1", "2026-10-10")),
            listOf(card("p1", "2026-10-11"), card("p0", "2026-10-01")),
            until = "2026-10-10",
        )
        assertEquals(listOf("card:c-p1", "t1"), keys(merged))
        assertEquals("2026-10-10", ReviewRules.oldestDate(merged))
        assertEquals("", ReviewRules.oldestDate(emptyList()))
        // Sem mais paginas, todas; com mais, ate a data mais antiga carregada.
        assertEquals("", ReviewRules.statementUntil(merged, hasMore = false))
        assertEquals("2026-10-10", ReviewRules.statementUntil(merged, hasMore = true))
    }

    // node: 'a purchase goes out, a refund comes back'
    @Test
    fun aPurchaseGoesOutARefundComesBack() {
        assertEquals(-1, ReviewRules.cardAmountSign(ReviewRules.cardStatementRow(card("p", "2026-10-10"))))
        assertEquals(1, ReviewRules.cardAmountSign(ReviewRules.cardStatementRow(card("p", "2026-10-10", type = "REFUND"))))
    }

    private fun review(
        table: String = "transactions",
        type: String = "EXPENSE",
        id: String = "a",
        categoryId: String? = null,
        category: String? = null,
        cardName: String? = null,
        installments: Int? = null,
        accountName: String? = null,
        transferAccountName: String? = null,
    ) = ReviewItemDto(
        table = table, id = id, type = type, categoryId = categoryId, category = category, cardName = cardName,
        installments = installments, accountName = accountName, transferAccountName = transferAccountName,
    )

    // node: 'the review line says where it came from'
    @Test
    fun theReviewLineSaysWhereItCameFrom() {
        assertEquals("Itaú Visa · 3x", ReviewRules.reviewPlace(review(table = "cc_expenses", cardName = "Itaú Visa", installments = 3)))
        assertEquals("Itaú Visa", ReviewRules.reviewPlace(review(table = "cc_expenses", cardName = "Itaú Visa", installments = 1)))
        assertEquals("Itaú", ReviewRules.reviewPlace(review(accountName = "Itaú")))
        assertEquals("Itaú → BB", ReviewRules.reviewPlace(review(type = "TRANSFER", accountName = "Itaú", transferAccountName = "BB")))
        // Sem nome: "Cartão" / "Conta".
        assertEquals("Cartão", ReviewRules.reviewPlace(review(table = "cc_expenses")))
        assertEquals("Conta → Conta", ReviewRules.reviewPlace(review(type = "TRANSFER")))
    }

    // node: 'signs and category types follow the movement'
    @Test
    fun signsAndCategoryTypesFollowTheMovement() {
        assertEquals(-1, ReviewRules.reviewSign(review(type = "EXPENSE")))
        assertEquals(-1, ReviewRules.reviewSign(review(type = "CARD")))
        assertEquals(1, ReviewRules.reviewSign(review(type = "INCOME")))
        assertEquals(1, ReviewRules.reviewSign(review(type = "REFUND")))
        assertEquals(0, ReviewRules.reviewSign(review(type = "TRANSFER")))
        assertEquals("INCOME", ReviewRules.reviewCategoryType(review(type = "REFUND")))
        assertEquals("EXPENSE", ReviewRules.reviewCategoryType(review(type = "CARD")))
        assertFalse(ReviewRules.reviewHasCategory(review(type = "TRANSFER")))
    }

    // node: 'the payload sends a category only when the owner changed it'
    @Test
    fun thePayloadSendsACategoryOnlyWhenTheOwnerChangedIt() {
        val items = listOf(
            review(id = "a", type = "EXPENSE", categoryId = "food"),
            review(table = "cc_expenses", id = "b", type = "CARD", categoryId = "food"),
            review(id = "c", type = "TRANSFER"),
        )
        val chosen = mapOf("transactions:a" to "food", "cc_expenses:b" to "fun", "transactions:c" to "fun")
        assertEquals(
            """[{"table":"transactions","id":"a"},{"table":"cc_expenses","id":"b","category_id":"fun"},{"table":"transactions","id":"c"}]""",
            JsonBody.encode(mapOf("items" to ReviewRules.reviewPayload(items, chosen))).removePrefix("{\"items\":").removeSuffix("}"),
        )
        assertEquals(
            items.map { mapOf("table" to it.table, "id" to it.id) },
            ReviewRules.reviewPayload(items),
        )
    }

    // node: 'notices count in Portuguese and vanish at zero'
    @Test
    fun noticesCountInPortugueseAndVanishAtZero() {
        assertEquals("", ReviewRules.reviewNoticeText(0))
        assertTrue(ReviewRules.reviewNoticeText(1).startsWith("1 lançamento gravado sozinho espera"))
        assertTrue(ReviewRules.reviewNoticeText(3).startsWith("3 lançamentos gravados sozinhos esperam"))
        assertEquals("", ReviewRules.waitingNoticeText(0))
        assertTrue(ReviewRules.waitingNoticeText(2).startsWith("2 movimentos"))
    }

    // ---- Sem par no node ----

    @Test
    fun aCardRowCarriesItsTagAndKey() {
        val row = ReviewRules.cardStatementRow(card("p", "2026-10-10", installments = 4).copy(cardName = "BTG black", needsReview = true))
        assertEquals("Cartão · 4x", ReviewRules.cardTag(row))
        assertEquals("Estorno", ReviewRules.cardTag(ReviewRules.cardStatementRow(card("r", "2026-10-10", type = "REFUND"))))
        assertEquals("Cartão", ReviewRules.cardTag(ReviewRules.cardStatementRow(card("q", "2026-10-10"))))
        assertEquals("card:c-p", ReviewRules.statementKey(row))
        // Sem client_id, o id da primeira parcela.
        assertEquals("card:p", ReviewRules.statementKey(row.copy(clientId = null)))
        assertTrue(row.needsReview)
        assertEquals("BTG black", row.cardName)
    }

    @Test
    fun theSuggestedCategoryStaysOnTopWhenItIsNotAnOption() {
        val options = listOf(
            CategoryOption("food", "Alimentação", "Alimentação", "EXPENSE", null),
            CategoryOption("salary", "Salário", "Salário", "INCOME", null),
            CategoryOption("other", "Outros", "Lazer > Outros", "BOTH", "fun"),
        )
        val item = review(categoryId = "food", category = "Alimentação")
        assertEquals("food", ReviewRules.reviewCategoryValue(item, emptyMap()))
        assertEquals("other", ReviewRules.reviewCategoryValue(item, mapOf("transactions:a" to "other")))
        assertEquals(listOf("food" to "Alimentação", "other" to "Lazer > Outros"), ReviewRules.reviewCategoryOptions(options, item, "food"))
        // Receita: so as de receita (e as dos dois tipos).
        assertEquals(listOf("salary", "other"), ReviewRules.reviewCategoryOptions(options, review(type = "REFUND", categoryId = "salary"), "salary").map { it.first })
        // A sugerida so pelo nome (sem id) entra no alto.
        val nameOnly = review(category = "Padaria")
        assertEquals("" to "Padaria", ReviewRules.reviewCategoryOptions(options, nameOnly, "").first())
        assertEquals("" to "Sem categoria", ReviewRules.reviewCategoryOptions(options, review(), "").first())
    }

    @Test
    fun theListShowsFiveAndConfirmedOnesLeave() {
        val items = (1..7).map { review(id = "i$it") }
        assertEquals(5, ReviewRules.visibleItems(items, showAll = false).size)
        assertEquals(7, ReviewRules.visibleItems(items, showAll = true).size)
        assertEquals(listOf("i1", "i3", "i4", "i5", "i6", "i7"), ReviewRules.withoutConfirmed(items, listOf(items[1])).map { it.id })
        assertEquals("Confirmado.", ReviewRules.confirmedText(1))
        assertEquals("3 lançamentos confirmados.", ReviewRules.confirmedText(3))
        assertEquals("Extrato · 3", ReviewRules.tabLabel("Extrato", 3))
        assertEquals("Extrato", ReviewRules.tabLabel("Extrato", 0))
    }

    private fun waiting(
        entryType: String? = "TRANSFER",
        direction: String? = "OUT",
        needs: List<String> = listOf("transfer_account"),
        accountId: String? = "itau",
        transferAccountId: String? = null,
    ) = InboxItemDto(
        id = "w1", version = 4, state = "PENDING", entryType = entryType, direction = direction, amount = BigDecimal("250"),
        occurredAt = "2026-10-27T09:15:00-03:00", description = "Pix para Ana", accountId = accountId, accountName = accountId?.let { "Itaú" },
        transferAccountId = transferAccountId, needs = needs,
    )

    @Test
    fun aTransferWithOneSideAsksForTheOtherAccount() {
        val item = waiting()
        assertEquals(listOf(ReviewRules.WaitingFix.TRANSFER_ACCOUNT), ReviewRules.waitingFixes(item))
        assertFalse(ReviewRules.waitingNeedsComputer(item))
        assertEquals("Para qual conta?", ReviewRules.waitingReason(item))
        assertEquals("27/10/2026 às 09:15 · Itaú → ?", ReviewRules.waitingLine(item))
        assertEquals("Para qual conta?", ReviewRules.waitingMissing(item, null, null, null))
        assertEquals("", ReviewRules.waitingMissing(item, null, "btg", null))
        assertEquals(
            """{"version":4,"remember":false,"transfer_account_id":"btg"}""",
            JsonBody.encode(ReviewRules.waitingApproveBody(item, null, "btg", null)),
        )
        // A entrada sem a origem pergunta a conta de onde saiu.
        val incoming = waiting(direction = "IN", needs = listOf("account"), accountId = null, transferAccountId = "itau")
        assertEquals(listOf(ReviewRules.WaitingFix.ACCOUNT), ReviewRules.waitingFixes(incoming))
        assertEquals("Qual conta?", ReviewRules.waitingMissing(incoming, "", null, null))
    }

    @Test
    fun aTransferThatIsNotBetweenOwnAccountsBecomesExpenseOrIncome() {
        val item = waiting()
        assertTrue(ReviewRules.waitingCanBeSingle(item))
        assertEquals("EXPENSE", ReviewRules.singleType(item))
        assertEquals("INCOME", ReviewRules.singleType(waiting(direction = "IN")))
        assertEquals("""{"version":4,"remember":false,"entry_type":"EXPENSE"}""", JsonBody.encode(ReviewRules.waitingSingleBody(item)))
        assertFalse(ReviewRules.waitingCanBeSingle(waiting(entryType = "EXPENSE", needs = emptyList())))
        // Sem nenhuma das pontas nao ha conta para gravar.
        assertFalse(ReviewRules.waitingCanBeSingle(waiting(accountId = null)))
    }

    @Test
    fun anotherCurrencyAsksTheAmountInReais() {
        val item = waiting(entryType = "CARD", needs = listOf("amount"))
        assertEquals(listOf(ReviewRules.WaitingFix.AMOUNT), ReviewRules.waitingFixes(item))
        assertEquals("Informe o valor em reais.", ReviewRules.waitingMissing(item, null, null, null))
        assertEquals("Informe o valor em reais.", ReviewRules.waitingMissing(item, null, null, BigDecimal.ZERO))
        assertEquals("", ReviewRules.waitingMissing(item, null, null, BigDecimal("123.45")))
        assertEquals(
            """{"version":4,"remember":false,"amount":123.45}""",
            JsonBody.encode(ReviewRules.waitingApproveBody(item, null, null, BigDecimal("123.45"))),
        )
    }

    @Test
    fun aPixToTheGlobalAccountAsksWhatArrivedInDollars() {
        // A ponta em reais de um Pix para a Wise (047): o servidor recusa sem o valor em dolar.
        val accounts = listOf(
            AccountDto(id = "btg", name = "BTG conta corrente"),
            AccountDto(id = "wise", name = "Wise", currency = "USD"),
            AccountDto(id = "itau", name = "Itaú"),
        )
        val pix = waiting(needs = emptyList(), accountId = "btg", transferAccountId = "wise")
        assertEquals("USD", ReviewRules.waitingTransferCurrency(pix, accounts, null, null))
        assertEquals("Informe quanto entrou em USD.", ReviewRules.waitingMissing(pix, null, null, null, "USD", null))
        assertEquals("", ReviewRules.waitingMissing(pix, null, null, null, "USD", BigDecimal("46.10")))
        assertEquals(
            """{"version":4,"remember":false,"transfer_amount":46.10}""",
            JsonBody.encode(ReviewRules.waitingApproveBody(pix, null, null, null, BigDecimal("46.10"))),
        )
        // A outra ponta escolhida no celular tambem conta; mesma moeda, ou o dolar ja trazido, nada.
        val open = waiting(accountId = "btg")
        assertEquals("USD", ReviewRules.waitingTransferCurrency(open, accounts, null, "wise"))
        assertNull(ReviewRules.waitingTransferCurrency(open, accounts, null, "itau"))
        assertNull(ReviewRules.waitingTransferCurrency(open, accounts, null, null))
        assertNull(ReviewRules.waitingTransferCurrency(pix.copy(transferAmount = BigDecimal("46.10")), accounts, null, null))
        assertNull(ReviewRules.waitingTransferCurrency(pix.copy(entryType = "EXPENSE"), accounts, null, null))
    }

    @Test
    fun whatThePhoneDoesNotAskGoesToTheComputer() {
        val item = waiting(entryType = null, needs = listOf("method"))
        assertTrue(ReviewRules.waitingNeedsComputer(item))
        assertEquals(emptyList<ReviewRules.WaitingFix>(), ReviewRules.waitingFixes(item))
        assertFalse(ReviewRules.waitingCanBeSingle(item))
        // Um item completo (Gravar sozinho desligado) grava como esta.
        val ready = waiting(entryType = "EXPENSE", needs = emptyList())
        assertEquals("", ReviewRules.waitingMissing(ready, null, null, null))
        assertEquals("""{"version":4,"remember":false}""", JsonBody.encode(ReviewRules.waitingApproveBody(ready, null, null, null)))
        assertEquals("Pix para Ana", ReviewRules.waitingTitle(ready))
        assertEquals("Transferência", ReviewRules.waitingTitle(waiting().copy(description = null)))
    }

    @Test
    fun theOtherSideIsAnActiveAccountThatIsNotThisOne() {
        val accounts = listOf(
            AccountDto(id = "itau", name = "Itaú"),
            AccountDto(id = "btg", name = "BTG"),
            AccountDto(id = "old", name = "Antiga", archivedAt = "2026-01-01"),
        )
        assertEquals(listOf("btg"), ReviewRules.waitingAccountOptions(accounts, waiting()).map { it.id })
    }
}
