package br.financas.app.notify;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.json.JSONArray;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;

import br.financas.app.outbox.DeviceKey;
import br.financas.app.outbox.Session;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

public class DetectionSenderTest {

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
    public void aBatchCarriesTheDeviceKey() throws Exception {
        server.enqueue(new MockResponse().setBody("{\"results\":[]}"));
        DetectionSender.Answer answer = DetectionSender.post(session("chave-1"), new JSONArray());
        RecordedRequest request = server.takeRequest();
        assertEquals("/api/inbox/detections", request.getPath());
        assertEquals("chave-1", request.getHeader(DeviceKey.HEADER));
        assertEquals("Bearer tok", request.getHeader("Authorization"));
        assertEquals(200, answer.status);
        assertFalse(answer.proxyAuth);
    }

    @Test
    public void theProxy401IsNotALoginProblem() throws Exception {
        server.enqueue(new MockResponse().setResponseCode(401).setHeader("X-Proxy-Auth", "required"));
        DetectionSender.Answer answer = DetectionSender.post(session("errada"), new JSONArray());
        // run() devolve "key": a fila fica e o worker tenta de novo.
        assertTrue(answer.proxyAuth);
    }

    @Test
    public void theApp401IsStillALoginProblem() throws Exception {
        server.enqueue(new MockResponse().setResponseCode(401));
        DetectionSender.Answer answer = DetectionSender.post(session("certa"), new JSONArray());
        assertFalse(answer.proxyAuth);
        assertEquals(401, answer.status);
    }
}
