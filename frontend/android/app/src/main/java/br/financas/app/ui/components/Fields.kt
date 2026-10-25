package br.financas.app.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import br.financas.app.core.formatDateBR
import br.financas.app.core.parseLocalDate
import br.financas.app.ui.theme.LocalPalette
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset

/** O Field de components/ui.jsx: o rotulo (e a dica abaixo dele) sobre o campo. */
@Composable
fun Field(
    label: String,
    modifier: Modifier = Modifier,
    hint: String? = null,
    content: @Composable () -> Unit,
) {
    val palette = LocalPalette.current
    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        // O aviso vai abaixo do rotulo, nao ao lado: numa Row o aviso (sem peso) era medido
        // primeiro, ficava com a largura toda e o rotulo quebrava letra por letra.
        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(
                text = label,
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.SemiBold,
                color = palette["zinc-700"],
            )
            if (hint != null) {
                Text(
                    text = hint,
                    style = MaterialTheme.typography.labelMedium,
                    color = palette.muted,
                )
            }
        }
        content()
    }
}

private val FieldShape = RoundedCornerShape(14.dp)

/** Um campo de texto do app (o app-input da web), 56 dp de altura, cores do tema. */
@Composable
fun AppTextField(
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    placeholder: String? = null,
    keyboardType: KeyboardType = KeyboardType.Text,
    textStyle: TextStyle = MaterialTheme.typography.bodyLarge,
    focusRequester: FocusRequester? = null,
    contentDescription: String? = null,
    password: Boolean = false,
) {
    val palette = LocalPalette.current
    var fieldModifier = modifier.fillMaxWidth().heightIn(min = 56.dp)
    if (focusRequester != null) fieldModifier = fieldModifier.focusRequester(focusRequester)
    if (contentDescription != null) fieldModifier = fieldModifier.semantics { this.contentDescription = contentDescription }
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        modifier = fieldModifier,
        singleLine = true,
        textStyle = textStyle.copy(color = palette.text),
        placeholder = if (placeholder != null) {
            { Text(placeholder, style = textStyle, color = palette["zinc-400"]) }
        } else {
            null
        },
        keyboardOptions = KeyboardOptions(
            keyboardType = if (password) KeyboardType.Password else keyboardType,
            imeAction = ImeAction.Next,
        ),
        visualTransformation = if (password) PasswordVisualTransformation() else VisualTransformation.None,
        shape = FieldShape,
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = palette.accent,
            unfocusedBorderColor = palette["zinc-300"],
            focusedContainerColor = palette.surface,
            unfocusedContainerColor = palette.surface,
            cursorColor = palette.accent,
        ),
    )
}

/** Uma opcao de [SelectField]: o valor enviado e o texto mostrado. */
data class SelectOption(val value: String, val label: String)

/**
 * O app-select da web: mostra a opcao escolhida e abre a lista. [placeholder] ("Selecione...")
 * e a primeira opcao, de valor "", como o <option value=""> do HTML; null = sem ela.
 */
@Composable
fun SelectField(
    value: String,
    options: List<SelectOption>,
    onSelect: (String) -> Unit,
    modifier: Modifier = Modifier,
    placeholder: String? = null,
    contentDescription: String? = null,
) {
    val palette = LocalPalette.current
    var expanded by remember { mutableStateOf(false) }
    val selected = options.firstOrNull { it.value == value }
    Box(modifier = modifier.fillMaxWidth()) {
        Surface(
            onClick = { expanded = true },
            shape = FieldShape,
            color = palette.surface,
            border = BorderStroke(1.dp, palette["zinc-300"]),
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = 56.dp)
                .semantics {
                    role = Role.Button
                    if (contentDescription != null) this.contentDescription = contentDescription
                },
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 16.dp),
            ) {
                Text(
                    text = selected?.label ?: placeholder.orEmpty(),
                    style = MaterialTheme.typography.bodyLarge,
                    color = if (selected != null) palette.text else palette.muted,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
                Text(text = "\u25BE", color = palette.muted, style = MaterialTheme.typography.bodyLarge)
            }
        }
        DropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false },
        ) {
            val all = if (placeholder != null) listOf(SelectOption("", placeholder)) + options else options
            all.forEach { option ->
                DropdownMenuItem(
                    text = {
                        Text(
                            text = option.label,
                            color = if (option.value.isEmpty()) palette.muted else palette.text,
                            fontWeight = if (option.value == value) FontWeight.Bold else FontWeight.Normal,
                        )
                    },
                    onClick = {
                        expanded = false
                        onSelect(option.value)
                    },
                    modifier = Modifier.heightIn(min = 48.dp),
                )
            }
        }
    }
}

/**
 * O <input type="date"> da web: mostra dd/mm/aaaa e abre o calendario. [value] e [onChange] em
 * AAAA-MM-DD (o que o servidor recebe).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DateField(
    value: String,
    onChange: (String) -> Unit,
    confirmLabel: String,
    cancelLabel: String,
    modifier: Modifier = Modifier,
    contentDescription: String? = null,
    placeholder: String? = null,
    clearLabel: String? = null,
    onClear: (() -> Unit)? = null,
) {
    val palette = LocalPalette.current
    var open by remember { mutableStateOf(false) }
    Row(verticalAlignment = Alignment.CenterVertically, modifier = modifier.fillMaxWidth()) {
    Surface(
        onClick = { open = true },
        shape = FieldShape,
        color = palette.surface,
        border = BorderStroke(1.dp, palette["zinc-300"]),
        modifier = Modifier
            .weight(1f)
            .heightIn(min = 56.dp)
            .semantics {
                role = Role.Button
                if (contentDescription != null) this.contentDescription = contentDescription
            },
    ) {
        Box(contentAlignment = Alignment.CenterStart, modifier = Modifier.padding(horizontal = 16.dp, vertical = 16.dp)) {
            val shown = formatDateBR(value, "")
            Text(
                text = shown.ifEmpty { placeholder.orEmpty() },
                style = MaterialTheme.typography.bodyLarge,
                color = if (shown.isEmpty()) palette["zinc-400"] else palette.text,
                maxLines = 1,
            )
        }
    }
    // Uma data opcional: o X a apaga (volta ao placeholder).
    if (onClear != null && value.isNotEmpty()) {
        Surface(
            onClick = onClear,
            shape = RoundedCornerShape(12.dp),
            color = palette.background,
            modifier = Modifier.padding(start = 8.dp).size(48.dp).semantics { this.contentDescription = clearLabel ?: "" },
        ) {
            Box(contentAlignment = Alignment.Center) {
                Text("\u00D7", style = MaterialTheme.typography.titleLarge, color = palette["zinc-700"])
            }
        }
    }
    }
    if (open) {
        val initial = parseLocalDate(value) ?: LocalDate.now()
        val state = rememberDatePickerState(
            initialSelectedDateMillis = initial.atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli(),
        )
        DatePickerDialog(
            onDismissRequest = { open = false },
            confirmButton = {
                TextButton(onClick = {
                    state.selectedDateMillis?.let { millis ->
                        onChange(Instant.ofEpochMilli(millis).atZone(ZoneOffset.UTC).toLocalDate().toString())
                    }
                    open = false
                }) { Text(confirmLabel) }
            },
            dismissButton = {
                TextButton(onClick = { open = false }) { Text(cancelLabel) }
            },
        ) {
            DatePicker(state = state)
        }
    }
}

/**
 * O SegmentedControl de components/ui.jsx: opcoes lado a lado, a escolhida em destaque.
 * 48 dp de altura.
 */
@Composable
fun SegmentedChoice(
    items: List<SelectOption>,
    value: String,
    onChange: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val palette = LocalPalette.current
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = palette["zinc-100"],
    ) {
        Row(modifier = Modifier.padding(4.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            items.forEach { item ->
                val active = item.value == value
                Surface(
                    selected = active,
                    onClick = { onChange(item.value) },
                    shape = RoundedCornerShape(12.dp),
                    color = if (active) palette.surface else palette["zinc-100"],
                    contentColor = if (active) palette.text else palette["zinc-600"],
                    modifier = Modifier.weight(1f).heightIn(min = 48.dp),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text(
                            text = item.label,
                            style = MaterialTheme.typography.labelLarge,
                            fontWeight = FontWeight.SemiBold,
                        )
                    }
                }
            }
        }
    }
}
