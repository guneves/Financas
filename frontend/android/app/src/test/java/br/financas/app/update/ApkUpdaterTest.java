package br.financas.app.update;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import org.junit.After;
import org.junit.Before;
import org.junit.Test;

import java.io.IOException;
import java.net.HttpURLConnection;

import br.financas.app.outbox.DeviceKey;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

public class ApkUpdaterTest {

    private MockWebServer server;

    @Before
    public void setUp() throws Exception {
        server = new MockWebServer();
        server.start();
    }

    @After
    public void tearDown() throws Exception {
        server.shutdown();
    }

    private String base() {
        return server.url("/").toString().replaceAll("/+$", "");
    }

    @Test
    public void theManifestRequestCarriesTheDeviceKey() throws Exception {
        server.enqueue(new MockResponse().setResponseCode(404));
        assertNull(ApkUpdater.fetchLatest(base(), "chave-1"));
        RecordedRequest request = server.takeRequest();
        assertEquals(ApkUpdateRules.MANIFEST_PATH, request.getPath());
        assertEquals("chave-1", request.getHeader(DeviceKey.HEADER));
    }

    @Test
    public void theDownloadConnectionCarriesTheDeviceKey() throws Exception {
        server.enqueue(new MockResponse().setBody("apk"));
        HttpURLConnection connection = ApkUpdater.open(base() + "/apk/financas-1.apk", "chave-1");
        assertEquals(200, connection.getResponseCode());
        connection.disconnect();
        assertEquals("chave-1", server.takeRequest().getHeader(DeviceKey.HEADER));
    }

    @Test
    public void theProxy401SaysTheKeyIsWrong() throws Exception {
        server.enqueue(new MockResponse().setResponseCode(401).setHeader("X-Proxy-Auth", "required"));
        try {
            ApkUpdater.fetchLatest(base(), "errada");
            fail("Esperava a recusa do proxy");
        } catch (IOException error) {
            assertTrue(error.getMessage().startsWith(DeviceKey.MESSAGE));
        }
    }
}
