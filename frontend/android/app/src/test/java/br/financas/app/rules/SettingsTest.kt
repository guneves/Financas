// O que pages/ajustes/ faz inline (sem par no node): ver Settings.kt.
package br.financas.app.rules

import br.financas.app.core.MoneyInput
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

class SettingsTest {

    @Test
    fun rotulosComoNaWeb() {
        assertEquals("Conta corrente", Settings.accountTypeLabel("CHECKING"))
        assertEquals("Corretora", Settings.accountTypeLabel("BROKERAGE"))
        assertEquals("XPTO", Settings.accountTypeLabel("XPTO"))
        assertEquals("Ambos", Settings.categoryKindLabel("BOTH"))
        assertEquals(listOf("CHECKING", "SAVINGS", "BROKERAGE", "CASH", "OTHER"), Settings.ACCOUNT_TYPES.map { it.first })
    }

    @Test
    fun saldoEmReais() {
        assertEquals(0, BigDecimal("10.5").compareTo(Settings.accountBalanceBrl(BigDecimal("10.5"), BigDecimal("10.5"), "BRL")))
        assertEquals(0, BigDecimal("55").compareTo(Settings.accountBalanceBrl(BigDecimal("10"), BigDecimal("55"), "USD")))
        assertNull(Settings.accountBalanceBrl(BigDecimal("10"), null, "USD"))
        assertEquals(0, BigDecimal("7").compareTo(Settings.accountBalanceBrl(BigDecimal("7"), null, "BRL")))
        assertEquals(0, BigDecimal.ZERO.compareTo(Settings.accountBalanceBrl(null, null, null)))
    }

    @Test
    fun saldoInicialComSinal() {
        assertEquals(MoneyInput.Amount(BigDecimal("-150.5")), Settings.parseBalanceInput("-150,50"))
        assertEquals(MoneyInput.Amount(BigDecimal("1500")), Settings.parseBalanceInput("1.500"))
        assertEquals(MoneyInput.Empty, Settings.parseBalanceInput(" "))
        assertEquals(MoneyInput.Invalid, Settings.parseBalanceInput("-abc"))
        assertEquals(MoneyInput.Empty, Settings.parseBalanceInput("-"))
    }

    @Test
    fun oMenuDaConta() {
        assertEquals(Settings.AccountMenu(makeDefault = true, linkToPortfolio = true, unlinkFromPortfolio = false), Settings.accountMenu("CHECKING", false, "BRL"))
        assertEquals(Settings.AccountMenu(makeDefault = false, linkToPortfolio = false, unlinkFromPortfolio = false), Settings.accountMenu("CHECKING", true, "BRL"))
        assertEquals(Settings.AccountMenu(makeDefault = false, linkToPortfolio = false, unlinkFromPortfolio = true), Settings.accountMenu("BROKERAGE", false, "BRL"))
        assertEquals(Settings.AccountMenu(makeDefault = true, linkToPortfolio = false, unlinkFromPortfolio = false), Settings.accountMenu("SAVINGS", false, "USD"))
    }

    @Test
    fun fechamentoSugerido() {
        assertEquals("3", Settings.suggestedClosingDay("10"))
        assertEquals("29", Settings.suggestedClosingDay("6"))
        assertEquals("23", Settings.suggestedClosingDay("30"))
        assertEquals("30", Settings.suggestedClosingDay("7"))
        assertEquals("", Settings.suggestedClosingDay(""))
        assertEquals("", Settings.suggestedClosingDay("x"))
    }

    @Test
    fun avisosDoCartao() {
        assertEquals(
            "Débito automático do \"Nubank\" ligado: a fatura será paga no vencimento, dia 10, com saldo de Itaú.",
            Settings.autopayNotice("Nubank", 10, "Itaú"),
        )
        assertEquals("Débito automático do \"Nubank\" desligado.", Settings.autopayNotice("Nubank", 10, null))
        assertEquals("Vence dia 10 • Fecha dia 3 • Débito em Itaú", Settings.cardDetail(true, 10, 3, "Itaú"))
        assertEquals("Débito em Itaú", Settings.cardDetail(false, 1, 1, "Itaú"))
        assertEquals("Vence dia 10 • Fecha dia 3", Settings.cardDetail(true, 10, 3, null))
    }

    @Test
    fun nomeDeUsuario() {
        assertTrue(Settings.canSaveUsername(" Ana ", null))
        assertFalse(Settings.canSaveUsername("Ana", "Ana"))
        assertFalse(Settings.canSaveUsername("A", null))
        assertTrue(Settings.canSaveUsername("Bia", "Ana"))
    }
}
