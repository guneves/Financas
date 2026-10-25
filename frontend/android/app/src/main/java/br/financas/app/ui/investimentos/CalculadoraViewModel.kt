package br.financas.app.ui.investimentos

import android.app.Application
import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import br.financas.app.rules.CompoundInterest
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject

/**
 * Investimentos › Calculadora nativa (16-…, C): juros compostos so no aparelho, sem servidor e
 * sem gravar nada da carteira. O resultado espera 250 ms depois da ultima tecla; o ultimo
 * formulario fica no aparelho (o @financeMVP:calculadoraJuros da web).
 */
class CalculadoraViewModel(application: Application) : AndroidViewModel(application) {

    private val app = application

    var form by mutableStateOf(FormStore.load(application))
        private set
    var result by mutableStateOf(CompoundInterest.calculate(form))
        private set
    var selected by mutableStateOf<Int?>(null)
        private set

    private var debounce: Job? = null

    fun change(next: CompoundInterest.Form) {
        form = next
        debounce?.cancel()
        debounce = viewModelScope.launch {
            delay(DEBOUNCE_MS)
            result = CompoundInterest.calculate(next)
            selected = null
            FormStore.save(app, next)
        }
    }

    fun clear() {
        change(CompoundInterest.DEFAULT_FORM)
    }

    fun select(index: Int) {
        selected = if (selected == index) null else index
    }

    /** O formulario guardado: os campos que faltarem vem do padrao ({ ...DEFAULT_FORM, ...saved }). */
    private object FormStore {
        private const val PREFS = "financas_native_invest"
        private const val KEY = "calculadoraJuros"

        fun load(context: Context): CompoundInterest.Form {
            val text = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY, null) ?: return CompoundInterest.DEFAULT_FORM
            val json = runCatching { JSONObject(text) }.getOrNull() ?: return CompoundInterest.DEFAULT_FORM
            val base = CompoundInterest.DEFAULT_FORM
            return CompoundInterest.Form(
                initial = json.optString("initial", base.initial),
                monthly = json.optString("monthly", base.monthly),
                rate = json.optString("rate", base.rate),
                rateUnit = json.optString("rateUnit", base.rateUnit),
                period = json.optString("period", base.period),
                periodUnit = json.optString("periodUnit", base.periodUnit),
                timing = json.optString("timing", base.timing),
                inflation = json.optString("inflation", base.inflation),
            )
        }

        fun save(context: Context, form: CompoundInterest.Form) {
            val json = JSONObject()
                .put("initial", form.initial)
                .put("monthly", form.monthly)
                .put("rate", form.rate)
                .put("rateUnit", form.rateUnit)
                .put("period", form.period)
                .put("periodUnit", form.periodUnit)
                .put("timing", form.timing)
                .put("inflation", form.inflation)
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString(KEY, json.toString()).apply()
        }
    }

    companion object {
        const val DEBOUNCE_MS = 250L
    }
}
