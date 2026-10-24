package br.financas.app.ui.components

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.sp
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import br.financas.app.ui.theme.LocalPalette

/** Os tons do Badge de components/ui.jsx. */
enum class BadgeTone { NEUTRAL, WARNING, INFO, DANGER, SUCCESS }

/** O Badge da web: uma etiqueta pequena. Cor so quando significa aviso ou informacao. */
@Composable
fun Badge(text: String, tone: BadgeTone = BadgeTone.NEUTRAL) {
    val palette = LocalPalette.current
    val (fill, ink) = when (tone) {
        BadgeTone.NEUTRAL -> palette["zinc-100"] to palette["zinc-700"]
        BadgeTone.WARNING -> palette["amber-50"] to palette.warning
        BadgeTone.INFO -> palette["sky-50"] to palette.info
        BadgeTone.DANGER -> palette["rose-50"] to palette.loss
        BadgeTone.SUCCESS -> palette["emerald-50"] to palette.gain
    }
    Surface(shape = RoundedCornerShape(50), color = fill, contentColor = ink) {
        Text(
            text = text,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.SemiBold,
            color = ink,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
        )
    }
}

/** Uma acao do [OverflowMenu]. */
data class MenuAction(val label: String, val onSelect: () -> Unit)

/** O Menu ("⋯") da web: duas ou mais acoes de uma linha atras de um botao. 48 dp. */
@Composable
fun OverflowMenu(actions: List<MenuAction>, label: String, enabled: Boolean = true) {
    val palette = LocalPalette.current
    var open by remember { mutableStateOf(false) }
    Box {
        Surface(
            onClick = { open = true },
            enabled = enabled,
            shape = RoundedCornerShape(14.dp),
            color = palette.surface,
            contentColor = palette["zinc-700"],
            border = BorderStroke(1.dp, palette["zinc-300"]),
            modifier = Modifier.size(48.dp).semantics { contentDescription = label },
        ) {
            Box(contentAlignment = Alignment.Center) {
                Text("⋯", style = MaterialTheme.typography.titleLarge, color = palette["zinc-700"])
            }
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            actions.forEach { action ->
                DropdownMenuItem(
                    text = { Text(action.label, color = palette.text) },
                    onClick = {
                        open = false
                        action.onSelect()
                    },
                    modifier = Modifier.heightIn(min = 48.dp),
                )
            }
        }
    }
}

/** O pedido de confirmacao: os textos do confirmAction() da web. */
data class ConfirmRequest(
    val title: String,
    val message: String,
    val confirmLabel: String,
    val onConfirm: () -> Unit,
)

/**
 * O confirmAction() da web: titulo, texto e o botao de confirmar. Toda acao destrutiva passa por
 * aqui, nunca direto. Nada quando [request] e null.
 */
@Composable
fun ConfirmDialog(request: ConfirmRequest?, cancelLabel: String, onDismiss: () -> Unit) {
    if (request == null) return
    val palette = LocalPalette.current
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = palette.surface,
        titleContentColor = palette.text,
        textContentColor = palette["zinc-700"],
        title = { Text(request.title, fontWeight = FontWeight.ExtraBold) },
        text = { Text(request.message) },
        confirmButton = {
            TextButton(onClick = {
                onDismiss()
                request.onConfirm()
            }) { Text(request.confirmLabel, fontWeight = FontWeight.Bold, color = palette["emerald-700"]) }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text(cancelLabel, color = palette["zinc-700"]) }
        },
    )
}

/** O ListSkeleton da web: linhas que pulsam enquanto a lista chega (nunca o vazio). */
@Composable
fun ListSkeleton(rows: Int = 3, modifier: Modifier = Modifier) {
    val palette = LocalPalette.current
    val transition = rememberInfiniteTransition(label = "skeleton")
    val pulse by transition.animateFloat(
        initialValue = 0.45f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(800), RepeatMode.Reverse),
        label = "pulse",
    )
    Column(modifier = modifier.fillMaxWidth().alpha(pulse), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        repeat(rows) {
            Surface(shape = RoundedCornerShape(20.dp), color = palette.surface, border = BorderStroke(1.dp, palette.border)) {
                Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Box(Modifier.fillMaxWidth(0.6f).height(16.dp).background(palette["zinc-200"], RoundedCornerShape(8.dp)))
                    Box(Modifier.fillMaxWidth(0.35f).height(12.dp).background(palette["zinc-100"], RoundedCornerShape(6.dp)))
                    Box(Modifier.fillMaxWidth(0.8f).height(12.dp).background(palette["zinc-100"], RoundedCornerShape(6.dp)))
                }
            }
        }
    }
}

/** O EmptyState da web: o titulo e, se houver, a explicacao. */
@Composable
fun EmptyState(title: String, message: String? = null, modifier: Modifier = Modifier) {
    val palette = LocalPalette.current
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        color = palette.surface,
        border = BorderStroke(1.dp, palette.border),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 20.dp, vertical = 28.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = palette.text, textAlign = TextAlign.Center)
            if (!message.isNullOrEmpty()) {
                Text(message, style = MaterialTheme.typography.bodyMedium, color = palette.muted, textAlign = TextAlign.Center)
            }
        }
    }
}

/** O Panel de components/ui.jsx: a superficie branca com borda de cada bloco da tela. */
@Composable
fun Panel(
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    content: @Composable () -> Unit,
) {
    val palette = LocalPalette.current
    val shape = RoundedCornerShape(20.dp)
    val border = BorderStroke(1.dp, palette.border)
    if (onClick != null) {
        Surface(onClick = onClick, modifier = modifier.fillMaxWidth(), shape = shape, color = palette.surface, border = border) {
            content()
        }
    } else {
        Surface(modifier = modifier.fillMaxWidth(), shape = shape, color = palette.surface, border = border) {
            content()
        }
    }
}

/**
 * O FitValue da web: um valor grande que encolhe para caber na linha, em vez de ser cortado.
 * Comeca em [maxSize] e desce ate [minSize]; abaixo disso, corta.
 */
@Composable
fun FitText(
    text: String,
    maxSize: TextUnit,
    minSize: TextUnit,
    color: Color,
    modifier: Modifier = Modifier,
    fontWeight: FontWeight = FontWeight.ExtraBold,
) {
    var size by remember(text, maxSize) { mutableStateOf(maxSize) }
    Text(
        text = text,
        color = color,
        fontSize = size,
        fontWeight = fontWeight,
        maxLines = 1,
        softWrap = false,
        overflow = TextOverflow.Clip,
        modifier = modifier,
        onTextLayout = { layout ->
            if (layout.didOverflowWidth && size.value > minSize.value) {
                size = (size.value - 2f).coerceAtLeast(minSize.value).sp
            }
        },
    )
}
