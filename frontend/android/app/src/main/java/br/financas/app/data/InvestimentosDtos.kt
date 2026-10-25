package br.financas.app.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

// As leituras de Investimentos (12 a 16 de mobile-docs/native/screens/): os nomes do JSON do
// servidor, so os campos que as telas nativas leem. Numeros sao Money (BigDecimal do texto), tambem
// os percentuais: nada passa por Double.

/** A cotacao de uma posicao: fresh/stale/missing, a fonte e quando. */
@Serializable
data class QuoteInfoDto(
    val status: String? = null,
    val source: String? = null,
    @SerialName("quoted_at") val quotedAt: String? = null,
)

/** Uma compra de um titulo do Tesouro agrupado (services/treasury.py, lot_payload + finish_lots). */
@Serializable
data class TreasuryLotDto(
    val id: String? = null,
    @SerialName("purchase_date") val purchaseDate: String? = null,
    val invested: Money? = null,
    val rate: Money? = null,
    val units: Money? = null,
    val gross: Money? = null,
    val net: Money? = null,
)

/** O bloco `treasury` de uma posicao do Tesouro. */
@Serializable
data class TreasuryInfoDto(
    @SerialName("title_type") val titleType: String? = null,
    @SerialName("maturity_date") val maturityDate: String? = null,
    val units: Money? = null,
    @SerialName("average_rate") val averageRate: Money? = null,
    @SerialName("market_pu") val marketPu: Money? = null,
    @SerialName("market_rate") val marketRate: Money? = null,
    @SerialName("price_date") val priceDate: String? = null,
    val valuation: String? = null,
    val custody: Money? = null,
    val iof: Money? = null,
    @SerialName("income_tax") val incomeTax: Money? = null,
    @SerialName("lot_count") val lotCount: Int? = null,
)

/** Uma posicao de GET /api/investments/portfolio (build_portfolio_snapshot). */
@Serializable
data class PortfolioAssetDto(
    val id: String,
    @SerialName("asset_id") val assetId: String? = null,
    @SerialName("asset_ids") val assetIds: List<String> = emptyList(),
    val ticker: String? = null,
    val name: String? = null,
    @SerialName("class") val assetClass: String? = null,
    @SerialName("market_kind") val marketKind: String? = null,
    val category: String? = null,
    @SerialName("category_label") val categoryLabel: String? = null,
    @SerialName("rate_kind") val rateKind: String? = null,
    @SerialName("fixed_income_type") val fixedIncomeType: String? = null,
    val quantity: Money? = null,
    @SerialName("average_price") val averagePrice: Money? = null,
    @SerialName("current_price") val currentPrice: Money? = null,
    @SerialName("total_invested") val totalInvested: Money? = null,
    @SerialName("current_value") val currentValue: Money? = null,
    @SerialName("net_value") val netValue: Money? = null,
    @SerialName("profitability_percent") val profitabilityPercent: Money? = null,
    @SerialName("proceeds_net") val proceedsNet: Money? = null,
    @SerialName("total_return_percent") val totalReturnPercent: Money? = null,
    val quote: QuoteInfoDto? = null,
    val metadata: JsonObject? = null,
    val lots: List<TreasuryLotDto> = emptyList(),
    val treasury: TreasuryInfoDto? = null,
)

/** realized_result do portfolio: as somas das vendas e resgates (o resumo de Operacoes). */
@Serializable
data class RealizedResultDto(
    @SerialName("net_profit_after_tax") val netProfitAfterTax: Money? = null,
    @SerialName("realized_profit") val realizedProfit: Money? = null,
    @SerialName("tax_amount") val taxAmount: Money? = null,
    @SerialName("cost_basis") val costBasis: Money? = null,
    @SerialName("operation_count") val operationCount: Int = 0,
)

@Serializable
data class PortfolioDto(
    @SerialName("total_invested") val totalInvested: Money? = null,
    @SerialName("current_balance") val currentBalance: Money? = null,
    @SerialName("current_net_balance") val currentNetBalance: Money? = null,
    @SerialName("gross_portfolio_profitability") val grossProfitability: Money? = null,
    val assets: List<PortfolioAssetDto> = emptyList(),
    @SerialName("realized_result") val realizedResult: RealizedResultDto? = null,
)

/** Um mes de GET /api/investments/history (Evolucao do Patrimonio). */
@Serializable
data class EvolutionPointDto(
    val month: String? = null,
    @SerialName("month_key") val monthKey: String? = null,
    val patrimonio: Money? = null,
    val patrimonioBruto: Money? = null,
    val valorAplicado: Money? = null,
    val ganhoCapitalBruto: Money? = null,
)

@Serializable
data class InvestmentHistoryDto(val evolution: List<EvolutionPointDto> = emptyList())

/** Um ativo nas listas de POST /api/investments/update-prices. */
@Serializable
data class QuoteAssetDto(
    val ticker: String? = null,
    val name: String? = null,
    val error: String? = null,
)

@Serializable
data class QuoteUpdateDto(
    @SerialName("updated_count") val updatedCount: Int = 0,
    @SerialName("updated_assets") val updatedAssets: List<QuoteAssetDto> = emptyList(),
    @SerialName("failed_assets") val failedAssets: List<QuoteAssetDto> = emptyList(),
    @SerialName("cached_assets") val cachedAssets: List<QuoteAssetDto> = emptyList(),
    @SerialName("stale_assets") val staleAssets: List<QuoteAssetDto> = emptyList(),
)

/** As colunas de exportacao de Investimentos (GET /api/exports/columns). */
@Serializable
data class InvestmentExportColumnsDto(
    val portfolio: List<ExportColumnDto> = emptyList(),
    val movements: List<ExportColumnDto> = emptyList(),
    val proceeds: List<ExportColumnDto> = emptyList(),
)

/**
 * Uma operacao de GET /api/investments (Operacoes): o que o Extrato de investimentos le
 * (InvestmentMovementDto) mais o resultado realizado de cada venda e resgate.
 */
@Serializable
data class OperationDto(
    val id: String,
    @SerialName("asset_id") val assetId: String? = null,
    @SerialName("asset_class") val assetClass: String? = null,
    @SerialName("asset_category") val assetCategory: String? = null,
    @SerialName("asset_category_label") val assetCategoryLabel: String? = null,
    @SerialName("ticker_or_name") val tickerOrName: String? = null,
    val quantity: Money? = null,
    @SerialName("average_price") val averagePrice: Money? = null,
    @SerialName("current_price") val currentPrice: Money? = null,
    @SerialName("fee_amount") val feeAmount: Money? = null,
    @SerialName("created_at") val createdAt: String? = null,
    val metadata: JsonObject? = null,
    @SerialName("realized_profit") val realizedProfit: Money? = null,
    @SerialName("realized_tax_amount") val realizedTaxAmount: Money? = null,
    @SerialName("realized_tax_rate") val realizedTaxRate: Money? = null,
    @SerialName("realized_net_profit_after_tax") val realizedNetProfitAfterTax: Money? = null,
    @SerialName("realized_net_proceeds") val realizedNetProceeds: Money? = null,
    @SerialName("realized_cost_basis") val realizedCostBasis: Money? = null,
    @SerialName("realized_profitability_percent") val realizedProfitabilityPercent: Money? = null,
    @SerialName("realized_fee_amount") val realizedFeeAmount: Money? = null,
    @SerialName("realized_metadata") val realizedMetadata: JsonObject? = null,
)

/** Um evento corporativo de GET /api/corporate-actions. */
@Serializable
data class CorporateActionDto(
    val id: String,
    @SerialName("asset_id") val assetId: String? = null,
    val ticker: String? = null,
    @SerialName("action_type") val actionType: String? = null,
    val label: String? = null,
    @SerialName("ex_date") val exDate: String? = null,
    @SerialName("ratio_from") val ratioFrom: Money? = null,
    @SerialName("ratio_to") val ratioTo: Money? = null,
    @SerialName("bonus_unit_cost") val bonusUnitCost: Money? = null,
    val notes: String? = null,
    @SerialName("price_refreshed") val priceRefreshed: Boolean? = null,
)

/** Um papel do catalogo da B3 (GET /api/market/tickers). */
@Serializable
data class MarketTickerDto(
    val ticker: String,
    val name: String? = null,
    val kind: String? = null,
    @SerialName("kind_label") val kindLabel: String? = null,
    @SerialName("asset_class") val assetClass: String? = null,
)

/** GET /api/tax-report/exemption: o medidor da isencao de acoes num mes. */
@Serializable
data class ExemptionDto(
    val month: String? = null,
    val limit: Money? = null,
    @SerialName("sales_after") val salesAfter: Money? = null,
    val remaining: Money? = null,
    val exempt: Boolean = true,
    @SerialName("would_exceed") val wouldExceed: Boolean = false,
    val eligible: Boolean = true,
    val kind: String? = null,
    @SerialName("stock_sales") val stockSales: Money? = null,
    @SerialName("stock_tax") val stockTax: Money? = null,
    val percent: Money? = null,
    @SerialName("stock_result") val stockResult: Money? = null,
    @SerialName("stock_loss_balance") val stockLossBalance: Money? = null,
    @SerialName("reit_sales") val reitSales: Money? = null,
    @SerialName("reit_tax") val reitTax: Money? = null,
    val darf: Money? = null,
)

// ---- Proventos ----

/** Um ativo de GET /api/assets (o seletor de Registrar provento). */
@Serializable
data class AssetDto(
    val id: String,
    val ticker: String? = null,
    val name: String? = null,
    @SerialName("asset_class") val assetClass: String? = null,
    val category: String? = null,
    @SerialName("category_label") val categoryLabel: String? = null,
)

@Serializable
data class ProceedRowAssetDto(
    val ticker: String? = null,
    @SerialName("asset_class") val assetClass: String? = null,
    val name: String? = null,
)

/** Um provento de GET /api/investment-proceeds (Historico de proventos). */
@Serializable
data class ProceedDto(
    val id: String,
    @SerialName("asset_id") val assetId: String? = null,
    val asset: ProceedRowAssetDto? = null,
    @SerialName("proceeds_type") val proceedsType: String? = null,
    @SerialName("declared_date") val declaredDate: String? = null,
    @SerialName("record_date") val recordDate: String? = null,
    @SerialName("ex_date") val exDate: String? = null,
    @SerialName("payment_date") val paymentDate: String? = null,
    @SerialName("amount_per_unit") val amountPerUnit: Money? = null,
    @SerialName("eligible_quantity") val eligibleQuantity: Money? = null,
    @SerialName("gross_amount") val grossAmount: Money? = null,
    @SerialName("tax_amount") val taxAmount: Money? = null,
    @SerialName("net_amount") val netAmount: Money? = null,
    val notes: String? = null,
    val status: String? = null,
    @SerialName("sync_key") val syncKey: String? = null,
    @SerialName("yield_on_cost_percent") val yieldOnCostPercent: Money? = null,
)

@Serializable
data class ProceedsMonthDto(
    val month: String? = null,
    @SerialName("net_amount") val netAmount: Money? = null,
    @SerialName("event_count") val eventCount: Int = 0,
)

@Serializable
data class ProceedsYearDto(
    val year: Int = 0,
    @SerialName("net_amount") val netAmount: Money? = null,
    @SerialName("event_count") val eventCount: Int = 0,
)

@Serializable
data class ProceedsByAssetDto(
    @SerialName("asset_id") val assetId: String? = null,
    val ticker: String? = null,
    @SerialName("event_count") val eventCount: Int = 0,
    @SerialName("net_amount") val netAmount: Money? = null,
    @SerialName("net_12m") val net12m: Money? = null,
    @SerialName("yield_on_cost_percent") val yieldOnCostPercent: Money? = null,
    @SerialName("share_percent") val sharePercent: Money? = null,
)

@Serializable
data class ProceedsSummaryDto(
    @SerialName("event_count") val eventCount: Int = 0,
    @SerialName("gross_amount") val grossAmount: Money? = null,
    @SerialName("tax_amount") val taxAmount: Money? = null,
    @SerialName("net_amount") val netAmount: Money? = null,
    @SerialName("yield_on_cost_percent") val yieldOnCostPercent: Money? = null,
    @SerialName("scheduled_net_amount") val scheduledNetAmount: Money? = null,
    @SerialName("by_month") val byMonth: List<ProceedsMonthDto> = emptyList(),
    @SerialName("by_year") val byYear: List<ProceedsYearDto> = emptyList(),
    @SerialName("by_asset") val byAsset: List<ProceedsByAssetDto> = emptyList(),
)

/** POST /api/investment-proceeds/sync. */
@Serializable
data class ProceedsSyncDto(
    val status: String? = null,
    val message: String? = null,
    val created: Int = 0,
    val updated: Int = 0,
    val removed: Int = 0,
)

// ---- Rentabilidade ----

@Serializable
data class ReturnsPeriodDto(val start: String? = null, val end: String? = null)

@Serializable
data class ReturnsComparisonDto(
    @SerialName("base_month") val baseMonth: String? = null,
    val start: String? = null,
    val end: String? = null,
    val months: Int? = null,
    @SerialName("starts_after_window") val startsAfterWindow: Boolean = false,
)

@Serializable
data class BenchmarkDto(
    val code: String,
    val label: String? = null,
    val available: Boolean = false,
    val complete: Boolean = true,
    @SerialName("months_covered") val monthsCovered: Int? = null,
    @SerialName("months_total") val monthsTotal: Int? = null,
    @SerialName("period_percent") val periodPercent: Money? = null,
    @SerialName("difference_pp") val differencePp: Money? = null,
    val note: String? = null,
)

@Serializable
data class BenchmarkPointDto(@SerialName("accumulated_percent") val accumulatedPercent: Money? = null)

@Serializable
data class ReturnsPointDto(
    val base: Boolean = false,
    @SerialName("month_key") val monthKey: String? = null,
    @SerialName("accumulated_percent") val accumulatedPercent: Money? = null,
    @SerialName("cdi_accumulated_percent") val cdiAccumulatedPercent: Money? = null,
    val value: Money? = null,
    val benchmarks: Map<String, BenchmarkPointDto?> = emptyMap(),
)

@Serializable
data class ReturnsYearDto(
    val year: Int = 0,
    val months: List<Money?> = emptyList(),
    @SerialName("total_percent") val totalPercent: Money? = null,
)

@Serializable
data class ReturnsAssetDto(
    val key: String? = null,
    val ticker: String? = null,
    @SerialName("class") val assetClass: String? = null,
    @SerialName("twr_percent") val twrPercent: Money? = null,
    val since: String? = null,
    val capped: Boolean = false,
    val open: Boolean = true,
    @SerialName("current_value") val currentValue: Money? = null,
)

@Serializable
data class ReturnsDto(
    @SerialName("twr_percent") val twrPercent: Money? = null,
    @SerialName("ytd_percent") val ytdPercent: Money? = null,
    @SerialName("cdi_available") val cdiAvailable: Boolean = false,
    @SerialName("cdi_percent") val cdiPercent: Money? = null,
    @SerialName("percent_of_cdi") val percentOfCdi: Money? = null,
    val period: ReturnsPeriodDto? = null,
    val comparison: ReturnsComparisonDto? = null,
    val benchmarks: List<BenchmarkDto> = emptyList(),
    val series: List<ReturnsPointDto> = emptyList(),
    val years: List<ReturnsYearDto> = emptyList(),
    val assets: List<ReturnsAssetDto> = emptyList(),
    @SerialName("basis_label") val basisLabel: String? = null,
    val notes: List<String> = emptyList(),
)

/** GET /api/investments/contributions (Aportes e resgates, em Operacoes). */
@Serializable
data class ContributionMonthDto(
    val month: String? = null,
    val aportes: Money? = null,
    val resgates: Money? = null,
    val liquido: Money? = null,
)

@Serializable
data class ContributionTotalsDto(
    val aportes: Money? = null,
    val resgates: Money? = null,
    val liquido: Money? = null,
    val count: Int = 0,
)

@Serializable
data class ContributionsDto(
    val months: List<ContributionMonthDto> = emptyList(),
    val totals: ContributionTotalsDto = ContributionTotalsDto(),
)

// ---- Alocacao ----

@Serializable
data class AllocationAssetDto(
    @SerialName("asset_id") val assetId: String? = null,
    val ticker: String? = null,
    val value: Money? = null,
    @SerialName("percent_in_class") val percentInClass: Money? = null,
    @SerialName("target_percent") val targetPercent: Money? = null,
    @SerialName("gap_value") val gapValue: Money? = null,
    val suggested: Money? = null,
    @SerialName("below_average_price") val belowAveragePrice: Boolean = false,
)

@Serializable
data class AllocationClassDto(
    @SerialName("asset_class") val assetClass: String,
    val value: Money? = null,
    val percent: Money? = null,
    @SerialName("target_percent") val targetPercent: Money? = null,
    @SerialName("diff_percent") val diffPercent: Money? = null,
    @SerialName("gap_value") val gapValue: Money? = null,
    val suggested: Money? = null,
    @SerialName("has_asset_targets") val hasAssetTargets: Boolean = false,
    val assets: List<AllocationAssetDto> = emptyList(),
)

@Serializable
data class OpportunityDto(
    @SerialName("asset_id") val assetId: String? = null,
    val ticker: String? = null,
    @SerialName("asset_class") val assetClass: String? = null,
    @SerialName("current_price") val currentPrice: Money? = null,
    @SerialName("average_price") val averagePrice: Money? = null,
    @SerialName("percent_in_class") val percentInClass: Money? = null,
    @SerialName("target_percent") val targetPercent: Money? = null,
)

@Serializable
data class ConcentrationAssetDto(
    @SerialName("asset_id") val assetId: String? = null,
    val ticker: String? = null,
    val percent: Money? = null,
)

@Serializable
data class ConcentrationDto(
    @SerialName("threshold_percent") val thresholdPercent: Money? = null,
    @SerialName("assets_over_threshold") val assetsOverThreshold: List<ConcentrationAssetDto> = emptyList(),
)

@Serializable
data class AllocationDto(
    val total: Money? = null,
    @SerialName("has_class_targets") val hasClassTargets: Boolean = false,
    val classes: List<AllocationClassDto> = emptyList(),
    val opportunities: List<OpportunityDto> = emptyList(),
    val concentration: ConcentrationDto = ConcentrationDto(),
)

@Serializable
data class SectorAssetDto(
    @SerialName("asset_id") val assetId: String? = null,
    val ticker: String? = null,
    @SerialName("category_label") val categoryLabel: String? = null,
    val segment: String? = null,
    val source: String? = null,
    val value: Money? = null,
    @SerialName("percent_in_sector") val percentInSector: Money? = null,
    @SerialName("percent_of_total") val percentOfTotal: Money? = null,
)

@Serializable
data class SectorDto(
    val sector: String? = null,
    val label: String? = null,
    val value: Money? = null,
    val percent: Money? = null,
    val assets: List<SectorAssetDto> = emptyList(),
)

@Serializable
data class SectorsDto(
    val sectors: List<SectorDto> = emptyList(),
    @SerialName("unassigned_value") val unassignedValue: Money? = null,
)

// ---- IR (so o que o celular mostra: o medidor e os meses de DARF) ----

@Serializable
data class TaxStocksMonthDto(
    val sales: Money? = null,
    val result: Money? = null,
    val exempt: Boolean = false,
    @SerialName("loss_used") val lossUsed: Money? = null,
)

@Serializable
data class TaxEtfsMonthDto(val sales: Money? = null, val result: Money? = null)

@Serializable
data class TaxReitsMonthDto(
    val sales: Money? = null,
    val result: Money? = null,
    @SerialName("loss_used") val lossUsed: Money? = null,
)

@Serializable
data class TaxMonthDto(
    val month: String,
    val stocks: TaxStocksMonthDto = TaxStocksMonthDto(),
    val etfs: TaxEtfsMonthDto = TaxEtfsMonthDto(),
    val reits: TaxReitsMonthDto = TaxReitsMonthDto(),
    val darf: Money? = null,
    @SerialName("darf_carried") val darfCarried: Money? = null,
)

@Serializable
data class TaxTotalsDto(
    @SerialName("tax_due") val taxDue: Money? = null,
    @SerialName("stock_loss_balance") val stockLossBalance: Money? = null,
    @SerialName("etf_loss_balance") val etfLossBalance: Money? = null,
    @SerialName("reit_loss_balance") val reitLossBalance: Money? = null,
)

@Serializable
data class RendaVariavelDto(
    val months: List<TaxMonthDto> = emptyList(),
    val totals: TaxTotalsDto = TaxTotalsDto(),
)

@Serializable
data class TaxReportDto(
    @SerialName("available_years") val availableYears: List<Int> = emptyList(),
    @SerialName("renda_variavel") val rendaVariavel: RendaVariavelDto = RendaVariavelDto(),
)
