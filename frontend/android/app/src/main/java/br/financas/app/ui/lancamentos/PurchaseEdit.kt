package br.financas.app.ui.lancamentos

import android.app.Application
import android.widget.Toast
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.SheetValue
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.data.LancamentosRepository
import br.financas.app.rules.CardRules
import br.financas.app.rules.CategoryOption
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.AppSheet
import br.financas.app.ui.components.AppTextField
import br.financas.app.ui.components.ButtonVariant
import br.financas.app.ui.components.Field
import br.financas.app.ui.components.SelectField
import br.financas.app.ui.components.SelectOption
import br.financas.app.ui.theme.LocalPalette
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch

/**
 * A compra no sheet "Editar compra": categoria e descricao. No credito (`debit` false) vale para
 * todas as parcelas (PATCH /api/cc-expenses/purchases/<id>); no debito e o lancamento da conta (049).
 * O CardPurchaseEditSheet.jsx da web.
 */
data class EditTarget(
    val id: String,
    val debit: Boolean,
    val refund: Boolean,
    val subtitle: String,
    val currentDescription: String?,
    val currentCategoryId: String?,
    val currentCategory: String?,
    val installments: Int,
    val description: String,
    val categoryId: String,
)

/** O estado do sheet, dividido por Cartoes e Extrato (como o AttachmentsState). */
class PurchaseEditState(
    private val app: Application,
    private val repo: LancamentosRepository,
    private val scope: CoroutineScope,
    private val isCleared: () -> Boolean,
    private val onSaved: (String) -> Unit,
) {
    var target by mutableStateOf<EditTarget?>(null)
        private set
    var busy by mutableStateOf(false)
        private set
    var error by mutableStateOf("")
        private set

    fun open(target: EditTarget) {
        error = ""
        this.target = target
    }

    fun change(target: EditTarget) {
        this.target = target
    }

    fun close() {
        if (!busy) target = null
    }

    fun save() {
        val current = target ?: return
        if (busy) return
        val result = CardRules.purchaseEditPayload(current.currentDescription, current.currentCategoryId, current.description, current.categoryId)
        val message = result.error
        if (message != null) {
            error = message
            return
        }
        val payload = result.payload
        if (payload == null) {
            target = null
            return
        }
        busy = true
        error = ""
        scope.launch {
            val write = if (current.debit) repo.updateTransaction(current.id, payload) else repo.updatePurchase(current.id, payload)
            busy = false
            val failure = writeErrorOf(app, write, R.string.cartoes_edit_failed)
            if (failure == null) {
                target = null
                onSaved(app.getString(R.string.cartoes_edit_saved))
            } else if (isCleared()) {
                Toast.makeText(app, failure, Toast.LENGTH_LONG).show()
            } else {
                error = failure
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PurchaseEditSheet(state: PurchaseEditState, categoryOptions: List<CategoryOption>) {
    val target = state.target ?: return
    val palette = LocalPalette.current
    val sheetState = rememberModalBottomSheetState(
        skipPartiallyExpanded = true,
        confirmValueChange = { value -> value != SheetValue.Hidden || !state.busy },
    )
    AppSheet(
        title = stringResource(if (target.refund) R.string.cartoes_edit_refund_title else R.string.cartoes_edit_title),
        sheetState = sheetState,
        onDismiss = state::close,
        footer = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AppButton(stringResource(R.string.lanc_cancel), state::close, Modifier.weight(1f), ButtonVariant.SECONDARY, enabled = !state.busy)
                AppButton(stringResource(R.string.lanc_save), state::save, Modifier.weight(1f), loading = state.busy)
            }
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(target.subtitle, color = palette["zinc-600"], fontSize = 14.sp)
            AlertMessage(message = state.error, dismissLabel = stringResource(R.string.lanc_dismiss))
            Field(stringResource(R.string.cartoes_edit_description)) {
                AppTextField(target.description, { state.change(target.copy(description = it)) })
            }
            val hint = if (!target.debit && target.installments > 1) stringResource(R.string.cartoes_edit_all_installments) else null
            Field(stringResource(R.string.cartoes_edit_category), hint = hint) {
                // A categoria que a compra ja tem, quando nao esta na lista (arquivada), fica como esta.
                val keep = if (categoryOptions.none { it.id == target.currentCategoryId.orEmpty() }) {
                    listOf(SelectOption(target.currentCategoryId.orEmpty(), target.currentCategory?.takeIf { it.isNotEmpty() } ?: stringResource(R.string.extrato_edit_no_category)))
                } else {
                    emptyList()
                }
                SelectField(
                    value = target.categoryId,
                    options = keep + categoryOptions.map { SelectOption(it.id, it.label) },
                    onSelect = { state.change(target.copy(categoryId = it)) },
                )
            }
            Text(stringResource(R.string.cartoes_edit_note), color = palette.muted, fontSize = 12.sp)
        }
    }
}
