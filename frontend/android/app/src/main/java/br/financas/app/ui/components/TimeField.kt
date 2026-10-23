package br.financas.app.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TimePicker
import androidx.compose.material3.rememberTimePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import br.financas.app.ui.theme.LocalPalette

/**
 * O <input type="time"> da web: mostra "HH:MM" e abre o relogio de 24 h. [value] e [onChange] em
 * "HH:MM"; vazio e "sem hora" ([clearLabel] limpa, como apagar o campo na web).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TimeField(
    value: String,
    onChange: (String) -> Unit,
    confirmLabel: String,
    cancelLabel: String,
    clearLabel: String,
    modifier: Modifier = Modifier,
    contentDescription: String? = null,
) {
    val palette = LocalPalette.current
    var open by remember { mutableStateOf(false) }
    Surface(
        onClick = { open = true },
        shape = RoundedCornerShape(14.dp),
        color = palette.surface,
        border = BorderStroke(1.dp, palette["zinc-300"]),
        modifier = modifier
            .fillMaxWidth()
            .heightIn(min = 56.dp)
            .semantics {
                role = Role.Button
                if (contentDescription != null) this.contentDescription = contentDescription
            },
    ) {
        Box(contentAlignment = Alignment.CenterStart, modifier = Modifier.padding(horizontal = 16.dp, vertical = 16.dp)) {
            Text(
                text = value.ifEmpty { "--:--" },
                style = MaterialTheme.typography.bodyLarge,
                color = if (value.isEmpty()) palette.muted else palette.text,
                maxLines = 1,
            )
        }
    }
    if (open) {
        val parts = value.split(":")
        val state = rememberTimePickerState(
            initialHour = parts.getOrNull(0)?.toIntOrNull()?.coerceIn(0, 23) ?: 12,
            initialMinute = parts.getOrNull(1)?.toIntOrNull()?.coerceIn(0, 59) ?: 0,
            is24Hour = true,
        )
        AlertDialog(
            onDismissRequest = { open = false },
            containerColor = palette.surface,
            text = { TimePicker(state = state) },
            confirmButton = {
                TextButton(onClick = {
                    onChange("%02d:%02d".format(state.hour, state.minute))
                    open = false
                }) { Text(confirmLabel) }
            },
            dismissButton = {
                Row {
                    TextButton(onClick = {
                        onChange("")
                        open = false
                    }) { Text(clearLabel) }
                    TextButton(onClick = { open = false }) { Text(cancelLabel) }
                }
            },
        )
    }
}
