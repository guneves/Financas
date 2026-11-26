package br.financas.app.data

import kotlinx.coroutines.flow.Flow
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/**
 * O Inicio sobre a API, os mesmos pedidos da web (pages/Dashboard.jsx, lib/attention.js):
 * GET /api/home?months=12, GET /api/home/panels, GET /api/attention, GET /api/budgets?month=, com a copia guardada
 * primeiro (CachedReader); e as duas acoes, so com o servidor (nunca na fila): pagar uma fatura
 * (POST /api/cc-expenses/pay-invoice, uma por pedido) e lancar as recorrencias
 * (POST /api/recurring/run); e o puxar para atualizar pede ao servidor o que a Pluggy ja trouxe
 * (POST /api/open-finance/refresh).
 */
class HomeRepository(
    private val reader: CachedReader,
    private val sender: Sender,
    private val json: Json = ApiJson,
) {
    fun home(): Flow<Load<HomeDto>> = reader.read(HOME_PATH, HomeDto.serializer())

    /** Categorias, ritmo, proximas faturas e parcelamentos (GET /api/home/panels). */
    fun panels(): Flow<Load<HomePanelsDto>> = reader.read(PANELS_PATH, HomePanelsDto.serializer())

    fun attention(): Flow<Load<AttentionDto>> = reader.read(ATTENTION_PATH, AttentionDto.serializer())

    fun budget(month: String): Flow<Load<BudgetMonthDto>> = reader.read(budgetPath(month), BudgetMonthDto.serializer())

    /** Uma fatura; sem [accountId] o servidor usa a conta do debito automatico, senao a padrao. */
    suspend fun payInvoice(cardId: String, invoiceMonth: Int, invoiceYear: Int, accountId: String?): InboxWrite<Unit> =
        when (val result = sendWrite(sender, "POST", PAY_INVOICE_PATH, JsonBody.encode(payInvoiceBody(cardId, invoiceMonth, invoiceYear, accountId)))) {
            is InboxWrite.Done -> InboxWrite.Done(Unit)
            is InboxWrite.Conflict -> result
            is InboxWrite.Refused -> result
            is InboxWrite.Offline -> result
            is InboxWrite.SessionExpired -> result
        }

    /** "Lançar": o mesmo POST de Recorrentes, com {} (idempotente). */
    suspend fun runRecurring(): InboxWrite<RecurringRunDto> =
        when (val result = sendWrite(sender, "POST", RUN_RECURRING_PATH, "{}")) {
            is InboxWrite.Done -> decode(result.value)?.let { InboxWrite.Done(it) } ?: InboxWrite.Offline
            is InboxWrite.Conflict -> result
            is InboxWrite.Refused -> result
            is InboxWrite.Offline -> result
            is InboxWrite.SessionExpired -> result
        }

    /**
     * Puxar para atualizar: o servidor le (GET) a Pluggy e puxa ja a conexao que ela atualizou,
     * sem esperar o passo de 5 min. Devolve quantas conexoes trouxeram algo (0 sem nada novo).
     */
    suspend fun refreshBanks(): InboxWrite<Int> =
        when (val result = sendWrite(sender, "POST", REFRESH_BANKS_PATH, "{}")) {
            is InboxWrite.Done -> InboxWrite.Done(pulledOf(result.value))
            is InboxWrite.Conflict -> result
            is InboxWrite.Refused -> result
            is InboxWrite.Offline -> result
            is InboxWrite.SessionExpired -> result
        }

    private fun decode(body: String): RecurringRunDto? = try {
        json.decodeFromString(RecurringRunDto.serializer(), body)
    } catch (error: SerializationException) {
        null
    } catch (error: IllegalArgumentException) {
        null
    }

    companion object {
        /** Os 12 meses do fluxo, como useHome() (HOME_MONTHS em lib/attention.js). */
        const val HOME_MONTHS = 12
        const val HOME_PATH = "/api/home?months=$HOME_MONTHS"
        const val PANELS_PATH = "/api/home/panels"
        const val ATTENTION_PATH = "/api/attention"
        const val PAY_INVOICE_PATH = "/api/cc-expenses/pay-invoice"
        const val RUN_RECURRING_PATH = "/api/recurring/run"
        const val REFRESH_BANKS_PATH = "/api/open-finance/refresh"

        /** O `pulled` da resposta de [REFRESH_BANKS_PATH]; 0 num corpo que nao e o esperado. */
        fun pulledOf(body: String): Int = try {
            ApiJson.parseToJsonElement(body).jsonObject["pulled"]?.jsonPrimitive?.intOrNull ?: 0
        } catch (error: SerializationException) {
            0
        } catch (error: IllegalArgumentException) {
            0
        }

        fun budgetPath(month: String): String = "/api/budgets?month=$month"

        /**
         * O corpo que a web manda: { card_id, invoice_month, invoice_year, account_id? } — sem
         * conta escolhida a chave nao vai (o JSON.stringify do JS deixa o undefined de fora).
         */
        fun payInvoiceBody(cardId: String, invoiceMonth: Int, invoiceYear: Int, accountId: String?): Map<String, Any?> {
            val body = linkedMapOf<String, Any?>(
                "card_id" to cardId,
                "invoice_month" to invoiceMonth,
                "invoice_year" to invoiceYear,
            )
            if (!accountId.isNullOrEmpty()) body["account_id"] = accountId
            return body
        }
    }
}
