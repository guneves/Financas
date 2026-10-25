package br.financas.app.ui.login

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import br.financas.app.R
import br.financas.app.data.AppGraph
import br.financas.app.data.LoginResult
import br.financas.app.outbox.Outbox
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * O login nativo (pages/Auth.jsx, so "Entrar": o cadastro fica fechado no celular). Deu certo: a
 * sessao vai para o Session (Outbox.signIn), a fila e as deteccoes voltam a ser enviadas e
 * [onSignedIn] leva ao Inicio.
 */
class LoginViewModel(application: Application) : AndroidViewModel(application) {

    private val app: Application = application
    private val graph = AppGraph.from(application)

    var email by mutableStateOf("")
    var password by mutableStateOf("")

    var busy by mutableStateOf(false)
        private set

    var error by mutableStateOf("")
        private set

    fun submit(onSignedIn: () -> Unit) {
        if (busy) return
        if (email.isBlank() || password.isEmpty()) {
            error = app.getString(R.string.login_missing)
            return
        }
        busy = true
        error = ""
        val base = graph.serverUrl()
        viewModelScope.launch {
            val result = graph.auth.login(base, email, password)
            val failure = when (result) {
                is LoginResult.Done -> withContext(Dispatchers.IO) {
                    try {
                        Outbox.signIn(app, base, result.token, result.userId)
                        null
                    } catch (error: Exception) {
                        error.message ?: app.getString(R.string.login_failed)
                    }
                }
                is LoginResult.Refused -> result.message ?: app.getString(R.string.login_failed)
                LoginResult.Offline -> app.getString(R.string.login_offline)
            }
            busy = false
            if (failure == null) {
                password = ""
                graph.signedIn()
                onSignedIn()
            } else {
                error = failure
            }
        }
    }
}
