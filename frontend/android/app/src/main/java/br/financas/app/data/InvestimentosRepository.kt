package br.financas.app.data

import kotlinx.coroutines.flow.Flow
import kotlinx.serialization.DeserializationStrategy
import kotlinx.serialization.SerializationException
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json

/**
 * Investimentos (Posicao, Operacoes, Proventos, Rentabilidade, Alocacao, IR) sobre a API, os
 * mesmos pedidos da web: as leituras com a copia guardada primeiro (CachedReader), as escritas so
 * com o servidor e sem prazo (writeApi). As duas criacoes que a fila guarda sem conexao (a
 * operacao e o provento) nao passam por aqui: vao pelo EntrySaver (ui/investimentos/).
 */
class InvestimentosRepository(
    private val reader: CachedReader,
    private val fetcher: Fetcher,
    private val sender: Sender,
    private val files: FileApi,
    private val json: Json = ApiJson,
) {
    // ---- Leituras ----

    fun portfolio(): Flow<Load<PortfolioDto>> = reader.read(PORTFOLIO_PATH, PortfolioDto.serializer())

    /** A conta investimento (049); 404 sem Corretora. */
    fun settlement(): Flow<Load<SettlementDto>> = reader.read(SETTLEMENT_PATH, SettlementDto.serializer())

    fun operations(): Flow<Load<List<OperationDto>>> =
        reader.read(LancamentosRepository.INVESTMENTS_PATH, ListSerializer(OperationDto.serializer()))

    fun history(months: Int): Flow<Load<InvestmentHistoryDto>> =
        reader.read("/api/investments/history?months=$months", InvestmentHistoryDto.serializer())

    fun corporateActions(): Flow<Load<List<CorporateActionDto>>> =
        reader.read(CORPORATE_ACTIONS_PATH, ListSerializer(CorporateActionDto.serializer()))

    fun contributions(months: Int, assetClass: String): Flow<Load<ContributionsDto>> =
        reader.read("/api/investments/contributions" + query(mapOf("months" to months.toString(), "asset_class" to assetClass)), ContributionsDto.serializer())

    fun returns(months: String, assetClass: String): Flow<Load<ReturnsDto>> =
        reader.read("/api/investments/returns" + query(mapOf("months" to months, "asset_class" to assetClass)), ReturnsDto.serializer())

    fun assets(): Flow<Load<List<AssetDto>>> = reader.read(ASSETS_PATH, ListSerializer(AssetDto.serializer()))

    fun proceeds(filters: Map<String, String>): Flow<Load<List<ProceedDto>>> =
        reader.read(LancamentosRepository.PROCEEDS_PATH + query(filters), ListSerializer(ProceedDto.serializer()))

    fun proceedsSummary(filters: Map<String, String>): Flow<Load<ProceedsSummaryDto>> =
        reader.read("/api/investment-proceeds/summary" + query(filters), ProceedsSummaryDto.serializer())

    fun proceedsCalendar(filters: Map<String, String>): Flow<Load<List<ProceedDto>>> =
        reader.read("/api/investment-proceeds/calendar" + query(filters), ListSerializer(ProceedDto.serializer()))

    fun allocation(contribution: String): Flow<Load<AllocationDto>> =
        reader.read("/api/allocation" + query(mapOf("contribution" to contribution)), AllocationDto.serializer())

    fun sectors(assetClass: String): Flow<Load<SectorsDto>> =
        reader.read("/api/allocation/sectors" + query(mapOf("asset_class" to assetClass)), SectorsDto.serializer())

    fun taxReport(year: Int): Flow<Load<TaxReportDto>> = reader.read("/api/tax-report?year=$year", TaxReportDto.serializer())

    fun exemption(month: String): Flow<Load<ExemptionDto>> =
        reader.read("/api/tax-report/exemption?month=${enc(month)}", ExemptionDto.serializer())

    fun exportColumns(): Flow<Load<InvestmentExportColumnsDto>> =
        reader.read(LancamentosRepository.EXPORT_COLUMNS_PATH, InvestmentExportColumnsDto.serializer())

    /** O aviso de isencao da venda: so da rede (muda a cada tecla), sem copia guardada. */
    suspend fun saleExemption(month: String, plannedSale: String, ticker: String): InboxWrite<ExemptionDto> = get(
        "/api/tax-report/exemption" + query(mapOf("month" to month, "planned_sale" to plannedSale, "ticker" to ticker)),
        ExemptionDto.serializer(),
    )

    /** A busca no catalogo da B3 (dados de referencia), so da rede. */
    suspend fun searchTickers(text: String, assetClass: String, kind: String): InboxWrite<List<MarketTickerDto>> = get(
        "/api/market/tickers" + query(mapOf("q" to text, "asset_class" to assetClass, "kind" to kind, "limit" to "20")),
        ListSerializer(MarketTickerDto.serializer()),
    )

    /** O papel na lista da B3? Done(null) = 404 (nao esta). */
    suspend fun ticker(code: String): InboxWrite<MarketTickerDto?> =
        when (val result = get("/api/market/tickers/${enc(code)}", MarketTickerDto.serializer())) {
            is InboxWrite.Refused -> if (result.status == 404) InboxWrite.Done(null) else result
            else -> result
        }

    // ---- Escritas (online) ----

    suspend fun updatePrices(body: Map<String, Any?>): InboxWrite<QuoteUpdateDto> =
        decoded(send("POST", "/api/investments/update-prices", body), QuoteUpdateDto.serializer(), QuoteUpdateDto())

    suspend fun updatePriceByAsset(assetId: String, assetClass: String, price: java.math.BigDecimal): InboxWrite<Unit> =
        unit(send("PATCH", "/api/investments/price-by-asset/${enc(assetId)}", mapOf("asset_class" to assetClass, "current_price" to price)))

    suspend fun redeem(body: Map<String, Any?>): InboxWrite<Unit> = unit(send("POST", "/api/investments/redemptions", body))

    suspend fun deleteMovement(id: String): InboxWrite<Unit> = unit(send("DELETE", "/api/investments/${enc(id)}", null))

    suspend fun deleteByAsset(assetId: String, assetClass: String): InboxWrite<Unit> =
        unit(send("DELETE", "/api/investments/by-asset/${enc(assetId)}?asset_class=${enc(assetClass)}", null))

    suspend fun deleteByAssets(assetIds: List<String>, assetClass: String): InboxWrite<Unit> =
        unit(send("DELETE", "/api/investments/by-assets", mapOf("asset_ids" to assetIds, "asset_class" to assetClass)))

    suspend fun updateMovement(id: String, body: Map<String, Any?>): InboxWrite<Unit> =
        unit(send("PATCH", "/api/investments/${enc(id)}", body))

    suspend fun createCorporateAction(body: Map<String, Any?>): InboxWrite<CorporateActionDto?> =
        decoded(send("POST", CORPORATE_ACTIONS_PATH, body), CorporateActionDto.serializer(), null)

    suspend fun deleteCorporateAction(id: String): InboxWrite<Unit> = unit(send("DELETE", "$CORPORATE_ACTIONS_PATH/${enc(id)}", null))

    suspend fun updateProceed(id: String, body: Map<String, Any?>): InboxWrite<Unit> =
        unit(send("PATCH", "${LancamentosRepository.PROCEEDS_PATH}/${enc(id)}", body))

    suspend fun deleteProceed(id: String): InboxWrite<Unit> = unit(send("DELETE", "${LancamentosRepository.PROCEEDS_PATH}/${enc(id)}", null))

    /** A sincronizacao dos proventos automaticos; [force] passa por cima do cache de 6 h do servidor. */
    suspend fun syncProceeds(force: Boolean): InboxWrite<ProceedsSyncDto> = decoded(
        send("POST", LancamentosRepository.PROCEEDS_SYNC_PATH, if (force) mapOf("force" to true) else emptyMap()),
        ProceedsSyncDto.serializer(),
        ProceedsSyncDto(),
    )

    /** Exportar: a carteira, as operacoes ou os proventos ([path] com os filtros), no formato. */
    suspend fun export(path: String, params: Map<String, String>, format: String, columns: List<String>?): InboxWrite<Downloaded> {
        val all = LinkedHashMap(params)
        all["format"] = format
        if (!columns.isNullOrEmpty()) all["columns"] = columns.joinToString(",")
        return try {
            InboxWrite.Done(files.download(path + query(all)))
        } catch (error: ApiException) {
            failure(error)
        }
    }

    // ---- Comum ----

    private suspend fun <T> get(path: String, deserializer: DeserializationStrategy<T>): InboxWrite<T> = try {
        val body = fetcher.get(path)
        val value = try {
            json.decodeFromString(deserializer, body)
        } catch (error: SerializationException) {
            throw ApiException.BadResponse(error)
        } catch (error: IllegalArgumentException) {
            throw ApiException.BadResponse(error)
        }
        InboxWrite.Done(value)
    } catch (error: ApiException) {
        failure(error)
    }

    private fun failure(error: ApiException): InboxWrite<Nothing> = when (error) {
        is ApiException.Network, is ApiException.BadResponse -> InboxWrite.Offline
        is ApiException.Unauthorized -> InboxWrite.SessionExpired(error.serverMessage)
        is ApiException.Http -> when {
            error.status in 300..399 -> InboxWrite.Offline
            error.status == 409 -> InboxWrite.Conflict(error.serverMessage)
            else -> InboxWrite.Refused(error.status, error.serverMessage)
        }
    }

    private suspend fun send(method: String, path: String, body: Map<String, Any?>?): InboxWrite<String> =
        sendWrite(sender, method, path, body?.let { JsonBody.encode(it) })

    private fun unit(result: InboxWrite<String>): InboxWrite<Unit> = when (result) {
        is InboxWrite.Done -> InboxWrite.Done(Unit)
        is InboxWrite.Conflict -> result
        is InboxWrite.Refused -> result
        is InboxWrite.Offline -> result
        is InboxWrite.SessionExpired -> result
    }

    private fun <T> decoded(result: InboxWrite<String>, deserializer: DeserializationStrategy<T>, fallback: T): InboxWrite<T> = when (result) {
        is InboxWrite.Done -> InboxWrite.Done(
            try {
                json.decodeFromString(deserializer, result.value)
            } catch (error: SerializationException) {
                fallback
            } catch (error: IllegalArgumentException) {
                fallback
            },
        )
        is InboxWrite.Conflict -> result
        is InboxWrite.Refused -> result
        is InboxWrite.Offline -> result
        is InboxWrite.SessionExpired -> result
    }

    companion object {
        const val PORTFOLIO_PATH = "/api/investments/portfolio?refresh_prices=false"
        const val SETTLEMENT_PATH = "/api/investments/settlement"
        const val CORPORATE_ACTIONS_PATH = "/api/corporate-actions"
        const val ASSETS_PATH = "/api/assets"
        const val PORTFOLIO_EXPORT_PATH = "/api/investments/portfolio/export"
        const val MOVEMENTS_EXPORT_PATH = "/api/investments/export"
        const val PROCEEDS_EXPORT_PATH = "/api/investment-proceeds/export"

        fun query(params: Map<String, String>): String = LancamentosRepository.query(params)

        private fun enc(part: String) = LancamentosRepository.encode(part)
    }
}
