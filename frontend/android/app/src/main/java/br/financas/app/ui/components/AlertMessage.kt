package br.financas.app.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import br.financas.app.ui.theme.LocalPalette

/** Os tons do AlertMessage da web: danger (rose), warning (amber), info (sky). */
enum class AlertTone { DANGER, WARNING, INFO }

/**
 * O AlertMessage de components/ui.jsx: a caixa de erro/aviso no corpo da tela, que fica ate ser
 * lida (o toast some). Nada quando [message] e vazio. [onDismiss] mostra o X (48 dp).
 */
@Composable
fun AlertMessage(
    message: String,
    tone: AlertTone = AlertTone.DANGER,
    dismissLabel: String,
    onDismiss: (() -> Unit)? = null,
    modifier: Modifier = Modifier,
) {
    if (message.isEmpty()) return
    val palette = LocalPalette.current
    val (fill, ink) = when (tone) {
        AlertTone.DANGER -> palette["rose-50"] to palette.loss
        AlertTone.WARNING -> palette["amber-50"] to palette.warning
        AlertTone.INFO -> palette["sky-50"] to palette.info
    }
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = fill,
        contentColor = ink,
        border = BorderStroke(1.dp, ink.copy(alpha = 0.25f)),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = message,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium,
                color = ink,
                modifier = Modifier.weight(1f).padding(start = 16.dp, top = 12.dp, bottom = 12.dp, end = 4.dp),
            )
            if (onDismiss != null) {
                Surface(
                    onClick = onDismiss,
                    color = fill,
                    contentColor = ink,
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier.size(48.dp).semantics { contentDescription = dismissLabel },
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text(text = "\u00D7", style = MaterialTheme.typography.titleLarge, color = ink)
                    }
                }
            }
        }
    }
}
