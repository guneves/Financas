// Port: mudou um, muda o outro, com um teste de cada lado.
// Os casos de frontend/src/lib/monthlyPlan.test.js do lado da entrada, na mesma ordem; o nome do
// teste do node vai no comentario de cada um. parseMoneyInput e moneyInputValue estao em
// MoneyInputTest.kt.
package br.financas.app.rules

import br.financas.app.core.MoneyInput
import br.financas.app.data.PlanFlagDto
import br.financas.app.rules.MonthlyPlan.categoryAmountPreview
import br.financas.app.rules.MonthlyPlan.clampPercent
import br.financas.app.rules.MonthlyPlan.flagText
import br.financas.app.rules.MonthlyPlan.formatPlanPercent
import br.financas.app.rules.MonthlyPlan.incomeReceivedText
import br.financas.app.rules.MonthlyPlan.livePlanText
import br.financas.app.rules.MonthlyPlan.livePlanTotals
import br.financas.app.rules.MonthlyPlan.percentOf
import br.financas.app.rules.MonthlyPlan.percentRoom
import br.financas.app.rules.MonthlyPlan.planFlagKey
import br.financas.app.rules.MonthlyPlan.sortFlags
import br.financas.app.rules.MonthlyPlan.spendStatus
import br.financas.app.rules.MonthlyPlan.stepPercent
import br.financas.app.rules.MonthlyPlan.unallocatedText
import br.financas.app.rules.MonthlyPlan.visibleFlags
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

class MonthlyPlanTest {

    private fun d(value: String) = BigDecimal(value)
    private fun n(value: String) = MoneyInput.Amount(BigDecimal(value))
    private val blank = MoneyInput.Empty

    private fun assertMoney(expected: String?, actual: BigDecimal?) {
        if (expected == null) {
            assertNull(actual)
            return
        }
        assertNotNull(actual)
        assertEquals("$actual", 0, BigDecimal(expected).compareTo(actual))
    }

    // Os testes de texto comparam sem o espaco de R$ (o Intl usa NBSP).
    private fun plain(text: String) = text.replace(' ', ' ')

    // node: 'cada codigo de alerta tem texto'
    @Test
    fun cadaCodigoDeAlertaTemTexto() {
        val codes = listOf(
            "PLAN_OVER_INCOME", "SPEND_OVER", "SPEND_PACE", "SPEND_NEAR", "SPEND_KEPT",
            "INVEST_DONE", "INVEST_PENDING", "INVEST_MISSED", "GOAL_SHORT", "GOAL_COVERED",
            "CATEGORIES_OVER_SPEND",
        )
        for (code in codes) {
            val text = flagText(PlanFlagDto(code = code, amount = d("100"), over = d("10"), missing = d("5"), daysLeft = 3, goalName = "Reserva", targetMonth = "2026-12"))
            assertTrue(code, text.length > 10)
        }
        assertTrue(flagText(PlanFlagDto(code = "GOAL_SHORT", amount = d("1000"), missing = d("400"), goalName = "Reserva", targetMonth = "2026-12")).contains("Reserva"))
        assertTrue(flagText(PlanFlagDto(code = "CATEGORIES_OVER_SPEND", amount = d("180"), percent = d("120.5"))).contains("120,5% do Gastar"))
    }

    // node: 'alertas que pedem acao vem primeiro'
    @Test
    fun alertasQuePedemAcaoVemPrimeiro() {
        val sorted = sortFlags(listOf(PlanFlagDto(code = "A", tone = "gain"), PlanFlagDto(code = "B", tone = "loss"), PlanFlagDto(code = "C", tone = "warning")))
        assertEquals(listOf("B", "C", "A"), sorted.map { it.code })
    }

    // node: 'spendStatus segue o alerta de gasto'
    @Test
    fun spendStatusSegueOAlertaDeGasto() {
        assertEquals(BudgetStatus.OVER, spendStatus(listOf(PlanFlagDto(code = "SPEND_OVER"))))
        assertEquals(BudgetStatus.WARNING, spendStatus(listOf(PlanFlagDto(code = "SPEND_PACE"))))
        assertEquals(BudgetStatus.OK, spendStatus(listOf(PlanFlagDto(code = "INVEST_DONE"))))
    }

    // node: 'percentOf arredonda meio-para-cima nos centavos, como percent_of() do servidor'
    @Test
    fun percentOfArredondaMeioParaCima() {
        assertMoney("1000", percentOf(d("5000"), d("20")))
        assertMoney("1666.67", percentOf(d("5000"), d("33.333333")))
        assertMoney("50.03", percentOf(d("100.05"), d("50"))) // 50,025 -> 50,03
        assertMoney("0.05", percentOf(d("0.1"), d("50")))
        assertMoney("0", percentOf(d("1234.56"), d("0")))
        assertMoney("375", percentOf(d("3000"), d("12.5")))
        assertMoney(null, percentOf(null, d("10")))
        assertMoney(null, percentOf(d("1000"), null))
    }

    // node: 'formatPlanPercent mostra ate duas casas, com virgula'
    @Test
    fun formatPlanPercentMostraAteDuasCasas() {
        assertEquals("20%", formatPlanPercent(d("20")))
        assertEquals("33,33%", formatPlanPercent(d("33.333333")))
        assertEquals("12,5%", formatPlanPercent(d("12.5")))
        assertEquals("0%", formatPlanPercent(null))
    }

    // node: 'unallocatedText: sobra da renda, ou quanto passa de 100%'
    @Test
    fun unallocatedTextSobraOuPassa() {
        assertEquals("Sem destino 15%", unallocatedText(d("15")))
        assertEquals("Sem destino 0%", unallocatedText(d("0")))
        assertEquals("Passa de 100% da renda em 5,5%", unallocatedText(d("-5.5")))
        assertEquals("", unallocatedText(null))
    }

    // node: 'incomeReceivedText compara o recebido com a renda planejada'
    @Test
    fun incomeReceivedTextComparaORecebido() {
        assertEquals("Recebido R$ 3.200,00 de R$ 5.000,00 esperados", plain(incomeReceivedText(d("3200"), d("5000"))))
    }

    // node: 'livePlanTotals: R$ e Sem destino a cada tecla, e salvar so com renda e ate 100%'
    @Test
    fun livePlanTotalsACadaTecla() {
        val totals = livePlanTotals(n("5000"), n("20"), n("70"))
        assertMoney("1000", totals.investAmount)
        assertMoney("3500", totals.spendAmount)
        assertMoney("10", totals.unallocatedPercent)
        assertFalse(totals.over)
        assertNull(totals.blocked)
        assertEquals("Investir R$ 1.000,00 · Gastar R$ 3.500,00 · Sem destino 10%", plain(livePlanText(totals)))

        // 33,33 + 66,67 da 100% exatos.
        val full = livePlanTotals(n("4000"), n("33.33"), n("66.67"))
        assertMoney("0", full.unallocatedPercent)
        assertNull(full.blocked)

        val over = livePlanTotals(n("5000"), n("40"), n("70"))
        assertTrue(over.over)
        assertMoney("-10", over.unallocatedPercent)
        assertTrue(over.blocked!!.contains("100%"))
        assertTrue(livePlanText(over).contains("Passa de 100% da renda em 10%"))

        val noIncome = livePlanTotals(blank, n("20"), n("70"))
        assertNull(noIncome.investAmount)
        assertMoney("10", noIncome.unallocatedPercent)
        assertTrue(noIncome.blocked!!.contains("renda"))
        assertEquals("Investir — · Gastar — · Sem destino 10%", livePlanText(noIncome))

        assertTrue(livePlanTotals(n("0"), n("20"), n("70")).blocked!!.contains("renda"))

        val partial = livePlanTotals(n("5000"), n("20"), blank)
        assertMoney("1000", partial.investAmount)
        assertNull(partial.spendAmount)
        assertNull(partial.unallocatedPercent)
        assertTrue(partial.blocked!!.contains("investir e gastar"))
        assertNotNull(livePlanTotals(n("5000"), MoneyInput.Invalid, n("70")).blocked)
    }

    // node: 'livePlanTotals: plano antigo sem renda, % em branco converte os reais de antes'
    @Test
    fun livePlanTotalsPlanoAntigoConverte() {
        fun legacy(income: MoneyInput, invest: MoneyInput, spend: MoneyInput) =
            livePlanTotals(income, invest, spend, legacyInvest = d("1000"), legacySpend = d("3000"), hasLegacy = true)
        val totals = legacy(n("5000"), blank, blank)
        assertTrue(totals.convert)
        assertMoney("1000", totals.investAmount)
        assertMoney("3000", totals.spendAmount)
        assertMoney("20", totals.unallocatedPercent)
        assertNull(totals.blocked)

        // Acima da renda a conversao e aceita (vira alerta no plano), nao bloqueada.
        val over = legacy(n("3000"), blank, blank)
        assertTrue(over.over)
        assertNull(over.blocked)

        assertTrue(legacy(blank, blank, blank).blocked!!.contains("renda"))
        // Digitar um % sai da conversao: vale a regra normal.
        assertTrue(legacy(n("5000"), n("20"), blank).blocked!!.contains("investir e gastar"))
    }

    // node: 'categoryAmountPreview: o % do Gastar em reais'
    @Test
    fun categoryAmountPreviewOPercentEmReais() {
        assertMoney("350", categoryAmountPreview(d("3500"), d("10")))
        assertMoney(null, categoryAmountPreview(d("3500"), null))
        assertMoney(null, categoryAmountPreview(d("3500"), d("-1")))
        assertMoney(null, categoryAmountPreview(null, d("10")))
    }

    // node: 'planFlagKey: codigo + mes, e a meta nos alertas de meta'
    @Test
    fun planFlagKeyCodigoMesEMeta() {
        assertEquals("plan:2026-10:SPEND_PACE", planFlagKey(PlanFlagDto(code = "SPEND_PACE", tone = "warning"), "2026-10"))
        assertEquals("plan:2026-10:GOAL_SHORT:7", planFlagKey(PlanFlagDto(code = "GOAL_SHORT", goalId = "7"), "2026-10"))
        // O valor do alerta muda todo dia; a chave nao.
        assertEquals(
            planFlagKey(PlanFlagDto(code = "SPEND_PACE", amount = d("10")), "2026-10"),
            planFlagKey(PlanFlagDto(code = "SPEND_PACE", amount = d("99")), "2026-10"),
        )
    }

    // node: 'visibleFlags: o dispensado nao volta no mes; um novo, outra meta ou o mes seguinte voltam'
    @Test
    fun visibleFlagsODispensadoNaoVolta() {
        val flags = listOf(
            PlanFlagDto(code = "SPEND_PACE", tone = "warning", amount = d("120")),
            PlanFlagDto(code = "GOAL_SHORT", tone = "loss", goalId = "1"),
            PlanFlagDto(code = "GOAL_SHORT", tone = "loss", goalId = "2"),
        )
        val dismissed = listOf("plan:2026-10:SPEND_PACE", "plan:2026-10:GOAL_SHORT:1")
        assertEquals(listOf("2"), visibleFlags(flags, "2026-10", dismissed).map { it.goalId ?: it.code })
        assertEquals(1, visibleFlags(listOf(PlanFlagDto(code = "SPEND_OVER", tone = "loss")), "2026-10", dismissed).size)
        assertEquals(3, visibleFlags(flags, "2026-11", dismissed).size)
        assertEquals(emptyList<PlanFlagDto>(), visibleFlags(null, "2026-10", dismissed))
    }

    // node: 'percentRoom: o que ainda cabe depois dos outros, nunca negativo'
    @Test
    fun percentRoomOQueAindaCabe() {
        assertMoney("40", percentRoom(d("60")))
        assertMoney("66.666667", percentRoom(d("33.333333")))
        assertMoney("0", percentRoom(d("120")))
        assertMoney("100", percentRoom(null))
    }

    // node: 'clampPercent prende o controle entre 0 e o que cabe'
    @Test
    fun clampPercentPrendeOControle() {
        assertMoney("40", clampPercent(d("45"), d("40")))
        assertMoney("0", clampPercent(d("-3")))
        assertMoney("25", clampPercent(d("25")))
        assertMoney("0", clampPercent(null))
        assertMoney("0", clampPercent(d("10"), d("-5")))
    }

    // node: 'stepPercent anda de ponto inteiro em ponto inteiro, sem passar do limite'
    @Test
    fun stepPercentAndaDePontoInteiro() {
        assertMoney("34", stepPercent(d("33.333333"), 1))
        assertMoney("33", stepPercent(d("33.333333"), -1))
        assertMoney("21", stepPercent(d("20"), 1))
        assertMoney("19", stepPercent(d("20"), -1))
        assertMoney("0", stepPercent(d("0"), -1))
        assertMoney("66.666667", stepPercent(d("66"), 1, d("66.666667")))
        assertMoney("100", stepPercent(d("100"), 1))
    }

    @Test
    fun budgetStatusLabelsComoNaWeb() {
        assertEquals("No plano", BudgetStatus.of("OK").label)
        assertEquals("Perto do limite", BudgetStatus.of("WARNING").label)
        assertEquals("Estourou", BudgetStatus.of("OVER").label)
        assertEquals("Falta a renda", BudgetStatus.of("NEEDS_INCOME").label)
        assertEquals(BudgetStatus.OK, BudgetStatus.of("???"))
        assertEquals(FlagTone.DANGER, MonthlyPlan.flagTone("loss"))
        assertEquals(FlagTone.SUCCESS, MonthlyPlan.flagTone("gain"))
    }
}
