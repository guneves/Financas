package br.financas.app.ui.lancamentos

import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import br.financas.app.ui.components.AppTextField
import kotlinx.coroutines.delay

/**
 * Um campo de valor como o do "+ Novo": grande, com o teclado decimal, e (com [autoFocus]) ja
 * focado quando o sheet abre.
 */
@Composable
fun AmountInput(value: String, onChange: (String) -> Unit, label: String, autoFocus: Boolean = true) {
    val focus = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current
    if (autoFocus) {
        LaunchedEffect(Unit) {
            delay(150)
            try {
                focus.requestFocus()
                keyboard?.show()
            } catch (ignored: IllegalStateException) {
                // O campo ainda nao esta na tela: o dono toca nele.
            }
        }
    }
    AppTextField(
        value = value,
        onValueChange = onChange,
        placeholder = "0,00",
        keyboardType = KeyboardType.Decimal,
        textStyle = MaterialTheme.typography.headlineSmall.copy(fontWeight = FontWeight.Bold),
        focusRequester = focus,
        contentDescription = label,
    )
}
