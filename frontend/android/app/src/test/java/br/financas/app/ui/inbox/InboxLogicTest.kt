// Port: mudou um, muda o outro, com um teste de cada lado.
// O que pages/lancamentos/Aprovar.jsx monta inline (sem teste no node): os casos saem do JSX.
package br.financas.app.ui.inbox

import br.financas.app.core.MINUS
import br.financas.app.core.NBSP
import br.financas.app.data.AccountDto
import br.financas.app.data.ApiJson
import br.financas.app.data.CreditCardDto
import br.financas.app.data.InboxCandidateDto
import br.financas.app.data.InboxHintDto
import br.financas.app.data.InboxItemDto
import br.financas.app.data.InboxSourceDto
import br.financas.app.data.InboxTargetDto
import br.financas.app.data.JsonBody
import br.financas.app.rules.CategoryOption
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal
import java.time.ZoneId

class InboxLogicTest {

    private fun item(
        id: String = "i1",
        version: Int? = 3,
        state: String = "PENDING",
        entryType: String? = "EXPENSE",
        direction: String? = "OUT",
        amount: String = "45.90",
        category: String? = null,
        categoryId: String? = null,
    ) = InboxItemDto(
        id = id,
        version = version,
        state = state,
        entryType = entryType,
        direction = direction,
        amount = BigDecimal(amount),
        occurredAt = "2026-10-17T22:30:00-03:00",
        category = category,
        categoryId = categoryId,
    )

    private val notification = InboxSourceDto(
        source = "notification", id = "d1", role = "SOURCE", app = "com.itau", appLabel = "Itaú",
        kind = "CREDIT_PURCHASE", occurredAt = "2026-10-17T22:30:00-03:00", cardLast4 = "1234",
    )

    @Test
    fun approveMatchAndSplitBodiesCarryTheVersion() {
        val it = item()
        assertEquals("""{"version":3,"remember":true}""", JsonBody.encode(InboxLogic.approveBody(it, true)))
        assertEquals(
            """{"version":3,"remember":false,"candidate":{"table":"cc_expenses","id":"e1"}}""",
            JsonBody.encode(InboxLogic.matchBody(it, InboxCandidateDto(table = "cc_expenses", id = "e1"), false)),
        )
        assertEquals(
            """{"version":3,"source":"notification","source_id":"d1"}""",
            JsonBody.encode(InboxLogic.splitBody(it, notification)),
        )
        // Sem versao, a chave nao vai.
        assertEquals("""{"remember":true}""", JsonBody.encode(InboxLogic.approveBody(item(version = null), true)))
    }

    @Test
    fun aDecisionReplacesOrRemovesTheItemInEachView() {
        val a = item("a")
        val b = item("b")
        val bUpdated = item("b", version = 4)
        val bApproved = item("b", version = 5, state = "APPROVED")

        assertEquals(listOf(a, bUpdated), InboxLogic.applyDecision(listOf(a, b), bUpdated, pendingView = true))
        assertEquals(listOf(a), InboxLogic.applyDecision(listOf(a, b), bApproved, pendingView = true))
        // Decidido: entra na lista de decididos so pela releitura; um restaurado sai dela.
        assertEquals(listOf(a), InboxLogic.applyDecision(listOf(a), bApproved, pendingView = false))
        assertEquals(emptyList<InboxItemDto>(), InboxLogic.applyDecision(listOf(bApproved), item("b", version = 6), pendingView = false))
        // Pendente que nao estava (o split, a notificacao): entra no alto.
        assertEquals(listOf(bUpdated, a), InboxLogic.applyDecision(listOf(a), bUpdated, pendingView = true))
        assertNull(InboxLogic.applyDecision(null, a, pendingView = true))
    }

    @Test
    fun theAmountIsSignedByDirectionAndTheTransferUnsigned() {
        assertEquals("${MINUS}R\$${NBSP}45,90", InboxLogic.amountText(item()))
        assertEquals("+R\$${NBSP}45,90", InboxLogic.amountText(item(entryType = "INCOME", direction = "IN")))
        assertEquals("R\$${NBSP}45,90", InboxLogic.amountText(item(entryType = "TRANSFER")))
        assertEquals("${MINUS}R\$${NBSP}1.234,56", InboxLogic.amountText(item(entryType = null, amount = "1234.56")))
    }

    @Test
    fun theSourceLine() {
        assertEquals(
            "Notificação Itaú · compra no crédito · final 1234 · 17/10/2026 às 22:30",
            InboxLogic.sourceLine(notification),
        )
        assertEquals(
            "Notificação Samsung Wallet · Itaú Visa · 17/10/2026 às 22:31 · mesma compra",
            InboxLogic.sourceLine(
                InboxSourceDto(
                    source = "notification", id = "d2", role = "PAIRED", app = "com.samsung.android.spay",
                    appLabel = "Samsung Wallet", occurredAt = "2026-10-17T22:31:00-03:00", cardName = "Itaú Visa",
                ),
            ),
        )
        // Uma fonte que nao e notificacao mostra a data dela.
        assertEquals("Notificação import · 05/10/2026", InboxLogic.sourceLine(InboxSourceDto(source = "import", app = "import", date = "2026-10-05")))
    }

    @Test
    fun theCandidateRow() {
        val card = InboxCandidateDto(
            table = "cc_expenses", id = "e1", kind = "card_purchase", date = "2026-10-17",
            amount = BigDecimal("45.9"), description = "Padaria", installmentInfo = "1/3", cardName = "Itaú Visa",
        )
        assertEquals("Padaria", InboxLogic.candidateTitle(card))
        assertEquals("Compra no cartão · 17/10/2026 · R\$${NBSP}45,90 · parcela 1/3 · Itaú Visa", InboxLogic.candidateLine(card))

        val transfer = InboxCandidateDto(
            kind = "transfer", date = "2026-10-01", amount = BigDecimal("100"),
            accountName = "Itaú", transferAccountName = "BTG",
        )
        assertEquals("Transferência", InboxLogic.candidateTitle(transfer))
        assertEquals("Transferência · 01/10/2026 · R\$${NBSP}100,00 · Itaú → BTG", InboxLogic.candidateLine(transfer))
        assertEquals("Mercado", InboxLogic.candidateTitle(InboxCandidateDto(category = "Mercado")))
        assertEquals("Lançamento · - · R\$${NBSP}0,00", InboxLogic.candidateLine(InboxCandidateDto()))
    }

    @Test
    fun theDecidedRow() {
        val approved = item(state = "APPROVED").copy(description = "Padaria", target = InboxTargetDto(table = "transactions", date = "2026-10-18"))
        assertEquals("Padaria", InboxLogic.itemTitle(approved))
        assertEquals("Aprovado · 17/10/2026 às 22:30 · R\$${NBSP}45,90 · lançado em 18/10/2026", InboxLogic.decidedLine(approved))
        // Mesma data do aviso: sem "lançado em".
        val sameDay = approved.copy(target = InboxTargetDto(date = "2026-10-17"))
        assertEquals("Aprovado · 17/10/2026 às 22:30 · R\$${NBSP}45,90", InboxLogic.decidedLine(sameDay))
        val matched = item(state = "MATCHED").copy(reason = "created_elsewhere")
        assertEquals("Lançado pelo \"+ Novo\" · 17/10/2026 às 22:30 · R\$${NBSP}45,90", InboxLogic.decidedLine(matched))
        assertEquals("Despesa", InboxLogic.itemTitle(item()))
        assertTrue(InboxLogic.restorable(item(state = "DENIED")))
        assertFalse(InboxLogic.restorable(approved))
    }

    @Test
    fun theHintUsageInTheLocalDate() {
        val saoPaulo = ZoneId.of("America/Sao_Paulo")
        val hint = InboxHintDto(id = "h1", uses = 1, createdAt = "2026-10-18T02:00:00.000Z")
        // 02:00 UTC e 23:00 do dia anterior em Sao Paulo.
        assertEquals("Usada 1 vez · desde 17/10/2026", InboxLogic.hintUsage(hint, saoPaulo))
        assertEquals("Usada 3 vezes · desde 18/10/2026", InboxLogic.hintUsage(hint.copy(uses = 3), ZoneId.of("UTC")))
        assertEquals("05/10/2026", InboxLogic.hintDate("2026-10-05 10:00:00", saoPaulo))
        assertEquals("-", InboxLogic.hintDate(null, saoPaulo))
    }

    @Test
    fun theEditCategoryOptionsKeepTheItemsOwnCategory() {
        val options = listOf(
            CategoryOption("food", "Alimentação", "Alimentação", "EXPENSE", null),
            CategoryOption("salary", "Salário", "Salário", "INCOME", null),
            CategoryOption("other", "Outros", "Lazer > Outros", "BOTH", "fun"),
        )
        val expense = item(categoryId = "food", category = "Alimentação")
        assertEquals(listOf("food" to "Alimentação", "other" to "Lazer > Outros"), InboxLogic.editCategoryOptions(options, "EXPENSE", expense))
        // Trocou para receita: a categoria de despesa do item fica como opcao, com o nome dele.
        assertEquals(
            listOf("food" to "Alimentação", "salary" to "Salário", "other" to "Lazer > Outros"),
            InboxLogic.editCategoryOptions(options, "INCOME", expense),
        )
        // So o nome (sem id): a opcao "do item".
        val nameOnly = item(category = "Padaria")
        assertEquals("__item__" to "Padaria", InboxLogic.editCategoryOptions(options, "EXPENSE", nameOnly).first())
    }

    @Test
    fun thePickersShowCreditCardsAndActiveAccountsOnly() {
        val cards = ApiJson.decodeFromString(
            kotlinx.serialization.builtins.ListSerializer(CreditCardDto.serializer()),
            """[{"id":"c1","name":"Itaú Visa"},{"id":"c2","name":"Flash","credit_enabled":0,"debit_account_id":"a9"},
                {"id":"c3","name":"BB","credit_enabled":1,"debit_account_id":"a1"}]""",
        )
        assertEquals(listOf("c1", "c3"), InboxLogic.pickerCards(cards).map { it.id })
        val accounts = listOf(
            AccountDto(id = "a1", name = "Itaú"),
            AccountDto(id = "a2", name = "Velha", archivedAt = "2026-01-01"),
            AccountDto(id = "a3", name = "BTG"),
        )
        val active = InboxLogic.activeAccounts(accounts)
        assertEquals(listOf("a1", "a3"), active.map { it.id })
        assertEquals(listOf("a3"), InboxLogic.destinationAccounts(active, "a1").map { it.id })
        assertEquals(listOf("a1", "a3"), InboxLogic.destinationAccounts(active, null).map { it.id })
    }

    @Test
    fun theMenuOnlyWithSourcesToSplit() {
        val paired = notification.copy(id = "d2", role = "PAIRED", app = "com.samsung.android.spay")
        val two = item().copy(sources = listOf(notification, paired))
        assertTrue(InboxLogic.showsMenu(two))
        assertEquals(listOf("d1", "d2"), InboxLogic.splittable(two).map { it.id })
        assertFalse(InboxLogic.showsMenu(item().copy(sources = listOf(notification))))
        assertTrue(InboxLogic.approvesAsNew(item().copy(candidates = listOf(InboxCandidateDto(id = "e1")))))
        assertFalse(InboxLogic.approvesAsNew(item()))
    }

    @Test
    fun theNotificationItemIsFoundInTheList() {
        val list = listOf(item("a"), item("b"))
        assertEquals(1, InboxLogic.indexOf(list, "b"))
        assertEquals(-1, InboxLogic.indexOf(list, "z"))
        assertEquals(-1, InboxLogic.indexOf(null, "a"))
        assertEquals(-1, InboxLogic.indexOf(list, null))
        assertEquals("i1:approve", InboxLogic.busyKey("i1", "approve"))
    }

    @Test
    fun theNotificationOnlyForNewOrMergedItems() {
        val body = """{"results":[
            {"key":"k1","status":"new","item_id":"i1"},
            {"key":"k2","status":"known","item_id":"i0"},
            {"key":"k3","status":"merged","item_id":"i2"},
            {"key":"k4","status":"repeated","item_id":"i2"},
            {"key":"k5","status":"invalid","error":"x"},
            {"key":"k6","status":"merged","item_id":"i1"},
            {"key":"k7","status":"declined","item_id":null}
        ]}"""
        assertEquals(listOf("i1", "i2"), InboxNotifier.newItemIds(body))
        assertEquals(emptyList<String>(), InboxNotifier.newItemIds("""{"results":[]}"""))
        assertEquals(emptyList<String>(), InboxNotifier.newItemIds("<html>"))
        assertEquals(emptyList<String>(), InboxNotifier.newItemIds(null))
    }
}
