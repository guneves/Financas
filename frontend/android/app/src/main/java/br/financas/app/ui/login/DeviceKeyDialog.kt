package br.financas.app.ui.login

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import br.financas.app.R
import br.financas.app.ui.components.AppTextField
import br.financas.app.ui.components.Field
import br.financas.app.ui.theme.LocalPalette

/**
 * Colar a chave de acesso remoto (outbox/DeviceKey.java): a casca o abre num 401 do proxy
 * ("Chave de acesso inválida ou ausente"), e Ajustes › Perfil para trocar a chave. [title] e
 * [message] dizem por que abriu; [onSave] recebe a chave colada.
 */
@Composable
fun DeviceKeyDialog(
    title: String,
    message: String?,
    busy: Boolean,
    onSave: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    val palette = LocalPalette.current
    var key by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = palette.surface,
        titleContentColor = palette.text,
        textContentColor = palette["zinc-700"],
        title = { Text(title, fontWeight = FontWeight.ExtraBold) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                if (message != null) Text(message)
                Field(stringResource(R.string.device_key_label), hint = stringResource(R.string.device_key_hint)) {
                    AppTextField(value = key, onValueChange = { key = it }, password = true)
                }
            }
        },
        confirmButton = {
            TextButton(onClick = { onSave(key) }, enabled = !busy && key.isNotBlank()) {
                Text(stringResource(R.string.device_key_save), fontWeight = FontWeight.Bold, color = palette["emerald-700"])
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text(stringResource(R.string.device_key_later), color = palette["zinc-700"]) }
        },
        modifier = Modifier,
    )
}
