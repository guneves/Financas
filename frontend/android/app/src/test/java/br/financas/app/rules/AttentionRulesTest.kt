// Port: mudou um, muda o outro, com um teste de cada lado.
// Os casos de frontend/src/lib/attentionRules.test.js, na mesma ordem; o nome do teste do node vai
// no comentario de cada um.
package br.financas.app.rules

import br.financas.app.rules.AttentionRules.MAX_DISMISSED_KEYS
import br.financas.app.rules.AttentionRules.addDismissed
import br.financas.app.rules.AttentionRules.attentionLink
import br.financas.app.rules.AttentionRules.attentionText
import br.financas.app.rules.AttentionRules.bellBadge
import br.financas.app.rules.AttentionRules.bellLabel
import br.financas.app.rules.AttentionRules.invoiceMonthKey
import br.financas.app.rules.AttentionRules.isPastDue
import br.financas.app.rules.AttentionRules.overdueDetail
import br.financas.app.rules.AttentionRules.undismissedItems
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

class AttentionRulesTest {
    private fun item(key: String, kind: String) = AttentionItem(key = key, kind = kind)

    private fun money(text: String) = BigDecimal(text)

    private val nbsp = " "

    // node: 'dispensar esconde so os casos dispensados'
    @Test
    fun dismissingHidesOnlyTheDismissedCases() {
        val items = listOf(item("recorrencias:3@x2", "RECURRING"), item("orcamento:2026-10:1", "OVER_BUDGET"))
        val dismissed = addDismissed(emptyList(), listOf(items[0].key))
        assertEquals(listOf("OVER_BUDGET"), undismissedItems(items, dismissed) { it.key }.map { it.kind })
        // Um caso novo (outra chave) volta.
        assertEquals(1, undismissedItems(listOf(item("recorrencias:3@2026-10-01x1", "RECURRING")), dismissed) { it.key }.size)
    }

    // node: 'a lista de dispensados nao cresce sem fim e nao repete'
    @Test
    fun theDismissedListIsBoundedAndHasNoRepeats() {
        val many = (0 until MAX_DISMISSED_KEYS + 5).map { "k$it" }
        val kept = addDismissed(emptyList(), many)
        assertEquals(MAX_DISMISSED_KEYS, kept.size)
        assertEquals("k${MAX_DISMISSED_KEYS + 4}", kept.last())
        assertEquals(listOf("b", "a"), addDismissed(listOf("a", "b"), listOf("a")))
    }

    // node: 'o texto da fatura vencida: uma, ou a mais antiga de varias'
    @Test
    fun theOverdueTextNamesOneOrTheOldest() {
        val nubank = AttentionInvoice(cardName = "Nubank", dueDate = "2026-10-10")
        assertEquals("Nubank · venceu em 10/10/2026", overdueDetail(listOf(nubank)))
        assertEquals(
            "2 faturas · a mais antiga venceu em 10/10/2026",
            overdueDetail(listOf(nubank, AttentionInvoice(cardName = "Itaú", dueDate = "2026-10-25"))),
        )
    }

    // node: 'vencida so depois do dia do vencimento; o mes da fatura com zero'
    @Test
    fun pastDueOnlyAfterTheDueDayAndTheInvoiceMonthIsPadded() {
        assertFalse(isPastDue("2026-11-10", "2026-11-10"))
        assertTrue(isPastDue("2026-11-10", "2026-11-11"))
        assertFalse(isPastDue(null, "2026-11-11"))
        assertEquals("2026-09", invoiceMonthKey(2026, 9))
    }

    // node: 'o texto de cada aviso, com os numeros do servidor'
    @Test
    fun theTextOfEachItem() {
        val overdue = AttentionItem(
            key = "fatura-vencida:x",
            kind = "INVOICE_OVERDUE",
            total = money("1234.5"),
            itemCount = 3,
            invoices = listOf(AttentionInvoice(cardName = "Nubank", dueDate = "2026-10-10")),
        )
        assertEquals(
            AttentionText("Fatura vencida: R$${nbsp}1.234,50", "Nubank · venceu em 10/10/2026 · 3 lançamento(s)"),
            attentionText(overdue),
        )
        assertEquals(
            AttentionText("Fatura fechada: R$${nbsp}80,00", "O pagamento já está liberado."),
            attentionText(AttentionItem(key = "k", kind = "INVOICE_PAYABLE", total = money("80"))),
        )
        assertEquals(AttentionText("1 recorrência vencida", ""), attentionText(AttentionItem(key = "k", kind = "RECURRING", count = 1)))
        assertEquals(AttentionText("4 recorrências vencidas", ""), attentionText(AttentionItem(key = "k", kind = "RECURRING", count = 4)))
        assertEquals(
            AttentionText("Alimentação › Mercado passou do orçamento", "R$${nbsp}650,00 de R$${nbsp}600,00"),
            attentionText(
                AttentionItem(key = "k", kind = "OVER_BUDGET", categoryName = "Alimentação › Mercado", spent = money("650"), available = money("600")),
            ),
        )
        assertEquals(AttentionText("", ""), attentionText(AttentionItem(key = "k", kind = "OUTRO")))
    }

    // node: 'debito automatico sem saldo: o saldo e o que falta somem no modo privado'
    @Test
    fun theShortfallHidesTheBalanceInPrivacyMode() {
        val shortfall = AttentionItem(
            key = "k",
            kind = "AUTOPAY_SHORTFALL",
            accountName = "Itaú",
            total = money("900"),
            balance = money("300.1"),
            missing = money("599.9"),
            firstDue = "2026-11-05",
        )
        assertEquals(
            AttentionText(
                "Débito automático sem saldo: faltam R$${nbsp}599,90",
                "Itaú tem R$${nbsp}300,10 para R$${nbsp}900,00 a debitar · o primeiro em 05/11/2026",
            ),
            attentionText(shortfall),
        )
        assertEquals(
            AttentionText(
                "Débito automático sem saldo: faltam R$ ••••••",
                "Itaú tem R$ •••••• para R$${nbsp}900,00 a debitar · o primeiro em 05/11/2026",
            ),
            attentionText(shortfall) { "R$ ••••••" },
        )
    }

    // node: 'para onde cada aviso leva'
    @Test
    fun whereEachItemLeads() {
        assertEquals(AttentionLink("/lancamentos/cartoes", "Ver faturas"), attentionLink("INVOICE_OVERDUE"))
        assertEquals(AttentionLink("/lancamentos/cartoes", "Ver faturas"), attentionLink("AUTOPAY_SHORTFALL"))
        assertEquals(AttentionLink("/planejamento/recorrentes", "Ver recorrentes"), attentionLink("RECURRING"))
        assertEquals(AttentionLink("/planejamento/orcamento", "Ver orçamento"), attentionLink("OVER_BUDGET"))
        assertNull(attentionLink("OUTRO"))
        assertEquals(5, AttentionRules.linkCount)
    }

    // node: 'o selo do sino: todos os avisos, 9+ acima de nove'
    @Test
    fun theBellBadge() {
        assertEquals("", bellBadge(0))
        assertEquals("1", bellBadge(1))
        assertEquals("9", bellBadge(9))
        assertEquals("9+", bellBadge(10))
        assertEquals("Precisa de atenção: nenhum aviso", bellLabel(0))
        assertEquals("Precisa de atenção: 1 aviso", bellLabel(1))
        assertEquals("Precisa de atenção: 3 avisos", bellLabel(3))
    }
}
