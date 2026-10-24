package br.financas.app.ui.lancamentos

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * O seletor e a camera, prontos para um botao: [onPicked] recebe os arquivos lidos (os grandes
 * demais com bytes null, para a tela dizer "passa de 10 MB"). A foto vai para um arquivo do
 * FileProvider (nada de permissao de camera: quem fotografa e o app de camera); o nome dela
 * sobrevive a Activity recriada enquanto a camera esta aberta.
 */
@Composable
fun rememberReceiptPicker(onPicked: (List<PickedFile>) -> Unit): ReceiptPicker {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val deliver by rememberUpdatedState(onPicked)
    var photoName by rememberSaveable { mutableStateOf("") }

    val files = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        if (uris.isEmpty()) return@rememberLauncherForActivityResult
        scope.launch {
            val picked = uris.mapNotNull { NativeFiles.read(context, it) }
            if (picked.isNotEmpty()) deliver(picked)
        }
    }
    val camera = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { saved ->
        val name = photoName
        photoName = ""
        if (!saved || name.isEmpty()) return@rememberLauncherForActivityResult
        val file = NativeFiles.tempFile(context, name)
        scope.launch {
            val bytes = withContext(Dispatchers.IO) { runCatching { file.readBytes() }.getOrNull() }
            if (bytes != null && bytes.isNotEmpty()) {
                deliver(listOf(PickedFile(name, "image/jpeg", if (bytes.size > NativeFiles.MAX_BYTES) null else bytes)))
            }
        }
    }
    return ReceiptPicker(
        pickFiles = { files.launch(arrayOf("application/pdf", "image/*")) },
        takePhoto = {
            val name = "foto-${System.currentTimeMillis()}.jpg"
            photoName = name
            runCatching { camera.launch(NativeFiles.uriFor(context, NativeFiles.tempFile(context, name))) }
        },
    )
}
