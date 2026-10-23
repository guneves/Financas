package br.financas.app.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import br.financas.app.ui.theme.LocalPalette

/** As variantes do Button de components/ui.jsx. */
enum class ButtonVariant { PRIMARY, SECONDARY, SUBTLE }

/**
 * O Button da web: primario (verde), secundario (contorno) ou sutil (so o texto). [loading]
 * mostra o giro no lugar e desliga o toque, como o `loading` da web. 48 dp de altura.
 */
@Composable
fun AppButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    variant: ButtonVariant = ButtonVariant.PRIMARY,
    loading: Boolean = false,
    enabled: Boolean = true,
) {
    val palette = LocalPalette.current
    val shape = RoundedCornerShape(14.dp)
    val padding = PaddingValues(horizontal = 16.dp, vertical = 10.dp)
    val sized = modifier.heightIn(min = 48.dp)
    val content: @Composable (Color) -> Unit = { spinner ->
        if (loading) {
            CircularProgressIndicator(modifier = Modifier.size(16.dp), strokeWidth = 2.dp, color = spinner)
            Spacer(Modifier.width(8.dp))
        }
        Text(text, fontWeight = FontWeight.Bold, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
    when (variant) {
        ButtonVariant.PRIMARY -> Button(
            onClick = onClick,
            enabled = enabled && !loading,
            modifier = sized,
            shape = shape,
            contentPadding = padding,
            colors = ButtonDefaults.buttonColors(
                containerColor = palette.accent,
                contentColor = palette.onAccent,
                disabledContainerColor = palette["zinc-200"],
                disabledContentColor = palette.muted,
            ),
        ) { content(palette.muted) }
        ButtonVariant.SECONDARY -> OutlinedButton(
            onClick = onClick,
            enabled = enabled && !loading,
            modifier = sized,
            shape = shape,
            contentPadding = padding,
            border = BorderStroke(1.dp, palette["zinc-300"]),
            colors = ButtonDefaults.outlinedButtonColors(
                contentColor = palette.text,
                disabledContentColor = palette.muted,
            ),
        ) { content(palette.muted) }
        ButtonVariant.SUBTLE -> TextButton(
            onClick = onClick,
            enabled = enabled && !loading,
            modifier = sized,
            shape = shape,
            contentPadding = padding,
            colors = ButtonDefaults.textButtonColors(
                contentColor = palette["zinc-700"],
                disabledContentColor = palette.muted,
            ),
        ) { content(palette.muted) }
    }
}
