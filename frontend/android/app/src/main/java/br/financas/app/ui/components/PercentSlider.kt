package br.financas.app.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.BorderStroke
import br.financas.app.rules.MonthlyPlan
import br.financas.app.ui.theme.LocalPalette
import java.math.BigDecimal
import java.math.RoundingMode

/**
 * O PercentSlider de components/ui.jsx: um % escolhido de 1 em 1 ponto, nunca digitado, com − e +
 * dos lados e [aside] (o R$ ao vivo) ao lado do valor. [room] e quanto ainda cabe
 * (MonthlyPlan.percentRoom): o controle nao passa dele. [value] null e "em branco" ("—"; o plano
 * antigo que o servidor converte). Um toque de vibracao a cada ponto e ao bater no limite.
 * O Float e so a posicao do dedo; o valor e BigDecimal (MonthlyPlan.clampPercent/stepPercent).
 */
@Composable
fun PercentSlider(
    label: String,
    value: BigDecimal?,
    onChange: (BigDecimal) -> Unit,
    room: BigDecimal,
    modifier: Modifier = Modifier,
    aside: String? = null,
    hint: String? = null,
    enabled: Boolean = true,
) {
    val palette = LocalPalette.current
    val haptic = LocalHapticFeedback.current
    val shown = value ?: BigDecimal.ZERO
    val shownText = if (value == null) "—" else MonthlyPlan.formatPlanPercent(value)
    fun emit(next: BigDecimal) {
        if (next.compareTo(shown) == 0 && value != null) return
        haptic.performHapticFeedback(HapticFeedbackType.TextHandleMove)
        if (next.compareTo(room) == 0) haptic.performHapticFeedback(HapticFeedbackType.LongPress)
        onChange(next)
    }
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(label, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold, color = palette["zinc-700"], modifier = Modifier.weight(1f))
            Text(shownText, fontSize = 18.sp, fontWeight = FontWeight.Bold, color = palette.text)
            if (aside != null) Text(aside, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = palette["zinc-600"])
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            StepButton("Diminuir $label", enabled && shown.signum() > 0, minus = true) {
                emit(MonthlyPlan.stepPercent(shown, -1, room))
            }
            Slider(
                value = shown.toFloat(),
                onValueChange = { position ->
                    val point = BigDecimal(position.toDouble()).setScale(0, RoundingMode.HALF_UP)
                    emit(MonthlyPlan.clampPercent(point, room))
                },
                valueRange = 0f..100f,
                steps = 99,
                enabled = enabled,
                colors = SliderDefaults.colors(
                    thumbColor = palette.accent,
                    activeTrackColor = palette.accent,
                    inactiveTrackColor = palette["zinc-200"],
                    activeTickColor = palette.accent.copy(alpha = 0f),
                    inactiveTickColor = palette["zinc-200"].copy(alpha = 0f),
                ),
                modifier = Modifier.weight(1f).semantics {
                    contentDescription = label
                    stateDescription = if (value == null) "em branco" else shownText
                },
            )
            StepButton("Aumentar $label", enabled && shown < room, minus = false) {
                emit(MonthlyPlan.stepPercent(shown, 1, room))
            }
        }
        if (hint != null) Text(hint, style = MaterialTheme.typography.labelMedium, color = palette.muted)
    }
}

@Composable
private fun StepButton(label: String, enabled: Boolean, minus: Boolean, onClick: () -> Unit) {
    val palette = LocalPalette.current
    Surface(
        onClick = onClick,
        enabled = enabled,
        shape = CircleShape,
        color = palette.surface,
        border = BorderStroke(1.dp, palette.border),
        modifier = Modifier.size(48.dp).semantics { contentDescription = label },
    ) {
        Box(contentAlignment = Alignment.Center) {
            Icon(
                imageVector = if (minus) AppIcons.Minus else AppIcons.Plus,
                contentDescription = null,
                tint = if (enabled) palette["zinc-700"] else palette["zinc-300"],
                modifier = Modifier.size(18.dp),
            )
        }
    }
}
