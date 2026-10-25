package br.financas.app.data

import android.content.Context
import br.financas.app.outbox.LoginNotifier
import br.financas.app.outbox.OutboxStore
import br.financas.app.outbox.Session
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.io.File

/**
 * Monta, uma vez por processo, o cliente, o cache e os repositorios das telas nativas
 * (sem framework de injecao: architecture.md). Uso: AppGraph.from(context).accounts.
 */
class AppGraph private constructor(context: Context) {

    private val appContext: Context = context.applicationContext

    private val _sessionExpired = MutableStateFlow(false)

    /**
     * true depois de um 401 (ou sem sessao): a tela para, diz "Sessão expirada" e manda entrar
     * de novo pela WebView, que ainda e dona do login. Volta a false no proximo pedido que passa.
     */
    val sessionExpired: StateFlow<Boolean> = _sessionExpired.asStateFlow()

    private fun currentSession(): SessionInfo? =
        Session.load(appContext)?.let { SessionInfo(it.baseUrl, it.token, it.userId) }

    // O mesmo tratamento do envio da fila (OutboxWorker): com itens guardados, o aviso
    // "Sessão expirada" do LoginNotifier, que abre o app no login.
    private fun handleUnauthorized() {
        _sessionExpired.value = true
        val pending = OutboxStore.get(appContext).countPending()
        if (pending > 0) LoginNotifier.show(appContext, pending)
    }

    val api: ApiClient = ApiClient(
        session = { currentSession().also { if (it != null) _sessionExpired.value = false } },
        onUnauthorized = ::handleUnauthorized,
    )

    /** O POST de uma criacao do "+ Novo" (ui/newentry/): o mesmo cliente, com o prazo de 6 s. */
    val creationApi: ApiClient = ApiClient(
        session = { currentSession().also { if (it != null) _sessionExpired.value = false } },
        http = ApiClient.creationHttpClient(),
        onUnauthorized = ::handleUnauthorized,
    )

    /** Escritas que nao sao criacao (Inicio: pagar fatura, lancar): sem prazo de resposta. */
    val writeApi: ApiClient = ApiClient(
        session = { currentSession().also { if (it != null) _sessionExpired.value = false } },
        http = ApiClient.writeHttpClient(),
        onUnauthorized = ::handleUnauthorized,
    )

    /**
     * Trabalho que nao pode morrer com a tela: um Salvar ja comecado termina (e avisa) mesmo que o
     * dono feche o sheet ou a Activity acabe. Vive o processo inteiro; roda na thread da tela.
     */
    val appScope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    /** O usuario da sessao (o user_id de um item da fila), ou null sem login. */
    fun sessionUserId(): String? = Session.load(appContext)?.userId

    val cache: ReadCache = FileReadCache(File(appContext.filesDir, CACHE_DIR))

    private val reader = CachedReader(
        fetcher = api,
        cache = cache,
        userId = { currentSession()?.userId },
    )

    val accounts = AccountsRepository(reader)
    val categories = CategoriesRepository(reader)
    val cards = CardsRepository(reader)

    /** Aprovar: leituras com a copia guardada, decisoes so com o servidor (nunca na fila), sem prazo. */
    val inbox = InboxRepository(reader, Sender { method, path, body -> writeApi.send(method, path, body) })

    /** Inicio: o saldo, o mes, os avisos e o orcamento; pagar fatura e lancar recorrencias. */
    val home = HomeRepository(reader, Sender { method, path, body -> writeApi.send(method, path, body) })

    /** Extrato e Cartoes: as leituras com a copia guardada, as escritas sem prazo (writeApi). */
    val lancamentos = LancamentosRepository(
        reader = reader,
        fetcher = api,
        sender = Sender { method, path, body -> writeApi.send(method, path, body) },
        files = writeApi,
    )

    /** Planejar (Orcamento, Recorrentes, Metas) e A receber: leituras com a copia, escritas sem prazo. */
    val planejamento = PlanejamentoRepository(
        reader = reader,
        sender = Sender { method, path, body -> writeApi.send(method, path, body) },
    )

    /** Investimentos: leituras com a copia, escritas sem prazo; a operacao e o provento novos vao pela fila. */
    val investimentos = InvestimentosRepository(
        reader = reader,
        fetcher = api,
        sender = Sender { method, path, body -> writeApi.send(method, path, body) },
        files = writeApi,
    )

    /** Ajustes: contas, cartoes, categorias, Aprovar e o perfil; escritas sem prazo. */
    val ajustes = AjustesRepository(
        reader = reader,
        sender = Sender { method, path, body -> writeApi.send(method, path, body) },
    )

    companion object {
        /** files/native-read-cache: a ultima resposta boa de cada leitura. */
        const val CACHE_DIR = "native-read-cache"

        @Volatile
        private var instance: AppGraph? = null

        @JvmStatic
        fun from(context: Context): AppGraph =
            instance ?: synchronized(this) {
                instance ?: AppGraph(context).also { instance = it }
            }
    }
}
