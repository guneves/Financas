package br.financas.app.data

import java.io.File
import java.io.IOException
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/** A ultima resposta boa de uma leitura e quando ela foi guardada (epoch em ms). */
data class CachedBody(val body: String, val storedAt: Long)

/**
 * A ultima resposta boa de cada leitura, para a tela abrir na hora e funcionar sem rede
 * ("atualizado as HH:MM"). A chave e o usuario + caminho + query do pedido.
 */
interface ReadCache {
    fun get(key: String): CachedBody?
    fun put(key: String, body: String): CachedBody
    fun clear()
}

/**
 * Um arquivo por chave em [dir] (o nome e o SHA-256 da chave). Grava num arquivo temporario e
 * renomeia por cima: uma leitura nunca ve um arquivo pela metade. O formato:
 * "v1\n<epoch ms>\n<chave>\n<corpo>"; a chave guardada confere com a pedida.
 */
class FileReadCache(
    private val dir: File,
    private val clock: () -> Long = System::currentTimeMillis,
) : ReadCache {

    override fun get(key: String): CachedBody? = synchronized(this) {
        val file = fileFor(key)
        if (!file.isFile) return null
        val text = try {
            file.readText(StandardCharsets.UTF_8)
        } catch (error: IOException) {
            return null
        }
        return decode(key, text)
    }

    override fun put(key: String, body: String): CachedBody = synchronized(this) {
        val entry = CachedBody(body, clock())
        try {
            if (!dir.isDirectory && !dir.mkdirs() && !dir.isDirectory) return entry
            val target = fileFor(key)
            val temp = File(dir, target.name + ".tmp")
            temp.writeText(encode(key, entry), StandardCharsets.UTF_8)
            if (!temp.renameTo(target)) {
                // No Android (Linux) o rename substitui de uma vez; so outros sistemas caem aqui.
                target.delete()
                if (!temp.renameTo(target)) temp.delete()
            }
        } catch (error: IOException) {
            // Cache e so conforto: falhar ao gravar nao derruba a leitura que deu certo.
        }
        return entry
    }

    override fun clear() = synchronized(this) {
        dir.listFiles()?.forEach { it.delete() }
        Unit
    }

    private fun fileFor(key: String): File = File(dir, sha256(key) + ".json")

    companion object {
        private const val VERSION = "v1"

        internal fun encode(key: String, entry: CachedBody): String =
            "$VERSION\n${entry.storedAt}\n${key.replace('\n', ' ')}\n${entry.body}"

        internal fun decode(key: String, text: String): CachedBody? {
            val parts = text.split('\n', limit = 4)
            if (parts.size < 4 || parts[0] != VERSION) return null
            val storedAt = parts[1].toLongOrNull() ?: return null
            if (parts[2] != key.replace('\n', ' ')) return null
            return CachedBody(parts[3], storedAt)
        }

        private fun sha256(text: String): String =
            MessageDigest.getInstance("SHA-256")
                .digest(text.toByteArray(StandardCharsets.UTF_8))
                .joinToString("") { "%02x".format(it) }
    }
}

/** "14:03", a hora local em que a copia foi guardada (para "atualizado às HH:MM"). */
fun storedTimeLabel(storedAt: Long, zone: ZoneId = ZoneId.systemDefault()): String =
    DateTimeFormatter.ofPattern("HH:mm").format(Instant.ofEpochMilli(storedAt).atZone(zone))
