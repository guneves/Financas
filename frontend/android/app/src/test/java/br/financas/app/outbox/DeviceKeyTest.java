package br.financas.app.outbox;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

import java.net.HttpURLConnection;
import java.net.URL;

public class DeviceKeyTest {

    @Test
    public void onlyTheProxy401IsAKeyProblem() {
        assertTrue(DeviceKey.isProxyAuthRequired(401, "required"));
        assertTrue(DeviceKey.isProxyAuthRequired(401, " Required "));
        // O 401 do app (login vencido) nao traz o cabecalho: e outra coisa.
        assertFalse(DeviceKey.isProxyAuthRequired(401, null));
        assertFalse(DeviceKey.isProxyAuthRequired(401, "other"));
        assertFalse(DeviceKey.isProxyAuthRequired(403, "required"));
        assertFalse(DeviceKey.isProxyAuthRequired(200, "required"));
    }

    @Test
    public void aPastedKeyLosesSpacesAndLineBreaks() {
        assertEquals("abcDEF-_123", DeviceKey.normalize("  abc DEF-_\n123\r\n"));
        assertEquals("", DeviceKey.normalize(null));
        assertEquals("", DeviceKey.normalize("   "));
    }

    @Test
    public void applyPutsTheKeyOnTheConnection() throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL("https://example.invalid/api/health").openConnection();
        DeviceKey.apply(connection, " chave-123 ");
        assertEquals("chave-123", connection.getRequestProperty(DeviceKey.HEADER));
    }

    @Test
    public void withoutAKeyNoHeaderIsSent() throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL("https://example.invalid/api/health").openConnection();
        DeviceKey.apply(connection, "");
        DeviceKey.apply(connection, null);
        assertNull(connection.getRequestProperty(DeviceKey.HEADER));
    }
}
