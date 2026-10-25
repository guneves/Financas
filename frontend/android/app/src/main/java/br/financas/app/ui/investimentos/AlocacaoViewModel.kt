package br.financas.app.ui.investimentos

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import br.financas.app.R
import br.financas.app.data.AllocationDto
import br.financas.app.data.AppGraph
import br.financas.app.data.SectorsDto
import br.financas.app.rules.AllocationRules
import br.financas.app.ui.planejar.ScreenLoad
import br.financas.app.ui.theme.ShellPrefs
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.math.BigDecimal

/**
 * Investimentos › Alocacao nativo, so leitura (16-…, A): classes contra a meta, concentracao,
 * oportunidades, setores e a divisao do proximo aporte (GET /api/allocation?contribution=, 350 ms
 * depois de parar de digitar). A divisao e do servidor. Definir metas e mexer em setores ficam na
 * pagina web.
 */
class AlocacaoViewModel(application: Application) : AndroidViewModel(application) {

    private val app = application
    private val repo = AppGraph.from(application).investimentos

    val allocation = ScreenLoad<AllocationDto>()
    val sectors = ScreenLoad<SectorsDto>()

    var hidden by mutableStateOf(ShellPrefs.valuesHidden(application) ?: false)
        private set
    var contributionText by mutableStateOf("")
        private set
    var contribution by mutableStateOf(BigDecimal.ZERO)
        private set
    var openClasses by mutableStateOf<Set<String>>(emptySet())
        private set
    var openSectors by mutableStateOf<Set<String>>(emptySet())
        private set
    var sectorClass by mutableStateOf("")
        private set

    private var allocationJob: Job? = null
    private var sectorsJob: Job? = null
    private var debounce: Job? = null

    fun refreshAll() {
        hidden = ShellPrefs.valuesHidden(app) ?: hidden
        readAllocation()
        readSectors()
    }

    private fun readAllocation() {
        allocationJob?.cancel()
        val amount = contribution
        val param = if (amount.signum() > 0) amount.stripTrailingZeros().toPlainString() else ""
        allocationJob = viewModelScope.launch { allocation.collect(app, repo.allocation(param), R.string.inv_allocation_failed) }
    }

    private fun readSectors() {
        sectorsJob?.cancel()
        sectorsJob = viewModelScope.launch { sectors.collect(app, repo.sectors(sectorClass), R.string.inv_sectors_failed) }
    }

    fun toggleHidden() {
        hidden = !hidden
        ShellPrefs.saveValuesHidden(app, hidden)
    }

    fun typeContribution(text: String) {
        contributionText = text
        debounce?.cancel()
        debounce = viewModelScope.launch {
            delay(DEBOUNCE_MS)
            val next = AllocationRules.contribution(text)
            if (next.compareTo(contribution) != 0) {
                contribution = next
                readAllocation()
            }
        }
    }

    fun toggleClass(key: String) {
        openClasses = if (key in openClasses) openClasses - key else openClasses + key
    }

    fun toggleSector(key: String) {
        openSectors = if (key in openSectors) openSectors - key else openSectors + key
    }

    fun changeSectorClass(next: String) {
        sectorClass = next
        readSectors()
    }

    companion object {
        const val DEBOUNCE_MS = 350L
    }
}
