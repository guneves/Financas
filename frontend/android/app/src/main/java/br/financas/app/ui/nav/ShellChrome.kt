package br.financas.app.ui.nav

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.core.formatCurrency
import br.financas.app.core.formatDateBR
import br.financas.app.rules.ApkUpdateTexts
import br.financas.app.rules.PendingRow
import br.financas.app.rules.PendingRows
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AlertTone
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.AppIcons
import br.financas.app.ui.components.AppSheet
import br.financas.app.ui.components.Badge
import br.financas.app.ui.components.BadgeTone
import br.financas.app.ui.components.ButtonVariant
import br.financas.app.ui.components.ConfirmDialog
import br.financas.app.ui.components.ConfirmRequest
import br.financas.app.ui.components.EmptyState
import br.financas.app.ui.components.MenuAction
import br.financas.app.ui.components.OverflowMenu
import br.financas.app.ui.theme.LocalPalette

// ---- A barra de baixo ----

@Composable
fun ShellBottomBar(current: ShellNav.Section?, onSelect: (ShellNav.Section) -> Unit) {
    val palette = LocalPalette.current
    Surface(color = palette.surface) {
        Column {
            HorizontalDivider(color = palette.border)
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .windowInsetsPadding(WindowInsets.navigationBars)
                    .padding(vertical = 4.dp),
            ) {
                ShellNav.Section.entries.forEach { section ->
                    val (icon, label) = when (section) {
                        ShellNav.Section.HOME -> AppIcons.Home to R.string.home_nav_home
                        ShellNav.Section.LANCAMENTOS -> AppIcons.Receipt to R.string.home_nav_entries
                        ShellNav.Section.PLANEJAR -> AppIcons.Target to R.string.home_nav_plan
                        ShellNav.Section.INVESTIR -> AppIcons.Briefcase to R.string.home_nav_invest
                        ShellNav.Section.AJUSTES -> AppIcons.Settings to R.string.shell_nav_settings
                    }
                    NavTab(icon, stringResource(label), active = section == current, onClick = { onSelect(section) }, modifier = Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
private fun NavTab(icon: ImageVector, name: String, active: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val palette = LocalPalette.current
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
        modifier = modifier.heightIn(min = 56.dp).clickable(onClick = onClick).semantics { contentDescription = name },
    ) {
        Box(
            contentAlignment = Alignment.Center,
            modifier = Modifier
                .size(width = 48.dp, height = 28.dp)
                .background(if (active) palette["emerald-100"] else Color.Transparent, RoundedCornerShape(50)),
        ) {
            Icon(icon, contentDescription = null, tint = if (active) palette["emerald-800"] else palette.muted, modifier = Modifier.size(20.dp))
        }
        Text(
            text = name,
            fontSize = 11.sp,
            fontWeight = FontWeight.SemiBold,
            color = if (active) palette.text else palette.muted,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

/** O "+" (o "+ Novo"): o botao verde de 56 dp, por cima da pagina, no canto de baixo. */
@Composable
fun NewEntryButton(onClick: () -> Unit, modifier: Modifier = Modifier) {
    val palette = LocalPalette.current
    val label = stringResource(R.string.home_nav_new)
    Surface(
        onClick = onClick,
        shape = RoundedCornerShape(18.dp),
        color = palette.accent,
        shadowElevation = 6.dp,
        modifier = modifier.size(56.dp).semantics { contentDescription = label },
    ) {
        Box(contentAlignment = Alignment.Center) {
            Icon(AppIcons.Plus, contentDescription = null, tint = palette.onAccent, modifier = Modifier.size(26.dp))
        }
    }
}

/** O aviso do APK novo (ApkUpdateBanner da web), logo acima da barra de baixo. */
@Composable
fun ApkBanner(prompt: ApkUpdateTexts.Prompt, status: ApkUpdateTexts.Message?, busy: Boolean, onInstall: () -> Unit) {
    val palette = LocalPalette.current
    Surface(color = palette["sky-50"], border = BorderStroke(1.dp, palette.info.copy(alpha = 0.25f))) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    stringResource(R.string.ajustes_apk_new, prompt.versionName),
                    color = palette.info,
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 13.sp,
                    modifier = Modifier.weight(1f),
                )
                AppButton(stringResource(R.string.ajustes_apk_install), onInstall, variant = ButtonVariant.SECONDARY, loading = busy)
            }
            status?.let { Text(it.text, color = palette["zinc-700"], fontSize = 12.sp) }
        }
    }
}

// ---- Pendentes ----

/**
 * A folha Pendentes (components/PendingSheet.jsx): o que foi lancado neste aparelho e ainda nao
 * chegou ao servidor. Corrigir reabre o "+ Novo" ([onEdit]); Descartar confirma antes.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PendingSheet(viewModel: ShellViewModel, onEdit: (PendingRow) -> Unit) {
    val palette = LocalPalette.current
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var confirm by remember { mutableStateOf<ConfirmRequest?>(null) }
    val rows = viewModel.rows
    val discardTitle = stringResource(R.string.shell_pending_discard_title)
    val discardLabel = stringResource(R.string.shell_pending_discard)
    val dismiss = stringResource(R.string.home_dismiss_error)
    AppSheet(
        title = stringResource(R.string.shell_pending_title),
        sheetState = sheetState,
        onDismiss = viewModel::closePending,
        footer = {
            if (rows.isNotEmpty()) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    AppButton(stringResource(R.string.shell_close), viewModel::closePending, Modifier.weight(1f), ButtonVariant.SECONDARY)
                    AppButton(stringResource(R.string.shell_sync_now), viewModel::sync, Modifier.weight(1f), loading = viewModel.syncing)
                }
            } else {
                AppButton(stringResource(R.string.shell_close), viewModel::closePending, Modifier.fillMaxWidth(), ButtonVariant.SECONDARY)
            }
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(stringResource(R.string.shell_pending_description), color = palette.muted, fontSize = 14.sp)
            if (viewModel.syncWarning.isNotEmpty()) {
                AlertMessage(viewModel.syncWarning, AlertTone.WARNING, dismiss, onDismiss = viewModel::dismissWarning)
            } else if (viewModel.offline) {
                AlertMessage(stringResource(R.string.shell_offline_info), AlertTone.INFO, dismiss)
            }
            if (rows.isEmpty()) {
                EmptyState(stringResource(R.string.shell_pending_empty_title), stringResource(R.string.shell_pending_empty_message))
            } else {
                Column {
                    rows.forEachIndexed { index, row ->
                        if (index > 0) HorizontalDivider(color = palette["zinc-100"])
                        PendingRowView(
                            row = row,
                            onEdit = { onEdit(row) },
                            onDiscard = {
                                confirm = ConfirmRequest(
                                    title = discardTitle,
                                    message = PendingRows.discardMessage(row, ::formatCurrency),
                                    confirmLabel = discardLabel,
                                    onConfirm = { viewModel.discard(row) },
                                )
                            },
                        )
                    }
                }
            }
        }
    }
    ConfirmDialog(confirm, stringResource(R.string.lanc_cancel)) { confirm = null }
}

@Composable
private fun PendingRowView(row: PendingRow, onEdit: () -> Unit, onDiscard: () -> Unit) {
    val palette = LocalPalette.current
    val fix = stringResource(R.string.shell_pending_fix)
    val discard = stringResource(R.string.shell_pending_discard)
    // Operacao e provento (Investimentos) nao tem formulario no "+ Novo": so Descartar.
    val actions = listOfNotNull(MenuAction(fix, onEdit).takeIf { row.editable }, MenuAction(discard, onDiscard))
    Row(verticalAlignment = Alignment.Top, modifier = Modifier.fillMaxWidth().padding(vertical = 12.dp)) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    row.title,
                    color = palette.text,
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 14.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f, fill = false),
                )
                Badge(
                    stringResource(if (row.refused) R.string.shell_pending_refused else R.string.shell_pending_badge),
                    if (row.refused) BadgeTone.WARNING else BadgeTone.NEUTRAL,
                )
            }
            Text(PendingRows.detail(row) { formatDateBR(it) }, color = palette.muted, fontSize = 12.sp)
            row.lastError?.let { Text(it, color = palette["amber-800"], fontSize = 12.sp, fontWeight = FontWeight.Medium) }
        }
        Text(
            formatCurrency(row.amount),
            color = palette.text,
            fontWeight = FontWeight.SemiBold,
            fontSize = 14.sp,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 12.dp),
        )
        OverflowMenu(actions, stringResource(R.string.shell_pending_actions))
    }
}
