// Porte: mudou um, muda o outro, com um teste de cada lado.
// Os casos de frontend/src/lib/investmentStatement.test.js, na mesma ordem; o nome do teste do
// node vai no comentario de cada um.
package br.financas.app.rules

import br.financas.app.data.InvestmentMovementDto
import br.financas.app.data.InvestmentProceedDto
import br.financas.app.data.ProceedAssetDto
import br.financas.app.rules.InvestmentStatement.buildInvestmentStatement
import br.financas.app.rules.InvestmentStatement.groupEntriesByDay
import br.financas.app.rules.InvestmentStatement.movementEntry
import br.financas.app.rules.InvestmentStatement.proceedEntry
import br.financas.app.rules.InvestmentStatement.statementTotals
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.math.BigDecimal

class InvestmentStatementTest {
    private fun money(text: String) = BigDecimal(text)

    private fun assertMoney(expected: String, actual: BigDecimal) =
        assertEquals("$actual", 0, money(expected).compareTo(actual))

    private val buy = InvestmentMovementDto(
        id = "m1", assetClass = "STOCKS", tickerOrName = "BBAS3", quantity = money("10"), averagePrice = money("20"),
        feeAmount = money("1"), metadata = buildJsonObject { put("purchase_date", "2026-03-01") },
    )
    private val sale = InvestmentMovementDto(
        id = "m2", assetClass = "STOCKS", tickerOrName = "BBAS3", quantity = money("-5"), averagePrice = money("20"),
        realizedNetProceeds = money("120"),
        metadata = buildJsonObject {
            put("sale_date", "2026-05-01")
            put("sale_price", JsonPrimitive(25))
        },
    )
    private val bonus = InvestmentMovementDto(
        id = "m3", assetClass = "STOCKS", tickerOrName = "ITSA4", quantity = money("2"), averagePrice = money("0"),
        metadata = buildJsonObject {
            put("purchase_date", "2026-03-01")
            put("corporate_action_id", "ca")
        },
    )
    private val redemption = InvestmentMovementDto(
        id = "m4", assetClass = "FIXED_INCOME", tickerOrName = "LCI", quantity = money("-1"), currentPrice = money("1000"),
        metadata = buildJsonObject {
            put("is_redemption", true)
            put("redemption_date", "2026-04-01")
        },
    )
    private val paid = InvestmentProceedDto(
        id = "p1", proceedsType = "JCP", paymentDate = "2026-06-11", netAmount = money("8.25"), taxAmount = money("1.75"),
        eligibleQuantity = money("10"), amountPerUnit = money("1"), asset = ProceedAssetDto(ticker = "BBAS3"), syncKey = "k",
    )
    private val future = InvestmentProceedDto(
        id = "p2", proceedsType = "DIVIDEND", paymentDate = "2026-12-20", netAmount = money("5"), taxAmount = money("0"),
        asset = ProceedAssetDto(ticker = "KLBN4"),
    )

    private fun entry(date: String, amount: String, scheduled: Boolean) = StatementEntry(
        id = date + amount, source = InvestmentStatement.MOVEMENT, date = date, title = "", kind = "",
        quantity = null, unitPrice = null, amount = money(amount), scheduled = scheduled,
    )

    // node: 'a compra sai com a taxa, a venda entra pelo liquido, bonificacao e zero'
    @Test
    fun buyCostsWithFeeSaleIsNetBonusIsZero() {
        assertMoney("-201", movementEntry(buy).amount)
        assertEquals("Compra", movementEntry(buy).kind)
        assertMoney("120", movementEntry(sale).amount)
        assertEquals("Venda", movementEntry(sale).kind)
        assertMoney("0", movementEntry(bonus).amount)
        assertEquals("Bonificação", movementEntry(bonus).kind)
    }

    // node: 'a operacao leva o id para ser excluida; bonificacao nao se exclui'
    @Test
    fun movementCarriesItsIdAndBonusIsNotDeletable() {
        assertEquals(buy.id, movementEntry(buy).movementId)
        assertEquals(true, movementEntry(buy).deletable)
        assertEquals(true, movementEntry(sale).deletable)
        assertEquals(false, movementEntry(bonus).deletable)
    }

    // node: 'renda fixa e aporte/resgate, sem quantidade'
    @Test
    fun fixedIncomeIsAporteResgateWithoutQuantity() {
        val entry = movementEntry(redemption)
        assertEquals("Resgate", entry.kind)
        assertMoney("1000", entry.amount)
        assertNull(entry.quantity)
        assertEquals("2026-04-01", entry.date)
    }

    // node: 'provento entra pelo liquido e o futuro fica agendado'
    @Test
    fun proceedIsNetAndFutureIsScheduled() {
        assertMoney("8.25", proceedEntry(paid, "2026-10-16").amount)
        assertEquals(false, proceedEntry(paid, "2026-10-16").scheduled)
        assertEquals(true, proceedEntry(paid, "2026-10-16").automatic)
        assertEquals(true, proceedEntry(future, "2026-10-16").scheduled)
    }

    // node: 'lista do mais novo ao mais antigo, filtrada por tipo e busca'
    @Test
    fun newestFirstFilteredByKindAndSearch() {
        val all = buildInvestmentStatement(listOf(buy, sale), listOf(paid, future), today = "2026-10-16")
        assertEquals(listOf("prov:p2", "prov:p1", "mov:m2", "mov:m1"), all.map { it.id })
        assertEquals(listOf("prov:p1"), buildInvestmentStatement(listOf(buy), listOf(paid), kind = "PROCEEDS").map { it.id })
        assertEquals(listOf("mov:m1"), buildInvestmentStatement(listOf(buy), listOf(paid), kind = "MOVEMENTS").map { it.id })
        assertEquals(listOf("mov:m3"), buildInvestmentStatement(listOf(buy, bonus), emptyList(), query = "itsa").map { it.id })
    }

    // node: 'totais separam aporte, retirada, provento recebido e agendado'
    @Test
    fun totalsSplitInvestedWithdrawnProceedsAndScheduled() {
        val entries = buildInvestmentStatement(listOf(buy, sale), listOf(paid, future), today = "2026-10-16")
        val totals = statementTotals(entries)
        assertMoney("201", totals.invested)
        assertMoney("120", totals.withdrawn)
        assertMoney("8.25", totals.proceeds)
        assertMoney("5", totals.scheduled)
    }

    // node: 'o total do dia ignora o agendado'
    @Test
    fun dayTotalIgnoresScheduled() {
        val groups = groupEntriesByDay(
            listOf(entry("2026-12-20", "5", true), entry("2026-03-01", "-201", false), entry("2026-03-01", "0", false)),
        )
        assertEquals(listOf("2026-12-20" to 1, "2026-03-01" to 2), groups.map { it.date to it.items.size })
        assertMoney("0", groups[0].total)
        assertMoney("-201", groups[1].total)
    }

    // node: 'no mesmo dia, operacoes antes de proventos'
    @Test
    fun sameDayMovementsBeforeProceeds() {
        val sameDay = paid.copy(id = "p3", paymentDate = "2026-03-01")
        val ids = buildInvestmentStatement(listOf(buy), listOf(sameDay), today = "2026-10-16").map { it.id }
        assertEquals(listOf("mov:m1", "prov:p3"), ids)
    }

    // Sem par no node: o detailText de ExtratoInvestimentos.jsx.
    @Test
    fun theDetailLineHasQuantityPriceAndTax() {
        assertEquals("10 un. · R$ 20,00", InvestmentStatement.detailText(movementEntry(buy)))
        assertEquals("10 cotas · R$ 1,00/cota · IR R$ 1,75", InvestmentStatement.detailText(proceedEntry(paid, "2026-10-16")))
        assertEquals("", InvestmentStatement.detailText(movementEntry(redemption)))
    }
}
