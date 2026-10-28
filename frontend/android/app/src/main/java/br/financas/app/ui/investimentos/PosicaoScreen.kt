package br.financas.app.ui.investimentos

import android.app.Application
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.core.formatCurrency
import br.financas.app.core.formatDateBR
import br.financas.app.core.formatDecimal
import br.financas.app.core.formatPercent
import br.financas.app.core.formatQuantity
import br.financas.app.core.formatSignedCurrency
import br.financas.app.core.shortMonthLabel
import br.financas.app.data.PortfolioAssetDto
import br.financas.app.data.QuoteUpdateDto
import br.financas.app.data.SettlementDto
import br.financas.app.rules.BrokerSettlement
import br.financas.app.rules.FixedIncome
import br.financas.app.rules.HomeFlow
import br.financas.app.rules.Operations
import br.financas.app.rules.PortfolioView
import br.financas.app.rules.TreasuryLabels
import br.financas.app.ui.charts.BarColumn
import br.financas.app.ui.charts.DonutChart
import br.financas.app.ui.charts.StackedBarChart
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AlertTone
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.AppSheet
import br.financas.app.ui.components.AppTextField
import br.financas.app.ui.components.ButtonVariant
import br.financas.app.ui.components.ConfirmDialog
import br.financas.app.ui.components.DateField
import br.financas.app.ui.components.EmptyState
import br.financas.app.ui.components.Field
import br.financas.app.ui.components.ListSkeleton
import br.financas.app.ui.components.MenuAction
import br.financas.app.ui.components.OverflowMenu
import br.financas.app.ui.components.Panel
import br.financas.app.ui.components.SegmentedChoice
import br.financas.app.ui.components.SelectOption
import br.financas.app.ui.home.HomeLogic
import br.financas.app.ui.lancamentos.moneyOrMasked
import br.financas.app.ui.planejar.PlanejarScaffold
import br.financas.app.ui.planejar.SummaryPanel
import br.financas.app.ui.planejar.SummaryValue
import br.financas.app.ui.theme.LocalPalette
import java.math.BigDecimal

private const val MASKED_TEXT = "••••••"

/** Investimentos › Posicao nativo (12-investimentos-posicao.md): o ramo de celular de Posicao.jsx. */
@Composable
fun PosicaoScreen(viewModel: PosicaoViewModel, onBack: () -> Unit, onTab: (InvestimentosTab) -> Unit) {
    val palette = LocalPalette.current
    val app = LocalContext.current.applicationContext as Application
    val dismiss = stringResource(R.string.lanc_dismiss)
    val hidden = viewModel.hidden
    val assets = viewModel.assets
    PlanejarScaffold(
        notices = viewModel.notices,
        onRefresh = viewModel::refreshAll,
        topBar = {
            InvestimentosTopBar(stringResource(R.string.inv_posicao_title), InvestimentosTab.POSICAO, hidden, onBack, viewModel::toggleHidden, onTab)
        },
    ) {
        item(key = "intro") {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(stringResource(R.string.inv_posicao_description), fontSize = 14.sp, color = palette["zinc-600"])
                AppButton(stringResource(R.string.inv_register_operation), viewModel.launchSheet::openBuy, Modifier.fillMaxWidth())
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    AppButton(
                        stringResource(R.string.inv_update_quotes),
                        { viewModel.updatePrices() },
                        Modifier.weight(1f),
                        variant = ButtonVariant.SECONDARY,
                        loading = viewModel.updatingPrices,
                    )
                    AppButton(stringResource(R.string.inv_export), viewModel.export::show, Modifier.weight(1f), variant = ButtonVariant.SECONDARY, enabled = assets.isNotEmpty())
                }
            }
        }
        item(key = "alerts") {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (viewModel.portfolio.offline) AlertMessage(viewModel.portfolio.offlineText, AlertTone.WARNING, dismiss)
                AlertMessage(viewModel.portfolio.error, AlertTone.WARNING, dismiss)
                AlertMessage(viewModel.dataError, AlertTone.WARNING, dismiss, onDismiss = viewModel::dismissError)
                viewModel.quoteResult?.let { QuoteResultPanel(it, viewModel::closeQuoteResult) }
            }
        }
        val data = viewModel.portfolio.value
        if (data != null && assets.isNotEmpty()) {
            item(key = "summary") { PortfolioSummary(viewModel) }
        }
        // A Conta investimento logo abaixo do resumo (049), mesmo sem posicoes, como na web.
        viewModel.settlement?.let { settlement -> item(key = "settlement") { ContaInvestimento(settlement, hidden) } }
        if (data != null && assets.isNotEmpty()) {
            item(key = "allocation") { AllocationPanel(assets, hidden) }
            item(key = "evolution") { EvolutionPanel(viewModel) }
        }
        item(key = "tabs") {
            SegmentedChoice(
                items = listOf(
                    SelectOption(PortfolioView.Tab.VARIAVEL.name, stringResource(R.string.inv_tab_variable)),
                    SelectOption(PortfolioView.Tab.FIXA.name, stringResource(R.string.inv_tab_fixed)),
                    SelectOption(PortfolioView.Tab.TESOURO.name, stringResource(R.string.inv_tab_treasury)),
                ),
                value = viewModel.tab.name,
                onChange = { viewModel.selectTab(PortfolioView.Tab.valueOf(it)) },
            )
        }
        val tab = viewModel.tab
        val inTab = assets.filter { PortfolioView.inTab(PosicaoViewModel.positionOf(it), tab) }
        when {
            data == null && !viewModel.portfolio.loaded -> item(key = "loading") { Panel { ListSkeleton(rows = 6, modifier = Modifier.padding(16.dp)) } }
            data == null -> Unit
            inTab.isEmpty() -> item(key = "empty-$tab") {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    EmptyState(stringResource(R.string.inv_posicao_empty_title), stringResource(R.string.inv_posicao_empty_message))
                    AppButton(stringResource(R.string.inv_register_operation), viewModel.launchSheet::openBuy, Modifier.fillMaxWidth())
                }
            }
            else -> {
                val groups = PortfolioView.groupAssets(inTab, tab, PosicaoViewModel::positionOf)
                groups.forEach { group ->
                    item(key = "group-${tab}-${group.key}") {
                        GroupPanel(group, viewModel, tab)
                    }
                }
                if (tab == PortfolioView.Tab.TESOURO) item(key = "treasury-note") { TreasuryNote(inTab, dismiss) }
            }
        }
    }
    LaunchSheetView(viewModel.launchSheet, hidden, app)
    InvestExportSheet(viewModel.export, stringResource(R.string.inv_export_portfolio_title), stringResource(R.string.inv_export_portfolio_description))
    viewModel.quoteFor?.let { QuoteSheet(it, viewModel) }
    viewModel.redeem?.let { RedeemSheetView(it, viewModel) }
    viewModel.detailFor?.let { TreasuryDetailSheet(it, hidden, viewModel::closeDetail) }
    ConfirmDialog(viewModel.confirm, stringResource(R.string.lanc_cancel), viewModel::dismissConfirm)
}

@Composable
private fun PortfolioSummary(viewModel: PosicaoViewModel) {
    val data = viewModel.portfolio.value ?: return
    val hidden = viewModel.hidden
    val invested = data.totalInvested ?: BigDecimal.ZERO
    val value = data.currentBalance ?: BigDecimal.ZERO
    val result = value - invested
    // O percentual do servidor (gross_portfolio_profitability), o mesmo que a web calcula.
    val percent = data.grossProfitability
    val figures = listOf(
        SummaryValue(stringResource(R.string.inv_summary_invested), moneyOrMasked(invested, hidden), stringResource(R.string.inv_summary_invested_hint)),
        SummaryValue(
            stringResource(R.string.inv_summary_result),
            if (hidden) HomeLogic.MASKED_CURRENCY else formatSignedCurrency(result),
            stringResource(R.string.inv_summary_result_hint, formatPercent(percent, 2, signed = true)),
            loss = !hidden && result.signum() < 0,
        ),
        SummaryValue(stringResource(R.string.inv_summary_net), moneyOrMasked(data.currentNetBalance, hidden), stringResource(R.string.inv_summary_net_hint)),
    )
    SummaryPanel(
        lead = SummaryValue(stringResource(R.string.inv_summary_portfolio), moneyOrMasked(value, hidden), stringResource(R.string.inv_summary_portfolio_hint)),
        figures = figures,
    )
}

/**
 * A Conta investimento (ContaInvestimento.jsx, 049): o caixa da Corretora como a corretora o ve.
 * "Saldo hoje" e o que ja liquidou, "Em trânsito" o que vai liquidar (D+2 na B3) e os proventos
 * anunciados, "Saldo" o que sobra depois de tudo. O servidor faz a conta.
 */
@Composable
private fun ContaInvestimento(view: SettlementDto, hidden: Boolean) {
    val palette = LocalPalette.current
    val transit = view.inTransit
    val signed = { value: BigDecimal? -> if (hidden) HomeLogic.MASKED_CURRENCY else formatSignedCurrency(value) }
    val pluggy = view.pluggy
    val hint = when (val chosen = BrokerSettlement.hint(pluggy != null, pluggy?.balance, pluggy?.difference, view.accountName)) {
        BrokerSettlement.Hint.Matches -> stringResource(R.string.inv_settlement_matches)
        is BrokerSettlement.Hint.Broker -> stringResource(R.string.inv_settlement_broker, moneyOrMasked(chosen.balance, hidden), signed(chosen.difference))
        is BrokerSettlement.Hint.Account -> chosen.name
    }
    val tone = BrokerSettlement.transitTone(view.inTransitTotal, hidden)
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        SummaryPanel(
            lead = SummaryValue(stringResource(R.string.inv_settlement_today), moneyOrMasked(view.settled, hidden), hint.ifEmpty { null }),
            figures = listOf(
                SummaryValue(
                    stringResource(R.string.inv_settlement_transit),
                    signed(view.inTransitTotal),
                    if (transit.isNotEmpty()) stringResource(R.string.inv_settlement_transit_count, transit.size) else stringResource(R.string.inv_settlement_transit_none),
                    loss = tone == BrokerSettlement.Tone.LOSS,
                    gain = tone == BrokerSettlement.Tone.GAIN,
                ),
                SummaryValue(stringResource(R.string.inv_settlement_expected), moneyOrMasked(view.expected, hidden), stringResource(R.string.inv_settlement_expected_hint)),
            ),
        )
        if (transit.isNotEmpty()) {
            Panel {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    PanelTitle(stringResource(R.string.inv_settlement_list_title), stringResource(R.string.inv_settlement_list_description))
                    transit.forEachIndexed { index, item ->
                        if (index > 0) HorizontalDivider(color = palette["zinc-100"])
                        Row(
                            Modifier.fillMaxWidth().heightIn(min = 44.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                Text(item.description.orEmpty(), color = palette.text, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
                                Text(
                                    stringResource(
                                        if (BrokerSettlement.isPayment(item.kind)) R.string.inv_settlement_pays_on else R.string.inv_settlement_settles_on,
                                        formatDateBR(item.date),
                                    ),
                                    color = palette.muted,
                                    fontSize = 12.sp,
                                )
                            }
                            val amount = item.amount ?: BigDecimal.ZERO
                            Text(
                                signed(item.amount),
                                color = when {
                                    hidden -> palette.text
                                    amount.signum() >= 0 -> palette["emerald-700"]
                                    else -> palette["rose-700"]
                                },
                                fontSize = 14.sp,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                    }
                }
            }
        }
    }
}

/** As cores da rosca e das series: SERIES[i] por posicao, o resto OTHER_COLOR (chart-other = zinc-400). */
@Composable
internal fun seriesColor(index: Int) = LocalPalette.current.let { palette -> if (index in 0..7) palette["series-$index"] else palette["zinc-400"] }

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun AllocationPanel(assets: List<PortfolioAssetDto>, hidden: Boolean) {
    val palette = LocalPalette.current
    val slices = PortfolioView.donutSlices(PortfolioView.allocationByCategory(assets.map(PosicaoViewModel::positionOf)))
    val total = slices.fold(BigDecimal.ZERO) { acc, slice -> acc + slice.value }
    val colors = slices.map { seriesColor(it.colorIndex) }
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            PanelTitle(stringResource(R.string.inv_allocation_title), stringResource(R.string.inv_allocation_description))
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                DonutChart(slices.mapIndexed { index, slice -> slice.value.toDouble() to colors[index] })
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(stringResource(R.string.inv_allocation_center), color = palette.muted, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                    Text(moneyOrMasked(total, hidden), color = palette.text, fontSize = 15.sp, fontWeight = FontWeight.Bold)
                }
            }
            slices.forEachIndexed { index, slice ->
                val share = if (total.signum() > 0) slice.value.multiply(BigDecimal(100)).divide(total, 4, java.math.RoundingMode.HALF_UP) else BigDecimal.ZERO
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Box(Modifier.size(10.dp).background(colors[index], CircleShape))
                    Text(slice.name, color = palette["zinc-700"], fontSize = 14.sp, modifier = Modifier.weight(1f))
                    Text("${formatDecimal(share, 1)}%", color = palette.muted, fontSize = 13.sp)
                    Text(moneyOrMasked(slice.value, hidden), color = palette.text, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun EvolutionPanel(viewModel: PosicaoViewModel) {
    val palette = LocalPalette.current
    val hidden = viewModel.hidden
    val points = viewModel.history.value?.evolution.orEmpty()
    val bars = points.map { PortfolioView.evolutionBar(it.month.orEmpty(), it.valorAplicado, it.patrimonioBruto, it.patrimonio, it.ganhoCapitalBruto) }
    val hasLoss = bars.any { it.perda.signum() > 0 }
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            PanelTitle(stringResource(R.string.inv_evolution_title), stringResource(R.string.inv_evolution_description))
            PeriodChips(PosicaoViewModel.PERIODS, viewModel.months.toString()) { viewModel.changeMonths(it.toInt()) }
            if (viewModel.history.error.isNotEmpty() || (viewModel.history.offline && points.isEmpty())) {
                AlertMessage(stringResource(R.string.inv_history_failed), AlertTone.WARNING, stringResource(R.string.lanc_dismiss))
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                LegendDot(palette["flow-investment"], stringResource(R.string.inv_legend_applied))
                LegendDot(palette["flow-income"], stringResource(R.string.inv_legend_gain))
                if (hasLoss) LegendDot(palette["flow-expense"], stringResource(R.string.inv_legend_loss))
            }
            if (bars.isEmpty() && !viewModel.history.loaded) {
                ListSkeleton(rows = 1)
            } else {
                StackedBarChart(
                    columns = bars.map { bar ->
                        BarColumn(
                            shortMonthLabel(bar.month),
                            listOf(
                                bar.base.toDouble() to palette["flow-investment"],
                                bar.ganho.toDouble() to palette["flow-income"],
                                bar.perda.toDouble() to palette["flow-expense"],
                            ),
                            null,
                        )
                    },
                    lineColor = palette["zinc-900"],
                    tickLabel = { if (hidden) "" else HomeFlow.compactAxis(BigDecimal.valueOf(it)) },
                    selected = viewModel.selectedMonth,
                    onSelect = viewModel::selectMonth,
                    maxBarWidth = 32.dp,
                )
                viewModel.selectedMonth?.let { index -> bars.getOrNull(index) }?.let { bar ->
                    Column(
                        Modifier.fillMaxWidth().background(palette["zinc-50"], androidx.compose.foundation.shape.RoundedCornerShape(12.dp)).padding(12.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        Text(shortMonthLabel(bar.month), color = palette.text, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                        DetailFigure(stringResource(R.string.inv_legend_applied), moneyOrMasked(bar.applied, hidden))
                        DetailFigure(
                            stringResource(if (bar.gain.signum() >= 0) R.string.inv_legend_gain else R.string.inv_legend_loss),
                            moneyOrMasked(bar.gain.abs(), hidden),
                        )
                        Text(stringResource(R.string.inv_evolution_gross, moneyOrMasked(bar.patrimonio, hidden)), color = palette.muted, fontSize = 12.sp)
                        if (bar.patrimonioLiquido.compareTo(bar.patrimonio) != 0) {
                            Text(stringResource(R.string.inv_evolution_net, moneyOrMasked(bar.patrimonioLiquido, hidden)), color = palette.muted, fontSize = 12.sp)
                        }
                    }
                }
            }
        }
    }
}

@Composable
internal fun PanelTitle(title: String, description: String? = null) {
    val palette = LocalPalette.current
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(title, color = palette.text, fontWeight = FontWeight.ExtraBold, fontSize = 17.sp)
        if (!description.isNullOrEmpty()) Text(description, color = palette.muted, fontSize = 13.sp)
    }
}

@Composable
private fun QuoteResultPanel(result: QuoteUpdateDto, onClose: () -> Unit) {
    val palette = LocalPalette.current
    fun names(list: List<br.financas.app.data.QuoteAssetDto>) = list.joinToString(", ") { it.ticker ?: it.name.orEmpty() }
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(stringResource(R.string.inv_quotes_result_title), color = palette.text, fontWeight = FontWeight.Bold)
                    Text(
                        stringResource(R.string.inv_quotes_result_summary, result.updatedAssets.size, result.failedAssets.size, result.staleAssets.size),
                        color = palette.muted,
                        fontSize = 13.sp,
                    )
                }
                AppButton(stringResource(R.string.inv_close), onClose, variant = ButtonVariant.SUBTLE)
            }
            if (result.updatedAssets.isNotEmpty()) Text(stringResource(R.string.inv_quotes_updated, names(result.updatedAssets)), color = palette["emerald-700"], fontSize = 13.sp)
            if (result.cachedAssets.isNotEmpty()) Text(stringResource(R.string.inv_quotes_cached, names(result.cachedAssets)), color = palette["amber-800"], fontSize = 13.sp)
            // Uma linha por motivo: um tempo limite do provedor nao se repete ticker a ticker.
            result.failedAssets.groupBy { it.error ?: "sem detalhe" }.forEach { (error, assets) ->
                Text(stringResource(R.string.inv_quotes_failed_list, error, names(assets)), color = palette["rose-700"], fontSize = 13.sp)
            }
            if (result.staleAssets.isNotEmpty()) Text(stringResource(R.string.inv_quotes_stale, names(result.staleAssets)), color = palette["zinc-600"], fontSize = 13.sp)
        }
    }
}

@Composable
private fun GroupPanel(group: PortfolioView.Group<PortfolioAssetDto>, viewModel: PosicaoViewModel, tab: PortfolioView.Tab) {
    val palette = LocalPalette.current
    val open = group.key in viewModel.openGroups
    val count = group.items.size
    Panel {
        Column {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 52.dp)
                    .clickable { viewModel.toggleGroup(group.key) }
                    .padding(horizontal = 16.dp, vertical = 10.dp),
            ) {
                Text(if (open) "▾" else "▸", color = palette.muted, modifier = Modifier.padding(end = 8.dp))
                Text(group.label.uppercase(), color = palette["zinc-600"], fontWeight = FontWeight.SemiBold, fontSize = 12.sp, modifier = Modifier.weight(1f))
                Text(
                    stringResource(if (count == 1) R.string.inv_group_one else R.string.inv_group_many, count, moneyOrMasked(group.total, viewModel.hidden)),
                    color = palette.muted,
                    fontSize = 12.sp,
                )
            }
            if (open) {
                group.items.forEach { asset ->
                    HorizontalDivider(color = palette.border)
                    if (tab == PortfolioView.Tab.TESOURO) TreasuryCard(asset, viewModel) else PositionCard(asset, viewModel)
                }
            }
        }
    }
}

@Composable
private fun QuoteValue(asset: PortfolioAssetDto, viewModel: PosicaoViewModel) {
    val palette = LocalPalette.current
    val quote = asset.quote
    val status = quote?.status ?: "missing"
    val fixed = asset.assetClass == "FIXED_INCOME"
    val masked = viewModel.hidden && fixed && !TreasuryLabels.isMarketValued(treasuryPosition(asset))
    val updatingThis = viewModel.updatingAssetId == (asset.assetId ?: asset.id) && viewModel.updatingAssetId.isNotEmpty()
    val statusText = "${PortfolioView.quoteStatusLabel(status)} · ${PortfolioView.quoteSourceLabel(quote?.source)} · ${PortfolioView.formatDateTime(quote?.quotedAt)}"
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        modifier = Modifier.semantics { contentDescription = statusText },
    ) {
        if (updatingThis) {
            CircularProgressIndicator(Modifier.size(12.dp), strokeWidth = 2.dp, color = palette.muted)
        } else {
            Box(Modifier.size(8.dp).background(if (status == "fresh") palette.accent else palette["amber-500"], CircleShape))
        }
        Text(if (masked) HomeLogic.MASKED_CURRENCY else formatCurrency(asset.currentPrice), color = palette["zinc-700"], fontSize = 14.sp)
    }
}

private fun treasuryPosition(asset: PortfolioAssetDto): TreasuryLabels.Position = TreasuryLabels.Position(
    metadata = Operations.fixedIncomeMetadata(asset.metadata),
    treasury = asset.treasury?.let {
        TreasuryLabels.Treasury(
            averageRate = it.averageRate?.toDouble(),
            lotCount = it.lotCount,
            marketRate = it.marketRate?.toDouble(),
            titleType = it.titleType,
            valuation = it.valuation,
        )
    },
)

@Composable
private fun positionMenu(asset: PortfolioAssetDto, viewModel: PosicaoViewModel): List<MenuAction> {
    val items = PortfolioView.menuItems(PosicaoViewModel.positionOf(asset), viewModel.updatingPrices)
    return items.map { item ->
        when (item) {
            PortfolioView.MenuItem.DETAILS -> MenuAction(stringResource(R.string.inv_menu_details)) { viewModel.openDetail(asset) }
            PortfolioView.MenuItem.EDIT_QUOTE -> MenuAction(stringResource(R.string.inv_menu_edit_quote)) { viewModel.openQuote(asset) }
            PortfolioView.MenuItem.REFRESH_QUOTE -> MenuAction(stringResource(R.string.inv_menu_refresh_quote)) { viewModel.updatePrices(asset) }
            PortfolioView.MenuItem.REFRESH_VALUE -> MenuAction(stringResource(R.string.inv_menu_refresh_value)) { viewModel.updatePrices(asset) }
            PortfolioView.MenuItem.DELETE_CONTRIBUTION -> MenuAction(stringResource(R.string.inv_menu_delete_contribution)) { viewModel.askDelete(asset) }
            PortfolioView.MenuItem.DELETE_POSITION -> MenuAction(stringResource(R.string.inv_menu_delete_position)) { viewModel.askDelete(asset) }
        }
    }
}

@Composable
private fun PositionCard(asset: PortfolioAssetDto, viewModel: PosicaoViewModel) {
    val palette = LocalPalette.current
    val hidden = viewModel.hidden
    val fixed = asset.assetClass == "FIXED_INCOME"
    val metadata = Operations.fixedIncomeMetadata(asset.metadata)
    Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Column(Modifier.weight(1f)) {
                // Sem cortar: o nome do titulo quebra, nunca vira "PETR…".
                Text(asset.name.orEmpty(), color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
                val first = if (fixed) {
                    FixedIncome.describeFixedIncome(metadata).ifEmpty { PortfolioView.classLabel(asset.assetClass) }
                } else {
                    "${if (hidden) MASKED_TEXT else formatQuantity(asset.quantity)} un."
                }
                val pm = if (hidden && fixed) HomeLogic.MASKED_CURRENCY else formatCurrency(asset.averagePrice)
                Text("$first · PM $pm", color = palette.muted, fontSize = 12.sp, maxLines = 1)
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(moneyOrMasked(asset.currentValue, hidden), color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
                ProfitText(asset.profitabilityPercent)
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(stringResource(R.string.inv_position_proceeds, moneyOrMasked(asset.proceedsNet, hidden)), color = palette["zinc-600"], fontSize = 12.sp, modifier = Modifier.weight(1f))
            Text(stringResource(R.string.inv_position_with_proceeds), color = palette["zinc-600"], fontSize = 12.sp)
            ProfitText(asset.totalReturnPercent, fontSize = 12, modifier = Modifier.padding(start = 4.dp))
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(Modifier.weight(1f)) { QuoteValue(asset, viewModel) }
            AppButton(
                stringResource(if (fixed) R.string.inv_redeem else R.string.inv_sell),
                { if (fixed) viewModel.openRedeem(asset) else viewModel.launchSheet.openSell(asset) },
                variant = ButtonVariant.SECONDARY,
            )
            OverflowMenu(positionMenu(asset, viewModel), stringResource(R.string.inv_more_actions, asset.name.orEmpty()))
        }
    }
}

private fun formatUnits(value: BigDecimal?): String = br.financas.app.rules.ptBrNumber((value ?: BigDecimal.ZERO).toDouble(), 2, 2)

@Composable
private fun TreasuryCard(asset: PortfolioAssetDto, viewModel: PosicaoViewModel) {
    val palette = LocalPalette.current
    val hidden = viewModel.hidden
    val treasury = asset.treasury
    val facts = listOfNotNull(
        treasury?.maturityDate?.let { stringResource(R.string.inv_treasury_maturity, formatDateBR(it)) },
        treasury?.units?.let { stringResource(R.string.inv_treasury_units, if (hidden) MASKED_TEXT else formatUnits(it)) },
    ).joinToString(" · ")
    val rate = TreasuryLabels.treasuryRateLabel(treasuryPosition(asset)).ifEmpty { FixedIncome.describeFixedIncome(Operations.fixedIncomeMetadata(asset.metadata)) }
    Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Column(Modifier.weight(1f)) {
                Text(asset.name.orEmpty(), color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
                if (facts.isNotEmpty()) Text(facts, color = palette.muted, fontSize = 12.sp)
                if (rate.isNotEmpty()) Text(rate, color = palette.muted, fontSize = 12.sp)
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(moneyOrMasked(asset.netValue, hidden), color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
                Text(stringResource(R.string.inv_treasury_gross, moneyOrMasked(asset.currentValue, hidden)), color = palette.muted, fontSize = 12.sp)
                ProfitText(asset.profitabilityPercent)
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(Modifier.weight(1f)) { QuoteValue(asset, viewModel) }
            AppButton(stringResource(R.string.inv_redeem), { viewModel.openRedeem(asset) }, variant = ButtonVariant.SECONDARY)
            OverflowMenu(positionMenu(asset, viewModel), stringResource(R.string.inv_more_actions, asset.name.orEmpty()))
        }
    }
}

@Composable
private fun TreasuryNote(assets: List<PortfolioAssetDto>, dismiss: String) {
    val palette = LocalPalette.current
    val onCurve = assets.filter { !TreasuryLabels.isMarketValued(treasuryPosition(it)) }
    val priceDate = assets.mapNotNull { it.treasury?.priceDate?.takeIf { date -> date.isNotEmpty() } }.maxOrNull()
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (priceDate != null) Text(stringResource(R.string.inv_treasury_source, formatDateBR(priceDate)), color = palette.muted, fontSize = 12.sp)
        if (onCurve.isNotEmpty()) {
            AlertMessage(stringResource(R.string.inv_treasury_on_curve, onCurve.joinToString(", ") { it.name.orEmpty() }), AlertTone.INFO, dismiss)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun QuoteSheet(asset: PortfolioAssetDto, viewModel: PosicaoViewModel) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val palette = LocalPalette.current
    AppSheet(
        title = stringResource(R.string.inv_quote_title),
        sheetState = sheetState,
        onDismiss = viewModel::closeQuote,
        footer = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AppButton(stringResource(R.string.lanc_cancel), viewModel::closeQuote, Modifier.weight(1f), variant = ButtonVariant.SECONDARY)
                AppButton(stringResource(R.string.inv_quote_save), viewModel::saveQuote, Modifier.weight(1f), loading = viewModel.quoteSaving)
            }
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(
                "${asset.name.orEmpty()} · ${PortfolioView.quoteSourceLabel(asset.quote?.source)}, ${PortfolioView.formatDateTime(asset.quote?.quotedAt)}",
                color = palette["zinc-600"],
                fontSize = 14.sp,
            )
            AlertMessage(viewModel.quoteError, AlertTone.DANGER, stringResource(R.string.lanc_dismiss))
            Field(stringResource(R.string.inv_quote_field), hint = stringResource(R.string.inv_quote_hint)) {
                br.financas.app.ui.lancamentos.AmountInput(viewModel.quoteText, viewModel::changeQuote, stringResource(R.string.inv_quote_field))
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun RedeemSheetView(sheet: RedeemSheet, viewModel: PosicaoViewModel) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val palette = LocalPalette.current
    val cancel = stringResource(R.string.lanc_cancel)
    AppSheet(
        title = stringResource(R.string.inv_redeem_title),
        sheetState = sheetState,
        onDismiss = viewModel::closeRedeem,
        footer = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AppButton(cancel, viewModel::closeRedeem, Modifier.weight(1f), variant = ButtonVariant.SECONDARY)
                AppButton(stringResource(R.string.inv_redeem_save), viewModel::saveRedeem, Modifier.weight(1f), loading = viewModel.redeemSaving)
            }
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text(
                stringResource(R.string.inv_redeem_description, sheet.asset.name.orEmpty(), moneyOrMasked(sheet.asset.currentValue, viewModel.hidden)),
                color = palette["zinc-600"],
                fontSize = 14.sp,
            )
            AlertMessage(viewModel.redeemError, AlertTone.DANGER, stringResource(R.string.lanc_dismiss))
            Field(
                stringResource(R.string.inv_redeem_amount),
                hint = stringResource(if (sheet.asset.lots.size > 1) R.string.inv_redeem_hint_grouped else R.string.inv_redeem_hint_single),
            ) {
                br.financas.app.ui.lancamentos.AmountInput(sheet.amount, { viewModel.changeRedeem(sheet.copy(amount = it)) }, stringResource(R.string.inv_redeem_amount))
            }
            Field(stringResource(R.string.inv_redeem_date_label)) {
                DateField(sheet.date, { viewModel.changeRedeem(sheet.copy(date = it)) }, stringResource(R.string.lanc_date_ok), cancel)
            }
            CashLinkField(sheet.cashLink, { viewModel.changeRedeem(sheet.copy(cashLink = it)) }, viewModel.accounts.value, "REDEMPTION")
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TreasuryDetailSheet(asset: PortfolioAssetDto, hidden: Boolean, onClose: () -> Unit) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val palette = LocalPalette.current
    val treasury = asset.treasury
    val position = treasuryPosition(asset)
    val metadata = position.metadata
    val marketRate = TreasuryLabels.treasuryMarketRateText(position)
    val context = LocalContext.current
    val units = { value: BigDecimal? -> context.getString(R.string.inv_treasury_units, if (hidden) MASKED_TEXT else formatUnits(value)) }
    AppSheet(
        title = asset.name ?: stringResource(R.string.inv_treasury_title_fallback),
        sheetState = sheetState,
        onDismiss = onClose,
        footer = { AppButton(stringResource(R.string.inv_close), onClose, Modifier.fillMaxWidth(), variant = ButtonVariant.SECONDARY) },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            treasury?.maturityDate?.let { Text(stringResource(R.string.inv_treasury_matures, formatDateBR(it)), color = palette["zinc-600"], fontSize = 14.sp) }
            if (treasury?.valuation != "MARKET") {
                AlertMessage(stringResource(R.string.inv_treasury_detail_curve), AlertTone.INFO, stringResource(R.string.lanc_dismiss))
            }
            Column {
                DetailFigure(stringResource(R.string.inv_treasury_gross_balance), moneyOrMasked(asset.currentValue, hidden), treasury?.units?.let { units(it) })
                DetailFigure(stringResource(R.string.inv_treasury_custody), moneyOrMasked(treasury?.custody, hidden), stringResource(R.string.inv_treasury_custody_hint))
                if ((treasury?.iof ?: BigDecimal.ZERO).signum() > 0) DetailFigure(stringResource(R.string.inv_treasury_iof), moneyOrMasked(treasury?.iof, hidden))
                DetailFigure(stringResource(R.string.inv_treasury_ir), moneyOrMasked(treasury?.incomeTax, hidden), stringResource(R.string.inv_treasury_ir_hint))
                DetailFigure(stringResource(R.string.inv_treasury_net_balance), moneyOrMasked(asset.netValue, hidden))
                DetailFigure(stringResource(R.string.inv_treasury_invested), moneyOrMasked(asset.totalInvested, hidden))
            }
            HorizontalDivider(color = palette.border)
            Column {
                treasury?.marketPu?.let { pu ->
                    DetailFigure(stringResource(R.string.inv_treasury_pu), formatCurrency(pu), treasury.priceDate?.let { stringResource(R.string.inv_treasury_base_date, formatDateBR(it)) })
                }
                if (marketRate.isNotEmpty()) DetailFigure(stringResource(R.string.inv_treasury_market_rate), marketRate)
                DetailFigure(
                    stringResource(if ((treasury?.lotCount ?: 0) > 1) R.string.inv_treasury_your_average_rate else R.string.inv_treasury_your_rate),
                    TreasuryLabels.treasuryRateText(treasury?.averageRate?.toDouble(), metadata).ifEmpty { "—" },
                )
            }
            if (asset.lots.isNotEmpty()) {
                Text(
                    (if (asset.lots.size == 1) stringResource(R.string.inv_treasury_one_lot) else stringResource(R.string.inv_treasury_lots, asset.lots.size)).uppercase(),
                    color = palette["zinc-600"],
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 12.sp,
                )
                asset.lots.forEach { lot ->
                    Column(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Row {
                            Text(formatDateBR(lot.purchaseDate), color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, modifier = Modifier.weight(1f))
                            Text(moneyOrMasked(lot.net, hidden), color = palette.text, fontSize = 14.sp)
                        }
                        val line = listOfNotNull(
                            TreasuryLabels.treasuryRateText(lot.rate?.toDouble(), metadata).takeIf { it.isNotEmpty() },
                            lot.units?.let { units(it) },
                        ).joinToString(" · ")
                        if (line.isNotEmpty()) Text(line, color = palette.muted, fontSize = 12.sp)
                        Text(
                            stringResource(R.string.inv_treasury_lot_values, moneyOrMasked(lot.invested, hidden), moneyOrMasked(lot.gross, hidden)),
                            color = palette.muted,
                            fontSize = 12.sp,
                            textAlign = TextAlign.Start,
                        )
                    }
                    HorizontalDivider(color = palette.border)
                }
            }
        }
    }
}
