package br.financas.app.ui.cartoes

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SheetValue
import androidx.compose.material3.Snackbar
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
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
import br.financas.app.core.formatCurrency
import br.financas.app.core.formatDateBR
import br.financas.app.core.formatSignedCurrency
import br.financas.app.data.CardInvoiceDto
import br.financas.app.data.InvoiceCardDto
import br.financas.app.data.InvoicePurchaseDto
import br.financas.app.rules.CardRules
import br.financas.app.rules.InvoiceStatus
import br.financas.app.rules.SharedRow
import br.financas.app.rules.Sharing
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AlertTone
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.AppIcons
import br.financas.app.ui.components.AppSheet
import br.financas.app.ui.components.AppTextField
import br.financas.app.ui.components.Badge
import br.financas.app.ui.components.BadgeTone
import br.financas.app.ui.components.ButtonVariant
import br.financas.app.ui.components.ConfirmDialog
import br.financas.app.ui.components.DateField
import br.financas.app.ui.components.EmptyState
import br.financas.app.ui.components.Field
import br.financas.app.ui.components.ListSkeleton
import br.financas.app.ui.components.MenuAction
import br.financas.app.ui.components.OverflowMenu
import br.financas.app.ui.components.Panel
import br.financas.app.ui.components.SelectField
import br.financas.app.ui.components.SelectOption
import br.financas.app.ui.home.HomeLogic
import br.financas.app.ui.lancamentos.AmountInput
import br.financas.app.ui.lancamentos.AttachmentsSheet
import br.financas.app.ui.lancamentos.LancamentosTab
import br.financas.app.ui.lancamentos.LancamentosTopBar
import br.financas.app.ui.lancamentos.ProjectionHeader
import br.financas.app.ui.lancamentos.ShareFields
import br.financas.app.ui.theme.LocalPalette

/**
 * Cartoes nativo (05-cartoes.md): pages/lancamentos/Cartoes.jsx, CardRefundSheet, CardShareSheet
 * e PayInvoiceSheet em Compose, sobre GET /api/cc-invoices.
 */
@Composable
fun CartoesScreen(
    viewModel: CartoesViewModel,
    onBack: () -> Unit,
    onTab: (LancamentosTab) -> Unit,
    onOpenWeb: (String) -> Unit,
    onNewPurchase: () -> Unit,
) {
    val palette = LocalPalette.current
    val snackbar = remember { SnackbarHostState() }
    val haptic = LocalHapticFeedback.current
    val lifecycleOwner = LocalLifecycleOwner.current

    LaunchedEffect(lifecycleOwner) {
        lifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) { viewModel.refreshAll() }
    }
    LaunchedEffect(Unit) {
        viewModel.notices.collect { message ->
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
        topBar = {
            LancamentosTopBar(
                title = stringResource(R.string.cartoes_title),
                current = LancamentosTab.CARTOES,
                hidden = viewModel.hidden,
                onBack = onBack,
                onToggleHidden = viewModel::toggleHidden,
                onTab = onTab,
            )
        },
    ) { padding ->
        val data = viewModel.data
        val cards = viewModel.invoiceCards
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 32.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item(key = "intro") { Intro(viewModel, onNewPurchase) }
            item(key = "alerts") {
                val dismiss = stringResource(R.string.lanc_dismiss)
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (viewModel.offline) AlertMessage(message = viewModel.offlineText, tone = AlertTone.WARNING, dismissLabel = dismiss)
                    AlertMessage(message = viewModel.loadError, tone = AlertTone.WARNING, dismissLabel = dismiss)
                    AlertMessage(message = viewModel.actionError, tone = AlertTone.WARNING, dismissLabel = dismiss, onDismiss = viewModel::dismissActionError)
                }
            }
            item(key = "header") {
                viewModel.header?.let { (balance, next, global) -> ProjectionHeader(balance, next, global, viewModel.hidden) }
            }
            when {
                data == null || viewModel.cards == null -> item(key = "skeleton") { ListSkeleton(rows = 4) }
                viewModel.creditCards.isEmpty() && cards.isEmpty() -> item(key = "no-cards") {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        EmptyState(
                            title = stringResource(R.string.cartoes_no_cards_title),
                            message = stringResource(R.string.cartoes_no_cards_message),
                        )
                        AppButton(
                            text = stringResource(R.string.cartoes_no_cards_link),
                            onClick = { onOpenWeb("/ajustes#cartoes") },
                            variant = ButtonVariant.SECONDARY,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                }
                cards.isEmpty() -> item(key = "empty") {
                    EmptyState(title = stringResource(R.string.cartoes_empty_title), message = stringResource(R.string.cartoes_empty_message))
                }
                else -> items(cards, key = { it.cardId }) { card -> CardPanel(card, viewModel) }
            }
        }
    }

    viewModel.paying?.let { PaySheet(it, viewModel) }
    viewModel.refund?.let { RefundSheet(it, viewModel) }
    viewModel.share?.let { ShareSheet(it, viewModel) }
    AttachmentsSheet(viewModel.attachments)
    ConfirmDialog(request = viewModel.confirm, cancelLabel = stringResource(R.string.lanc_cancel), onDismiss = viewModel::dismissConfirm)
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Intro(viewModel: CartoesViewModel, onNewPurchase: () -> Unit) {
    val palette = LocalPalette.current
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(
            CardRules.headerDescription(viewModel.invoiceCards, viewModel.data?.openTotal ?: java.math.BigDecimal.ZERO),
            color = palette.muted,
            fontSize = 14.sp,
        )
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            AppButton(text = stringResource(R.string.cartoes_new_purchase), onClick = onNewPurchase, variant = ButtonVariant.SECONDARY)
            if (viewModel.creditCards.isNotEmpty()) {
                AppButton(text = stringResource(R.string.cartoes_refund), onClick = { viewModel.openRefund(null, null) }, variant = ButtonVariant.SECONDARY)
            }
            // "Pagar fatura" so quando a mais proxima ja fechou.
            if (viewModel.nearest?.second?.closed == true) {
                AppButton(text = stringResource(R.string.cartoes_pay_nearest), onClick = viewModel::openPayNearest)
            }
        }
    }
}

@Composable
private fun CardPanel(card: InvoiceCardDto, viewModel: CartoesViewModel) {
    val palette = LocalPalette.current
    val current = card.invoices.filter { !it.future }
    val future = card.invoices.filter { it.future }
    Panel {
        Column {
            Row(Modifier.padding(start = 16.dp, end = 16.dp, top = 16.dp, bottom = 10.dp), verticalAlignment = Alignment.Top) {
                Column(Modifier.weight(1f)) {
                    Text(card.cardName, color = palette.text, fontWeight = FontWeight.Bold, fontSize = 18.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(CardRules.cardSubtitle(card, viewModel.accountName(card.autopayAccountId)), color = palette.muted, fontSize = 13.sp)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(stringResource(R.string.cartoes_open), color = palette.muted, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                    Text(formatCurrency(card.total), color = palette.text, fontWeight = FontWeight.Bold, fontSize = 18.sp)
                }
            }
            current.forEach { invoice ->
                HorizontalDivider(color = palette["zinc-100"])
                InvoiceBlock(card, invoice, viewModel, future = false)
            }
            if (future.isNotEmpty()) {
                HorizontalDivider(color = palette["zinc-100"])
                val open = card.cardId in viewModel.futureOpen
                val last = future.last()
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { viewModel.toggleFuture(card.cardId) }
                        .heightIn(min = 48.dp)
                        .padding(horizontal = 16.dp, vertical = 8.dp),
                ) {
                    Chevron(open)
                    Text(
                        "${CardRules.futureLabel(future)} · ${stringResource(R.string.cartoes_until, CardRules.formatInvoiceLabel(last.invoiceMonth, last.invoiceYear))}",
                        color = palette["zinc-600"],
                        fontWeight = FontWeight.SemiBold,
                        fontSize = 14.sp,
                        modifier = Modifier.weight(1f),
                    )
                    Text(formatCurrency(CardRules.futureTotal(future)), color = palette["zinc-600"], fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                }
                if (open) {
                    Column(Modifier.background(palette.background)) {
                        future.forEach { invoice ->
                            HorizontalDivider(color = palette["zinc-100"])
                            InvoiceBlock(card, invoice, viewModel, future = true)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun Chevron(open: Boolean) {
    val palette = LocalPalette.current
    Icon(AppIcons.ChevronDown, contentDescription = null, tint = palette.muted, modifier = Modifier.size(20.dp).rotate(if (open) 180f else 0f))
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun InvoiceBlock(card: InvoiceCardDto, invoice: CardInvoiceDto, viewModel: CartoesViewModel, future: Boolean) {
    val palette = LocalPalette.current
    val expanded = viewModel.isExpanded(card, invoice)
    val hint = CardRules.paymentHint(invoice, card.autopayAccountId, future)
    Column {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier.fillMaxWidth().padding(start = 16.dp, end = 12.dp, top = 6.dp, bottom = 6.dp),
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                modifier = Modifier.weight(1f).heightIn(min = 48.dp).clickable { viewModel.toggle(card, invoice) },
            ) {
                Chevron(expanded)
                Column(Modifier.weight(1f)) {
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(CardRules.formatInvoiceLabel(invoice.invoiceMonth, invoice.invoiceYear), color = palette.text, fontWeight = FontWeight.SemiBold)
                        StatusBadge(invoice, future)
                        if (invoice.nearest) Badge(stringResource(R.string.cartoes_badge_nearest))
                    }
                    Text(formatCurrency(invoice.total), color = palette.text, fontWeight = FontWeight.SemiBold)
                    if (hint != null) Text(hint, color = palette.muted, fontSize = 12.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
            }
            if (CardRules.canPay(invoice)) {
                AppButton(
                    text = stringResource(R.string.cartoes_pay),
                    onClick = { viewModel.openPay(card, invoice) },
                    variant = if (invoice.nearest) ButtonVariant.PRIMARY else ButtonVariant.SECONDARY,
                )
            }
        }
        if (expanded) {
            Column(Modifier.padding(start = 12.dp, end = 4.dp, bottom = 10.dp)) {
                invoice.purchases.forEachIndexed { index, purchase ->
                    if (index > 0) HorizontalDivider(color = palette["zinc-100"])
                    PurchaseRow(purchase, card, viewModel)
                }
            }
        }
    }
}

@Composable
private fun StatusBadge(invoice: CardInvoiceDto, future: Boolean) {
    val palette = LocalPalette.current
    val status = CardRules.invoiceStatus(invoice)
    if (status == InvoiceStatus.CREDIT) {
        androidx.compose.material3.Surface(shape = androidx.compose.foundation.shape.RoundedCornerShape(50), color = palette["emerald-50"]) {
            Text(stringResource(R.string.cartoes_badge_credit), color = palette["emerald-700"], fontWeight = FontWeight.SemiBold, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp))
        }
        return
    }
    if (future) return
    when (status) {
        InvoiceStatus.PAST_DUE -> Badge(stringResource(R.string.cartoes_badge_past_due), BadgeTone.DANGER)
        InvoiceStatus.CLOSED -> Badge(stringResource(R.string.cartoes_badge_closed), BadgeTone.WARNING)
        else -> Badge(stringResource(R.string.cartoes_badge_open))
    }
}

@Composable
private fun PurchaseRow(purchase: InvoicePurchaseDto, card: InvoiceCardDto, viewModel: CartoesViewModel) {
    val palette = LocalPalette.current
    val receipts = if (purchase.attachmentCount > 0) stringResource(R.string.attach_menu_count, purchase.attachmentCount) else stringResource(R.string.attach_menu)
    val actions = if (purchase.isRefund) {
        listOf(
            MenuAction(receipts) { viewModel.openAttachments(purchase) },
            MenuAction(stringResource(R.string.cartoes_menu_delete_refund)) { viewModel.askDelete(purchase) },
        )
    } else {
        listOf(
            MenuAction(stringResource(R.string.cartoes_menu_refund)) { viewModel.openRefund(purchase, card.cardId) },
            MenuAction(stringResource(R.string.cartoes_menu_share)) { viewModel.openShare(purchase) },
            MenuAction(receipts) { viewModel.openAttachments(purchase) },
            MenuAction(CardRules.deletePurchaseLabel(purchase.installmentTotal)) { viewModel.askDelete(purchase) },
        )
    }
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp).padding(start = 8.dp, top = 6.dp, bottom = 6.dp),
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(purchase.description.orEmpty(), color = palette["zinc-900"], fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                if (purchase.attachmentCount > 0) Icon(AppIcons.Paperclip, contentDescription = null, tint = palette["zinc-400"], modifier = Modifier.size(14.dp))
            }
            val line = buildString {
                if (purchase.isRefund) append(stringResource(R.string.cartoes_refund_prefix))
                append(purchase.category?.takeIf { it.isNotEmpty() } ?: "Outros").append(" · ").append(formatDateBR(purchase.purchaseDate))
                if (purchase.installmentTotal > 1) append(" · ").append(stringResource(R.string.cartoes_installment, purchase.installmentCurrent, purchase.installmentTotal))
            }
            Text(line, color = palette.muted, fontSize = 12.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
            val share = Sharing.shareSummary(SharedRow(purchase.amount, purchase.shareMode, purchase.sharePerson, purchase.shareOthersAmount))
            if (share.isNotEmpty()) Text(share, color = palette.muted, fontSize = 12.sp, fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        if (purchase.isRefund) {
            Text(formatSignedCurrency(purchase.amount), color = palette["emerald-700"], fontWeight = FontWeight.SemiBold)
        } else {
            Text(formatCurrency(purchase.amount), color = palette.text, fontWeight = FontWeight.SemiBold)
        }
        OverflowMenu(actions = actions, label = stringResource(R.string.lanc_actions_of, purchase.description.orEmpty()))
    }
}

// ---- Sheets ----

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PaySheet(target: PayTarget, viewModel: CartoesViewModel) {
    val palette = LocalPalette.current
    val sheetState = rememberModalBottomSheetState(
        skipPartiallyExpanded = true,
        confirmValueChange = { value -> value != SheetValue.Hidden || !viewModel.payBusy },
    )
    val accounts = viewModel.payAccounts
    val selected = accounts.firstOrNull { it.id == viewModel.payAccountId }
    AppSheet(
        title = stringResource(R.string.cartoes_pay_title),
        sheetState = sheetState,
        onDismiss = viewModel::closePay,
        footer = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AppButton(stringResource(R.string.lanc_cancel), viewModel::closePay, Modifier.weight(1f), ButtonVariant.SECONDARY, enabled = !viewModel.payBusy)
                AppButton(
                    text = stringResource(R.string.home_pay_confirm, formatCurrency(target.invoice.total)),
                    onClick = viewModel::confirmPay,
                    loading = viewModel.payBusy,
                    modifier = Modifier.weight(1f),
                )
            }
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text(
                "${target.card.cardName} · ${CardRules.formatInvoiceLabel(target.invoice.invoiceMonth, target.invoice.invoiceYear)}",
                color = palette["zinc-600"],
                fontSize = 14.sp,
            )
            AlertMessage(message = viewModel.payError, dismissLabel = stringResource(R.string.lanc_dismiss))
            Field(stringResource(R.string.home_pay_account)) {
                SelectField(
                    value = viewModel.payAccountId,
                    options = accounts.map { SelectOption(it.id, HomeLogic.accountOptionLabel(it, viewModel.hidden)) },
                    onSelect = viewModel::choosePayAccount,
                )
            }
            if (selected != null && HomeLogic.shortfall(selected, target.invoice.total)) {
                AlertMessage(message = HomeLogic.shortfallText(selected, viewModel.hidden), tone = AlertTone.WARNING, dismissLabel = stringResource(R.string.lanc_dismiss))
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun RefundSheet(form: RefundForm, viewModel: CartoesViewModel) {
    val palette = LocalPalette.current
    val sheetState = rememberModalBottomSheetState(
        skipPartiallyExpanded = true,
        confirmValueChange = { value -> value != SheetValue.Hidden || !viewModel.refundBusy },
    )
    AppSheet(
        title = stringResource(R.string.cartoes_refund_title),
        sheetState = sheetState,
        onDismiss = viewModel::closeRefund,
        footer = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AppButton(stringResource(R.string.lanc_cancel), viewModel::closeRefund, Modifier.weight(1f), ButtonVariant.SECONDARY, enabled = !viewModel.refundBusy)
                AppButton(stringResource(R.string.cartoes_refund_save), viewModel::saveRefund, Modifier.weight(1f), loading = viewModel.refundBusy)
            }
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(
                form.purchase?.description ?: stringResource(R.string.cartoes_refund_description),
                color = palette["zinc-600"],
                fontSize = 14.sp,
            )
            AlertMessage(message = viewModel.refundError, dismissLabel = stringResource(R.string.lanc_dismiss))
            Field(stringResource(R.string.cartoes_refund_amount)) {
                AmountInput(form.amount, { viewModel.changeRefund(form.copy(amount = it)) }, stringResource(R.string.cartoes_refund_amount))
            }
            Field(stringResource(R.string.cartoes_refund_text)) {
                AppTextField(form.description, { viewModel.changeRefund(form.copy(description = it)) }, placeholder = stringResource(R.string.cartoes_refund_text_placeholder))
            }
            Field(stringResource(R.string.cartoes_refund_card)) {
                SelectField(
                    value = form.cardId,
                    options = viewModel.creditCards.map { SelectOption(it.id, it.name) },
                    // Aberto por uma compra: o cartao dela, travado.
                    onSelect = { if (form.purchase == null) viewModel.changeRefund(form.copy(cardId = it)) },
                )
            }
            Field(stringResource(R.string.cartoes_refund_date), hint = stringResource(R.string.cartoes_refund_date_hint)) {
                DateField(form.date, { viewModel.changeRefund(form.copy(date = it)) }, stringResource(R.string.lanc_date_ok), stringResource(R.string.lanc_cancel))
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ShareSheet(target: ShareTarget, viewModel: CartoesViewModel) {
    val palette = LocalPalette.current
    val sheetState = rememberModalBottomSheetState(
        skipPartiallyExpanded = true,
        confirmValueChange = { value -> value != SheetValue.Hidden || !viewModel.shareBusy },
    )
    AppSheet(
        title = stringResource(R.string.cartoes_share_title),
        sheetState = sheetState,
        onDismiss = viewModel::closeShare,
        footer = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AppButton(stringResource(R.string.lanc_cancel), viewModel::closeShare, Modifier.weight(1f), ButtonVariant.SECONDARY, enabled = !viewModel.shareBusy)
                AppButton(
                    stringResource(R.string.lanc_save),
                    viewModel::saveShare,
                    Modifier.weight(1f),
                    loading = viewModel.shareBusy,
                    enabled = target.start != null,
                )
            }
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(viewModel.shareDescription(target), color = palette["zinc-600"], fontSize = 14.sp)
            AlertMessage(message = viewModel.shareError, dismissLabel = stringResource(R.string.lanc_dismiss))
            ShareFields(target.form, viewModel::changeShare, enabled = target.start != null && !viewModel.shareBusy)
            Text(stringResource(R.string.cartoes_share_note), color = palette.muted, fontSize = 12.sp)
        }
    }
}
