package br.financas.app.data

import kotlinx.coroutines.flow.Flow

/**
 * Ajustes sobre a API (pages/ajustes/): contas, cartoes, categorias, e o perfil (o "Sempre
 * perguntar" de Aprovar e o InboxRepository). As listas vem dos mesmos repositorios do "+ Novo" (AccountsRepository,
 * CardsRepository, CategoriesRepository); aqui so o que e de Ajustes e as escritas, todas so com
 * o servidor e sem prazo (writeApi), nunca na fila.
 */
class AjustesRepository(
    private val reader: CachedReader,
    private val sender: Sender,
) {
    fun me(): Flow<Load<MeDto>> = reader.read(ME_PATH, MeDto.serializer())

    suspend fun saveUsername(username: String): InboxWrite<Unit> = unit(send("PATCH", ME_PATH, mapOf("username" to username)))

    // ---- Contas ----

    suspend fun createAccount(body: Map<String, Any?>): InboxWrite<Unit> = unit(send("POST", ACCOUNTS_PATH, body))

    suspend fun updateAccount(id: String, body: Map<String, Any?>): InboxWrite<Unit> = unit(send("PATCH", "$ACCOUNTS_PATH/${enc(id)}", body))

    /** Arquiva (o servidor nunca apaga uma conta). */
    suspend fun archiveAccount(id: String): InboxWrite<Unit> = unit(send("DELETE", "$ACCOUNTS_PATH/${enc(id)}", null))

    // ---- Cartoes ----

    suspend fun createCard(body: Map<String, Any?>): InboxWrite<Unit> = unit(send("POST", CARDS_PATH, body))

    suspend fun updateCard(id: String, body: Map<String, Any?>): InboxWrite<Unit> = unit(send("PATCH", "$CARDS_PATH/${enc(id)}", body))

    /** Exclui um vazio, arquiva um com historico, recusa um com item em aberto (409). */
    suspend fun deleteCard(id: String): InboxWrite<Unit> = unit(send("DELETE", "$CARDS_PATH/${enc(id)}", null))

    // ---- Categorias ----

    suspend fun createCategory(body: Map<String, Any?>): InboxWrite<Unit> = unit(send("POST", CATEGORIES_PATH, body))

    suspend fun updateCategory(id: String, body: Map<String, Any?>): InboxWrite<Unit> =
        unit(send("PATCH", "$CATEGORIES_PATH/${enc(id)}", body))

    suspend fun archiveCategory(id: String): InboxWrite<Unit> = unit(send("DELETE", "$CATEGORIES_PATH/${enc(id)}", null))

    // ---- Open Finance (043): so ler e "Atualizar"; conectar e mapear ficam na web ----

    fun openFinance(): Flow<Load<OpenFinanceDto>> = reader.read(OPEN_FINANCE_PATH, OpenFinanceDto.serializer())

    fun openFinanceSettings(): Flow<Load<OpenFinanceSettingsDto>> =
        reader.read("$OPEN_FINANCE_PATH/settings", OpenFinanceSettingsDto.serializer())

    /** PATCH parcial (sync_hours, include_pending); a resposta e o conjunto inteiro. */
    suspend fun updateOpenFinanceSettings(body: Map<String, Any?>): InboxWrite<OpenFinanceSettingsDto> =
        when (val result = send("PATCH", "$OPEN_FINANCE_PATH/settings", body)) {
            is InboxWrite.Done -> try {
                InboxWrite.Done(ApiJson.decodeFromString(OpenFinanceSettingsDto.serializer(), result.value))
            } catch (_: Exception) {
                InboxWrite.Offline
            }
            is InboxWrite.Conflict -> result
            is InboxWrite.Refused -> result
            is InboxWrite.Offline -> result
            is InboxWrite.SessionExpired -> result
        }

    /** Pede dados novos ao banco (se a Pluggy deixa) e puxa para o Aprovar; a resposta e a lista nova. */
    suspend fun syncOpenFinance(itemId: String): InboxWrite<OpenFinanceDto> =
        when (val result = send("POST", "$OPEN_FINANCE_PATH/items/${enc(itemId)}/sync", emptyMap())) {
            is InboxWrite.Done -> try {
                InboxWrite.Done(ApiJson.decodeFromString(OpenFinanceDto.serializer(), result.value))
            } catch (_: Exception) {
                InboxWrite.Offline
            }
            is InboxWrite.Conflict -> result
            is InboxWrite.Refused -> result
            is InboxWrite.Offline -> result
            is InboxWrite.SessionExpired -> result
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

    companion object {
        const val ME_PATH = "/api/auth/me"
        const val ACCOUNTS_PATH = "/api/accounts"
        const val CARDS_PATH = "/api/credit-cards"
        const val CATEGORIES_PATH = "/api/categories"
        const val OPEN_FINANCE_PATH = "/api/open-finance"

        private fun enc(part: String) = LancamentosRepository.encode(part)
    }
}
