// Porte: mudou um, muda o outro, com um teste de cada lado.
// Par: o que pages/investimentos/Posicao.jsx (groupAssets, groupKeyAndLabel, variableGroupKey,
// positionMenuItems, filtro das abas), PortfolioOverview.jsx (rosca por categoria, barras da
// evolucao), helpers.js (quoteSourceLabel, quoteStatusLabel, formatDateTime, getClassLabel) e o
// DonutChart de components/charts.jsx (as fatias) fazem inline, sem teste do lado web. Aqui
// PortfolioViewTest.kt.
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import java.math.BigDecimal
import java.text.Collator
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException
import java.util.Locale

object PortfolioView {
    /** As abas da Posicao: renda variavel, renda fixa (sem o Tesouro) e Tesouro Direto. */
    enum class Tab { VARIAVEL, FIXA, TESOURO }

    /** Uma posicao, so o que as regras leem. */
    data class Position(
        val id: String,
        val assetClass: String?,
        val category: String? = null,
        val categoryLabel: String? = null,
        val marketKind: String? = null,
        val rateKind: String? = null,
        val fixedIncomeType: String? = null,
        val currentValue: BigDecimal? = null,
        val lotCount: Int = 0,
        val hasTreasury: Boolean = false,
    )

    data class Group<T>(val key: String, val label: String, val items: List<T>, val total: BigDecimal)

    val CLASS_LABELS = mapOf(
        "STOCKS" to "Ações",
        "FIXED_INCOME" to "Renda Fixa",
        "REIT" to "Fundos Imobiliários",
        "OTHER" to "Outros",
    )

    /** As classes do filtro por classe (backend/asset_classes.py). */
    val ASSET_CLASSES = listOf("STOCKS", "REIT", "FIXED_INCOME", "OTHER")

    fun classLabel(assetClass: String?): String = CLASS_LABELS[assetClass] ?: assetClass.orEmpty()

    /** Tesouro Direto e a categoria TESOURO da renda fixa (services/asset_categories.py). */
    fun isTreasury(position: Position): Boolean = position.category == "TESOURO"

    fun inTab(position: Position, tab: Tab): Boolean = when (tab) {
        Tab.VARIAVEL -> position.assetClass != "FIXED_INCOME"
        Tab.FIXA -> position.assetClass == "FIXED_INCOME" && !isTreasury(position)
        Tab.TESOURO -> isTreasury(position)
    }

    private val RATE_KIND_ORDER = listOf("POS", "PRE", "IPCA")
    private val RATE_KIND_LABELS = mapOf("POS" to "Pós-fixado (Selic)", "PRE" to "Pré-fixado", "IPCA" to "IPCA+")
    private const val NO_RATE_KIND = "SEM_INDEXADOR"
    private val VARIABLE_ORDER = listOf("ACAO", "ETF", "BDR", "FII", "CRIPTO", "OTHER")
    private val VARIABLE_LABELS = mapOf(
        "ACAO" to "Ações",
        "ETF" to "ETFs",
        "BDR" to "BDRs",
        "FII" to "Fundos Imobiliários",
        "CRIPTO" to "Cripto",
    )
    private val FIXED_INCOME_ORDER = FixedIncome.FIXED_INCOME_TYPES.map { it.value }
    private const val NO_FIXED_INCOME_TYPE = "SEM_TIPO"

    // STOCKS junta acao, ETF e BDR (market_kind do catalogo); o Bitcoin, dentro de Outros, tem o dele.
    private fun variableGroupKey(position: Position): String = when {
        position.assetClass == "STOCKS" -> position.marketKind?.takeIf { it.isNotEmpty() } ?: "ACAO"
        position.assetClass == "REIT" -> "FII"
        position.marketKind == "CRIPTO" -> "CRIPTO"
        else -> position.assetClass.orEmpty()
    }

    /** A chave e o rotulo do grupo da posicao na aba. */
    fun groupKeyAndLabel(position: Position, tab: Tab): Pair<String, String> = when (tab) {
        Tab.TESOURO -> {
            val key = position.rateKind?.takeIf { it.isNotEmpty() } ?: NO_RATE_KIND
            key to (RATE_KIND_LABELS[key] ?: "Sem indexador")
        }
        Tab.FIXA -> {
            val key = position.fixedIncomeType?.takeIf { it.isNotEmpty() } ?: NO_FIXED_INCOME_TYPE
            key to (FixedIncome.FIXED_INCOME_TYPES.firstOrNull { it.value == key }?.label ?: if (key == NO_FIXED_INCOME_TYPE) "Sem tipo" else key)
        }
        Tab.VARIAVEL -> {
            val key = variableGroupKey(position)
            key to (VARIABLE_LABELS[key] ?: classLabel(key))
        }
    }

    /**
     * Os grupos da aba, na ordem da web: a ordem fixa de cada aba e, entre os que nao estao nela, o
     * rotulo em ordem alfabetica do pt-BR. Dentro do grupo, a ordem do servidor.
     */
    fun <T> groupAssets(items: List<T>, tab: Tab, position: (T) -> Position): List<Group<T>> {
        val order = when (tab) {
            Tab.TESOURO -> RATE_KIND_ORDER
            Tab.FIXA -> FIXED_INCOME_ORDER
            Tab.VARIAVEL -> VARIABLE_ORDER
        }
        val groups = LinkedHashMap<String, Triple<String, MutableList<T>, Array<BigDecimal>>>()
        items.forEach { item ->
            val view = position(item)
            val (key, label) = groupKeyAndLabel(view, tab)
            val group = groups.getOrPut(key) { Triple(label, mutableListOf(), arrayOf(BigDecimal.ZERO)) }
            group.second.add(item)
            group.third[0] = group.third[0] + (view.currentValue ?: BigDecimal.ZERO)
        }
        val collator = Collator.getInstance(Locale.forLanguageTag("pt-BR"))
        fun rank(key: String) = order.indexOf(key).let { if (it == -1) order.size else it }
        return groups.map { (key, value) -> Group(key, value.first, value.second.toList(), value.third[0]) }
            .sortedWith { a, b -> rank(a.key).compareTo(rank(b.key)).takeIf { it != 0 } ?: collator.compare(a.label, b.label) }
    }

    /** As acoes do "⋯" de uma posicao, na ordem da web (positionMenuItems). */
    enum class MenuItem { DETAILS, EDIT_QUOTE, REFRESH_QUOTE, REFRESH_VALUE, DELETE_CONTRIBUTION, DELETE_POSITION }

    fun menuItems(position: Position, updatingPrices: Boolean): List<MenuItem> {
        val fixed = position.assetClass == "FIXED_INCOME"
        val singleBuy = fixed && position.lotCount <= 1
        val items = mutableListOf<MenuItem>()
        if (position.hasTreasury) items += MenuItem.DETAILS
        if (!fixed) items += MenuItem.EDIT_QUOTE
        if (!updatingPrices) items += if (fixed) MenuItem.REFRESH_VALUE else MenuItem.REFRESH_QUOTE
        items += if (singleBuy) MenuItem.DELETE_CONTRIBUTION else MenuItem.DELETE_POSITION
        return items
    }

    /** O que um "Excluir" pede ao servidor (handleDeleteFullPosition). */
    sealed interface DeleteTarget {
        /** Tesouro com mais de uma compra: todos os ativos do titulo de uma vez. */
        data class Assets(val assetIds: List<String>) : DeleteTarget

        /** Renda fixa de uma compra so: o aporte. */
        data class Movement(val id: String) : DeleteTarget

        /** Renda variavel: o ativo inteiro. */
        data class Asset(val assetId: String) : DeleteTarget
    }

    fun deleteTarget(position: Position, assetId: String?, assetIds: List<String>): DeleteTarget = when {
        position.lotCount > 1 -> DeleteTarget.Assets(assetIds.ifEmpty { listOfNotNull(assetId) })
        position.assetClass == "FIXED_INCOME" -> DeleteTarget.Movement(position.id)
        else -> DeleteTarget.Asset(assetId?.takeIf { it.isNotEmpty() } ?: position.id)
    }

    // ---- A rosca da Alocacao ----

    /** Uma fatia: o nome, o valor e o indice da cor em SERIES (-1 = OTHER_COLOR). */
    data class Slice(val name: String, val value: BigDecimal, val colorIndex: Int)

    /** Soma por categoria (category_label, senao o rotulo da classe), na ordem em que aparecem. */
    fun allocationByCategory(positions: List<Position>): List<Pair<String, BigDecimal>> {
        val sums = LinkedHashMap<String, BigDecimal>()
        positions.forEach { position ->
            val label = position.categoryLabel?.takeIf { it.isNotEmpty() } ?: classLabel(position.assetClass)
            sums[label] = (sums[label] ?: BigDecimal.ZERO) + (position.currentValue ?: BigDecimal.ZERO)
        }
        return sums.toList()
    }

    /**
     * As fatias do DonutChart da web: so as positivas, da maior para a menor (empate fica na ordem
     * dada), a cor pela posicao; mais de [maxSlices] viram "Outros" (ou "Demais", quando uma das
     * maiores ja se chama "Outros"). [colors] e quantas cores SERIES ha (as demais, OTHER_COLOR).
     */
    fun donutSlices(data: List<Pair<String, BigDecimal>>, maxSlices: Int = 6, colors: Int = 8): List<Slice> {
        val sorted = data.filter { it.second.signum() > 0 }.sortedByDescending { it.second }
        val colored = sorted.mapIndexed { index, (name, value) -> Slice(name, value, if (index < colors) index else -1) }
        if (colored.size <= maxSlices) return colored
        val head = colored.take(maxSlices - 1)
        val rest = colored.drop(maxSlices - 1).fold(BigDecimal.ZERO) { acc, slice -> acc + slice.value }
        val restName = if (head.any { it.name == "Outros" }) "Demais" else "Outros"
        return head + Slice(restName, rest, -1)
    }

    // ---- As barras da Evolucao do Patrimonio ----

    /** Um mes: a base (aplicado no ganho, patrimonio na perda), o ganho e a perda empilhados. */
    data class EvolutionBar(
        val month: String,
        val applied: BigDecimal,
        val patrimonio: BigDecimal,
        val patrimonioLiquido: BigDecimal,
        val gain: BigDecimal,
        val base: BigDecimal,
        val ganho: BigDecimal,
        val perda: BigDecimal,
    )

    fun evolutionBar(
        month: String,
        valorAplicado: BigDecimal?,
        patrimonioBruto: BigDecimal?,
        patrimonio: BigDecimal?,
        ganhoCapitalBruto: BigDecimal?,
    ): EvolutionBar {
        val applied = valorAplicado ?: BigDecimal.ZERO
        val gross = patrimonioBruto ?: patrimonio ?: BigDecimal.ZERO
        val gain = ganhoCapitalBruto ?: BigDecimal.ZERO
        return EvolutionBar(
            month = month,
            applied = applied,
            patrimonio = gross,
            patrimonioLiquido = patrimonio ?: BigDecimal.ZERO,
            gain = gain,
            base = if (gain.signum() >= 0) applied else gross,
            ganho = gain.max(BigDecimal.ZERO),
            perda = gain.negate().max(BigDecimal.ZERO),
        )
    }

    // ---- Cotacao ----

    private val SOURCE_LABELS = mapOf(
        "market" to "Mercado",
        "manual" to "Manual",
        "cdi" to "Taxa do título",
        "tesouro" to "Tesouro Nacional",
        "legacy" to "Legado",
        "cache" to "Cache",
        "cache_stale" to "Cache antigo",
        "fallback" to "Sem fonte",
    )

    fun quoteSourceLabel(source: String?): String = SOURCE_LABELS[source] ?: source?.takeIf { it.isNotEmpty() } ?: "Sem fonte"

    fun quoteStatusLabel(status: String?): String = when (status) {
        "fresh" -> "Atual"
        "stale" -> "Desatualizada"
        else -> "Sem cotação"
    }

    private val DATE_TIME = DateTimeFormatter.ofPattern("dd/MM/yy, HH:mm")

    /** "22/10/26, 14:03" na hora local (o toLocaleString da web); vazio "Sem atualização". */
    fun formatDateTime(value: String?, zone: ZoneId = ZoneId.systemDefault()): String {
        if (value.isNullOrEmpty()) return "Sem atualização"
        val instant = try {
            OffsetDateTime.parse(value).atZoneSameInstant(zone)
        } catch (error: DateTimeParseException) {
            try {
                java.time.LocalDateTime.parse(value).atZone(zone)
            } catch (again: DateTimeParseException) {
                return "Data inválida"
            }
        }
        return DATE_TIME.format(instant)
    }
}
