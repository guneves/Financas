// As regras inline de Posicao.jsx / PortfolioOverview.jsx / helpers.js (sem teste do lado web):
// os casos daqui sao o comportamento da web hoje, conferido no codigo.
package br.financas.app.rules

import br.financas.app.rules.PortfolioView.DeleteTarget
import br.financas.app.rules.PortfolioView.MenuItem
import br.financas.app.rules.PortfolioView.Position
import br.financas.app.rules.PortfolioView.Tab
import org.junit.Assert.assertEquals
import org.junit.Test
import java.math.BigDecimal
import java.time.ZoneId

class PortfolioViewTest {
    private fun money(text: String) = BigDecimal(text)

    private fun stock(id: String, kind: String? = null, value: String = "10") =
        Position(id, "STOCKS", marketKind = kind, currentValue = money(value))

    @Test
    fun theThreeTabsSplitByClassAndTreasuryCategory() {
        val stock = stock("a")
        val cdb = Position("b", "FIXED_INCOME", category = "RENDA_FIXA")
        val treasury = Position("c", "FIXED_INCOME", category = "TESOURO")
        val fii = Position("d", "REIT")
        val all = listOf(stock, cdb, treasury, fii)
        assertEquals(listOf("a", "d"), all.filter { PortfolioView.inTab(it, Tab.VARIAVEL) }.map { it.id })
        assertEquals(listOf("b"), all.filter { PortfolioView.inTab(it, Tab.FIXA) }.map { it.id })
        assertEquals(listOf("c"), all.filter { PortfolioView.inTab(it, Tab.TESOURO) }.map { it.id })
    }

    @Test
    fun variableGroupsFollowTheKindOrderWithTotals() {
        val items = listOf(
            Position("x", "OTHER", currentValue = money("5")),
            stock("e1", "ETF", "100.10"),
            Position("btc", "OTHER", marketKind = "CRIPTO", currentValue = money("7")),
            stock("a1", null, "1.05"),
            Position("f", "REIT", currentValue = money("3")),
            stock("b1", "BDR", "2"),
            stock("e2", "ETF", "0.20"),
        )
        val groups = PortfolioView.groupAssets(items, Tab.VARIAVEL) { it }
        assertEquals(listOf("ACAO", "ETF", "BDR", "FII", "CRIPTO", "OTHER"), groups.map { it.key })
        assertEquals(listOf("Ações", "ETFs", "BDRs", "Fundos Imobiliários", "Cripto", "Outros"), groups.map { it.label })
        assertEquals(listOf("e1", "e2"), groups[1].items.map { it.id })
        assertEquals(0, money("100.30").compareTo(groups[1].total))
    }

    @Test
    fun fixedIncomeGroupsByTypeWithoutTypeLast() {
        val items = listOf(
            Position("old", "FIXED_INCOME"),
            Position("lci", "FIXED_INCOME", fixedIncomeType = "LCI"),
            Position("cdb", "FIXED_INCOME", fixedIncomeType = "CDB"),
            Position("deb", "FIXED_INCOME", fixedIncomeType = "DEBENTURE"),
        )
        val groups = PortfolioView.groupAssets(items, Tab.FIXA) { it }
        assertEquals(listOf("CDB", "LCI", "Debênture", "Sem tipo"), groups.map { it.label })
    }

    @Test
    fun treasuryGroupsByIndexerWithoutIndexerLast() {
        val items = listOf(
            Position("x", "FIXED_INCOME", category = "TESOURO"),
            Position("i", "FIXED_INCOME", category = "TESOURO", rateKind = "IPCA"),
            Position("s", "FIXED_INCOME", category = "TESOURO", rateKind = "POS"),
            Position("p", "FIXED_INCOME", category = "TESOURO", rateKind = "PRE"),
        )
        val groups = PortfolioView.groupAssets(items, Tab.TESOURO) { it }
        assertEquals(listOf("Pós-fixado (Selic)", "Pré-fixado", "IPCA+", "Sem indexador"), groups.map { it.label })
    }

    // Fora da ordem fixa: o rotulo, em ordem alfabetica do pt-BR (o localeCompare da web).
    @Test
    fun groupsOutsideTheOrderSortByLabel() {
        val items = listOf(Position("z", "ZETA"), Position("o", "OUTRA"), Position("a", "ÁGUA"))
        val groups = PortfolioView.groupAssets(items, Tab.VARIAVEL) { it }
        assertEquals(listOf("ÁGUA", "OUTRA", "ZETA"), groups.map { it.label })
    }

    @Test
    fun menuItemsFollowTheWebOrder() {
        val stockMenu = PortfolioView.menuItems(stock("a"), updatingPrices = false)
        assertEquals(listOf(MenuItem.EDIT_QUOTE, MenuItem.REFRESH_QUOTE, MenuItem.DELETE_POSITION), stockMenu)
        val cdb = Position("b", "FIXED_INCOME", lotCount = 0)
        assertEquals(listOf(MenuItem.REFRESH_VALUE, MenuItem.DELETE_CONTRIBUTION), PortfolioView.menuItems(cdb, false))
        val treasury = Position("c", "FIXED_INCOME", category = "TESOURO", lotCount = 2, hasTreasury = true)
        // Atualizando cotacoes: some o "Atualizar".
        assertEquals(listOf(MenuItem.DETAILS, MenuItem.DELETE_POSITION), PortfolioView.menuItems(treasury, true))
    }

    @Test
    fun deleteGoesToTheRightEndpoint() {
        val grouped = Position("tesouro:1", "FIXED_INCOME", lotCount = 2)
        assertEquals(DeleteTarget.Assets(listOf("a1", "a2")), PortfolioView.deleteTarget(grouped, "a1", listOf("a1", "a2")))
        assertEquals(DeleteTarget.Assets(listOf("a1")), PortfolioView.deleteTarget(grouped, "a1", emptyList()))
        assertEquals(DeleteTarget.Movement("m1"), PortfolioView.deleteTarget(Position("m1", "FIXED_INCOME", lotCount = 1), "a1", emptyList()))
        assertEquals(DeleteTarget.Asset("a9"), PortfolioView.deleteTarget(stock("p9"), "a9", emptyList()))
        assertEquals(DeleteTarget.Asset("p9"), PortfolioView.deleteTarget(stock("p9"), null, emptyList()))
    }

    @Test
    fun allocationSumsByCategoryLabelOrClass() {
        val sums = PortfolioView.allocationByCategory(
            listOf(
                Position("a", "STOCKS", categoryLabel = "Ações", currentValue = money("10")),
                Position("b", "OTHER", currentValue = money("4")),
                Position("c", "STOCKS", categoryLabel = "Ações", currentValue = money("0.5")),
            ),
        )
        assertEquals(listOf("Ações" to money("10.5"), "Outros" to money("4")), sums)
    }

    @Test
    fun donutKeepsSixSlicesAndGroupsTheRest() {
        val data = (1..8).map { "C$it" to money(it.toString()) } + ("Zero" to BigDecimal.ZERO)
        val slices = PortfolioView.donutSlices(data)
        assertEquals(listOf("C8", "C7", "C6", "C5", "C4", "Outros"), slices.map { it.name })
        assertEquals(0, money("6").compareTo(slices.last().value))
        assertEquals(listOf(0, 1, 2, 3, 4, -1), slices.map { it.colorIndex })
        // "Outros" de verdade entre as maiores: o resto vira "Demais".
        val withOthers = PortfolioView.donutSlices(listOf("Outros" to money("100")) + data)
        assertEquals("Demais", withOthers.last().name)
        assertEquals(3, PortfolioView.donutSlices(data.take(3)).size)
    }

    @Test
    fun evolutionBarStacksGainOnAppliedAndLossOnPatrimony() {
        val gain = PortfolioView.evolutionBar("2026-09", money("1000"), money("1100"), money("1080"), money("100"))
        assertEquals(listOf(money("1000"), money("100"), BigDecimal.ZERO), listOf(gain.base, gain.ganho, gain.perda))
        val loss = PortfolioView.evolutionBar("2026-10", money("1000"), money("900"), null, money("-100"))
        assertEquals(listOf(money("900"), BigDecimal.ZERO, money("100")), listOf(loss.base, loss.ganho, loss.perda))
        assertEquals(BigDecimal.ZERO, loss.patrimonioLiquido)
        // Sem patrimonio bruto, o patrimonio (o ?? da web).
        assertEquals(money("950"), PortfolioView.evolutionBar("x", null, null, money("950"), null).patrimonio)
    }

    @Test
    fun quoteLabels() {
        assertEquals("Tesouro Nacional", PortfolioView.quoteSourceLabel("tesouro"))
        assertEquals("brapi", PortfolioView.quoteSourceLabel("brapi"))
        assertEquals("Sem fonte", PortfolioView.quoteSourceLabel(null))
        assertEquals("Atual", PortfolioView.quoteStatusLabel("fresh"))
        assertEquals("Sem cotação", PortfolioView.quoteStatusLabel("whatever"))
        val zone = ZoneId.of("America/Sao_Paulo")
        assertEquals("22/10/26, 14:03", PortfolioView.formatDateTime("2026-10-22T17:03:00Z", zone))
        assertEquals("Sem atualização", PortfolioView.formatDateTime("", zone))
        assertEquals("Data inválida", PortfolioView.formatDateTime("ontem", zone))
    }

    @Test
    fun classLabels() {
        assertEquals("Fundos Imobiliários", PortfolioView.classLabel("REIT"))
        assertEquals("XYZ", PortfolioView.classLabel("XYZ"))
    }
}
