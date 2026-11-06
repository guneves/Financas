package br.financas.app.data

import android.content.Context
import br.financas.app.BuildConfig
import br.financas.app.notify.DetectionSender
import br.financas.app.outbox.LoginNotifier
import br.financas.app.outbox.Outbox
import br.financas.app.outbox.OutboxStore
import br.financas.app.outbox.Session
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
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

    init {
        // Um login guardado com o endereco antigo (443, so na VPN) passa para o do build (8443).
        Session.migrateBaseUrl(appContext, BuildConfig.API_BASE_URL)
    }

    private val _sessionExpired = MutableStateFlow(false)

    private val _deviceKeyNeeded = MutableStateFlow(false)

    /**
     * true depois de um 401 do proxy de autenticacao (outbox/DeviceKey.java): a casca pede a chave
     * de acesso remoto. O login fica. "Agora nao" cala o pedido ate a proxima chave salva.
     */
    val deviceKeyNeeded: StateFlow<Boolean> = _deviceKeyNeeded.asStateFlow()

    @Volatile
    private var keyPromptDismissed = false

    private fun handleProxyAuth() {
        if (!keyPromptDismissed) _deviceKeyNeeded.value = true
    }

    /** "Agora nao" no pedido da chave: nao pergunta de novo ate uma chave nova ser salva. */
    fun dismissDeviceKeyPrompt() {
        keyPromptDismissed = true
        _deviceKeyNeeded.value = false
    }

    /** A chave de acesso remoto guardada ("" sem chave). Bloqueia (Keystore): fora da tela. */
    fun deviceKey(): String = Session.deviceKey(appContext)

    /**
     * Guarda a chave de acesso remoto (vazia apaga) e, com login, manda ja o que a fila e as
     * deteccoes guardaram enquanto o proxy recusava. Bloqueia (Keystore): fora da tela.
     */
    fun saveDeviceKey(key: String) {
        Session.saveDeviceKey(appContext, key)
        keyPromptDismissed = false
        _deviceKeyNeeded.value = false
        if (Session.load(appContext) != null) {
            appScope.launch(Dispatchers.IO) {
                Outbox.flush(appContext, false)
                DetectionSender.run(appContext)
            }
        }
    }

    /**
     * true depois de um 401 (ou sem sessao): a casca (NativeActivity) volta para o login. Volta a
     * false no proximo pedido com sessao (o login novo).
     */
    val sessionExpired: StateFlow<Boolean> = _sessionExpired.asStateFlow()

    private fun currentSession(): SessionInfo? =
        Session.load(appContext)?.let { SessionInfo(it.baseUrl, it.token, it.userId) }

    // Um 401: apaga a sessao se ela ainda e a do pedido recusado e a casca volta ao login. Um
    // pedido antigo que volta depois de um login novo nao derruba nem avisa nada. Com itens
    // guardados, o mesmo aviso "Sessão expirada" do envio da fila (LoginNotifier).
    private fun handleUnauthorized(token: String?) {
        val stored = Session.load(appContext)
        if (token != null && stored != null && stored.token != token) return
        if (stored != null) Outbox.signOut(appContext)
        _sessionExpired.value = true
        val pending = OutboxStore.get(appContext).countPending()
        if (pending > 0) LoginNotifier.show(appContext, pending)
    }

    /** O login novo deu certo: as telas voltam a pedir. */
    fun signedIn() {
        _sessionExpired.value = false
    }

    /** O servidor deste APK (o do login guardado, senao o do build: BuildConfig.API_BASE_URL). */
    fun serverUrl(): String =
        Session.load(appContext)?.baseUrl?.takeIf { it.startsWith("https://") } ?: BuildConfig.API_BASE_URL

    /** O login nativo (POST /api/auth/login, sem token; com a chave de acesso remoto). */
    val auth = AuthRepository(deviceKey = ::deviceKey)

    val api: ApiClient = ApiClient(
        session = { currentSession().also { if (it != null) _sessionExpired.value = false } },
        onUnauthorized = ::handleUnauthorized,
        deviceKey = ::deviceKey,
        onProxyAuth = ::handleProxyAuth,
    )

    /** O POST de uma criacao do "+ Novo" (ui/newentry/): o mesmo cliente, com o prazo de 6 s. */
    val creationApi: ApiClient = ApiClient(
        session = { currentSession().also { if (it != null) _sessionExpired.value = false } },
        http = ApiClient.creationHttpClient(),
        onUnauthorized = ::handleUnauthorized,
        deviceKey = ::deviceKey,
        onProxyAuth = ::handleProxyAuth,
    )

    /** Escritas que nao sao criacao (Inicio: pagar fatura, lancar): sem prazo de resposta. */
    val writeApi: ApiClient = ApiClient(
        session = { currentSession().also { if (it != null) _sessionExpired.value = false } },
        http = ApiClient.writeHttpClient(),
        onUnauthorized = ::handleUnauthorized,
        deviceKey = ::deviceKey,
        onProxyAuth = ::handleProxyAuth,
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

    /**
     * Os avisos do celular (os ajustes e o que nao gravou sozinho): leituras com a copia guardada,
     * decisoes so com o servidor (nunca na fila), sem prazo.
     */
    val inbox = InboxRepository(reader, Sender { method, path, body -> writeApi.send(method, path, body) })

    /** Revisar e as compras no cartao do Extrato (045); confirmar so com o servidor, sem prazo. */
    val review = ReviewRepository(reader, Sender { method, path, body -> writeApi.send(method, path, body) })

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

    /** Ajustes: contas, cartoes, categorias, os avisos do celular e o perfil; escritas sem prazo. */
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
