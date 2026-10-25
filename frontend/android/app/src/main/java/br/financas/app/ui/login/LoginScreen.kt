package br.financas.app.ui.login

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AlertTone
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.AppTextField
import br.financas.app.ui.components.Field
import br.financas.app.ui.components.Panel
import br.financas.app.ui.theme.LocalPalette

/**
 * Entrar (00-shell.md, "Login"): e-mail e senha, o erro do servidor como chegou. [expired]: a
 * sessao caiu por um 401, e a fila do aparelho continua guardada.
 */
@Composable
fun LoginScreen(viewModel: LoginViewModel, expired: Boolean, onSignedIn: () -> Unit) {
    val palette = LocalPalette.current
    Box(
        contentAlignment = Alignment.Center,
        modifier = Modifier
            .fillMaxSize()
            .background(palette.background)
            .windowInsetsPadding(WindowInsets.safeDrawing)
            .imePadding()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
    ) {
        Column(Modifier.widthIn(max = 420.dp).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(20.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    contentAlignment = Alignment.Center,
                    modifier = Modifier.size(40.dp).background(palette.brand, RoundedCornerShape(12.dp)),
                ) {
                    Text("F", color = palette.brandInk, fontWeight = FontWeight.ExtraBold, fontSize = 18.sp)
                }
                Text(
                    stringResource(R.string.login_brand),
                    color = palette.text,
                    fontWeight = FontWeight.ExtraBold,
                    fontSize = 22.sp,
                    modifier = Modifier.padding(start = 12.dp),
                )
            }
            Panel {
                Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    Text(stringResource(R.string.login_title), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.ExtraBold, color = palette.text)
                    if (expired && viewModel.error.isEmpty()) {
                        AlertMessage(stringResource(R.string.login_session_expired), AlertTone.INFO, stringResource(R.string.home_dismiss_error))
                    }
                    AlertMessage(viewModel.error, AlertTone.DANGER, stringResource(R.string.home_dismiss_error))
                    Field(stringResource(R.string.login_email)) {
                        AppTextField(
                            value = viewModel.email,
                            onValueChange = { viewModel.email = it },
                            keyboardType = KeyboardType.Email,
                        )
                    }
                    Field(stringResource(R.string.login_password)) {
                        AppTextField(
                            value = viewModel.password,
                            onValueChange = { viewModel.password = it },
                            password = true,
                        )
                    }
                    AppButton(
                        stringResource(R.string.login_submit),
                        { viewModel.submit(onSignedIn) },
                        Modifier.fillMaxWidth(),
                        loading = viewModel.busy,
                    )
                }
            }
        }
    }
}
