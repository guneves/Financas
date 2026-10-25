package br.financas.app.ui.investimentos

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import br.financas.app.R
import br.financas.app.data.AppGraph
import br.financas.app.data.ReturnsDto
import br.financas.app.rules.ReturnsRules
import br.financas.app.ui.planejar.ScreenLoad
import br.financas.app.ui.theme.ShellPrefs
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

/**
 * Investimentos › Rentabilidade nativo (14-investimentos-rentabilidade.md): o TWR da carteira (ou
 * de uma classe) contra CDI e indices, tudo do servidor. Uma leitura por periodo × classe, com a
 * copia guardada (a conta no servidor e lenta); o periodo e os indices ligados ficam no aparelho.
 * Sem escritas.
 */
class RentabilidadeViewModel(application: Application) : AndroidViewModel(application) {

    private val app = application
    private val repo = AppGraph.from(application).investimentos

    val returns = ScreenLoad<ReturnsDto>()

    var hidden by mutableStateOf(ShellPrefs.valuesHidden(application) ?: false)
        private set
    var months by mutableStateOf(PeriodStore.loadText(application, PERIOD_KEY, ReturnsRules.DEFAULT_PERIOD, ReturnsRules.PERIODS.map { it.first }))
        private set
    var assetClass by mutableStateOf("")
        private set
    var visible by mutableStateOf(PeriodStore.loadSet(application, BENCHMARKS_KEY, ReturnsRules.DEFAULT_VISIBLE))
        private set
    var selected by mutableStateOf<Int?>(null)
        private set

    private var job: Job? = null

    fun refreshAll() {
        hidden = ShellPrefs.valuesHidden(app) ?: hidden
        read()
    }

    private fun read() {
        job?.cancel()
        job = viewModelScope.launch { returns.collect(app, repo.returns(months, assetClass), R.string.inv_returns_failed) }
    }

    fun toggleHidden() {
        hidden = !hidden
        ShellPrefs.saveValuesHidden(app, hidden)
    }

    fun changeMonths(next: String) {
        months = next
        selected = null
        PeriodStore.saveText(app, PERIOD_KEY, next)
        read()
    }

    fun changeClass(next: String) {
        assetClass = next
        selected = null
        read()
    }

    fun toggleBenchmark(code: String) {
        visible = ReturnsRules.toggle(visible, code)
        PeriodStore.saveSet(app, BENCHMARKS_KEY, visible)
    }

    fun select(index: Int) {
        selected = if (selected == index) null else index
    }

    companion object {
        const val PERIOD_KEY = "rentabilidadePeriod"
        const val BENCHMARKS_KEY = "rentabilidadeBenchmarks"
    }
}
