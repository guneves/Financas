package br.financas.app.ui.investimentos

import android.app.Application
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.core.formatPercent
import br.financas.app.data.AppGraph
import br.financas.app.data.InboxWrite
import br.financas.app.outbox.OutboxPlugin
import br.financas.app.outbox.OutboxStore
import br.financas.app.outbox.OutboxWorker
import br.financas.app.rules.ProceedsRules
import br.financas.app.ui.components.NativeTopBar
import br.financas.app.ui.components.SegmentedChoice
import br.financas.app.ui.components.SelectOption
import br.financas.app.ui.components.TopTab
import br.financas.app.ui.newentry.EntryQueue
import br.financas.app.ui.newentry.EntrySaver
import br.financas.app.ui.theme.LocalPalette
import br.financas.app.ui.theme.Palette
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.math.BigDecimal

/** As abas de Investimentos, na ordem de lib/navigation.js. */
enum class InvestimentosTab { POSICAO, RENTABILIDADE, OPERACOES, ALOCACAO, PROVENTOS, IR, CALCULADORA }

/** O topo das paginas de Investimentos: voltar, titulo, o olho e as sete abas. */
@Composable
fun InvestimentosTopBar(
    title: String,
    current: InvestimentosTab,
    hidden: Boolean,
    onBack: () -> Unit,
    onToggleHidden: (() -> Unit)?,
    onTab: (InvestimentosTab) -> Unit,
) {
    @Composable
    fun tab(label: Int, value: InvestimentosTab) = TopTab(stringResource(label), current == value) { onTab(value) }
    NativeTopBar(
        title = title,
        hidden = hidden,
        onBack = onBack,
        onToggleHidden = onToggleHidden,
        tabs = listOf(
            tab(R.string.inv_tab_posicao, InvestimentosTab.POSICAO),
            tab(R.string.inv_tab_rentabilidade, InvestimentosTab.RENTABILIDADE),
            tab(R.string.inv_tab_operacoes, InvestimentosTab.OPERACOES),
            tab(R.string.inv_tab_alocacao, InvestimentosTab.ALOCACAO),
            tab(R.string.inv_tab_proventos, InvestimentosTab.PROVENTOS),
            tab(R.string.inv_tab_ir, InvestimentosTab.IR),
            tab(R.string.inv_tab_calculadora, InvestimentosTab.CALCULADORA),
        ),
    )
}

/**
 * O texto de uma escrita de Investimentos que nao deu (ou null quando deu): a mensagem do servidor
 * como chegou; sem conexao, "Esta ação só funciona conectado." (edicoes, exclusoes, cotacoes e
 * resgates nunca vao para a fila).
 */
fun investWriteError(app: Application, result: InboxWrite<*>, fallback: Int): String? =
    br.financas.app.ui.planejar.planWriteError(app, result, fallback)

/** A cor de um percentual de rentabilidade: ganho verde, perda vermelha, zero apagado (Profit da web). */
fun profitColor(palette: Palette, value: BigDecimal?): Color = when {
    value == null -> palette.muted
    value.signum() > 0 -> palette["emerald-700"]
    value.signum() < 0 -> palette.loss
    else -> palette.muted
}

/** "+1,23%" com a cor de ganho/perda. */
@Composable
fun ProfitText(value: BigDecimal?, fontSize: Int = 14, modifier: Modifier = Modifier) {
    val palette = LocalPalette.current
    Text(
        formatPercent(value, 2, signed = true),
        color = profitColor(palette, value),
        fontWeight = FontWeight.SemiBold,
        fontSize = fontSize.sp,
        modifier = modifier,
    )
}

/** Um ponto de legenda (LegendDot): a cor e o rotulo. */
@Composable
fun LegendDot(color: Color, label: String) {
    val palette = LocalPalette.current
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Box(Modifier.size(10.dp).background(color, CircleShape))
        Text(label, color = palette["zinc-600"], fontSize = 12.sp)
    }
}

/** Os chips de periodo (6M, 1A...): o SegmentedControl da web, rolando quando nao cabe. */
@Composable
fun PeriodChips(items: List<Pair<String, String>>, value: String, onChange: (String) -> Unit) {
    SegmentedChoice(items = items.map { SelectOption(it.first, it.second) }, value = value, onChange = onChange)
}

/** Uma linha "rotulo ... valor" de um detalhe (DetailFigure da web). */
@Composable
fun DetailFigure(label: String, value: String, hint: String? = null) {
    val palette = LocalPalette.current
    Row(
        verticalAlignment = Alignment.Top,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier.fillMaxWidth().heightIn(min = 36.dp).padding(vertical = 6.dp),
    ) {
        Text(label, color = palette["zinc-600"], fontSize = 14.sp, modifier = Modifier.weight(1f))
        Column(horizontalAlignment = Alignment.End) {
            Text(value, color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
            if (hint != null) Text(hint, color = palette.muted, fontSize = 12.sp)
        }
    }
}

/**
 * A sincronizacao dos proventos automaticos (lib/proceedsSync.js): ao abrir uma tela no maximo a
 * cada 10 min por processo, e 1,5 s depois de uma escrita que muda posicao (changesPositions). So
 * avisa ([onChanged]) quando algo mudou. Falha calada: e so conforto.
 */
object ProceedsSync {
    const val MIN_INTERVAL_MS = 10 * 60 * 1000L
    const val AFTER_WRITE_DELAY_MS = 1500L

    @Volatile
    private var lastRun = 0L

    /** Ao abrir: roda se a ultima foi ha mais de 10 min. */
    fun onOpen(app: Application, onChanged: () -> Unit) {
        val now = System.currentTimeMillis()
        if (now - lastRun < MIN_INTERVAL_MS) return
        lastRun = now
        run(app, onChanged)
    }

    /** Depois de gravar em [path] (/api/investments..., /api/corporate-actions...). */
    fun afterWrite(app: Application, path: String, onChanged: () -> Unit) {
        if (!ProceedsRules.changesPositions(path)) return
        val graph = AppGraph.from(app)
        graph.appScope.launch {
            delay(AFTER_WRITE_DELAY_MS)
            lastRun = System.currentTimeMillis()
            run(app, onChanged)
        }
    }

    private fun run(app: Application, onChanged: () -> Unit) {
        val graph = AppGraph.from(app)
        graph.appScope.launch {
            val result = graph.investimentos.syncProceeds(force = false)
            if (result is InboxWrite.Done && result.value.created + result.value.updated + result.value.removed > 0) onChanged()
        }
    }
}

/**
 * O Salvar das duas criacoes de Investimentos que a fila guarda sem conexao (conventions.md):
 * o mesmo caminho do "+ Novo" (EntrySaver), com o prazo de 6 s, o item na fila antes do POST e o
 * envio em segundo plano (OutboxWorker).
 */
fun investmentSaver(app: Application): EntrySaver {
    val graph = AppGraph.from(app)
    return EntrySaver(
        hasNetwork = { OutboxPlugin.hasRealNetwork(app) },
        post = { path, body -> graph.creationApi.send("POST", path, body) },
        queue = object : EntryQueue {
            override fun put(item: org.json.JSONObject) = OutboxStore.get(app).put(item)
            override fun remove(clientId: String) = OutboxStore.get(app).remove(clientId)
            override fun schedule() = OutboxWorker.schedule(app)
        },
        userId = { graph.sessionUserId() },
    )
}

/** Quantos itens de [kind] o usuario da sessao tem na fila (o aviso "N na fila" das telas). */
fun queuedCount(app: Application, kind: String): Int {
    val user = AppGraph.from(app).sessionUserId() ?: return 0
    return OutboxStore.get(app).all().count { item -> item.optString("user_id") == user && item.optString("kind") == kind }
}
