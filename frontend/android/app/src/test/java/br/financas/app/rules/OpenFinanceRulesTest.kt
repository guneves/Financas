package br.financas.app.rules

import java.math.BigDecimal
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** Os casos de frontend/src/lib/openFinance.test.js que o celular usa. */
class OpenFinanceRulesTest {

    // node: 'item status in Portuguese with the badge tone'
    @Test
    fun itemStatusInPortugueseWithTheBadgeTone() {
        assertEquals(OpenFinanceRules.Status("Atualizada", "success"), OpenFinanceRules.itemStatus("UPDATED", false))
        assertEquals("danger", OpenFinanceRules.itemStatus("LOGIN_ERROR", true).tone)
        assertEquals("Precisa de você no banco", OpenFinanceRules.itemStatus("UPDATED", true).label)
        assertEquals("NEW_THING", OpenFinanceRules.itemStatus("NEW_THING", false).label)
    }

    // node: "Pluggy's own message wins, then what the owner must do"
    @Test
    fun pluggysOwnMessageWinsThenWhatTheOwnerMustDo() {
        assertEquals("Seu plano permite apenas um CPF.", OpenFinanceRules.itemProblem("Seu plano permite apenas um CPF.", false, null))
        assertTrue(OpenFinanceRules.itemProblem(null, true, null).contains("Reconectar"))
        assertTrue(OpenFinanceRules.itemProblem(null, false, "timeout").contains("falhou: timeout"))
        assertEquals("", OpenFinanceRules.itemProblem(null, false, null))
    }

    // node: 'account labels show the card final'
    @Test
    fun accountLabelsShowTheCardFinal() {
        assertEquals("Mastercard Black · final 9437", OpenFinanceRules.accountLabel("CREDIT", "Mastercard Black", "5555 **** 9437"))
        assertEquals("Conta Corrente · 0001/12345-0", OpenFinanceRules.accountLabel("BANK", "Conta Corrente", "0001/12345-0"))
        assertEquals("Conta", OpenFinanceRules.accountLabel("BANK", null, null))
    }

    // node: 'balance check compares to the cent and never for cards'
    @Test
    fun balanceCheckComparesToTheCentAndNeverForCards() {
        assertEquals(
            OpenFinanceRules.BalanceCheck("match", BigDecimal("0.00")),
            OpenFinanceRules.balanceCheck("BANK", BigDecimal("1000"), BigDecimal("1000")),
        )
        assertEquals(
            OpenFinanceRules.BalanceCheck("drift", BigDecimal("0.10")),
            OpenFinanceRules.balanceCheck("BANK", BigDecimal("1000.1"), BigDecimal("1000")),
        )
        assertEquals("none", OpenFinanceRules.balanceCheck("CREDIT", BigDecimal("-800"), BigDecimal.ZERO).state)
        assertEquals("none", OpenFinanceRules.balanceCheck("BANK", BigDecimal("10"), null).state)
    }

    // node: 'sync summary'
    @Test
    fun syncSummary() {
        assertEquals(
            "2 movimentos novos no Aprovar, 1 juntou-se a um aviso, 1 saiu (o banco desfez).",
            OpenFinanceRules.syncSummary(mapOf("new" to 2, "merged" to 1), 1),
        )
        assertEquals("Nada novo.", OpenFinanceRules.syncSummary(mapOf("known" to 4), 0))
    }

    // node: 'sync hours labels and choices'
    @Test
    fun syncHoursLabelsAndChoices() {
        assertEquals("Desligada", OpenFinanceRules.syncHoursLabel(0))
        assertEquals("A cada 6 h", OpenFinanceRules.syncHoursLabel(6))
        assertEquals(listOf(0, 1, 3, 6, 12, 24), OpenFinanceRules.syncHoursChoices(6).map { it.first })
        assertEquals(listOf(0, 1, 2, 3, 6, 12, 24), OpenFinanceRules.syncHoursChoices(2).map { it.first })
        assertEquals(listOf(0, 1, 3, 6, 12, 24), OpenFinanceRules.syncHoursChoices(30).map { it.first })
        assertEquals(listOf(0, 1, 3, 6, 12, 24), OpenFinanceRules.syncHoursChoices(null).map { it.first })
    }

    // node: 'check summary'
    @Test
    fun checkSummary() {
        assertEquals(OpenFinanceRules.CheckSummary("none", ""), OpenFinanceRules.checkSummary(false, 0, 0, 0))
        assertEquals(OpenFinanceRules.CheckSummary("match", "Movimentos conferem"), OpenFinanceRules.checkSummary(true, 0, 0, 0))
        assertEquals(
            OpenFinanceRules.CheckSummary("match", "Movimentos conferem · 2 esperam no Aprovar"),
            OpenFinanceRules.checkSummary(true, 0, 0, 2),
        )
        assertEquals(
            OpenFinanceRules.CheckSummary("drift", "1 só no banco · 3 só no app · 1 espera no Aprovar"),
            OpenFinanceRules.checkSummary(true, 1, 3, 1),
        )
        assertEquals(OpenFinanceRules.CheckSummary("drift", "2 só no banco"), OpenFinanceRules.checkSummary(true, 2, 0, 0))
    }
}
