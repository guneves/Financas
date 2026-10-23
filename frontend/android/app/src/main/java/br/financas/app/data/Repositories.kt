package br.financas.app.data

import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.serialization.DeserializationStrategy
import kotlinx.serialization.SerializationException
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json

/**
 * Uma leitura vista pela tela. Primeiro a copia guardada (se houver), depois a nova; se a nova
 * falhar, o erro leva a copia junto, para a tela seguir mostrando o que tinha.
 */
sealed interface Load<out T> {
    /** A copia guardada; [storedAt] da o "atualizado às HH:MM". */
    data class Cached<T>(val value: T, val storedAt: Long) : Load<T>

    /** A resposta que acabou de chegar (ja guardada). */
    data class Fresh<T>(val value: T, val storedAt: Long) : Load<T>

    /** A leitura falhou; [cached] e a copia guardada, ou null se nao ha nenhuma. */
    data class Failed<T>(val error: ApiException, val cached: Cached<T>?) : Load<T>
}

/**
 * Cache primeiro, rede depois (o mesmo que o cache persistido do TanStack faz na web): emite
 * [Load.Cached] na hora, busca, guarda e emite [Load.Fresh]; numa falha, [Load.Failed] com a
 * copia. Uma resposta que nao e o JSON esperado nunca substitui a copia boa.
 *
 * A chave do cache leva o usuario da sessao: outro login nunca ve as contas do anterior.
 */
class CachedReader(
    private val fetcher: Fetcher,
    private val cache: ReadCache,
    private val userId: () -> String?,
    private val json: Json = ApiJson,
    private val io: CoroutineDispatcher = Dispatchers.IO,
) {

    fun <T> read(path: String, deserializer: DeserializationStrategy<T>): Flow<Load<T>> = flow {
        val user = userId()
        val key = user?.let { "$it $path" }
        val cached = key?.let { cache.get(it) }?.let { entry ->
            decodeOrNull(entry.body, deserializer)?.let { Load.Cached(it, entry.storedAt) }
        }
        if (cached != null) emit(cached)

        val outcome: Load<T> = try {
            val body = fetcher.get(path)
            val value = try {
                json.decodeFromString(deserializer, body)
            } catch (error: SerializationException) {
                throw ApiException.BadResponse(error)
            } catch (error: IllegalArgumentException) {
                throw ApiException.BadResponse(error)
            }
            val stored = if (key != null) cache.put(key, body).storedAt else System.currentTimeMillis()
            Load.Fresh(value, stored)
        } catch (error: ApiException) {
            Load.Failed(error, cached)
        }
        emit(outcome)
    }.flowOn(io)

    private fun <T> decodeOrNull(body: String, deserializer: DeserializationStrategy<T>): T? =
        try {
            json.decodeFromString(deserializer, body)
        } catch (error: SerializationException) {
            null
        } catch (error: IllegalArgumentException) {
            null
        }
}

/** As contas. A web pede as ativas (+ Novo, Aprovar) e, onde o saldo conta, tambem as arquivadas. */
class AccountsRepository(private val reader: CachedReader) {
    fun accounts(includeArchived: Boolean = false): Flow<Load<List<AccountDto>>> =
        reader.read(accountsPath(includeArchived), ListSerializer(AccountDto.serializer()))

    companion object {
        /** O mesmo endereco da web: accountsApi.list() e accountsApi.list({ include_archived: 1 }). */
        fun accountsPath(includeArchived: Boolean): String =
            if (includeArchived) "/api/accounts?include_archived=1" else "/api/accounts"
    }
}

/** As categorias, na ordem do servidor. */
class CategoriesRepository(private val reader: CachedReader) {
    fun categories(includeArchived: Boolean = false): Flow<Load<List<CategoryDto>>> =
        reader.read(categoriesPath(includeArchived), ListSerializer(CategoryDto.serializer()))

    companion object {
        fun categoriesPath(includeArchived: Boolean): String =
            if (includeArchived) "/api/categories?include_archived=1" else "/api/categories"
    }
}

/** Os cartoes ativos (creditCardsApi.list(): nenhuma tela lanca num arquivado). */
class CardsRepository(private val reader: CachedReader) {
    fun cards(): Flow<Load<List<CreditCardDto>>> =
        reader.read(CARDS_PATH, ListSerializer(CreditCardDto.serializer()))

    companion object {
        const val CARDS_PATH = "/api/credit-cards"
    }
}
