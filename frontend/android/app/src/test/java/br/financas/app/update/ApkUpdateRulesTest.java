package br.financas.app.update;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertThrows;
import static org.junit.Assert.assertTrue;

import org.json.JSONObject;
import org.junit.Test;

public class ApkUpdateRulesTest {

    private static final String SHA = "ab".repeat(32);

    private static JSONObject manifest() throws Exception {
        JSONObject json = new JSONObject();
        json.put("version_code", 10012);
        json.put("version_name", "2026.10.17-abc1234");
        json.put("native_level", 2);
        json.put("sha256", SHA);
        json.put("size", 9_000_000);
        json.put("file", "financas-10012.apk");
        return json;
    }

    @Test
    public void leOManifestoInteiro() throws Exception {
        ApkUpdateRules.Latest latest = ApkUpdateRules.parse(manifest());
        assertEquals(10012, latest.versionCode);
        assertEquals(2, latest.nativeLevel);
        assertEquals("/apk/financas-10012.apk", latest.path());
    }

    @Test
    public void recusaManifestoIncompleto() throws Exception {
        for (String key : new String[] { "version_code", "native_level", "sha256", "size", "file" }) {
            JSONObject json = manifest();
            json.remove(key);
            assertThrows(key, IllegalArgumentException.class, () -> ApkUpdateRules.parse(json));
        }
    }

    @Test
    public void recusaNomeQueSaiDaPasta() throws Exception {
        for (String file : new String[] { "../financas-1.apk", "financas-1.apk/x", "outro.apk", "financas-.apk", "financas-1.zip" }) {
            JSONObject json = manifest();
            json.put("file", file);
            assertThrows(file, IllegalArgumentException.class, () -> ApkUpdateRules.parse(json));
        }
    }

    @Test
    public void recusaTamanhoESha256Implausiveis() throws Exception {
        JSONObject huge = manifest();
        huge.put("size", ApkUpdateRules.MAX_APK_BYTES + 1);
        assertThrows(IllegalArgumentException.class, () -> ApkUpdateRules.parse(huge));
        JSONObject upper = manifest();
        upper.put("sha256", SHA.toUpperCase());
        assertThrows(IllegalArgumentException.class, () -> ApkUpdateRules.parse(upper));
    }

    @Test
    public void soOfereceUmVersionCodeMaior() throws Exception {
        ApkUpdateRules.Latest latest = ApkUpdateRules.parse(manifest());
        assertTrue(ApkUpdateRules.isNewer(latest, 213));
        assertFalse(ApkUpdateRules.isNewer(latest, 10012));
        assertFalse(ApkUpdateRules.isNewer(latest, 10013));
        assertFalse(ApkUpdateRules.isNewer(null, 1));
    }

    @Test
    public void oArquivoBaixadoPrecisaSerOAnunciado() throws Exception {
        ApkUpdateRules.Latest latest = ApkUpdateRules.parse(manifest());
        assertTrue(ApkUpdateRules.matchesArchive(latest, "br.financas.app", "br.financas.app", 10012));
        assertFalse(ApkUpdateRules.matchesArchive(latest, "br.financas.app", "outro.app", 10012));
        assertFalse(ApkUpdateRules.matchesArchive(latest, "br.financas.app", "br.financas.app", 10011));
        assertFalse(ApkUpdateRules.matchesArchive(latest, "br.financas.app", null, 10012));
    }
}
