package br.financas.app.ui.planejar

import android.app.Application
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Snackbar
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import br.financas.app.R
import br.financas.app.data.ApiException
import br.financas.app.data.InboxWrite
import br.financas.app.data.Load
import br.financas.app.data.storedTimeLabel
import br.financas.app.rules.BudgetStatus
import br.financas.app.ui.components.FitText
import br.financas.app.ui.components.NativeTopBar
import br.financas.app.ui.components.Panel
import br.financas.app.ui.components.TopTab
import br.financas.app.ui.theme.LocalPalette
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.SharedFlow
import java.math.BigDecimal

/** As abas de Planejar (lib/navigation.js): Orcamento, Recorrentes, Metas. */
enum class PlanejarTab { ORCAMENTO, RECORRENTES, METAS }

/** O topo de Orcamento, Recorrentes e Metas: voltar, titulo, o olho e as tres abas. */
@Composable
fun PlanejarTopBar(title: String, current: PlanejarTab, hidden: Boolean, onBack: () -> Unit, onToggleHidden: () -> Unit, onTab: (PlanejarTab) -> Unit) {
    NativeTopBar(
        title = title,
        hidden = hidden,
        onBack = onBack,
        onToggleHidden = onToggleHidden,
        tabs = listOf(
            TopTab(stringResource(R.string.plan_tab_orcamento), current == PlanejarTab.ORCAMENTO) { onTab(PlanejarTab.ORCAMENTO) },
            TopTab(stringResource(R.string.plan_tab_recorrentes), current == PlanejarTab.RECORRENTES) { onTab(PlanejarTab.RECORRENTES) },
            TopTab(stringResource(R.string.plan_tab_metas), current == PlanejarTab.METAS) { onTab(PlanejarTab.METAS) },
        ),
    )
}

/**
 * Uma leitura vista pela tela: o valor (a copia guardada, depois a nova), "sem conexão" e o erro.
 * Uma releitura que falha nunca apaga o que ja estava na tela.
 */
class ScreenLoad<T> {
    var value by mutableStateOf<T?>(null)
    var loaded by mutableStateOf(false)
    var offline by mutableStateOf(false)
    var offlineText by mutableStateOf("")
    var error by mutableStateOf("")

    /** Le [flow] para dentro desta leitura; [accept] recusa uma copia que nao serve (o plano de antes de 038). */
    suspend fun collect(app: Application, flow: Flow<Load<T>>, failure: Int, accept: (T) -> Boolean = { true }) {
        flow.collect { load ->
            when (load) {
                is Load.Cached -> if (accept(load.value)) {
                    value = load.value
                    loaded = true
                    offlineText = app.getString(R.string.lanc_offline, storedTimeLabel(load.storedAt))
                }
                is Load.Fresh -> {
                    if (accept(load.value)) value = load.value
                    loaded = true
                    offline = false
                    error = ""
                }
                is Load.Failed -> {
                    loaded = true
                    when (val failed = load.error) {
                        is ApiException.Network, is ApiException.BadResponse -> {
                            offline = true
                            if (load.cached == null) offlineText = app.getString(R.string.lanc_offline_no_copy)
                        }
                        is ApiException.Unauthorized -> error = failed.serverMessage ?: app.getString(R.string.data_session_expired)
                        is ApiException.Http -> error = failed.serverMessage ?: app.getString(failure)
                    }
                }
            }
        }
    }
}

/**
 * O texto de uma escrita de Planejar/Ajustes que nao deu (ou null quando deu): a mensagem do
 * servidor como chegou; sem conexao, "Esta ação só funciona conectado." (nada vai para a fila).
 */
fun planWriteError(app: Application, result: InboxWrite<*>, fallback: Int): String? = when (result) {
    is InboxWrite.Done<*> -> null
    is InboxWrite.Offline -> app.getString(R.string.plan_offline_action)
    is InboxWrite.SessionExpired -> result.message ?: app.getString(R.string.data_session_expired)
    is InboxWrite.Conflict -> result.message ?: app.getString(fallback)
    is InboxWrite.Refused -> result.message ?: app.getString(fallback)
}

/** A pagina: o topo, o snackbar dos avisos (com a vibracao) e a lista; relê ao voltar para a frente. */
@Composable
fun PlanejarScaffold(
    notices: SharedFlow<String>,
    onRefresh: () -> Unit,
    topBar: @Composable () -> Unit,
    content: LazyListScope.() -> Unit,
) {
    val palette = LocalPalette.current
    val snackbar = remember { SnackbarHostState() }
    val haptic = LocalHapticFeedback.current
    val lifecycleOwner = LocalLifecycleOwner.current
    LaunchedEffect(lifecycleOwner) {
        lifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) { onRefresh() }
    }
    LaunchedEffect(notices) {
        notices.collect { message ->
            haptic.performHapticFeedback(HapticFeedbackType.LongPress)
            snackbar.showSnackbar(message)
        }
    }
    Scaffold(
        containerColor = palette.background,
        snackbarHost = {
            SnackbarHost(snackbar) { data ->
                Snackbar(snackbarData = data, containerColor = palette["zinc-900"], contentColor = palette["zinc-50"])
            }
        },
        topBar = topBar,
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 32.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            content = content,
        )
    }
}

/** Um numero do SummaryPanel: rotulo, valor, dica e a cor (perda em rose, ganho em emerald, apagado em cinza). */
data class SummaryValue(
    val label: String,
    val value: String,
    val hint: String? = null,
    val loss: Boolean = false,
    val muted: Boolean = false,
    val gain: Boolean = false,
)

/** O SummaryPanel de components/ui.jsx: o numero principal em destaque e os outros embaixo. */
@Composable
fun SummaryPanel(lead: SummaryValue, figures: List<SummaryValue>) {
    val palette = LocalPalette.current
    fun color(item: SummaryValue): Color = when {
        item.loss -> palette.loss
        item.gain -> palette.gain
        item.muted -> palette.muted
        else -> palette.text
    }
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(lead.label, color = palette.muted, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                FitText(text = lead.value, maxSize = 30.sp, minSize = 20.sp, color = color(lead))
                if (lead.hint != null) Text(lead.hint, color = palette.muted, fontSize = 12.sp)
            }
            figures.chunked(2).forEach { row ->
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    row.forEach { item ->
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text(item.label, color = palette.muted, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            FitText(text = item.value, maxSize = 18.sp, minSize = 12.sp, color = color(item), fontWeight = FontWeight.Bold)
                            if (item.hint != null) Text(item.hint, color = palette.muted, fontSize = 11.sp, maxLines = 2)
                        }
                    }
                    if (row.size == 1) Box(Modifier.weight(1f))
                }
            }
        }
    }
}

/** O BudgetProgressBar: a barra de 0 a 100% na cor do estado (OK emerald, perto amber, estourou rose). */
@Composable
fun BudgetProgressBar(percent: BigDecimal?, status: BudgetStatus, modifier: Modifier = Modifier, height: Int = 8) {
    val palette = LocalPalette.current
    val fraction = ((percent ?: BigDecimal.ZERO).toFloat() / 100f).coerceIn(0f, 1f)
    val fill = when (status) {
        BudgetStatus.OVER -> palette["rose-500"]
        BudgetStatus.WARNING -> palette["amber-500"]
        else -> palette.accent
    }
    Box(
        modifier
            .fillMaxWidth()
            .height(height.dp)
            .background(palette["zinc-100"], RoundedCornerShape(50)),
    ) {
        if (fraction > 0f) Box(Modifier.fillMaxWidth(fraction).fillMaxHeight().background(fill, RoundedCornerShape(50)))
    }
}
