package br.financas.app.ui.lancamentos

import android.app.Application
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.core.formatCurrency
import br.financas.app.data.InboxWrite
import br.financas.app.rules.ShareForm
import br.financas.app.rules.Sharing
import br.financas.app.ui.components.AppIcons
import br.financas.app.ui.components.AppTextField
import br.financas.app.ui.components.Field
import br.financas.app.ui.components.FitText
import br.financas.app.ui.components.Panel
import br.financas.app.ui.components.SelectField
import br.financas.app.ui.components.SelectOption
import br.financas.app.ui.home.HomeLogic
import br.financas.app.ui.theme.LocalPalette
import java.math.BigDecimal

/** As abas de Lancamentos que este APK tem em nativo (a ordem da web: lib/navigation.js). */
enum class LancamentosTab { EXTRATO, APROVAR, CARTOES }

/** O texto de uma escrita que nao deu (ou null quando deu): a mensagem do servidor, como chegou. */
fun writeErrorOf(app: Application, result: InboxWrite<*>, fallback: Int): String? = when (result) {
    is InboxWrite.Done<*> -> null
    is InboxWrite.Offline -> app.getString(R.string.lanc_offline_action)
    is InboxWrite.SessionExpired -> result.message ?: app.getString(R.string.data_session_expired)
    is InboxWrite.Conflict -> result.message ?: app.getString(fallback)
    is InboxWrite.Refused -> result.message ?: app.getString(fallback)
}

/** Um valor de saldo: mascarado no modo privado (MASKED_CURRENCY). */
fun moneyOrMasked(value: BigDecimal?, hidden: Boolean): String =
    if (hidden) HomeLogic.MASKED_CURRENCY else formatCurrency(value)

/**
 * O topo de Extrato e Cartoes: voltar, o titulo, o olho do modo privado e as abas nativas de
 * Lancamentos (tocar numa troca de pagina sem passar pela WebView).
 */
@Composable
fun LancamentosTopBar(
    title: String,
    current: LancamentosTab,
    hidden: Boolean,
    onBack: () -> Unit,
    onToggleHidden: () -> Unit,
    onTab: (LancamentosTab) -> Unit,
    inboxCount: Int = 0,
) {
    val palette = LocalPalette.current
    val backLabel = stringResource(R.string.native_back)
    Column(
        Modifier
            .fillMaxWidth()
            .windowInsetsPadding(WindowInsets.statusBars)
            .padding(horizontal = 8.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Surface(
                onClick = onBack,
                shape = RoundedCornerShape(50),
                color = palette.background,
                contentColor = palette.text,
                modifier = Modifier.size(48.dp).semantics { contentDescription = backLabel },
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Text("←", style = MaterialTheme.typography.titleLarge, color = palette.text)
                }
            }
            Text(
                text = title,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.ExtraBold,
                color = palette.text,
                modifier = Modifier.padding(start = 8.dp).weight(1f),
            )
            val eyeLabel = stringResource(if (hidden) R.string.lanc_show_values else R.string.lanc_hide_values)
            Surface(
                onClick = onToggleHidden,
                shape = CircleShape,
                color = if (hidden) palette["emerald-50"] else palette.surface,
                border = BorderStroke(1.dp, if (hidden) palette.accent.copy(alpha = 0.35f) else palette.border),
                modifier = Modifier.size(48.dp).semantics { contentDescription = eyeLabel },
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(
                        imageVector = if (hidden) AppIcons.EyeOff else AppIcons.Eye,
                        contentDescription = null,
                        tint = if (hidden) palette["emerald-700"] else palette["zinc-700"],
                        modifier = Modifier.size(20.dp),
                    )
                }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(horizontal = 8.dp)) {
            TabChip(stringResource(R.string.lanc_tab_extrato), current == LancamentosTab.EXTRATO) { onTab(LancamentosTab.EXTRATO) }
            val aprovar = stringResource(R.string.lanc_tab_aprovar)
            TabChip(if (inboxCount > 0) "$aprovar · $inboxCount" else aprovar, current == LancamentosTab.APROVAR) { onTab(LancamentosTab.APROVAR) }
            TabChip(stringResource(R.string.lanc_tab_cartoes), current == LancamentosTab.CARTOES) { onTab(LancamentosTab.CARTOES) }
        }
    }
}

@Composable
private fun TabChip(label: String, active: Boolean, onClick: () -> Unit) {
    val palette = LocalPalette.current
    Surface(
        onClick = { if (!active) onClick() },
        shape = RoundedCornerShape(50),
        color = if (active) palette["zinc-900"] else palette.surface,
        contentColor = if (active) palette["zinc-50"] else palette["zinc-700"],
        border = if (active) null else BorderStroke(1.dp, palette.border),
        modifier = Modifier.heightIn(min = 48.dp),
    ) {
        Box(contentAlignment = Alignment.Center, modifier = Modifier.padding(horizontal = 16.dp)) {
            Text(label, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, maxLines = 1)
        }
    }
}

/**
 * O ProjectionHeader da web (Extrato e Cartoes): "Saldo em contas" em destaque e as duas
 * projecoes. Sao saldos: somem no modo privado, e o vermelho de negativo some junto.
 */
@Composable
fun ProjectionHeader(
    balance: BigDecimal,
    nextMonth: BigDecimal,
    global: BigDecimal,
    hidden: Boolean,
    estimated: Boolean = false,
) {
    val palette = LocalPalette.current
    fun tone(value: BigDecimal) = if (!hidden && value.signum() < 0) palette.loss else palette.text
    Panel {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(stringResource(R.string.lanc_balance), color = palette.muted, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                FitText(text = moneyOrMasked(balance, hidden), maxSize = 30.sp, minSize = 20.sp, color = tone(balance))
                Text(
                    stringResource(if (estimated) R.string.lanc_balance_estimated else R.string.lanc_balance_confirmed),
                    color = palette.muted,
                    fontSize = 12.sp,
                )
            }
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Figure(stringResource(R.string.lanc_projection_next), stringResource(R.string.lanc_projection_next_hint), moneyOrMasked(nextMonth, hidden), tone(nextMonth), Modifier.weight(1f))
                Figure(stringResource(R.string.lanc_projection_global), stringResource(R.string.lanc_projection_global_hint), moneyOrMasked(global, hidden), tone(global), Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun Figure(label: String, hint: String, value: String, color: androidx.compose.ui.graphics.Color, modifier: Modifier) {
    val palette = LocalPalette.current
    Column(modifier, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(label, color = palette.muted, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
        FitText(text = value, maxSize = 18.sp, minSize = 12.sp, color = color, fontWeight = FontWeight.Bold)
        Text(hint, color = palette.muted, fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

/**
 * "De quem é?" (ShareFields da web): so minha, dividida ou de outra pessoa, o nome e a parte dela.
 * A parte e digitada com virgula (o teclado do celular); quem salva a le com parseMoneyInput.
 */
@Composable
fun ShareFields(form: ShareForm, onChange: (ShareForm) -> Unit, income: Boolean = false, enabled: Boolean = true) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Field(label = stringResource(R.string.lanc_share_who)) {
            SelectField(
                value = form.shareMode.orEmpty(),
                options = Sharing.SHARE_OPTIONS.map { SelectOption(it.value, it.label) },
                onSelect = { if (enabled) onChange(form.copy(shareMode = it)) },
            )
        }
        if (!form.shareMode.isNullOrEmpty()) {
            Field(
                label = stringResource(R.string.lanc_share_person),
                hint = stringResource(if (income) R.string.lanc_share_person_hint_income else R.string.lanc_share_person_hint_expense),
            ) {
                AppTextField(value = form.sharePerson.orEmpty(), onValueChange = { if (enabled) onChange(form.copy(sharePerson = it.take(120))) })
            }
        }
        if (form.shareMode == Sharing.SPLIT) {
            Field(label = stringResource(R.string.lanc_share_part)) {
                AppTextField(
                    value = form.shareOthersAmount.orEmpty(),
                    onValueChange = { if (enabled) onChange(form.copy(shareOthersAmount = it)) },
                    keyboardType = KeyboardType.Decimal,
                )
            }
        }
    }
}

/**
 * A divisao digitada pronta para shareFormError/sharePayload: "12,5" vira "12.5" (o Number do
 * JS recusaria a virgula, que e o que o teclado do celular escreve).
 */
fun normalizedShare(form: ShareForm): ShareForm {
    val text = form.shareOthersAmount ?: return form
    val parsed = br.financas.app.core.parseMoneyInput(text)
    return if (parsed is br.financas.app.core.MoneyInput.Amount) form.copy(shareOthersAmount = parsed.value.toPlainString()) else form
}
