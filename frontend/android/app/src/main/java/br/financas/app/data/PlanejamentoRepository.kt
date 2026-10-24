package br.financas.app.data

import kotlinx.coroutines.flow.Flow
import kotlinx.serialization.DeserializationStrategy
import kotlinx.serialization.SerializationException
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json

/**
 * Planejar (Orcamento, Recorrentes, Metas) e A receber sobre a API, os mesmos pedidos da web: as
 * leituras com a copia guardada primeiro (CachedReader), as escritas so com o servidor e sem
 * prazo (writeApi). Nada aqui vai para a fila: plano, orcamento, recorrencia, meta e "Pago" sao
 * recusados sem conexao ("Sem conexão com o servidor...").
 */
class PlanejamentoRepository(
    private val reader: CachedReader,
    private val sender: Sender,
    private val json: Json = ApiJson,
) {
    // ---- Orcamento ----

    fun monthlyPlan(month: String): Flow<Load<MonthlyPlanDto>> = reader.read(monthlyPlanPath(month), MonthlyPlanDto.serializer())

    /** As linhas de uma categoria: a copia guardada vale offline (como o cache da web). */
    fun budgetLines(budgetId: String, month: String): Flow<Load<BudgetLinesDto>> =
        reader.read("/api/budgets/${enc(budgetId)}/lines?month=${enc(month)}", BudgetLinesDto.serializer())

    suspend fun savePlan(body: Map<String, Any?>): InboxWrite<Unit> = unit(send("PUT", MONTHLY_PLAN_PATH, body))

    suspend fun removePlan(month: String): InboxWrite<Unit> = unit(send("DELETE", monthlyPlanPath(month), null))

    suspend fun createBudget(body: Map<String, Any?>): InboxWrite<Unit> = unit(send("POST", BUDGETS_PATH, body))

    /** `?month=` e sempre o mes mostrado: num mes herdado o servidor materializa antes de mudar. */
    suspend fun updateBudget(id: String, month: String, body: Map<String, Any?>): InboxWrite<Unit> =
        unit(send("PATCH", budgetPath(id, month), body))

    suspend fun deleteBudget(id: String, month: String): InboxWrite<Unit> = unit(send("DELETE", budgetPath(id, month), null))

    suspend fun copyBudgets(toMonth: String): InboxWrite<BudgetCopyDto> =
        decoded(send("POST", "$BUDGETS_PATH/copy", mapOf("to_month" to toMonth)), BudgetCopyDto.serializer(), BudgetCopyDto())

    // ---- Recorrentes ----

    fun recurring(): Flow<Load<RecurringListDto>> = reader.read(RECURRING_PATH, RecurringListDto.serializer())

    fun forecast(): Flow<Load<RecurringForecastDto>> = reader.read(FORECAST_PATH, RecurringForecastDto.serializer())

    suspend fun runRecurring(): InboxWrite<RecurringRunDto> =
        decoded(send("POST", "$RECURRING_PATH/run", emptyMap()), RecurringRunDto.serializer(), RecurringRunDto())

    suspend fun createRecurring(body: Map<String, Any?>): InboxWrite<Unit> = unit(send("POST", RECURRING_PATH, body))

    suspend fun updateRecurring(id: String, body: Map<String, Any?>): InboxWrite<Unit> =
        unit(send("PATCH", "$RECURRING_PATH/${enc(id)}", body))

    suspend fun deleteRecurring(id: String): InboxWrite<RecurringDeletedDto> =
        decoded(send("DELETE", "$RECURRING_PATH/${enc(id)}", null), RecurringDeletedDto.serializer(), RecurringDeletedDto())

    // ---- Metas ----

    fun goals(): Flow<Load<List<GoalDto>>> = reader.read(GOALS_PATH, ListSerializer(GoalDto.serializer()))

    suspend fun createGoal(body: Map<String, Any?>): InboxWrite<Unit> = unit(send("POST", GOALS_PATH, body))

    suspend fun updateGoal(id: String, body: Map<String, Any?>): InboxWrite<Unit> = unit(send("PATCH", "$GOALS_PATH/${enc(id)}", body))

    suspend fun deleteGoal(id: String): InboxWrite<Unit> = unit(send("DELETE", "$GOALS_PATH/${enc(id)}", null))

    // ---- A receber ----

    fun receivables(includeSettled: Boolean): Flow<Load<List<ReceivableDto>>> =
        reader.read(receivablesPath(includeSettled), ListSerializer(ReceivableDto.serializer()))

    suspend fun settle(body: Map<String, Any?>): InboxWrite<Unit> = unit(send("POST", "/api/receivables/settle", body))

    // ---- Comum ----

    private suspend fun send(method: String, path: String, body: Map<String, Any?>?): InboxWrite<String> =
        sendWrite(sender, method, path, body?.let { JsonBody.encode(it) })

    private fun unit(result: InboxWrite<String>): InboxWrite<Unit> = when (result) {
        is InboxWrite.Done -> InboxWrite.Done(Unit)
        is InboxWrite.Conflict -> result
        is InboxWrite.Refused -> result
        is InboxWrite.Offline -> result
        is InboxWrite.SessionExpired -> result
    }

    // A escrita valeu mesmo que a resposta nao seja a esperada: [fallback] no lugar dela.
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
        const val MONTHLY_PLAN_PATH = "/api/monthly-plan"
        const val BUDGETS_PATH = "/api/budgets"
        const val RECURRING_PATH = "/api/recurring"
        const val FORECAST_PATH = "/api/recurring/forecast?days=90"
        const val GOALS_PATH = "/api/goals"

        fun monthlyPlanPath(month: String) = "$MONTHLY_PLAN_PATH?month=${enc(month)}"

        fun budgetPath(id: String, month: String) = "$BUDGETS_PATH/${enc(id)}?month=${enc(month)}"

        fun receivablesPath(includeSettled: Boolean) =
            if (includeSettled) "/api/receivables?include_settled=1" else "/api/receivables"

        private fun enc(part: String) = LancamentosRepository.encode(part)
    }
}
