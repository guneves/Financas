// Porte: mudou um, muda o outro, com um teste de cada lado.
// Par: frontend/src/lib/investmentStatement.js (testes em investmentStatement.test.js);
// aqui: InvestmentStatementTest.kt, os mesmos casos na mesma ordem.
//
// Extrato de investimentos: operacoes e proventos numa lista so, do mais novo para o mais antigo,
// agrupada por dia. O sinal e o do dinheiro do investidor: compra/aporte sai (-), venda, resgate e
// provento entram (+), bonificacao e 0. Dinheiro em BigDecimal (o JS soma em float e arredonda so
// ao formatar; aqui a conta e exata e o formatador arredonda HALF_UP). No mesmo dia, operacoes
// antes de proventos, como hoje na web.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.data.InvestmentMovementDto
import br.financas.app.data.InvestmentProceedDto
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import java.math.BigDecimal

/** Uma linha do extrato de investimentos (movementEntry / proceedEntry). */
data class StatementEntry(
    val id: String,
    /** "movement" ou "proceed" (a ordem do mesmo dia sai deste texto). */
    val source: String,
    val date: String,
    val title: String,
    val kind: String,
    val quantity: BigDecimal?,
    val unitPrice: BigDecimal?,
    val amount: BigDecimal,
    val scheduled: Boolean,
    val movementId: String? = null,
    val deletable: Boolean = false,
    val inStatement: Boolean = false,
    val tax: BigDecimal = BigDecimal.ZERO,
    val automatic: Boolean = false,
)

data class StatementTotals(
    val invested: BigDecimal,
    val withdrawn: BigDecimal,
    val proceeds: BigDecimal,
    val scheduled: BigDecimal,
)

data class EntryDay(val date: String, val items: List<StatementEntry>, val total: BigDecimal)

object InvestmentStatement {
    const val MOVEMENT = "movement"
    const val PROCEED = "proceed"

    const val KIND_ALL = "ALL"
    const val KIND_MOVEMENTS = "MOVEMENTS"
    const val KIND_PROCEEDS = "PROCEEDS"
    val STATEMENT_KINDS = listOf(KIND_ALL, KIND_MOVEMENTS, KIND_PROCEEDS)

    private val PROCEED_LABELS = mapOf(
        "DIVIDEND" to "Dividendo",
        "JCP" to "JCP",
        "AMORTIZATION" to "Amortização",
        "INTEREST" to "Juros",
    )

    private fun day(value: String?): String = (value ?: "").take(10)

    // O `a || b` do JS sobre os campos de metadata: o primeiro texto nao vazio.
    private fun metaText(meta: JsonObject?, key: String): String? {
        val value = meta?.get(key) ?: return null
        if (value !is JsonPrimitive || !value.isString) return null
        return value.content.takeIf { it.isNotEmpty() }
    }

    // Number(...) de um campo de metadata; null quando ausente, nulo ou nao numerico.
    private fun metaNumber(meta: JsonObject?, key: String): BigDecimal? {
        val value = meta?.get(key) ?: return null
        if (value is JsonNull || value !is JsonPrimitive) return null
        return value.content.trim().takeIf { it.isNotEmpty() }?.toBigDecimalOrNull()
    }

    // Boolean(meta.x) do JS: false, 0, "" e null sao falsos.
    private fun metaFlag(meta: JsonObject?, key: String): Boolean {
        val value = meta?.get(key) ?: return false
        if (value is JsonNull || value !is JsonPrimitive) return value !is JsonNull
        val text = value.content
        if (value.isString) return text.isNotEmpty()
        return text != "false" && text.toBigDecimalOrNull()?.signum() != 0
    }

    private fun movementDate(movement: InvestmentMovementDto): String {
        val meta = movement.metadata
        return day(
            metaText(meta, "redemption_date") ?: metaText(meta, "sale_date")
                ?: metaText(meta, "purchase_date") ?: movement.createdAt,
        )
    }

    private fun quantityOf(movement: InvestmentMovementDto): BigDecimal = movement.quantity ?: BigDecimal.ZERO

    private fun unitPrice(movement: InvestmentMovementDto): BigDecimal {
        val meta = movement.metadata
        if (metaFlag(meta, "is_redemption")) return movement.currentPrice ?: BigDecimal.ZERO
        val salePrice = metaNumber(meta, "sale_price")
        if (quantityOf(movement).signum() < 0 && salePrice != null && salePrice.signum() != 0) return salePrice
        return movement.averagePrice ?: BigDecimal.ZERO
    }

    // realized_fee_amount ?? fee_amount ?? metadata.other_costs ?? 0
    private fun fees(movement: InvestmentMovementDto): BigDecimal =
        movement.realizedFeeAmount ?: movement.feeAmount ?: metaNumber(movement.metadata, "other_costs") ?: BigDecimal.ZERO

    fun movementEntry(movement: InvestmentMovementDto): StatementEntry {
        val meta = movement.metadata
        val isFixed = movement.assetClass == "FIXED_INCOME"
        val isSale = quantityOf(movement).signum() < 0
        val isBonus = metaFlag(meta, "corporate_action_id")
        val quantity = quantityOf(movement).abs()
        val price = unitPrice(movement)
        val gross = quantity.multiply(price)
        val cost = fees(movement)
        val amount = when {
            isBonus -> BigDecimal.ZERO
            isSale -> movement.realizedNetProceeds ?: gross.subtract(cost).max(BigDecimal.ZERO)
            else -> gross.add(cost).negate()
        }
        val kind = when {
            isBonus -> "Bonificação"
            isFixed -> if (isSale) "Resgate" else "Aporte"
            else -> if (isSale) "Venda" else "Compra"
        }
        return StatementEntry(
            id = "mov:${movement.id}",
            source = MOVEMENT,
            movementId = movement.id,
            // Bonificacao so sai desfazendo o evento (o servidor recusa, 409).
            deletable = !isBonus,
            date = movementDate(movement),
            title = movement.tickerOrName ?: "",
            kind = kind,
            quantity = if (isFixed) null else quantity,
            unitPrice = if (isFixed) null else price,
            amount = amount,
            scheduled = false,
            inStatement = metaFlag(meta, "cash_account_id"),
        )
    }

    fun proceedEntry(proceed: InvestmentProceedDto, today: String?): StatementEntry {
        val date = day(proceed.paymentDate)
        val quantity = proceed.eligibleQuantity
        return StatementEntry(
            id = "prov:${proceed.id}",
            source = PROCEED,
            date = date,
            title = proceed.asset?.ticker?.takeIf { it.isNotEmpty() } ?: proceed.asset?.name ?: "",
            kind = PROCEED_LABELS[proceed.proceedsType] ?: proceed.proceedsType.orEmpty(),
            quantity = if (quantity == null || quantity.signum() == 0) null else quantity,
            unitPrice = proceed.amountPerUnit,
            amount = proceed.netAmount ?: BigDecimal.ZERO,
            tax = proceed.taxAmount ?: BigDecimal.ZERO,
            scheduled = !today.isNullOrEmpty() && date > today,
            automatic = !proceed.syncKey.isNullOrEmpty(),
        )
    }

    fun buildInvestmentStatement(
        movements: List<InvestmentMovementDto> = emptyList(),
        proceeds: List<InvestmentProceedDto> = emptyList(),
        today: String = "",
        kind: String = KIND_ALL,
        query: String = "",
    ): List<StatementEntry> {
        val entries = mutableListOf<StatementEntry>()
        if (kind != KIND_PROCEEDS) movements.forEach { entries.add(movementEntry(it)) }
        if (kind != KIND_MOVEMENTS) proceeds.forEach { entries.add(proceedEntry(it, today)) }
        val needle = query.trim().lowercase()
        val visible = if (needle.isEmpty()) entries else entries.filter { "${it.title} ${it.kind}".lowercase().contains(needle) }
        // Mais novo primeiro; no mesmo dia, operacoes antes de proventos (sort estavel, como o JS).
        return visible.sortedWith { a, b ->
            if (a.date == b.date) a.source.compareTo(b.source) else b.date.compareTo(a.date)
        }
    }

    fun statementTotals(entries: List<StatementEntry>): StatementTotals {
        var invested = BigDecimal.ZERO
        var withdrawn = BigDecimal.ZERO
        var proceeds = BigDecimal.ZERO
        var scheduled = BigDecimal.ZERO
        for (entry in entries) {
            when {
                entry.scheduled -> scheduled += entry.amount
                entry.source == PROCEED -> proceeds += entry.amount
                entry.amount.signum() < 0 -> invested += entry.amount.negate()
                else -> withdrawn += entry.amount
            }
        }
        return StatementTotals(invested, withdrawn, proceeds, scheduled)
    }

    /**
     * A linha de baixo (o detailText de ExtratoInvestimentos.jsx): "10 un. · R$ 20,00 · IR R$ 1,75";
     * proventos em "cotas" e "/cota". A quantidade com ate 6 casas, como o toLocaleString de la.
     */
    fun detailText(entry: StatementEntry): String {
        val parts = mutableListOf<String>()
        val proceed = entry.source == PROCEED
        val quantity = entry.quantity
        if (quantity != null && quantity.signum() != 0) {
            val rounded = quantity.setScale(6, java.math.RoundingMode.HALF_UP)
            parts += "${br.financas.app.core.formatQuantity(rounded)} ${if (proceed) "cotas" else "un."}"
        }
        val price = entry.unitPrice
        if (price != null && price.signum() != 0) parts += br.financas.app.core.formatUnitCurrency(price) + if (proceed) "/cota" else ""
        if (entry.tax.signum() != 0) parts += "IR ${br.financas.app.core.formatCurrency(entry.tax)}"
        return parts.joinToString(" · ")
    }

    /** Dias em ordem; o total do dia ignora o agendado (ainda nao entrou). */
    fun groupEntriesByDay(entries: List<StatementEntry>): List<EntryDay> {
        val groups = mutableListOf<Triple<String, MutableList<StatementEntry>, Array<BigDecimal>>>()
        for (entry in entries) {
            val last = groups.lastOrNull()
            val group = if (last == null || last.first != entry.date) {
                Triple(entry.date, mutableListOf<StatementEntry>(), arrayOf(BigDecimal.ZERO)).also { groups.add(it) }
            } else {
                last
            }
            group.second.add(entry)
            if (!entry.scheduled) group.third[0] = group.third[0].add(entry.amount)
        }
        return groups.map { EntryDay(it.first, it.second, it.third[0]) }
    }
}
