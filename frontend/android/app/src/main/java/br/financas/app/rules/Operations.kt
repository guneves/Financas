// Porte: mudou um, muda o outro, com um teste de cada lado.
// Par: pages/investimentos/helpers.js (movementDateValue, movementUnitPrice, movementTotalValue,
// movementFees, hasRealizedResult, parseNumberInput), o describeMovement/realizedDetail e a edicao
// de pages/investimentos/Operacoes.jsx, o formulario de components/InvestmentLaunchModal.jsx
// (assetTypeOf, movementAssetClass, Valor total, preco medio, as validacoes e os corpos de compra e
// venda) e o corpo de CorporateActionsPanel.jsx — tudo inline na web, sem teste de la. Aqui
// OperationsTest.kt. Diferenca deliberada: dinheiro em BigDecimal (a web soma em float e arredonda
// o preco medio com toFixed(6); aqui 6 casas HALF_UP, igual fora do ruido de float).
// Puro: nada de Android nem de Compose, roda nos testes de JVM.
package br.financas.app.rules

import br.financas.app.core.Js
import br.financas.app.core.formatCurrency
import br.financas.app.core.formatDateBR
import br.financas.app.core.formatDecimal
import br.financas.app.core.formatPercent
import br.financas.app.core.localDateOfTimestamp
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import java.math.BigDecimal
import java.math.RoundingMode
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException

object Operations {
    /** Um campo recusado pelo formulario, com o texto para a tela (o `throw new Error` da web). */
    class FormError(message: String) : IllegalArgumentException(message)

    // ---- Leitura do metadata (JSON livre do servidor) ----

    fun metaText(meta: JsonObject?, key: String): String? {
        val value = meta?.get(key) as? JsonPrimitive ?: return null
        if (value is JsonNull) return null
        return value.content.takeIf { it.isNotEmpty() }
    }

    fun metaNumber(meta: JsonObject?, key: String): BigDecimal? {
        val value = meta?.get(key) as? JsonPrimitive ?: return null
        if (value is JsonNull) return null
        return value.content.trim().takeIf { it.isNotEmpty() }?.toBigDecimalOrNull()
    }

    // O Boolean() do JS: false, 0, "" e null sao falsos.
    fun metaFlag(meta: JsonObject?, key: String): Boolean {
        val value = meta?.get(key) ?: return false
        if (value is JsonNull || value !is JsonPrimitive) return value !is JsonNull
        value.booleanOrNull?.let { return it }
        val text = value.content
        return text.isNotEmpty() && text != "0"
    }

    /** A conta do lancamento ligado: so `cash_account_id` texto conta (cashLinkFromMetadata). */
    fun cashAccountOf(meta: JsonObject?): String {
        val value = meta?.get("cash_account_id") as? JsonPrimitive ?: return ""
        return if (value.isString) Js.trim(value.content) else ""
    }

    /** O metadata de renda fixa de uma operacao ou posicao (o que FixedIncome le). */
    fun fixedIncomeMetadata(meta: JsonObject?): FixedIncome.Metadata = FixedIncome.Metadata(
        fixedIncomeType = metaText(meta, "fixed_income_type"),
        rateType = metaText(meta, "rate_type"),
        indexer = metaText(meta, "indexer"),
        cdiPercentage = metaNumber(meta, "cdi_percentage")?.toDouble(),
        annualRate = metaNumber(meta, "annual_rate")?.toDouble(),
        isTaxFree = metaFlag(meta, "is_tax_free"),
    )

    private fun metaListSize(meta: JsonObject?, key: String): Int = (meta?.get(key) as? JsonArray)?.size ?: 0

    // ---- Numeros digitados ----

    /**
     * O parseNumberInput da web: "1.234,5" (teclado brasileiro) ou "1234.5"; vazio vale 0 (o
     * Number('') do JS); ilegivel e null (NaN).
     */
    fun parseNumberInput(raw: String?): BigDecimal? {
        val text = Js.trim(raw ?: "")
        val normalized = if (text.contains(',')) text.replace(".", "").replaceFirst(",", ".") else text
        if (normalized.isEmpty()) return BigDecimal.ZERO
        return normalized.toBigDecimalOrNull()
    }

    /** O parseAmount do formulario de lancamento: como [parseNumberInput], com ilegivel valendo 0. */
    fun parseAmount(raw: String?): BigDecimal = parseNumberInput(raw) ?: BigDecimal.ZERO

    // ---- Uma operacao da lista ----

    /** Uma operacao, so o que as regras leem (OperationDto). */
    data class Movement(
        val id: String,
        val assetClass: String?,
        val quantity: BigDecimal?,
        val averagePrice: BigDecimal?,
        val currentPrice: BigDecimal?,
        val feeAmount: BigDecimal? = null,
        val createdAt: String? = null,
        val metadata: JsonObject? = null,
        val realizedProfit: BigDecimal? = null,
        val realizedFeeAmount: BigDecimal? = null,
        val realizedNetProceeds: BigDecimal? = null,
        val realizedMetadata: JsonObject? = null,
        val realizedProfitabilityPercent: BigDecimal? = null,
        val assetCategory: String? = null,
    )

    /** A data da operacao: resgate, venda ou compra digitada; senao o created_at. */
    fun movementDateValue(movement: Movement): String? =
        metaText(movement.metadata, "redemption_date")
            ?: metaText(movement.metadata, "sale_date")
            ?: metaText(movement.metadata, "purchase_date")
            ?: movement.createdAt

    fun isSale(movement: Movement): Boolean = (movement.quantity ?: BigDecimal.ZERO).signum() < 0

    fun unitPrice(movement: Movement): BigDecimal {
        if (metaFlag(movement.metadata, "is_redemption")) return movement.currentPrice ?: BigDecimal.ZERO
        val salePrice = metaNumber(movement.metadata, "sale_price")
        if (isSale(movement) && salePrice != null && salePrice.signum() != 0) return salePrice
        return movement.averagePrice ?: BigDecimal.ZERO
    }

    fun totalValue(movement: Movement): BigDecimal = ((movement.quantity ?: BigDecimal.ZERO) * unitPrice(movement)).abs()

    fun fees(movement: Movement): BigDecimal =
        movement.realizedFeeAmount ?: movement.feeAmount ?: metaNumber(movement.metadata, "other_costs") ?: BigDecimal.ZERO

    fun hasRealizedResult(movement: Movement): Boolean = movement.realizedProfit != null

    /** O que o cartao de uma operacao mostra (describeMovement). */
    data class Description(
        val isSale: Boolean,
        val isBonus: Boolean,
        val adjusted: Boolean,
        val inStatement: Boolean,
        val kind: String,
        val kindLabel: String,
        val unitPrice: BigDecimal,
        val totalValue: BigDecimal,
        val fees: BigDecimal,
        val hasResult: Boolean,
        val netProceeds: BigDecimal,
        val dateLabel: String,
    )

    private val TIME = DateTimeFormatter.ofPattern("HH:mm")

    fun describe(movement: Movement, zone: ZoneId = ZoneId.systemDefault()): Description {
        val fixed = movement.assetClass == "FIXED_INCOME"
        val sale = isSale(movement)
        val redemption = metaFlag(movement.metadata, "is_redemption")
        val total = totalValue(movement)
        val fee = fees(movement)
        val result = hasRealizedResult(movement)
        val net = if (result) movement.realizedNetProceeds ?: BigDecimal.ZERO else (total - fee).max(BigDecimal.ZERO)
        val dateValue = movementDateValue(movement)
        val custom = !dateValue.isNullOrEmpty() && dateValue != movement.createdAt
        val dateLabel = if (custom) {
            formatDateBR(dateValue!!.take(10))
        } else {
            val day = localDateOfTimestamp(movement.createdAt, zone)
            val time = try {
                TIME.format(OffsetDateTime.parse(movement.createdAt).atZoneSameInstant(zone))
            } catch (error: DateTimeParseException) {
                null
            } catch (error: NullPointerException) {
                null
            }
            formatDateBR(day) + (time?.let { " às $it" } ?: "")
        }
        val bonus = !metaText(movement.metadata, "corporate_action_id").isNullOrEmpty()
        val kind = when {
            bonus -> "Bonificação"
            fixed -> if (sale) "Resgate" else "Aporte"
            else -> if (sale) "Venda" else "Compra"
        }
        val quantityText = formatDecimal((movement.quantity ?: BigDecimal.ZERO).abs(), 6)
        val inStatement = cashAccountOf(movement.metadata).isNotEmpty()
        return Description(
            isSale = sale,
            isBonus = bonus,
            adjusted = metaListSize(movement.metadata, "corporate_adjustments") > 0,
            inStatement = inStatement,
            kind = kind,
            kindLabel = "$kind de ${if (redemption) formatCurrency(total) else quantityText}",
            unitPrice = unitPrice(movement),
            totalValue = total,
            fees = fee,
            hasResult = result,
            netProceeds = net,
            dateLabel = dateLabel,
        )
    }

    private val COST_METHOD_LABELS = mapOf("AVERAGE" to "custo médio", "FIFO" to "FIFO", "LOT_REDEMPTION" to "resgate do título")

    /** "−11,90% · custo médio" (realizedDetail); FIFO conta os lotes. */
    fun realizedDetail(movement: Movement): String {
        val method = metaText(movement.realizedMetadata, "cost_method")
        val label = COST_METHOD_LABELS[method] ?: method ?: "custo médio"
        val count = metaListSize(movement.realizedMetadata, "allocations")
        val lots = if (method == "FIFO" && count > 0) ", $count lote${if (count > 1) "s" else ""}" else ""
        return "${formatPercent(movement.realizedProfitabilityPercent, 2, signed = true)} · $label$lots"
    }

    // ---- Editar operacao ----

    /** O sheet "Editar operacao", como texto (openEditModal). */
    data class EditForm(
        val assetClass: String?,
        val tickerOrName: String,
        val quantity: String,
        val averagePrice: String,
        val currentPrice: BigDecimal?,
        val isSale: Boolean,
        val isRedemption: Boolean,
        val salePrice: String,
        val otherCosts: String,
        val fixedIncome: FixedIncome.Form,
        val isTreasuryBuy: Boolean,
        val treasuryUnits: String,
        val movementDate: String,
        val cashLink: PortfolioAccount.CashLink,
        val savedCashAccountId: String,
        val originalQuantity: BigDecimal,
    )

    private fun inputText(value: BigDecimal?): String = value?.stripTrailingZeros()?.toPlainString()?.replace('.', ',') ?: ""

    fun editForm(movement: Movement, tickerOrName: String, fixedIncomeMetadata: FixedIncome.Metadata): EditForm {
        val meta = movement.metadata
        val quantity = (movement.quantity ?: BigDecimal.ZERO).abs()
        val cashAccountId = cashAccountOf(meta)
        val redemption = metaFlag(meta, "is_redemption")
        return EditForm(
            assetClass = movement.assetClass,
            tickerOrName = tickerOrName,
            quantity = inputText(quantity),
            averagePrice = inputText(movement.averagePrice),
            currentPrice = movement.currentPrice,
            isSale = isSale(movement) && movement.assetClass != "FIXED_INCOME",
            isRedemption = redemption,
            salePrice = metaNumber(meta, "sale_price")?.takeIf { it.signum() != 0 }?.let(::inputText).orEmpty(),
            otherCosts = inputText(metaNumber(meta, "other_costs") ?: movement.feeAmount),
            fixedIncome = FixedIncome.fixedIncomeFormFromMetadata(fixedIncomeMetadata),
            isTreasuryBuy = movement.assetCategory == "TESOURO" && !redemption && (movement.quantity ?: BigDecimal.ZERO).signum() > 0,
            treasuryUnits = metaNumber(meta, "treasury_units")?.takeIf { it.signum() != 0 }?.let(::inputText).orEmpty(),
            movementDate = movementDateValue(movement)?.take(10).orEmpty(),
            cashLink = PortfolioAccount.CashLink(enabled = cashAccountId.isNotEmpty(), accountId = cashAccountId, missing = false),
            savedCashAccountId = cashAccountId,
            originalQuantity = quantity,
        )
    }

    private val DATE_KEYS = listOf("purchase_date", "sale_date", "redemption_date")

    /**
     * O corpo do PATCH /api/investments/<id> (handleSaveEdit): a quantidade com o sinal do tipo
     * gravado, o preco medio e o metadata de antes com as datas, os custos, a conta e a renda fixa
     * regravados. Um campo recusado e [FormError] (ou o RateError/CashLinkError das outras regras).
     */
    fun editPayload(form: EditForm, metadata: JsonObject?): Map<String, Any?> {
        val averagePrice = parseNumberInput(form.averagePrice)
        val finalQuantity = if (form.assetClass == "FIXED_INCOME") BigDecimal.ONE else parseNumberInput(form.quantity)
        val otherCosts = if (form.otherCosts.isEmpty()) BigDecimal.ZERO else parseNumberInput(form.otherCosts)
        if (averagePrice == null || averagePrice.signum() < 0) throw FormError("Informe um preço/valor válido.")
        if (otherCosts == null || otherCosts.signum() < 0) throw FormError("Informe custos válidos.")
        if (form.isSale) {
            val salePrice = parseNumberInput(form.salePrice)
            if (salePrice == null || salePrice.signum() <= 0) throw FormError("Informe um preço de venda válido.")
        }
        if (!form.isRedemption && (finalQuantity == null || finalQuantity.signum() <= 0)) throw FormError("Informe uma quantidade válida.")

        val next = LinkedHashMap<String, Any?>()
        metadata?.forEach { (key, value) -> next[key] = value }
        DATE_KEYS.forEach { next.remove(it) }
        next["other_costs"] = otherCosts
        next.putAll(PortfolioAccount.cashLinkMetadata(form.cashLink, editing = true))
        when {
            form.isRedemption -> {
                next["redemption_date"] = form.movementDate
                next["is_redemption"] = true
            }
            form.isSale -> {
                next["sale_date"] = form.movementDate
                val salePrice = parseNumberInput(form.salePrice)?.takeIf { it.signum() != 0 }
                next["sale_price"] = salePrice ?: form.currentPrice?.takeIf { it.signum() != 0 } ?: averagePrice
            }
            else -> next["purchase_date"] = form.movementDate
        }
        if (form.assetClass == "FIXED_INCOME" && !form.isRedemption) {
            FixedIncome.FIXED_INCOME_METADATA_KEYS.forEach { next.remove(it) }
            next.putAll(FixedIncome.fixedIncomeMetadataFromForm(form.fixedIncome))
        }
        if (form.isTreasuryBuy) {
            val units = TreasuryLabels.parseTreasuryUnits(form.treasuryUnits)
            when {
                units == null -> next.remove("treasury_units")
                units.isNaN() -> throw FormError("Informe uma quantidade de títulos válida.")
                else -> next["treasury_units"] = units
            }
        }
        val quantity = when {
            form.isRedemption -> form.originalQuantity.negate()
            form.isSale -> finalQuantity!!.negate()
            else -> finalQuantity!!
        }
        return linkedMapOf("quantity" to quantity, "average_price" to averagePrice, "metadata" to next)
    }

    // ---- Registrar operacao ----

    const val BITCOIN = "BITCOIN"
    const val BITCOIN_TICKER = "BTC"
    const val ETF = "ETF"
    const val TREASURY = "TESOURO"

    /** Os tipos de ativo da tela, na ordem do seletor. */
    val ASSET_TYPES = listOf(
        "STOCKS" to "Ações",
        ETF to "ETFs",
        "REIT" to "Fundos Imobiliários",
        "FIXED_INCOME" to "Renda Fixa",
        TREASURY to "Tesouro Direto",
        BITCOIN to "Bitcoin",
        "OTHER" to "Outros",
    )

    /** Os tipos com cotacao na B3: o ativo vem do catalogo, nao de texto livre. */
    val CATALOG_ASSET_TYPES = listOf("STOCKS", ETF, "REIT")

    /** O tipo da tela -> a classe gravada (ETF e acao, Tesouro e renda fixa, Bitcoin e Outros). */
    fun movementAssetClass(assetType: String): String = when (assetType) {
        BITCOIN -> "OTHER"
        ETF -> "STOCKS"
        TREASURY -> "FIXED_INCOME"
        else -> assetType
    }

    /** O tipo da tela de uma posicao (a venda abre no tipo dela). */
    fun assetTypeOf(assetClass: String?, marketKind: String?, category: String?): String = when {
        assetClass == null -> "STOCKS"
        marketKind == "CRIPTO" -> BITCOIN
        category == "ETF" -> ETF
        category == "TESOURO" -> TREASURY
        else -> assetClass
    }

    fun normalizeAssetName(value: String?): String = Js.trim(value ?: "").uppercase()

    /** O formulario de "Registrar operacao", como o dono digita. */
    data class LaunchForm(
        val mode: String = "BUY",
        val assetType: String = "STOCKS",
        val tickerOrName: String = "",
        val tickerConfirmed: Boolean = false,
        val assetId: String = "",
        val date: String = "",
        val quantity: String = "1",
        val price: String = "",
        val otherCosts: String = "",
        val treasuryUnits: String = "",
        val fixedIncome: FixedIncome.Form = FixedIncome.emptyFixedIncomeForm(),
        val cashLink: PortfolioAccount.CashLink = PortfolioAccount.emptyCashLink(),
    ) {
        val isFixedIncome: Boolean get() = movementAssetClass(assetType) == "FIXED_INCOME"
        val usesCatalog: Boolean get() = mode == "BUY" && assetType in CATALOG_ASSET_TYPES
    }

    /** A posicao vendida, so o que a venda le. */
    data class SaleAsset(
        val assetClass: String,
        val ticker: String,
        val quantity: BigDecimal,
        val averagePrice: BigDecimal?,
        val currentPrice: BigDecimal?,
    )

    fun launchQuantity(form: LaunchForm): BigDecimal =
        if (form.mode == "BUY" && form.isFixedIncome) BigDecimal.ONE else parseAmount(form.quantity)

    /** O "Valor total" ao vivo: venda q × p − custos (nunca negativo); renda fixa p + custos; compra q × p + custos. */
    fun launchTotal(form: LaunchForm): BigDecimal {
        val quantity = launchQuantity(form)
        val price = parseAmount(form.price)
        val costs = parseAmount(form.otherCosts)
        return when {
            form.mode == "SELL" -> (quantity * price - costs).max(BigDecimal.ZERO)
            form.isFixedIncome -> price + costs
            else -> quantity * price + costs
        }
    }

    /** Trocar o tipo de ativo: o ativo recomeca (Bitcoin ja vem como BTC) e a renda fixa do tipo. */
    fun changeAssetType(form: LaunchForm, assetType: String): LaunchForm = form.copy(
        assetType = assetType,
        tickerOrName = if (assetType == BITCOIN) BITCOIN_TICKER else "",
        tickerConfirmed = false,
        fixedIncome = if (assetType == TREASURY) FixedIncome.emptyFixedIncomeForm().copy(fixedIncomeType = FixedIncome.TREASURY_TYPE) else FixedIncome.emptyFixedIncomeForm(),
        treasuryUnits = "",
    )

    /** O nome do titulo de renda fixa; no Tesouro, o nome ja diz a rentabilidade (zera a taxa ao mudar). */
    fun changeFixedIncomeName(form: LaunchForm, name: String): LaunchForm {
        val mode = if (form.assetType == TREASURY) FixedIncome.treasuryRateMode(name) else null
        val current = form.fixedIncome
        val fixedIncome = if (mode != null && mode != FixedIncome.rateModeOf(current.rateType, current.indexer)) {
            val (rateType, indexer) = FixedIncome.rateFieldsForMode(mode)
            current.copy(rateType = rateType, indexer = indexer, rate = "")
        } else {
            current
        }
        return form.copy(tickerOrName = name, fixedIncome = fixedIncome)
    }

    /** Trocar Compra/Venda: ativo, quantidade, preco e custos recomecam; a venda volta a Acoes. */
    fun changeMode(form: LaunchForm, mode: String): LaunchForm = form.copy(
        mode = mode,
        assetId = "",
        tickerOrName = "",
        quantity = "1",
        price = "",
        otherCosts = "",
        assetType = if (mode == "SELL") "STOCKS" else form.assetType,
    )

    /** O ticker digitado precisa passar pelo catalogo? (nao escolhido da lista nem ja na carteira) */
    fun needsCatalogCheck(form: LaunchForm, walletNames: List<String>): Boolean {
        if (!form.usesCatalog || form.tickerConfirmed) return false
        val ticker = normalizeAssetName(form.tickerOrName)
        return walletNames.none { normalizeAssetName(it) == ticker }
    }

    fun notInCatalogMessage(ticker: String): String = "$ticker não está na lista da B3. Selecione um ativo pela busca."

    /**
     * O corpo da compra (createBuyMovement), um objeto so: a classe gravada, o ticker em caixa
     * alta, a quantidade (1 na renda fixa), o preco medio com os custos (6 casas), a cotacao da
     * posicao que ja existe (senao o preco digitado) e o metadata com a data, os custos, a renda
     * fixa e a conta. [existingCurrentPrice]: a cotacao da posicao de mesmo nome, se houver.
     */
    fun buyPayload(form: LaunchForm, existingCurrentPrice: BigDecimal?, existing: Boolean): Map<String, Any?> {
        val ticker = normalizeAssetName(form.tickerOrName)
        if (ticker.isEmpty()) throw FormError("Informe o ativo do lançamento.")
        val price = parseAmount(form.price)
        val quantity = launchQuantity(form)
        val costs = parseAmount(form.otherCosts)
        if (price.signum() <= 0) throw FormError("Informe um preço válido.")
        if (!form.isFixedIncome && quantity.signum() <= 0) throw FormError("Informe uma quantidade válida.")
        val finalQuantity = if (form.isFixedIncome) BigDecimal.ONE else quantity
        val gross = if (form.isFixedIncome) price else price * finalQuantity
        val averagePrice = if (form.isFixedIncome) gross + costs else (gross + costs).divide(finalQuantity, 6, RoundingMode.HALF_UP)

        val metadata = LinkedHashMap<String, Any?>()
        if (form.isFixedIncome) {
            val fixedForm = if (form.assetType == TREASURY) form.fixedIncome.copy(fixedIncomeType = FixedIncome.TREASURY_TYPE) else form.fixedIncome
            metadata.putAll(FixedIncome.fixedIncomeMetadataFromForm(fixedForm))
        }
        metadata["purchase_date"] = form.date
        metadata["other_costs"] = costs
        if (form.assetType == TREASURY) {
            val units = TreasuryLabels.parseTreasuryUnits(form.treasuryUnits)
            if (units != null) {
                if (units.isNaN()) throw FormError("Informe uma quantidade de títulos válida.")
                metadata["treasury_units"] = units
            }
        }
        metadata.putAll(PortfolioAccount.cashLinkMetadata(form.cashLink))
        return linkedMapOf(
            "asset_class" to movementAssetClass(form.assetType),
            "ticker_or_name" to ticker,
            "quantity" to finalQuantity,
            "average_price" to averagePrice.stripTrailingZeros(),
            "current_price" to if (existing) existingCurrentPrice else price,
            "metadata" to metadata,
        )
    }

    /** O corpo da venda (createSellMovement): a quantidade com "−", o preco e a data da venda. */
    fun sellPayload(form: LaunchForm, asset: SaleAsset?): Map<String, Any?> {
        if (asset == null) throw FormError("Selecione o ativo para venda.")
        val quantity = launchQuantity(form)
        val price = parseAmount(form.price)
        if (quantity.signum() <= 0) throw FormError("Informe uma quantidade válida.")
        if (quantity > asset.quantity) throw FormError("A quantidade informada é maior do que a posição disponível.")
        if (price.signum() <= 0) throw FormError("Informe o preço da venda.")
        val metadata = linkedMapOf<String, Any?>(
            "sale_date" to form.date,
            "sale_price" to price,
            "other_costs" to parseAmount(form.otherCosts),
        )
        metadata.putAll(PortfolioAccount.cashLinkMetadata(form.cashLink))
        return linkedMapOf(
            "asset_class" to asset.assetClass,
            "ticker_or_name" to asset.ticker,
            "quantity" to quantity.negate(),
            "average_price" to asset.averagePrice,
            "current_price" to asset.currentPrice,
            "metadata" to metadata,
        )
    }

    /** O preco sugerido na venda: a cotacao da carteira, como o dono digita. */
    fun saleUnitPrice(currentPrice: BigDecimal?): String =
        currentPrice?.takeIf { it.signum() != 0 }?.let(::inputText).orEmpty()

    // ---- Eventos corporativos ----

    val CORPORATE_TYPES = listOf("SPLIT" to "Desdobramento", "REVERSE_SPLIT" to "Grupamento", "BONUS" to "Bonificação")

    val CORPORATE_HINTS = mapOf(
        "SPLIT" to "Cada cota vira mais de uma. Ex.: 1 para 2 dobra a quantidade e divide o preço médio por 2.",
        "REVERSE_SPLIT" to "Várias cotas viram uma. Ex.: 10 para 1. Sobra de fração vendida pela corretora entra como venda.",
        "BONUS" to "Cotas novas sem pagamento. Ex.: 10 para 1 = 1 cota nova para cada 10. O custo atribuído vem no aviso da empresa.",
    )

    val DEFAULT_RATIOS = mapOf("SPLIT" to ("1" to "2"), "REVERSE_SPLIT" to ("10" to "1"), "BONUS" to ("10" to "1"))

    /** "1 para 2", com ate 6 casas. */
    fun ratioLabel(from: BigDecimal?, to: BigDecimal?): String =
        "${formatDecimal(from ?: BigDecimal.ZERO, 6)} para ${formatDecimal(to ?: BigDecimal.ZERO, 6)}"

    // parseDecimal: vazio = ausente (a chave nao vai); ilegivel = null (o NaN que o JSON manda null).
    private sealed interface Decimal {
        data object Absent : Decimal
        data class Value(val value: BigDecimal?) : Decimal
    }

    private fun parseDecimal(raw: String?): Decimal {
        val text = Js.trim(raw ?: "")
        if (text.isEmpty()) return Decimal.Absent
        val normalized = if (text.contains(',')) text.replace(".", "").replace(",", ".") else text
        return Decimal.Value(normalized.toBigDecimalOrNull())
    }

    /** O corpo de POST /api/corporate-actions (sem o client_id, que o ViewModel poe). */
    fun corporateActionPayload(
        assetId: String,
        actionType: String,
        exDate: String,
        ratioFrom: String,
        ratioTo: String,
        bonusUnitCost: String,
        notes: String,
    ): Map<String, Any?> {
        val body = linkedMapOf<String, Any?>("asset_id" to assetId, "action_type" to actionType, "ex_date" to exDate)
        (parseDecimal(ratioFrom) as? Decimal.Value)?.let { body["ratio_from"] = it.value }
        (parseDecimal(ratioTo) as? Decimal.Value)?.let { body["ratio_to"] = it.value }
        if (actionType == "BONUS") (parseDecimal(bonusUnitCost) as? Decimal.Value)?.let { body["bonus_unit_cost"] = it.value }
        if (notes.isNotEmpty()) body["notes"] = notes
        return body
    }

    /** O JSON livre do metadata como mapa de [JsonElement] (o `{ ...mov.metadata }` da web). */
    fun metadataMap(meta: JsonObject?): Map<String, JsonElement> = meta?.toMap().orEmpty()
}
