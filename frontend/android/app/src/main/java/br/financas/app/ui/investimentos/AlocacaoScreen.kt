package br.financas.app.ui.investimentos

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.core.formatCurrency
import br.financas.app.core.formatPercent
import br.financas.app.data.AllocationClassDto
import br.financas.app.data.AllocationDto
import br.financas.app.data.SectorDto
import br.financas.app.rules.AllocationRules
import br.financas.app.rules.PortfolioView
import br.financas.app.ui.charts.DonutChart
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AlertTone
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.AppTextField
import br.financas.app.ui.components.Badge
import br.financas.app.ui.components.BadgeTone
import br.financas.app.ui.components.ButtonVariant
import br.financas.app.ui.components.EmptyState
import br.financas.app.ui.components.Field
import br.financas.app.ui.components.ListSkeleton
import br.financas.app.ui.components.Panel
import br.financas.app.ui.lancamentos.moneyOrMasked
import br.financas.app.ui.planejar.PlanejarScaffold
import br.financas.app.ui.theme.LocalPalette
import kotlinx.coroutines.flow.MutableSharedFlow
import java.math.BigDecimal

/** O caminho web da Alocacao (definir metas, setores): a pagina React, mesmo num APK que tem a nativa. */
const val ALOCACAO_WEB_ROUTE = "/investimentos/alocacao?web=1"

/** Investimentos › Alocacao nativo, so leitura e a divisao do aporte (16-…, A). */
@Composable
fun AlocacaoScreen(viewModel: AlocacaoViewModel, onBack: () -> Unit, onTab: (InvestimentosTab) -> Unit, onOpenWeb: (String) -> Unit) {
    val palette = LocalPalette.current
    val dismiss = stringResource(R.string.lanc_dismiss)
    val data = viewModel.allocation.value
    PlanejarScaffold(
        notices = remember { MutableSharedFlow() },
        onRefresh = viewModel::refreshAll,
        topBar = {
            InvestimentosTopBar(stringResource(R.string.inv_aloc_title), InvestimentosTab.ALOCACAO, viewModel.hidden, onBack, viewModel::toggleHidden, onTab)
        },
    ) {
        item(key = "intro") {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(stringResource(R.string.inv_aloc_description), fontSize = 14.sp, color = palette["zinc-600"])
                AppButton(stringResource(R.string.inv_aloc_edit_on_web), { onOpenWeb(ALOCACAO_WEB_ROUTE) }, Modifier.fillMaxWidth(), variant = ButtonVariant.SECONDARY)
                Text(stringResource(R.string.inv_aloc_edit_hint), fontSize = 12.sp, color = palette.muted)
            }
        }
        item(key = "alerts") {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (viewModel.allocation.offline) AlertMessage(viewModel.allocation.offlineText, AlertTone.WARNING, dismiss)
                AlertMessage(viewModel.allocation.error, AlertTone.DANGER, dismiss)
            }
        }
        when {
            data == null && !viewModel.allocation.loaded -> item(key = "loading") { Panel { ListSkeleton(rows = 4, modifier = Modifier.padding(16.dp)) } }
            data == null -> Unit
            data.classes.isEmpty() -> item(key = "empty") {
                EmptyState(stringResource(R.string.inv_aloc_empty_title), stringResource(R.string.inv_aloc_empty_message))
            }
            else -> {
                if (!data.hasClassTargets) item(key = "no-targets") { AlertMessage(stringResource(R.string.inv_aloc_no_targets), AlertTone.INFO, dismiss) }
                item(key = "concentration") { Concentration(data, dismiss) }
                if (data.hasClassTargets) item(key = "contribution") { ContributionPanel(data, viewModel) }
                if (data.opportunities.isNotEmpty()) item(key = "opportunities") { OpportunitiesPanel(data) }
                item(key = "classes") { ClassesPanel(data, viewModel) }
                item(key = "sectors") { SectorsPanel(viewModel) }
            }
        }
    }
}

@Composable
private fun Concentration(data: AllocationDto, dismiss: String) {
    val over = data.concentration.assetsOverThreshold
    if (over.isEmpty()) return
    val threshold = formatPercent(data.concentration.thresholdPercent, 0)
    val list = over.joinToString(", ") { "${it.ticker.orEmpty()} ${formatPercent(it.percent, 1)}" }
    val head = if (over.size == 1) stringResource(R.string.inv_aloc_concentration_one, threshold, list) else stringResource(R.string.inv_aloc_concentration_many, over.size, threshold, list)
    AlertMessage("$head ${stringResource(R.string.inv_aloc_concentration_tail)}", AlertTone.WARNING, dismiss)
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ContributionPanel(data: AllocationDto, viewModel: AlocacaoViewModel) {
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Field(stringResource(R.string.inv_aloc_contribution), hint = stringResource(R.string.inv_aloc_contribution_hint)) {
                AppTextField(viewModel.contributionText, viewModel::typeContribution, placeholder = "0,00", keyboardType = KeyboardType.Decimal)
            }
            if (viewModel.contribution.signum() > 0) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    // O que voce vai aportar, dividido: nao e saldo da carteira (a web tambem mostra).
                    data.classes.filter { (it.suggested ?: BigDecimal.ZERO).signum() > 0 }.forEach {
                        Badge("${PortfolioView.classLabel(it.assetClass)}: ${formatCurrency(it.suggested)}", BadgeTone.INFO)
                    }
                }
            }
        }
    }
}

@Composable
private fun OpportunitiesPanel(data: AllocationDto) {
    val palette = LocalPalette.current
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) { PanelTitle(stringResource(R.string.inv_aloc_opportunities), stringResource(R.string.inv_aloc_opportunities_description)) }
                Badge(stringResource(R.string.inv_assets_count, data.opportunities.size), BadgeTone.INFO)
            }
            data.opportunities.forEach { item ->
                HorizontalDivider(color = palette.border)
                Column(Modifier.padding(vertical = 4.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(item.ticker.orEmpty(), color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                        Text(PortfolioView.classLabel(item.assetClass), color = palette.muted, fontSize = 13.sp)
                    }
                    // Precos e percentuais: publicos, ficam no modo privado (como na web).
                    Text(
                        stringResource(
                            R.string.inv_aloc_opportunity_line,
                            formatCurrency(item.currentPrice),
                            formatCurrency(item.averagePrice),
                            formatPercent(item.percentInClass, 1),
                            formatPercent(item.targetPercent, 1),
                        ),
                        color = palette["zinc-600"],
                        fontSize = 12.sp,
                    )
                }
            }
        }
    }
}

/** A barra do atual com um traco na meta (AllocationBar). */
@Composable
private fun AllocationBar(percent: BigDecimal?, target: BigDecimal?) {
    val palette = LocalPalette.current
    val fraction = ((percent ?: BigDecimal.ZERO).toFloat() / 100f).coerceIn(0f, 1f)
    BoxWithConstraints(Modifier.fillMaxWidth().height(16.dp), contentAlignment = Alignment.CenterStart) {
        Box(Modifier.fillMaxWidth().height(8.dp).background(palette["zinc-100"], RoundedCornerShape(50)))
        if (fraction > 0f) Box(Modifier.fillMaxWidth(fraction).height(8.dp).background(palette.accent, RoundedCornerShape(50)))
        if (target != null) {
            val at = (target.toFloat() / 100f).coerceIn(0f, 1f)
            Box(Modifier.offset(x = maxWidth * at - 1.dp).width(2.dp).fillMaxHeight().background(palette.text, RoundedCornerShape(1.dp)))
        }
    }
}

@Composable
private fun ClassesPanel(data: AllocationDto, viewModel: AlocacaoViewModel) {
    val palette = LocalPalette.current
    val hidden = viewModel.hidden
    val hasContribution = viewModel.contribution.signum() > 0 && data.hasClassTargets
    val money = { value: BigDecimal -> moneyOrMasked(value, hidden) }
    Panel {
        Column(Modifier.padding(vertical = 16.dp)) {
            Box(Modifier.padding(horizontal = 16.dp)) {
                PanelTitle(stringResource(R.string.inv_aloc_classes), stringResource(R.string.inv_aloc_classes_description, moneyOrMasked(data.total, hidden)))
            }
            data.classes.forEach { item -> ClassRow(item, viewModel, hasContribution, money) }
        }
    }
}

@Composable
private fun ClassRow(item: AllocationClassDto, viewModel: AlocacaoViewModel, hasContribution: Boolean, money: (BigDecimal) -> String) {
    val palette = LocalPalette.current
    val open = item.assetClass in viewModel.openClasses
    HorizontalDivider(color = palette.border, modifier = Modifier.padding(top = 12.dp))
    Column(
        Modifier.fillMaxWidth().clickable { viewModel.toggleClass(item.assetClass) }.padding(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(if (open) "▾" else "▸", color = palette.muted)
            Text(PortfolioView.classLabel(item.assetClass), color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, modifier = Modifier.weight(1f))
            Text(moneyOrMasked(item.value, viewModel.hidden), color = palette.muted, fontSize = 13.sp)
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val target = item.targetPercent?.let { " " + stringResource(R.string.inv_aloc_target, formatPercent(it, 1)) }.orEmpty()
            Text(formatPercent(item.percent, 1) + target, color = palette["zinc-700"], fontSize = 13.sp, modifier = Modifier.weight(1f))
            val drift = AllocationRules.drift(item.diffPercent)
            Badge(drift.label, if (drift.warning) BadgeTone.WARNING else BadgeTone.NEUTRAL)
        }
        AllocationBar(item.percent, item.targetPercent)
        val suggested = item.suggested ?: BigDecimal.ZERO
        if (hasContribution && suggested.signum() > 0) {
            Text(stringResource(R.string.inv_aloc_contribute, formatCurrency(suggested)), color = palette["sky-700"], fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
        } else {
            val gap = AllocationRules.gapText(item.gapValue, money)
            if (gap.isNotEmpty()) Text(gap, color = palette["zinc-600"], fontSize = 13.sp)
        }
    }
    if (open) {
        Column(
            Modifier.fillMaxWidth().background(palette["zinc-50"]).padding(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            if (!item.hasAssetTargets && item.assets.size > 1) {
                Text(stringResource(R.string.inv_aloc_no_asset_targets), color = palette.muted, fontSize = 12.sp)
            }
            item.assets.forEach { asset ->
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Column(Modifier.weight(1f)) {
                        Text(asset.ticker.orEmpty(), color = palette.text, fontWeight = FontWeight.Medium, fontSize = 14.sp)
                        if (asset.belowAveragePrice) Text(stringResource(R.string.inv_aloc_below_average), color = palette.muted, fontSize = 11.sp)
                        val target = asset.targetPercent?.let { formatPercent(it, 1) } ?: "—"
                        Text(stringResource(R.string.inv_aloc_asset_line, formatPercent(asset.percentInClass, 1), target), color = palette.muted, fontSize = 11.sp)
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text(moneyOrMasked(asset.value, viewModel.hidden), color = palette["zinc-700"], fontSize = 13.sp)
                        val suggested = asset.suggested ?: BigDecimal.ZERO
                        val right = when {
                            hasContribution -> if (suggested.signum() > 0) formatCurrency(suggested) else "—"
                            else -> AllocationRules.gapText(asset.gapValue, money).ifEmpty { "—" }
                        }
                        Text(right, color = if (hasContribution && suggested.signum() > 0) palette["sky-700"] else palette["zinc-600"], fontSize = 12.sp)
                    }
                }
            }
        }
    }
}

@Composable
private fun SectorsPanel(viewModel: AlocacaoViewModel) {
    val palette = LocalPalette.current
    val hidden = viewModel.hidden
    val data = viewModel.sectors.value
    val sectors = data?.sectors.orEmpty()
    val colorIndices = AllocationRules.sectorColorIndices(sectors.map { it.sector })
    val colors = colorIndices.map { seriesColor(it) }
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            PanelTitle(stringResource(R.string.inv_aloc_sectors), stringResource(R.string.inv_aloc_sectors_description))
            ClassSelect(viewModel.sectorClass, viewModel::changeSectorClass)
            AlertMessage(viewModel.sectors.error, AlertTone.DANGER, stringResource(R.string.lanc_dismiss))
            when {
                data == null && !viewModel.sectors.loaded -> ListSkeleton(rows = 2)
                sectors.isEmpty() -> EmptyState(stringResource(R.string.inv_aloc_sectors_empty))
                else -> {
                    val total = sectors.fold(BigDecimal.ZERO) { acc, item -> acc + (item.value ?: BigDecimal.ZERO) }
                    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                        DonutChart(sectors.take(9).mapIndexed { index, item -> (item.value ?: BigDecimal.ZERO).toDouble() to colors[index] })
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(stringResource(R.string.inv_allocation_center), color = palette.muted, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                            Text(moneyOrMasked(total, hidden), color = palette.text, fontSize = 15.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                    sectors.forEachIndexed { index, sector -> SectorRow(sector, colors[index], viewModel) }
                }
            }
        }
    }
}

@Composable
private fun SectorRow(sector: SectorDto, color: androidx.compose.ui.graphics.Color, viewModel: AlocacaoViewModel) {
    val palette = LocalPalette.current
    val key = sector.sector ?: "-"
    val open = key in viewModel.openSectors
    HorizontalDivider(color = palette.border)
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable { viewModel.toggleSector(key) },
    ) {
        Box(Modifier.size(10.dp).background(color, CircleShape))
        Column(Modifier.weight(1f)) {
            Text(sector.label.orEmpty(), color = palette.text, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
            Text(stringResource(R.string.inv_assets_count, sector.assets.size), color = palette.muted, fontSize = 12.sp)
        }
        Column(horizontalAlignment = Alignment.End) {
            Text(moneyOrMasked(sector.value, viewModel.hidden), color = palette.text, fontSize = 13.sp)
            Text(formatPercent(sector.percent, 1), color = palette.muted, fontSize = 12.sp)
        }
    }
    if (open) {
        sector.assets.forEach { asset ->
            Row(Modifier.fillMaxWidth().padding(start = 18.dp, top = 2.dp, bottom = 2.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Column(Modifier.weight(1f)) {
                    Text(asset.ticker.orEmpty(), color = palette.text, fontSize = 13.sp, fontWeight = FontWeight.Medium)
                    val meta = listOfNotNull(asset.categoryLabel, asset.segment?.takeIf { it.isNotEmpty() }, if (asset.source == "MANUAL") "manual" else null).joinToString(" · ")
                    if (meta.isNotEmpty()) Text(meta, color = palette.muted, fontSize = 11.sp)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(moneyOrMasked(asset.value, viewModel.hidden), color = palette["zinc-700"], fontSize = 12.sp)
                    Text("${formatPercent(asset.percentInSector, 1)} · ${formatPercent(asset.percentOfTotal, 1)}", color = palette.muted, fontSize = 11.sp)
                }
            }
        }
    }
}
