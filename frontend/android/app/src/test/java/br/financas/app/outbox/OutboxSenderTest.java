package br.financas.app.outbox;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.json.JSONObject;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

public class OutboxSenderTest {

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

    private Session session(String key) {
        return Session.of(server.url("/").toString(), "tok", "u1", key);
    }

    @Test
    public void aCreationCarriesTheDeviceKeyAndTheToken() throws Exception {
        server.enqueue(new MockResponse().setResponseCode(201).setBody("{\"id\":\"t1\"}"));
        OutboxSender.Response response = OutboxSender.post(session("chave-1"), "/api/transactions", new JSONObject().put("amount", 10));
        RecordedRequest request = server.takeRequest();
        assertEquals("chave-1", request.getHeader(DeviceKey.HEADER));
        assertEquals("Bearer tok", request.getHeader("Authorization"));
        assertEquals(201, response.status);
        assertFalse(response.proxyAuth);
    }

    @Test
    public void withoutAKeyTheHeaderIsAbsent() throws Exception {
        server.enqueue(new MockResponse().setResponseCode(201).setBody("{}"));
        OutboxSender.post(session(""), "/api/transactions", new JSONObject());
        assertNull(server.takeRequest().getHeader(DeviceKey.HEADER));
    }

    @Test
    public void theProxy401KeepsTheItemForARetry() throws Exception {
        server.enqueue(new MockResponse().setResponseCode(401).setHeader("X-Proxy-Auth", "required"));
        OutboxSender.Response response = OutboxSender.post(session("errada"), "/api/transactions", new JSONObject());
        assertTrue(response.proxyAuth);
        assertEquals(OutboxRules.Outcome.RETRY, OutboxRules.outcomeOf(response.network, response.proxyAuth, response.status));
    }

    @Test
    public void theApp401StillStops() throws Exception {
        server.enqueue(new MockResponse().setResponseCode(401).setBody("{\"message\":\"Token expirado\"}"));
        OutboxSender.Response response = OutboxSender.post(session("certa"), "/api/transactions", new JSONObject());
        assertFalse(response.proxyAuth);
        assertEquals(OutboxRules.Outcome.STOP, OutboxRules.outcomeOf(response.network, response.proxyAuth, response.status));
    }
}
