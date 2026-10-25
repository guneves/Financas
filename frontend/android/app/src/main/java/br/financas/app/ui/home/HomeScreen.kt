package br.financas.app.ui.home

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Snackbar
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarVisuals
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
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
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import br.financas.app.R
import br.financas.app.core.formatCurrency
import br.financas.app.core.formatSignedCurrency
import br.financas.app.core.monthKey
import br.financas.app.core.monthLabel
import br.financas.app.data.HomeDto
import br.financas.app.data.storedTimeLabel
import br.financas.app.rules.HomeRules
import br.financas.app.rules.HomeSummary
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AlertTone
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.AppIcons
import br.financas.app.ui.components.FitText
import br.financas.app.ui.components.ListSkeleton
import br.financas.app.ui.components.PendingPill
import br.financas.app.ui.components.Panel
import br.financas.app.ui.components.Badge
import br.financas.app.ui.components.BadgeTone
import br.financas.app.ui.theme.LocalPalette
import java.math.BigDecimal

/** Um toast com o tom: [info] e o toast(..., { tone: 'info' }) da web. */
private class NoticeVisuals(override val message: String, val info: Boolean) : SnackbarVisuals {
    override val actionLabel: String? = null
    override val withDismissAction: Boolean = false
    override val duration: SnackbarDuration = SnackbarDuration.Short
}

/**
 * Inicio nativo (mobile-docs/native/screens/03-inicio.md): o pages/Dashboard.jsx em Compose, com
 * o cabecalho da casca (Aprovar, pendentes, o sino, o olho). [onOpenWeb] abre o link de um painel
 * (um caminho da web, NativeLinks); [onOpenInbox] abre Aprovar. A barra de baixo e o "+" sao da
 * casca (NativeActivity).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    viewModel: HomeViewModel,
    onOpenWeb: (String) -> Unit,
    onOpenInbox: () -> Unit,
) {
    val palette = LocalPalette.current
    val snackbar = remember { SnackbarHostState() }
    val lifecycleOwner = LocalLifecycleOwner.current

    // Ao abrir e a cada volta (inclusive de "+ Novo", que fica por cima sem parar esta tela).
    LaunchedEffect(lifecycleOwner) {
        lifecycleOwner.repeatOnLifecycle(Lifecycle.State.RESUMED) {
            viewModel.refreshAll()
        }
    }

    LaunchedEffect(Unit) {
        viewModel.notices.collect { notice -> snackbar.showSnackbar(NoticeVisuals(notice.message, notice.info)) }
    }

    val view = viewModel.view
    val home = viewModel.home
    val hidden = viewModel.hidden

    Scaffold(
        containerColor = palette.background,
        snackbarHost = {
            SnackbarHost(snackbar) { data ->
                // O Toaster da web: o mesmo fundo invertido para todo tom; o informativo so troca o
                // icone (Info no lugar do check).
                val info = (data.visuals as? NoticeVisuals)?.info == true
                Snackbar(containerColor = palette["zinc-900"], contentColor = palette["white"]) {
                    Row(verticalAlignment = Alignment.Top) {
                        Icon(
                            imageVector = if (info) AppIcons.Info else AppIcons.CheckCircle,
                            contentDescription = null,
                            tint = palette["white"],
                            modifier = Modifier.padding(top = 2.dp).size(16.dp),
                        )
                        Text(
                            text = data.visuals.message,
                            color = palette["white"],
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Medium,
                            modifier = Modifier.padding(start = 12.dp),
                        )
                    }
                }
            }
        },
        topBar = { HomeTopBar(viewModel, onOpenInbox) },
    ) { padding ->
        PullToRefreshBox(
            isRefreshing = viewModel.refreshing,
            onRefresh = viewModel::pullRefresh,
            modifier = Modifier.fillMaxSize().padding(padding),
        ) {
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                item(key = "alerts") { Alerts(viewModel, onOpenWeb) }
                if (view == null || home == null) {
                    item(key = "skeleton") { ListSkeleton(rows = 4) }
                } else {
                    item(key = "hero") { BalanceHero(view, hidden) }
                    item(key = "summary") { MonthSummary(view.summary, hidden, onOpenWeb) }
                    item(key = "invoice") { NextInvoiceTile(home, onOpenWeb) }
                    val shown = viewModel.shownAttention
                    if (shown.isNotEmpty()) {
                        item(key = "attention") { NeedsAttention(shown, viewModel, onOpenWeb) }
                    }
                    item(key = "flow") { CashFlowPanel(view, onOpenWeb) }
                    val panels = viewModel.panels
                    if (panels != null) item(key = "categories") { CategoriesPanel(panels, onOpenWeb) }
                    val budget = viewModel.budget
                    if (budget != null && budget.items.isNotEmpty()) {
                        item(key = "budget") { BudgetStrip(budget, onOpenWeb) }
                    }
                    if (panels != null) {
                        item(key = "invoices") {
                            InvoicesPanel(
                                panels = panels,
                                nextInvoicesTotal = home.nextInvoicesTotal,
                                payable = home.nextInvoices.any { it.payable },
                                closingDate = home.nextClosingDate,
                                paying = viewModel.paying,
                                onPay = viewModel::openPayPayable,
                                onOpenLink = onOpenWeb,
                            )
                        }
                        item(key = "installments") { InstallmentsPanel(panels, onOpenWeb) }
                        item(key = "pace") { PacePanel(panels) }
                    } else {
                        item(key = "panels-skeleton") { ListSkeleton(rows = 2) }
                    }
                    item(key = "balance") { BalancePanel(view, hidden) }
                }
            }
        }
    }

    viewModel.payRequest?.let { request -> PayInvoiceSheet(request, viewModel, view?.accounts.orEmpty()) }
    if (viewModel.bellOpen) AttentionBellSheet(viewModel, onOpenWeb)
}

// ---- Cabecalho e barra de baixo (os do Layout.jsx no celular) ----

@Composable
private fun HomeTopBar(viewModel: HomeViewModel, onOpenInbox: () -> Unit) {
    val palette = LocalPalette.current
    val hidden = viewModel.hidden
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        modifier = Modifier
            .fillMaxWidth()
            .windowInsetsPadding(WindowInsets.statusBars)
            .padding(horizontal = 16.dp, vertical = 8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.weight(1f)) {
            Box(
                contentAlignment = Alignment.Center,
                modifier = Modifier.size(36.dp).background(palette.brand, RoundedCornerShape(12.dp)),
            ) {
                Text("F", color = palette.brandInk, fontWeight = FontWeight.ExtraBold, fontSize = 16.sp)
            }
            Text(
                text = stringResource(R.string.home_brand),
                color = palette.text,
                fontWeight = FontWeight.ExtraBold,
                fontSize = 18.sp,
                maxLines = 1,
                overflow = TextOverflow.Clip,
                modifier = Modifier.padding(start = 10.dp),
            )
        }
        if (viewModel.inboxCount > 0) InboxPill(viewModel.inboxCount, onOpenInbox)
        PendingPill()
        BellButton(viewModel.attention.size, viewModel::openBell)
        RoundIconButton(
            icon = if (hidden) AppIcons.EyeOff else AppIcons.Eye,
            label = stringResource(if (hidden) R.string.home_privacy_show else R.string.home_privacy_hide),
            active = hidden,
            onClick = viewModel::toggleHidden,
        )
    }
}

@Composable
private fun RoundIconButton(icon: ImageVector, label: String, onClick: () -> Unit, active: Boolean = false) {
    val palette = LocalPalette.current
    Surface(
        onClick = onClick,
        shape = CircleShape,
        color = if (active) palette["emerald-50"] else palette.surface,
        border = BorderStroke(1.dp, if (active) palette.accent.copy(alpha = 0.35f) else palette.border),
        modifier = Modifier.size(48.dp).semantics { contentDescription = label },
    ) {
        Box(contentAlignment = Alignment.Center) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = if (active) palette["emerald-700"] else palette["zinc-700"],
                modifier = Modifier.size(20.dp),
            )
        }
    }
}

/** O sino: o numero e de todos os avisos de agora, os dispensados no Inicio inclusive. */
@Composable
private fun BellButton(count: Int, onClick: () -> Unit) {
    val palette = LocalPalette.current
    val badge = br.financas.app.rules.AttentionRules.bellBadge(count)
    Box {
        RoundIconButton(
            icon = AppIcons.Bell,
            label = br.financas.app.rules.AttentionRules.bellLabel(count),
            onClick = onClick,
        )
        if (badge.isNotEmpty()) {
            Surface(
                shape = CircleShape,
                color = palette["amber-100"],
                border = BorderStroke(1.dp, palette.surface),
                modifier = Modifier.align(Alignment.TopEnd).offset(x = 2.dp, y = (-2).dp),
            ) {
                Text(
                    text = badge,
                    color = palette["amber-800"],
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(horizontal = 5.dp, vertical = 1.dp),
                )
            }
        }
    }
}

/** A pilula de Aprovar: ambar, o que espera a decisao do dono. Abre Aprovar nativo. */
@Composable
private fun InboxPill(count: Int, onClick: () -> Unit) {
    val palette = LocalPalette.current
    val label = stringResource(R.string.home_inbox_pill, count)
    Surface(
        onClick = onClick,
        shape = RoundedCornerShape(50),
        color = palette["amber-50"],
        border = BorderStroke(1.dp, palette.warning.copy(alpha = 0.35f)),
        modifier = Modifier.heightIn(min = 48.dp).semantics { contentDescription = label },
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(horizontal = 12.dp)) {
            Icon(AppIcons.BellRing, contentDescription = null, tint = palette["amber-800"], modifier = Modifier.size(16.dp))
            Text(
                text = count.toString(),
                color = palette["amber-800"],
                fontWeight = FontWeight.SemiBold,
                fontSize = 14.sp,
                modifier = Modifier.padding(start = 6.dp),
            )
        }
    }
}

// ---- Avisos do alto ----

@Composable
private fun Alerts(viewModel: HomeViewModel, onOpenWeb: (String) -> Unit) {
    val dismissLabel = stringResource(R.string.home_dismiss_error)
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (viewModel.dataError.isNotEmpty()) {
            AlertMessage(
                message = stringResource(R.string.home_error_banner, viewModel.dataError),
                tone = AlertTone.DANGER,
                dismissLabel = dismissLabel,
            )
        }
        // Sem copia e sem rede a caixa de erro ja diz "Sem conexão": um aviso so.
        if (viewModel.offline && viewModel.loadError.isEmpty()) {
            AlertMessage(message = stringResource(R.string.data_offline), tone = AlertTone.INFO, dismissLabel = dismissLabel)
        }
        val pending = viewModel.pendingInBalance
        if (pending > 0) {
            AlertMessage(message = HomeRules.estimateText(pending), tone = AlertTone.INFO, dismissLabel = dismissLabel)
        }
        viewModel.cachedAt?.let { stored ->
            Text(
                text = stringResource(R.string.data_updated_at, storedTimeLabel(stored)),
                style = MaterialTheme.typography.bodySmall,
                color = LocalPalette.current.muted,
            )
        }
    }
}

// ---- Saldo em conta ----

@Composable
private fun BalanceHero(view: HomeView, hidden: Boolean) {
    val palette = LocalPalette.current
    val title = stringResource(R.string.home_balance_title)
    Surface(
        shape = RoundedCornerShape(24.dp),
        color = palette.brand,
        contentColor = palette.brandInk,
        modifier = Modifier.fillMaxWidth().semantics { contentDescription = title },
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = title,
                    color = palette["brand-soft"],
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 14.sp,
                    modifier = Modifier.weight(1f),
                )
                Surface(shape = RoundedCornerShape(50), color = palette.brandInk.copy(alpha = 0.1f)) {
                    Text(
                        text = HomeRules.sentenceCase(monthLabel(monthKey())),
                        color = palette.brandInk,
                        fontWeight = FontWeight.SemiBold,
                        fontSize = 12.sp,
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 2.dp),
                    )
                }
            }
            FitText(
                text = if (hidden) HomeLogic.MASKED_CURRENCY else formatCurrency(view.consolidatedBalance),
                maxSize = 38.sp,
                minSize = 24.sp,
                color = palette.brandInk,
            )
            val strip = HomeLogic.stripAccounts(view.accounts)
            if (strip.isNotEmpty()) {
                LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(strip, key = { it.id }) { account -> AccountChip(account, hidden) }
                }
            }
        }
    }
}

@Composable
private fun AccountChip(account: HomeAccount, hidden: Boolean) {
    val palette = LocalPalette.current
    val balance = account.balanceBrl
    Surface(shape = RoundedCornerShape(16.dp), color = palette.brandInk.copy(alpha = 0.08f)) {
        Column(Modifier.widthIn(min = 136.dp, max = 220.dp).padding(horizontal = 12.dp, vertical = 8.dp)) {
            Text(
                text = account.name,
                color = palette["brand-soft"],
                fontSize = 12.sp,
                fontWeight = FontWeight.Medium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (balance == null) {
                Text(stringResource(R.string.home_no_rate), color = palette["brand-soft"], fontSize = 14.sp, fontWeight = FontWeight.Medium)
            } else {
                Text(
                    text = if (hidden) HomeLogic.MASKED_CURRENCY else formatCurrency(balance),
                    // A cor do negativo some no modo privado: senao o sinal vaza.
                    color = if (!hidden && balance.signum() < 0) palette["rose-200"] else palette.brandInk,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                )
            }
        }
    }
}

// ---- Resumo do mes ----

private data class SummaryRow(
    val label: String,
    val value: String,
    val hint: String,
    val color: Color,
    val lead: Boolean = false,
    val hintLink: String? = null,
)

@Composable
private fun MonthSummary(summary: HomeSummary, hidden: Boolean, onOpenWeb: (String) -> Unit) {
    val palette = LocalPalette.current
    val money = { value: BigDecimal -> if (hidden) HomeLogic.MASKED_CURRENCY else formatCurrency(value) }
    val result = summary.income - summary.expense
    val rows = mutableListOf(
        SummaryRow(
            label = stringResource(R.string.home_result),
            value = if (hidden) HomeLogic.MASKED_CURRENCY else formatSignedCurrency(result),
            hint = stringResource(R.string.home_result_hint),
            // No modo privado a cor sai junto, senao o sinal vaza.
            color = when {
                hidden -> palette.text
                result.signum() < 0 -> palette.loss
                else -> palette["emerald-700"]
            },
            lead = true,
        ),
        SummaryRow(stringResource(R.string.home_income), money(summary.income), stringResource(R.string.home_income_hint), palette.text),
        SummaryRow(stringResource(R.string.home_expense), money(summary.expense), stringResource(R.string.home_expense_hint), palette.text),
    )
    if (summary.invested.signum() != 0 || summary.redeemed.signum() != 0) {
        rows += SummaryRow(
            label = stringResource(R.string.home_invested),
            value = money(summary.invested - summary.redeemed),
            hint = stringResource(R.string.home_invested_hint, money(summary.invested), money(summary.redeemed)),
            color = palette.text,
        )
    }
    val others = summary.othersNet
    if (others.signum() != 0) {
        rows += SummaryRow(
            label = stringResource(if (others.signum() < 0) R.string.home_others_paid else R.string.home_others_received),
            value = money(others.abs()),
            hint = stringResource(R.string.home_others_link),
            color = palette.text,
            hintLink = "/lancamentos/a-receber",
        )
    }
    Panel {
        Column(Modifier.padding(20.dp)) {
            Text(stringResource(R.string.home_summary_title), color = palette["zinc-600"], fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
            Spacer(Modifier.height(8.dp))
            rows.forEachIndexed { index, row ->
                if (index > 0) HorizontalDivider(color = palette["zinc-100"])
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.fillMaxWidth().padding(vertical = 10.dp),
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(row.label, color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                        val link = row.hintLink
                        if (link != null) {
                            Text(
                                text = row.hint,
                                color = palette["emerald-700"],
                                fontWeight = FontWeight.SemiBold,
                                fontSize = 12.sp,
                                modifier = Modifier.clickable { onOpenWeb(link) }.padding(vertical = 4.dp),
                            )
                        } else {
                            Text(row.hint, color = palette.muted, fontSize = 12.sp)
                        }
                    }
                    Text(
                        text = row.value,
                        color = row.color,
                        fontWeight = if (row.lead) FontWeight.ExtraBold else FontWeight.Bold,
                        fontSize = if (row.lead) 20.sp else 15.sp,
                        maxLines = 1,
                        modifier = Modifier.padding(start = 12.dp),
                    )
                }
            }
        }
    }
}

// ---- Proxima fatura ----

@Composable
private fun NextInvoiceTile(home: HomeDto, onOpenWeb: (String) -> Unit) {
    val palette = LocalPalette.current
    val months = HomeLogic.nextInvoiceMonths(home.nextInvoices)
    val payable = home.nextInvoices.any { it.payable }
    Panel(onClick = { onOpenWeb("/lancamentos/cartoes") }) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(20.dp)) {
            Box(
                contentAlignment = Alignment.Center,
                modifier = Modifier.size(48.dp).background(palette["emerald-100"], RoundedCornerShape(16.dp)),
            ) {
                Icon(AppIcons.CreditCard, contentDescription = null, tint = palette["emerald-800"], modifier = Modifier.size(20.dp))
            }
            Column(Modifier.weight(1f).padding(horizontal = 16.dp)) {
                Text(HomeRules.nextInvoiceLabel(months), color = palette["zinc-600"], fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                FitText(text = formatCurrency(home.nextInvoicesTotal), maxSize = 24.sp, minSize = 16.sp, color = palette.text)
            }
            val closing = home.nextClosingDate
            if (payable) {
                Badge(stringResource(R.string.home_invoice_closed), BadgeTone.WARNING)
            } else if (closing != null) {
                Column(horizontalAlignment = Alignment.End) {
                    Text(stringResource(R.string.home_invoice_closes), color = palette["zinc-600"], fontSize = 14.sp)
                    Text(HomeRules.closingDayMonth(closing), color = palette.text, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                }
            }
        }
    }
}

// ---- Precisa de atencao ----

@Composable
private fun NeedsAttention(
    items: List<br.financas.app.data.AttentionItemDto>,
    viewModel: HomeViewModel,
    onOpenWeb: (String) -> Unit,
) {
    val palette = LocalPalette.current
    val dismissLabel = stringResource(R.string.home_attention_dismiss)
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(AppIcons.BellRing, contentDescription = null, tint = palette["zinc-600"], modifier = Modifier.size(16.dp))
            Text(
                text = stringResource(R.string.home_attention_title, items.size),
                color = palette["zinc-600"],
                fontWeight = FontWeight.SemiBold,
                fontSize = 14.sp,
                modifier = Modifier.weight(1f).padding(start = 8.dp),
            )
            Surface(
                onClick = viewModel::dismissShown,
                shape = CircleShape,
                color = palette.background,
                modifier = Modifier.size(48.dp).semantics { contentDescription = dismissLabel },
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(AppIcons.X, contentDescription = null, tint = palette["zinc-700"], modifier = Modifier.size(18.dp))
                }
            }
        }
        items.forEach { item ->
            AttentionCard(item, viewModel, onOpenWeb)
        }
    }
}

@Composable
private fun AttentionCard(item: br.financas.app.data.AttentionItemDto, viewModel: HomeViewModel, onOpenWeb: (String) -> Unit) {
    val palette = LocalPalette.current
    val text = attentionTextOf(item, viewModel.hidden)
    val link = br.financas.app.rules.AttentionRules.attentionLink(item.kind)
    // Tres tipos tem uma acao na propria tela no lugar do link (a web: `actions` de AttentionCards).
    val hasAction = item.kind in ACTION_KINDS
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            ToneIcon(item.kind, item.tone)
            Column {
                Text(text.title, color = palette.text, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                if (text.detail.isNotEmpty()) {
                    Text(text.detail, color = palette["zinc-600"], fontSize = 14.sp, modifier = Modifier.padding(top = 4.dp))
                } else if (hasAction && link != null) {
                    // A recorrencia: o botao e "Lançar", o link fica no detalhe.
                    LinkText(link.label) { onOpenWeb(link.route) }
                }
            }
            when (item.kind) {
                br.financas.app.rules.AttentionRules.INVOICE_OVERDUE ->
                    AppButton(stringResource(R.string.home_pay), onClick = viewModel::openPayOverdue, loading = viewModel.paying)
                br.financas.app.rules.AttentionRules.INVOICE_PAYABLE ->
                    AppButton(stringResource(R.string.home_pay), onClick = viewModel::openPayPayable, loading = viewModel.paying)
                br.financas.app.rules.AttentionRules.RECURRING ->
                    AppButton(stringResource(R.string.home_run_recurring), onClick = viewModel::runRecurring, loading = viewModel.runningRecurring)
                else -> link?.let { target -> LinkText(target.label) { onOpenWeb(target.route) } }
            }
        }
    }
}

private val ACTION_KINDS = setOf(
    br.financas.app.rules.AttentionRules.INVOICE_OVERDUE,
    br.financas.app.rules.AttentionRules.INVOICE_PAYABLE,
    br.financas.app.rules.AttentionRules.RECURRING,
)

/** O texto de um aviso, com o saldo e o que falta mascarados no modo privado. */
private fun attentionTextOf(item: br.financas.app.data.AttentionItemDto, hidden: Boolean) =
    br.financas.app.rules.AttentionRules.attentionText(item.rule) { value ->
        if (hidden) HomeLogic.MASKED_CURRENCY else formatCurrency(value)
    }

@Composable
private fun LinkText(label: String, onClick: () -> Unit) {
    val palette = LocalPalette.current
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier.heightIn(min = 48.dp).clickable(onClick = onClick),
    ) {
        Text(label, color = palette["emerald-700"], fontWeight = FontWeight.Bold, fontSize = 14.sp)
        Icon(AppIcons.ChevronRight, contentDescription = null, tint = palette["emerald-700"], modifier = Modifier.size(16.dp))
    }
}

/** O icone do aviso na cor do tom: perigo (rosa), aviso (ambar), informacao (azul). */
@Composable
internal fun ToneIcon(kind: String, tone: String) {
    val palette = LocalPalette.current
    val (fill, ink) = when (tone) {
        "danger" -> palette["rose-100"] to palette["rose-700"]
        "warning" -> palette["amber-100"] to palette["amber-800"]
        "info" -> palette["sky-100"] to palette["sky-700"]
        else -> palette["zinc-100"] to palette["zinc-700"]
    }
    val icon = when (kind) {
        br.financas.app.rules.AttentionRules.INVOICE_OVERDUE, br.financas.app.rules.AttentionRules.INVOICE_PAYABLE -> AppIcons.CreditCard
        br.financas.app.rules.AttentionRules.AUTOPAY_SHORTFALL -> AppIcons.Wallet
        br.financas.app.rules.AttentionRules.RECURRING -> AppIcons.Repeat
        br.financas.app.rules.AttentionRules.OVER_BUDGET -> AppIcons.Target
        else -> AppIcons.Bell
    }
    Box(contentAlignment = Alignment.Center, modifier = Modifier.size(36.dp).background(fill, RoundedCornerShape(12.dp))) {
        Icon(icon, contentDescription = null, tint = ink, modifier = Modifier.size(16.dp))
    }
}

/** O titulo de um painel que leva para a tela do assunto (o PanelLink da web). */
@Composable
internal fun PanelTitleLink(title: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val palette = LocalPalette.current
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = modifier.heightIn(min = 48.dp).clickable(onClick = onClick),
    ) {
        Text(title, color = palette.text, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        Spacer(Modifier.width(4.dp))
        Icon(AppIcons.ChevronRight, contentDescription = null, tint = palette["zinc-400"], modifier = Modifier.size(16.dp))
    }
}
