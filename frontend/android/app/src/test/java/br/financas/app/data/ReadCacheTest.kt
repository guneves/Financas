package br.financas.app.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.time.ZoneId

class ReadCacheTest {

    @get:Rule
    val folder = TemporaryFolder()

    private var now = 1_000L
    private fun cache(dir: File = File(folder.root, "cache")) = FileReadCache(dir) { now }

    @Test
    fun nothingStoredReadsNull() {
        assertNull(cache().get("u1 /api/accounts"))
    }

    @Test
    fun storesTheBodyAndItsTime() {
        val cache = cache()
        val stored = cache.put("u1 /api/accounts", """[{"id":"a"}]""")
        assertEquals(1_000L, stored.storedAt)
        assertEquals(CachedBody("""[{"id":"a"}]""", 1_000L), cache.get("u1 /api/accounts"))
    }

    @Test
    fun aNewerBodyReplacesTheOldOne() {
        val cache = cache()
        cache.put("u1 /api/accounts", "[1]")
        now = 2_000L
        cache.put("u1 /api/accounts", "[2]")
        assertEquals(CachedBody("[2]", 2_000L), cache.get("u1 /api/accounts"))
        // Nenhum temporario fica para tras.
        val names = File(folder.root, "cache").list()!!.toList()
        assertEquals(1, names.size)
        assertTrue(names[0].endsWith(".json"))
    }

    @Test
    fun keysAreSeparate() {
        val cache = cache()
        cache.put("u1 /api/accounts", "[1]")
        cache.put("u1 /api/accounts?include_archived=1", "[1,2]")
        cache.put("u2 /api/accounts", "[3]")
        assertEquals("[1]", cache.get("u1 /api/accounts")?.body)
        assertEquals("[1,2]", cache.get("u1 /api/accounts?include_archived=1")?.body)
        assertEquals("[3]", cache.get("u2 /api/accounts")?.body)
    }

    @Test
    fun bodiesWithLineBreaksAndAccentsSurvive() {
        val cache = cache()
        val body = "[\n  {\"name\": \"Alimentação\"}\n]"
        cache.put("k", body)
        assertEquals(body, cache.get("k")?.body)
    }

    @Test
    fun survivesANewInstance() {
        cache().put("k", "[1]")
        assertEquals(CachedBody("[1]", 1_000L), cache().get("k"))
    }

    @Test
    fun aDamagedFileIsIgnored() {
        val dir = File(folder.root, "cache")
        val cache = cache(dir)
        cache.put("k", "[1]")
        dir.listFiles()!!.single().writeText("lixo")
        assertNull(cache.get("k"))
    }

    @Test
    fun clearRemovesEverything() {
        val cache = cache()
        cache.put("a", "1")
        cache.put("b", "2")
        cache.clear()
        assertNull(cache.get("a"))
        assertNull(cache.get("b"))
    }

    @Test
    fun formatRoundTrip() {
        val text = FileReadCache.encode("k", CachedBody("x\ny", 5L))
        assertEquals(CachedBody("x\ny", 5L), FileReadCache.decode("k", text))
        assertNull(FileReadCache.decode("outra", text))
        assertNull(FileReadCache.decode("k", "v0\n5\nk\nx"))
    }

    @Test
    fun storedTimeIsLocalHoursAndMinutes() {
        // 2026-10-22T17:03:00Z = 14:03 em Sao Paulo.
        val millis = java.time.Instant.parse("2026-10-22T17:03:00Z").toEpochMilli()
        assertEquals("14:03", storedTimeLabel(millis, ZoneId.of("America/Sao_Paulo")))
    }
}
