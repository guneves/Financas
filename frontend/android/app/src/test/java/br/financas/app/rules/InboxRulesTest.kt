// Port: mudou um, muda o outro, com um teste de cada lado.
// Os casos de frontend/src/lib/inboxRules.test.js, na mesma ordem; o nome do teste do node vai no
// comentario de cada um (os de matchedInboxNotice chamam InboxNotice, que e o port dele). Os
// ultimos testes ("Sem par no node") cobrem o que o node nao testa: as regras soltas de
// frontend/src/pages/lancamentos/Aprovar.jsx e as bordas do corpo do PATCH.
package br.financas.app.rules

import br.financas.app.rules.InboxRules.ITEM_CATEGORY
import br.financas.app.rules.InboxRules.accountPickerLabel
import br.financas.app.rules.InboxRules.alreadyOpen
import br.financas.app.rules.InboxRules.ambiguousText
import br.financas.app.rules.InboxRules.amountSign
import br.financas.app.rules.InboxRules.approveReadySummary
import br.financas.app.rules.InboxRules.candidateKindLabel
import br.financas.app.rules.InboxRules.changesFromDraft
import br.financas.app.rules.InboxRules.composeOccurredAt
import br.financas.app.rules.InboxRules.decisionText
import br.financas.app.rules.InboxRules.decisionsWarn
import br.financas.app.rules.InboxRules.draftFromItem
import br.financas.app.rules.InboxRules.entryTypeLabel
import br.financas.app.rules.InboxRules.hintText
import br.financas.app.rules.InboxRules.itemCategoryOption
import br.financas.app.rules.InboxRules.needText
import br.financas.app.rules.InboxRules.offersRemember
import br.financas.app.rules.InboxRules.onlySamsung
import br.financas.app.rules.InboxRules.openPickers
import br.financas.app.rules.InboxRules.pendingNoticeText
import br.financas.app.rules.InboxRules.quickChoice
import br.financas.app.rules.InboxRules.readyIds
import br.financas.app.rules.InboxRules.reasonText
import br.financas.app.rules.InboxRules.recurringText
import br.financas.app.rules.InboxRules.recurringToggle
import br.financas.app.rules.InboxRules.showsDecisions
import br.financas.app.rules.InboxRules.sourceLabel
import br.financas.app.rules.InboxRules.splitOccurredAt
import br.financas.app.rules.InboxRules.splittableSources
import br.financas.app.rules.InboxRules.targetFields
import br.financas.app.rules.InboxRules.targetText
import br.financas.app.rules.InboxRules.whenText
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

class InboxRulesTest {
    private fun assertContains(part: String, text: String) =
        assertTrue("\"$text\" contem \"$part\"", text.contains(part))

    // As chaves na ordem em que o JS as poe no objeto (o JSON sai nessa ordem).
    private fun assertBody(expected: List<Pair<String, Any?>>, actual: Map<String, Any?>) =
        assertEquals(expected, actual.toList())

    private val item = InboxItem(
        id = "i1",
        version = 3,
        entryType = "CARD",
        direction = "OUT",
        amount = BigDecimal("45.9"),
        occurredAt = "2026-10-17T22:30:00-03:00",
        description = "PADARIA",
        category = "Outros",
        accountId = null,
        cardId = "c1",
        transferAccountId = null,
        installments = 1,
    )

    // node: 'the time is shown as the source said it, without converting the time zone'
    @Test
    fun theTimeIsShownAsTheSourceSaidIt() {
        assertEquals("17/10/2026 às 22:30", whenText("2026-10-17T22:30:00-03:00"))
        assertEquals("18/10/2026 às 01:30", whenText("2026-10-18T01:30:00+00:00"))
        assertEquals("10/10/2026", whenText("2026-10-10"))
        assertEquals("", whenText(""))
        assertEquals(InboxRules.OccurredAt("2026-10-10", ""), splitOccurredAt("2026-10-10"))
        assertEquals("2026-10-10T08:05", composeOccurredAt("2026-10-10", "08:05"))
        assertEquals("2026-10-10", composeOccurredAt("2026-10-10", ""))
    }

    // node: 'the edit sends only what changed, with the version'
    @Test
    fun theEditSendsOnlyWhatChangedWithTheVersion() {
        val draft = draftFromItem(item)
        assertBody(listOf("version" to 3), changesFromDraft(item, draft))
        assertBody(
            listOf(
                "version" to 3,
                "amount" to BigDecimal("50"),
                "occurred_at" to "2026-10-17T21:00",
                "description" to "Padaria",
            ),
            changesFromDraft(item, draft.copy(amount = "50", description = " Padaria ", time = "21:00")),
        )
        assertBody(listOf("version" to 3, "card_id" to null), changesFromDraft(item, draft.copy(cardId = "")))
        // O teclado do celular digita virgula; o do PC, ponto. Os dois valem.
        assertBody(listOf("version" to 3), changesFromDraft(item, draft.copy(amount = "45,90")))
        assertBody(
            listOf("version" to 3, "amount" to BigDecimal("1234.56")),
            changesFromDraft(item, draft.copy(amount = "1.234,56")),
        )
        assertBody(
            listOf("version" to 3, "amount" to BigDecimal("50.5")),
            changesFromDraft(item, draft.copy(amount = "R$ 50.5")),
        )
        // Sem tipo escolhido (compra vaga), nao manda tipo.
        val vague = item.copy(entryType = null)
        assertBody(listOf("version" to 3), changesFromDraft(vague, draftFromItem(vague)))
    }

    // node: 'a quick choice picks the type that goes with credit or debit'
    @Test
    fun aQuickChoicePicksTheTypeThatGoesWithCreditOrDebit() {
        assertBody(listOf("version" to 3, "entry_type" to "CARD"), quickChoice(item, QuickChoice(method = "CARD")))
        assertBody(listOf("version" to 3, "entry_type" to "EXPENSE"), quickChoice(item, QuickChoice(method = "DEBIT")))
        assertBody(
            listOf("version" to 3, "entry_type" to "INCOME"),
            quickChoice(item.copy(direction = "IN"), QuickChoice(method = "DEBIT")),
        )
        assertBody(listOf("version" to 3, "card_id" to "c2"), quickChoice(item, QuickChoice(cardId = "c2")))
    }

    // node: 'sources say where each report came from'
    @Test
    fun sourcesSayWhereEachReportCameFrom() {
        assertEquals(
            "Notificação Itaú · compra no crédito · final 1234",
            sourceLabel(InboxSource(source = "notification", appLabel = "Itaú", kind = "CREDIT_PURCHASE", cardLast4 = "1234")),
        )
        assertEquals(
            true,
            onlySamsung(InboxItem(sources = listOf(InboxSource(source = "notification", app = "com.samsung.android.spay")))),
        )
        assertEquals(
            false,
            onlySamsung(
                InboxItem(
                    sources = listOf(
                        InboxSource(source = "notification", app = "com.samsung.android.spay"),
                        InboxSource(source = "notification", app = "com.itau"),
                    ),
                ),
            ),
        )
    }

    // node: 'a transfer has no sign; money out is negative, money in positive'
    @Test
    fun aTransferHasNoSignMoneyOutIsNegativeMoneyInPositive() {
        assertEquals(-1, amountSign(item))
        assertEquals(1, amountSign(item.copy(direction = "IN", entryType = "INCOME")))
        assertEquals(0, amountSign(item.copy(entryType = "TRANSFER")))
        assertEquals("Crédito ou débito?", entryTypeLabel(null))
        assertEquals("Transferência", entryTypeLabel("TRANSFER"))
    }

    // node: 'only items with two or more live sources can be split'
    @Test
    fun onlyItemsWithTwoOrMoreLiveSourcesCanBeSplit() {
        assertEquals(
            emptyList<InboxSource>(),
            splittableSources(InboxItem(sources = listOf(InboxSource(source = "notification", role = "SOURCE")))),
        )
        val sources = listOf(
            InboxSource(source = "notification", role = "SOURCE"),
            InboxSource(source = "notification", role = "PAIRED"),
            InboxSource(source = "notification", role = "CANCELLED"),
        )
        assertEquals(2, splittableSources(InboxItem(sources = sources)).size)
        // Uma notificacao e uma transacao do Open Finance da mesma compra tambem se separam;
        // a que saiu do banco (REMOVED) nao conta.
        assertEquals(
            2,
            splittableSources(InboxItem(sources = listOf(
                InboxSource(source = "notification", role = "SOURCE"), InboxSource(source = "open_finance", role = "SOURCE"),
            ))).size,
        )
        assertEquals(
            emptyList<InboxSource>(),
            splittableSources(InboxItem(sources = listOf(
                InboxSource(source = "notification", role = "SOURCE"), InboxSource(source = "open_finance", role = "REMOVED"),
            ))),
        )
    }

    // node: 'an Open Finance source says the bank, the account and the installment'
    @Test
    fun anOpenFinanceSourceSaysTheBankTheAccountAndTheInstallment() {
        assertEquals(
            "Open Finance Itaú · Mastercard Black · LOJA X · parcela 1/3",
            sourceLabel(InboxSource(
                source = "open_finance", connectorName = "Itaú", accountName = "Mastercard Black", description = "LOJA X",
                installmentNumber = 1, totalInstallments = 3, role = "SOURCE",
            )),
        )
        assertEquals(
            "Open Finance BB · PIX · saiu do banco",
            sourceLabel(InboxSource(source = "open_finance", connectorName = "BB", description = "PIX", role = "REMOVED")),
        )
        assertEquals("Open Finance", sourceLabel(InboxSource(source = "open_finance")))
    }

    // node: 'ready items, remember and the texts'
    @Test
    fun readyItemsRememberAndTheTexts() {
        assertEquals(listOf("a"), readyIds(listOf(InboxItem(id = "a", ready = true), InboxItem(id = "b", ready = false))))
        assertEquals(true, offersRemember(InboxItem(needs = listOf("card"), confirm = emptyList())))
        assertEquals(false, offersRemember(InboxItem(needs = emptyList(), confirm = emptyList())))
        assertContains("não conta como entrada nem saída", reasonText(InboxItem(reason = "own_transfer")))
        assertContains("Com outra pessoa", reasonText(InboxItem(reason = "external_transfer")))
        assertEquals("", reasonText(InboxItem(reason = "new")))
        assertEquals("", pendingNoticeText(0))
        assertTrue(pendingNoticeText(2).startsWith("2 movimentos"))
        assertEquals("Compra negada pelo banco", decisionText(InboxItem(state = "REMOVED", reason = "declined")))
        assertEquals("Pagamento de fatura", candidateKindLabel("invoice_payment"))
        assertEquals("Lançamento", candidateKindLabel("?"))
        assertEquals("Lançado pelo \"+ Novo\"", decisionText(InboxItem(state = "MATCHED", reason = "created_elsewhere")))
        assertEquals(
            "2 aprovados, 1 ficou para você decidir.",
            approveReadySummary(ApproveReadyResult(approved = listOf("a", "b"), skipped = listOf(ApproveReadySkip(id = "c")))),
        )
        // matchedInboxNotice: o port e InboxNotice (InboxNoticeTest.kt tem os outros casos).
        assertEquals(
            true,
            InboxNotice.matchedInboxNotice(JSONObject().put("matched_inbox", true), "Despesa").startsWith("Despesa: já tinha chegado"),
        )
        assertEquals("", InboxNotice.matchedInboxNotice(JSONArray().put(JSONObject().put("id", "x")), "Compra"))
        assertEquals(
            "Samsung Wallet · sem crédito/débito · final 1234 → Itaú Visa",
            hintText(InboxHint(label = "Samsung Wallet · sem crédito/débito · final 1234", entryType = "CARD", cardName = "Itaú Visa")),
        )
    }

    // node: 'recurringText: the occurrence approving settles, the opt-out and the settled one'
    @Test
    fun recurringTextTheOccurrenceApprovingSettlesTheOptOutAndTheSettledOne() {
        val recurring = InboxRecurring(
            description = "Netflix",
            date = "2026-10-05",
            amount = BigDecimal("55.9"),
            exactAmount = true,
            settled = false,
        )
        assertEquals("", recurringText(InboxItem(recurring = null)))
        assertTrue(
            recurringText(InboxItem(recurring = recurring)).startsWith("Recorrente: ao aprovar, \"Netflix\" de 05/10 fica como feita"),
        )
        // O \s do JS casa o espaco inquebravel depois do "R$".
        assertContains("(previsto R$ 55,90)", recurringText(InboxItem(recurring = recurring.copy(exactAmount = false))))
        assertEquals(
            "Não marca \"Netflix\" de 05/10 em Recorrentes.",
            recurringText(InboxItem(recurring = recurring, recurringOff = true)),
        )
        assertEquals(
            "Marcou \"Netflix\" de 05/10 como feita em Recorrentes.",
            recurringText(InboxItem(recurring = recurring.copy(settled = true))),
        )
    }

    // node: 'recurringToggle: the PATCH body keeps the version'
    @Test
    fun recurringToggleThePatchBodyKeepsTheVersion() {
        assertBody(listOf("version" to 3, "recurring" to false), recurringToggle(InboxItem(version = 3), false))
        assertBody(listOf("version" to 4, "recurring" to true), recurringToggle(InboxItem(version = 4), true))
    }

    // node: 'the category goes by id: same name under two parents is two categories'
    @Test
    fun theCategoryGoesByIdSameNameUnderTwoParentsIsTwoCategories() {
        val withId = item.copy(category = "Outros", categoryId = "lazer-outros")
        val draft = draftFromItem(withId)
        assertEquals("lazer-outros", draft.categoryId)
        // Sem mexer na categoria, nada dela vai no pedido.
        assertBody(listOf("version" to 3, "description" to "Cinema"), changesFromDraft(withId, draft.copy(description = "Cinema")))
        assertBody(
            listOf("version" to 3, "category_id" to "raiz-outros"),
            changesFromDraft(withId, draft.copy(categoryId = "raiz-outros")),
        )
        // "Sugerida pelas regras" limpa as duas: o servidor escolhe ao aprovar.
        assertBody(
            listOf("version" to 3, "category" to null, "category_id" to null),
            changesFromDraft(withId, draft.copy(categoryId = "")),
        )
        // Um item so com o nome fica como esta ate o dono escolher outra.
        val nameOnly = draftFromItem(item)
        assertEquals(ITEM_CATEGORY, nameOnly.categoryId)
        assertBody(listOf("version" to 3), changesFromDraft(item, nameOnly))
        assertBody(listOf("version" to 3, "category_id" to "mercado"), changesFromDraft(item, nameOnly.copy(categoryId = "mercado")))
    }

    // node: 'targetText: where the item goes, only once it is known'
    @Test
    fun targetTextWhereTheItemGoesOnlyOnceItIsKnown() {
        assertEquals(
            "Itaú Conta corrente",
            targetText(InboxItem(entryType = "EXPENSE", accountId = "a1", accountName = "Itaú Conta corrente")),
        )
        assertEquals(
            "Itaú Visa · 3x",
            targetText(InboxItem(entryType = "CARD", cardId = "c1", cardName = "Itaú Visa", installments = 3)),
        )
        assertEquals(
            "Itaú → BTG",
            targetText(
                InboxItem(
                    entryType = "TRANSFER",
                    accountId = "a1",
                    accountName = "Itaú",
                    transferAccountId = "a2",
                    transferAccountName = "BTG",
                ),
            ),
        )
        // Falta escolher (ou credito/debito ainda aberto): nada, o seletor ja esta la.
        assertEquals("", targetText(InboxItem(entryType = "EXPENSE", accountId = null)))
        assertEquals("", targetText(InboxItem(entryType = "TRANSFER", accountId = "a1", transferAccountId = null)))
        assertEquals("", targetText(InboxItem(entryType = null, accountId = "a1")))
    }

    // node: 'targetFields: the pickers "Trocar" opens for each type'
    @Test
    fun targetFieldsThePickersTrocarOpensForEachType() {
        assertEquals(listOf("card"), targetFields(InboxItem(entryType = "CARD")))
        assertEquals(listOf("account"), targetFields(InboxItem(entryType = "INCOME")))
        assertEquals(listOf("account", "transfer_account"), targetFields(InboxItem(entryType = "TRANSFER")))
        assertEquals(emptyList<String>(), targetFields(InboxItem(entryType = null)))
    }

    // node: 'an ambiguous item never offers to remember, and says why'
    @Test
    fun anAmbiguousItemNeverOffersToRememberAndSaysWhy() {
        assertEquals(false, offersRemember(InboxItem(needs = listOf("account"), confirm = emptyList(), ambiguous = true)))
        assertContains("mais de uma conta neste banco", ambiguousText(InboxItem(ambiguous = true, entryType = "EXPENSE")))
        assertContains("mais de um cartão", ambiguousText(InboxItem(ambiguous = true, entryType = "CARD")))
        assertEquals("", ambiguousText(InboxItem(ambiguous = false)))
    }

    // Sem par no node: openPickers() de Aprovar.jsx (o que falta, o palpite e, depois de
    // "Trocar", todos os do tipo), a caixa de escolhas e o rotulo da conta.
    @Test
    fun openPickersShowWhatIsMissingTheGuessAndAllAfterTrocar() {
        val transfer = InboxItem(entryType = "TRANSFER", needs = listOf("transfer_account"), confirm = listOf("account"))
        assertEquals(listOf("account", "transfer_account"), openPickers(transfer, false))
        val guessedCard = InboxItem(entryType = "CARD", confirm = listOf("card"))
        assertEquals(listOf("card"), openPickers(guessedCard, false))
        val known = InboxItem(entryType = "EXPENSE", accountId = "a1")
        assertEquals(emptyList<String>(), openPickers(known, false))
        assertEquals(listOf("account"), openPickers(known, true))
        // Sem tipo (credito ou debito?), nenhum seletor: so a escolha do metodo.
        val vague = InboxItem(entryType = null, needs = listOf("method"))
        assertEquals(emptyList<String>(), openPickers(vague, true))
        assertTrue(showsDecisions(vague, false))
        assertTrue(decisionsWarn(vague, false))
        // Nada a decidir e sem "Trocar": nenhuma caixa.
        assertFalse(showsDecisions(known, false))
        // Depois de "Trocar" num item ja decidido: caixa neutra.
        assertTrue(showsDecisions(known, true))
        assertFalse(decisionsWarn(known, true))
        assertTrue(decisionsWarn(guessedCard, false))
        assertEquals("De qual conta?", accountPickerLabel(InboxItem(entryType = "TRANSFER")))
        assertEquals(needText("account"), accountPickerLabel(InboxItem(entryType = "EXPENSE")))
        assertEquals("Qual conta?", accountPickerLabel(null))
    }

    // Sem par no node: o "alreadyOpen" de TargetLine em Aprovar.jsx — o "Trocar" some quando todos
    // os seletores do tipo ja estao abertos.
    @Test
    fun theTrocarButtonHidesWhenEveryPickerIsAlreadyOpen() {
        val guessedCard = InboxItem(entryType = "CARD", cardId = "c1", confirm = listOf("card"))
        assertTrue(alreadyOpen(guessedCard, false))
        // Aberto pelo proprio "Trocar": o botao fica, para fechar.
        assertFalse(alreadyOpen(guessedCard, true))
        // Transferencia com so um dos dois aberto: "Trocar" abre o outro.
        val halfOpen = InboxItem(entryType = "TRANSFER", accountId = "a1", transferAccountId = "a2", confirm = listOf("account"))
        assertFalse(alreadyOpen(halfOpen, false))
        assertTrue(alreadyOpen(halfOpen.copy(needs = listOf("transfer_account")), false))
        // Nada aberto: "Trocar" aparece. Sem tipo: nao ha seletor, nao conta como aberto.
        assertFalse(alreadyOpen(InboxItem(entryType = "EXPENSE", accountId = "a1"), false))
        assertFalse(alreadyOpen(InboxItem(entryType = null), false))
    }

    // Sem par no node: a opcao extra de categoria na edicao (Aprovar.jsx, EditSheet).
    @Test
    fun theEditSheetKeepsTheItemsOwnCategoryWhenNotInTheList() {
        // So o nome: a opcao ITEM_CATEGORY com o nome do item.
        assertEquals(CategoryFallbackOption(ITEM_CATEGORY, "Outros"), itemCategoryOption(item, listOf("mercado", "lazer-outros")))
        // Com id que esta na lista: nenhuma opcao extra.
        val withId = item.copy(categoryId = "lazer-outros")
        assertNull(itemCategoryOption(withId, listOf("mercado", "lazer-outros")))
        // Com id fora da lista (arquivada ou de outro tipo): fica, com o nome do item.
        assertEquals(CategoryFallbackOption("lazer-outros", "Outros"), itemCategoryOption(withId, listOf("mercado")))
        // Sem categoria nenhuma: nada.
        assertNull(itemCategoryOption(item.copy(category = null), emptyList()))
    }

    // Sem par no node: as bordas do corpo do PATCH, lidas do JS.
    @Test
    fun theBodyEdgesFollowTheJs() {
        val draft = draftFromItem(item)
        assertEquals("45.9", draft.amount)
        assertEquals("1", draft.installments)
        // Valor apagado ou invalido: o JS manda null (o NaN vira null no JSON).
        assertBody(listOf("version" to 3, "amount" to null), changesFromDraft(item, draft.copy(amount = "")))
        assertBody(listOf("version" to 3, "amount" to null), changesFromDraft(item, draft.copy(amount = "1.2.3")))
        // Parcelas: o texto do campo vira numero; vazio e 1 (sem mudanca).
        assertBody(listOf("version" to 3, "installments" to 3L), changesFromDraft(item, draft.copy(installments = "3")))
        assertBody(listOf("version" to 3), changesFromDraft(item, draft.copy(installments = "")))
        // "0" e texto verdadeiro: Number("0") = 0 != 1, e o corpo leva Number("0") || 1 = 1.
        assertBody(listOf("version" to 3, "installments" to 1L), changesFromDraft(item, draft.copy(installments = "0")))
        // Descricao so de espacos: null (o servidor apaga).
        assertBody(listOf("version" to 3, "description" to null), changesFromDraft(item, draft.copy(description = "  ")))
        // Data trocada sem hora: so a data.
        assertBody(
            listOf("version" to 3, "occurred_at" to "2026-10-16"),
            changesFromDraft(item, draft.copy(date = "2026-10-16", time = "")),
        )
        // Sem versao no item, a chave nao vai (undefined some no JSON).
        assertBody(listOf("recurring" to true), recurringToggle(null, true))
        // Escolher "vazio" num seletor manda null; a escolha que nao veio nao entra.
        assertBody(listOf("version" to 3, "account_id" to null), quickChoice(item, QuickChoice(accountId = "")))
        assertEquals("Nada para aprovar.", approveReadySummary(null))
        assertEquals("1 aprovado.", approveReadySummary(ApproveReadyResult(approved = listOf("a"))))
        assertEquals(
            "0 aprovados, 2 ficaram para você decidir.",
            approveReadySummary(ApproveReadyResult(skipped = listOf(ApproveReadySkip("a"), ApproveReadySkip("b")))),
        )
        assertEquals("1 movimento do celular ou do banco espera sua aprovação.", pendingNoticeText(1))
        assertEquals("Saiu da lista", decisionText(InboxItem(state = "REMOVED")))
        assertEquals("Já estava lançado", decisionText(InboxItem(state = "MATCHED")))
        assertEquals("", whenText("17/10/2026"))
        assertEquals("transferência para ?", hintText(InboxHint(hintKey = "k", entryType = "TRANSFER")).substringAfter("→ "))
        assertEquals("k → conta removida (receita)", hintText(InboxHint(hintKey = "k", entryType = "INCOME")))
        assertEquals("Notificação com.itau · Pix enviado · Ana", sourceLabel(InboxSource(app = "com.itau", kind = "PIX_OUT", counterparty = "Ana")))
    }

    // node: 'an Open Finance source names the bank, not the MeuPluggy connector'
    @Test
    fun anOpenFinanceSourceNamesTheBankNotTheMeuPluggyConnector() {
        assertEquals(
            "Open Finance BTG Pactual · BTG Banking · PIX",
            sourceLabel(
                InboxSource(
                    source = "open_finance", connectorName = "MeuPluggy", bankName = "BTG Pactual",
                    accountName = "BTG Banking", description = "PIX",
                ),
            ),
        )
    }
}
