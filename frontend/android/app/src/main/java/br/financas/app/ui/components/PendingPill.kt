package br.financas.app.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.ui.theme.LocalPalette

/**
 * O que a casca mostra no topo de cada pagina (a pilula de pendentes do Layout.jsx): as paginas
 * so leem; quem abre a folha e a casca. null fora da casca (o "+ Novo", o login).
 */
data class ShellChrome(
    val pendingCount: Int,
    val attention: Boolean,
    val offline: Boolean,
    val onOpenPending: () -> Unit,
)

val LocalShellChrome = compositionLocalOf<ShellChrome?> { null }

/**
 * A pilula de pendentes (PendingPill do Layout.jsx): "<n> pendente(s)" quando a fila tem itens
 * do usuario, ou o icone de sem conexao; ambar com um recusado ou sem conexao. Abre Pendentes.
 */
@Composable
fun PendingPill() {
    val chrome = LocalShellChrome.current ?: return
    if (chrome.pendingCount <= 0 && !chrome.offline) return
    val palette = LocalPalette.current
    val warn = chrome.attention
    val label = if (chrome.pendingCount > 0) {
        stringResource(if (chrome.pendingCount == 1) R.string.shell_pending_one else R.string.shell_pending_many, chrome.pendingCount)
    } else {
        stringResource(R.string.shell_offline)
    }
    Surface(
        onClick = chrome.onOpenPending,
        shape = RoundedCornerShape(50),
        color = if (warn) palette["amber-50"] else palette.surface,
        border = BorderStroke(1.dp, if (warn) palette.warning.copy(alpha = 0.35f) else palette.border),
        modifier = Modifier.heightIn(min = 48.dp).semantics { contentDescription = label },
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(horizontal = 12.dp)) {
            if (chrome.offline) {
                Icon(AppIcons.CloudOff, contentDescription = null, tint = palette["amber-800"], modifier = Modifier.size(16.dp))
            }
            if (chrome.pendingCount > 0) {
                Text(
                    text = label,
                    color = if (warn) palette["amber-800"] else palette["zinc-700"],
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 13.sp,
                    maxLines = 1,
                    modifier = Modifier.padding(start = if (chrome.offline) 6.dp else 0.dp),
                )
            }
        }
    }
}
