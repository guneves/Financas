package br.financas.app.ui.lancamentos

import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import android.webkit.MimeTypeMap
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/** Um arquivo escolhido (ou fotografado) para virar comprovante. [bytes] null = grande demais. */
class PickedFile(val name: String, val mimeType: String, val bytes: ByteArray?)

/** A camera e o seletor de arquivos dos comprovantes (o input type=file da web). */
class ReceiptPicker(val pickFiles: () -> Unit, val takePhoto: () -> Unit)

/**
 * Arquivos das telas nativas: a foto da camera direto para "Comprovantes", o seletor do Android
 * (PDF ou imagem, varios de uma vez), e a exportacao e os comprovantes saindo pela folha de
 * compartilhar do Android (no lugar do download do navegador). Tudo passa pelo FileProvider do
 * app (cache-path de res/xml/file_paths.xml), numa pasta que cada uso limpa.
 */
object NativeFiles {
    /** O limite da web (AttachmentsSheet): o servidor decide, isto so evita subir 200 MB para ouvir "nao". */
    const val MAX_BYTES = 10L * 1024 * 1024

    private const val DIR = "native-files"

    private fun folder(context: Context): File = File(context.cacheDir, DIR).apply { mkdirs() }

    private fun authority(context: Context) = context.packageName + ".fileprovider"

    /** Um arquivo novo na pasta temporaria, com um nome seguro. */
    fun tempFile(context: Context, name: String): File {
        val safe = name.replace(Regex("[\\\\/:*?\"<>|]"), "_").ifBlank { "arquivo" }
        return File(folder(context), safe)
    }

    fun uriFor(context: Context, file: File): Uri = FileProvider.getUriForFile(context, authority(context), file)

    /** Le um content:// escolhido: o nome, o tipo e os bytes (null acima de [MAX_BYTES]). */
    suspend fun read(context: Context, uri: Uri, fallbackName: String = "comprovante"): PickedFile? = withContext(Dispatchers.IO) {
        val resolver = context.contentResolver
        var name = fallbackName
        var size = -1L
        runCatching {
            resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) {
                    val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    val sizeIndex = cursor.getColumnIndex(OpenableColumns.SIZE)
                    if (nameIndex >= 0) cursor.getString(nameIndex)?.let { name = it }
                    if (sizeIndex >= 0 && !cursor.isNull(sizeIndex)) size = cursor.getLong(sizeIndex)
                }
            }
        }
        val mime = resolver.getType(uri) ?: mimeOf(name)
        if (size > MAX_BYTES) return@withContext PickedFile(name, mime, null)
        val bytes = runCatching { resolver.openInputStream(uri)?.use { it.readBytes() } }.getOrNull() ?: return@withContext null
        PickedFile(name, mime, if (bytes.size > MAX_BYTES) null else bytes)
    }

    fun mimeOf(name: String): String =
        MimeTypeMap.getSingleton().getMimeTypeFromExtension(name.substringAfterLast('.', "").lowercase()) ?: "application/octet-stream"

    /** Grava [bytes] na pasta temporaria e devolve o content:// dele. */
    suspend fun stage(context: Context, bytes: ByteArray, name: String): Uri = withContext(Dispatchers.IO) {
        val file = tempFile(context, name)
        file.writeBytes(bytes)
        uriFor(context, file)
    }

    /** A folha de compartilhar do Android com o arquivo (exportacao, comprovante). */
    fun share(context: Context, uri: Uri, mimeType: String, title: String) {
        val send = Intent(Intent.ACTION_SEND)
            .setType(mimeType)
            .putExtra(Intent.EXTRA_STREAM, uri)
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        send.clipData = ClipData.newRawUri(title, uri)
        context.startActivity(Intent.createChooser(send, title).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    /** Abre o arquivo em tela cheia no app que o Android escolher; false sem nenhum que abra. */
    fun open(context: Context, uri: Uri, mimeType: String): Boolean {
        val view = Intent(Intent.ACTION_VIEW)
            .setDataAndType(uri, mimeType)
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        return try {
            context.startActivity(view)
            true
        } catch (error: ActivityNotFoundException) {
            false
        }
    }
}

