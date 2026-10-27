package br.financas.app.ui.nav

import android.app.Application
import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.os.Handler
import android.os.Looper
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import br.financas.app.R
import br.financas.app.data.ApiException
import br.financas.app.data.AppGraph
import br.financas.app.data.Load
import br.financas.app.outbox.Outbox
import br.financas.app.outbox.OutboxEvents
import br.financas.app.outbox.OutboxStore
import br.financas.app.rules.ApkUpdateTexts
import br.financas.app.rules.PendingRow
import br.financas.app.rules.PendingRows
import br.financas.app.ui.ajustes.AjustesViewModel
import br.financas.app.update.ApkUpdater
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

/** Um aviso da casca (o toast da web): [tone] success | info | warning. */
data class ShellNotice(val message: String, val tone: String? = null, val long: Boolean = false)

/**
 * O estado da casca (00-shell.md): a fila do aparelho (a pilula e a folha Pendentes, com
 * Sincronizar, Corrigir e Descartar), "sem conexão" e o aviso do APK novo. A fila se rele ao
 * voltar para a frente, quando uma tela grava (ShellEvents) e quando o envio em segundo plano
 * manda ou recusa um item (OutboxEvents).
 */
class ShellViewModel(application: Application) : AndroidViewModel(application) {

    private val app: Application = application
    private val graph = AppGraph.from(application)
    private val main = Handler(Looper.getMainLooper())

    /** Os itens da fila do usuario da sessao, na ordem de envio. */
    var rows by mutableStateOf<List<PendingRow>>(emptyList())
        private set

    /** Gravados sozinhos esperando "é meu" (045): a pilula ambar e o numero da aba Extrato. */
    var reviewCount by mutableStateOf(0)
        private set

    /** Sem rede de verdade por baixo (a VPN nao conta): a pilula diz "Sem conexão". */
    var offline by mutableStateOf(false)
        private set

    var pendingOpen by mutableStateOf(false)
        private set

    var syncing by mutableStateOf(false)
        private set

    /** O aviso ambar dentro de Pendentes (recusado, servidor fora, login). */
    var syncWarning by mutableStateOf("")
        private set

    /** "Nova versão disponível (x)": null quando o instalado e o mais novo (ou sem resposta). */
    var apkPrompt by mutableStateOf<ApkUpdateTexts.Prompt?>(null)
        private set

    var apkStatus by mutableStateOf<ApkUpdateTexts.Message?>(null)
        private set

    var apkBusy by mutableStateOf(false)
        private set

    private var lastApkCheck = 0L
    private var installAfterPermission = false

    private val _notices = MutableSharedFlow<ShellNotice>(extraBufferCapacity = 8)
    val notices: SharedFlow<ShellNotice> = _notices.asSharedFlow()

    val attention: Boolean get() = offline || rows.any { it.refused }

    private val connectivity = app.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager

    private val networkCallback = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: Network) {
            main.post { readNetwork() }
        }

        override fun onLost(network: Network) {
            main.post { readNetwork() }
        }
    }

    init {
        // O envio do WorkManager mandou (ou o servidor recusou) com a tela aberta.
        OutboxEvents.setListener { main.post { refresh() } }
        try {
            connectivity?.registerDefaultNetworkCallback(networkCallback)
        } catch (error: RuntimeException) {
            // Sem o callback, a rede e lida ao voltar para a frente.
        }
    }

    override fun onCleared() {
        OutboxEvents.setListener(null)
        try {
            connectivity?.unregisterNetworkCallback(networkCallback)
        } catch (error: RuntimeException) {
        }
        super.onCleared()
    }

    private fun readNetwork() {
        offline = !Outbox.hasRealNetwork(app)
    }

    /** A fila e a rede de novo (ao voltar para a frente, depois de uma escrita). */
    fun refresh() {
        readNetwork()
        viewModelScope.launch {
            rows = withContext(Dispatchers.IO) {
                PendingRows.forUser(OutboxStore.get(app).all().map { it.toString() }, graph.sessionUserId())
            }
            if (rows.isEmpty()) syncWarning = ""
        }
        refreshReview()
    }

    /**
     * GET /api/review: quantos esperam a revisao (a leitura tambem grava o que esperava o prazo).
     * Sem rede fica o ultimo numero; um erro do servidor apaga a pilula.
     */
    fun refreshReview() {
        viewModelScope.launch {
            graph.review.queue().collect { load ->
                when (load) {
                    is Load.Cached -> if (reviewCount == 0) reviewCount = load.value.count
                    is Load.Fresh -> reviewCount = load.value.count
                    is Load.Failed ->
                        if (load.error !is ApiException.Network) reviewCount = 0
                }
            }
        }
    }

    fun notice(notice: ShellNotice) {
        _notices.tryEmit(notice)
    }

    fun openPending() {
        refresh()
        pendingOpen = true
    }

    fun closePending() {
        pendingOpen = false
    }

    fun dismissWarning() {
        syncWarning = ""
    }

    /** "Sincronizar agora": uma rodada ja, tentando tambem os recusados (como a web). */
    fun sync() {
        if (syncing) return
        syncing = true
        syncWarning = ""
        graph.appScope.launch {
            val summary = withContext(Dispatchers.IO) { Outbox.flush(app, true) }
            syncing = false
            syncWarning = PendingRows.syncWarning(summary.stopped, summary.attention).orEmpty()
            PendingRows.sentNotice(summary.sent)?.let { notice(ShellNotice(it)) }
            refresh()
        }
    }

    /** "Descartar" (depois da confirmacao): o item sai do aparelho e nunca chega ao servidor. */
    fun discard(row: PendingRow) {
        viewModelScope.launch {
            withContext(Dispatchers.IO) { OutboxStore.get(app).remove(row.clientId) }
            refresh()
        }
    }

    // ---- O APK novo ----

    /** Ao abrir e ao voltar para a frente, no maximo uma vez a cada [APK_CHECK_INTERVAL_MS]. */
    fun checkApk(force: Boolean = false) {
        val now = System.currentTimeMillis()
        if (installAfterPermission) {
            installAfterPermission = false
            installApk()
            return
        }
        if (!force && now - lastApkCheck < APK_CHECK_INTERVAL_MS) return
        if (graph.sessionUserId() == null) return
        lastApkCheck = now
        val base = graph.serverUrl().trimEnd('/')
        viewModelScope.launch {
            val state = withContext(Dispatchers.IO) {
                try {
                    AjustesViewModel.parseApk(ApkUpdater.latestState(app, base))
                } catch (error: Exception) {
                    null
                }
            }
            // Sem resposta (fora da tailnet): fica o que havia, sem aviso de erro.
            if (state != null) apkPrompt = ApkUpdateTexts.apkPrompt(state)
        }
    }

    /** "Instalar": a mesma vez de download de Ajustes › Versão do app (ApkUpdater). */
    fun installApk() {
        if (apkBusy) return
        val early: JSONObject? = ApkUpdater.installPrecheck(app)
        if (early != null) {
            val status = early.optString("status")
            installAfterPermission = status == "needs-permission"
            apkStatus = ApkUpdateTexts.installStatusMessage(status)
            return
        }
        apkBusy = true
        val base = graph.serverUrl().trimEnd('/')
        graph.appScope.launch {
            val (status, message) = withContext(Dispatchers.IO) {
                try {
                    ApkUpdater.installNow(app, base).optString("status") to null
                } catch (error: Exception) {
                    "error" to ApkUpdater.failureMessage(error, app.getString(R.string.ajustes_apk_install_failed))
                }
            }
            apkBusy = false
            apkStatus = ApkUpdateTexts.installStatusMessage(status, message)
        }
    }

    companion object {
        const val APK_CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000L
    }
}
