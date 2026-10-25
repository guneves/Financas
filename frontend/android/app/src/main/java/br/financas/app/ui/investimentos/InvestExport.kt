package br.financas.app.ui.investimentos

import android.app.Application
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.core.getLocalDateString
import br.financas.app.data.AppGraph
import br.financas.app.data.ExportColumnDto
import br.financas.app.data.InboxWrite
import br.financas.app.data.InvestmentExportColumnsDto
import br.financas.app.data.Load
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.AppSheet
import br.financas.app.ui.components.ButtonVariant
import br.financas.app.ui.components.SegmentedChoice
import br.financas.app.ui.components.SelectOption
import br.financas.app.ui.extrato.ExportChoice
import br.financas.app.ui.lancamentos.NativeFiles
import br.financas.app.ui.theme.LocalPalette
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch

/**
 * O ExportSheet de Investimentos: carteira, operacoes ou proventos, em .xlsx ou .csv, com as
 * colunas escolhidas (GET /api/exports/columns), entregue pela folha de compartilhar do Android.
 * [columnsOf] escolhe a lista da tela; [path] e o endereco da exportacao.
 */
class InvestExportState(
    private val app: Application,
    private val scope: CoroutineScope,
    private val path: String,
    private val baseName: String,
    private val columnsOf: (InvestmentExportColumnsDto) -> List<ExportColumnDto>,
) {
    private val repo = AppGraph.from(app).investimentos

    var open by mutableStateOf(false)
        private set
    var columns by mutableStateOf<List<ExportColumnDto>>(emptyList())
        private set
    var choice by mutableStateOf(ExportChoice())
        private set
    var exporting by mutableStateOf(false)
        private set
    var error by mutableStateOf("")
        private set

    /** Os filtros da tela que vao junto (Proventos manda os dela). */
    var params: Map<String, String> = emptyMap()

    fun show() {
        open = true
        error = ""
        scope.launch {
            repo.exportColumns().collect { load ->
                val list = when (load) {
                    is Load.Cached -> load.value.let(columnsOf)
                    is Load.Fresh -> load.value.let(columnsOf)
                    is Load.Failed -> load.cached?.value?.let(columnsOf).orEmpty()
                }
                if (list.isNotEmpty() || columns.isEmpty()) columns = list
                if (load is Load.Failed && columns.isEmpty()) error = app.getString(R.string.extrato_export_columns_failed)
                if (choice.columns.isEmpty()) choice = choice.copy(columns = columns.map { it.key }.toSet())
            }
        }
    }

    fun close() {
        if (!exporting) open = false
    }

    fun change(next: ExportChoice) {
        choice = next
    }

    fun export() {
        val current = choice
        if (current.columns.isEmpty()) {
            error = app.getString(R.string.extrato_export_pick_one)
            return
        }
        val all = columns.map { it.key }
        val chosen = if (current.columns.containsAll(all)) null else all.filter { it in current.columns }
        exporting = true
        error = ""
        scope.launch {
            when (val result = repo.export(path, params, current.format, chosen)) {
                is InboxWrite.Done -> {
                    val name = result.value.fileName ?: "$baseName-${getLocalDateString()}.${current.format}"
                    val mime = result.value.contentType?.substringBefore(';') ?: NativeFiles.mimeOf(name)
                    val uri = NativeFiles.stage(app, result.value.bytes, name)
                    open = false
                    NativeFiles.share(app, uri, mime, name)
                }
                else -> error = investWriteError(app, result, R.string.extrato_export_failed).orEmpty()
            }
            exporting = false
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun InvestExportSheet(state: InvestExportState, title: String, description: String) {
    if (!state.open) return
    val palette = LocalPalette.current
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val choice = state.choice
    AppSheet(
        title = title,
        sheetState = sheetState,
        onDismiss = state::close,
        footer = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AppButton(stringResource(R.string.lanc_cancel), state::close, Modifier.weight(1f), variant = ButtonVariant.SECONDARY)
                AppButton(stringResource(R.string.extrato_export_share), state::export, Modifier.weight(1f), loading = state.exporting, enabled = choice.columns.isNotEmpty())
            }
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(description, color = palette["zinc-600"], fontSize = 14.sp)
            AlertMessage(message = state.error, dismissLabel = stringResource(R.string.lanc_dismiss))
            SegmentedChoice(
                items = listOf(
                    SelectOption("xlsx", stringResource(R.string.extrato_export_xlsx)),
                    SelectOption("csv", stringResource(R.string.extrato_export_csv)),
                ),
                value = choice.format,
                onChange = { state.change(choice.copy(format = it)) },
            )
            val all = state.columns.map { it.key }.toSet()
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(R.string.extrato_export_columns), color = palette.text, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                val allChosen = all.isNotEmpty() && choice.columns.containsAll(all)
                AppButton(
                    text = stringResource(if (allChosen) R.string.extrato_export_none else R.string.extrato_export_all),
                    onClick = { state.change(choice.copy(columns = if (allChosen) emptySet() else all)) },
                    variant = ButtonVariant.SUBTLE,
                )
            }
            state.columns.forEach { column ->
                val checked = column.key in choice.columns
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 48.dp)
                        .clickable { state.change(choice.copy(columns = if (checked) choice.columns - column.key else choice.columns + column.key)) },
                ) {
                    Checkbox(
                        checked = checked,
                        onCheckedChange = null,
                        colors = CheckboxDefaults.colors(checkedColor = palette.accent, checkmarkColor = palette.onAccent),
                    )
                    Text(column.label, color = palette.text)
                }
            }
        }
    }
}
