package br.financas.app.ui.lancamentos

import android.app.Application
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import br.financas.app.R
import br.financas.app.data.AttachmentDto
import br.financas.app.data.AttachmentOwner
import br.financas.app.data.InboxWrite
import br.financas.app.data.LancamentosRepository
import br.financas.app.rules.ExtratoRules
import br.financas.app.ui.components.AlertMessage
import br.financas.app.ui.components.AppButton
import br.financas.app.ui.components.AppIcons
import br.financas.app.ui.components.AppSheet
import br.financas.app.ui.components.ButtonVariant
import br.financas.app.ui.components.ConfirmRequest
import br.financas.app.ui.components.EmptyState
import br.financas.app.ui.components.MenuAction
import br.financas.app.ui.components.OverflowMenu
import br.financas.app.ui.theme.LocalPalette
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch

/**
 * Os comprovantes abertos (o AttachmentsSheet da web), de um lancamento ou de uma compra:
 * listar, anexar (camera ou arquivo, varios de uma vez), abrir em tela cheia, compartilhar e
 * excluir. Tudo so com o servidor. [onChanged] roda ao fechar se algo mudou (a lista rele).
 */
class AttachmentsState(
    private val app: Application,
    private val repo: LancamentosRepository,
    private val scope: CoroutineScope,
    private val confirm: (ConfirmRequest) -> Unit,
    private val onChanged: () -> Unit,
) {
    var owner by mutableStateOf<AttachmentOwner?>(null)
        private set
    var description by mutableStateOf("")
        private set
    var items by mutableStateOf<List<AttachmentDto>?>(null)
        private set
    var error by mutableStateOf("")
        private set
    var uploading by mutableStateOf(false)
        private set
    var busyId by mutableStateOf("")
        private set

    private var changed = false

    fun open(owner: AttachmentOwner, description: String) {
        this.owner = owner
        this.description = description
        items = null
        error = ""
        changed = false
        reload()
    }

    fun close() {
        if (uploading) return
        owner = null
        if (changed) onChanged()
        changed = false
    }

    fun dismissError() {
        error = ""
    }

    private fun reload() {
        val target = owner ?: return
        scope.launch {
            when (val result = repo.attachments(target)) {
                is InboxWrite.Done -> if (owner == target) items = result.value
                else -> if (owner == target) {
                    items = items ?: emptyList()
                    error = writeErrorOf(app, result, R.string.attach_load_failed).orEmpty()
                }
            }
        }
    }

    /** Sobe os arquivos um a um; os grandes demais nem saem do aparelho. */
    fun upload(files: List<PickedFile>) {
        val target = owner ?: return
        if (uploading) return
        uploading = true
        error = ""
        scope.launch {
            val problems = mutableListOf<String>()
            for (file in files) {
                val bytes = file.bytes
                if (bytes == null) {
                    problems += app.getString(R.string.attach_too_big, file.name)
                    continue
                }
                val result = repo.uploadAttachment(target, file.name, file.mimeType, bytes)
                if (result is InboxWrite.Done) {
                    changed = true
                } else {
                    val message = writeErrorOf(app, result, R.string.attach_failed) ?: ""
                    problems += if (result is InboxWrite.Refused || result is InboxWrite.Conflict) "${file.name}: $message" else message
                    if (result is InboxWrite.Offline || result is InboxWrite.SessionExpired) break
                }
            }
            uploading = false
            error = problems.distinct().joinToString(" ")
            reload()
        }
    }

    /** Baixa e entrega ao app que o Android escolher (abrir em tela cheia ou compartilhar). */
    fun deliver(item: AttachmentDto, share: Boolean) {
        val target = owner ?: return
        busyId = item.id
        error = ""
        scope.launch {
            when (val result = repo.attachmentFile(target, item.id)) {
                is InboxWrite.Done -> {
                    val mime = item.contentType ?: result.value.contentType ?: NativeFiles.mimeOf(item.originalName)
                    val uri = NativeFiles.stage(app, result.value.bytes, item.originalName.ifBlank { "comprovante" })
                    if (share) {
                        NativeFiles.share(app, uri, mime, item.originalName)
                    } else if (!NativeFiles.open(app, uri, mime)) {
                        error = app.getString(R.string.attach_no_viewer)
                    }
                }
                else -> error = writeErrorOf(app, result, R.string.attach_open_failed).orEmpty()
            }
            busyId = ""
        }
    }

    fun delete(item: AttachmentDto) {
        val target = owner ?: return
        confirm(
            ConfirmRequest(
                title = app.getString(R.string.attach_delete_title),
                message = app.getString(R.string.attach_delete_message, item.originalName),
                confirmLabel = app.getString(R.string.attach_delete),
            ) {
                busyId = item.id
                scope.launch {
                    val result = repo.deleteAttachment(target, item.id)
                    busyId = ""
                    if (result is InboxWrite.Done) {
                        changed = true
                        reload()
                    } else {
                        error = writeErrorOf(app, result, R.string.attach_delete_failed).orEmpty()
                    }
                }
            },
        )
    }
}

/** O sheet "Comprovantes". */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AttachmentsSheet(state: AttachmentsState) {
    if (state.owner == null) return
    val palette = LocalPalette.current
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val picker = rememberReceiptPicker(onPicked = state::upload)
    AppSheet(
        title = stringResource(R.string.attach_title),
        sheetState = sheetState,
        onDismiss = state::close,
        footer = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                AppButton(
                    text = stringResource(R.string.attach_photo),
                    onClick = picker.takePhoto,
                    variant = ButtonVariant.SECONDARY,
                    enabled = !state.uploading,
                    modifier = Modifier.weight(1f),
                )
                AppButton(
                    text = stringResource(if (state.uploading) R.string.attach_uploading else R.string.attach_file),
                    onClick = picker.pickFiles,
                    loading = state.uploading,
                    modifier = Modifier.weight(1f),
                )
            }
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (state.description.isNotEmpty()) Text(state.description, color = palette["zinc-600"], fontSize = 14.sp)
            AlertMessage(message = state.error, dismissLabel = stringResource(R.string.lanc_dismiss), onDismiss = state::dismissError)
            val items = state.items
            when {
                items == null -> Text(stringResource(R.string.attach_loading), color = palette.muted, fontSize = 14.sp)
                items.isEmpty() -> EmptyState(
                    title = stringResource(R.string.attach_empty_title),
                    message = stringResource(R.string.attach_empty_message),
                )
                else -> Column {
                    items.forEachIndexed { index, item ->
                        if (index > 0) HorizontalDivider(color = palette["zinc-100"])
                        AttachmentRow(item, state)
                    }
                }
            }
        }
    }
}

@Composable
private fun AttachmentRow(item: AttachmentDto, state: AttachmentsState) {
    val palette = LocalPalette.current
    val busy = state.busyId == item.id
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
    ) {
        Icon(AppIcons.Paperclip, contentDescription = null, tint = palette.muted, modifier = Modifier.size(20.dp))
        Column(Modifier.weight(1f)) {
            Text(item.originalName, color = palette.text, fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(ExtratoRules.attachmentDetail(item.contentType, item.sizeBytes), color = palette.muted, fontSize = 12.sp)
        }
        AppButton(
            text = stringResource(R.string.attach_open),
            onClick = { state.deliver(item, share = false) },
            variant = ButtonVariant.SUBTLE,
            loading = busy,
        )
        OverflowMenu(
            label = stringResource(R.string.lanc_actions_of, item.originalName),
            enabled = !busy,
            actions = listOf(
                MenuAction(stringResource(R.string.attach_share)) { state.deliver(item, share = true) },
                MenuAction(stringResource(R.string.attach_delete)) { state.delete(item) },
            ),
        )
    }
}
