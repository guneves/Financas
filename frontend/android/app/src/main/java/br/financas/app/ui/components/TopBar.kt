package br.financas.app.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
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

/** Uma aba do topo: o rotulo, se e a aberta e o toque. */
data class TopTab(val label: String, val active: Boolean, val onClick: () -> Unit)

/**
 * O topo das paginas nativas: voltar, o titulo, o olho do modo privado (sem [onToggleHidden],
 * nenhum) e as abas da secao, que rolam de lado quando nao cabem.
 */
@Composable
fun NativeTopBar(
    title: String,
    onBack: () -> Unit,
    hidden: Boolean = false,
    onToggleHidden: (() -> Unit)? = null,
    tabs: List<TopTab> = emptyList(),
) {
    val palette = LocalPalette.current
    val backLabel = stringResource(R.string.native_back)
    Column(
        Modifier
            .fillMaxWidth()
            .windowInsetsPadding(WindowInsets.statusBars)
            .padding(vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(horizontal = 8.dp)) {
            Surface(
                onClick = onBack,
                shape = RoundedCornerShape(50),
                color = palette.background,
                contentColor = palette.text,
                modifier = Modifier.size(48.dp).semantics { contentDescription = backLabel },
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Text("←", style = MaterialTheme.typography.titleLarge, color = palette.text)
                }
            }
            Text(
                text = title,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.ExtraBold,
                color = palette.text,
                modifier = Modifier.padding(start = 8.dp).weight(1f),
            )
            if (onToggleHidden != null) {
                val eyeLabel = stringResource(if (hidden) R.string.lanc_show_values else R.string.lanc_hide_values)
                Surface(
                    onClick = onToggleHidden,
                    shape = CircleShape,
                    color = if (hidden) palette["emerald-50"] else palette.surface,
                    border = BorderStroke(1.dp, if (hidden) palette.accent.copy(alpha = 0.35f) else palette.border),
                    modifier = Modifier.size(48.dp).semantics { contentDescription = eyeLabel },
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(
                            imageVector = if (hidden) AppIcons.EyeOff else AppIcons.Eye,
                            contentDescription = null,
                            tint = if (hidden) palette["emerald-700"] else palette["zinc-700"],
                            modifier = Modifier.size(20.dp),
                        )
                    }
                }
            }
        }
        if (tabs.isNotEmpty()) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp),
            ) {
                tabs.forEach { TabChip(it) }
            }
        }
    }
}

@Composable
private fun TabChip(tab: TopTab) {
    val palette = LocalPalette.current
    Surface(
        onClick = { if (!tab.active) tab.onClick() },
        shape = RoundedCornerShape(50),
        color = if (tab.active) palette["zinc-900"] else palette.surface,
        contentColor = if (tab.active) palette["zinc-50"] else palette["zinc-700"],
        border = if (tab.active) null else BorderStroke(1.dp, palette.border),
        modifier = Modifier.heightIn(min = 48.dp),
    ) {
        Box(contentAlignment = Alignment.Center, modifier = Modifier.padding(PaddingValues(horizontal = 16.dp))) {
            Text(tab.label, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, maxLines = 1)
        }
    }
}
