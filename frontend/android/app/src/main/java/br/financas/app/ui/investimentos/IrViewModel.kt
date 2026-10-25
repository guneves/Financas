package br.financas.app.ui.investimentos

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import br.financas.app.R
import br.financas.app.core.monthKey
import br.financas.app.data.AppGraph
import br.financas.app.data.ExemptionDto
import br.financas.app.data.TaxReportDto
import br.financas.app.ui.planejar.ScreenLoad
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import java.time.LocalDate

/**
 * Investimentos › IR nativo, a parte do celular (16-…, B): o medidor da isencao de acoes do mes e
 * os meses de DARF do ano, so leitura, os numeros da apuracao do servidor. O relatorio completo
 * (bens, rendimentos, o texto do IRPF, o .xlsx) fica na pagina web.
 */
class IrViewModel(application: Application) : AndroidViewModel(application) {

    private val app = application
    private val repo = AppGraph.from(application).investimentos

    val month: String = monthKey()
    val currentYear: Int = LocalDate.now().year

    val exemption = ScreenLoad<ExemptionDto>()
    val report = ScreenLoad<TaxReportDto>()

    /** O ano-calendario: de fabrica o passado (o que se declara agora). */
    var year by mutableStateOf(currentYear - 1)
        private set

    private var reportJob: Job? = null

    fun refreshAll() {
        viewModelScope.launch { exemption.collect(app, repo.exemption(month), R.string.inv_ir_exemption_failed) }
        readReport()
    }

    private fun readReport() {
        reportJob?.cancel()
        reportJob = viewModelScope.launch { report.collect(app, repo.taxReport(year), R.string.inv_ir_failed) }
    }

    fun changeYear(next: Int) {
        year = next
        readReport()
    }
}
