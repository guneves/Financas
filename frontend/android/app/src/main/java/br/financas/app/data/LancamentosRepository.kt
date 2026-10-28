package br.financas.app.data

import kotlinx.coroutines.flow.Flow
import kotlinx.serialization.DeserializationStrategy
import kotlinx.serialization.SerializationException
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

/**
 * Extrato e Cartoes sobre a API, os mesmos pedidos da web (pages/lancamentos/): as leituras com a
 * copia guardada primeiro (CachedReader), as escritas so com o servidor e sem prazo de resposta
 * (writeApi: uma edicao, exclusao ou pagamento nunca vai para a fila nem e repetido).
 */
class LancamentosRepository(
    private val reader: CachedReader,
    private val fetcher: Fetcher,
    private val sender: Sender,
    private val files: FileApi,
    private val json: Json = ApiJson,
) {
    // ---- Leituras ----

    /** A primeira pagina do extrato com estes filtros, com a copia guardada dela. */
    fun firstPage(filters: Map<String, String>): Flow<Load<TransactionPageDto>> =
        reader.read(pagePath(filters, null), TransactionPageDto.serializer())

    /** As paginas seguintes: so a rede (rolar sem conexao para no fim do que ja veio). */
    suspend fun nextPage(filters: Map<String, String>, cursor: String): TransactionPageDto =
        decodeOrBad(fetcher.get(pagePath(filters, cursor)), TransactionPageDto.serializer())

    fun ccInvoices(): Flow<Load<CcInvoicesDto>> = reader.read(CC_INVOICES_PATH, CcInvoicesDto.serializer())

    fun investments(): Flow<Load<List<InvestmentMovementDto>>> =
        reader.read(INVESTMENTS_PATH, ListSerializer(InvestmentMovementDto.serializer()))

    fun proceeds(): Flow<Load<List<InvestmentProceedDto>>> =
        reader.read(PROCEEDS_PATH, ListSerializer(InvestmentProceedDto.serializer()))

    fun exportColumns(): Flow<Load<ExportColumnsDto>> = reader.read(EXPORT_COLUMNS_PATH, ExportColumnsDto.serializer())

    /** As parcelas de uma compra (todas, pagas inclusive), so da rede. */
    suspend fun candidates(purchaseId: String): InboxWrite<List<PurchaseInstallmentDto>> = try {
        InboxWrite.Done(decodeOrBad(fetcher.get(candidatesPath(purchaseId)), ListSerializer(PurchaseInstallmentDto.serializer())))
    } catch (error: ApiException) {
        failure(error)
    }

    suspend fun attachments(owner: AttachmentOwner): InboxWrite<List<AttachmentDto>> = try {
        InboxWrite.Done(decodeOrBad(fetcher.get(owner.listPath), ListSerializer(AttachmentDto.serializer())))
    } catch (error: ApiException) {
        failure(error)
    }

    // ---- Escritas do Extrato ----

    suspend fun updateTransaction(id: String, body: Map<String, Any?>): InboxWrite<Unit> =
        unit(sendWrite(sender, "PATCH", "/api/transactions/${encode(id)}", JsonBody.encode(body)))

    suspend fun deleteTransaction(id: String): InboxWrite<Unit> =
        unit(sendWrite(sender, "DELETE", "/api/transactions/${encode(id)}", null))

    /** "Desfazer pagamento": reabre a fatura (DELETE /api/cc-expenses/payments/<lancamento>). */
    suspend fun undoPayment(transactionId: String): InboxWrite<Unit> =
        unit(sendWrite(sender, "DELETE", "/api/cc-expenses/payments/${encode(transactionId)}", null))

    /** Exclui a operacao (e o lancamento de caixa dela). */
    suspend fun deleteInvestment(movementId: String): InboxWrite<Unit> =
        unit(sendWrite(sender, "DELETE", "/api/investments/${encode(movementId)}", null))

    /** O mesmo do useProceedsSync() da web ao abrir o extrato de investimentos; falha calada. */
    suspend fun syncProceeds(): InboxWrite<Unit> = unit(sendWrite(sender, "POST", PROCEEDS_SYNC_PATH, "{}"))

    // ---- Escritas de Cartoes ----

    suspend fun payInvoice(cardId: String, invoiceMonth: Int, invoiceYear: Int, accountId: String?): InboxWrite<Unit> =
        unit(
            sendWrite(
                sender, "POST", HomeRepository.PAY_INVOICE_PATH,
                JsonBody.encode(HomeRepository.payInvoiceBody(cardId, invoiceMonth, invoiceYear, accountId)),
            ),
        )

    suspend fun createRefund(body: Map<String, Any?>): InboxWrite<RefundCreatedDto> =
        when (val result = sendWrite(sender, "POST", REFUNDS_PATH, JsonBody.encode(body))) {
            is InboxWrite.Done -> InboxWrite.Done(decodeOrNull(result.value, RefundCreatedDto.serializer()) ?: RefundCreatedDto())
            is InboxWrite.Conflict -> result
            is InboxWrite.Refused -> result
            is InboxWrite.Offline -> result
            is InboxWrite.SessionExpired -> result
        }

    /** POST /api/transfers sem a fila: o Pix para a conta global leva dois valores (047). */
    suspend fun createTransfer(body: Map<String, Any?>): InboxWrite<Unit> =
        unit(sendWrite(sender, "POST", TRANSFERS_PATH, JsonBody.encode(body)))

    /** Categoria e descricao da compra (ou estorno): todas as parcelas, pagas inclusive. */
    suspend fun updatePurchase(purchaseId: String, body: Map<String, Any?>): InboxWrite<Unit> =
        unit(sendWrite(sender, "PATCH", "/api/cc-expenses/purchases/${encode(purchaseId)}", JsonBody.encode(body)))

    suspend fun updateShare(purchaseId: String, body: Map<String, Any?>): InboxWrite<Unit> =
        unit(sendWrite(sender, "PATCH", "/api/cc-expenses/${encode(purchaseId)}/share", JsonBody.encode(body)))

    /** As parcelas em aberto da compra (ou o estorno) saem; as pagas ficam (o servidor decide). */
    suspend fun deletePurchase(purchaseId: String): InboxWrite<Unit> =
        unit(sendWrite(sender, "DELETE", "/api/cc-expenses/purchases/${encode(purchaseId)}", null))

    // ---- Comprovantes e exportacao ----

    suspend fun uploadAttachment(owner: AttachmentOwner, fileName: String, mimeType: String, bytes: ByteArray): InboxWrite<Unit> =
        try {
            files.upload(owner.listPath, "file", fileName, mimeType, bytes)
            InboxWrite.Done(Unit)
        } catch (error: ApiException) {
            failure(error)
        }

    suspend fun deleteAttachment(owner: AttachmentOwner, attachmentId: String): InboxWrite<Unit> =
        unit(sendWrite(sender, "DELETE", owner.filePath(attachmentId).removeSuffix("/file"), null))

    suspend fun attachmentFile(owner: AttachmentOwner, attachmentId: String): InboxWrite<Downloaded> =
        download(owner.filePath(attachmentId))

    /** GET /api/transactions/export com os filtros da tela, o formato e as colunas. */
    suspend fun export(filters: Map<String, String>, format: String, columns: List<String>?): InboxWrite<Downloaded> {
        val params = LinkedHashMap(filters)
        params["format"] = format
        if (!columns.isNullOrEmpty()) params["columns"] = columns.joinToString(",")
        return download(EXPORT_PATH + query(params))
    }

    private suspend fun download(path: String): InboxWrite<Downloaded> = try {
        InboxWrite.Done(files.download(path))
    } catch (error: ApiException) {
        failure(error)
    }

    private fun <T> failure(error: ApiException): InboxWrite<T> = when (error) {
        is ApiException.Network, is ApiException.BadResponse -> InboxWrite.Offline
        is ApiException.Unauthorized -> InboxWrite.SessionExpired(error.serverMessage)
        is ApiException.Http -> when {
            error.status in 300..399 -> InboxWrite.Offline
            error.status == 409 -> InboxWrite.Conflict(error.serverMessage)
            else -> InboxWrite.Refused(error.status, error.serverMessage)
        }
    }

    private fun unit(result: InboxWrite<String>): InboxWrite<Unit> = when (result) {
        is InboxWrite.Done -> InboxWrite.Done(Unit)
        is InboxWrite.Conflict -> result
        is InboxWrite.Refused -> result
        is InboxWrite.Offline -> result
        is InboxWrite.SessionExpired -> result
    }

    private fun <T> decodeOrNull(body: String, deserializer: DeserializationStrategy<T>): T? = try {
        json.decodeFromString(deserializer, body)
    } catch (error: SerializationException) {
        null
    } catch (error: IllegalArgumentException) {
        null
    }

    private fun <T> decodeOrBad(body: String, deserializer: DeserializationStrategy<T>): T =
        decodeOrNull(body, deserializer) ?: throw ApiException.BadResponse(null)

    companion object {
        /** O tamanho da pagina do extrato (o STATEMENT_PAGE_LIMIT da web). */
        const val PAGE_LIMIT = 200
        const val CC_INVOICES_PATH = "/api/cc-invoices"
        const val INVESTMENTS_PATH = "/api/investments?order=created_at&ascending=false"
        const val PROCEEDS_PATH = "/api/investment-proceeds"
        const val PROCEEDS_SYNC_PATH = "/api/investment-proceeds/sync"
        const val EXPORT_COLUMNS_PATH = "/api/exports/columns"
        const val EXPORT_PATH = "/api/transactions/export"
        const val REFUNDS_PATH = "/api/cc-expenses/refunds"
        const val TRANSFERS_PATH = "/api/transfers"

        /** Os filtros com valor, na ordem dada, mais limit e cursor: o queryString() da web. */
        fun pagePath(filters: Map<String, String>, cursor: String?): String {
            val params = LinkedHashMap<String, String>()
            filters.forEach { (key, value) -> if (value.isNotBlank()) params[key] = value }
            params["limit"] = PAGE_LIMIT.toString()
            if (!cursor.isNullOrEmpty()) params["cursor"] = cursor
            return "/api/transactions" + query(params)
        }

        fun candidatesPath(id: String): String = "/api/cc-expenses/candidates?id=${encode(id)}"

        fun query(params: Map<String, String>): String {
            val parts = params.filter { it.value.isNotEmpty() }.map { (key, value) -> "${encode(key)}=${encode(value)}" }
            return if (parts.isEmpty()) "" else "?" + parts.joinToString("&")
        }

        // O URLSearchParams da web escreve espaco como "+"; o servidor le os dois.
        fun encode(part: String): String = URLEncoder.encode(part, StandardCharsets.UTF_8.name())
    }
}

/** Quem tem os comprovantes: um lancamento ou uma compra no cartao (as rotas sao aninhadas). */
data class AttachmentOwner(val base: String, val id: String) {
    val listPath: String get() = "$base/${LancamentosRepository.encode(id)}/attachments"

    fun filePath(attachmentId: String): String = "$listPath/${LancamentosRepository.encode(attachmentId)}/file"

    companion object {
        fun transaction(id: String) = AttachmentOwner("/api/transactions", id)
        fun purchase(id: String) = AttachmentOwner("/api/cc-expenses", id)
    }
}

/** Upload e download (o ApiClient no app; um falso nos testes). */
interface FileApi {
    suspend fun upload(path: String, field: String, fileName: String, mimeType: String, bytes: ByteArray): String
    suspend fun download(path: String): Downloaded
}
