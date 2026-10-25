package br.financas.app.ui.investimentos

import android.app.Application
import android.widget.Toast
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import br.financas.app.R
import br.financas.app.core.formatDateBR
import br.financas.app.core.getLocalDateString
import br.financas.app.data.AppGraph
import br.financas.app.data.AssetDto
import br.financas.app.data.InboxWrite
import br.financas.app.data.InvestimentosRepository
import br.financas.app.data.JsonBody
import br.financas.app.data.ProceedDto
import br.financas.app.data.ProceedsSummaryDto
import br.financas.app.rules.AssetSearch
import br.financas.app.rules.ProceedsForm
import br.financas.app.rules.ProceedsRules
import br.financas.app.ui.components.ConfirmRequest
import br.financas.app.ui.nav.NativeScreensPlugin
import br.financas.app.ui.newentry.SaveResult
import br.financas.app.ui.planejar.ScreenLoad
import br.financas.app.ui.theme.ShellPrefs
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDate

/** Os filtros de Proventos (valem ao mudar). */
data class ProceedsFilters(
    val dateFrom: String,
    val dateTo: String,
    val proceedsType: String = "",
    val assetId: String = "",
    val status: String = "ALL",
) {
    fun params(): Map<String, String> = linkedMapOf(
        "date_from" to dateFrom,
        "date_to" to dateTo,
        "proceeds_type" to proceedsType,
        "asset_id" to assetId,
        "status" to status,
    )

    /** O calendario respeita o ativo e o tipo, sempre os agendados (o servidor poe hoje a +180 dias). */
    fun calendarParams(): Map<String, String> = linkedMapOf("asset_id" to assetId, "proceeds_type" to proceedsType, "status" to "SCHEDULED")
}

/** O sheet "Registrar provento" / "Editar provento". */
data class ProceedSheet(val editing: ProceedDto?, val form: ProceedsForm.Form, val assetQuery: String = "", val pickerOpen: Boolean = true)

/**
 * Investimentos › Proventos nativo (15-investimentos-proventos.md): resumo, calendario,
 * recebimentos por mes/ano, por ativo, filtros e historico, quatro leituras com a copia guardada.
 * O provento novo leva client_id e vai para a fila sem conexao; editar, excluir e "Atualizar"
 * (a sincronizacao forcada) so com o servidor.
 */
class ProventosViewModel(application: Application) : AndroidViewModel(application) {

    private val app = application
    private val graph = AppGraph.from(application)
    private val repo = graph.investimentos
    private val saver = investmentSaver(application)

    private val year = LocalDate.now().year

    var filters by mutableStateOf(ProceedsFilters("$year-01-01", "$year-12-31"))
        private set
    var filtersOpen by mutableStateOf(false)
        private set

    val assets = ScreenLoad<List<AssetDto>>()
    val proceeds = ScreenLoad<List<ProceedDto>>()
    val summary = ScreenLoad<ProceedsSummaryDto>()
    val calendar = ScreenLoad<List<ProceedDto>>()

    var hidden by mutableStateOf(ShellPrefs.valuesHidden(application) ?: false)
        private set
    var error by mutableStateOf("")
        private set
    var syncing by mutableStateOf(false)
        private set
    var chartPeriod by mutableStateOf("month")
        private set
    var chartSelected by mutableStateOf<Int?>(null)
        private set
    var confirm by mutableStateOf<ConfirmRequest?>(null)
        private set
    var queued by mutableStateOf(0)
        private set

    var sheet by mutableStateOf<ProceedSheet?>(null)
        private set
    var sheetError by mutableStateOf("")
        private set
    var sheetSaving by mutableStateOf(false)
        private set

    private val _notices = MutableSharedFlow<String>(extraBufferCapacity = 8)
    val notices: SharedFlow<String> = _notices.asSharedFlow()

    val export = InvestExportState(application, viewModelScope, InvestimentosRepository.PROCEEDS_EXPORT_PATH, "proventos") { it.proceeds }

    private var cleared = false
    private var readJobs: List<Job> = emptyList()

    override fun onCleared() {
        cleared = true
        super.onCleared()
    }

    fun refreshAll() {
        hidden = ShellPrefs.valuesHidden(app) ?: hidden
        queued = queuedCount(app, "PROCEED")
        read()
        ProceedsSync.onOpen(app) { reread() }
    }

    // Cada combinacao de filtros e uma leitura (a copia de uma busca velha nunca cobre a nova);
    // a da combinacao anterior fica na tela ate a nova chegar.
    private fun read() {
        readJobs.forEach { it.cancel() }
        val params = filters.params()
        readJobs = listOf(
            viewModelScope.launch { assets.collect(app, repo.assets(), R.string.inv_proceeds_failed) },
            viewModelScope.launch { proceeds.collect(app, repo.proceeds(params), R.string.inv_proceeds_failed) },
            viewModelScope.launch { summary.collect(app, repo.proceedsSummary(params), R.string.inv_proceeds_failed) },
            viewModelScope.launch { calendar.collect(app, repo.proceedsCalendar(filters.calendarParams()), R.string.inv_proceeds_failed) },
        )
        export.params = params
    }

    private fun reread() {
        if (!cleared) refreshAll()
        NativeScreensPlugin.emitDataChanged()
    }

    fun toggleHidden() {
        hidden = !hidden
        ShellPrefs.saveValuesHidden(app, hidden)
    }

    fun dismissError() {
        error = ""
    }

    fun dismissConfirm() {
        confirm = null
    }

    fun toggleFilters() {
        filtersOpen = !filtersOpen
    }

    fun changeFilters(next: ProceedsFilters) {
        filters = next
        chartSelected = null
        read()
    }

    fun changeChartPeriod(period: String) {
        chartPeriod = period
        chartSelected = null
    }

    fun selectChart(index: Int) {
        chartSelected = if (chartSelected == index) null else index
    }

    val assetsById: Map<String, AssetDto> get() = assets.value.orEmpty().associateBy { it.id }

    fun ruleAsset(asset: AssetDto): ProceedsRules.Asset =
        ProceedsRules.Asset(asset.id, asset.ticker, asset.name, asset.category, asset.assetClass)

    /** A categoria de um ativo (ETF e ETF, Tesouro e Tesouro Direto), pelo /api/assets. */
    fun categoryOf(assetId: String?, fallbackClass: String?): String {
        val asset = assetId?.let { assetsById[it] }
        return ProceedsRules.categoryLabel(asset?.let(::ruleAsset) ?: ProceedsRules.Asset(assetId.orEmpty(), assetClass = fallbackClass))
    }

    // ---- Atualizar (a sincronizacao forcada) ----

    fun sync() {
        if (syncing) return
        syncing = true
        viewModelScope.launch {
            val result = repo.syncProceeds(force = true)
            syncing = false
            when (result) {
                is InboxWrite.Done -> {
                    val value = result.value
                    if (!value.message.isNullOrEmpty()) {
                        error = value.message
                    } else {
                        notice(ProceedsForm.syncToast(value.created, value.updated, value.removed))
                    }
                    reread()
                }
                else -> error = investWriteError(app, result, R.string.inv_proceeds_sync_failed) ?: app.getString(R.string.inv_proceeds_sync_failed)
            }
        }
    }

    // ---- O sheet ----

    fun openNew() {
        sheet = ProceedSheet(null, ProceedsForm.blankForm(getLocalDateString()))
        sheetError = ""
    }

    fun openEdit(item: ProceedDto) {
        val form = ProceedsForm.editForm(
            item.assetId, item.proceedsType, item.declaredDate, item.recordDate, item.exDate, item.paymentDate,
            item.amountPerUnit, item.eligibleQuantity, item.grossAmount, item.taxAmount, item.notes, getLocalDateString(),
        )
        sheet = ProceedSheet(item, form, pickerOpen = form.assetId.isEmpty())
        sheetError = ""
    }

    fun closeSheet() {
        if (!sheetSaving) sheet = null
    }

    fun changeForm(form: ProceedsForm.Form) {
        sheet = sheet?.copy(form = form)
    }

    /** Trocar o tipo tira o ativo que nao recebe aquele tipo (menos o do provento editado). */
    fun changeType(type: String) {
        val current = sheet ?: return
        val asset = assetsById[current.form.assetId]?.let(::ruleAsset)
        val original = current.editing?.assetId.orEmpty()
        val keep = asset == null || ProceedsRules.proceedsTypeFitsAsset(type, asset) || current.form.assetId == original
        sheet = current.copy(
            form = current.form.copy(proceedsType = type, assetId = if (keep) current.form.assetId else ""),
            pickerOpen = current.pickerOpen || !keep,
        )
    }

    fun typeAssetQuery(text: String) {
        sheet = sheet?.copy(assetQuery = text, pickerOpen = true)
    }

    fun reopenPicker() {
        sheet = sheet?.copy(pickerOpen = true)
    }

    fun pickAsset(assetId: String) {
        val current = sheet ?: return
        sheet = current.copy(form = current.form.copy(assetId = assetId), pickerOpen = false, assetQuery = "")
    }

    /** As opcoes do seletor: so os ativos que recebem o tipo; na edicao, o do provento fica. */
    fun assetOptions(): List<PickerOption> {
        val current = sheet ?: return emptyList()
        val all = assets.value.orEmpty()
        val eligible = ProceedsRules.assetsForProceedsType(all.map(::ruleAsset), current.form.proceedsType, current.editing?.assetId.orEmpty())
        val options = eligible.map { asset ->
            val meta = listOfNotNull(
                ProceedsRules.categoryLabel(asset).takeIf { it.isNotEmpty() },
                asset.name?.takeIf { it.isNotEmpty() && it != asset.ticker },
            ).joinToString(" · ")
            PickerOption(asset.id, asset.ticker.orEmpty(), meta)
        }
        val names = eligible.associate { it.id to it.name }
        return AssetSearch.filterAssetOptions(options, current.assetQuery, label = { it.label }, name = { names[it.value] })
    }

    fun save() {
        val current = sheet ?: return
        if (sheetSaving) return
        val asset = assetsById[current.form.assetId]
        val editing = current.editing
        val body = try {
            ProceedsForm.payload(current.form, asset?.let(::ruleAsset), editing = editing != null)
        } catch (refused: ProceedsForm.FormError) {
            sheetError = refused.message.orEmpty()
            return
        }
        sheetSaving = true
        sheetError = ""
        graph.appScope.launch {
            if (editing != null) {
                val result = repo.updateProceed(editing.id, body)
                sheetSaving = false
                val failure = investWriteError(app, result, R.string.inv_proceed_save_failed)
                when {
                    failure == null -> {
                        sheet = null
                        notice(app.getString(R.string.inv_proceed_updated))
                        reread()
                    }
                    cleared -> Toast.makeText(app, failure, Toast.LENGTH_LONG).show()
                    else -> sheetError = failure
                }
                return@launch
            }
            // O provento novo vai pela fila (042): um `repeat` reenviado devolve a serie ja gravada.
            val ticker = asset?.ticker.orEmpty()
            val result = saver.createJson("PROCEED", JSONObject(JsonBody.encode(body)), title = ticker)
            sheetSaving = false
            when (result) {
                is SaveResult.Saved -> {
                    sheet = null
                    val count = (result.data as? JSONArray)?.length()
                    notice(if (count != null) app.getString(R.string.inv_proceed_series_saved, count) else app.getString(R.string.inv_proceed_saved))
                    reread()
                }
                is SaveResult.Queued -> {
                    sheet = null
                    notice(app.getString(R.string.inv_proceed_queued, ticker))
                    reread()
                }
                is SaveResult.Refused -> sheetError = result.message ?: app.getString(R.string.inv_proceed_save_failed)
                is SaveResult.SessionExpired -> sheetError = result.message ?: app.getString(R.string.data_session_expired)
            }
        }
    }

    fun askDelete(item: ProceedDto) {
        confirm = ConfirmRequest(
            title = app.getString(R.string.inv_proceed_delete_title),
            message = ProceedsForm.deleteMessage(item.asset?.ticker, formatDateBR(item.paymentDate), automatic = !item.syncKey.isNullOrEmpty()),
            confirmLabel = app.getString(R.string.inv_delete),
        ) {
            error = ""
            graph.appScope.launch {
                val result = repo.deleteProceed(item.id)
                val failure = investWriteError(app, result, R.string.inv_proceed_delete_failed)
                when {
                    failure == null -> {
                        notice(app.getString(R.string.inv_proceed_deleted))
                        reread()
                    }
                    cleared -> Toast.makeText(app, failure, Toast.LENGTH_LONG).show()
                    else -> error = failure
                }
            }
        }
    }

    private fun notice(message: String) {
        if (cleared) Toast.makeText(app, message, Toast.LENGTH_SHORT).show() else _notices.tryEmit(message)
    }

    companion object {
        val STATUS_ITEMS = listOf("ALL" to "Todos", "PAID" to "Pagos", "SCHEDULED" to "Agendados")
        val CHART_PERIODS = listOf("month" to "Mensal", "year" to "Anual")
    }
}
