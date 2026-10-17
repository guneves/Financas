package br.financas.app.notify;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotEquals;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;
import java.util.TimeZone;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;

/** As regras do leitor de notificacoes (NotifyRules). */
public class NotifyRulesTest {

    private static final TimeZone SAO_PAULO = TimeZone.getTimeZone("America/Sao_Paulo");
    // backend/validators.py: o client_id que o servidor aceita.
    private static final Pattern CLIENT_ID = Pattern.compile("^[A-Za-z0-9][A-Za-z0-9_.:-]{7,63}$");

    private static NotifyRules.Captured row(String pkg, String key, long postedAt) {
        NotifyRules.Captured row = new NotifyRules.Captured();
        row.packageName = pkg;
        row.key = key;
        row.postedAt = postedAt;
        row.receivedAt = postedAt + 5;
        return row;
    }

    @Test
    public void theOwnersAppsAreHeard() {
        for (String pkg : new String[] {
            "com.samsung.android.spay",
            "com.itau", "com.itaucard.activity",
            "br.com.bb.android", "br.com.bb.oewallet",
            "com.btg.pactual.banking",
        }) {
            assertTrue(pkg, NotifyRules.isAllowed(pkg, false));
        }
    }

    @Test
    public void everythingElseIsIgnored() {
        // O app de investimentos do BTG fica de fora de proposito.
        assertFalse(NotifyRules.isAllowed("com.btg.pactual.digital.mobile", false));
        assertFalse(NotifyRules.isAllowed("com.whatsapp", false));
        assertFalse(NotifyRules.isAllowed("br.financas.app", false));
        // So o pacote exato: nada de prefixo.
        assertFalse(NotifyRules.isAllowed("com.itau.fake", false));
        assertFalse(NotifyRules.isAllowed("com.ita", false));
        assertFalse(NotifyRules.isAllowed("", true));
        assertFalse(NotifyRules.isAllowed(null, true));
    }

    @Test
    public void theAdbShellOnlyInADebugBuild() {
        assertFalse("release", NotifyRules.isAllowed(NotifyRules.SHELL_PACKAGE, false));
        assertTrue("debug", NotifyRules.isAllowed(NotifyRules.SHELL_PACKAGE, true));
        // O debug nao abre a porta para outros apps.
        assertFalse(NotifyRules.isAllowed("com.whatsapp", true));
    }

    @Test
    public void everyAppHasAScreenLabel() {
        Set<String> packages = new HashSet<>();
        for (NotifyRules.App app : NotifyRules.APPS) {
            assertTrue("duplicado: " + app.packageName, packages.add(app.packageName));
            assertFalse(app.label.isEmpty());
        }
        assertEquals("Samsung Wallet", NotifyRules.labelFor("com.samsung.android.spay"));
        assertEquals(NotifyRules.SHELL_LABEL, NotifyRules.labelFor(NotifyRules.SHELL_PACKAGE));
        assertEquals("com.outro", NotifyRules.labelFor("com.outro"));
    }

    @Test
    public void theManifestCanSeeEveryHeardApp() throws Exception {
        // O <queries> do manifesto deixa a tela saber se cada app esta instalado (Android 11+).
        // Os testes rodam na pasta do modulo (app/).
        String manifest = new String(Files.readAllBytes(new File("src/main/AndroidManifest.xml").toPath()), StandardCharsets.UTF_8);
        Matcher queries = Pattern.compile("<queries>(.*?)</queries>", Pattern.DOTALL).matcher(manifest);
        assertTrue("manifesto sem <queries>", queries.find());
        Set<String> declared = new HashSet<>();
        Matcher pkg = Pattern.compile("<package android:name=\"([^\"]+)\"").matcher(queries.group(1));
        while (pkg.find()) declared.add(pkg.group(1));
        Set<String> heard = new HashSet<>();
        for (NotifyRules.App app : NotifyRules.APPS) heard.add(app.packageName);
        assertEquals(heard, declared);
    }

    @Test
    public void theSamePostingAlwaysGivesTheSameKey() {
        String key = "0|com.itau|42|null|10123";
        assertEquals(
            NotifyRules.dedupKey("com.itau", key, 1792236000123L),
            NotifyRules.dedupKey("com.itau", key, 1792236000123L));
    }

    @Test
    public void anyPartChangesTheKey() {
        String base = NotifyRules.dedupKey("com.itau", "k", 1000L);
        assertNotEquals(base, NotifyRules.dedupKey("com.itaucard.activity", "k", 1000L));
        assertNotEquals(base, NotifyRules.dedupKey("com.itau", "k2", 1000L));
        // Atualizada pelo banco = postada de novo, outra hora: outra linha.
        assertNotEquals(base, NotifyRules.dedupKey("com.itau", "k", 1001L));
        // Os separadores impedem que "ab"+"c" e "a"+"bc" colidam.
        assertNotEquals(NotifyRules.dedupKey("ab", "c", 1L), NotifyRules.dedupKey("a", "bc", 1L));
    }

    @Test
    public void theKeyFitsTheServersClientId() {
        String key = NotifyRules.dedupKey("com.samsung.android.spay", "0|com.samsung.android.spay|7|null|10200", 1L);
        assertEquals(64, key.length());
        assertTrue(CLIENT_ID.matcher(key).matches());
        assertTrue(CLIENT_ID.matcher(NotifyRules.dedupKey(null, null, 0L)).matches());
    }

    @Test
    public void bigTextWinsWhenItCarriesSomething() {
        assertEquals("Compra aprovada em PADARIA CENTRAL LTDA",
            NotifyRules.bestText("Compra aprovada em PADARIA...", "Compra aprovada em PADARIA CENTRAL LTDA"));
        assertEquals("curto", NotifyRules.bestText("curto", null));
        assertEquals("curto", NotifyRules.bestText("curto", "  \n"));
        assertNull(NotifyRules.bestText(null, null));
    }

    @Test
    public void theJsonExportKeepsEveryFieldWordForWord() throws Exception {
        NotifyRules.Captured wallet = row("com.samsung.android.spay", "w", 1792236000500L);
        wallet.title = "Samsung Wallet";
        wallet.text = "  R$ 12,34 \n";
        NotifyRules.Captured bank = row("com.itau", "i", 1792236000100L);
        bank.title = "Compra aprovada";
        bank.bigText = "texto longo";
        bank.extras.put("android.bigText", "texto longo");
        bank.extras.put("android.subText", "Cartão final 1234");
        bank.groupSummary = true;
        bank.via = NotifyRules.VIA_ACTIVE;

        JSONObject out = new JSONObject(NotifyRules.toJson(Arrays.asList(wallet, bank), 1792236001000L, SAO_PAULO));
        assertEquals(2, out.getInt("count"));
        assertEquals("America/Sao_Paulo", out.getString("time_zone"));
        JSONArray list = out.getJSONArray("notifications");
        // Em ordem de postagem: o banco veio 400 ms antes do Wallet.
        assertEquals("com.itau", list.getJSONObject(0).getString("package"));
        JSONObject first = list.getJSONObject(1);
        assertEquals("Samsung Wallet", first.getString("app"));
        assertEquals("  R$ 12,34 \n", first.getString("text"));
        assertTrue(first.isNull("big_text"));
        assertEquals(1792236000500L, first.getLong("posted_at"));
        assertEquals("2026-10-17T08:20:00.500-03:00", first.getString("posted_at_local"));
        assertEquals(wallet.dedupKey(), first.getString("dedup_key"));
        JSONObject second = list.getJSONObject(0);
        assertTrue(second.getBoolean("group_summary"));
        assertEquals("Cartão final 1234", second.getJSONObject("extras").getString("android.subText"));
        assertEquals(0, first.getJSONObject("extras").length());
        assertEquals("active", second.getString("via"));
    }

    @Test
    public void theTextExportListsEachNotification() {
        NotifyRules.Captured shell = row(NotifyRules.SHELL_PACKAGE, "0|com.android.shell|2020|teste|2000", 1792236000000L);
        shell.title = "Compra aprovada";
        shell.bigText = "Compra de R$ 10,00 em LOJA TESTE";
        shell.extras.put("android.title", "Compra aprovada");
        shell.extras.put("android.bigText", "Compra de R$ 10,00 em LOJA TESTE");
        shell.extras.put("android.textLines", "linha 1\nlinha 2");
        String text = NotifyRules.toText(Collections.singletonList(shell), 1792236001000L, SAO_PAULO);
        assertTrue(text.startsWith("Finanças: notificações capturadas (1)\n"));
        assertTrue(text.contains("Teste (adb) (com.android.shell)"));
        assertTrue(text.contains("título: Compra aprovada\n"));
        assertTrue(text.contains("texto longo: Compra de R$ 10,00 em LOJA TESTE\n"));
        // Os outros extras aparecem pelo nome; os tres de cima nao se repetem.
        assertTrue(text.contains("android.textLines: linha 1\nlinha 2\n"));
        assertFalse(text.contains("android.title:"));
        assertFalse(text.contains("android.bigText:"));
        // Campo que nao veio nao aparece (nem como "null").
        assertFalse(text.contains("texto: "));
        assertFalse(text.contains("null"));
        assertTrue(text.contains("2026-10-17T08:20:00.000-03:00"));
    }

    @Test
    public void anEmptyExportIsStillValid() throws Exception {
        JSONObject out = new JSONObject(NotifyRules.toJson(Collections.emptyList(), 0L, SAO_PAULO));
        assertEquals(0, out.getInt("count"));
        assertTrue(NotifyRules.toText(Collections.emptyList(), 0L, SAO_PAULO).contains("(0)"));
    }
}
